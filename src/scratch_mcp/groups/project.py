"""project_manager: create/open/save/duplicate/rename/delete/import projects, undo/redo, metadata."""

from __future__ import annotations

import base64
import binascii
import io
import zipfile
from pathlib import Path
from typing import Any

from ..ctx import Ctx
from ..registry import GROUP_DOCS, action
from ..render import summarize_project
from ..store import Session
from ..template import blank_project
from ..validate import validate_project
from ..workspace import Sb3, WorkspaceError

G = "project_manager"
GROUP_DOCS[G] = (
    "Manage Scratch project files (.sb3) in the projects folder: create, open, save, save as, duplicate, "
    "rename, delete (moves to backups/deleted), import, inspect, undo/redo, unsaved-change tracking. "
    "One project is 'active' (the last opened/created); other tools default to it."
)


def project_info(session: Session) -> dict[str, Any]:
    p = session.project
    targets = p.get("targets") or []
    return {
        **session.info(),
        "meta": p.get("meta"),
        "extensions": p.get("extensions") or [],
        "sprites": [t["name"] for t in targets if not t.get("isStage")],
        "counts": {
            "sprites": sum(1 for t in targets if not t.get("isStage")),
            "blocks": sum(len(t.get("blocks") or {}) for t in targets),
            "costumes": sum(len(t.get("costumes") or []) for t in targets),
            "sounds": sum(len(t.get("sounds") or []) for t in targets),
            "assets_in_file": len(session.assets),
            "asset_bytes": sum(len(b) for b in session.assets.values()),
        },
    }


@action(G)
def list(ctx: Ctx) -> dict:
    """List .sb3 projects in the folder (subfolders included, backups excluded) with open/dirty state."""
    rows = []
    for path in ctx.ws.list_projects():
        key = ctx.ws.display(path)
        s = ctx.store.sessions.get(key)
        rows.append({"project": key, "size_kb": round(path.stat().st_size / 1024, 1),
                     "open": s is not None, "dirty": bool(s and s.dirty), "active": key == ctx.store.active})
    return {"folder": str(ctx.ws.root), "projects": rows}


@action(G)
def create(ctx: Ctx, name: str, sprite_name: str = "Sprite1", empty: bool = False) -> dict:
    """Create a new project (Stage + one sprite with the default cat) and make it active.

    Args:
        name: file name, e.g. "My Game" (".sb3" optional; subfolders allowed).
        sprite_name: name of the first sprite.
        empty: true = Stage only, no sprites (add sprites with sprite_manager).
    """
    project, assets = blank_project(sprite_name.strip() or "Sprite1")
    if empty:
        project["targets"] = project["targets"][:1]
        used = {a["md5ext"] for t in project["targets"] for k in ("costumes", "sounds") for a in t[k]}
        assets = {n: d for n, d in assets.items() if n in used}
    session = ctx.store.create(name, project, assets)
    if not empty:
        session.selected_sprite = sprite_name.strip() or "Sprite1"
    return {"created": session.name, **project_info(session)}


@action(G)
def open(ctx: Ctx, name: str, reload: bool = False) -> dict:
    """Open a project (load it into memory) and make it the active project.

    Args:
        name: project file name.
        reload: true = discard in-memory state and re-read the file from disk.
    """
    session = ctx.store.open(name, reload=reload)
    if session.selected_sprite is None:
        sprites = [t["name"] for t in session.project["targets"] if not t.get("isStage")]
        session.selected_sprite = sprites[0] if sprites else None
    return project_info(session)


@action(G)
def close(ctx: Ctx, project: str | None = None, discard: bool = False) -> dict:
    """Close an open project. Refuses if it has unsaved changes unless discard=true."""
    return {"closed": ctx.store.close(project, discard)}


@action(G)
def save(ctx: Ctx, project: str | None = None) -> dict:
    """Write the open project to disk (the previous file is backed up with a timestamp first)."""
    session, backup = ctx.store.save(project)
    return {"saved": session.name, "backup": ctx.ws.display(backup) if backup else None}


@action(G)
def save_as(ctx: Ctx, new_name: str, project: str | None = None, overwrite: bool = False) -> dict:
    """Save under a new name; the session then points at the new file.

    Args:
        new_name: new project name.
        overwrite: replace an existing file of that name (it is backed up first).
    """
    session = ctx.store.save_as(new_name, project, overwrite)
    return {"saved_as": session.name}


@action(G)
def duplicate(ctx: Ctx, new_name: str, project: str | None = None) -> dict:
    """Copy a project to a new file (the active project does not change)."""
    return {"duplicated_to": ctx.store.duplicate(project or ctx.store.get(None).name, new_name)}


@action(G)
def rename(ctx: Ctx, name: str, new_name: str) -> dict:
    """Rename a project file (must have no unsaved changes)."""
    return {"renamed_to": ctx.store.rename(name, new_name)}


@action(G)
def delete(ctx: Ctx, name: str) -> dict:
    """'Delete' a project by moving it to backups/deleted/<name>.<timestamp>.sb3 so it can be restored."""
    dest = ctx.store.delete(name)
    return {"deleted": name, "moved_to": ctx.ws.display(dest)}


