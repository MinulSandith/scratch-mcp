"""input_manager: simulate a person using the project - keys, mouse, clicks, drags, answering prompts."""

from __future__ import annotations

from typing import Any

from ..ctx import Ctx
from ..registry import GROUP_DOCS, action
from ..workspace import WorkspaceError
from .runtime import ensure, frames_for

G = "input_manager"
GROUP_DOCS[G] = (
    "Simulate user input in the running project (starts it automatically if needed). Keys use Scratch's names: "
    "a-z, 0-9, 'space', 'up arrow', 'down arrow', 'left arrow', 'right arrow', 'enter'. Mouse positions are Scratch "
    "stage coordinates (x -240..240, y -180..180, 0,0 = centre). Every action accepts 'then_run' - simulated seconds "
    "to keep running afterwards so the effect can play out - and returns a short state summary. Time only advances "
    "when you run it (see runtime_manager)."
)

VALID_NAMED = {"space", "up arrow", "down arrow", "left arrow", "right arrow", "enter"}
held_keys: dict[str, set[str]] = {}


def check_key(key: str) -> str:
    k = key.strip().lower()
    if k in VALID_NAMED or (len(k) == 1 and (k.isalnum())):
        return k
    raise WorkspaceError(f"Unknown key '{key}'. Use a-z, 0-9, space, up arrow, down arrow, left arrow, right arrow or enter.")


async def _finish(ctx: Ctx, session, rm, then_run: float) -> dict[str, Any]:
    if then_run:
        await rm.run_frames(session.name, frames_for(then_run))
    st = await rm.call(session.name, "state")
    return {"project_time": st["time"], "sprites": {t["name"]: {k: t[k] for k in ("x", "y", "direction", "costume", "visible") if k in t}
                                                   for t in st["targets"] if not t["isStage"]},
            "variables": {v["name"]: v["value"] for v in st["variables"] if v["type"] == "variable"}, "question": st["question"]}


@action(G)
async def key_press(ctx: Ctx, key: str, hold_seconds: float = 0.1, then_run: float = 0.2, project: str | None = None) -> dict:
    """Press and release a key (held for `hold_seconds` of simulated time)."""
    k = check_key(key)
    session, rm = await ensure(ctx, project)
    await rm.call(session.name, "key", k, True)
    await rm.run_frames(session.name, max(1, frames_for(hold_seconds)))
    await rm.call(session.name, "key", k, False)
    return await _finish(ctx, session, rm, then_run)


@action(G)
async def key_down(ctx: Ctx, key: str, then_run: float = 0, project: str | None = None) -> dict:
    """Press a key and keep holding it (until key_up / release_all)."""
    k = check_key(key)
    session, rm = await ensure(ctx, project)
    await rm.call(session.name, "key", k, True)
    held_keys.setdefault(session.name, set()).add(k)
    return await _finish(ctx, session, rm, then_run)


@action(G)
async def key_up(ctx: Ctx, key: str, then_run: float = 0, project: str | None = None) -> dict:
    """Release a held key."""
    k = check_key(key)
    session, rm = await ensure(ctx, project)
    await rm.call(session.name, "key", k, False)
    held_keys.get(session.name, set()).discard(k)
    return await _finish(ctx, session, rm, then_run)


@action(G)
async def release_all(ctx: Ctx, project: str | None = None) -> dict:
    """Release every key and mouse button that is being held."""
    session, rm = await ensure(ctx, project)
    for k in list(held_keys.get(session.name, ())):
        await rm.call(session.name, "key", k, False)
    held_keys[session.name] = set()
    await rm.call(session.name, "mouseUp")
    return {"released": True}


@action(G)
async def type_keys(ctx: Ctx, keys: list[str], seconds_each: float = 0.15, then_run: float = 0.2, project: str | None = None) -> dict:
    """Press several keys one after another (e.g. ['right arrow','right arrow','space'])."""
    session, rm = await ensure(ctx, project)
    for key in keys:
        k = check_key(key)
        await rm.call(session.name, "key", k, True)
        await rm.run_frames(session.name, max(1, frames_for(seconds_each)))
        await rm.call(session.name, "key", k, False)
        await rm.run_frames(session.name, 1)
    return await _finish(ctx, session, rm, then_run)


def check_xy(x: float, y: float) -> None:
    if not (-240 <= x <= 240 and -180 <= y <= 180):
        raise WorkspaceError("Mouse position must be within the stage: x -240..240, y -180..180.")


