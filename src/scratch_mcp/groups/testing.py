"""testing_manager: scripted test scenarios (input -> expectation) run in the real Scratch VM."""

from __future__ import annotations

import json
from typing import Any

from ..ctx import Ctx
from ..registry import GROUP_DOCS, Reply, action
from ..workspace import WorkspaceError
from . import inputs as I
from . import runtime as R

G = "testing_manager"
GROUP_DOCS[G] = (
    "Automated tests for the running project. A scenario is a list of steps: actions {\"do\": ...} and checks "
    "{\"expect\": ...}. Actions: start (reload project fresh), flag, run{seconds}, key_press{key,hold,then_run}, key_down{key}, "
    "key_up{key}, click{x,y}, click_sprite{sprite}, mouse_move{x,y}, drag{from_x,from_y,to_x,to_y}, answer{text}, "
    "set_variable{name,value}, set_sprite{sprite,x,y,...}, move_onto{sprite,other}, remember{as,sprite,property | variable}, stop. "
    "Checks (add \"within\": seconds to wait for it to become true): {\"sprite\":\"Robot\",\"property\":\"x\",\"op\":\">\",\"value\":10} "
    "(properties x y size direction visible costume say; ops == != > >= < <= contains; or \"than\":\"<remembered name>\" to compare with a "
    "remembered value); {\"variable\":\"score\",\"op\":\">=\",\"value\":3}; {\"touching\":[\"A\",\"B\"]}; {\"sound_played\":\"pop\"}; "
    "{\"broadcast_sent\":\"jump\"}; {\"costume_changed\":\"Robot\"}; {\"clones\":{\"sprite\":\"Bullet\",\"op\":\">=\",\"value\":2}}; "
    "{\"say\":{\"sprite\":\"Cat\",\"contains\":\"Hi\"}}; {\"asking\":\"name\"}. Use 'quick' for common tests (keyboard, click, "
    "collision, variable, broadcast, clones, animation, audio). A failing run returns a screenshot and the state so you can fix "
    "and 'rerun_failed'. Audio: plays are verified from the VM's run log (nothing is audible here)."
)

_tests: dict[str, dict[str, dict[str, Any]]] = {}


def normalize_expect(e: dict[str, Any]) -> dict[str, Any]:
    e = dict(e)
    if "type" in e:
        return e
    if "touching" in e:
        a, b = e["touching"]
        return {"type": "touching", "a": a, "b": b, "value": e.get("value", True)}
    if "sound_played" in e:
        return {"type": "count", "event": "sound_play", "arg": e["sound_played"], "op": e.get("op", ">="), "value": e.get("value", 1)}
    if "broadcast_sent" in e:
        return {"type": "count", "event": "event_broadcast", "arg": e["broadcast_sent"], "op": e.get("op", ">="), "value": e.get("value", 1)}
    if "costume_changed" in e:
        return {"type": "costume_changed", "sprite": e["costume_changed"], "value": e.get("value", 1)}
    if "clones" in e:
        c = dict(e["clones"])
        c["type"] = "clones"
        return c
    if "say" in e:
        s = e["say"]
        return {"type": "sprite", "sprite": s["sprite"], "property": "say", "op": "contains" if "contains" in s else "==",
                "value": s.get("contains", s.get("equals", ""))}
    if "asking" in e:
        return {"type": "question", "op": "contains", "value": e["asking"]}
    if "variable" in e:
        return {"type": "variable", "name": e["variable"], **{k: v for k, v in e.items() if k in ("op", "value", "sprite", "index")}}
    if "sprite" in e and "property" in e:
        return {"type": "sprite", **{k: v for k, v in e.items() if k in ("sprite", "property", "op", "value", "than")}}
    raise WorkspaceError(f"Can't understand check {json.dumps(e)}. See the tool description for the supported forms.")


