"""animation_manager: ready-made animation patterns (cycles, blinks, jumps, entrances, dialogue, transitions, timelines).

Every action just *writes real scripts* with the block engine - nothing here is special at run time - so the results can be
read with script_manager, edited with block_manager, run with runtime_manager and tested with testing_manager.
"""

from __future__ import annotations

from typing import Any

from .. import editing
from ..ctx import Ctx
from ..engine import Graph
from ..registry import GROUP_DOCS, action
from ..render import ScriptRenderer
from ..vector import VectorDoc
from ..workspace import WorkspaceError
from ._common import graph_edit

G = "animation_manager"
GROUP_DOCS[G] = (
    "Generate common cartoon/animation scripts in one call: costume cycles (walk/run/idle), blinking, jumps, entrances/exits/"
    "paths, multi-character dialogue, scene transitions (fade/wipe) and a scene timeline on the Stage. 'on' says what starts the "
    "script: \"flag\" | \"clicked\" | {\"key\": \"space\"} | {\"broadcast\": \"name\"} | {\"while_key\": \"right arrow\"} (repeats while "
    "the key is held; for cycles). Everything is ordinary Scratch blocks you can inspect and edit afterwards. Animation timing "
    "is in seconds; Scratch runs at 30 frames/second."
)

STAGE_HALF_W, STAGE_HALF_H = 240, 180


def op(opcode: str, inputs: dict | None = None, fields: dict | None = None, nxt: list | None = None) -> dict:
    t: dict[str, Any] = {"opcode": opcode}
    if inputs:
        t["inputs"] = inputs
    if fields:
        t["fields"] = fields
    if nxt:
        t["next"] = nxt
    return t


def hat(on: Any, body: list[dict]) -> dict:
    """A script that starts with the requested trigger; `while_key` wraps the body in forever/if."""
    if on in (None, "flag"):
        return op("event_whenflagclicked", nxt=body)
    if on == "clicked":
        return op("event_whenthisspriteclicked", nxt=body)
    if on == "clone":
        return op("control_start_as_clone", nxt=body)
    if isinstance(on, dict):
        if "key" in on:
            return op("event_whenkeypressed", fields={"KEY_OPTION": on["key"]}, nxt=body)
        if "broadcast" in on:
            return op("event_whenbroadcastreceived", fields={"BROADCAST_OPTION": on["broadcast"]}, nxt=body)
        if "while_key" in on:
            cond = op("sensing_keypressed", {"KEY_OPTION": on["while_key"]})
            return op("event_whenflagclicked", nxt=[op("control_forever", {"SUBSTACK": [op("control_if", {"CONDITION": cond, "SUBSTACK": body})]})])
    raise WorkspaceError("'on' must be \"flag\", \"clicked\", \"clone\", {\"key\": k}, {\"broadcast\": name} or {\"while_key\": k}.")


def _check_costumes(g: Graph, names: list[str]) -> None:
    have = {c["name"] for c in g.target.get("costumes") or []}
    missing = [n for n in names if n not in have]
    if missing:
        raise WorkspaceError(f"{'The Stage' if g.target.get('isStage') else g.target['name']} has no costume(s) {missing}. Has: {sorted(have)}.")


def _result(g: Graph, ids: list[str], extra: dict | None = None) -> dict:
    r = ScriptRenderer(g.blocks)
    return {"scripts_added": len(ids), "script_ids": ids, "text": "\n\n".join("\n".join(r.render_stack(i)) for i in ids), **(extra or {})}


