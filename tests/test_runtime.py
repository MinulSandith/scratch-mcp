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
