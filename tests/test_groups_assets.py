import base64
import json
import zipfile

import pytest

from scratch_mcp.runtime.browser import find_chromium
from scratch_mcp.validate import validate_project
from scratch_mcp.workspace import WorkspaceError

from .conftest import call

try:
    import playwright  # noqa: F401
    HAVE_BROWSER = find_chromium() is not None
except ImportError:
    HAVE_BROWSER = False
needs_browser = pytest.mark.skipif(not HAVE_BROWSER, reason="headless Chromium / playwright not available")


@pytest.fixture
def pm(ctx):
    call(ctx, "project_manager", "open", name="sample")
    return ctx


def valid(ctx):
    s = ctx.session(None)
    r = validate_project(s.project, set(s.assets))
    assert r.ok, r.format()


# ---- project_manager -----------------------------------------------------------------

def test_project_lifecycle(ctx, root):
    r = call(ctx, "project_manager", "create", name="Fresh", sprite_name="Hero")
    assert r["created"] == "Fresh.sb3" and r["selected_sprite"] == "Hero"
    assert call(ctx, "project_manager", "list")["projects"][0]["project"] in ("Fresh.sb3", "sample.sb3")
    call(ctx, "project_manager", "set_autosave", enabled=False)
    call(ctx, "sprite_manager", "set", sprite="Hero", x=42)
    st = call(ctx, "project_manager", "status")["open"][0]
    assert st["dirty"] and st["can_undo"]
    assert (root / "Fresh.sb3").exists()
    on_disk = zipfile.ZipFile(root / "Fresh.sb3").read("project.json")
    assert json.loads(on_disk)["targets"][1]["x"] == 0  # not saved yet
    out = call(ctx, "project_manager", "save")
    assert out["backup"].startswith("backups/Fresh.")
    assert json.loads(zipfile.ZipFile(root / "Fresh.sb3").read("project.json"))["targets"][1]["x"] == 42
    call(ctx, "project_manager", "undo")
    assert call(ctx, "sprite_manager", "get", sprite="Hero")["x"] == 0
    call(ctx, "project_manager", "redo")
    assert call(ctx, "sprite_manager", "get", sprite="Hero")["x"] == 42
    with pytest.raises(WorkspaceError, match="unsaved"):
        call(ctx, "project_manager", "close")
    call(ctx, "project_manager", "close", discard=True)


def test_save_as_duplicate_rename_delete_import(ctx, root):
    call(ctx, "project_manager", "open", name="sample")
    call(ctx, "project_manager", "save_as", new_name="copy1")
    assert (root / "copy1.sb3").exists() and call(ctx, "project_manager", "info")["project"] == "copy1.sb3"
    with pytest.raises(WorkspaceError, match="already exists"):
        call(ctx, "project_manager", "save_as", new_name="sample")
    call(ctx, "project_manager", "duplicate", new_name="copy2")
    call(ctx, "project_manager", "rename", name="copy2", new_name="renamed")
    assert (root / "renamed.sb3").exists() and not (root / "copy2.sb3").exists()
    d = call(ctx, "project_manager", "delete", name="renamed")
    assert not (root / "renamed.sb3").exists() and (root / d["moved_to"]).exists()
    r = call(ctx, "project_manager", "import_sb3", name="imported", source_path="sample.sb3")
    assert r["counts"]["sprites"] == 2
    b64 = base64.b64encode((root / "sample.sb3").read_bytes()).decode()
    assert call(ctx, "project_manager", "import_sb3", name="imported2", data_base64=b64)["imported"] == "imported2.sb3"
    with pytest.raises(WorkspaceError):
        call(ctx, "project_manager", "import_sb3", name="bad", data_base64=base64.b64encode(b"nope").decode())
    with pytest.raises(WorkspaceError, match="outside"):
        call(ctx, "project_manager", "import_sb3", name="x", source_path="../../etc/passwd")
    call(ctx, "project_manager", "update_metadata", meta={"agent": "tests"})
    assert call(ctx, "project_manager", "info")["meta"]["agent"] == "tests"
    with pytest.raises(WorkspaceError):
        call(ctx, "project_manager", "update_metadata", meta={"semver": "2.0.0"})
    assert call(ctx, "project_manager", "validate")["ok"]