async def run_step(ctx: Ctx, project: str | None, step: dict[str, Any], memory: dict[str, Any]) -> tuple[bool, str, Any]:
    """Execute one step. Returns (ok, detail, extra)."""
    rm = ctx.runtime
    if "do" in step:
        do, a = step["do"], {k: v for k, v in step.items() if k != "do"}
        session = ctx.session(project)
        if do == "start":
            await R.start(ctx, project, False, 0)
            memory.clear()
            return True, "project reloaded", None
        await R.ensure(ctx, project)
        if do == "flag":
            await R.green_flag(ctx, project, a.get("run_seconds", 0))
        elif do in ("run", "wait"):
            await R.run(ctx, a["seconds"], project)
        elif do == "key_press":
            await I.key_press(ctx, a["key"], a.get("hold", a.get("hold_seconds", 0.1)), a.get("then_run", 0.2), project)
        elif do == "key_down":
            await I.key_down(ctx, a["key"], a.get("then_run", 0), project)
        elif do == "key_up":
            await I.key_up(ctx, a["key"], a.get("then_run", 0), project)
        elif do == "click":
            await I.click(ctx, a["x"], a["y"], a.get("hold", 0.1), a.get("then_run", 0.2), project)
        elif do == "click_sprite":
            await I.click_sprite(ctx, a["sprite"], 0.1, a.get("then_run", 0.2), project)
        elif do == "mouse_move":
            await I.mouse_move(ctx, a["x"], a["y"], a.get("then_run", 0.1), project)
        elif do == "drag":
            await I.drag(ctx, a["from_x"], a["from_y"], a["to_x"], a["to_y"], a.get("seconds", 0.5), a.get("then_run", 0.2), project)
        elif do == "answer":
            await I.answer(ctx, a["text"], a.get("then_run", 0.2), project)
        elif do == "set_variable":
            await rm.call(session.name, "setVariable", a["name"], a["value"], a.get("sprite"))
        elif do == "set_sprite":
            props = {k: v for k, v in a.items() if k in ("x", "y", "direction", "size", "visible")}
            await rm.call(session.name, "setSprite", a["sprite"], props)
        elif do == "move_onto":
            st = await rm.call(session.name, "state")
            tgt = next((t for t in st["targets"] if t["name"] == a["other"] and not t["isStage"]), None)
            if tgt is None:
                raise WorkspaceError(f"No sprite '{a['other']}'.")
            await rm.call(session.name, "setSprite", a["sprite"], {"x": tgt["x"], "y": tgt["y"]})
        elif do == "stop":
            await rm.call(session.name, "stopAll")
        elif do == "remember":
            st = await rm.call(session.name, "state")
            if "variable" in a:
                val = next((v["value"] for v in st["variables"] if v["name"] == a["variable"]), None)
            else:
                t = next((t for t in st["targets"] if t["name"] == a["sprite"]), None)
                if t is None:
                    raise WorkspaceError(f"No sprite '{a['sprite']}'.")
                val = t.get(a["property"])
            memory[a["as"]] = val
            return True, f"remembered {a['as']} = {val}", None
        else:
            raise WorkspaceError(f"Unknown step action '{do}'.")
        return True, do, None
    if "expect" in step:
        cond = normalize_expect(step["expect"])
        if "than" in cond:
            if cond["than"] not in memory:
                raise WorkspaceError(f"Nothing was remembered as '{cond['than']}' (use a 'remember' step first).")
            cond["value"] = memory[cond["than"]]
        session = ctx.session(project)
        await R.ensure(ctx, project, auto_start=False)
        if step.get("within"):
            r = await rm.run_frames(session.name, R.frames_for(step["within"]), cond)
            ok, actual = bool(r["met"]), r["actual"]
        else:
            res = await rm.call(session.name, "check", cond)
            ok, actual = res["ok"], res["actual"]
        desc = json.dumps(step["expect"], ensure_ascii=False)
        return ok, f"{'ok' if ok else 'FAILED'}: {desc} (actual: {json.dumps(actual)})", actual
    raise WorkspaceError(f"A step needs 'do' or 'expect': {json.dumps(step)[:120]}")


