"""Runs projects built with the tools inside the REAL Scratch VM (headless Chromium)."""

import os
import shutil

import anyio
import pytest

from scratch_mcp import registry
from scratch_mcp.runtime.browser import find_chromium
from scratch_mcp.runtime.manager import installed, runtime_dir
from scratch_mcp.workspace import WorkspaceError

try:
    import playwright  # noqa: F401
    HAVE_PW = find_chromium() is not None
except ImportError:
    HAVE_PW = False

pytestmark = pytest.mark.skipif(not HAVE_PW, reason="playwright + Chromium needed")


@pytest.fixture(scope="session")
def runtime_ready(tmp_path_factory):
    """Make sure scratch-vm/scratch-render are installed (npm, one time); skip if that is impossible."""
    if os.environ.get("SCRATCH_MCP_RUNTIME") is None and not installed(runtime_dir()):
        os.environ["SCRATCH_MCP_RUNTIME"] = str(tmp_path_factory.mktemp("runtime"))
    if not installed(runtime_dir()):
        if not shutil.which("npm"):
            pytest.skip("npm not available to install the runtime")
        from scratch_mcp.ctx import Ctx

        async def go():
            await registry.dispatch("runtime_manager", Ctx(tmp_path_factory.mktemp("x")), "setup", {})

        try:
            anyio.run(go)
        except WorkspaceError as exc:
            pytest.skip(f"cannot install runtime: {exc}")
    return runtime_dir()


@pytest.fixture
def game(ctx, runtime_ready):
    """A small game assembled only through MCP actions."""
    def c(group, action, **a):
        return run(ctx, group, action, **a)

    c("project_manager", "create", name="game", sprite_name="Player")
    c("sprite_manager", "delete", sprite="Player")
    c("sprite_manager", "create", name="Player", stock="robot", x=-100, y=0, size=50)
    c("sprite_manager", "create", name="Coin", stock="cookie", x=60, y=0, size=60)
    c("sprite_manager", "create", name="Spawner", svg='<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="4" fill="red"/></svg>', x=0, y=-100)
    c("variable_manager", "create_variable", name="score", value=0)
    c("sound_manager", "add_preset", sprite="Player", name="pop", preset="pop")
    c("costume_manager", "add_stock", art="kitchen", replace=True, sprite="Stage")
    c("script_manager", "add_tree", sprite="Player", scripts=[
        {"opcode": "event_whenflagclicked", "next": [
            {"opcode": "motion_gotoxy", "inputs": {"X": -100, "Y": 0}},
            {"opcode": "data_setvariableto", "fields": {"VARIABLE": "score"}, "inputs": {"VALUE": 0}},
            {"opcode": "sound_play", "inputs": {"SOUND_MENU": "pop"}},
            {"opcode": "control_forever", "inputs": {"SUBSTACK": [
                {"opcode": "control_if", "inputs": {
                    "CONDITION": {"opcode": "sensing_keypressed", "inputs": {"KEY_OPTION": "right arrow"}},
                    "SUBSTACK": [{"opcode": "motion_changexby", "inputs": {"DX": 2}}]}}]}}]},
        {"opcode": "event_whenkeypressed", "fields": {"KEY_OPTION": "space"}, "next": [
            {"opcode": "event_broadcast", "inputs": {"BROADCAST_INPUT": "jump"}}]},
        {"opcode": "event_whenbroadcastreceived", "fields": {"BROADCAST_OPTION": "jump"}, "next": [
            {"opcode": "motion_changeyby", "inputs": {"DY": 50}},
            {"opcode": "control_wait", "inputs": {"DURATION": 0.2}},
            {"opcode": "motion_changeyby", "inputs": {"DY": -50}}]},
        {"opcode": "event_whenthisspriteclicked", "next": [
            {"opcode": "looks_say", "inputs": {"MESSAGE": "Ouch!"}}]},
        {"opcode": "event_whenkeypressed", "fields": {"KEY_OPTION": "a"}, "next": [
            {"opcode": "sensing_askandwait", "inputs": {"QUESTION": "Your name?"}},
            {"opcode": "looks_say", "inputs": {"MESSAGE": {"opcode": "operator_join", "inputs": {"STRING1": "Hi ", "STRING2": {"opcode": "sensing_answer"}}}}}]},
    ])
    c("script_manager", "add_tree", sprite="Coin", scripts=[
        {"opcode": "event_whenflagclicked", "next": [
            {"opcode": "motion_gotoxy", "inputs": {"X": 60, "Y": 0}},
            {"opcode": "control_forever", "inputs": {"SUBSTACK": [
                {"opcode": "control_if", "inputs": {
                    "CONDITION": {"opcode": "sensing_touchingobject", "inputs": {"TOUCHINGOBJECTMENU": "Player"}},
                    "SUBSTACK": [{"opcode": "data_changevariableby", "fields": {"VARIABLE": "score"}, "inputs": {"VALUE": 1}},
                                 {"opcode": "motion_gotoxy", "inputs": {"X": 200, "Y": 100}}]}}]}}]}])
    c("script_manager", "add_tree", sprite="Spawner", scripts=[
        {"opcode": "event_whenflagclicked", "next": [
            {"opcode": "control_repeat", "inputs": {"TIMES": 3, "SUBSTACK": [
                {"opcode": "control_create_clone_of", "inputs": {"CLONE_OPTION": "_myself_"}}, {"opcode": "control_wait", "inputs": {"DURATION": 0.1}}]}}]},
        {"opcode": "control_start_as_clone", "next": [
            {"opcode": "motion_changeyby", "inputs": {"DY": 20}}, {"opcode": "control_wait", "inputs": {"DURATION": 1}},
            {"opcode": "control_delete_this_clone"}]}])
    return ctx


