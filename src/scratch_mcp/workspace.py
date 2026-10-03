"""Filesystem access, confined to one projects folder.

Every path a tool receives goes through ``Workspace.resolve`` which rejects
anything that ends up outside the root (``..``, absolute paths elsewhere,
symlinks pointing out of the folder).
"""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

BACKUP_DIR_NAME = "backups"


class WorkspaceError(Exception):
    """A user-facing error (bad path, missing file, invalid project...)."""


@dataclass
class Sb3:
    """An .sb3 file loaded into memory."""

    project: dict[str, Any]
    assets: dict[str, bytes]  # every zip member except project.json


class Workspace:
    def __init__(self, root: str | os.PathLike[str]):
        root_path = Path(root).expanduser()
        root_path.mkdir(parents=True, exist_ok=True)
        self.root = root_path.resolve()
        self.backup_dir = self.root / BACKUP_DIR_NAME

    # -- paths -------------------------------------------------------------

    def resolve(self, name: str, *, must_exist: bool = True) -> Path:
        """Turn a project name / relative path into a safe absolute .sb3 path."""
        if not name or not name.strip():
            raise WorkspaceError("Project name is empty.")
        name = name.strip()
        if "\x00" in name:
            raise WorkspaceError("Invalid project name.")
        if not name.lower().endswith(".sb3"):
            name += ".sb3"
        candidate = Path(name).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root) or resolved == self.root:
            raise WorkspaceError(
                f"Access denied: '{name}' is outside the Scratch projects folder ({self.root})."
            )
        if resolved.is_relative_to(self.backup_dir):
            raise WorkspaceError("Backups are read-only; copy one out of the backups folder first.")
        if must_exist and not resolved.is_file():
            raise WorkspaceError(f"Project not found: {self.display(resolved)}")
        return resolved

    def resolve_file(self, name: str | None, *, must_exist: bool = True) -> Path:
        """Any file (not only .sb3) inside the projects folder - never outside, never in backups/."""
        if not name or not str(name).strip():
            raise WorkspaceError("File path is empty.")
        candidate = Path(str(name).strip()).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root) or resolved == self.root:
            raise WorkspaceError(f"Access denied: '{name}' is outside the Scratch projects folder ({self.root}).")
        if must_exist and not resolved.is_file():
            raise WorkspaceError(f"File not found: {self.display(resolved)}")
        return resolved

    def display(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def list_projects(self) -> list[Path]:
        found = []
        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() != ".sb3" or not path.is_file():
                continue
            if path.resolve().is_relative_to(self.backup_dir):
                continue
            if not path.resolve().is_relative_to(self.root):  # symlink escaping the root
                continue
            found.append(path)
        return found

    # -- reading / writing ----------------------------------------------------

    def load(self, path: Path) -> Sb3:
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                if "project.json" not in names:
                    raise WorkspaceError(f"{self.display(path)} has no project.json - is it a Scratch 3 file?")
                project = json.loads(zf.read("project.json").decode("utf-8"))
                assets = {n: zf.read(n) for n in names if n != "project.json" and not n.endswith("/")}
        except zipfile.BadZipFile as exc:
            raise WorkspaceError(f"{self.display(path)} is not a valid .sb3 (zip) file.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceError(f"{self.display(path)} contains an unreadable project.json: {exc}") from exc
        if not isinstance(project, dict):
            raise WorkspaceError(f"{self.display(path)}: project.json is not a JSON object.")
        return Sb3(project, assets)

    def backup(self, path: Path) -> Path:
        """Copy ``path`` into backups/ with a timestamp. Returns the backup path."""
        rel = path.relative_to(self.root)
        dest_dir = self.backup_dir / rel.parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = dest_dir / f"{path.stem}.{stamp}.sb3"
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{path.stem}.{stamp}-{counter}.sb3"
            counter += 1
        data = path.read_bytes()
        with open(dest, "xb") as fh:  # "x": never overwrite an existing backup
            fh.write(data)
        return dest

    def prune_backups(self, path: Path, keep: int) -> None:
        """Keep only the newest ``keep`` backups of one project (0 = keep everything)."""
        if keep <= 0:
            return
        rel = path.relative_to(self.root)
        folder = self.backup_dir / rel.parent
        mine = sorted(folder.glob(f"{path.stem}.????????-??????*.sb3"), key=lambda p: p.stat().st_mtime)
        for old in mine[:-keep]:
            old.unlink(missing_ok=True)

    def write(self, path: Path, sb3: Sb3, *, overwrite: bool) -> Path | None:
        """Write an .sb3. If the file exists it is backed up first.

        Returns the backup path (or None for a brand new file).
        """
        backup = None
        if path.exists():
            if not overwrite:
                raise WorkspaceError(f"{self.display(path)} already exists.")
            backup = self.backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same folder, then atomically swap it in.
        fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=".sb3", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as fh, zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("project.json", json.dumps(sb3.project, ensure_ascii=False, separators=(",", ":")))
                for name, data in sb3.assets.items():
                    zf.writestr(name, data)
            if not overwrite and path.exists():
                raise WorkspaceError(f"{self.display(path)} already exists.")
            os.replace(tmp_name, path)
        except BaseException:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise
        return backup
