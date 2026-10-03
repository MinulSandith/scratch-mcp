"""End-to-end acceptance run: "Robot's First Adventure", built ONLY through MCP tool calls.

This script plays the role of the AI agent: it starts the real server over stdio and calls tools, exactly like
Claude Desktop would. It writes nothing into the project itself. Every call is logged (success / failure) and
the log, screenshots, the exported .sb3 and a recorded MP4 end up in the output folder.

    python scripts/e2e_robots_first_adventure.py OUT_DIR [--video-seconds 15]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT = "Robot's First Adventure"
FLOOR_Y = -80  # robots/aliens stand here (feet on the pavement)


def op(opcode: str, inputs: dict | None = None, fields: dict | None = None, nxt: list | None = None) -> dict:
    t: dict[str, Any] = {"opcode": opcode}
    if inputs:
        t["inputs"] = inputs
    if fields:
        t["fields"] = fields
    if nxt:
        t["next"] = nxt
    return t


def key_pressed(k: str) -> dict:
    return op("sensing_keypressed", {"KEY_OPTION": k})


def var_eq(name: str, v: Any) -> dict:
    return op("operator_equals", {"OPERAND1": {"variable": name}, "OPERAND2": v})


class Agent:
    """Thin MCP client that records every call."""

    def __init__(self, session: ClientSession, out: Path):
        self.s, self.out, self.log = session, out, []
        self.images = 0

    async def call(self, tool: str, action: str, expect_error: bool = False, **args: Any) -> Any:
        t0 = time.time()
        res = await self.s.call_tool(tool, {"action": action, "args": args})
        text = "".join(c.text for c in res.content if c.type == "text")
        ok = (not res.isError) != expect_error
        entry = {"tool": tool, "action": action, "ok": ok, "error": bool(res.isError), "seconds": round(time.time() - t0, 2),
                 "summary": (text.replace("\n", " ")[:160])}
        self.log.append(entry)
        if not ok:
            raise RuntimeError(f"{tool}.{action} {'unexpectedly succeeded' if expect_error else 'failed'}: {text[:600]}")
        for c in res.content:
            if c.type == "image":
                self.images += 1
                (self.out / f"shot-{self.images:02d}-{action}.png").write_bytes(base64.b64decode(c.data))
        try:
            return json.loads(text) if text.startswith(("{", "[")) else text
        except ValueError:
            return text

    async def draw(self, shape: str, sprite: str, costume: str, **kw: Any) -> dict:
        return await self.call("costume_manager", "draw", shape=shape, sprite=sprite, costume=costume, **kw)


# ----------------------------------------------------------------------------------------------------------------
async def build_city(a: Agent) -> None:
    """A futuristic night-city backdrop drawn shape by shape with the vector editor."""
    S, C = "Stage", "city"
    await a.call("backdrop_manager", "add_blank", name=C, background="#0b1030")
    rnd = random.Random(7)
    for _ in range(26):
        await a.draw("circle", S, C, cx=rnd.randint(5, 475), cy=rnd.randint(5, 150), r=rnd.choice([0.8, 1.2, 1.6]), fill="#ffffff", opacity=rnd.choice([0.6, 0.9]))
    await a.draw("circle", S, C, cx=405, cy=62, r=30, fill="#fff3c4")
    await a.draw("circle", S, C, cx=395, cy=55, r=6, fill="#e6d79b")
    await a.draw("circle", S, C, cx=415, cy=72, r=4, fill="#e6d79b")
    x = 0
    far = []
    while x < 480:  # far skyline
        w, h = rnd.randint(30, 55), rnd.randint(70, 150)
        far.append((x, w, h))
        await a.draw("rect", S, C, x=x, y=285 - h, width=w, height=h, fill="#1a2557")
        x += w + 2
    x = -10
    while x < 480:  # near buildings with lit windows and neon roofs
        w, h = rnd.randint(46, 80), rnd.randint(60, 120)
        top = 285 - h
        await a.draw("rect", S, C, x=x, y=top, width=w, height=h, fill="#26397a", stroke="#3a55a8", stroke_width=1)
        neon = rnd.choice(["#ff3df0", "#35f2ff", "#7dff6a"])
        await a.draw("rect", S, C, x=x, y=top - 3, width=w, height=3, fill=neon)
        for wy in range(top + 8, 280, 14):
            for wx in range(int(x) + 6, int(x) + w - 8, 12):
                if rnd.random() < 0.55:
                    await a.draw("rect", S, C, x=wx, y=wy, width=6, height=7, fill=rnd.choice(["#ffe08a", "#8af3ff", "#ffb3f6"]))
        x += w + rnd.randint(2, 8)
    for cx, cy, col in [(90, 120, "#35f2ff"), (300, 90, "#ff3df0")]:  # flying cars with glow
        await a.draw("ellipse", S, C, cx=cx, cy=cy + 4, rx=26, ry=7, fill=col, opacity=0.25)
        await a.draw("rect", S, C, x=cx - 14, y=cy - 4, width=28, height=8, fill="#cfd8ff", stroke=col, stroke_width=1.5)
        await a.draw("circle", S, C, cx=cx + 6, cy=cy - 4, r=4, fill=col)
    await a.draw("rect", S, C, x=0, y=285, width=480, height=75, fill="#2a2a40")          # pavement and road
    await a.draw("rect", S, C, x=0, y=285, width=480, height=12, fill="#4a4a6a")
    await a.draw("rect", S, C, x=0, y=296, width=480, height=2, fill="#35f2ff")
    for lx in range(10, 480, 70):
        await a.draw("rect", S, C, x=lx, y=335, width=36, height=4, fill="#ffe08a")
    await a.draw("text", S, C, text="NEO CITY", x=240, y=36, font_size=22, bold=True, anchor="middle", fill="#ff3df0")


async def build_characters(a: Agent) -> None:
    await a.call("sprite_manager", "create", name="Robo", stock="robot", x=-180, y=FLOOR_Y, size=55)
    await a.call("sprite_manager", "create", name="Zorp", stock="alien", x=150, y=FLOOR_Y + 8, size=55)
    # walking frames: duplicate the idle pose and tilt it (a waddle), through the vector editor
    for name, angle in (("walk1", -6), ("walk2", 6)):
        await a.call("costume_manager", "duplicate", sprite="Robo", costume="idle", new_name=name)
        els = await a.call("costume_manager", "elements", sprite="Robo", costume=name)
        await a.call("costume_manager", "transform", sprite="Robo", costume=name, id=els["elements"][0]["id"], rotate=angle, move_y=-1 if angle < 0 else 0)
    await a.call("sprite_manager", "set", sprite="Robo", rotation_style="left-right", costume="idle")
    await a.call("sprite_manager", "set", sprite="Zorp", rotation_style="left-right")
    # a collectible battery, drawn with the editor
    await a.call("sprite_manager", "create", name="Battery", x=120, y=FLOOR_Y + 5)
    await a.call("costume_manager", "set_canvas", sprite="Battery", costume="costume1", width=26, height=40)
    await a.draw("rect", "Battery", "costume1", x=3, y=8, width=20, height=30, rx=4, fill="#39d353", stroke="#145a22", stroke_width=2)
    await a.draw("rect", "Battery", "costume1", x=9, y=3, width=8, height=6, fill="#cfd8ff", stroke="#145a22", stroke_width=1.5)
    await a.draw("polygon", "Battery", "costume1", points=[[14, 12], [8, 24], [13, 24], [11, 34], [19, 21], [14, 21]], fill="#ffe14d")
    await a.call("costume_manager", "set_center", sprite="Battery", costume="costume1", mode="center")
    # full-screen black used for scene transitions
    await a.call("sprite_manager", "create", name="Fader", x=0, y=0, visible=False)
    await a.call("costume_manager", "add_blank", sprite="Fader", name="black", width=480, height=360, background="#000000")
    await a.call("costume_manager", "delete", sprite="Fader", costume="costume1")
    await a.call("sprite_manager", "layer", sprite="Fader", mode="front")


async def build_audio(a: Agent) -> None:
    await a.call("sound_manager", "add_preset", sprite="Stage", name="music", preset="music_cheerful", seconds=24, tempo=118)
    await a.call("sound_manager", "add_preset", sprite="Stage", name="whoosh", preset="whoosh")
    await a.call("sound_manager", "add_preset", sprite="Robo", name="boing", preset="boing")
    await a.call("sound_manager", "add_preset", sprite="Robo", name="bloop", preset="bloop")
    await a.call("sound_manager", "add_preset", sprite="Battery", name="chime", preset="chime")
    await a.call("sound_manager", "add_preset", sprite="Zorp", name="warble", preset="alien_warble")
    # shape one sound with the audio editor: softer + echo on the whoosh
    await a.call("sound_manager", "edit", sprite="Stage", sound="whoosh", operation="volume", factor=0.7)
    pv = await a.call("sound_manager", "preview", sprite="Zorp", sound="warble")
    assert isinstance(pv, dict) and not pv.get("silent"), pv


async def build_scripts(a: Agent) -> None:
    await a.call("variable_manager", "create_variable", name="score", value=0)
    await a.call("variable_manager", "create_variable", name="scene", value=1)
    await a.call("variable_manager", "create_variable", name="jumping", value=0)
    await a.call("variable_manager", "set_monitor", name="score", mode="large", x=5, y=5)

    await a.call("script_manager", "add_tree", sprite="Stage", scripts=[
        op("event_whenflagclicked", nxt=[
            op("looks_switchbackdropto", {"BACKDROP": "city"}),
            op("data_setvariableto", {"VALUE": 0}, {"VARIABLE": "score"}),
            op("data_setvariableto", {"VALUE": 1}, {"VARIABLE": "scene"}),
            op("data_setvariableto", {"VALUE": 0}, {"VARIABLE": "jumping"})]),
        op("event_whenflagclicked", nxt=[op("control_forever", {"SUBSTACK": [op("sound_playuntildone", {"SOUND_MENU": "music"})]})]),
        op("event_whenbroadcastreceived", fields={"BROADCAST_OPTION": "change scene"}, nxt=[
            op("sound_play", {"SOUND_MENU": "whoosh"}),
            op("control_wait", {"DURATION": 0.5}),
            op("data_changevariableby", {"VALUE": 1}, {"VARIABLE": "scene"}),
            op("control_if_else", {"CONDITION": var_eq("scene", 2),
                                   "SUBSTACK": [op("looks_switchbackdropto", {"BACKDROP": "kitchen1"})],
                                   "SUBSTACK2": [op("looks_switchbackdropto", {"BACKDROP": "city"}),
                                                 op("data_setvariableto", {"VALUE": 1}, {"VARIABLE": "scene"})]}),
            op("event_broadcast", {"BROADCAST_INPUT": "scene ready"})]),
    ])

    walk_cycle = [op("looks_switchcostumeto", {"COSTUME": "walk1"}), op("control_wait", {"DURATION": 0.08}),
                  op("looks_switchcostumeto", {"COSTUME": "walk2"}), op("control_wait", {"DURATION": 0.08})]
    moving = op("operator_or", {"OPERAND1": key_pressed("right arrow"), "OPERAND2": key_pressed("left arrow")})
    await a.call("script_manager", "add_tree", sprite="Robo", scripts=[
        op("event_whenflagclicked", nxt=[
            op("motion_gotoxy", {"X": -180, "Y": FLOOR_Y}), op("motion_pointindirection", {"DIRECTION": 90}),
            op("looks_switchcostumeto", {"COSTUME": "idle"}), op("looks_show"),
            op("control_forever", {"SUBSTACK": [
                op("control_if", {"CONDITION": key_pressed("right arrow"), "SUBSTACK": [
                    op("motion_pointindirection", {"DIRECTION": 90}), op("motion_changexby", {"DX": 4})]}),
                op("control_if", {"CONDITION": key_pressed("left arrow"), "SUBSTACK": [
                    op("motion_pointindirection", {"DIRECTION": -90}), op("motion_changexby", {"DX": -4})]}),
                op("control_if_else", {"CONDITION": op("operator_and", {"OPERAND1": var_eq("jumping", 0), "OPERAND2": moving}),
                                       "SUBSTACK": walk_cycle,
                                       "SUBSTACK2": [op("control_if", {"CONDITION": var_eq("jumping", 0),
                                                                       "SUBSTACK": [op("looks_switchcostumeto", {"COSTUME": "idle"})]})]})]})]),
        # jumping animation
        op("event_whenkeypressed", fields={"KEY_OPTION": "space"}, nxt=[
            op("control_if", {"CONDITION": var_eq("jumping", 0), "SUBSTACK": [
                op("data_setvariableto", {"VALUE": 1}, {"VARIABLE": "jumping"}),
                op("sound_play", {"SOUND_MENU": "boing"}),
                op("looks_switchcostumeto", {"COSTUME": "happy"}),
                op("control_repeat", {"TIMES": 10, "SUBSTACK": [op("motion_changeyby", {"DY": 9})]}),
                op("control_repeat", {"TIMES": 10, "SUBSTACK": [op("motion_changeyby", {"DY": -9})]}),
                op("motion_sety", {"Y": FLOOR_Y}),
                op("data_setvariableto", {"VALUE": 0}, {"VARIABLE": "jumping"})]})]),
        # leaving the right edge changes the scene
        op("event_whenflagclicked", nxt=[op("control_forever", {"SUBSTACK": [
            op("control_wait_until", {"CONDITION": op("operator_gt", {"OPERAND1": op("motion_xposition"), "OPERAND2": 200})}),
            op("event_broadcast", {"BROADCAST_INPUT": "change scene"}),
            op("control_wait", {"DURATION": 1.2})]})]),
        op("event_whenbroadcastreceived", fields={"BROADCAST_OPTION": "scene ready"}, nxt=[
            op("motion_gotoxy", {"X": -200, "Y": FLOOR_Y}), op("motion_pointindirection", {"DIRECTION": 90})]),
        # dialogue, part 1 and 3
        op("event_whenflagclicked", nxt=[
            op("control_wait", {"DURATION": 0.5}),
            op("looks_sayforsecs", {"MESSAGE": "Hello! I'm Robo.", "SECS": 2}),
            op("event_broadcast", {"BROADCAST_INPUT": "robo greeted"})]),
        op("event_whenbroadcastreceived", fields={"BROADCAST_OPTION": "zorp replied"}, nxt=[
            op("looks_sayforsecs", {"MESSAGE": "Nice to meet you! Use the arrow keys.", "SECS": 2.5})]),
        op("event_whenkeypressed", fields={"KEY_OPTION": "right arrow"}, nxt=[op("sound_play", {"SOUND_MENU": "bloop"})]),
    ])

    await a.call("script_manager", "add_tree", sprite="Zorp", scripts=[
        op("event_whenflagclicked", nxt=[op("motion_gotoxy", {"X": 150, "Y": FLOOR_Y + 8}), op("motion_pointindirection", {"DIRECTION": -90}),
                                         op("looks_show"), op("looks_switchcostumeto", {"COSTUME": "smug"})]),
        op("event_whenbroadcastreceived", fields={"BROADCAST_OPTION": "robo greeted"}, nxt=[
            op("sound_play", {"SOUND_MENU": "warble"}),
            op("looks_sayforsecs", {"MESSAGE": "Bleep! I'm Zorp, from Planet Blorp.", "SECS": 2.5}),
            op("event_broadcast", {"BROADCAST_INPUT": "zorp replied"})]),
        # hovering
        op("event_whenflagclicked", nxt=[op("control_forever", {"SUBSTACK": [
            op("control_repeat", {"TIMES": 8, "SUBSTACK": [op("motion_changeyby", {"DY": 1}), op("control_wait", {"DURATION": 0.05})]}),
            op("control_repeat", {"TIMES": 8, "SUBSTACK": [op("motion_changeyby", {"DY": -1}), op("control_wait", {"DURATION": 0.05})]})]})]),
        # collision between the two characters
        op("event_whenflagclicked", nxt=[op("control_forever", {"SUBSTACK": [
            op("control_if", {"CONDITION": op("sensing_touchingobject", {"TOUCHINGOBJECTMENU": "Robo"}), "SUBSTACK": [
                op("looks_switchcostumeto", {"COSTUME": "happy"}), op("looks_sayforsecs", {"MESSAGE": "Friends!", "SECS": 1}),
                op("looks_switchcostumeto", {"COSTUME": "smug"})]})]})]),
        op("event_whenbroadcastreceived", fields={"BROADCAST_OPTION": "scene ready"}, nxt=[
            op("motion_gotoxy", {"X": 120, "Y": FLOOR_Y + 8})]),
    ])

    await a.call("script_manager", "add_tree", sprite="Battery", scripts=[
        op("event_whenflagclicked", nxt=[op("motion_gotoxy", {"X": 20, "Y": FLOOR_Y + 5}), op("looks_show"), op("control_forever", {"SUBSTACK": [
            op("control_if", {"CONDITION": op("sensing_touchingobject", {"TOUCHINGOBJECTMENU": "Robo"}), "SUBSTACK": [
                op("data_changevariableby", {"VALUE": 1}, {"VARIABLE": "score"}),
                op("sound_play", {"SOUND_MENU": "chime"}),
                op("motion_gotoxy", {"X": op("operator_random", {"FROM": -150, "TO": 150}), "Y": FLOOR_Y + 5}),
                op("control_wait", {"DURATION": 0.3})]})]})]),
    ])

    await a.call("script_manager", "add_tree", sprite="Fader", scripts=[
        op("event_whenflagclicked", nxt=[op("looks_hide"), op("looks_seteffectto", {"VALUE": 100}, {"EFFECT": "ghost"})]),
        op("event_whenbroadcastreceived", fields={"BROADCAST_OPTION": "change scene"}, nxt=[
            op("looks_show"), op("control_repeat", {"TIMES": 10, "SUBSTACK": [op("looks_changeeffectby", {"CHANGE": -10}, {"EFFECT": "ghost"}), op("control_wait", {"DURATION": 0.03})]})]),
        op("event_whenbroadcastreceived", fields={"BROADCAST_OPTION": "scene ready"}, nxt=[
            op("control_repeat", {"TIMES": 10, "SUBSTACK": [op("looks_changeeffectby", {"CHANGE": 10}, {"EFFECT": "ghost"}), op("control_wait", {"DURATION": 0.03})]}),
            op("looks_hide")]),
    ])


# ----------------------------------------------------------------------------------------------------------------
async def main_async(out: Path, video_seconds: float) -> dict:
    root = out / "projects"
    root.mkdir(parents=True, exist_ok=True)
    # MCP clients give servers a minimal environment by default; pass ours so SCRATCH_MCP_RUNTIME / proxy settings reach it
    params = StdioServerParameters(command=sys.executable, args=["-m", "scratch_mcp", "--root", str(root)], env=dict(os.environ))
    report: dict[str, Any] = {"project": PROJECT, "steps": []}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            a = Agent(session, out)
            t = a.call

            async def step(name: str, coro) -> Any:
                try:
                    r = await coro
                    report["steps"].append({"step": name, "ok": True})
                    return r
                except Exception as exc:  # noqa: BLE001
                    report["steps"].append({"step": name, "ok": False, "error": str(exc)[:600]})
                    raise

            await step("runtime setup", t("runtime_manager", "setup"))
            await step("create project", t("project_manager", "create", name=PROJECT, sprite_name="Placeholder", empty=True))
            await t("project_manager", "set_autosave", enabled=False)   # build in memory, save once (also exercises dirty tracking)
            await step("city backdrop", build_city(a))
            await step("stock scene 2 backdrop", t("backdrop_manager", "add_stock", art="kitchen"))
            await step("characters, battery, fader", build_characters(a))
            await step("audio", build_audio(a))
            await step("scripts", build_scripts(a))
            status = await t("project_manager", "status")
            report["dirty_before_save"] = status["open"][0]["dirty"]
            saved = await t("project_manager", "save")
            report["saved"] = saved
            await t("backdrop_manager", "set_initial", backdrop="city")
            await t("project_manager", "set_autosave", enabled=True)

            # ---- look at it
            diag = await step("diagnose", t("debug_manager", "diagnose", seconds=4))
            report["diagnose"] = {k: diag[k] for k in ("ok", "counts")} | {"errors": [p for p in diag["problems"] if p["severity"] == "error"]}
            await t("runtime_manager", "start", green_flag=True, run_seconds=0.4)
            await t("runtime_manager", "screenshot")                                    # opening frame
            await t("runtime_manager", "run", seconds=1.6)
            await t("runtime_manager", "screenshot")                                    # dialogue visible
            await t("runtime_manager", "snapshot", name="before-walk")
            await t("input_manager", "key_down", key="right arrow", then_run=1.5)
            await t("runtime_manager", "compare", against="before-walk")
            await t("input_manager", "release_all")
            await t("input_manager", "key_press", key="space", hold_seconds=0.1, then_run=0.15)
            await t("runtime_manager", "screenshot")                                    # mid-jump

            # ---- automated tests through simulated input
            tests = [
                ("walk right", dict(kind="keyboard", sprite="Robo", key="right arrow", property="x", change="increase", hold=0.6)),
                ("walk left", dict(kind="keyboard", sprite="Robo", key="left arrow", property="x", change="decrease", hold=0.6)),
                ("jump", dict(kind="keyboard", sprite="Robo", key="space", property="y", change="increase", hold=0.1)),
                ("walking animation", dict(kind="animation", sprite="Robo", seconds=1, minimum=1)),
                ("battery collision + score", dict(kind="collision", sprite="Robo", other="Battery", variable="score", op=">=", value=1)),
                ("dialogue 1", dict(kind="say", sprite="Robo", text="Hello", seconds=2)),
                ("dialogue 2", dict(kind="say", sprite="Zorp", text="Zorp", seconds=5)),
                ("music loop", dict(kind="audio", sound="music", seconds=1)),
                ("boing on jump", None),
            ]
            results: dict[str, bool] = {}
            for name, params in tests:
                if params is None:
                    r = await t("testing_manager", "run_scenario", name=name, steps=[
                        {"do": "flag", "run_seconds": 0.3}, {"do": "key_press", "key": "space", "hold": 0.1},
                        {"expect": {"sound_played": "boing"}}, {"expect": {"broadcast_sent": "robo greeted"}, "within": 4}])
                else:
                    r = await t("testing_manager", "quick", name=name, **params)
                results[name] = bool(r.get("passed")) if isinstance(r, dict) else False
                if isinstance(r, dict) and not r.get("passed"):
                    report.setdefault("failed_tests", {})[name] = r.get("steps")
            r = await t("testing_manager", "run_scenario", name="scene change", save=True, steps=[
                {"do": "flag", "run_seconds": 0.2}, {"do": "set_sprite", "sprite": "Robo", "x": 215},
                {"expect": {"sprite": "Stage", "property": "costume", "op": "==", "value": "kitchen1"}, "within": 2.5},
                {"expect": {"variable": "scene", "op": "==", "value": 2}},
                {"expect": {"sprite": "Robo", "property": "x", "op": "<", "value": -150}, "within": 1}])
            results["scene transition"] = bool(r.get("passed")) if isinstance(r, dict) else False
            if isinstance(r, dict) and not r.get("passed"):
                report.setdefault("failed_tests", {})["scene transition"] = r.get("steps")
            report["tests"] = results

            await t("runtime_manager", "start", green_flag=True, run_seconds=0.3)
            await t("runtime_manager", "set_sprite", sprite="Robo", x=215)
            await t("runtime_manager", "run", seconds=2.5)
            await t("runtime_manager", "screenshot")                                    # scene 2 (kitchen)

            # ---- deliver
            exp = await step("export sb3", t("export_manager", "sb3", name="robots-first-adventure", overwrite=True))
            report["export"] = exp
            reopened = await step("reopen exported project", t("project_manager", "import_sb3", name="reopened", source_path="exports/robots-first-adventure.sb3", overwrite=True))
            ov = await t("inspection_manager", "overview", project="reopened")
            report["reopened"] = {"sprites": [s["name"] for s in ov["sprites"]], "backdrops": ov["stage"]["costumes"], "blocks": ov["total_blocks"],
                                  "extensions": ov["extensions"], "validation_ok": (await t("project_manager", "validate", project="reopened"))["ok"]}
            report["reopened"]["import"] = {k: reopened[k] for k in ("imported", "counts")}
            vid = await step("record video", t("export_manager", "video", name="robots-first-adventure", seconds=video_seconds, overwrite=True, inputs=[
                {"at": 3.5, "key": "right arrow"}, {"at": 4.5, "key": "space"}, {"at": 7, "key": "space"}]))
            report["video"] = vid
            await t("runtime_manager", "stop")
            report["final_overview"] = {"sprites": [s["name"] for s in ov["sprites"]], "backdrops": ov["stage"]["costumes"],
                                        "global_variables": [v["name"] for v in ov["global_variables"]], "total_blocks": ov["total_blocks"]}
            report["calls"] = a.log
    report["ok_calls"] = sum(1 for c in report["calls"] if c["ok"])
    report["total_calls"] = len(report["calls"])
    report["failed_calls"] = [c for c in report["calls"] if not c["ok"]]
    (out / "e2e_report.json").write_text(json.dumps(report, indent=1))
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--video-seconds", type=float, default=15)
    args = ap.parse_args()
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    report = anyio.run(main_async, out, args.video_seconds)
    print(f"{report['ok_calls']}/{report['total_calls']} tool calls succeeded")
    print("tests:", json.dumps(report["tests"]))
    print("export ok:", report["export"]["ok"], "| loads in VM:", report["export"]["loads_in_scratch_vm"])
    print("video:", json.dumps(report["video"].get("verified")))


if __name__ == "__main__":
    main()