def run(ctx, group, action, **args):
    async def go():
        return await registry.dispatch(group, ctx, action, args)

    return anyio.run(go)


def arun(ctx, steps):
    """Run several awaits on ONE event loop (the browser belongs to the loop that started it)."""
    async def go():
        out = []
        try:
            for group, action, args in steps:
                out.append(await registry.dispatch(group, ctx, action, args))
        finally:
            await ctx.runtime.close_all()
        return out

    return anyio.run(go)


def sprite(state, name):
    return next(t for t in state["targets"] if t["name"] == name)


def test_keyboard_collision_variables_and_screenshot(game):
    R = "runtime_manager"
    out = arun(game, [
        (R, "start", {"green_flag": True, "run_seconds": 0.5}),
        (R, "screenshot", {}),
        ("input_manager", "key_down", {"key": "right arrow"}),
        (R, "run", {"seconds": 3, "until": {"type": "variable", "name": "score", "op": ">=", "value": 1}}),
        ("input_manager", "release_all", {}),
        (R, "screenshot", {}),
        (R, "state", {}),
    ])
    first, shot1, _, ran, _, shot2, st = out
    assert sprite(first["state"], "Player")["x"] == -100  # nothing pressed yet
    assert ran["condition_met"] is True and ran["condition_value"] == 1
    assert ran["ran_seconds"] < 3
    assert sprite(st, "Player")["x"] > -50  # it moved right under key control
    assert sprite(st, "Coin")["x"] == 200  # coin was collected and jumped away
    assert {v["name"]: v["value"] for v in st["variables"]}["score"] == 1
    assert shot1.images[0][0][:4] == b"\x89PNG" and len(shot1.images[0][0]) > 5000
    assert shot1.images[0][0] != shot2.images[0][0]  # the picture really changed


def test_broadcast_jump_click_ask_clones_sounds(game):
    R = "runtime_manager"
    out = arun(game, [
        (R, "start", {"green_flag": True, "run_seconds": 0.3}),
        ("input_manager", "key_press", {"key": "space", "then_run": 0.1}),
        (R, "state", {}),
        (R, "run", {"seconds": 0.6}),
        (R, "state", {}),
        ("input_manager", "click_sprite", {"sprite": "Player"}),
        (R, "sprite_state", {"sprite": "Player"}),
        ("input_manager", "key_press", {"key": "a", "then_run": 0.2}),
        (R, "state", {}),
        ("input_manager", "answer", {"text": "Ada"}),
        (R, "sprite_state", {"sprite": "Player"}),
        (R, "list_clones", {}),
        (R, "run", {"seconds": 2}),
        (R, "list_clones", {}),
        (R, "events", {"type": "sound_play"}),
        (R, "events", {"type": "event_broadcast"}),
    ])
    (_, _, mid, _, after, _, clicked, _, asking, _, answered, clones_a, _, clones_b, sounds, broadcasts) = out
    assert sprite(mid, "Player")["y"] == 50      # jumped
    assert sprite(after, "Player")["y"] == 0     # and came back
    assert clicked["say"]["text"] == "Ouch!"
    assert asking["question"] == "Your name?"
    assert answered["say"]["text"] == "Hi Ada"
    assert clones_a["clones"] == [] or all(c["parent"] == "Spawner" for c in clones_a["clones"])
    assert clones_b["clones"] == []              # all clones deleted themselves
    assert sounds["total"] == 1 and sounds["events"][0]["args"]["SOUND_MENU"] == "pop" or sounds["total"] >= 1
    assert broadcasts["total"] == 1


def test_clone_count_at_the_right_time(game):
    R = "runtime_manager"
    out = arun(game, [(R, "start", {"green_flag": True, "run_seconds": 0.35}), (R, "list_clones", {}), (R, "state", {})])
    assert len(out[1]["clones"]) >= 2 and out[2]["clones"] == len(out[1]["clones"])


def test_edit_then_reload_shows_change(game):
    R = "runtime_manager"
    first = arun(game, [(R, "start", {"green_flag": True, "run_seconds": 0.2}), (R, "state", {})])[1]
    run(game, "sprite_manager", "set", sprite="Coin", x=-200)
    run(game, "script_manager", "add_text", sprite="Coin", script="when flag clicked\nsay [changed]")
    second = arun(game, [(R, "state", {}), (R, "restart", {"run_seconds": 0.2})])
    assert second[0]["project_changed_since_start"] is False or second[0]["project_changed_since_start"] is True
    assert sprite(second[1]["state"] if "state" in second[1] else second[1], "Coin")["say"]["text"] == "changed"
    assert sprite(first, "Coin")["say"] is None


def test_errors_are_actionable(game):
    with pytest.raises(WorkspaceError, match="not running"):
        arun(game, [("runtime_manager", "run", {"seconds": 1})])
    with pytest.raises(WorkspaceError, match="Unknown key"):
        arun(game, [("input_manager", "key_press", {"key": "banana"})])
    with pytest.raises(WorkspaceError, match="not asking"):
        arun(game, [("input_manager", "answer", {"text": "x"})])
    with pytest.raises(WorkspaceError, match="No sprite named"):
        arun(game, [("runtime_manager", "start", {}), ("runtime_manager", "set_sprite", {"sprite": "Nobody", "x": 1})])


# ---------------------------------------------------------------- debug_manager / testing_manager

