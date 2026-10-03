"""variable_manager: variables, lists, broadcast messages and their monitors."""

from __future__ import annotations

from typing import Any

from ..ctx import Ctx
from ..engine import Graph
from ..registry import GROUP_DOCS, action
from ..textparse import make_id_factory
from ..workspace import WorkspaceError

G = "variable_manager"
GROUP_DOCS[G] = (
    "Manage variables (global = Stage, or local to one sprite), lists, broadcast messages and on-screen monitors. "
    "Renaming updates every block that uses the variable; deleting refuses while blocks still use it unless force=true."
)


def _scopes(data: dict[str, Any]):
    for t in data["targets"]:
        yield t


def _find(data: dict[str, Any], key: str, name: str, sprite_scope: dict[str, Any] | None):
    """(owner target, id) for a variable/list visible from sprite_scope (local first, then global)."""
    stage = next(t for t in data["targets"] if t.get("isStage"))
    scopes = ([sprite_scope] if sprite_scope is not None and sprite_scope is not stage else []) + [stage]
    for sc in scopes:
        for vid, entry in (sc.get(key) or {}).items():
            if entry and entry[0] == name:
                return sc, vid
    return None, None


def _uses(data: dict[str, Any], kind: str, ident: str) -> int:
    n = 0
    code = {"variable": 12, "list": 13, "broadcast": 11}[kind]
    fieldname = {"variable": "VARIABLE", "list": "LIST", "broadcast": "BROADCAST_OPTION"}[kind]
    for t in data["targets"]:
        for b in (t.get("blocks") or {}).values():
            if isinstance(b, list):
                n += int(len(b) > 2 and b[0] == code and b[2] == ident)
                continue
            f = (b.get("fields") or {}).get(fieldname)
            if isinstance(f, list) and len(f) > 1 and f[1] == ident:
                n += 1
            for inp in (b.get("inputs") or {}).values():
                for v in inp[1:] if isinstance(inp, list) else []:
                    if isinstance(v, list) and len(v) > 2 and v[0] == code and v[2] == ident:
                        n += 1
    return n


def _rewrite(data: dict[str, Any], kind: str, ident: str, new_name: str | None, remove: bool = False) -> None:
    code = {"variable": 12, "list": 13, "broadcast": 11}[kind]
    fieldname = {"variable": "VARIABLE", "list": "LIST", "broadcast": "BROADCAST_OPTION"}[kind]
    for t in data["targets"]:
        blocks = t.get("blocks") or {}
        for bid, b in list(blocks.items()):
            if isinstance(b, list):
                if len(b) > 2 and b[0] == code and b[2] == ident and new_name:
                    b[1] = new_name
                continue
            f = (b.get("fields") or {}).get(fieldname)
            if isinstance(f, list) and len(f) > 1 and f[1] == ident and new_name:
                f[0] = new_name
            for inp in (b.get("inputs") or {}).values():
                for v in inp[1:] if isinstance(inp, list) else []:
                    if isinstance(v, list) and len(v) > 2 and v[0] == code and v[2] == ident and new_name:
                        v[1] = new_name
    for m in data.get("monitors") or []:
        if m.get("id") == ident:
            if new_name:
                m["params"] = {**(m.get("params") or {}), ("VARIABLE" if kind == "variable" else "LIST"): new_name}


@action(G, "list")
def list_all(ctx: Ctx, project: str | None = None) -> dict:
    """All variables, lists and broadcast messages with scope, values and how many blocks use each."""
    data = ctx.session(project).project
    out: dict[str, Any] = {"variables": [], "lists": [], "broadcasts": []}
    for t in data["targets"]:
        scope = "global" if t.get("isStage") else t["name"]
        for vid, v in (t.get("variables") or {}).items():
            out["variables"].append({"name": v[0], "id": vid, "value": v[1], "scope": scope, "cloud": bool(len(v) > 2 and v[2]),
                                     "used_by_blocks": _uses(data, "variable", vid)})
        for lid, v in (t.get("lists") or {}).items():
            out["lists"].append({"name": v[0], "id": lid, "items": len(v[1]), "preview": v[1][:5], "scope": scope,
                                 "used_by_blocks": _uses(data, "list", lid)})
        if t.get("isStage"):
            for bid, name in (t.get("broadcasts") or {}).items():
                out["broadcasts"].append({"name": name, "id": bid, "used_by_blocks": _uses(data, "broadcast", bid)})
    return out