@action(G)
async def mouse_move(ctx: Ctx, x: float, y: float, then_run: float = 0.1, project: str | None = None) -> dict:
    """Move the mouse pointer to stage coordinates (x, y)."""
    check_xy(x, y)
    session, rm = await ensure(ctx, project)
    await rm.call(session.name, "mouse", x, y, None)
    return await _finish(ctx, session, rm, then_run)


@action(G)
async def mouse_down(ctx: Ctx, x: float | None = None, y: float | None = None, then_run: float = 0, project: str | None = None) -> dict:
    """Press and hold the mouse button (at x,y if given). Clicking a sprite this way triggers 'when this sprite clicked' and starts dragging a draggable sprite."""
    session, rm = await ensure(ctx, project)
    if x is None or y is None:
        x, y = 0, 0
    check_xy(x, y)
    await rm.call(session.name, "mouse", x, y, True)
    return await _finish(ctx, session, rm, then_run)


@action(G)
async def mouse_up(ctx: Ctx, then_run: float = 0.1, project: str | None = None) -> dict:
    """Release the mouse button."""
    session, rm = await ensure(ctx, project)
    await rm.call(session.name, "mouseUp")
    return await _finish(ctx, session, rm, then_run)


@action(G)
async def click(ctx: Ctx, x: float, y: float, hold_seconds: float = 0.1, then_run: float = 0.2, project: str | None = None) -> dict:
    """Click at stage coordinates: move there, press, hold, release."""
    check_xy(x, y)
    session, rm = await ensure(ctx, project)
    await rm.call(session.name, "mouse", x, y, None)
    await rm.run_frames(session.name, 1)
    await rm.call(session.name, "mouse", x, y, True)
    await rm.run_frames(session.name, max(1, frames_for(hold_seconds)))
    await rm.call(session.name, "mouse", x, y, False)
    return await _finish(ctx, session, rm, then_run)


@action(G)
async def click_sprite(ctx: Ctx, sprite: str, hold_seconds: float = 0.1, then_run: float = 0.2, project: str | None = None) -> dict:
    """Click on a sprite (at its current position) - triggers its 'when this sprite clicked' scripts. Fails if the sprite is hidden or off stage."""
    session, rm = await ensure(ctx, project)
    st = await rm.call(session.name, "state")
    t = next((t for t in st["targets"] if t["name"].lower() == sprite.lower() and not t["isStage"]), None)
    if t is None:
        raise WorkspaceError(f"No sprite '{sprite}' in the running project.")
    if not t["visible"]:
        raise WorkspaceError(f"'{t['name']}' is hidden, so it can't be clicked.")
    x, y = max(-240, min(240, t["x"])), max(-180, min(180, t["y"]))
    await rm.call(session.name, "mouse", x, y, None)
    await rm.run_frames(session.name, 1)
    await rm.call(session.name, "mouse", x, y, True)
    await rm.run_frames(session.name, max(1, frames_for(hold_seconds)))
    await rm.call(session.name, "mouse", x, y, False)
    out = await _finish(ctx, session, rm, then_run)
    out["clicked"] = [x, y]
    return out


@action(G)
async def drag(ctx: Ctx, from_x: float, from_y: float, to_x: float, to_y: float, seconds: float = 0.5, then_run: float = 0.2,
               project: str | None = None) -> dict:
    """Press at one point, move to another over `seconds`, release (drags draggable sprites, moves sliders...)."""
    check_xy(from_x, from_y)
    check_xy(to_x, to_y)
    session, rm = await ensure(ctx, project)
    n = max(2, frames_for(seconds))
    await rm.call(session.name, "mouse", from_x, from_y, None)
    await rm.run_frames(session.name, 1)
    await rm.call(session.name, "mouse", from_x, from_y, True)
    for i in range(1, n + 1):
        f = i / n
        await rm.call(session.name, "mouse", from_x + (to_x - from_x) * f, from_y + (to_y - from_y) * f, True)
        await rm.run_frames(session.name, 1)
    await rm.call(session.name, "mouse", to_x, to_y, False)
    return await _finish(ctx, session, rm, then_run)


@action(G)
async def answer(ctx: Ctx, text: str, then_run: float = 0.2, project: str | None = None) -> dict:
    """Type a response into an 'ask ... and wait' prompt (the project must be waiting for one: see state.question)."""
    session, rm = await ensure(ctx, project)
    st = await rm.call(session.name, "state")
    if st["question"] is None:
        raise WorkspaceError("The project is not asking a question right now. Run it until state.question is set "
                             "(runtime_manager run with until {\"type\":\"question\",\"op\":\"contains\",\"value\":\"\"}).")
    await rm.call(session.name, "answer", text)
    return await _finish(ctx, session, rm, then_run)