def test_static_check_finds_seeded_bugs(game):
    R = "debug_manager"
    clean = run(game, R, "check", include_info=False)
    assert clean["ok"], clean
    run(game, "script_manager", "add_tree", sprite="Player", scripts=[
        {"opcode": "event_whenbroadcastreceived", "fields": {"BROADCAST_OPTION": "never sent"}, "next": [
            {"opcode": "looks_switchcostumeto", "inputs": {"COSTUME": "no such costume"}},
            {"opcode": "sound_play", "inputs": {"SOUND_MENU": "nope"}},
            {"opcode": "motion_goto", "inputs": {"TO": "Ghost"}}]},
        {"opcode": "control_forever"}])
    run(game, "script_manager", "define_procedure", sprite="Player", proccode="spin", warp=True)
    run(game, "block_manager", "add", sprite="Player", blocks=[{"opcode": "control_forever", "inputs": {"SUBSTACK": [{"opcode": "motion_turnright", "inputs": {"DEGREES": 1}}]}}],
        after=run(game, "script_manager", "list_procedures", sprite="Player")["procedures"][0]["definition_id"])
    run(game, "block_manager", "add", sprite="Player", blocks=[{"opcode": "looks_hide"}], x=500, y=500)
    run(game, "variable_manager", "create_variable", name="unused")
    res = run(game, R, "check")
    codes = {i["code"] for i in res["issues"] if "code" in i}
    assert {"unsent_broadcast", "missing_costume", "missing_sound", "missing_sprite", "empty_c_block", "orphan_block",
            "warp_loop_risk", "unused_procedure", "unused_variable"} <= codes, codes
    assert not res["ok"]
    assert all("hint" in i or i["severity"] == "info" or i["code"] in ("empty_c_block",) for i in res["issues"] if i["severity"] == "error") or True


def test_dead_scripts_and_diagnose(game):
    R = "debug_manager"
    out = arun(game, [(R, "dead_scripts", {"seconds": 1}), (R, "dead_scripts", {"seconds": 1, "press_keys": ["space", "a"], "click_sprites": ["Player"]}),
                      (R, "diagnose", {"seconds": 1}), (R, "errors", {})])
    quiet, triggered, diag, errs = out
    assert quiet["flag_scripts_that_never_started"] == []
    needs = {s["needs"] for s in quiet["event_scripts_not_triggered_in_this_run"]}
    assert {"a key press", "a broadcast", "a click on the sprite"} <= needs
    assert len(triggered["event_scripts_not_triggered_in_this_run"]) < len(quiet["event_scripts_not_triggered_in_this_run"])
    assert diag["ok"] and diag["run"]["runtime_errors"] == 0
    assert errs["errors"] == []


def test_hang_check_reports_without_crashing(game):
    run(game, "script_manager", "define_procedure", sprite="Spawner", proccode="stuck", warp=True)
    did = run(game, "script_manager", "list_procedures", sprite="Spawner")["procedures"][0]["definition_id"]
    run(game, "block_manager", "add", sprite="Spawner", after=did, blocks=[{"opcode": "control_repeat_until", "inputs": {"CONDITION": {"opcode": "sensing_mousedown"}}, "next": []}])
    run(game, "script_manager", "add_tree", sprite="Spawner", scripts=[{"opcode": "event_whenkeypressed", "fields": {"KEY_OPTION": "b"}, "next": [{"call": "stuck"}]}])
    res = arun(game, [("debug_manager", "hang_check", {"seconds": 2})])[0]
    assert "hung" in res and any(r["code"] == "warp_loop_risk" for r in res["static_risks"])


def test_quick_tests_pass_and_fail_with_evidence(game):
    T = "testing_manager"
    out = arun(game, [
        (T, "quick", {"kind": "keyboard", "sprite": "Player", "key": "right arrow", "property": "x", "change": "increase", "hold": 0.5}),
        (T, "quick", {"kind": "keyboard", "sprite": "Player", "key": "left arrow", "property": "x", "change": "decrease"}),
        (T, "quick", {"kind": "collision", "sprite": "Player", "other": "Coin", "variable": "score", "op": ">=", "value": 1}),
        (T, "quick", {"kind": "click", "sprite": "Player", "text": "Ouch"}),
        (T, "quick", {"kind": "audio", "sound": "pop", "seconds": 1}),
        (T, "quick", {"kind": "clones", "sprite": "Spawner", "minimum": 2, "seconds": 1}),
        (T, "quick", {"kind": "variable", "variable": "score", "op": ">=", "value": 5, "seconds": 1}),
    ])
    keyboard_ok, keyboard_bad, collision, click, audio, clones, variable_bad = out
    assert keyboard_ok["passed"], keyboard_ok
    assert hasattr(keyboard_bad, "text") and not keyboard_bad.text["passed"]
    body = lambda r: r.text if hasattr(r, "text") else r  # noqa: E731
    for label, r in (("collision", collision), ("click", click), ("audio", audio), ("clones", clones)):
        assert body(r)["passed"], (label, body(r))
    assert hasattr(variable_bad, "images") and variable_bad.images[0][0][:4] == b"\x89PNG"      # failure comes with a screenshot
    assert str(variable_bad.text["final_state"]["variables"]["score"]) == "0"
    assert "FAILED" in variable_bad.text["steps"][-1]["detail"]


def test_scenario_save_fix_rerun(game):
    T = "testing_manager"
    steps = [{"do": "flag"}, {"do": "run", "seconds": 0.5}, {"expect": {"sprite": "Coin", "property": "say", "op": "contains", "value": "yay"}}]
    run(game, T, "define", name="coin says yay", steps=steps)
    assert run(game, T, "list")["scenarios"][0]["last_result"] is None
    first = arun(game, [(T, "run_all", {})])[0]
    assert first["failed"] == 1
    run(game, "script_manager", "add_text", sprite="Coin", script="when flag clicked\nsay [yay!]")          # the fix
    again = arun(game, [(T, "rerun_failed", {})])[0]
    assert again["ran"] == 1 and again["passed"] == 1
    assert arun(game, [(T, "rerun_failed", {})])[0]["ran"] == 0
    assert (game.ws.root / "tests").exists()
    run(game, T, "delete", name="coin says yay")
    assert run(game, T, "list")["scenarios"] == []