def test_external_change_is_picked_up(ctx, root):
    call(ctx, "project_manager", "open", name="sample")
    (root / "sample.sb3").write_bytes((root / "sample.sb3").read_bytes() + b"")  # same bytes: no reload needed
    call(ctx, "sprite_manager", "set", sprite="Cat", x=5)
    assert call(ctx, "sprite_manager", "get", sprite="Cat")["x"] == 5


def test_unknown_action_and_bad_args(ctx):
    with pytest.raises(WorkspaceError, match="Did you mean"):
        call(ctx, "project_manager", "sav")
    with pytest.raises(WorkspaceError, match="Invalid args"):
        call(ctx, "project_manager", "create")
    with pytest.raises(WorkspaceError, match="Invalid args"):
        call(ctx, "project_manager", "create", name="x", bogus=1)
    h = call(ctx, "project_manager", "help", action="create")
    assert "name" in h["create"]["schema"]["properties"]
    with pytest.raises(WorkspaceError, match="No project specified"):
        call(ctx, "sprite_manager", "list")


# ---- sprites ------------------------------------------------------------------------

def test_sprite_crud(pm):
    r = call(pm, "sprite_manager", "create", name="Robot", stock="robot", x=10, y=-20, size=80)
    assert r["created"] == "Robot" and "idle" in r["costumes"]
    info = call(pm, "sprite_manager", "get", sprite="Robot")
    assert (info["x"], info["y"], info["size"]) == (10, -20, 80)
    call(pm, "sprite_manager", "set", sprite="Robot", visible=False, direction=45, rotation_style="left-right", costume="happy", draggable=True)
    info = call(pm, "sprite_manager", "get", sprite="Robot")
    assert info["visible"] is False and info["current_costume"] == "happy" and info["draggable"]
    with pytest.raises(WorkspaceError):
        call(pm, "sprite_manager", "set", sprite="Robot", rotation_style="spin")
    call(pm, "script_manager", "add_text", sprite="Cat", script="when flag clicked\nset [score v] to (1)\n\ndefine hop\nmove (1) steps")
    d = call(pm, "sprite_manager", "duplicate", sprite="Cat", new_name="Cat2")
    assert d["created"] == "Cat2"
    s = pm.session(None)
    a, b = [t for t in s.project["targets"] if t["name"] in ("Cat", "Cat2")]
    assert a["blocks"].keys().isdisjoint(b["blocks"].keys()) and len(a["blocks"]) == len(b["blocks"])
    valid(pm)
    call(pm, "sprite_manager", "rename", sprite="Cat2", new_name="Dog")
    assert call(pm, "sprite_manager", "list")["selected"] == "Dog"
    order = call(pm, "sprite_manager", "layer", sprite="Cat", mode="front")["order_back_to_front"]
    assert order[-1] == "Cat"
    call(pm, "sprite_manager", "select", sprite="Ball")
    assert call(pm, "sprite_manager", "get")["name"] == "Ball"
    call(pm, "sprite_manager", "delete", sprite="Dog")
    with pytest.raises(WorkspaceError):
        call(pm, "sprite_manager", "create", name="Cat")
    valid(pm)
    undone = call(pm, "project_manager", "undo")
    assert undone["undone"] == ["delete sprite Dog"]
    assert any(x["name"] == "Dog" for x in call(pm, "sprite_manager", "list")["sprites"])


def test_rename_sprite_updates_menus(pm):
    call(pm, "sprite_manager", "rename", sprite="Cat", new_name="Kitty")
    text = call(pm, "script_manager", "list_scripts", sprite="Ball")["scripts"]
    assert any("Kitty" in sc["text"] for sc in text) and not any("(Cat v)" in sc["text"] for sc in text)
    valid(pm)