@action(G)
def create_variable(ctx: Ctx, name: str, value: str | float | int = 0, sprite: str | None = None,
                    cloud: bool = False, project: str | None = None) -> dict:
    """Create a variable.

    Args:
        name: variable name (unique within its scope; a cloud variable's name is stored with the '☁ ' prefix).
        value: initial value.
        sprite: omit for a global variable ('for all sprites'); give a sprite name for 'this sprite only'.
        cloud: cloud variable (must be global; numbers only). Stored in the file; syncing needs the online Scratch site.
    """
    if cloud and sprite:
        raise WorkspaceError("Cloud variables must be global (omit sprite).")
    if not name.strip():
        raise WorkspaceError("Variable name is empty.")
    if cloud:
        name = name if name.startswith("☁ ") else "☁ " + name
        if not isinstance(value, (int, float)) and not str(value).lstrip("-").replace(".", "", 1).isdigit():
            raise WorkspaceError("Cloud variables hold numbers only.")
    session = ctx.session(project)
    with ctx.store.edit(project, f"create variable {name}") as h:
        stage = next(t for t in h.project["targets"] if t.get("isStage"))
        target = ctx.target(h.project, session, sprite) if sprite else stage
        for t in h.project["targets"]:  # Scratch forbids a sprite variable shadowing a global (and vice versa)
            if t is target or t is stage or target is stage:
                for v in (t.get("variables") or {}).values():
                    if v[0] == name and (t is target or target is stage or t is stage):
                        raise WorkspaceError(f"A variable named '{name}' already exists in that scope.")
        vid = make_id_factory(h.project)()
        entry: list[Any] = [name, value]
        if cloud:
            entry.append(True)
        target.setdefault("variables", {})[vid] = entry
    return {"created": name, "id": vid, "scope": "global" if target is stage else target["name"]}


@action(G)
def set_variable(ctx: Ctx, name: str, value: str | float | int, sprite: str | None = None, project: str | None = None) -> dict:
    """Set a variable's stored (starting) value."""
    session = ctx.session(project)
    with ctx.store.edit(project, f"set variable {name}") as h:
        scope = ctx.target(h.project, session, sprite) if sprite else None
        owner, vid = _find(h.project, "variables", name, scope)
        if owner is None:
            raise WorkspaceError(f"No variable named '{name}'.")
        owner["variables"][vid][1] = value
    return {"set": name, "value": value}


@action(G)
def rename_variable(ctx: Ctx, name: str, new_name: str, sprite: str | None = None, project: str | None = None) -> dict:
    """Rename a variable everywhere it is used."""
    session = ctx.session(project)
    with ctx.store.edit(project, f"rename variable {name}") as h:
        scope = ctx.target(h.project, session, sprite) if sprite else None
        owner, vid = _find(h.project, "variables", name, scope)
        if owner is None:
            raise WorkspaceError(f"No variable named '{name}'.")
        if any(v[0] == new_name for v in owner["variables"].values()):
            raise WorkspaceError(f"A variable named '{new_name}' already exists.")
        owner["variables"][vid][0] = new_name
        _rewrite(h.project, "variable", vid, new_name)
    return {"renamed": f"{name} -> {new_name}"}