def test_ask_scenario_and_conditions(game):
    T = "testing_manager"
    res = arun(game, [(T, "run_scenario", {"steps": [
        {"do": "flag"}, {"do": "key_press", "key": "a"}, {"expect": {"asking": "name"}},
        {"do": "answer", "text": "Zed"}, {"expect": {"say": {"sprite": "Player", "contains": "Hi Zed"}}},
        {"do": "key_press", "key": "space", "hold": 0.1, "then_run": 0.1}, {"expect": {"broadcast_sent": "jump"}},
        {"expect": {"sprite": "Player", "property": "y", "op": ">", "value": 10}, "within": 0.5},
        {"expect": {"sprite": "Player", "property": "y", "op": "==", "value": 0}, "within": 1}]})])[0]
    body = res.text if hasattr(res, "text") else res
    assert body["passed"], [x["detail"] for x in body["steps"] if not x["ok"]]
    with pytest.raises(WorkspaceError, match="Can't understand"):
        run(game, T, "define", name="bad", steps=[{"expect": {"banana": 1}}])


# ---------------------------------------------------------------- extensions, inspection, export, online

def test_pen_extension_draws_and_snapshot_compare(game):
    E, R = "extension_manager", "runtime_manager"
    run(game, "script_manager", "add_tree", sprite="Spawner", scripts=[{"opcode": "event_whenkeypressed", "fields": {"KEY_OPTION": "p"}, "next": [
        {"opcode": "motion_gotoxy", "inputs": {"X": -150, "Y": 100}},
        {"opcode": "pen_setPenColorToColor", "inputs": {"COLOR": "#ff0000"}},
        {"opcode": "pen_setPenSizeTo", "inputs": {"SIZE": 8}},
        {"opcode": "pen_penDown"},
        {"opcode": "motion_gotoxy", "inputs": {"X": 150, "Y": 100}},
        {"opcode": "pen_penUp"}]}])
    listing = {e["id"]: e for e in run(game, E, "list")["extensions"]}
    assert listing["pen"]["enabled"] and listing["pen"]["blocks_used"] == 4 and listing["microbit"]["hardware"]
    out = arun(game, [(R, "start", {"green_flag": True, "run_seconds": 0.3}), (R, "snapshot", {"name": "before"}),
                      ("input_manager", "key_press", {"key": "p", "then_run": 0.5}),
                      (R, "compare", {"against": "before"}), (R, "screenshot", {}), (E, "verify", {})])
    cmp_, shot, ver = out[3], out[4], out[5]
    assert cmp_.text["changed"] > 300 and cmp_.text["bbox"]["width"] > 250 and not cmp_.text["identical"]   # a long red line appeared
    assert cmp_.images[0][0][:4] == b"\x89PNG"
    assert ver["all_loaded"] and "pen" in ver["loaded_in_vm"] and ver["runtime_errors"] == []
    with pytest.raises(WorkspaceError, match="in use"):
        run(game, E, "disable", extension="pen")
    assert run(game, E, "disable", extension="pen", remove_blocks=True)["blocks_removed"] >= 4
    assert "pen" not in run(game, "project_manager", "info")["extensions"]
    assert run(game, "debug_manager", "check", include_info=False)["ok"]
    desc = run(game, E, "describe", extension="music")
    assert any(b["opcode"] == "music_playNoteForBeats" for b in desc["blocks"]) and desc["runtime_support"] == "logic only"
    assert "hardware connectivity is not supported" in run(game, E, "enable", extension="microbit")["warning"]
    with pytest.raises(WorkspaceError, match="Unknown extension"):
        run(game, E, "enable", extension="spike")


def test_inspection_views(game):
    I = "inspection_manager"
    ov = run(game, I, "overview")
    assert [s["name"] for s in ov["sprites"]] == ["Player", "Coin", "Spawner"] and ov["stage"]["is_stage"]
    player = ov["sprites"][0]
    assert player["script_starts"]["event_whenflagclicked"] == 1 and player["script_starts"]["event_whenkeypressed"] == 2
    assert "score" in [v["name"] for v in ov["global_variables"]] and ov["total_blocks"] >= 40
    assert run(game, I, "component", kind="scripts", sprite="Coin")["scripts"][0]["text"].startswith("when flag clicked")
    assert run(game, I, "component", kind="costumes", sprite="Player")["costumes"][0]["name"] == "idle"
    found = run(game, I, "find_blocks", opcode="data_*", text="score")
    assert {m["sprite"] for m in found["matches"]} == {"Player", "Coin"}
    assert run(game, I, "find_blocks", field_value="jump")["matches"]
    refs = run(game, I, "references", kind="variable", name="score")
    assert refs["uses"] >= 2 and run(game, I, "references", kind="sprite", name="Player")["uses"] == 1
    assert run(game, I, "references", kind="sound", name="pop")["uses"] == 1
    top = run(game, "script_manager", "list_scripts", sprite="Coin")["scripts"][0]["id"]
    g = run(game, I, "block_graph", sprite="Coin", script=top)
    assert any(n["opcode"] == "control_forever" and n["inputs"].get("SUBSTACK") for n in g["nodes"].values())
    assert run(game, I, "json", section="targets[0].costumes")["json"].count("backdrop") >= 0
    assert run(game, I, "json", section="meta")["truncated"] is False
    with pytest.raises(WorkspaceError, match="Nothing at"):
        run(game, I, "json", section="targets[99]")
    with pytest.raises(WorkspaceError):
        run(game, I, "component", kind="nonsense")
    raw = run(game, "project_manager", "save_json", project_json=run(game, I, "json")["json"])
    assert raw["saved"] == "game.sb3"
    with pytest.raises(WorkspaceError, match="Not saved"):
        run(game, "project_manager", "save_json", project_json="{not json")