def test_sprite_import_round_trip(pm, root):
    # build a .sprite3 by hand from the Ball sprite
    s = pm.session(None)
    ball = next(t for t in s.project["targets"] if t["name"] == "Ball")
    path = root / "ball.sprite3"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("sprite.json", json.dumps(ball))
        for c in ball["costumes"] + ball["sounds"]:
            zf.writestr(c["md5ext"], s.assets[c["md5ext"]])
    r = call(pm, "sprite_manager", "import_sprite", source_path="ball.sprite3")
    assert r["imported"] == "Ball2" and r["blocks"] == len(ball["blocks"])
    valid(pm)
    with pytest.raises(WorkspaceError, match="sprite.json"):
        zipfile.ZipFile(root / "bad.sprite3", "w").writestr("x", "y")
        call(pm, "sprite_manager", "import_sprite", source_path="bad.sprite3")


# ---- variables ----------------------------------------------------------------------

def test_variables_lists_broadcasts(pm):
    call(pm, "variable_manager", "create_variable", name="lives", value=3)
    call(pm, "variable_manager", "create_variable", name="mine", value="x", sprite="Ball")
    with pytest.raises(WorkspaceError, match="already exists"):
        call(pm, "variable_manager", "create_variable", name="lives")
    cloud = call(pm, "variable_manager", "create_variable", name="hi", value=0, cloud=True)
    assert cloud["created"] == "☁ hi"
    call(pm, "variable_manager", "create_list", name="inventory", items=["a", "b"])
    v = call(pm, "variable_manager", "list")
    names = {x["name"]: x for x in v["variables"]}
    assert names["score"]["used_by_blocks"] > 0 and names["mine"]["scope"] == "Ball" and names["lives"]["value"] == 3
    call(pm, "variable_manager", "rename_variable", name="score", new_name="points")
    scripts = call(pm, "script_manager", "list_scripts", sprite="Cat")["scripts"]
    assert any("[points v]" in s["text"] for s in scripts) and not any("[score v]" in s["text"] for s in scripts)
    with pytest.raises(WorkspaceError, match="used by"):
        call(pm, "variable_manager", "delete_variable", name="points")
    call(pm, "variable_manager", "delete_variable", name="lives")
    call(pm, "variable_manager", "rename_broadcast", name="game over", new_name="the end")
    texts = " ".join(s["text"] for s in call(pm, "script_manager", "list_scripts", sprite="Cat")["scripts"])
    assert "the end" in texts and "game over" not in texts
    call(pm, "variable_manager", "set_monitor", name="points", mode="large", x=10, y=10)
    assert any(m["id"] for m in pm.session(None).project["monitors"])
    call(pm, "variable_manager", "set_list", name="inventory", items=["z"])
    call(pm, "variable_manager", "delete_list", name="inventory")
    valid(pm)


# ---- costumes + vector editor ---------------------------------------------------------