@action(G)
def delete_variable(ctx: Ctx, name: str, sprite: str | None = None, force: bool = False, project: str | None = None) -> dict:
    """Delete a variable. Refuses while blocks use it unless force=true (those blocks then re-create it when run)."""
    session = ctx.session(project)
    with ctx.store.edit(project, f"delete variable {name}") as h:
        scope = ctx.target(h.project, session, sprite) if sprite else None
        owner, vid = _find(h.project, "variables", name, scope)
        if owner is None:
            raise WorkspaceError(f"No variable named '{name}'.")
        uses = _uses(h.project, "variable", vid)
        if uses and not force:
            raise WorkspaceError(f"'{name}' is used by {uses} block(s). Remove them first or pass force=true.")
        del owner["variables"][vid]
        h.project["monitors"] = [m for m in h.project.get("monitors") or [] if m.get("id") != vid]
    return {"deleted": name, "blocks_still_referencing": uses}


@action(G)
def create_list(ctx: Ctx, name: str, items: list[str | float | int] | None = None, sprite: str | None = None,
                project: str | None = None) -> dict:
    """Create a list (global unless sprite is given) with optional starting items."""
    session = ctx.session(project)
    with ctx.store.edit(project, f"create list {name}") as h:
        stage = next(t for t in h.project["targets"] if t.get("isStage"))
        target = ctx.target(h.project, session, sprite) if sprite else stage
        if any(v[0] == name for v in (target.get("lists") or {}).values()) or \
                (target is not stage and any(v[0] == name for v in (stage.get("lists") or {}).values())):
            raise WorkspaceError(f"A list named '{name}' already exists.")
        lid = make_id_factory(h.project)()
        target.setdefault("lists", {})[lid] = [name, list(items or [])]
    return {"created": name, "id": lid}


@action(G)
def set_list(ctx: Ctx, name: str, items: list[str | float | int], sprite: str | None = None, project: str | None = None) -> dict:
    """Replace a list's starting contents."""
    session = ctx.session(project)
    with ctx.store.edit(project, f"set list {name}") as h:
        scope = ctx.target(h.project, session, sprite) if sprite else None
        owner, lid = _find(h.project, "lists", name, scope)
        if owner is None:
            raise WorkspaceError(f"No list named '{name}'.")
        owner["lists"][lid][1] = list(items)
    return {"set": name, "items": len(items)}


@action(G)
def rename_list(ctx: Ctx, name: str, new_name: str, sprite: str | None = None, project: str | None = None) -> dict:
    """Rename a list everywhere it is used."""
    session = ctx.session(project)
    with ctx.store.edit(project, f"rename list {name}") as h:
        scope = ctx.target(h.project, session, sprite) if sprite else None
        owner, lid = _find(h.project, "lists", name, scope)
        if owner is None:
            raise WorkspaceError(f"No list named '{name}'.")
        owner["lists"][lid][0] = new_name
        _rewrite(h.project, "list", lid, new_name)
    return {"renamed": f"{name} -> {new_name}"}


@action(G)
def delete_list(ctx: Ctx, name: str, sprite: str | None = None, force: bool = False, project: str | None = None) -> dict:
    """Delete a list (refuses while blocks use it unless force=true)."""
    session = ctx.session(project)
    with ctx.store.edit(project, f"delete list {name}") as h:
        scope = ctx.target(h.project, session, sprite) if sprite else None
        owner, lid = _find(h.project, "lists", name, scope)
        if owner is None:
            raise WorkspaceError(f"No list named '{name}'.")
        uses = _uses(h.project, "list", lid)
        if uses and not force:
            raise WorkspaceError(f"'{name}' is used by {uses} block(s). Remove them first or pass force=true.")
        del owner["lists"][lid]
        h.project["monitors"] = [m for m in h.project.get("monitors") or [] if m.get("id") != lid]
    return {"deleted": name}


@action(G)
def create_broadcast(ctx: Ctx, name: str, project: str | None = None) -> dict:
    """Create a broadcast message (they are also created automatically when a block uses a new name)."""
    with ctx.store.edit(project, f"create broadcast {name}") as h:
        stage = next(t for t in h.project["targets"] if t.get("isStage"))
        g = Graph(h.project, stage)
        n, bid = g.broadcast(name)
    return {"name": n, "id": bid}