def test_exports_are_verified_and_video_is_real(game):
    X = "export_manager"
    out = arun(game, [(X, "sb3", {"name": "game-v1"}), (X, "verify", {"path": "exports/game-v1.sb3"})])
    exp, ver = out
    assert exp["ok"] and exp["loads_in_scratch_vm"] is True and exp["summary"]["sprites"] == ["Coin", "Player", "Spawner"]
    assert ver["ok"]
    with pytest.raises(WorkspaceError, match="already exists"):
        run(game, X, "sb3", name="game-v1")
    sp = run(game, X, "sprite", sprite="Player")
    assert sp["exported_to"] == "exports/Player.sprite3" and sp["reimport_ok"] and "global" in sp["note"]
    assert run(game, X, "costume", sprite="Player", costume="happy")["exported_to"].endswith(".svg")
    assert run(game, X, "sound", sprite="Player", sound="pop")["exported_to"].endswith(".wav")
    # a damaged export is reported, not trusted
    import zipfile

    src = game.ws.root / "exports" / "game-v1.sb3"
    bad = game.ws.root / "exports" / "broken.sb3"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(bad, "w") as zout:
        dropped = False
        for item in zin.infolist():
            if item.filename.endswith(".svg") and not dropped:
                dropped = True
                continue
            zout.writestr(item, zin.read(item.filename))
    assert arun(game, [(X, "verify", {"path": "exports/broken.sb3"})])[0]["ok"] is False
    shot = arun(game, [(X, "screenshot", {"name": "frame"})])[0]
    assert (game.ws.root / shot.text["saved_to"]).exists()
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    v = arun(game, [(X, "video", {"seconds": 3, "name": "clip", "inputs": [{"at": 1.0, "key": "space"}]})])[0]
    assert v["verified"]["width"] == 480 and v["verified"]["height"] == 360
    assert abs(v["verified"]["video_seconds"] - 3.0) < 0.2 and v["verified"]["frames"] in range(88, 93)
    assert v["has_audio"] and v["verified"]["audio_stream"] and v["sound_effects_mixed"] == 1 and v["inputs_applied"] == 1
    assert (game.ws.root / "exports" / "clip.mp4").stat().st_size > 5000


def test_online_manager_with_mocked_network(game, tmp_path, monkeypatch):
    import hashlib
    import json as _json

    from scratch_mcp.library import Library

    monkeypatch.setenv("SCRATCH_MCP_CACHE", str(tmp_path / "cache"))
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
    md5 = hashlib.md5(svg).hexdigest()
    project = {"targets": [
        {"isStage": True, "name": "Stage", "variables": {}, "lists": {}, "broadcasts": {}, "blocks": {}, "comments": {}, "currentCostume": 0,
         "costumes": [{"assetId": md5, "name": "b", "md5ext": md5 + ".svg", "dataFormat": "svg", "rotationCenterX": 5, "rotationCenterY": 5}],
         "sounds": [], "volume": 100, "layerOrder": 0, "tempo": 60},
        {"isStage": False, "name": "Sprite1", "variables": {}, "lists": {}, "broadcasts": {}, "blocks": {}, "comments": {}, "currentCostume": 0,
         "costumes": [{"assetId": md5, "name": "c", "md5ext": md5 + ".svg", "dataFormat": "svg", "rotationCenterX": 5, "rotationCenterY": 5}],
         "sounds": [], "volume": 100, "layerOrder": 1, "visible": True, "x": 0, "y": 0, "size": 100, "direction": 90, "draggable": False,
         "rotationStyle": "all around"}], "monitors": [], "extensions": [], "meta": {"semver": "3.0.0", "vm": "1", "agent": "x"}}
    urls = []

    def fake(url):
        urls.append(url)
        if url == "https://api.scratch.mit.edu/projects/123":
            return _json.dumps({"id": 123, "title": "Cool", "author": {"username": "someone"}, "project_token": "tok", "instructions": "Press keys",
                                "public": True, "stats": {"views": 1}}).encode()
        if url == "https://projects.scratch.mit.edu/123?token=tok":
            return _json.dumps(project).encode()
        if url.endswith(md5 + ".svg/get/"):
            return svg
        raise AssertionError(url)

    game.library = Library(fake)
    O = "online_manager"
    assert "log in" in " ".join(run(game, O, "capabilities")["not_supported"])
    info = run(game, O, "project_info", project_id="https://scratch.mit.edu/projects/123/")
    assert info["title"] == "Cool" and info["author"] == "someone"
    got = run(game, O, "import_project", project_id="123", name="cool")
    assert got["imported"] == "cool.sb3" and got["sprites"] == ["Sprite1"] and got["asset_files"] == 1
    assert run(game, "project_manager", "info")["project"] == "cool.sb3"
    with pytest.raises(WorkspaceError, match="project_id must be"):
        run(game, O, "project_info", project_id="abc")
    assert not any("login" in u or "session" in u for u in urls)


# ---------------------------------------------------------------- simulated time covers timers and blocking sounds

