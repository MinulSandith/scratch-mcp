"""list_projects, read_project, get_project_json, save_project_json, create_project."""

import hashlib
import json

import pytest

from scratch_mcp.validate import validate_project
from scratch_mcp.workspace import WorkspaceError

from .conftest import read_sb3, target


def test_list_projects(tools, root):
    out = tools.list_projects()
    assert [p["project"] for p in out["projects"]] == ["sample.sb3"]


def test_list_projects_empty(tmp_path):
    from scratch_mcp.ctx import Ctx

    from .conftest import Tools

    assert Tools(Ctx(tmp_path / "empty")).list_projects()["projects"] == []


def test_read_project_summary(tools):
    text = tools.read_project("sample")
    assert "Sprites: 2 | Extensions: pen" in text
    assert "## Sprite: Cat" in text and "## Sprite: Ball" in text
    assert "Costumes: costume1 (current), costume2" in text
    assert "  - score = 0" in text  # global variable
    assert "  - speed = 0" in text  # Ball's local variable
    assert '  - hits: 2 items ["3", "7"]' in text
    assert "Broadcasts: game over" in text
    expected_script = "\n".join([
        "when this sprite clicked",
        "change [score v] by (1)",
        "if <(score) > (10)> then",
        "  switch costume to (costume2 v)",
        "else",
        "  next costume",
        "end",
        "play sound (Meow v) until done",
    ])
    assert expected_script in text
    assert "define draw square (size)\nrepeat (4)\n  move (size) steps\n  turn left (90) degrees\nend" in text
    assert "when flag clicked\nreset timer\nwait until <(timer) > (5)>\nstop [all v]" in text


def test_get_project_json_matches_file(tools, root):
    on_disk, _ = read_sb3(root / "sample.sb3")
    assert json.loads(tools.get_project_json("sample")) == on_disk
    compact = tools.get_project_json("sample", pretty=False)
    assert "\n" not in compact and json.loads(compact) == on_disk


def test_tools_reject_outside_paths(tools):
    for call in (
        lambda: tools.read_project("../secret"),
        lambda: tools.get_project_json("/etc/passwd"),
        lambda: tools.save_project_json("../x", "{}"),
        lambda: tools.create_project("../x"),
        lambda: tools.add_script("../x", "Cat", "move (1) steps"),
    ):
        with pytest.raises(WorkspaceError):
            call()


# -- save_project_json -------------------------------------------------------

def test_save_valid_edit_creates_backup_and_keeps_assets(tools, root):
    original_bytes = (root / "sample.sb3").read_bytes()
    project = json.loads(tools.get_project_json("sample"))
    target(project, "Cat")["x"] = -150
    target(project, "Cat")["name"] = "Kitty"

    out = tools.save_project_json("sample", json.dumps(project))

    assert out["saved"] == "sample.sb3" and out["backups_made"][0].startswith("backups/sample.")
    saved, assets = read_sb3(root / "sample.sb3")
    assert target(saved, "Kitty")["x"] == -150
    assert assets == {"83a9787d4cb6f3b7632b4ddfebf74367.wav", "83c36d806dc92327b9e7049a565c6bff.wav",
                      "cd21514d0531fdffb22204e0ec5ed84a.svg", "bcf454acf82e4504149f7ffe07081dbc.svg",
                      "0fb9be3e8397c983338cb71dc84d0b25.svg"}
    backups = list((root / "backups").glob("sample.*.sb3"))
    assert len(backups) == 1 and backups[0].read_bytes() == original_bytes


def test_save_accepts_object_as_well_as_string(tools, root):
    project = json.loads(tools.get_project_json("sample"))
    project["targets"][1]["size"] = 50
    tools.save_project_json("sample", project)
    assert read_sb3(root / "sample.sb3")[0]["targets"][1]["size"] == 50


def _assert_not_saved(tools, root, payload, match):
    before = (root / "sample.sb3").read_bytes()
    with pytest.raises(WorkspaceError, match=match):
        tools.save_project_json("sample", payload)
    assert (root / "sample.sb3").read_bytes() == before
    assert not (root / "backups").exists()


def test_save_rejects_invalid_json(tools, root):
    _assert_not_saved(tools, root, '{"targets": [', "Invalid JSON")


def test_save_rejects_duplicate_block_ids(tools, root):
    text = tools.get_project_json("sample", pretty=False)
    project = json.loads(text)
    blocks = target(project, "Ball")["blocks"]
    block_id, block = next(iter(blocks.items()))
    # Hand-craft JSON with the same key twice inside "blocks".
    dup = json.dumps(block)
    raw = json.dumps(project).replace(f'"{block_id}": {dup}', f'"{block_id}": {dup}, "{block_id}": {dup}', 1)
    assert raw.count(f'"{block_id}": {{') == 2
    _assert_not_saved(tools, root, raw, "Duplicate keys")


def test_save_rejects_broken_links(tools, root):
    project = json.loads(tools.get_project_json("sample"))
    blocks = target(project, "Cat")["blocks"]
    hat_id = next(i for i, b in blocks.items() if b["opcode"] == "event_whenthisspriteclicked")
    blocks[hat_id]["next"] = "doesNotExist"
    _assert_not_saved(tools, root, json.dumps(project), "points to missing block 'doesNotExist'")


def test_save_rejects_unknown_opcode(tools, root):
    project = json.loads(tools.get_project_json("sample"))
    blocks = target(project, "Cat")["blocks"]
    some = next(b for b in blocks.values() if b["opcode"] == "motion_movesteps")
    some["opcode"] = "motion_teleport"
    _assert_not_saved(tools, root, json.dumps(project), "unknown opcode 'motion_teleport'")


def test_save_rejects_missing_costume_file(tools, root):
    project = json.loads(tools.get_project_json("sample"))
    target(project, "Cat")["costumes"][0]["md5ext"] = "ffffffffffffffffffffffffffffffff.png"
    _assert_not_saved(tools, root, json.dumps(project), "not in the .sb3")


def test_save_requires_existing_project(tools):
    with pytest.raises(WorkspaceError, match="not found"):
        tools.save_project_json("new-one", "{}")


# -- create_project ----------------------------------------------------------

def test_create_project_has_cat_and_is_valid(tools, root):
    out = tools.create_project("My Game", sprite_name="Hero")
    assert out["created"] == "My Game.sb3"
    project, assets = read_sb3(root / "My Game.sb3")
    stage, hero = project["targets"]
    assert stage["isStage"] and hero["name"] == "Hero"
    assert hero["costumes"][0]["md5ext"] == "bcf454acf82e4504149f7ffe07081dbc.svg"
    assert validate_project(project, assets).ok
    # Asset file names are the md5 of their content, as Scratch requires.
    import zipfile

    with zipfile.ZipFile(root / "My Game.sb3") as zf:
        for name in assets:
            assert hashlib.md5(zf.read(name)).hexdigest() == name.split(".")[0]


def test_create_project_never_overwrites(tools, root):
    before = (root / "sample.sb3").read_bytes()
    with pytest.raises(WorkspaceError, match="already exists"):
        tools.create_project("sample")
    assert (root / "sample.sb3").read_bytes() == before


def test_create_project_in_subfolder(tools, root):
    tools.create_project("class/week1")
    assert (root / "class" / "week1.sb3").is_file()
    assert "class/week1.sb3" in [p["project"] for p in tools.list_projects()["projects"]]
