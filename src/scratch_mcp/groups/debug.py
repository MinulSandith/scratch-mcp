"""debug_manager: find problems - static analysis, run-time errors, scripts that never start, hangs."""

from __future__ import annotations

from typing import Any

from .. import analysis
from ..ctx import Ctx
from ..registry import GROUP_DOCS, action
from ..workspace import WorkspaceError
from .runtime import frames_for

G = "debug_manager"
GROUP_DOCS[G] = (
    "Find and explain problems. 'check' is static (no running): structure, block rules, broken references (missing "
    "costumes/sounds/sprites/custom blocks), broadcasts nobody sends or receives, unused/write-only variables, empty loops, "
    "orphan blocks, hang risks. 'dead_scripts' and 'hang_check' RUN the project. 'errors' shows VM/browser errors. "
    "'diagnose' does all of it and returns a prioritised list with hints. After fixing, run it again to verify the fix."
)

NEEDS_TRIGGER = {
    "event_whenkeypressed": "a key press", "event_whenthisspriteclicked": "a click on the sprite", "event_whenstageclicked": "a click on the stage",
    "event_whenbroadcastreceived": "a broadcast", "event_whenbackdropswitchesto": "a backdrop switch", "event_whengreaterthan": "loudness/timer above a value",
    "event_whentouchingobject": "touching something", "control_start_as_clone": "a clone being created",
}


@action(G)
def check(ctx: Ctx, project: str | None = None, include_info: bool = True) -> dict:
    """Static analysis of the whole project (nothing is run). Returns issues with severity error/warning/info, the sprite, block id and a hint.

    Args:
        include_info: also list low-priority notes (unused variables, orphan blocks...).
    """
    s = ctx.session(project)
    issues = analysis.analyze(s.project, set(s.assets))
    if not include_info:
        issues = [i for i in issues if i["severity"] != "info"]
    return analysis.summarize(issues)


@action(G)
async def errors(ctx: Ctx, project: str | None = None, clear: bool = False) -> dict:
    """Errors the Scratch VM or browser reported while the project ran (empty list = none)."""
    s = ctx.session(project)
    errs = ctx.runtime.errors(s.name)
    rs = ctx.runtime.sessions.get(s.name)
    if clear and rs:
        rs.console = [c for c in rs.console if c["type"] not in ("error", "pageerror")]
    return {"running": rs is not None, "errors": errs, "runtime_stopped": rs.dead if rs else None}


async def _dead(ctx: Ctx, project: str | None, seconds: float, press: list[str] | None, click_sprites: list[str] | None) -> dict[str, Any]:
    from .inputs import key_press

    session = ctx.session(project)
    await rm_start(ctx, session)
    rm = ctx.runtime
    await rm.call(session.name, "flag")
    await rm.run_frames(session.name, frames_for(seconds))
    for k in press or []:
        await key_press(ctx, k, 0.1, 0.3, project)
    if click_sprites:
        from .inputs import click_sprite

        for sp in click_sprites:
            await click_sprite(ctx, sp, 0.1, 0.3, project)
    hats = await rm.call(session.name, "hatScripts")
    started = set(await rm.call(session.name, "scriptsStarted"))
    never = [h for h in hats if h["id"] not in started]
    flag = [h for h in never if h["opcode"] == "event_whenflagclicked"]
    other = [{**h, "needs": NEEDS_TRIGGER.get(h["opcode"], "a trigger that did not occur")} for h in never if h["opcode"] != "event_whenflagclicked"]
    return {"scripts_with_hats": len(hats), "started": len(hats) - len(never), "flag_scripts_that_never_started": flag,
            "event_scripts_not_triggered_in_this_run": other}


async def rm_start(ctx: Ctx, session):
    rs = await ctx.runtime.start(session.name, session.project, session.assets)
    return rs


@action(G)
async def dead_scripts(ctx: Ctx, seconds: float = 5, press_keys: list[str] | None = None, click_sprites: list[str] | None = None,
                       project: str | None = None) -> dict:
    """Reload the project, press the green flag, run, optionally press keys / click sprites, then list scripts whose hat never fired. 'when flag clicked' scripts that never start are bugs; event scripts only fire when their trigger happened (use press_keys / click_sprites to trigger them).

    Args:
        seconds: simulated seconds to run after the flag.
        press_keys: keys to press afterwards, e.g. ['space', 'a'].
        click_sprites: sprites to click afterwards.
    """
    return await _dead(ctx, project, seconds, press_keys, click_sprites)


@action(G)
async def hang_check(ctx: Ctx, seconds: float = 10, project: str | None = None) -> dict:
    """Run the project for `seconds` and report whether it froze (a script that never yields), with static hang risks."""
    session = ctx.session(project)
    static = [i for i in analysis.analyze(session.project, set(session.assets)) if i.get("code") in ("warp_loop_risk", "warp_recursion")]
    await rm_start(ctx, session)
    rm = ctx.runtime
    await rm.call(session.name, "flag")
    try:
        await rm.run_frames(session.name, frames_for(seconds))
    except WorkspaceError as exc:
        if "Infinite loop" in str(exc):
            return {"hung": True, "detail": str(exc), "static_risks": static}
        raise
    st = await rm.call(session.name, "state")
    return {"hung": False, "ran_seconds": seconds, "project_time": st["time"], "running_scripts": st["running_threads"], "static_risks": static}


@action(G)
async def diagnose(ctx: Ctx, seconds: float = 5, project: str | None = None) -> dict:
    """Everything at once: static check, then a short run (flag) looking for run-time errors, scripts that never start and hangs. Returns problems sorted by severity with hints."""
    session = ctx.session(project)
    static = analysis.analyze(session.project, set(session.assets))
    problems = [i for i in static if i["severity"] != "info"]
    run_info: dict[str, Any] = {}
    try:
        dead = await _dead(ctx, project, seconds, None, None)
        run_info["flag_scripts_that_never_started"] = dead["flag_scripts_that_never_started"]
        for h in dead["flag_scripts_that_never_started"]:
            problems.append({"severity": "error", "sprite": h["sprite"], "block": h["id"], "code": "script_never_started",
                             "message": "a 'when flag clicked' script never started", "hint": "Check the project actually loads this sprite/script."})
        errs = ctx.runtime.errors(session.name)
        for e in errs:
            problems.append({"severity": "error", "sprite": None, "code": "runtime_error", "message": e["text"][:300]})
        run_info["runtime_errors"] = len(errs)
        run_info["ran_seconds"] = seconds
    except WorkspaceError as exc:
        text = str(exc)
        problems.append({"severity": "error", "sprite": None, "code": "hang" if "Infinite loop" in text else "run_failed",
                         "message": text, "hint": "Fix this first - the project can't be tested while it freezes."})
        run_info["failed"] = text
    order = {"error": 0, "warning": 1, "info": 2}
    problems.sort(key=lambda p: order[p["severity"]])
    counts = {k: sum(1 for p in problems if p["severity"] == k) for k in order}
    return {"ok": counts["error"] == 0, "counts": counts, "problems": problems, "run": run_info,
            "info_notes_hidden": sum(1 for i in static if i["severity"] == "info")}