@action(G)
def cycle(ctx: Ctx, costumes: list[str], delay: float = 0.1, times: int | None = None, on: Any = "flag", move_x: float = 0,
          move_y: float = 0, face: int | None = None, rest_costume: str | None = None, sprite: str | None = None,
          project: str | None = None) -> dict:
    """Loop through costumes (a walk, run, idle or any frame-by-frame animation), optionally moving a little each frame.

    Args:
        costumes: costume names in order, e.g. ["walk1", "walk2"].
        delay: seconds each frame is shown.
        times: repeat this many times; omit to repeat forever.
        on: what starts it. With {"while_key": "right arrow"} it plays only while the key is held.
        move_x: pixels to move per frame (negative = left).
        face: point in this direction first (90 = right, -90 = left).
        rest_costume: costume to show after a finite cycle ends.
    """
    if len(costumes) < 2:
        raise WorkspaceError("A cycle needs at least two costumes.")

    def fn(g: Graph):
        _check_costumes(g, costumes + ([rest_costume] if rest_costume else []))
        body: list[dict] = []
        if face is not None:
            body.append(op("motion_pointindirection", {"DIRECTION": face}))
        for c in costumes:
            body.append(op("looks_switchcostumeto", {"COSTUME": c}))
            if move_x:
                body.append(op("motion_changexby", {"DX": move_x}))
            if move_y:
                body.append(op("motion_changeyby", {"DY": move_y}))
            body.append(op("control_wait", {"DURATION": delay}))
        keyed = isinstance(on, dict) and "while_key" in on
        if keyed or times is None:
            script = hat(on, body) if keyed else hat(on, [op("control_forever", {"SUBSTACK": body})])
        else:
            tail = [op("looks_switchcostumeto", {"COSTUME": rest_costume})] if rest_costume else []
            script = hat(on, [op("control_repeat", {"TIMES": times, "SUBSTACK": body}), *tail])
        ids = g.add([script])
        return _result(g, ids)

    return graph_edit(ctx, project, sprite, "animation cycle", fn)


@action(G)
def blink(ctx: Ctx, open_costume: str, closed_costume: str, min_wait: float = 2, max_wait: float = 5, closed_time: float = 0.15,
          sprite: str | None = None, project: str | None = None) -> dict:
    """Random blinking: wait a random time, show the closed-eyes costume briefly, go back. Runs forever from the green flag. (If you also run a walk cycle on the same sprite, give the cycle only costumes that already have open eyes, or blink via a separate eyes sprite.)"""
    def fn(g: Graph):
        _check_costumes(g, [open_costume, closed_costume])
        wait = op("operator_random", {"FROM": min_wait, "TO": max_wait})
        ids = g.add([op("event_whenflagclicked", nxt=[op("control_forever", {"SUBSTACK": [
            op("control_wait", {"DURATION": wait}),
            op("looks_switchcostumeto", {"COSTUME": closed_costume}), op("control_wait", {"DURATION": closed_time}),
            op("looks_switchcostumeto", {"COSTUME": open_costume})]})])])
        return _result(g, ids)

    return graph_edit(ctx, project, sprite, "blink animation", fn)


@action(G)
def jump(ctx: Ctx, height: float = 60, seconds: float = 0.5, on: Any = None, ground_y: float | None = None, jump_costume: str | None = None,
         land_costume: str | None = None, sound: str | None = None, guard_variable: str | None = None, sprite: str | None = None,
         project: str | None = None) -> dict:
    """A jump arc (up then down, frame by frame), with optional pose, landing pose and sound. By default triggered by the space key; a guard variable (created for you) stops double jumps.

    Args:
        height: pixels to rise.
        seconds: total time up + down.
        on: trigger (default {"key": "space"}).
        ground_y: y to return to (default: the sprite's current y).
        jump_costume: costume shown while in the air.
        land_costume: costume to return to afterwards.
        sound: name of one of the sprite's sounds to play at take-off.
    """
    if height <= 0 or seconds <= 0:
        raise WorkspaceError("height and seconds must be positive.")

    def fn(g: Graph):
        steps = max(2, round(seconds * 30 / 2))
        dy = round(height / steps, 3)
        ground = ground_y if ground_y is not None else g.target.get("y", 0)
        guard = guard_variable or f"{g.target['name']} jumping"
        _check_costumes(g, [c for c in (jump_costume, land_costume) if c])
        if sound and sound not in {s["name"] for s in g.target.get("sounds") or []}:
            raise WorkspaceError(f"{g.target['name']} has no sound '{sound}'.")
        air = [op("data_setvariableto", {"VALUE": 1}, {"VARIABLE": guard})]
        if sound:
            air.append(op("sound_play", {"SOUND_MENU": sound}))
        if jump_costume:
            air.append(op("looks_switchcostumeto", {"COSTUME": jump_costume}))
        air += [op("control_repeat", {"TIMES": steps, "SUBSTACK": [op("motion_changeyby", {"DY": dy})]}),
                op("control_repeat", {"TIMES": steps, "SUBSTACK": [op("motion_changeyby", {"DY": -dy})]}),
                op("motion_sety", {"Y": ground})]
        if land_costume:
            air.append(op("looks_switchcostumeto", {"COSTUME": land_costume}))
        air.append(op("data_setvariableto", {"VALUE": 0}, {"VARIABLE": guard}))
        cond = op("operator_equals", {"OPERAND1": {"variable": guard}, "OPERAND2": 0})
        g.variable(guard)
        ids = g.add([hat(on or {"key": "space"}, [op("control_if", {"CONDITION": cond, "SUBSTACK": air})])])
        return _result(g, ids, {"guard_variable": guard, "frames_up": steps, "pixels_per_frame": dy})

    return graph_edit(ctx, project, sprite, "jump animation", fn)


