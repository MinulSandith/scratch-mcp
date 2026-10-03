"""inspection_manager: understand a project before changing it - whole-project and targeted, structured output."""

from __future__ import annotations

import json
from typing import Any

from ..ctx import Ctx
from ..engine import Graph
from ..registry import GROUP_DOCS, action
from ..render import ScriptRenderer, top_level_ids
from ..workspace import WorkspaceError

G = "inspection_manager"
GROUP_DOCS[G] = (
    "Read-only views of a project for planning edits. 'overview' = the whole structure in one call; 'component' = one "
    "part in detail (sprite, costumes, sounds, scripts, variables, lists, broadcasts, monitors, extensions, stage, meta); "
    "'find_blocks' searches every script; 'block_graph' shows how blocks connect (parent/next/inputs); 'references' says "
    "what uses a variable/list/broadcast/costume/sound/sprite/custom block; 'json' returns raw project.json (optionally one "
    "part). Live run-time state: runtime_manager state / screenshot."
)


def _target_summary(t: dict[str, Any]) -> dict[str, Any]:
    g_blocks = t.get("blocks") or {}
    tops = [i for i, b in g_blocks.items() if isinstance(b, dict) and b.get("topLevel")]
    hats: dict[str, int] = {}
    for i in tops:
        op = g_blocks[i].get("opcode", "?")
        hats[op] = hats.get(op, 0) + 1
    info: dict[str, Any] = {
        "name": "Stage" if t.get("isStage") else t["name"], "is_stage": bool(t.get("isStage")),
        "costumes": [c["name"] for c in t.get("costumes") or []], "current_costume": t.get("currentCostume"),
        "sounds": [s["name"] for s in t.get("sounds") or []], "blocks": len(g_blocks), "scripts": len(tops),
        "script_starts": hats, "comments": len(t.get("comments") or {}),
        "local_variables": [v[0] for v in (t.get("variables") or {}).values()] if not t.get("isStage") else [],
        "local_lists": [v[0] for v in (t.get("lists") or {}).values()] if not t.get("isStage") else []}
    if not t.get("isStage"):
        info.update(x=t.get("x"), y=t.get("y"), size=t.get("size"), direction=t.get("direction"), visible=t.get("visible"),
                    draggable=t.get("draggable"), rotation_style=t.get("rotationStyle"), layer=t.get("layerOrder"))
    else:
        info.update(volume=t.get("volume"), tempo=t.get("tempo"), video_state=t.get("videoState"))
    return info


@action(G)
def overview(ctx: Ctx, project: str | None = None) -> dict:
    """The complete project structure: metadata, extensions, stage, every sprite (properties, costumes, sounds, script counts and trigger types), global variables/lists, broadcasts, monitors, asset totals."""
    s = ctx.session(project)
    p = s.project
    stage = next(t for t in p["targets"] if t.get("isStage"))
    return {"project": s.name, "state": s.info(), "meta": p.get("meta"), "extensions": p.get("extensions") or [],
            "stage": _target_summary(stage), "sprites": [_target_summary(t) for t in sorted(
                (t for t in p["targets"] if not t.get("isStage")), key=lambda t: t.get("layerOrder", 0))],
            "global_variables": [{"name": v[0], "value": v[1]} for v in (stage.get("variables") or {}).values()],
            "global_lists": [{"name": v[0], "items": len(v[1])} for v in (stage.get("lists") or {}).values()],
            "broadcasts": list((stage.get("broadcasts") or {}).values()),
            "monitors": [{"id": m.get("id"), "opcode": m.get("opcode"), "visible": m.get("visible"), "mode": m.get("mode")} for m in p.get("monitors") or []],
            "assets": {"files": len(s.assets), "bytes": sum(len(b) for b in s.assets.values())},
            "total_blocks": sum(len(t.get("blocks") or {}) for t in p["targets"])}