def test_costume_management(pm):
    c = call(pm, "costume_manager", "list", sprite="Cat")
    assert [x["name"] for x in c["costumes"]] == ["costume1", "costume2"]
    call(pm, "costume_manager", "duplicate", sprite="Cat", costume="costume1", new_name="copy")
    call(pm, "costume_manager", "rename", sprite="Cat", costume="copy", new_name="alt")
    call(pm, "costume_manager", "reorder", sprite="Cat", costume="alt", position=3)
    assert [x["name"] for x in call(pm, "costume_manager", "list", sprite="Cat")["costumes"]] == ["costume1", "costume2", "alt"]
    call(pm, "costume_manager", "set_center", sprite="Cat", costume="alt", mode="bottom")
    call(pm, "costume_manager", "set_current", sprite="Cat", costume=2)
    call(pm, "costume_manager", "delete", sprite="Cat", costume="alt")
    assert call(pm, "costume_manager", "list", sprite="Cat")["current"] == 2
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAYAAAC56t6BAAAAEklEQVR4nGNgYGD4z8DAwMAAAAAGAAH5mTPXAAAAAElFTkSuQmCC")
    r = call(pm, "costume_manager", "import_image", sprite="Cat", name="px", data_base64=base64.b64encode(png).decode(), bitmap_resolution=1)
    assert r["format"] == "png"
    assert call(pm, "costume_manager", "list", sprite="Cat")["costumes"][-1]["center"] == [1.0, 1.5]
    with pytest.raises(WorkspaceError, match="Unsupported image|bitmap"):
        call(pm, "costume_manager", "import_image", sprite="Cat", name="bad", data_base64=base64.b64encode(b"GIF89a....").decode())
    with pytest.raises(WorkspaceError, match="bitmap"):
        call(pm, "costume_manager", "draw", sprite="Cat", costume="px", shape="circle", cx=1, cy=1, r=1)
    with pytest.raises(WorkspaceError, match="not allowed"):
        call(pm, "costume_manager", "add_svg", sprite="Cat", name="evil", svg='<svg xmlns="http://www.w3.org/2000/svg" width="5" height="5"><script>alert(1)</script></svg>')
    with pytest.raises(WorkspaceError, match="External references"):
        call(pm, "costume_manager", "add_svg", sprite="Cat", name="evil", svg='<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="5" height="5"><image xlink:href="http://x.test/a.png"/></svg>')
    valid(pm)
    exp = call(pm, "costume_manager", "export", sprite="Cat", costume="costume1")
    assert exp["exported_to"].startswith("exports/")


def test_vector_editor(pm):
    call(pm, "costume_manager", "add_blank", sprite="Ball", name="art", width=200, height=100, background="#ffffff")
    r1 = call(pm, "costume_manager", "draw", sprite="Ball", costume="art", shape="rect", x=10, y=10, width=40, height=20, fill="#ff0000", stroke="#000000", stroke_width=2)
    r2 = call(pm, "costume_manager", "draw", sprite="Ball", costume="art", shape="circle", cx=100, cy=50, r=20, fill="#00ff00")
    call(pm, "costume_manager", "draw", sprite="Ball", costume="art", shape="star", cx=160, cy=50, r=25, fill="#ffd34d")
    call(pm, "costume_manager", "draw", sprite="Ball", costume="art", shape="text", text="Hi <&>", x=20, y=90, font_size=20, bold=True)
    curve = call(pm, "costume_manager", "draw", sprite="Ball", costume="art", shape="curve", points=[[0, 0], [50, 100], [100, 0]], stroke="#0000ff", stroke_width=3)
    valid(pm)
    els = call(pm, "costume_manager", "elements", sprite="Ball", costume="art")
    assert els["canvas"] == {"width": 200.0, "height": 100.0} and len(els["elements"]) == 6
    t = call(pm, "costume_manager", "transform", sprite="Ball", costume="art", id=r1["id"], rotate=90, scale=2)
    assert t["element"]["bbox"]["height"] > t["element"]["bbox"]["width"]
    call(pm, "costume_manager", "transform", sprite="Ball", costume="art", id=r2["id"], position_x=0, position_y=0)
    assert call(pm, "costume_manager", "elements", sprite="Ball", costume="art")["elements"][2]["bbox"]["x"] == 0
    call(pm, "costume_manager", "transform", sprite="Ball", costume="art", id=r2["id"], flip="horizontal", width=10)
    g = call(pm, "costume_manager", "group", sprite="Ball", costume="art", ids=[r1["id"], r2["id"]])
    call(pm, "costume_manager", "set_style", sprite="Ball", costume="art", id=g["group_id"], fill="#123456")
    svg = call(pm, "costume_manager", "svg", sprite="Ball", costume="art")["svg"]
    assert svg.count('fill="#123456"') == 2
    call(pm, "costume_manager", "layer", sprite="Ball", costume="art", id=g["group_id"], mode="back")
    call(pm, "costume_manager", "ungroup", sprite="Ball", costume="art", id=g["group_id"])
    nodes = call(pm, "costume_manager", "path_nodes", sprite="Ball", costume="art", id=curve["id"])["nodes"]
    assert nodes[1]["cmd"] == "Q" and nodes[1]["handles"] == [[50.0, 100.0]]
    call(pm, "costume_manager", "path_edit", sprite="Ball", costume="art", id=curve["id"], index=1, x=90, y=60)
    call(pm, "costume_manager", "path_add", sprite="Ball", costume="art", id=curve["id"], after_index=1, x=95, y=95)
    call(pm, "costume_manager", "path_delete", sprite="Ball", costume="art", id=curve["id"], index=2)
    call(pm, "costume_manager", "copy", sprite="Ball", costume="art", ids=[curve["id"]])
    pasted = call(pm, "costume_manager", "paste", sprite="Cat", costume="costume1", offset_x=5, offset_y=5)["pasted_ids"]
    assert len(pasted) == 1
    call(pm, "costume_manager", "delete_elements", sprite="Ball", costume="art", ids=[curve["id"]])
    with pytest.raises(WorkspaceError, match="No element"):
        call(pm, "costume_manager", "transform", sprite="Ball", costume="art", id="nope", rotate=5)
    with pytest.raises(WorkspaceError, match="Unknown shape"):
        call(pm, "costume_manager", "draw", sprite="Ball", costume="art", shape="blob")
    with pytest.raises(WorkspaceError, match="needs"):
        call(pm, "costume_manager", "draw", sprite="Ball", costume="art", shape="rect", x=1)
    els = call(pm, "costume_manager", "elements", sprite="Ball", costume="art")["elements"]
    x0, x1 = min(e["bbox"]["x"] for e in els), max(e["bbox"]["x"] + e["bbox"]["width"] for e in els)
    c = call(pm, "costume_manager", "crop", sprite="Ball", costume="art", padding=2)
    assert c["canvas"][0] == pytest.approx(x1 - x0 + 4, abs=0.01)
    call(pm, "costume_manager", "set_canvas", sprite="Ball", costume="art", width=300, height=300)
    call(pm, "costume_manager", "clear", sprite="Ball", costume="art")
    assert call(pm, "costume_manager", "elements", sprite="Ball", costume="art")["elements"] == []
    valid(pm)
    # every edit is undoable
    call(pm, "project_manager", "undo", steps=2)
    assert len(call(pm, "costume_manager", "elements", sprite="Ball", costume="art")["elements"]) >= 1


