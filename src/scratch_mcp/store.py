"""Open-project sessions: in-memory state, undo/redo history, dirty tracking, saving.

Every change goes through ``ProjectStore.edit``. It works on a copy, validates the result and
only then commits it, so a failed edit never leaves a half-changed project behind.

By default ``autosave`` is on: each committed edit is written to disk straight away, after a
timestamped backup of the previous file. Turn it off and edits stay in memory (``dirty``)
until ``save`` is called; ``undo``/``redo`` work either way.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .validate import validate_project
from .workspace import Sb3, Workspace, WorkspaceError

HISTORY_LIMIT = 100


@dataclass
class Snapshot:
    label: str
    project_json: str
    assets: dict[str, bytes]


@dataclass
class Session:
    name: str  # path relative to the projects folder, with .sb3
    path: Path
    project: dict[str, Any]
    assets: dict[str, bytes]
    autosave: bool = True
    dirty: bool = False
    selected_sprite: str | None = None
    undo_stack: list[Snapshot] = field(default_factory=list)
    redo_stack: list[Snapshot] = field(default_factory=list)
    disk_signature: str | None = None  # hash of the file as last read/written
    last_saved: str | None = None
    opened_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def snapshot(self, label: str) -> Snapshot:
        return Snapshot(label, json.dumps(self.project, ensure_ascii=False), dict(self.assets))

    def restore(self, snap: Snapshot) -> None:
        self.project = json.loads(snap.project_json)
        self.assets = dict(snap.assets)

    def info(self) -> dict[str, Any]:
        return {
            "project": self.name,
            "dirty": self.dirty,
            "autosave": self.autosave,
            "selected_sprite": self.selected_sprite,
            "can_undo": bool(self.undo_stack),
            "can_redo": bool(self.redo_stack),
            "last_undo_label": self.undo_stack[-1].label if self.undo_stack else None,
            "last_saved": self.last_saved,
        }


class EditHandle:
    """Working copy handed to edit callbacks."""

    def __init__(self, session: Session):
        self.session = session
        self.project: dict[str, Any] = copy.deepcopy(session.project)
        self.assets: dict[str, bytes] = dict(session.assets)
        self.notes: list[str] = []


def _signature(path: Path) -> str | None:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return None


class ProjectStore:
    def __init__(self, ws: Workspace, backup_keep: int | None = None):
        self.ws = ws
        self.sessions: dict[str, Session] = {}
        self.backup_events: list[str] = []  # backups made since the list was last cleared (reported to the caller)
        self.active: str | None = None
        self.backup_keep = backup_keep if backup_keep is not None else int(os.environ.get("SCRATCH_MCP_BACKUPS", "100"))

    # -- lookup ----------------------------------------------------------

    def key_for(self, name: str) -> tuple[str, Path]:
        path = self.ws.resolve(name, must_exist=False)
        return self.ws.display(path), path

    def open(self, name: str, *, reload: bool = False) -> Session:
        key, path = self.key_for(name)
        if not path.is_file():
            raise WorkspaceError(f"Project not found: {key}")
        session = self.sessions.get(key)
        if session is not None and not reload:
            sig = _signature(path)
            if sig != session.disk_signature and not session.dirty:
                reload = True  # changed outside (e.g. saved from the Scratch app): pick it up
            else:
                self.active = key
                return session
        sb3 = self.ws.load(path)
        if session is None or reload:
            keep_auto = session.autosave if session else True
            session = Session(key, path, sb3.project, sb3.assets, autosave=keep_auto)
            session.disk_signature = _signature(path)
            session.last_saved = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
            self.sessions[key] = session
        self.active = key
        return session

    def get(self, name: str | None = None) -> Session:
        """Session for ``name``, or the active project when ``name`` is omitted."""
        if not name:
            if not self.active or self.active not in self.sessions:
                raise WorkspaceError(
                    "No project specified and none is open. Pass 'project' or call project_manager open/create first."
                )
            return self.open(self.active)
        return self.open(name)

    # -- editing -----------------------------------------------------------

    @contextmanager
    def edit(self, name: str | None, label: str) -> Iterator[EditHandle]:
        session = self.get(name)
        handle = EditHandle(session)
        yield handle
        self.commit(session, handle, label)

    def commit(self, session: Session, handle: EditHandle, label: str) -> None:
        result = validate_project(handle.project, set(handle.assets))
        if not result.ok:
            raise WorkspaceError(f"Not applied - the project would be invalid:\n{result.format()}")
        if json.dumps(handle.project, sort_keys=True) == json.dumps(session.project, sort_keys=True) and handle.assets.keys() == session.assets.keys():
            return  # nothing changed
        session.undo_stack.append(session.snapshot(label))
        del session.undo_stack[:-HISTORY_LIMIT]
        session.redo_stack.clear()
        session.project, session.assets = handle.project, handle.assets
        session.dirty = True
        if result.warnings:
            handle.notes.append(result.format())
        if session.autosave:
            self._write(session)

    def undo(self, name: str | None = None) -> str:
        session = self.get(name)
        if not session.undo_stack:
            raise WorkspaceError("Nothing to undo.")
        snap = session.undo_stack.pop()
        session.redo_stack.append(session.snapshot(snap.label))
        session.restore(snap)
        session.dirty = True
        if session.autosave:
            self._write(session)
        return snap.label

    def redo(self, name: str | None = None) -> str:
        session = self.get(name)
        if not session.redo_stack:
            raise WorkspaceError("Nothing to redo.")
        snap = session.redo_stack.pop()
        session.undo_stack.append(session.snapshot(snap.label))
        session.restore(snap)
        session.dirty = True
        if session.autosave:
            self._write(session)
        return snap.label

    # -- persistence ---------------------------------------------------------

    def _write(self, session: Session, path: Path | None = None) -> Path | None:
        target = path or session.path
        backup = self.ws.write(target, Sb3(session.project, session.assets), overwrite=True) if target.exists() \
            else self.ws.write(target, Sb3(session.project, session.assets), overwrite=False)
        if backup:
            self.backup_events.append(self.ws.display(backup))
            self.ws.prune_backups(target, self.backup_keep)
        if target == session.path:
            session.dirty = False
            session.disk_signature = _signature(target)
            session.last_saved = datetime.now().isoformat(timespec="seconds")
        return backup

    def save(self, name: str | None = None) -> tuple[Session, Path | None]:
        session = self.get(name)
        return session, self._write(session)

    def save_as(self, new_name: str, name: str | None = None, overwrite: bool = False) -> Session:
        """Write the open project under a new name and switch the session to it."""
        session = self.get(name)
        key, path = self.key_for(new_name)
        if path.exists() and not overwrite:
            raise WorkspaceError(f"{key} already exists. Pass overwrite=true to replace it (a backup is made).")
        self._write(session, path)
        clone = Session(key, path, copy.deepcopy(session.project), dict(session.assets), autosave=session.autosave,
                        selected_sprite=session.selected_sprite)
        clone.disk_signature = _signature(path)
        clone.last_saved = datetime.now().isoformat(timespec="seconds")
        self.sessions[key] = clone
        self.active = key
        return clone

    def create(self, name: str, project: dict[str, Any], assets: dict[str, bytes]) -> Session:
        key, path = self.key_for(name)
        if path.exists():
            raise WorkspaceError(f"{key} already exists. Existing projects are never overwritten; pick another name.")
        result = validate_project(project, set(assets))
        if not result.ok:
            raise WorkspaceError(f"Invalid project:\n{result.format()}")
        session = Session(key, path, project, assets)
        self.ws.write(path, Sb3(project, assets), overwrite=False)
        session.disk_signature = _signature(path)
        session.last_saved = datetime.now().isoformat(timespec="seconds")
        self.sessions[key] = session
        self.active = key
        return session

    def close(self, name: str | None = None, discard: bool = False) -> str:
        session = self.get(name)
        if session.dirty and not discard:
            raise WorkspaceError(
                f"{session.name} has unsaved changes. Save it first or pass discard=true to throw them away."
            )
        del self.sessions[session.name]
        if self.active == session.name:
            self.active = next(iter(self.sessions), None)
        return session.name

    def reset(self, name: str | None = None) -> Session:
        """Throw away unsaved changes and history; reload from disk."""
        session = self.get(name)
        return self.open(session.name, reload=True)

    def rename(self, name: str, new_name: str) -> str:
        key, path = self.key_for(name)
        if not path.is_file():
            raise WorkspaceError(f"Project not found: {key}")
        session = self.sessions.get(key)
        if session and session.dirty:
            raise WorkspaceError(f"{key} has unsaved changes; save it before renaming.")
        new_key, new_path = self.key_for(new_name)
        if new_path.exists():
            raise WorkspaceError(f"{new_key} already exists.")
        new_path.parent.mkdir(parents=True, exist_ok=True)
        path.rename(new_path)
        self.sessions.pop(key, None)
        if self.active == key:
            self.active = None
        self.open(new_key)
        return new_key

    def duplicate(self, name: str, new_name: str) -> str:
        session = self.get(name)
        key, path = self.key_for(new_name)
        if path.exists():
            raise WorkspaceError(f"{key} already exists.")
        self.ws.write(path, Sb3(copy.deepcopy(session.project), dict(session.assets)), overwrite=False)
        return key

    def delete(self, name: str) -> Path:
        """'Delete' = move the file into backups/deleted/ so it can always be restored."""
        key, path = self.key_for(name)
        if not path.is_file():
            raise WorkspaceError(f"Project not found: {key}")
        dest_dir = self.ws.backup_dir / "deleted"
        dest_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = dest_dir / f"{path.stem}.{stamp}.sb3"
        n = 1
        while dest.exists():
            dest = dest_dir / f"{path.stem}.{stamp}-{n}.sb3"
            n += 1
        path.rename(dest)
        self.sessions.pop(key, None)
        if self.active == key:
            self.active = next(iter(self.sessions), None)
        return dest