def _offscreen(side: str, x: float, y: float) -> tuple[float, float]:
    return {"left": (-STAGE_HALF_W - 120, y), "right": (STAGE_HALF_W + 120, y), "top": (x, STAGE_HALF_H + 120), "bottom": (x, -STAGE_HALF_H - 120)}[side]


@action(G)
def move(ctx: Ctx, kind: str = "path", points: list[list[float]] | None = None, seconds_each: float = 1.0, side: str = "left",
         to_x: float | None = None, to_y: float | None = None, seconds: float = 1.0, on: Any = "flag", costumes: list[str] | None = None,
         delay: float = 0.1, sprite: str | None = None, project: str | None = None) -> dict:
    """Movement choreography. kind: 'path' (glide through `points`), 'entrance' (appear from off-screen `side` and glide to to_x/to_y), 'exit' (glide off-screen `side` then hide). With `costumes` the sprite also animates (a walk cycle) while it moves.

    Args:
        kind: path | entrance | exit.
        points: [[x,y], ...] for 'path'.
        side: left | right | top | bottom, for entrance/exit.
        seconds: duration for entrance/exit.
        costumes: optional frames to cycle while moving.
    """
    def fn(g: Graph):
        x0, y0 = g.target.get("x", 0), g.target.get("y", 0)
        if costumes:
            _check_costumes(g, costumes)
        steps: list[dict] = []
        if kind == "path":
            if not points or len(points) < 1:
                raise WorkspaceError("path needs points: [[x,y], ...].")
            steps = [op("motion_glidesecstoxy", {"SECS": seconds_each, "X": px, "Y": py}) for px, py in points]
            total = seconds_each * len(points)
        elif kind == "entrance":
            if to_x is None or to_y is None:
                raise WorkspaceError("entrance needs to_x and to_y.")
            sx, sy = _offscreen(side, to_x, to_y)
            steps = [op("looks_hide"), op("motion_gotoxy", {"X": sx, "Y": sy}), op("looks_show"),
                     op("motion_glidesecstoxy", {"SECS": seconds, "X": to_x, "Y": to_y})]
            total = seconds
        elif kind == "exit":
            ex, ey = _offscreen(side, x0, y0)
            steps = [op("motion_glidesecstoxy", {"SECS": seconds, "X": ex, "Y": ey}), op("looks_hide")]
            total = seconds
        else:
            raise WorkspaceError("kind must be path, entrance or exit.")
        scripts = [hat(on, steps)]
        if costumes:  # the walk cycle runs in parallel for the duration of the move
            frames = max(1, round(total / (delay * len(costumes))))
            body = []
            for c in costumes:
                body += [op("looks_switchcostumeto", {"COSTUME": c}), op("control_wait", {"DURATION": delay})]
            scripts.append(hat(on, [op("control_repeat", {"TIMES": frames, "SUBSTACK": body}), op("looks_switchcostumeto", {"COSTUME": costumes[0]})]))
        return _result(g, g.add(scripts), {"duration_seconds": round(total, 2)})

    return graph_edit(ctx, project, sprite, f"move {kind}", fn)