async def execute(ctx: Ctx, project: str | None, name: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    session = ctx.session(project)
    memory: dict[str, Any] = {}
    results: list[dict[str, Any]] = []
    passed = True
    if not steps or "do" not in steps[0] or steps[0]["do"] != "start":
        steps = [{"do": "start"}, *steps]
    for i, step in enumerate(steps):
        try:
            ok, detail, _ = await run_step(ctx, project, step, memory)
        except WorkspaceError as exc:
            ok, detail = False, f"ERROR: {exc}"
        results.append({"step": i + 1, "ok": ok, "detail": detail, **({"label": step["name"]} if "name" in step else {})})
        if not ok:
            passed = False
            if "expect" in step or detail.startswith("ERROR"):
                break
    out: dict[str, Any] = {"scenario": name, "passed": passed, "steps": results, "project": session.name}
    rs = ctx.runtime.sessions.get(session.name)
    if rs and not rs.dead:
        st = await ctx.runtime.call(session.name, "state")
        out["final_time"] = st["time"]
        out["errors"] = ctx.runtime.errors(session.name)
        if not passed:
            out["final_state"] = {"sprites": {t["name"]: {k: t[k] for k in ("x", "y", "costume", "visible", "say") if k in t} for t in st["targets"] if not t["isStage"]},
                                  "variables": {v["name"]: v["value"] for v in st["variables"]}, "question": st["question"]}
    return out


def _store(ctx: Ctx, session) -> dict[str, dict[str, Any]]:
    return _tests.setdefault(session.name, {})


def _persist(ctx: Ctx, session) -> None:
    folder = ctx.ws.root / "tests"
    path = folder / (session.name.rsplit(".", 1)[0].replace("/", "__") + ".tests.json")
    data = {n: {"steps": t["steps"]} for n, t in _store(ctx, session).items()}
    if data:
        folder.mkdir(exist_ok=True)
        path.write_text(json.dumps(data, indent=1))
    elif path.exists():
        path.unlink()


def _load(ctx: Ctx, session) -> None:
    folder = ctx.ws.root / "tests"
    path = folder / (session.name.rsplit(".", 1)[0].replace("/", "__") + ".tests.json")
    if path.exists() and session.name not in _tests:
        _tests[session.name] = {n: {"steps": t["steps"], "last": None} for n, t in json.loads(path.read_text()).items()}


async def _report_reply(ctx: Ctx, session, result: dict[str, Any]) -> Reply | dict:
    if result["passed"]:
        return result
    try:
        png = await ctx.runtime.screenshot(session.name)
        return Reply(text=result, images=[(png, "image/png")])
    except WorkspaceError:
        return result


@action(G)
async def run_scenario(ctx: Ctx, steps: list[dict[str, Any]], name: str = "scenario", save: bool = False, project: str | None = None) -> Reply | dict:
    """Run one scenario (a fresh project start is added automatically). Returns pass/fail per step; on failure also a screenshot and the final state.

    Args:
        steps: list of {"do": ...} / {"expect": ...} steps (see tool description).
        name: label for the report / when saving.
        save: remember the scenario under `name` (also written to <projects>/tests/) so it can be re-run later.
    """
    session = ctx.session(project)
    _load(ctx, session)
    result = await execute(ctx, project, name, steps)
    store = _store(ctx, session)
    if save:
        store[name] = {"steps": steps, "last": None}
    if name in store:
        store[name]["last"] = result["passed"]
    if save:
        _persist(ctx, session)
    return await _report_reply(ctx, session, result)


@action(G)
async def define(ctx: Ctx, name: str, steps: list[dict[str, Any]], project: str | None = None) -> dict:
    """Save a scenario under a name without running it."""
    session = ctx.session(project)
    _load(ctx, session)
    for s in steps:
        if "expect" in s:
            normalize_expect(s["expect"])
    _store(ctx, session)[name] = {"steps": steps, "last": None}
    _persist(ctx, session)
    return {"saved": name, "scenarios": list(_store(ctx, session))}


@action(G, "list")
def list_tests(ctx: Ctx, project: str | None = None) -> dict:
    """Saved scenarios and whether their last run passed."""
    session = ctx.session(project)
    _load(ctx, session)
    return {"scenarios": [{"name": n, "steps": len(t["steps"]), "last_result": t["last"]} for n, t in _store(ctx, session).items()]}


@action(G)
def delete(ctx: Ctx, name: str, project: str | None = None) -> dict:
    """Delete a saved scenario."""
    session = ctx.session(project)
    _load(ctx, session)
    if _store(ctx, session).pop(name, None) is None:
        raise WorkspaceError(f"No saved scenario '{name}'.")
    _persist(ctx, session)
    return {"deleted": name}


@action(G)
async def run_all(ctx: Ctx, project: str | None = None, only_failed: bool = False) -> dict:
    """Run every saved scenario (or only those whose last run failed) against the project's current state."""
    session = ctx.session(project)
    _load(ctx, session)
    store = _store(ctx, session)
    results = []
    for n, t in store.items():
        if only_failed and t["last"] is not False:
            continue
        res = await execute(ctx, project, n, t["steps"])
        t["last"] = res["passed"]
        results.append(res)
    return {"ran": len(results), "passed": sum(r["passed"] for r in results), "failed": sum(not r["passed"] for r in results),
            "results": [{"scenario": r["scenario"], "passed": r["passed"], "failed_steps": [s for s in r["steps"] if not s["ok"]]} for r in results]}


@action(G)
async def rerun_failed(ctx: Ctx, project: str | None = None) -> dict:
    """Re-run only the scenarios that failed last time - use after fixing the project."""
    return await run_all(ctx, project, only_failed=True)


@action(G)
async def quick(ctx: Ctx, kind: str, project: str | None = None, sprite: str | None = None, key: str | None = None,
                property: str = "x", change: str = "increase", hold: float = 0.5, value: Any = None, op: str = "==",
                name: str | None = None, other: str | None = None, variable: str | None = None, message: str | None = None,
                seconds: float = 2, minimum: int = 1, sound: str | None = None, text: str | None = None, save: bool = False) -> Reply | dict:
    """Ready-made tests. kind:
    keyboard (sprite, key, property, change=increase|decrease|differ) - hold a key, the property must change;
    click (sprite, + say text / variable+value) - click the sprite and expect `text` to be said or `variable` op value;
    collision (sprite, other, + variable/value optional) - move `sprite` onto `other`, expect touching (and variable check);
    variable (variable, op, value, seconds) - after the flag the variable must reach op value within seconds;
    broadcast (message, seconds) - after the flag the message must be sent within seconds;
    clones (sprite, minimum, seconds) - at least `minimum` clones of sprite appear within seconds;
    animation (sprite, minimum) - the sprite switches costume at least `minimum` times within seconds;
    audio (sound) - the sound is started within seconds;
    say (sprite, text) - the sprite says text within seconds.

    Args:
        kind: one of the kinds above.
    """
    if kind == "keyboard":
        if not sprite or not key:
            raise WorkspaceError("keyboard needs sprite and key.")
        cmp = {"increase": ">", "decrease": "<", "differ": "!="}.get(change)
        if cmp is None:
            raise WorkspaceError("change must be increase, decrease or differ.")
        steps = [{"do": "flag", "run_seconds": 0.5}, {"do": "remember", "as": "before", "sprite": sprite, "property": property},
                 {"do": "key_press", "key": key, "hold": hold}, {"expect": {"sprite": sprite, "property": property, "op": cmp, "than": "before"}}]
    elif kind == "click":
        if not sprite:
            raise WorkspaceError("click needs sprite.")
        exp = {"say": {"sprite": sprite, "contains": text}} if text else {"variable": variable, "op": op, "value": value}
        if not text and not variable:
            raise WorkspaceError("click needs text (to be said) or variable+value.")
        steps = [{"do": "flag", "run_seconds": 0.5}, {"do": "click_sprite", "sprite": sprite, "then_run": 0.3}, {"expect": exp, "within": 2}]
    elif kind == "collision":
        if not sprite or not other:
            raise WorkspaceError("collision needs sprite and other.")
        steps = [{"do": "flag", "run_seconds": 0.3}, {"do": "move_onto", "sprite": sprite, "other": other},
                 {"expect": {"touching": [sprite, other]}}]  # checked right away, before any script can react
        if variable is not None:
            steps.append({"expect": {"variable": variable, "op": op, "value": value}, "within": 1})
    elif kind == "variable":
        if not variable:
            raise WorkspaceError("variable needs variable (name).")
        steps = [{"do": "flag"}, {"expect": {"variable": variable, "op": op, "value": value}, "within": seconds}]
    elif kind == "broadcast":
        if not message:
            raise WorkspaceError("broadcast needs message.")
        steps = [{"do": "flag"}, {"expect": {"broadcast_sent": message}, "within": seconds}]
    elif kind == "clones":
        if not sprite:
            raise WorkspaceError("clones needs sprite.")
        steps = [{"do": "flag"}, {"expect": {"clones": {"sprite": sprite, "op": ">=", "value": minimum}}, "within": seconds}]
    elif kind == "animation":
        if not sprite:
            raise WorkspaceError("animation needs sprite.")
        steps = [{"do": "flag"}, {"do": "run", "seconds": seconds}, {"expect": {"costume_changed": sprite, "value": minimum}}]
    elif kind == "audio":
        if not sound:
            raise WorkspaceError("audio needs sound (name).")
        steps = [{"do": "flag"}, {"expect": {"sound_played": sound}, "within": seconds}]
    elif kind == "say":
        if not sprite or not text:
            raise WorkspaceError("say needs sprite and text.")
        steps = [{"do": "flag"}, {"expect": {"say": {"sprite": sprite, "contains": text}}, "within": seconds}]
    else:
        raise WorkspaceError("kind must be keyboard, click, collision, variable, broadcast, clones, animation, audio or say.")
    return await run_scenario(ctx, steps, name or f"quick {kind}", save, project)