@needs_browser
def test_preview_and_bitmap_round_trip(pm):
    import anyio

    from scratch_mcp import registry

    async def run():
        r = await registry.dispatch("costume_manager", pm, "preview", {"sprite": "Cat", "costume": "costume1"})
        await registry.dispatch("costume_manager", pm, "to_bitmap", {"sprite": "Cat", "costume": "costume1"})
        lst = await registry.dispatch("costume_manager", pm, "list", {"sprite": "Cat"})
        r2 = await registry.dispatch("costume_manager", pm, "preview", {"sprite": "Cat", "costume": "costume1"})
        await registry.dispatch("costume_manager", pm, "to_vector", {"sprite": "Cat", "costume": "costume1"})
        els = await registry.dispatch("costume_manager", pm, "elements", {"sprite": "Cat", "costume": "costume1"})
        await pm.browser.close()
        return r, lst, r2, els

    r, lst, r2, els = anyio.run(run)
    assert r.images[0][0][:4] == b"\x89PNG" and r.images[0][1] == "image/png"
    c1 = lst["costumes"][0]
    assert c1["format"] == "png" and c1["bitmap_resolution"] == 2 and c1["center"] == [96, 100]
    assert r2.images[0][0][:4] == b"\x89PNG"
    assert els["elements"][0]["type"] == "image"
    valid(pm)


# ---- sounds, backdrops, assets, library ----------------------------------------------------------