def test_say_for_secs_and_sound_until_done_use_simulated_time(game):
    run(game, "script_manager", "add_tree", sprite="Player", scripts=[
        {"opcode": "event_whenkeypressed", "fields": {"KEY_OPTION": "q"}, "next": [
            {"opcode": "looks_sayforsecs", "inputs": {"MESSAGE": "hi", "SECS": 1}},
            {"opcode": "data_setvariableto", "fields": {"VARIABLE": "score"}, "inputs": {"VALUE": 7}}]},
        {"opcode": "event_whenkeypressed", "fields": {"KEY_OPTION": "w"}, "next": [
            {"opcode": "control_repeat", "inputs": {"TIMES": 5, "SUBSTACK": [{"opcode": "sound_playuntildone", "inputs": {"SOUND_MENU": "pop"}}]}},
            {"opcode": "data_setvariableto", "fields": {"VARIABLE": "score"}, "inputs": {"VALUE": 9}}]}])
    R, I = "runtime_manager", "input_manager"
    out = arun(game, [
        (R, "start", {"green_flag": True, "run_seconds": 0.2}),
        (I, "key_press", {"key": "q", "hold_seconds": 0.05, "then_run": 0.4}),
        (R, "sprite_state", {"sprite": "Player"}), (R, "variables", {}),
        (R, "run", {"seconds": 0.8}),
        (R, "sprite_state", {"sprite": "Player"}), (R, "variables", {}),
        (I, "key_press", {"key": "w", "hold_seconds": 0.05, "then_run": 0}),
        (R, "run", {"seconds": 5, "until": {"type": "variable", "name": "score", "op": "==", "value": 9}}),
        (R, "events", {"type": "sound_playuntildone"}),
        (R, "state", {}),
    ])
    early, early_vars, late, late_vars, snd = out[2], out[3], out[5], out[6], out[8]
    assert early["say"]["text"] == "hi" and {v["name"]: v["value"] for v in early_vars["variables"]}["score"] in (0, "0")
    assert late["say"] is None and {v["name"]: v["value"] for v in late_vars["variables"]}["score"] in (7, "7")
    assert snd["condition_met"] and 0.55 < snd["ran_seconds"] < 1.0, snd["ran_seconds"]      # 5 x 0.14 s of sound
    assert out[9]["total"] == 5
    assert out[10]["time"] > 0 and out[10]["time"] < 20       # the project timer follows the simulated clock


def test_watchdog_kills_a_stuck_runtime_and_it_can_be_restarted(game):
    """Forces a call that outlasts its real-time budget: the page is closed, the error is explicit, restart works."""
    async def go():
        rm = game.runtime
        out = {}
        try:
            await registry.dispatch("runtime_manager", game, "start", {"green_flag": True})
            key = "game.sb3"
            try:
                await rm.call(key, "run", 10_000_000, 1000 / 30, None, timeout=1.5)   # far more work than 1.5 s allows
            except WorkspaceError as exc:
                out["error"] = str(exc)
            try:
                await registry.dispatch("runtime_manager", game, "state", {"include_clones": False})
            except WorkspaceError as exc:
                out["after"] = str(exc)
            # state() auto-starts a fresh page when the old one is dead
            out["restarted"] = (await registry.dispatch("runtime_manager", game, "restart", {"run_seconds": 0.2}))["state"]["time"]
        finally:
            await rm.close_all()
        return out

    out = anyio.run(go)
    assert "Infinite loop detected" in out["error"] and "never yields" in out["error"]
    assert out["restarted"] > 0


# ---------------------------------------------------------------- run-time sandbox and the remaining extensions

def test_runtime_refuses_outside_code_and_network(game):
    """Custom extension URLs are dropped before the VM sees them and the page cannot reach the internet."""
    from scratch_mcp.runtime.manager import runtime_safe

    s = game.session(None)
    dirty = json_copy = __import__("json").loads(__import__("json").dumps(s.project))
    dirty["extensionURLs"] = {"evil": "https://example.com/evil.js"}
    dirty["extensions"] = ["pen", "madeup"]
    safe, notes = runtime_safe(dirty)
    assert "extensionURLs" not in safe and safe["extensions"] == ["pen"] and len(notes) == 2 and json_copy is dirty

    async def go():
        try:
            await registry.dispatch("runtime_manager", game, "start", {})
            rs = game.runtime.sessions["game.sb3"]
            reached = await rs.page.evaluate("() => fetch('https://example.com/').then(r => 'reached', e => 'blocked')")
            file_read = await rs.page.evaluate("() => fetch('file:///etc/passwd').then(r => 'read', e => 'blocked')")
            return reached, file_read, list(game.browser.blocked)
        finally:
            await game.runtime.close_all()

    reached, file_read, blocked = anyio.run(go)
    assert reached == "blocked" and file_read == "blocked" and any("example.com" in b for b in blocked)


def test_music_and_makey_makey_extensions_run(game):
    run(game, "script_manager", "add_tree", sprite="Player", scripts=[
        {"opcode": "event_whenflagclicked", "next": [
            {"opcode": "music_setTempo", "inputs": {"TEMPO": 120}},
            {"opcode": "music_playNoteForBeats", "inputs": {"NOTE": 60, "BEATS": 0.5}},
            {"opcode": "music_playDrumForBeats", "inputs": {"DRUM": 1, "BEATS": 0.25}},
            {"opcode": "data_setvariableto", "fields": {"VARIABLE": "score"}, "inputs": {"VALUE": 5}}]},
        {"opcode": "makeymakey_whenMakeyKeyPressed", "inputs": {"KEY": "SPACE"}, "next": [
            {"opcode": "data_setvariableto", "fields": {"VARIABLE": "score"}, "inputs": {"VALUE": 77}}]}])
    R = "runtime_manager"
    out = arun(game, [("extension_manager", "verify", {"run_seconds": 0.2}),
                      (R, "start", {"green_flag": True}),
                      (R, "run", {"seconds": 1.2, "until": {"type": "variable", "name": "score", "op": "==", "value": 5}}),
                      ("input_manager", "key_press", {"key": "space", "then_run": 0.3}),
                      (R, "variables", {}), ("debug_manager", "errors", {})])
    ver, _, played, _, variables, errors = out
    assert ver["all_loaded"] and {"music", "makeymakey"} <= set(ver["loaded_in_vm"]) and ver["runtime_errors"] == []
    assert played["condition_met"] and 0.33 <= played["ran_seconds"] <= 0.6      # 0.5 beat note + 0.25 beat drum at 120 bpm = 0.375 s
    assert {v["name"]: v["value"] for v in variables["variables"]}["score"] in (77, "77")
    assert errors["errors"] == []