@action(G)
def dialogue(ctx: Ctx, lines: list[dict[str, Any]], on: Any = "flag", channel: str = "dialogue", pause: float = 0.2,
             project: str | None = None) -> dict:
    """A conversation between sprites. Each line is {"sprite": "Robo", "text": "Hello!", "seconds": 2, "costume": "happy"(optional), "sound": "name"(optional), "return_costume": optional}. Lines play one after another across sprites using broadcasts '<channel> 1', '<channel> 2', ... ('<channel> done' at the end - hook other scripts to it).

    Args:
        lines: the lines in order.
        on: what starts the first line.
        channel: prefix for the broadcast names.
        pause: seconds between lines.
    """
    if not lines:
        raise WorkspaceError("dialogue needs at least one line.")
    session = ctx.session(project)
    out: list[dict[str, Any]] = []
    with ctx.store.edit(project, "dialogue") as h:
        for i, line in enumerate(lines):
            for k in ("sprite", "text"):
                if k not in line:
                    raise WorkspaceError(f"Line {i + 1} needs '{k}'.")
            target = ctx.target(h.project, session, line["sprite"])
            g = Graph(h.project, target)
            secs = float(line.get("seconds", max(1.5, round(len(line["text"]) * 0.07, 1))))
            body: list[dict] = []
            if line.get("costume"):
                _check_costumes(g, [line["costume"]])
                body.append(op("looks_switchcostumeto", {"COSTUME": line["costume"]}))
            if line.get("sound"):
                body.append(op("sound_play", {"SOUND_MENU": line["sound"]}))
            body.append(op("looks_sayforsecs", {"MESSAGE": line["text"], "SECS": secs}))
            if line.get("return_costume"):
                _check_costumes(g, [line["return_costume"]])
                body.append(op("looks_switchcostumeto", {"COSTUME": line["return_costume"]}))
            if pause:
                body.append(op("control_wait", {"DURATION": pause}))
            nxt = f"{channel} {i + 2}" if i + 1 < len(lines) else f"{channel} done"
            body.append(op("event_broadcast", {"BROADCAST_INPUT": nxt}))
            trigger = on if i == 0 else {"broadcast": f"{channel} {i + 1}"}
            ids = g.add([hat(trigger, body)])
            out.append({"line": i + 1, "sprite": line["sprite"], "seconds": secs, "script": ids[0]})
    total = sum(x["seconds"] + pause for x in out)
    return {"lines": out, "duration_seconds": round(total, 2), "finished_broadcast": f"{channel} done"}


@action(G)
def transition(ctx: Ctx, kind: str = "fade", on: Any = None, to_backdrop: str | None = None, seconds: float = 0.6,
               color: str = "#000000", cover_sprite: str = "Transition", project: str | None = None) -> dict:
    """A scene transition. kind 'fade' (screen fades to a colour, backdrop changes, fades back) or 'wipe' (a colour sweeps across). Creates a full-screen cover sprite (default name 'Transition') if it doesn't exist. Default trigger: broadcast 'transition'. Broadcasts '<cover> midpoint' when the screen is fully covered, so scenes can swap sprites there.

    Args:
        kind: fade | wipe.
        on: trigger (default {"broadcast": "transition"}).
        to_backdrop: backdrop to switch to while covered.
        seconds: length of each half.
        color: cover colour.
    """
    if kind not in ("fade", "wipe"):
        raise WorkspaceError("kind must be fade or wipe.")
    trigger = on or {"broadcast": "transition"}
    mid = f"{cover_sprite} midpoint"
    with ctx.store.edit(project, f"{kind} transition") as h:
        stage = next(t for t in h.project["targets"] if t.get("isStage"))
        if to_backdrop and to_backdrop not in {c["name"] for c in stage.get("costumes") or []}:
            raise WorkspaceError(f"The Stage has no backdrop '{to_backdrop}'. Has: {[c['name'] for c in stage['costumes']]}")
        existing = next((t for t in h.project["targets"] if not t.get("isStage") and t["name"] == cover_sprite), None)
        if existing is None:
            sprite = editing.new_sprite(h.project, cover_sprite, 0, 0, 100, 90, False)
            editing.add_costume(h.project, h.assets, sprite, "cover", VectorDoc.blank(480, 360, color).to_string())
            sprite["layerOrder"] = max(t.get("layerOrder", 0) for t in h.project["targets"]) + 1
        else:
            sprite = existing
        g = Graph(h.project, sprite)
        n = max(2, round(seconds * 30 / 2))
        dt = max(0.01, round(seconds / n, 3))
        swap = [op("looks_switchbackdropto", {"BACKDROP": to_backdrop})] if to_backdrop else []
        if kind == "fade":
            body = [op("looks_seteffectto", {"VALUE": 100}, {"EFFECT": "ghost"}), op("looks_show"),
                    op("control_repeat", {"TIMES": n, "SUBSTACK": [op("looks_changeeffectby", {"CHANGE": -round(100 / n, 3)}, {"EFFECT": "ghost"}), op("control_wait", {"DURATION": dt})]}),
                    *swap, op("event_broadcast", {"BROADCAST_INPUT": mid}),
                    op("control_repeat", {"TIMES": n, "SUBSTACK": [op("looks_changeeffectby", {"CHANGE": round(100 / n, 3)}, {"EFFECT": "ghost"}), op("control_wait", {"DURATION": dt})]}),
                    op("looks_hide")]
        else:
            step = round(960 / n, 3)
            body = [op("looks_seteffectto", {"VALUE": 0}, {"EFFECT": "ghost"}), op("motion_gotoxy", {"X": -480, "Y": 0}), op("looks_show"),
                    op("control_repeat", {"TIMES": n, "SUBSTACK": [op("motion_changexby", {"DX": step / 2}), op("control_wait", {"DURATION": dt})]}),
                    *swap, op("event_broadcast", {"BROADCAST_INPUT": mid}),
                    op("control_repeat", {"TIMES": n, "SUBSTACK": [op("motion_changexby", {"DX": step / 2}), op("control_wait", {"DURATION": dt})]}),
                    op("looks_hide")]
        init = [op("event_whenflagclicked", nxt=[op("looks_hide"), op("looks_seteffectto", {"VALUE": 0 if kind == "wipe" else 100}, {"EFFECT": "ghost"})])]
        ids = g.add(init + [hat(trigger, body)])
        result = _result(g, ids, {"cover_sprite": cover_sprite, "midpoint_broadcast": mid, "duration_seconds": round(2 * n * dt, 2)})
    return result