@action(G)
def component(ctx: Ctx, kind: str, sprite: str | None = None, project: str | None = None) -> dict:
    """One part in detail.

    Args:
        kind: sprite | costumes | sounds | scripts | variables | lists | broadcasts | monitors | extensions | stage | meta | comments.
        sprite: which sprite (default: selected); for 'stage' not needed.
    """
    s = ctx.session(project)
    p = s.project
    stage = next(t for t in p["targets"] if t.get("isStage"))
    if kind == "meta":
        return {"meta": p.get("meta")}
    if kind == "extensions":
        return {"extensions": p.get("extensions") or []}
    if kind == "stage":
        return _target_summary(stage)
    if kind == "broadcasts":
        return {"broadcasts": list((stage.get("broadcasts") or {}).values())}
    if kind == "monitors":
        return {"monitors": p.get("monitors") or []}
    if kind in ("variables", "lists"):
        key = kind
        out = []
        for t in p["targets"]:
            for vid, v in (t.get(key) or {}).items():
                out.append({"name": v[0], "id": vid, "scope": "global" if t.get("isStage") else t["name"],
                            "value" if key == "variables" else "items": v[1]})
        return {kind: out}
    t = ctx.target(p, s, sprite)
    if kind == "sprite":
        return {**_target_summary(t), "raw_keys": sorted(t.keys())}
    if kind == "costumes":
        return {"costumes": t.get("costumes") or [], "current": t.get("currentCostume")}
    if kind == "sounds":
        return {"sounds": t.get("sounds") or []}
    if kind == "comments":
        return {"comments": [{"id": k, **v} for k, v in (t.get("comments") or {}).items()]}
    if kind == "scripts":
        r = ScriptRenderer(t.get("blocks") or {})
        return {"sprite": _target_summary(t)["name"], "scripts": [{"id": i, "text": "\n".join(r.render_stack(i))} for i in top_level_ids(t)]}
    raise WorkspaceError("kind must be sprite, costumes, sounds, scripts, variables, lists, broadcasts, monitors, extensions, stage, meta or comments.")


@action(G)
def find_blocks(ctx: Ctx, opcode: str | None = None, text: str | None = None, field_value: str | None = None,
                sprite: str | None = None, project: str | None = None, limit: int = 50) -> dict:
    """Search all blocks (or one sprite's).

    Args:
        opcode: exact opcode or prefix ending in '*', e.g. 'motion_*'.
        text: substring of the block's readable text (e.g. 'score').
        field_value: a dropdown/variable field value, e.g. 'game over'.
    """
    s = ctx.session(project)
    out = []
    targets = [ctx.target(s.project, s, sprite)] if sprite else s.project["targets"]
    for t in targets:
        r = ScriptRenderer(t.get("blocks") or {})
        for bid, b in (t.get("blocks") or {}).items():
            if not isinstance(b, dict) or b.get("shadow"):
                continue
            if opcode:
                if opcode.endswith("*"):
                    if not b["opcode"].startswith(opcode[:-1]):
                        continue
                elif b["opcode"] != opcode:
                    continue
            txt = r.render_inline(b)
            if text and text.lower() not in txt.lower():
                continue
            if field_value and not any(f and f[0] == field_value for f in (b.get("fields") or {}).values()):
                continue
            # find the script this block lives in
            top, seen = bid, set()
            while t["blocks"].get(top, {}).get("parent") and top not in seen:
                seen.add(top)
                top = t["blocks"][top]["parent"]
            out.append({"sprite": "Stage" if t.get("isStage") else t["name"], "id": bid, "opcode": b["opcode"], "text": txt, "script": top})
            if len(out) >= limit:
                return {"matches": out, "truncated": True}
    return {"matches": out, "truncated": False}