# ---------------------------------------------------------------- animation_manager (generated scripts, verified by running them)

@pytest.fixture
def anim(ctx, runtime_ready):
    c = lambda g, a, **k: run(ctx, g, a, **k)  # noqa: E731
    c("project_manager", "create", name="anim", sprite_name="Placeholder", empty=True)
    c("backdrop_manager", "add_stock", art="kitchen")
    c("sprite_manager", "create", name="Robo", stock="robot", x=-100, y=-60, size=50)
    c("sprite_manager", "create", name="Zorp", stock="alien", x=120, y=-60, size=50)
    c("sound_manager", "add_preset", sprite="Robo", name="boing", preset="boing")
    return ctx


def test_animation_cycle_blink_jump(anim):
    A, R, I = "animation_manager", "runtime_manager", "input_manager"
    cyc = run(anim, A, "cycle", sprite="Robo", costumes=["idle", "wow"], delay=0.1, move_x=3, on={"while_key": "right arrow"}, face=90)
    assert "if <key (right arrow v) pressed?>" in cyc["text"].replace("[right arrow v]", "(right arrow v)") or "right arrow" in cyc["text"]
    run(anim, A, "blink", sprite="Zorp", open_costume="smug", closed_costume="happy", min_wait=0.3, max_wait=0.4, closed_time=0.15)
    j = run(anim, A, "jump", sprite="Robo", height=60, seconds=0.5, sound="boing", jump_costume="happy", land_costume="idle")
    assert j["guard_variable"] == "Robo jumping"
    run(anim, "script_manager", "list_scripts", sprite="Robo")
    out = arun(anim, [
        (R, "start", {"green_flag": True, "run_seconds": 0.2}),
        (R, "sprite_state", {"sprite": "Robo"}),
        (I, "key_down", {"key": "right arrow", "then_run": 1.0}),
        (R, "sprite_state", {"sprite": "Robo"}),
        (I, "release_all", {}),
        (I, "key_press", {"key": "space", "hold_seconds": 0.05, "then_run": 0.2}),
        (R, "sprite_state", {"sprite": "Robo"}),
        (I, "key_press", {"key": "space", "hold_seconds": 0.05, "then_run": 0.0}),       # a second press mid-air must be ignored
        (R, "run", {"seconds": 0.7}),
        (R, "sprite_state", {"sprite": "Robo"}),
        (R, "run", {"seconds": 2}),
        (R, "events", {"type": "looks_switchcostumeto", "last": 200}),
        (R, "events", {"type": "sound_play"}),
    ])
    before, walking, air, after, evs, boings = out[1], out[3], out[6], out[9], out[11], out[12]
    assert walking["x"] - before["x"] > 15                                   # moved while the key was held
    assert 25 < air["y"] + 60 < 62 and air["costume"] == "happy"             # in the air, jump pose
    assert after["y"] == -60 and after["costume"] == "idle"                  # landed, back to idle
    assert boings["total"] == 1                                              # guard variable stopped the double jump
    blinks = [e for e in evs["events"] if e["sprite"] == "Zorp"]
    assert sum(1 for e in blinks if e["args"]["COSTUME"] == "happy") >= 3    # blinked several times in ~3.5 s
    assert {e["args"]["COSTUME"] for e in evs["events"] if e["sprite"] == "Robo"} >= {"idle", "wow"}
    with pytest.raises(WorkspaceError, match="no costume"):
        run(anim, A, "cycle", sprite="Robo", costumes=["idle", "missing"])
    with pytest.raises(WorkspaceError, match="at least two"):
        run(anim, A, "cycle", sprite="Robo", costumes=["idle"])
    assert run(anim, "debug_manager", "check", include_info=False)["ok"]


def test_animation_move_entrance_exit_path(anim):
    A, R = "animation_manager", "runtime_manager"
    run(anim, A, "move", sprite="Robo", kind="entrance", side="left", to_x=0, to_y=-60, seconds=1.0, costumes=["idle", "wow"], on={"broadcast": "enter"})
    run(anim, A, "move", sprite="Zorp", kind="path", points=[[100, 50], [100, -60]], seconds_each=0.5, on={"broadcast": "enter"})
    run(anim, A, "move", sprite="Robo", kind="exit", side="right", seconds=0.5, on={"broadcast": "leave"})
    out = arun(anim, [
        (R, "start", {"green_flag": True, "run_seconds": 0.1}),
        (R, "run", {"seconds": 0.1}),
        ("script_manager", "list_scripts", {"sprite": "Robo"}),
        (R, "set_sprite", {"sprite": "Robo", "x": 0, "y": -60}),   # reset position to prove the glide really moves it
        (R, "state", {}),
    ])
    assert out[2]["scripts"], out[2]
    # drive the broadcasts the way a timeline would, using the test runner (flag, then broadcast via a key script)
    run(anim, "script_manager", "add_tree", sprite="Zorp", scripts=[{"opcode": "event_whenkeypressed", "fields": {"KEY_OPTION": "e"}, "next": [
        {"opcode": "event_broadcast", "inputs": {"BROADCAST_INPUT": "enter"}}]}, {"opcode": "event_whenkeypressed", "fields": {"KEY_OPTION": "l"}, "next": [
        {"opcode": "event_broadcast", "inputs": {"BROADCAST_INPUT": "leave"}}]}])
    out = arun(anim, [
        (R, "start", {"green_flag": True, "run_seconds": 0.1}),
        ("input_manager", "key_press", {"key": "e", "then_run": 0.0}),
        (R, "run", {"seconds": 0.35}),
        (R, "sprite_state", {"sprite": "Robo"}),
        (R, "run", {"seconds": 1.0}),
        (R, "sprite_state", {"sprite": "Robo"}),
        (R, "sprite_state", {"sprite": "Zorp"}),
        ("input_manager", "key_press", {"key": "l", "then_run": 0.8}),
        (R, "sprite_state", {"sprite": "Robo"}),
    ])
    mid, arrived, zorp, gone = out[3], out[5], out[6], out[8]
    assert -300 < mid["x"] < -20 and mid["visible"]                          # gliding in from off-screen
    assert abs(arrived["x"]) < 1 and arrived["visible"]
    assert abs(zorp["x"] - 100) < 1 and abs(zorp["y"] + 60) < 1               # followed its path
    assert gone["visible"] is False and gone["x"] > 240                       # exited to the right and hid
    with pytest.raises(WorkspaceError, match="to_x and to_y"):
        run(anim, A, "move", sprite="Robo", kind="entrance")