@action(G)
def rename_broadcast(ctx: Ctx, name: str, new_name: str, project: str | None = None) -> dict:
    """Rename a broadcast message everywhere (senders and receivers)."""
    with ctx.store.edit(project, f"rename broadcast {name}") as h:
        stage = next(t for t in h.project["targets"] if t.get("isStage"))
        bid = next((i for i, n in (stage.get("broadcasts") or {}).items() if n == name), None)
        if bid is None:
            raise WorkspaceError(f"No broadcast message '{name}'.")
        if new_name in (stage.get("broadcasts") or {}).values():
            raise WorkspaceError(f"A message named '{new_name}' already exists.")
        stage["broadcasts"][bid] = new_name
        _rewrite(h.project, "broadcast", bid, new_name)
    return {"renamed": f"{name} -> {new_name}"}


@action(G)
def delete_broadcast(ctx: Ctx, name: str, force: bool = False, project: str | None = None) -> dict:
    """Delete an unused broadcast message (unused ones are also dropped by Scratch on save)."""
    with ctx.store.edit(project, f"delete broadcast {name}") as h:
        stage = next(t for t in h.project["targets"] if t.get("isStage"))
        bid = next((i for i, n in (stage.get("broadcasts") or {}).items() if n == name), None)
        if bid is None:
            raise WorkspaceError(f"No broadcast message '{name}'.")
        uses = _uses(h.project, "broadcast", bid)
        if uses and not force:
            raise WorkspaceError(f"'{name}' is used by {uses} block(s). Pass force=true to delete anyway.")
        del stage["broadcasts"][bid]
    return {"deleted": name}


@action(G)
def set_monitor(ctx: Ctx, name: str, visible: bool = True, mode: str = "default", x: int | None = None, y: int | None = None,
                slider_min: float = 0, slider_max: float = 100, sprite: str | None = None, project: str | None = None) -> dict:
    """Show/hide the stage monitor of a variable or list and choose its style.

    Args:
        name: variable or list name.
        mode: 'default' (name + value), 'large' (value only), 'slider', or 'list'.
        sprite: sprite owning a local variable (omit for global).
    """
    if mode not in ("default", "large", "slider", "list"):
        raise WorkspaceError("mode must be default, large, slider or list.")
    session = ctx.session(project)
    with ctx.store.edit(project, f"monitor {name}") as h:
        scope = ctx.target(h.project, session, sprite) if sprite else None
        owner, vid = _find(h.project, "variables", name, scope)
        kind = "variable"
        if owner is None:
            owner, vid = _find(h.project, "lists", name, scope)
            kind = "list"
        if owner is None:
            raise WorkspaceError(f"No variable or list named '{name}'.")
        monitors = h.project.setdefault("monitors", [])
        mon = next((m for m in monitors if m.get("id") == vid), None)
        spritename = None if owner.get("isStage") else owner["name"]
        if mon is None:
            mon = {"id": vid, "mode": "list" if kind == "list" else mode, "opcode": "data_variable" if kind == "variable" else "data_listcontents",
                   "params": {("VARIABLE" if kind == "variable" else "LIST"): name}, "spriteName": spritename, "value": [] if kind == "list" else owner["variables"][vid][1],
                   "width": 0, "height": 0, "x": x if x is not None else 5, "y": y if y is not None else 5, "visible": visible,
                   "sliderMin": slider_min, "sliderMax": slider_max, "isDiscrete": True}
            monitors.append(mon)
        else:
            mon.update(visible=visible, mode="list" if kind == "list" else mode, sliderMin=slider_min, sliderMax=slider_max)
            if x is not None:
                mon["x"] = x
            if y is not None:
                mon["y"] = y
    return {"monitor": name, "visible": visible, "mode": mon["mode"]}