@action(G)
def block_graph(ctx: Ctx, script: str | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Connections between blocks: for each block its opcode, parent, next, input children (and shadows) and fields. Give a script id for one script, else all blocks of the sprite (large!)."""
    s = ctx.session(project)
    import copy

    data = copy.deepcopy(s.project)
    t = ctx.target(data, s, sprite)
    g = Graph(data, t)
    ids = g.subtree_ids(script, include_next=True) if script else list(g.blocks)
    nodes = {}
    for i in ids:
        b = g.blocks.get(i)
        if not isinstance(b, dict):
            continue
        children = {n: [v for v in inp[1:] if isinstance(v, str)] for n, inp in (b.get("inputs") or {}).items() if isinstance(inp, list)}
        nodes[i] = {"opcode": b["opcode"], "parent": b.get("parent"), "next": b.get("next"), "shadow": bool(b.get("shadow")),
                    "inputs": {n: c for n, c in children.items() if c}, "fields": {n: f[0] for n, f in (b.get("fields") or {}).items()}}
    return {"sprite": "Stage" if t.get("isStage") else t["name"], "blocks": len(nodes), "nodes": nodes}


@action(G)
def references(ctx: Ctx, kind: str, name: str, project: str | None = None) -> dict:
    """Where something is used.

    Args:
        kind: variable | list | broadcast | costume | sound | sprite | procedure.
        name: its name (for procedure: the label, e.g. 'jump %s').
    """
    s = ctx.session(project)
    uses = []
    for t in s.project["targets"]:
        who = "Stage" if t.get("isStage") else t["name"]
        r = ScriptRenderer(t.get("blocks") or {})
        for bid, b in (t.get("blocks") or {}).items():
            if not isinstance(b, dict):
                continue
            hit = False
            fields = b.get("fields") or {}
            if kind == "variable":
                hit = (fields.get("VARIABLE") or [None])[0] == name and b["opcode"] != "data_listcontents"
                hit = hit or any(isinstance(v, list) and len(v) > 2 and v[0] == 12 and v[1] == name
                                 for inp in (b.get("inputs") or {}).values() if isinstance(inp, list) for v in inp[1:])
            elif kind == "list":
                hit = (fields.get("LIST") or [None])[0] == name
                hit = hit or any(isinstance(v, list) and len(v) > 2 and v[0] == 13 and v[1] == name
                                 for inp in (b.get("inputs") or {}).values() if isinstance(inp, list) for v in inp[1:])
            elif kind == "broadcast":
                hit = (fields.get("BROADCAST_OPTION") or [None])[0] == name or any(
                    isinstance(v, list) and len(v) > 2 and v[0] == 11 and v[1] == name
                    for inp in (b.get("inputs") or {}).values() if isinstance(inp, list) for v in inp[1:])
            elif kind in ("costume", "sound", "sprite"):
                menus = {"costume": ("looks_costume", "looks_backdrops"), "sound": ("sound_sounds_menu",),
                         "sprite": ("motion_goto_menu", "motion_glideto_menu", "motion_pointtowards_menu", "sensing_touchingobjectmenu",
                                    "event_touchingobjectmenu", "sensing_distancetomenu", "control_create_clone_of_menu", "sensing_of_object_menu")}[kind]
                hit = b["opcode"] in menus and next(iter(fields.values()), [None])[0] == name
            elif kind == "procedure":
                hit = b["opcode"] == "procedures_call" and (b.get("mutation") or {}).get("proccode") == name
            else:
                raise WorkspaceError("kind must be variable, list, broadcast, costume, sound, sprite or procedure.")
            if hit:
                uses.append({"sprite": who, "block": bid, "opcode": b["opcode"], "text": r.render_inline(b)})
    return {"kind": kind, "name": name, "uses": len(uses), "where": uses[:100]}


@action(G, "json")
def json_view(ctx: Ctx, section: str | None = None, project: str | None = None, pretty: bool = True, max_chars: int = 60000) -> dict:
    """Raw project.json (or part of it). section examples: 'targets[1].blocks', 'targets[0].costumes', 'meta', 'extensions', 'monitors'. Output is cut at max_chars with a note.

    Args:
        section: path into project.json using keys and [index]; omit for everything.
        max_chars: truncate the text beyond this length.
    """
    import re

    s = ctx.session(project)
    node: Any = s.project
    if section:
        for part in re.findall(r"[^.\[\]]+|\[\d+\]", section):
            try:
                node = node[int(part[1:-1])] if part.startswith("[") else node[part]
            except (KeyError, IndexError, TypeError):
                raise WorkspaceError(f"Nothing at '{section}' (failed at '{part}').") from None
    text = json.dumps(node, indent=1 if pretty else None, ensure_ascii=False, separators=None if pretty else (",", ":"))
    return {"section": section or "(whole project)", "chars": len(text), "truncated": len(text) > max_chars, "json": text[:max_chars]}