def test_sound_management_and_editing(pm):
    call(pm, "sound_manager", "add_preset", sprite="Ball", name="boing", preset="boing")
    call(pm, "sound_manager", "add_tone", sprite="Ball", name="beep", frequency=440, seconds=1, wave="square")
    lst = call(pm, "sound_manager", "list", sprite="Ball")["sounds"]
    assert [s["name"] for s in lst][-2:] == ["boing", "beep"] and lst[-1]["seconds"] == 1.0
    call(pm, "sound_manager", "edit", sprite="Ball", sound="beep", operation="trim", start=0.25, end=0.75)
    assert call(pm, "sound_manager", "list", sprite="Ball")["sounds"][-1]["seconds"] == 0.5
    call(pm, "sound_manager", "edit", sprite="Ball", sound="beep", operation="reverse")
    call(pm, "sound_manager", "edit", sprite="Ball", sound="beep", operation="volume", factor=0.5)
    call(pm, "sound_manager", "edit", sprite="Ball", sound="beep", operation="echo", delay=0.1, decay=0.4)
    out = call(pm, "sound_manager", "edit", sprite="Ball", sound="beep", operation="faster", factor=2, save_as="beep fast")
    assert out["sound"] == "beep fast" and out["seconds"] < out["was_seconds"]
    call(pm, "sound_manager", "edit", sprite="Ball", sound="beep", operation="fade_out", seconds=0.1)
    call(pm, "sound_manager", "edit", sprite="Ball", sound="beep", operation="robot")
    call(pm, "sound_manager", "edit", sprite="Ball", sound="beep", operation="normalize")
    call(pm, "sound_manager", "copy_segment", sprite="Ball", sound="beep", start=0, end=0.1)
    before = call(pm, "sound_manager", "list", sprite="Ball")["sounds"][-2]["seconds"]
    call(pm, "sound_manager", "paste_segment", sprite="Ball", sound="beep", at=0.2)
    assert call(pm, "sound_manager", "list", sprite="Ball")["sounds"][-2]["seconds"] > before
    with pytest.raises(WorkspaceError, match="Invalid time range"):
        call(pm, "sound_manager", "edit", sprite="Ball", sound="beep", operation="trim", start=5, end=6)
    with pytest.raises(WorkspaceError, match="Unknown operation"):
        call(pm, "sound_manager", "edit", sprite="Ball", sound="beep", operation="wobble")
    call(pm, "sound_manager", "rename", sprite="Ball", sound="beep", new_name="tone")
    call(pm, "sound_manager", "duplicate", sprite="Ball", sound="tone")
    call(pm, "sound_manager", "delete", sprite="Ball", sound="tone2")
    pv = call(pm, "sound_manager", "preview", sprite="Ball", sound="boing")
    assert pv.audio[0][0][:4] == b"RIFF" and pv.text["peak"] > 0.1 and not pv.text["silent"]
    with pytest.raises(WorkspaceError, match="Only WAV"):
        import unittest.mock as m
        with m.patch("shutil.which", return_value=None):
            call(pm, "sound_manager", "import_sound", sprite="Ball", name="x", data_base64=base64.b64encode(b"ID3....").decode())
    valid(pm)


def test_sound_rename_updates_menus(pm):
    call(pm, "script_manager", "add_text", sprite="Cat", script="when flag clicked\nplay sound (Meow v) until done")
    call(pm, "sound_manager", "rename", sprite="Cat", sound="Meow", new_name="Purr")
    texts = " ".join(s["text"] for s in call(pm, "script_manager", "list_scripts", sprite="Cat")["scripts"])
    assert "(Purr v)" in texts


