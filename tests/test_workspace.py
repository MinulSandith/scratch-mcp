import os
import zipfile

import pytest

from scratch_mcp.workspace import Sb3, Workspace, WorkspaceError


def test_resolve_accepts_names_with_or_without_extension(root):
    ws = Workspace(root)
    assert ws.resolve("sample") == root / "sample.sb3"
    assert ws.resolve("sample.sb3") == root / "sample.sb3"
    assert ws.resolve(str(root / "sample.sb3")) == root / "sample.sb3"


@pytest.mark.parametrize("bad", ["../escape.sb3", "../../etc/passwd", "/etc/passwd", "sub/../../x.sb3", "~/x.sb3"])
def test_resolve_rejects_paths_outside_root(root, bad):
    with pytest.raises(WorkspaceError, match="outside the Scratch projects folder|not found"):
        Workspace(root).resolve(bad, must_exist=False)


def test_resolve_rejects_symlink_escape(root, tmp_path):
    outside = tmp_path / "outside.sb3"
    outside.write_bytes(b"x")
    os.symlink(outside, root / "link.sb3")
    with pytest.raises(WorkspaceError, match="outside"):
        Workspace(root).resolve("link.sb3")


def test_resolve_rejects_backups_and_missing(root):
    ws = Workspace(root)
    with pytest.raises(WorkspaceError, match="Backups are read-only"):
        ws.resolve("backups/sample.20240101-000000.sb3", must_exist=False)
    with pytest.raises(WorkspaceError, match="not found"):
        ws.resolve("nope")
    with pytest.raises(WorkspaceError, match="empty"):
        ws.resolve("  ")


def test_root_is_created_and_tilde_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    ws = Workspace("~/New Folder/Scratch")
    assert ws.root == (tmp_path / "New Folder" / "Scratch").resolve()
    assert ws.root.is_dir()


def test_list_projects_skips_backups_and_includes_subfolders(root):
    ws = Workspace(root)
    (root / "sub").mkdir()
    (root / "sub" / "b.sb3").write_bytes(b"")
    (root / "notes.txt").write_text("hi")
    ws.backup(root / "sample.sb3")
    names = [ws.display(p) for p in ws.list_projects()]
    assert names == ["sample.sb3", "sub/b.sb3"]


def test_backup_names_are_timestamped_and_never_collide(root):
    ws = Workspace(root)
    first = ws.backup(root / "sample.sb3")
    second = ws.backup(root / "sample.sb3")
    assert first != second
    assert first.parent == root / "backups"
    assert first.name.startswith("sample.") and first.suffix == ".sb3"
    assert first.read_bytes() == (root / "sample.sb3").read_bytes() == second.read_bytes()


def test_write_backs_up_before_overwriting(root):
    ws = Workspace(root)
    path = root / "sample.sb3"
    original = path.read_bytes()
    sb3 = ws.load(path)
    sb3.project["targets"][1]["x"] = 99
    backup = ws.write(path, sb3, overwrite=True)
    assert backup is not None and backup.read_bytes() == original
    assert ws.load(path).project["targets"][1]["x"] == 99
    assert not [p for p in root.iterdir() if p.name.startswith(".tmp-")]


def test_write_without_overwrite_refuses_existing(root):
    ws = Workspace(root)
    with pytest.raises(WorkspaceError, match="already exists"):
        ws.write(root / "sample.sb3", Sb3({"targets": []}, {}), overwrite=False)


def test_load_rejects_non_sb3(root):
    ws = Workspace(root)
    (root / "fake.sb3").write_text("not a zip")
    with pytest.raises(WorkspaceError, match="not a valid"):
        ws.load(root / "fake.sb3")
    with zipfile.ZipFile(root / "empty.sb3", "w") as zf:
        zf.writestr("other.txt", "x")
    with pytest.raises(WorkspaceError, match="no project.json"):
        ws.load(root / "empty.sb3")
