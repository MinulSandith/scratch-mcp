"""runtime_manager: run the project in the real Scratch VM and look at the result."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..ctx import Ctx
from ..registry import GROUP_DOCS, Reply, action
from ..runtime.manager import FRAME_MS
from ..workspace import WorkspaceError

G = "runtime_manager"
GROUP_DOCS[G] = (
    "Run the active project in the REAL Scratch VM and renderer (headless Chromium) and observe it. Time is simulated "
    "deterministically at 30 frames/second: the project only advances when you call run/step (so it is 'paused' between "
    "calls, and 'run' seconds are simulated seconds, not real ones). Typical loop: start -> green_flag -> run(seconds) -> "
    "screenshot / state -> edit the project -> start again (reload picks up your edits; unsaved edits included). "
    "Needs a one-time 'setup' (downloads scratch-vm/scratch-render via npm) and a Chromium browser. Not supported: real "
    "audio output (sound plays are logged, see events), webcam, microphone, hardware extensions, cloud variables."
)


def frames_for(seconds: float) -> int:
    if seconds < 0 or seconds > 600:
        raise WorkspaceError("seconds must be between 0 and 600.")
    return max(0, int(round(seconds * 1000 / FRAME_MS)))


def project_hash(session) -> str:
    return hashlib.sha1(json.dumps(session.project, sort_keys=True).encode()).hexdigest()[:12]


async def ensure(ctx: Ctx, project: str | None, *, auto_start: bool = True):
    """Session + running runtime page (starting it if needed)."""
    session = ctx.session(project)
    rm = ctx.runtime
    if session.name not in rm.sessions or rm.sessions[session.name].dead:
        if not auto_start:
            raise WorkspaceError("The project is not running. Call runtime_manager start first.")
        rs = await rm.start(session.name, session.project, session.assets)
        rs.booted_hash = project_hash(session)
    return session, rm


@action(G)
async def setup(ctx: Ctx, force: bool = False) -> dict:
    """Install the Scratch runtime (scratch-vm + scratch-render from npm) into the cache folder. One time; needs node/npm and internet."""
    return await ctx.runtime.setup(force)


@action(G)
async def status(ctx: Ctx) -> dict:
    """What is installed (runtime files, playwright, Chromium, ffmpeg, node) and which projects are running."""
    out = ctx.runtime.status()
    out["running"] = {k: {"dead": v.dead} for k, v in ctx.runtime.sessions.items()}
    return out


@action(G)
async def start(ctx: Ctx, project: str | None = None, green_flag: bool = False, run_seconds: float = 0) -> dict:
    """Load the project's CURRENT in-memory state into a fresh VM (resets the simulation). Optionally press the green flag and run.

    Args:
        green_flag: press the green flag right after loading.
        run_seconds: simulated seconds to run after the flag.
    """
    session = ctx.session(project)
    rm = ctx.runtime
    rs = await rm.start(session.name, session.project, session.assets)
    rs.booted_hash = project_hash(session)
    out: dict[str, Any] = {"project": session.name, "targets": getattr(rs, "targets", [])}
    if rs.notes:
        out["notes"] = rs.notes
    if green_flag:
        await rm.call(session.name, "flag")
        if run_seconds:
            await rm.run_frames(session.name, frames_for(run_seconds))
        out["state"] = await rm.call(session.name, "state")
    return out


@action(G)
async def stop(ctx: Ctx, project: str | None = None) -> dict:
    """Close the runtime page for the project (frees memory)."""
    session = ctx.session(project)
    return {"stopped": await ctx.runtime.stop(session.name)}


@action(G)
async def green_flag(ctx: Ctx, project: str | None = None, run_seconds: float = 0) -> dict:
    """Press the green flag (starts all 'when flag clicked' scripts). Optionally run some simulated seconds afterwards."""
    session, rm = await ensure(ctx, project)
    await rm.call(session.name, "flag")
    if run_seconds:
        await rm.run_frames(session.name, frames_for(run_seconds))
    return await rm.call(session.name, "state")


@action(G)
async def stop_all(ctx: Ctx, project: str | None = None) -> dict:
    """Press the red stop sign: stops all scripts and deletes clones."""
    session, rm = await ensure(ctx, project, auto_start=False)
    await rm.call(session.name, "stopAll")
    return await rm.call(session.name, "state")


@action(G)
async def restart(ctx: Ctx, project: str | None = None, run_seconds: float = 0) -> dict:
    """Reload the project from its current state, press the green flag and optionally run."""
    return await start(ctx, project, True, run_seconds)


@action(G)
async def run(ctx: Ctx, seconds: float, project: str | None = None, until: dict | None = None) -> dict:
    """Advance the simulation by `seconds` (simulated; 30 fps). With `until`, stop early as soon as the condition holds.

    Args:
        seconds: simulated seconds to advance (max 600).
        until: optional condition. Examples: {"type":"variable","name":"score","op":">=","value":3}; {"type":"sprite","sprite":"Robot","property":"x","op":">","value":100}; {"type":"touching","a":"Robot","b":"Alien"}; {"type":"count","event":"sound_play","arg":"pop"}; {"type":"clones","sprite":"Bullet","op":">=","value":2}. Properties: x y size direction visible costume say. Ops: == != > >= < <= contains.
    """
    session, rm = await ensure(ctx, project, auto_start=False)
    r = await rm.run_frames(session.name, frames_for(seconds), until)
    st = await rm.call(session.name, "state")
    out = {"ran_seconds": round(r["frames"] * FRAME_MS / 1000, 3), "project_time": st["time"]}
    if until is not None:
        out["condition_met"] = r["met"]
        out["condition_value"] = r["actual"]
    out["state"] = st
    return out


@action(G)
async def step(ctx: Ctx, frames: int = 1, project: str | None = None) -> dict:
    """Advance a small number of frames (1 frame = 1/30 s) - for stepping through execution frame by frame."""
    if not 1 <= frames <= 3000:
        raise WorkspaceError("frames must be 1-3000.")
    session, rm = await ensure(ctx, project, auto_start=False)
    await rm.run_frames(session.name, frames)
    return await rm.call(session.name, "state")


@action(G)
async def state(ctx: Ctx, project: str | None = None, include_clones: bool = False) -> dict:
    """Current runtime state: project time, every sprite's position/size/direction/costume/visibility/speech bubble, variables and lists, pending question, clone count, running scripts."""
    session, rm = await ensure(ctx, project)
    st = await rm.call(session.name, "state", {"clones": include_clones})
    st["project_changed_since_start"] = rm.sessions[session.name].booted_hash != project_hash(session)
    return st