def test_backdrops_and_stage(pm):
    call(pm, "backdrop_manager", "add_stock", art="kitchen")
    call(pm, "backdrop_manager", "add_blank", name="sky", background="#87ceeb")
    names = [b["name"] for b in call(pm, "backdrop_manager", "list")["costumes"]]
    assert names[-3:] == ["kitchen1", "kitchen2", "sky"]
    call(pm, "costume_manager", "draw", sprite="Stage", costume="sky", shape="circle", cx=400, cy=60, r=30, fill="#ffd34d")
    call(pm, "backdrop_manager", "set_initial", backdrop="sky")
    call(pm, "backdrop_manager", "rename", backdrop="sky", new_name="day")
    call(pm, "backdrop_manager", "reorder", backdrop="day", position=1)
    assert call(pm, "backdrop_manager", "list")["costumes"][0]["name"] == "day"
    call(pm, "backdrop_manager", "stage_set", tempo=90, volume=50)
    assert call(pm, "backdrop_manager", "stage_get")["tempo"] == 90
    with pytest.raises(WorkspaceError):
        call(pm, "backdrop_manager", "stage_set", tempo=5)
    call(pm, "backdrop_manager", "delete", backdrop="kitchen2")
    valid(pm)


def test_assets_list_and_prune(pm):
    a = call(pm, "asset_manager", "list")
    assert a["unused"] == [] and a["missing"] == []
    call(pm, "costume_manager", "add_blank", sprite="Ball", name="tmp")
    n_before = len(call(pm, "asset_manager", "list")["files"])
    call(pm, "costume_manager", "delete", sprite="Ball", costume="tmp")
    assert len(call(pm, "asset_manager", "list")["files"]) == n_before - 1  # pruned automatically on delete
    assert call(pm, "asset_manager", "prune")["removed"] == []


def test_library_with_mock_network(pm, tmp_path, monkeypatch):
    import io

    from scratch_mcp.library import Library

    monkeypatch.setenv("SCRATCH_MCP_CACHE", str(tmp_path / "cache"))
    wav = __import__("scratch_mcp.sounds", fromlist=["x"]).render_preset("pop")
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="10" cy="10" r="9" fill="red"/></svg>'
    import hashlib

    wav_md5, svg_md5 = hashlib.md5(wav).hexdigest(), hashlib.md5(svg).hexdigest()
    meta = {
        "sounds": [{"name": "Pop", "md5ext": wav_md5 + ".wav", "dataFormat": "wav", "rate": 22050, "sampleCount": 3000, "tags": ["effects"]}],
        "costumes": [{"name": "Dot", "md5ext": svg_md5 + ".svg", "tags": ["shapes"], "rotationCenterX": 10, "rotationCenterY": 10}],
        "backdrops": [{"name": "Sky", "md5ext": svg_md5 + ".svg", "tags": ["outdoors"]}],
        "sprites": [{"name": "Blob", "tags": ["animals"], "isStage": False, "variables": {}, "lists": {}, "broadcasts": {}, "blocks": {},
                     "comments": {}, "currentCostume": 0, "costumes": [{"name": "dot", "assetId": svg_md5, "md5ext": svg_md5 + ".svg",
                     "dataFormat": "svg", "bitmapResolution": 1, "rotationCenterX": 10, "rotationCenterY": 10}],
                     "sounds": [{"name": "pop", "assetId": wav_md5, "md5ext": wav_md5 + ".wav", "dataFormat": "wav", "rate": 22050, "sampleCount": 3000}],
                     "volume": 100, "visible": True, "x": 0, "y": 0, "size": 100, "direction": 90, "draggable": False, "rotationStyle": "all around"}],
    }
    calls = []

    def fake(url: str) -> bytes:
        calls.append(url)
        for k, v in meta.items():
            if url.endswith(f"/{k}.json"):
                return json.dumps(v).encode()
        if url.endswith(wav_md5 + ".wav/get/"):
            return wav
        if url.endswith(svg_md5 + ".svg/get/"):
            return svg
        raise AssertionError(url)

    pm.library = Library(fake)
    assert call(pm, "asset_manager", "library_search", kind="sounds", query="effects")["results"][0]["name"] == "Pop"
    assert call(pm, "asset_manager", "library_search", kind="sprites", tag="animals")["results"][0]["name"] == "Blob"
    call(pm, "asset_manager", "library_add", kind="sounds", name="pop", sprite="Ball")
    call(pm, "asset_manager", "library_add", kind="costumes", name="Dot", sprite="Ball")
    call(pm, "asset_manager", "library_add", kind="backdrops", name="Sky")
    r = call(pm, "asset_manager", "library_add", kind="sprites", name="Blob")
    assert r["created_sprite"] == "Blob" and r["costumes"] == 1
    valid(pm)
    n = len(calls)
    call(pm, "asset_manager", "library_add", kind="sounds", name="Pop", sprite="Ball", new_name="Pop2")
    assert len(calls) == n  # served from the cache
    with pytest.raises(WorkspaceError, match="No library sound"):
        call(pm, "asset_manager", "library_add", kind="sounds", name="Nope", sprite="Ball")
    with pytest.raises(WorkspaceError, match="kind must be"):
        call(pm, "asset_manager", "library_search", kind="gifs")


