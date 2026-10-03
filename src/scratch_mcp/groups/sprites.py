"""sprite_manager: create / delete / duplicate / rename / select sprites and set their properties."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from .. import editing, stock_art
from ..blocks import MENUS
from ..ctx import Ctx
from ..registry import GROUP_DOCS, action
from ..textparse import make_id_factory
from ..workspace import WorkspaceError

G = "sprite_manager"
GROUP_DOCS[G] = (
    "Create and manage sprites and their properties (position, size, direction, rotation style, visibility, draggable, "
    "layer, volume, current costume). 'select' sets the default sprite for other tools. Clone creation/inspection happens "
    "at run time: see runtime_manager (create_clone, list_clones). Costumes: costume_manager. Sounds: sound_manager. "
    "Scripts: script_manager. The Stage is not a sprite - use backdrop_manager."
)

ROTATION_STYLES = ("all around", "left-right", "don't rotate")


def _sprites(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in data["targets"] if not t.get("isStage")]


def _sprite_info(t: dict[str, Any]) -> dict[str, Any]:
    costumes = t.get("costumes") or []
    cur = t.get("currentCostume", 0)
    return {"name": t["name"], "x": t.get("x"), "y": t.get("y"), "size": t.get("size"), "direction": t.get("direction"),
            "visible": t.get("visible"), "draggable": t.get("draggable"), "rotation_style": t.get("rotationStyle"),
            "layer": t.get("layerOrder"), "volume": t.get("volume"),
            "current_costume": costumes[cur]["name"] if costumes and cur < len(costumes) else None,
            "costumes": [c["name"] for c in costumes], "sounds": [s["name"] for s in t.get("sounds") or []],
            "blocks": len(t.get("blocks") or {}),
            "local_variables": [v[0] for v in (t.get("variables") or {}).values()],
            "local_lists": [v[0] for v in (t.get("lists") or {}).values()]}


def _normalize_layers(data: dict[str, Any]) -> None:
    ordered = sorted(data["targets"], key=lambda t: (0 if t.get("isStage") else 1, t.get("layerOrder", 0)))
    for i, t in enumerate(ordered):
        t["layerOrder"] = i


@action(G, "list")
def list_sprites(ctx: Ctx, project: str | None = None) -> dict:
    """List all sprites (back to front) with their properties."""
    s = ctx.session(project)
    sprites = sorted(_sprites(s.project), key=lambda t: t.get("layerOrder", 0))
    return {"selected": s.selected_sprite, "sprites": [_sprite_info(t) for t in sprites]}


@action(G)
def get(ctx: Ctx, sprite: str | None = None, project: str | None = None) -> dict:
    """All properties of one sprite."""
    s = ctx.session(project)
    return _sprite_info(ctx.target(s.project, s, sprite))


@action(G)
def create(ctx: Ctx, name: str, svg: str | None = None, stock: str | None = None, image_path: str | None = None,
           image_base64: str | None = None, x: float = 0, y: float = 0, size: float = 100, direction: float = 90,
           visible: bool = True, bitmap_resolution: int = 2, project: str | None = None) -> dict:
    """Create a sprite. Its first costume comes from one of: svg (SVG text), stock ('robot', 'alien', 'cookie', 'title' - all poses), image_path (png/jpg/svg file inside the projects folder) or image_base64. With none of them it gets a blank costume.

    Args:
        name: sprite name (unique).
        stock: stock art name, see costume_manager stock_list.
        image_path: image file inside the projects folder.
        bitmap_resolution: 2 (default, image shown at half size) or 1 (native pixels) for png/jpg.
    """
    sources = [bool(svg), bool(stock), bool(image_path), bool(image_base64)]
    if sum(sources) > 1:
        raise WorkspaceError("Give at most one of svg, stock, image_path, image_base64.")
    session = ctx.session(project)
    with ctx.store.edit(project, f"create sprite {name}") as h:
        sprite = editing.new_sprite(h.project, name, x, y, size, direction, visible)
        if stock:
            _, costumes, is_backdrop = _stock(stock)
            if is_backdrop:
                raise WorkspaceError(f"'{stock}' is a backdrop; use backdrop_manager.")
            for cname, csvg, cx, cy in costumes:
                editing.add_costume(h.project, h.assets, sprite, cname, csvg, (cx, cy))
        elif image_path or image_base64:
            data = ctx.ws.resolve_file(image_path).read_bytes() if image_path else _b64(image_base64)
            editing.import_image(h.project, h.assets, sprite, "costume1", data, bitmap_resolution)
        else:
            editing.add_costume(h.project, h.assets, sprite, "costume1", svg or editing.BLANK_SVG)
        _normalize_layers(h.project)
    session.selected_sprite = sprite["name"]
    return {"created": sprite["name"], "costumes": [c["name"] for c in sprite["costumes"]], "selected": True}


def _stock(name: str):
    try:
        return stock_art.stock_art(name)
    except KeyError as exc:
        raise WorkspaceError(f"Unknown stock art '{name}'. Choose from: {', '.join(stock_art.STOCK_NAMES)}.") from exc


def _b64(text: str | None) -> bytes:
    try:
        return base64.b64decode(text or "", validate=False)
    except (binascii.Error, ValueError) as exc:
        raise WorkspaceError("image_base64 is not valid base64.") from exc


@action(G)
def delete(ctx: Ctx, sprite: str, project: str | None = None) -> dict:
    """Delete a sprite, its scripts and any files nothing else uses."""
    session = ctx.session(project)
    with ctx.store.edit(project, f"delete sprite {sprite}") as h:
        target = ctx.target(h.project, session, sprite)
        if target.get("isStage"):
            raise WorkspaceError("The Stage can't be deleted.")
        h.project["targets"].remove(target)
        editing.prune_unused_assets(h.project, h.assets)
        _normalize_layers(h.project)
    if session.selected_sprite == target["name"]:
        names = [t["name"] for t in _sprites(session.project)]
        session.selected_sprite = names[-1] if names else None
    return {"deleted": target["name"], "selected": session.selected_sprite}


@action(G)
def duplicate(ctx: Ctx, sprite: str | None = None, new_name: str | None = None, project: str | None = None) -> dict:
    """Duplicate a sprite with all costumes, sounds, scripts and local variables (new block ids). It is placed in front and selected."""
    session = ctx.session(project)
    with ctx.store.edit(project, "duplicate sprite") as h:
        src = ctx.target(h.project, session, sprite)
        if src.get("isStage"):
            raise WorkspaceError("The Stage can't be duplicated.")
        new = editing.clone_sprite(h.project, src, new_name, make_id_factory(h.project))
        _normalize_layers(h.project)
    session.selected_sprite = new["name"]
    return {"created": new["name"], "from": src["name"]}


@action(G)
def rename(ctx: Ctx, new_name: str, sprite: str | None = None, project: str | None = None) -> dict:
    """Rename a sprite (menus like 'touching (Cat v)' that name it are updated)."""
    session = ctx.session(project)
    new_name = new_name.strip()
    with ctx.store.edit(project, "rename sprite") as h:
        target = ctx.target(h.project, session, sprite)
        if target.get("isStage"):
            raise WorkspaceError("The Stage can't be renamed.")
        if not new_name or new_name.lower() == "stage":
            raise WorkspaceError("Invalid sprite name.")
        if any(t is not target and str(t.get("name", "")).lower() == new_name.lower() for t in h.project["targets"]):
            raise WorkspaceError(f"A sprite named '{new_name}' already exists.")
        old = target["name"]
        for t in h.project["targets"]:
            for block in (t.get("blocks") or {}).values():
                if isinstance(block, dict) and block.get("opcode") in MENUS:
                    for f in (block.get("fields") or {}).values():
                        if isinstance(f, list) and f and f[0] == old:
                            f[0] = new_name
        target["name"] = new_name
        for m in h.project.get("monitors") or []:
            if m.get("spriteName") == old:
                m["spriteName"] = new_name
    if session.selected_sprite == old:
        session.selected_sprite = new_name
    return {"renamed": f"{old} -> {new_name}"}


@action(G)
def select(ctx: Ctx, sprite: str, project: str | None = None) -> dict:
    """Select the sprite other tools use by default (no project change, not undoable)."""
    s = ctx.session(project)
    from ..editing import EditError, find_target

    try:
        t = find_target(s.project, sprite)
    except EditError as exc:
        raise WorkspaceError(str(exc)) from exc
    s.selected_sprite = t["name"]
    return {"selected": t["name"]}


@action(G, "set")
def set_props(ctx: Ctx, sprite: str | None = None, x: float | None = None, y: float | None = None, size: float | None = None,
        direction: float | None = None, visible: bool | None = None, draggable: bool | None = None,
        rotation_style: str | None = None, volume: float | None = None, costume: str | None = None,
        project: str | None = None) -> dict:
    """Change sprite properties. Use visible=false/true to hide/show. costume = name or number.

    Args:
        size: percent (100 = normal).
        direction: degrees (90 = right, 0 = up).
        rotation_style: 'all around', 'left-right' or "don't rotate".
        volume: 0-100.
    """
    changes = {k: v for k, v in dict(x=x, y=y, size=size, direction=direction, visible=visible, draggable=draggable,
                                      rotationStyle=rotation_style, volume=volume).items() if v is not None}
    if rotation_style is not None and rotation_style not in ROTATION_STYLES:
        raise WorkspaceError(f"rotation_style must be one of {ROTATION_STYLES}.")
    if size is not None and size < 0:
        raise WorkspaceError("size can't be negative.")
    if volume is not None and not 0 <= volume <= 100:
        raise WorkspaceError("volume must be 0-100.")
    if not changes and costume is None:
        raise WorkspaceError("Nothing to change: pass at least one property.")
    session = ctx.session(project)
    with ctx.store.edit(project, "set sprite properties") as h:
        t = ctx.target(h.project, session, sprite)
        if t.get("isStage"):
            raise WorkspaceError("Use backdrop_manager for the Stage.")
        t.update(changes)
        if costume is not None:
            names = [c["name"] for c in t.get("costumes") or []]
            if costume in names:
                t["currentCostume"] = names.index(costume)
            elif costume.isdigit() and 0 < int(costume) <= len(names):
                t["currentCostume"] = int(costume) - 1
            else:
                raise WorkspaceError(f"No costume '{costume}'. Available: {', '.join(names)}")
    return _sprite_info(session.project["targets"][[x_["name"] for x_ in session.project["targets"]].index(t["name"])])


@action(G)
def layer(ctx: Ctx, mode: str, sprite: str | None = None, steps: int = 1, project: str | None = None) -> dict:
    """Change drawing order among sprites.

    Args:
        mode: 'front', 'back', 'forward' or 'backward' (by `steps`).
    """
    if mode not in ("front", "back", "forward", "backward"):
        raise WorkspaceError("mode must be front, back, forward or backward.")
    session = ctx.session(project)
    with ctx.store.edit(project, f"layer {mode}") as h:
        t = ctx.target(h.project, session, sprite)
        if t.get("isStage"):
            raise WorkspaceError("The Stage is always at the back.")
        order = sorted(_sprites(h.project), key=lambda s: s.get("layerOrder", 0))
        i = order.index(t)
        order.pop(i)
        j = {"front": len(order), "back": 0, "forward": min(len(order), i + steps), "backward": max(0, i - steps)}[mode]
        order.insert(j, t)
        for n, s in enumerate(order, start=1):
            s["layerOrder"] = n
    return {"order_back_to_front": [s["name"] for s in sorted(_sprites(session.project), key=lambda s: s["layerOrder"])]}


@action(G)
def import_sprite(ctx: Ctx, source_path: str | None = None, data_base64: str | None = None, name: str | None = None,
                  project: str | None = None) -> dict:
    """Import a .sprite3 file (exported from Scratch or by export_manager) into the project.

    Args:
        source_path: .sprite3 file inside the projects folder.
        data_base64: alternatively its bytes, base64 encoded.
    """
    if bool(source_path) == bool(data_base64):
        raise WorkspaceError("Give exactly one of source_path or data_base64.")
    data = ctx.ws.resolve_file(source_path).read_bytes() if source_path else _b64(data_base64)
    session = ctx.session(project)
    with ctx.store.edit(project, "import sprite") as h:
        sprite = editing.import_sprite3(h.project, h.assets, data, make_id_factory(h.project), name)
        _normalize_layers(h.project)
    session.selected_sprite = sprite["name"]
    return {"imported": sprite["name"], "costumes": len(sprite["costumes"]), "sounds": len(sprite["sounds"]),
            "blocks": len(sprite["blocks"])}