@action(G)
def timeline(ctx: Ctx, scenes: list[dict[str, Any]], on: Any = "flag", broadcast_prefix: str = "scene", stop_at_end: bool = False,
             project: str | None = None) -> dict:
    """A Stage script that runs a sequence of scenes on a timer (no drift): for each scene it switches the backdrop (optional), broadcasts '<prefix> N' and '<prefix> <name>', and waits until the scene's end time. Sprites react with `when I receive`. A final '<prefix> end' marks the end.

    Args:
        scenes: [{"name": "intro", "seconds": 5, "backdrop": "city"(optional)}, ...].
        on: what starts the timeline (default green flag).
        broadcast_prefix: prefix for broadcast names.
        stop_at_end: stop all scripts when the last scene finishes.
    """
    if not scenes:
        raise WorkspaceError("timeline needs at least one scene.")

    def fn(g: Graph):
        if not g.target.get("isStage"):
            raise WorkspaceError("The timeline lives on the Stage - pass sprite='Stage'.")
        _check_costumes(g, [s["backdrop"] for s in scenes if s.get("backdrop")])
        body = [op("sensing_resettimer")]
        t = 0.0
        names = []
        for i, sc in enumerate(scenes, start=1):
            if "seconds" not in sc or sc["seconds"] <= 0:
                raise WorkspaceError(f"Scene {i} needs a positive 'seconds'.")
            if sc.get("backdrop"):
                body.append(op("looks_switchbackdropto", {"BACKDROP": sc["backdrop"]}))
            body.append(op("event_broadcast", {"BROADCAST_INPUT": f"{broadcast_prefix} {i}"}))
            names.append(f"{broadcast_prefix} {i}")
            if sc.get("name"):
                body.append(op("event_broadcast", {"BROADCAST_INPUT": f"{broadcast_prefix} {sc['name']}"}))
                names.append(f"{broadcast_prefix} {sc['name']}")
            t += float(sc["seconds"])
            body.append(op("control_wait_until", {"CONDITION": op("operator_gt", {"OPERAND1": op("sensing_timer"), "OPERAND2": round(t, 3)})}))
        body.append(op("event_broadcast", {"BROADCAST_INPUT": f"{broadcast_prefix} end"}))
        if stop_at_end:
            body.append(op("control_stop", fields={"STOP_OPTION": "all"}))
        return _result(g, g.add([hat(on, body)]), {"total_seconds": round(t, 2), "broadcasts": names + [f"{broadcast_prefix} end"]})

    return graph_edit(ctx, project, "Stage", "scene timeline", fn)