def test_import_mp3_via_ffmpeg(pm, tmp_path):
    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    from scratch_mcp.sounds import render_preset

    wav = tmp_path / "a.wav"
    wav.write_bytes(render_preset("chime"))
    mp3 = tmp_path / "a.mp3"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), str(mp3)], capture_output=True)
    if r.returncode != 0 or not mp3.exists():
        pytest.skip("this ffmpeg can't encode mp3")
    out = call(pm, "sound_manager", "import_sound", sprite="Ball", name="song", data_base64=base64.b64encode(mp3.read_bytes()).decode())
    assert out["added"] == "song" and 0.9 < out["seconds"] < 1.4        # the chime is 1.1 s
    entry = [s for s in call(pm, "sound_manager", "list", sprite="Ball")["sounds"] if s["name"] == "song"][0]
    assert entry["format"] == "wav" and entry["rate"] == 22050
    call(pm, "sound_manager", "edit", sprite="Ball", sound="song", operation="reverse")   # converted audio is editable
    valid(pm)


def test_reset_history_and_backup_listing(pm, root):
    call(pm, "project_manager", "set_autosave", enabled=False)
    call(pm, "sprite_manager", "set", sprite="Cat", x=11)
    call(pm, "sprite_manager", "set", sprite="Cat", y=22)
    hist = call(pm, "project_manager", "history")
    assert hist["undo"] == ["set sprite properties", "set sprite properties"] and hist["redo"] == []
    assert call(pm, "project_manager", "info")["dirty"] is True
    call(pm, "project_manager", "reset")                          # throw the unsaved edits away
    info = call(pm, "project_manager", "info")
    assert info["dirty"] is False and not info["can_undo"]
    assert (call(pm, "sprite_manager", "get", sprite="Cat")["x"], call(pm, "sprite_manager", "get", sprite="Cat")["y"]) == (0, 0)
    assert call(pm, "project_manager", "list_backups")["backups"] == []
    call(pm, "project_manager", "set_autosave", enabled=True)
    out = call(pm, "sprite_manager", "set", sprite="Cat", x=5)
    assert out and call(pm, "project_manager", "list_backups")["backups"][0]["path"].startswith("backups/sample.")
    first = call(pm, "project_manager", "list_backups")["backups"][0]["path"]
    with pytest.raises(WorkspaceError, match="read-only"):
        call(pm, "project_manager", "import_sb3", name="x", source_path=first)      # backups aren't projects...
    # ...restoring is explicit: as a copy, or over the original (the current file is backed up first)
    copy = call(pm, "project_manager", "restore_backup", backup=first, as_name="restored")
    assert copy["restored"] == "restored.sb3" and call(pm, "sprite_manager", "get", sprite="Cat")["x"] == 0
    call(pm, "project_manager", "open", name="sample")
    assert call(pm, "sprite_manager", "get", sprite="Cat")["x"] == 5
    over = call(pm, "project_manager", "restore_backup", backup=first)
    assert over["restored"] == "sample.sb3" and len(over["backups_made"]) == 1
    assert call(pm, "sprite_manager", "get", sprite="Cat")["x"] == 0
    with pytest.raises(WorkspaceError, match="not a backup"):
        call(pm, "project_manager", "restore_backup", backup="sample.sb3")