@action(G)
async def sprite_state(ctx: Ctx, sprite: str | None = None, project: str | None = None) -> dict:
    """One sprite's current runtime state."""
    session, rm = await ensure(ctx, project)
    name = ctx.sprite_name(session, sprite)
    st = await rm.call(session.name, "state")
    for t in st["targets"]:
        if t["name"].lower() == name.lower():
            return t
    raise WorkspaceError(f"No sprite '{name}' in the running project.")


@action(G)
async def variables(ctx: Ctx, project: str | None = None) -> dict:
    """Runtime values of all variables and lists (lists show up to 200 items)."""
    session, rm = await ensure(ctx, project)
    return {"variables": await rm.call(session.name, "variables")}


@action(G)
async def threads(ctx: Ctx, project: str | None = None) -> dict:
    """Scripts that are running right now (sprite, top block, opcode)."""
    session, rm = await ensure(ctx, project)
    return {"threads": await rm.call(session.name, "threads")}


@action(G)
async def events(ctx: Ctx, project: str | None = None, type: str | None = None, last: int = 50, clear: bool = False) -> dict:
    """The run log: green flag, key/mouse input, sounds started (sound_play), broadcasts, say/think, clone creation, questions, costume switches ... with project time.

    Args:
        type: filter by event type, e.g. sound_play, event_broadcast, say, create_clone_of, key_down.
        last: how many of the most recent matching events to return.
        clear: empty the log afterwards.
    """
    session, rm = await ensure(ctx, project)
    r = await rm.call(session.name, "eventsSince", 0, type, last)
    if clear:
        await rm.call(session.name, "clearEvents")
    return r