@action(G)
def import_sb3(ctx: Ctx, name: str, source_path: str | None = None, data_base64: str | None = None,
               overwrite: bool = False) -> dict:
    """Import an .sb3 as a new project (validated first).

    Args:
        name: name for the imported project.
        source_path: .sb3 file inside the projects folder to import (for example one saved from the Scratch app).
        data_base64: alternatively the raw bytes of an .sb3 file, base64 encoded.
        overwrite: replace an existing project of that name (backed up first).
    """
    if bool(source_path) == bool(data_base64):
        raise WorkspaceError("Give exactly one of source_path or data_base64.")
    if source_path:
        src = ctx.ws.resolve(source_path)
        data = src.read_bytes()
    else:
        try:
            data = base64.b64decode(data_base64 or "", validate=False)
        except (binascii.Error, ValueError) as exc:
            raise WorkspaceError("data_base64 is not valid base64.") from exc
    sb3 = load_sb3_bytes(ctx, data)
    result = validate_project(sb3.project, set(sb3.assets))
    if not result.ok:
        raise WorkspaceError(f"Imported file is not a valid Scratch 3 project:\n{result.format()}")
    key, path = ctx.store.key_for(name)
    if path.exists():
        if not overwrite:
            raise WorkspaceError(f"{key} already exists. Pass overwrite=true to replace it (a backup is made).")
        ctx.store.sessions.pop(key, None)
        ctx.ws.write(path, sb3, overwrite=True)
        session = ctx.store.open(key)
    else:
        session = ctx.store.create(name, sb3.project, sb3.assets)
    return {"imported": session.name, "warnings": result.warnings[:10], **project_info(session)}


def load_sb3_bytes(ctx: Ctx, data: bytes) -> Sb3:
    import json

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if "project.json" not in zf.namelist():
                raise WorkspaceError("Not a Scratch 3 file: no project.json inside.")
            project = json.loads(zf.read("project.json").decode("utf-8"))
            assets = {n: zf.read(n) for n in zf.namelist() if n != "project.json" and not n.endswith("/")}
    except zipfile.BadZipFile as exc:
        raise WorkspaceError("Not a valid .sb3 (zip) file. Scratch 2 (.sb2) files are not supported.") from exc
    except (UnicodeDecodeError, ValueError) as exc:
        raise WorkspaceError(f"project.json is unreadable: {exc}") from exc
    if not isinstance(project, dict):
        raise WorkspaceError("project.json is not a JSON object.")
    return Sb3(project, assets)


@action(G)
def info(ctx: Ctx, project: str | None = None) -> dict:
    """Project metadata, sprite list, counts, extensions, dirty/undo state."""
    return project_info(ctx.session(project))


@action(G)
def status(ctx: Ctx) -> dict:
    """All open projects with their unsaved-change flags."""
    return {"active": ctx.store.active, "open": [s.info() for s in ctx.store.sessions.values()]}


@action(G)
def summary(ctx: Ctx, project: str | None = None) -> str:
    """Readable text summary: sprites, costumes, sounds, variables, lists and every script as block text."""
    s = ctx.session(project)
    return summarize_project(s.name, s.project)


@action(G)
def update_metadata(ctx: Ctx, meta: dict[str, str], project: str | None = None) -> dict:
    """Merge string values into project.json 'meta' (keys: semver, vm, agent, platform...).

    Args:
        meta: e.g. {"agent": "my tool"}. 'semver' must stay "3.0.0" for Scratch 3.
    """
    if "semver" in meta and meta["semver"] != "3.0.0":
        raise WorkspaceError("meta.semver must remain '3.0.0' for Scratch 3 projects.")
    with ctx.store.edit(project, "update metadata") as h:
        h.project.setdefault("meta", {}).update(meta)
    return {"meta": ctx.session(project).project["meta"]}


@action(G)
def set_autosave(ctx: Ctx, enabled: bool, project: str | None = None) -> dict:
    """autosave on (default): every edit is saved with a backup. Off: edits stay in memory until 'save'."""
    s = ctx.session(project)
    s.autosave = enabled
    return s.info()


@action(G)
def undo(ctx: Ctx, project: str | None = None, steps: int = 1) -> dict:
    """Undo the last edit(s) (history holds the last 100 edits per open project)."""
    labels = [ctx.store.undo(project) for _ in range(max(1, steps))]
    return {"undone": labels, **ctx.session(project).info()}


@action(G)
def redo(ctx: Ctx, project: str | None = None, steps: int = 1) -> dict:
    """Redo edits that were undone."""
    labels = [ctx.store.redo(project) for _ in range(max(1, steps))]
    return {"redone": labels, **ctx.session(project).info()}


@action(G)
def history(ctx: Ctx, project: str | None = None) -> dict:
    """List undoable edits, newest last."""
    s = ctx.session(project)
    return {"undo": [x.label for x in s.undo_stack], "redo": [x.label for x in reversed(s.redo_stack)]}


@action(G)
def reset(ctx: Ctx, project: str | None = None) -> dict:
    """Discard unsaved changes and history; reload the project from disk."""
    return project_info(ctx.store.reset(project))


@action(G)
def list_backups(ctx: Ctx, project: str | None = None) -> dict:
    """List timestamped backups of a project (restore one with import_sb3 or by copying it back)."""
    s = ctx.session(project)
    folder = ctx.ws.backup_dir / Path(s.name).parent
    items = sorted(folder.glob(f"{Path(s.name).stem}.????????-??????*.sb3"), key=lambda p: p.stat().st_mtime)
    return {"backups": [{"path": ctx.ws.display(p), "kb": round(p.stat().st_size / 1024, 1)} for p in items]}


@action(G)
def validate(ctx: Ctx, project: str | None = None) -> dict:
    """Structural validation: JSON shape, unique ids, links, opcodes, assets, variable references."""
    s = ctx.session(project)
    r = validate_project(s.project, set(s.assets))
    return {"ok": r.ok, "errors": r.errors, "warnings": r.warnings}