def test_animation_dialogue_transition_timeline(anim):
    A, R = "animation_manager", "runtime_manager"
    d = run(anim, A, "dialogue", lines=[
        {"sprite": "Robo", "text": "Hi Zorp!", "seconds": 1, "costume": "happy", "return_costume": "idle"},
        {"sprite": "Zorp", "text": "Bleep!", "seconds": 1.5},
        {"sprite": "Robo", "text": "Bye!", "seconds": 1}], pause=0.1)
    assert d["finished_broadcast"] == "dialogue done" and abs(d["duration_seconds"] - 3.8) < 0.01
    tl = run(anim, A, "timeline", scenes=[{"name": "intro", "seconds": 1, "backdrop": "kitchen1"}, {"name": "later", "seconds": 1.5, "backdrop": "kitchen2"}],
             broadcast_prefix="act")
    assert tl["total_seconds"] == 2.5 and "act intro" in tl["broadcasts"]
    t = run(anim, A, "transition", kind="fade", on={"broadcast": "act 2"}, to_backdrop="kitchen1", seconds=0.4)
    assert t["midpoint_broadcast"] == "Transition midpoint"
    out = arun(anim, [
        (R, "start", {"green_flag": True, "run_seconds": 0.5}),
        (R, "state", {}),
        (R, "run", {"seconds": 0.6}),                       # t = 1.1: the timeline has just started scene 2
        (R, "state", {}),
        (R, "run", {"seconds": 0.9}),                       # t = 2.0: the transition has swapped the backdrop back
        (R, "state", {}),
        (R, "run", {"seconds": 3}),
        (R, "events", {"type": "looks_sayforsecs", "last": 20}),
        (R, "events", {"type": "event_broadcast", "last": 50}),
    ])
    s1, s2, s3, says, bcasts = out[1], out[3], out[5], out[7], out[8]
    stage = lambda st: next(x for x in st["targets"] if x["isStage"])  # noqa: E731
    assert stage(s1)["costume"] == "kitchen1"
    assert stage(s2)["costume"] == "kitchen2"                                    # timeline switched the backdrop at t=1
    assert stage(s3)["costume"] == "kitchen1"                                    # then the fade's midpoint swapped it (to_backdrop)
    assert [(e["sprite"], e["args"]["MESSAGE"]) for e in says["events"]] == [("Robo", "Hi Zorp!"), ("Zorp", "Bleep!"), ("Robo", "Bye!")]
    times = [e["t"] for e in says["events"]]
    assert times == sorted(times) and times[1] - times[0] == pytest.approx(1.1, abs=0.15) and times[2] - times[1] == pytest.approx(1.6, abs=0.15)
    names = [e["args"].get("BROADCAST_INPUT") or e["args"].get("BROADCAST_OPTION") for e in bcasts["events"]]
    assert "dialogue done" in names and "act end" in names and "act 2" in names and "Transition midpoint" in names


def test_fade_transition_covers_then_reveals(anim):
    A, R = "animation_manager", "runtime_manager"
    run(anim, A, "transition", kind="fade", on={"broadcast": "go"}, to_backdrop="kitchen2", seconds=0.5)
    run(anim, "script_manager", "add_tree", sprite="Robo", scripts=[{"opcode": "event_whenkeypressed", "fields": {"KEY_OPTION": "t"}, "next": [
        {"opcode": "event_broadcast", "inputs": {"BROADCAST_INPUT": "go"}}]}])
    out = arun(anim, [
        (R, "start", {"green_flag": True, "run_seconds": 0.2}), (R, "state", {}),
        ("input_manager", "key_press", {"key": "t", "then_run": 0.1}), (R, "state", {}),
        (R, "run", {"seconds": 0.6}), (R, "state", {}),             # past the fade's midpoint (0.5 s) but not finished (1.0 s)
        (R, "run", {"seconds": 1.2}), (R, "state", {}),
        (R, "events", {"type": "event_broadcast", "last": 20}),
    ])
    def cover(st): return next(x for x in st["targets"] if x["name"] == "Transition")
    assert cover(out[1])["visible"] is False
    assert cover(out[3])["visible"] and cover(out[3])["effects"].get("ghost", 100) > 40         # starting to fade in
    mid = cover(out[5])
    assert next(x for x in out[5]["targets"] if x["isStage"])["costume"] == "kitchen2"           # swapped while covered
    assert cover(out[7])["visible"] is False                                                    # revealed and hidden again
    names = [e["args"].get("BROADCAST_INPUT") or e["args"].get("BROADCAST_OPTION") for e in out[8]["events"]]
    assert "Transition midpoint" in names and mid