@action(G)
async def screenshot(ctx: Ctx, project: str | None = None, scale: int = 1) -> Reply:
    """Capture the stage as a PNG image (what a player would see: sprites, backdrop, speech bubbles, pen drawings).

    Args:
        scale: 1 (480x360) or 2 (960x720).
    """
    if scale not in (1, 2):
        raise WorkspaceError("scale must be 1 or 2.")
    session, rm = await ensure(ctx, project)
    png = await rm.screenshot(session.name, scale)
    st = await rm.call(session.name, "state")
    return Reply(text={"project_time": st["time"], "size": [480 * scale, 360 * scale],
                       "sprites": {t["name"]: [t.get("x"), t.get("y")] for t in st["targets"] if not t["isStage"]}},
                 images=[(png, "image/png")])


@action(G)
async def create_clone(ctx: Ctx, sprite: str, project: str | None = None) -> dict:
    """Create a clone of a sprite at run time (as the 'create clone of' block would)."""
    session, rm = await ensure(ctx, project)
    return await rm.call(session.name, "createClone", sprite)


@action(G)
async def list_clones(ctx: Ctx, project: str | None = None) -> dict:
    """List all current clones with their state."""
    session, rm = await ensure(ctx, project)
    return {"clones": await rm.call(session.name, "clones")}


@action(G)
async def delete_clones(ctx: Ctx, sprite: str | None = None, project: str | None = None) -> dict:
    """Delete clones (of one sprite, or all)."""
    session, rm = await ensure(ctx, project)
    return {"deleted": await rm.call(session.name, "deleteClones", sprite)}


@action(G)
async def set_variable(ctx: Ctx, name: str, value: Any, sprite: str | None = None, project: str | None = None) -> dict:
    """Change a variable's value in the running simulation (for tests; does not edit the project)."""
    session, rm = await ensure(ctx, project)
    await rm.call(session.name, "setVariable", name, value, sprite)
    return {"set": name, "value": value}


@action(G)
async def set_sprite(ctx: Ctx, sprite: str, x: float | None = None, y: float | None = None, direction: float | None = None,
                     size: float | None = None, visible: bool | None = None, project: str | None = None) -> dict:
    """Move/resize a sprite in the running simulation (for tests; does not edit the project)."""
    props = {k: v for k, v in dict(x=x, y=y, direction=direction, size=size, visible=visible).items() if v is not None}
    session, rm = await ensure(ctx, project)
    return await rm.call(session.name, "setSprite", sprite, props)


@action(G)
async def console(ctx: Ctx, project: str | None = None, errors_only: bool = True, last: int = 30) -> dict:
    """Browser/VM console output for the running project (errors by default)."""
    session = ctx.session(project)
    rs = ctx.runtime.sessions.get(session.name)
    if rs is None:
        raise WorkspaceError("The project is not running.")
    items = [c for c in rs.console if not errors_only or c["type"] in ("error", "pageerror")]
    return {"messages": items[-last:], "total": len(items), "runtime_stopped": rs.dead}


_snapshots: dict[str, dict[str, bytes]] = {}


@action(G)
async def snapshot(ctx: Ctx, name: str, project: str | None = None) -> dict:
    """Remember the current stage picture under a name, to compare with later (before/after an edit or a run)."""
    session, rm = await ensure(ctx, project)
    _snapshots.setdefault(session.name, {})[name] = await rm.screenshot(session.name, 1)
    return {"saved": name, "snapshots": list(_snapshots[session.name])}


@action(G)
async def compare(ctx: Ctx, against: str, project: str | None = None, threshold: int = 24) -> Reply:
    """Compare the current stage with a saved snapshot. Returns how much changed (percent of pixels, bounding box) and a diff image with the changed pixels in red.

    Args:
        against: snapshot name from 'snapshot'.
        threshold: colour difference (0-765) above which a pixel counts as changed.
    """
    session, rm = await ensure(ctx, project)
    before = _snapshots.get(session.name, {}).get(against)
    if before is None:
        raise WorkspaceError(f"No snapshot '{against}'. Saved: {list(_snapshots.get(session.name, {})) or 'none'}.")
    now = await rm.screenshot(session.name, 1)
    stats, diff = await ctx.browser.diff_images(before, now, threshold)
    stats["identical"] = stats["changed"] == 0
    return Reply(text=stats, images=[(diff, "image/png")])
