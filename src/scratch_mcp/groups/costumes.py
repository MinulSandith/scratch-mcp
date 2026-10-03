"""costume_manager: costumes and backdrops (sprite='Stage') + the vector editor."""

from __future__ import annotations

import base64
from typing import Any, Callable

from .. import editing, stock_art
from ..ctx import Ctx
from ..registry import GROUP_DOCS, Reply, action
from ..vector import SHAPES, VectorDoc, VectorError, bbox_in_parent, fnum, tag
from ..workspace import WorkspaceError

G = "costume_manager"
GROUP_DOCS[G] = (
    "Costumes of a sprite - or backdrops when sprite='Stage'. Manage them (add, import png/jpg/svg, duplicate, rename, "
    "reorder, delete, set centre, export, preview) and draw/edit them as vectors: shapes, lines, curves, text, select + "
    "transform (move/resize/rotate/flip/skew), group/ungroup, layers, fill/outline, path nodes, copy/paste, canvas "
    "size, crop. Elements are addressed by id (see 'elements'). A costume is addressed by name or 1-based number. "
    "Coordinates: costume pixels, origin top-left; Scratch's stage is 480x360 (a sprite's rotation centre is the "
    "point that sits at its x/y position). Bitmap costumes can be switched to vector with to_vector and back with "
    "to_bitmap (needs the headless browser, see runtime_manager setup). Edits are undoable (project_manager undo)."
)


def _find_costume(target: dict[str, Any], costume: str | int | None) -> tuple[int, dict[str, Any]]:
    items = target.get("costumes") or []
    if costume is None:
        i = target.get("currentCostume", 0)
        return i, items[i]
    names = [c["name"] for c in items]
    if isinstance(costume, int) or (isinstance(costume, str) and costume.isdigit() and costume not in names):
        n = int(costume)
        if 1 <= n <= len(items):
            return n - 1, items[n - 1]
    if costume in names:
        return names.index(costume), items[names.index(costume)]
    raise WorkspaceError(f"No costume '{costume}'. Available: {', '.join(names)}")


def _label(target: dict[str, Any]) -> str:
    return "backdrop" if target.get("isStage") else "costume"


def _svg_of(h_assets: dict[str, bytes], entry: dict[str, Any]) -> str:
    if entry.get("dataFormat") != "svg":
        raise WorkspaceError(f"'{entry['name']}' is a bitmap ({entry.get('dataFormat')}) costume. "
                             "Use costume_manager to_vector to switch it to vector first.")
    return h_assets[entry["md5ext"]].decode("utf-8")


def _set_svg(h, entry: dict[str, Any], svg: str) -> None:
    editing.check_svg(svg)
    data = svg.encode("utf-8")
    md5 = editing.md5_of(data)
    h.assets[f"{md5}.svg"] = data
    entry.update(assetId=md5, md5ext=f"{md5}.svg", dataFormat="svg")
    editing.prune_unused_assets(h.project, h.assets)


def vec_edit(ctx: Ctx, project: str | None, sprite: str | None, costume: str | int | None, label: str,
             fn: Callable[[VectorDoc, dict[str, Any], dict[str, Any]], dict[str, Any] | None]) -> dict[str, Any]:
    session = ctx.session(project)
    out: dict[str, Any] = {}
    with ctx.store.edit(project, label) as h:
        target = ctx.target(h.project, session, sprite)
        _, entry = _find_costume(target, costume)
        doc = VectorDoc(_svg_of(h.assets, entry))
        try:
            out = dict(fn(doc, entry) or {})
        except VectorError as exc:
            raise WorkspaceError(f"Not applied. {exc}") from exc
        _set_svg(h, entry, doc.to_string())
        out["costume"] = entry["name"]
    return out


# ---------------------------------------------------------------- management

@action(G, "list")
def list_costumes(ctx: Ctx, sprite: str | None = None, project: str | None = None) -> dict:
    """List costumes (or backdrops for the Stage) with format, size and rotation centre."""
    s = ctx.session(project)
    t = ctx.target(s.project, s, sprite)
    cur = t.get("currentCostume", 0)
    return {"target": "Stage" if t.get("isStage") else t["name"], "current": cur + 1, "costumes": [
        {"number": i + 1, "name": c["name"], "format": c["dataFormat"], "bitmap_resolution": c.get("bitmapResolution", 1),
         "center": [c.get("rotationCenterX"), c.get("rotationCenterY")], "current": i == cur,
         "bytes": len(s.assets.get(c["md5ext"], b""))} for i, c in enumerate(t["costumes"])]}


@action(G)
def add_blank(ctx: Ctx, name: str = "costume", width: float = 100, height: float = 100, background: str | None = None,
              sprite: str | None = None, project: str | None = None) -> dict:
    """Add an empty vector costume of a given size (optionally filled with a background colour); draw on it with 'draw'.

    Args:
        width: canvas width in pixels (backdrops are 480x360).
        background: e.g. '#87ceeb' or omit for transparent.
    """
    session = ctx.session(project)
    with ctx.store.edit(project, f"add blank {name}") as h:
        t = ctx.target(h.project, session, sprite)
        entry = editing.add_costume(h.project, h.assets, t, name, VectorDoc.blank(width, height, background).to_string())
    return {"added": entry["name"], "center": [entry["rotationCenterX"], entry["rotationCenterY"]]}


@action(G)
def add_svg(ctx: Ctx, name: str, svg: str, center_x: float | None = None, center_y: float | None = None,
            sprite: str | None = None, project: str | None = None) -> dict:
    """Add a costume from SVG text (checked: no scripts/external links)."""
    session = ctx.session(project)
    with ctx.store.edit(project, f"add costume {name}") as h:
        t = ctx.target(h.project, session, sprite)
        entry = editing.add_costume(h.project, h.assets, t, name, svg, (center_x, center_y))
    return {"added": entry["name"], "center": [entry["rotationCenterX"], entry["rotationCenterY"]]}


@action(G)
def import_image(ctx: Ctx, name: str, source_path: str | None = None, data_base64: str | None = None,
                 bitmap_resolution: int = 2, sprite: str | None = None, project: str | None = None) -> dict:
    """Import a PNG, JPEG or SVG as a costume/backdrop.

    Args:
        source_path: image file inside the projects folder.
        data_base64: alternatively the file bytes, base64 encoded.
        bitmap_resolution: for png/jpg: 2 = shown at half pixel size (Scratch default), 1 = native pixels.
    """
    if bool(source_path) == bool(data_base64):
        raise WorkspaceError("Give exactly one of source_path or data_base64.")
    data = ctx.ws.resolve_file(source_path).read_bytes() if source_path else base64.b64decode(data_base64 or "")
    session = ctx.session(project)
    with ctx.store.edit(project, f"import {name}") as h:
        t = ctx.target(h.project, session, sprite)
        entry = editing.import_image(h.project, h.assets, t, name, data, bitmap_resolution)
    return {"imported": entry["name"], "format": entry["dataFormat"]}


@action(G)
def add_stock(ctx: Ctx, art: str, replace: bool = False, sprite: str | None = None, project: str | None = None,
              text: str | None = None) -> dict:
    """Add all costumes of a stock art set (robot, alien, cookie, title - or kitchen backdrops on the Stage). replace=true removes the existing ones first."""
    try:
        _, costumes, is_backdrop = stock_art.stock_art(art, text)
    except KeyError as exc:
        raise WorkspaceError(f"Unknown stock art '{art}'. Choose from: {', '.join(stock_art.STOCK_NAMES)}.") from exc
    session = ctx.session(project)
    with ctx.store.edit(project, f"add {art} art") as h:
        t = ctx.target(h.project, session, sprite)
        if is_backdrop != bool(t.get("isStage")):
            raise WorkspaceError(f"'{art}' is {'a backdrop set (use sprite=Stage)' if is_backdrop else 'sprite art (not for the Stage)'}.")
        if replace:
            t["costumes"], t["currentCostume"] = [], 0
        for cname, svg, cx, cy in costumes:
            editing.add_costume(h.project, h.assets, t, cname, svg, (cx, cy))
        editing.prune_unused_assets(h.project, h.assets)
    return {"costumes": [c["name"] for c in t["costumes"]]}


@action(G)
def stock_list(ctx: Ctx) -> dict:
    """List the built-in stock art sets."""
    out = {}
    for name in stock_art.STOCK_NAMES:
        description, costumes, is_backdrop = stock_art.stock_art(name)
        out[name] = {"description": description, "costumes": [c[0] for c in costumes], "backdrop": is_backdrop}
    return out


@action(G)
def delete(ctx: Ctx, costume: str | int, sprite: str | None = None, project: str | None = None) -> dict:
    """Delete a costume/backdrop (a sprite must keep at least one)."""
    session = ctx.session(project)
    with ctx.store.edit(project, "delete costume") as h:
        t = ctx.target(h.project, session, sprite)
        i, entry = _find_costume(t, costume)
        if len(t["costumes"]) == 1:
            raise WorkspaceError(f"A {_label(t)} list can't be empty - add another first.")
        del t["costumes"][i]
        cur = t.get("currentCostume", 0)
        if cur > i or cur >= len(t["costumes"]):
            t["currentCostume"] = max(0, min(cur - 1 if cur > i else cur, len(t["costumes"]) - 1))
        editing.prune_unused_assets(h.project, h.assets)
    return {"deleted": entry["name"], "remaining": len(t["costumes"])}


@action(G)
def duplicate(ctx: Ctx, costume: str | int | None = None, new_name: str | None = None, sprite: str | None = None,
              project: str | None = None) -> dict:
    """Duplicate a costume (placed right after the original)."""
    import copy

    session = ctx.session(project)
    with ctx.store.edit(project, "duplicate costume") as h:
        t = ctx.target(h.project, session, sprite)
        i, entry = _find_costume(t, costume)
        new = copy.deepcopy(entry)
        new["name"] = editing._unique(new_name or entry["name"], [c["name"] for c in t["costumes"]])
        t["costumes"].insert(i + 1, new)
        if t.get("currentCostume", 0) > i:
            t["currentCostume"] += 1
    return {"created": new["name"], "number": i + 2}


@action(G)
def rename(ctx: Ctx, costume: str | int, new_name: str, sprite: str | None = None, project: str | None = None) -> dict:
    """Rename a costume/backdrop (blocks that name it in a 'switch costume' menu are updated)."""
    session = ctx.session(project)
    with ctx.store.edit(project, "rename costume") as h:
        t = ctx.target(h.project, session, sprite)
        _, entry = _find_costume(t, costume)
        if not new_name.strip():
            raise WorkspaceError("New name is empty.")
        if any(c is not entry and c["name"] == new_name for c in t["costumes"]):
            raise WorkspaceError(f"A {_label(t)} named '{new_name}' already exists.")
        old = entry["name"]
        entry["name"] = new_name
        menu = "looks_backdrops" if t.get("isStage") else "looks_costume"
        owners = h.project["targets"] if t.get("isStage") else [t]
        for o in owners:
            for b in (o.get("blocks") or {}).values():
                if isinstance(b, dict) and b.get("opcode") == menu:
                    for f in (b.get("fields") or {}).values():
                        if f and f[0] == old:
                            f[0] = new_name
    return {"renamed": f"{old} -> {new_name}"}


@action(G)
def reorder(ctx: Ctx, costume: str | int, position: int, sprite: str | None = None, project: str | None = None) -> dict:
    """Move a costume to a 1-based position in the list."""
    session = ctx.session(project)
    with ctx.store.edit(project, "reorder costume") as h:
        t = ctx.target(h.project, session, sprite)
        i, entry = _find_costume(t, costume)
        if not 1 <= position <= len(t["costumes"]):
            raise WorkspaceError(f"position must be 1-{len(t['costumes'])}.")
        cur_entry = t["costumes"][t.get("currentCostume", 0)]
        t["costumes"].pop(i)
        t["costumes"].insert(position - 1, entry)
        t["currentCostume"] = t["costumes"].index(cur_entry)
    return {"order": [c["name"] for c in t["costumes"]]}


@action(G)
def set_current(ctx: Ctx, costume: str | int, sprite: str | None = None, project: str | None = None) -> dict:
    """Choose which costume/backdrop is shown when the project starts."""
    session = ctx.session(project)
    with ctx.store.edit(project, "set current costume") as h:
        t = ctx.target(h.project, session, sprite)
        i, entry = _find_costume(t, costume)
        t["currentCostume"] = i
    return {"current": entry["name"]}


@action(G)
def set_center(ctx: Ctx, costume: str | int | None = None, x: float | None = None, y: float | None = None,
               mode: str | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Set the rotation centre (the point that sits at the sprite's x/y).

    Args:
        x: centre x in costume pixels.
        y: centre y in costume pixels.
        mode: instead of x/y: 'center' (middle of the image), 'content' (middle of the artwork), 'bottom' (bottom middle - feet).
    """
    session = ctx.session(project)
    with ctx.store.edit(project, "set rotation centre") as h:
        t = ctx.target(h.project, session, sprite)
        _, entry = _find_costume(t, costume)
        if mode:
            if entry["dataFormat"] == "svg":
                doc = VectorDoc(h.assets[entry["md5ext"]].decode("utf-8"))
                w, hh = doc.size
                box = doc.content_bbox() or (0, 0, w, hh)
            else:
                _, w, hh = editing.image_info(h.assets[entry["md5ext"]])
                box = (0, 0, w, hh)
            if mode == "center":
                x, y = w / 2, hh / 2
            elif mode == "content":
                x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            elif mode == "bottom":
                x, y = w / 2, hh
            else:
                raise WorkspaceError("mode must be center, content or bottom.")
        if x is None or y is None:
            raise WorkspaceError("Give x and y, or a mode.")
        entry["rotationCenterX"], entry["rotationCenterY"] = round(x, 2), round(y, 2)
    return {"center": [entry["rotationCenterX"], entry["rotationCenterY"]]}


@action(G)
def svg(ctx: Ctx, costume: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Return the costume's SVG source text."""
    s = ctx.session(project)
    t = ctx.target(s.project, s, sprite)
    _, entry = _find_costume(t, costume)
    return {"name": entry["name"], "svg": _svg_of(s.assets, entry)}


@action(G)
async def preview(ctx: Ctx, costume: str | int | None = None, sprite: str | None = None, project: str | None = None,
            scale: float = 2.0, background: str | None = "#e8e8f0") -> Reply:
    """Render a costume/backdrop as a PNG image you can look at (needs the headless browser for vector costumes).

    Args:
        scale: pixel density multiplier.
        background: CSS colour behind transparent areas (null = transparent).
    """
    s = ctx.session(project)
    t = ctx.target(s.project, s, sprite)
    _, entry = _find_costume(t, costume)
    data = s.assets[entry["md5ext"]]
    if entry["dataFormat"] == "svg":
        doc = VectorDoc(data.decode("utf-8"))
        w, h = doc.size
        png = await ctx.browser.rasterize_svg(data.decode("utf-8"), int(w) or 1, int(h) or 1, scale, background)
        mime = "image/png"
    else:
        png, mime = data, "image/png" if entry["dataFormat"] == "png" else "image/jpeg"
    return Reply(text={"preview_of": entry["name"], "format": entry["dataFormat"]}, images=[(png, mime)])


@action(G)
def export(ctx: Ctx, costume: str | int | None = None, sprite: str | None = None, project: str | None = None,
           include_base64: bool = False) -> dict:
    """Write the costume file (svg/png/jpg) to <projects folder>/exports/ and return its path."""
    s = ctx.session(project)
    t = ctx.target(s.project, s, sprite)
    _, entry = _find_costume(t, costume)
    safe = "".join(ch if ch.isalnum() or ch in "-_ ." else "_" for ch in f"{t['name']}-{entry['name']}")
    folder = ctx.ws.root / "exports"
    folder.mkdir(exist_ok=True)
    path = folder / f"{safe}.{entry['dataFormat']}"
    data = s.assets[entry["md5ext"]]
    path.write_bytes(data)
    out = {"exported_to": ctx.ws.display(path), "bytes": len(data)}
    if include_base64 and len(data) < 512_000:
        out["base64"] = base64.b64encode(data).decode()
    return out


# ---------------------------------------------------------------- vector editing

@action(G)
def draw(ctx: Ctx, shape: str, costume: str | int | None = None, sprite: str | None = None, project: str | None = None,
         x: float | None = None, y: float | None = None, width: float | None = None, height: float | None = None,
         cx: float | None = None, cy: float | None = None, r: float | None = None, rx: float | None = None,
         ry: float | None = None, x1: float | None = None, y1: float | None = None, x2: float | None = None,
         y2: float | None = None, points: list[list[float]] | None = None, d: str | None = None,
         text: str | None = None, font_size: float | None = None, font_family: str | None = None, bold: bool = False,
         anchor: str | None = None, spikes: int | None = None, inner_ratio: float | None = None,
         fill: str | None = None, stroke: str | None = None, stroke_width: float | None = None,
         opacity: float | None = None, into_group: str | None = None) -> dict:
    """Draw a shape on a vector costume. shape: rect(x,y,width,height[,rx]), circle(cx,cy,r), ellipse(cx,cy,rx,ry), line(x1,y1,x2,y2), polyline(points), polygon(points), triangle(points), path(d), curve(points: 3 quadratic/4 cubic), star(cx,cy,r[,spikes,inner_ratio]), text(text,x,y[,font_size,font_family,bold,anchor]).

    Args:
        shape: one of rect, circle, ellipse, line, polyline, polygon, triangle, path, curve, star, text.
        points: [[x,y],...] for polyline/polygon/triangle/curve.
        d: SVG path data for 'path'.
        fill: CSS colour or 'none' (shapes default to black fill if omitted; lines/curves default to a black outline).
        stroke: outline colour.
        into_group: id of a group to draw into.
    """
    args = {k: v for k, v in dict(x=x, y=y, width=width, height=height, cx=cx, cy=cy, r=r, rx=rx, ry=ry, x1=x1, y1=y1, x2=x2,
                                  y2=y2, points=points, d=d, text=text, font_size=font_size, font_family=font_family,
                                  anchor=anchor, spikes=spikes, inner_ratio=inner_ratio).items() if v is not None}
    if bold:
        args["bold"] = True
    style = {k: v for k, v in dict(fill=fill, stroke=stroke, stroke_width=stroke_width, opacity=opacity).items() if v is not None}

    def fn(doc: VectorDoc, entry):
        parent = doc.find(into_group) if into_group else None
        el = doc.add_shape(shape, args, style, parent)
        if el.get("fill") is None and tag(el) not in ("line", "polyline") and "fill" not in style:
            if not (el.get("stroke") and shape in ("curve",)):
                el.set("fill", "#000000")
        return {"id": el.get("id"), "element": doc.describe(el)}

    return vec_edit(ctx, project, sprite, costume, f"draw {shape}", fn)


@action(G)
def elements(ctx: Ctx, costume: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """List the drawing's elements (with ids, bounding boxes, styles; groups nested) and canvas size/centre."""
    s = ctx.session(project)
    t = ctx.target(s.project, s, sprite)
    _, entry = _find_costume(t, costume)
    doc = VectorDoc(_svg_of(s.assets, entry))
    w, h = doc.size
    return {"costume": entry["name"], "canvas": {"width": w, "height": h}, "center": [entry["rotationCenterX"], entry["rotationCenterY"]],
            "elements": [doc.describe(c) for c in doc.drawable_children()]}


@action(G)
def transform(ctx: Ctx, id: str, costume: str | int | None = None, sprite: str | None = None, project: str | None = None,
              move_x: float = 0, move_y: float = 0, scale: float | None = None, scale_x: float | None = None,
              scale_y: float | None = None, width: float | None = None, height: float | None = None,
              rotate: float | None = None, flip: str | None = None, skew_x: float | None = None,
              skew_y: float | None = None, position_x: float | None = None, position_y: float | None = None,
              anchor: str = "top-left") -> dict:
    """Move / resize / rotate / flip / skew an element or group (select = reference by id). Scale, rotate, flip and skew act around the element's own centre.

    Args:
        id: element id.
        move_x: shift right by this many pixels.
        scale: uniform scale factor (2 = twice as big).
        width: resize to this width in pixels (keeps aspect unless height also given).
        rotate: degrees clockwise.
        flip: 'horizontal' or 'vertical'.
        position_x: move so the element's anchor point is at this x.
        anchor: which point position_x/position_y refer to: top-left, center, top-right, bottom-left, bottom-right.
    """
    def fn(doc: VectorDoc, entry):
        el = doc.find(id)
        if width or height:
            doc.resize_to(el, width, height, keep_aspect=not (width and height))
        if scale is not None or scale_x is not None or scale_y is not None or rotate or flip or skew_x or skew_y:
            doc.transform(el, scale_x=scale if scale is not None else scale_x,
                          scale_y=scale if scale is not None else scale_y, rotate=rotate, flip=flip, skew_x=skew_x, skew_y=skew_y)
        if move_x or move_y:
            doc.transform(el, dx=move_x, dy=move_y)
        if position_x is not None or position_y is not None:
            b = bbox_in_parent(el)
            if b is None:
                raise VectorError("No bounds.")
            doc.move_to(el, position_x if position_x is not None else b[0], position_y if position_y is not None else b[1], anchor)
        return {"element": doc.describe(el)}

    return vec_edit(ctx, project, sprite, costume, "transform element", fn)


@action(G)
def set_style(ctx: Ctx, id: str, costume: str | int | None = None, sprite: str | None = None, project: str | None = None,
              fill: str | None = None, stroke: str | None = None, stroke_width: float | None = None,
              opacity: float | None = None, fill_opacity: float | None = None, stroke_opacity: float | None = None,
              linecap: str | None = None, linejoin: str | None = None, dash: str | None = None) -> dict:
    """Change fill / outline colour and width, opacity, line caps/joins, dashes (groups apply to every shape inside)."""
    style = {k: v for k, v in dict(fill=fill, stroke=stroke, stroke_width=stroke_width, opacity=opacity, fill_opacity=fill_opacity,
                                   stroke_opacity=stroke_opacity, linecap=linecap, linejoin=linejoin, dash=dash).items() if v is not None}
    if not style:
        raise WorkspaceError("Nothing to change: pass at least one style.")

    def fn(doc: VectorDoc, entry):
        el = doc.find(id)
        doc.apply_style(el, style)
        return {"element": doc.describe(el)}

    return vec_edit(ctx, project, sprite, costume, "set style", fn)


@action(G)
def group(ctx: Ctx, ids: list[str], costume: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Group several elements (they must share a parent) so they move/transform together."""
    return vec_edit(ctx, project, sprite, costume, "group", lambda doc, e: {"group_id": doc.group(ids).get("id")})


@action(G)
def ungroup(ctx: Ctx, id: str, costume: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Dissolve a group; its children keep their look and position."""
    return vec_edit(ctx, project, sprite, costume, "ungroup", lambda doc, e: {"children": doc.ungroup(doc.find(id))})


@action(G)
def layer(ctx: Ctx, id: str, mode: str, steps: int = 1, costume: str | int | None = None, sprite: str | None = None,
          project: str | None = None) -> dict:
    """Change an element's z-order: mode = front | back | forward | backward (by steps)."""
    def fn(doc: VectorDoc, entry):
        doc.reorder(doc.find(id), mode, steps)
        return {"order": [c.get("id") for c in doc.drawable_children()]}

    return vec_edit(ctx, project, sprite, costume, f"layer {mode}", fn)


@action(G)
def delete_elements(ctx: Ctx, ids: list[str], costume: str | int | None = None, sprite: str | None = None,
                    project: str | None = None) -> dict:
    """Delete elements by id."""
    def fn(doc: VectorDoc, entry):
        for i in ids:
            doc.delete(doc.find(i))
        return {"deleted": ids}

    return vec_edit(ctx, project, sprite, costume, "delete elements", fn)


@action(G)
def edit_text(ctx: Ctx, id: str, text: str | None = None, font_size: float | None = None, font_family: str | None = None,
              bold: bool | None = None, anchor: str | None = None, costume: str | int | None = None,
              sprite: str | None = None, project: str | None = None) -> dict:
    """Change a text element's content, size, font (Sans Serif, Serif, Handwriting, Marker, Curly, Pixel, Scratch), weight, alignment."""
    def fn(doc: VectorDoc, entry):
        el = doc.find(id)
        if tag(el) != "text":
            raise VectorError("Not a text element.")
        if text is not None:
            for c in list(el):
                el.remove(c)
            el.text = text
        if font_size is not None:
            el.set("font-size", fnum(font_size))
        if font_family is not None:
            el.set("font-family", font_family)
        if bold is not None:
            el.set("font-weight", "bold" if bold else "normal")
        if anchor in ("start", "middle", "end"):
            el.set("text-anchor", anchor)
        return {"element": doc.describe(el)}

    return vec_edit(ctx, project, sprite, costume, "edit text", fn)


@action(G)
def path_nodes(ctx: Ctx, id: str, costume: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """List a path's nodes (index, command, anchor point and Bezier handles) for node editing."""
    s = ctx.session(project)
    t = ctx.target(s.project, s, sprite)
    _, entry = _find_costume(t, costume)
    doc = VectorDoc(_svg_of(s.assets, entry))
    try:
        return {"nodes": doc.path_nodes(doc.find(id))}
    except VectorError as exc:
        raise WorkspaceError(str(exc)) from exc


@action(G)
def path_edit(ctx: Ctx, id: str, index: int, x: float, y: float, move_handles: bool = True, costume: str | int | None = None,
              sprite: str | None = None, project: str | None = None) -> dict:
    """Move one path node's anchor to (x, y); its curve handles follow when move_handles is true."""
    def fn(doc: VectorDoc, entry):
        el = doc.find(id)
        doc.path_edit(el, index, x, y, move_handles)
        return {"d": el.get("d")}

    return vec_edit(ctx, project, sprite, costume, "edit path node", fn)


@action(G)
def path_add(ctx: Ctx, id: str, after_index: int, x: float, y: float, costume: str | int | None = None,
             sprite: str | None = None, project: str | None = None) -> dict:
    """Insert a straight-line node after node `after_index`."""
    def fn(doc: VectorDoc, entry):
        el = doc.find(id)
        doc.path_add(el, after_index, x, y)
        return {"d": el.get("d")}

    return vec_edit(ctx, project, sprite, costume, "add path node", fn)


@action(G)
def path_delete(ctx: Ctx, id: str, index: int, costume: str | int | None = None, sprite: str | None = None,
                project: str | None = None) -> dict:
    """Delete a path node."""
    def fn(doc: VectorDoc, entry):
        el = doc.find(id)
        doc.path_delete(el, index)
        return {"d": el.get("d")}

    return vec_edit(ctx, project, sprite, costume, "delete path node", fn)


@action(G)
def copy(ctx: Ctx, ids: list[str], costume: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Copy elements to the clipboard (including gradients they use). Paste into any costume with 'paste'."""
    s = ctx.session(project)
    t = ctx.target(s.project, s, sprite)
    _, entry = _find_costume(t, costume)
    doc = VectorDoc(_svg_of(s.assets, entry))
    try:
        ctx.clipboard = doc.export_elements(ids)
    except VectorError as exc:
        raise WorkspaceError(str(exc)) from exc
    return {"copied": len(ctx.clipboard)}


@action(G)
def paste(ctx: Ctx, costume: str | int | None = None, sprite: str | None = None, project: str | None = None,
          offset_x: float = 10, offset_y: float = 10) -> dict:
    """Paste the clipboard into a vector costume (works across costumes and sprites)."""
    if not ctx.clipboard:
        raise WorkspaceError("The clipboard is empty. Use costume_manager copy first.")
    return vec_edit(ctx, project, sprite, costume, "paste elements",
                    lambda doc, e: {"pasted_ids": doc.paste_elements(ctx.clipboard, offset_x, offset_y)})


@action(G)
def clear(ctx: Ctx, costume: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Erase all artwork (keeps canvas size and rotation centre)."""
    def fn(doc: VectorDoc, entry):
        for c in list(doc.root):
            if tag(c) in SHAPES:
                doc.root.remove(c)
        return {"cleared": True}

    return vec_edit(ctx, project, sprite, costume, "clear costume", fn)


@action(G)
def set_canvas(ctx: Ctx, width: float, height: float, costume: str | int | None = None, sprite: str | None = None,
               project: str | None = None) -> dict:
    """Resize the canvas (artwork stays where it is, top-left anchored)."""
    def fn(doc: VectorDoc, entry):
        doc.set_canvas(width, height)
        return {"canvas": [width, height]}

    return vec_edit(ctx, project, sprite, costume, "resize canvas", fn)


@action(G)
def crop(ctx: Ctx, padding: float = 0, costume: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Shrink the canvas to the artwork's bounds (rotation centre keeps pointing at the same spot of the art)."""
    def fn(doc: VectorDoc, entry):
        dx, dy = doc.crop_to_content(padding)
        entry["rotationCenterX"] = round(entry["rotationCenterX"] + dx, 2)
        entry["rotationCenterY"] = round(entry["rotationCenterY"] + dy, 2)
        w, h = doc.size
        return {"canvas": [w, h], "center": [entry["rotationCenterX"], entry["rotationCenterY"]]}

    return vec_edit(ctx, project, sprite, costume, "crop costume", fn)


@action(G)
def replace_svg(ctx: Ctx, svg: str, costume: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Replace a costume's whole SVG (checked). Use for edits the other actions can't express."""
    session = ctx.session(project)
    with ctx.store.edit(project, "replace svg") as h:
        t = ctx.target(h.project, session, sprite)
        _, entry = _find_costume(t, costume)
        try:
            _set_svg(h, entry, svg)
        except editing.EditError as exc:
            raise WorkspaceError(str(exc)) from exc
    return {"replaced": entry["name"]}


# ---------------------------------------------------------------- vector <-> bitmap

@action(G)
async def to_bitmap(ctx: Ctx, costume: str | int | None = None, bitmap_resolution: int = 2, sprite: str | None = None,
              project: str | None = None) -> dict:
    """Convert a vector costume to a PNG bitmap (rasterized in the headless browser at the given resolution)."""
    if bitmap_resolution not in (1, 2):
        raise WorkspaceError("bitmap_resolution must be 1 or 2.")
    session = ctx.session(project)
    with ctx.store.edit(project, "convert to bitmap") as h:
        t = ctx.target(h.project, session, sprite)
        _, entry = _find_costume(t, costume)
        svg = _svg_of(h.assets, entry)
        w, hh = VectorDoc(svg).size
        png = await ctx.browser.rasterize_svg(svg, int(w) or 1, int(hh) or 1, float(bitmap_resolution))
        md5 = editing.md5_of(png)
        h.assets[f"{md5}.png"] = png
        cx, cy = entry["rotationCenterX"], entry["rotationCenterY"]
        entry.update(assetId=md5, md5ext=f"{md5}.png", dataFormat="png", bitmapResolution=bitmap_resolution,
                     rotationCenterX=cx * bitmap_resolution, rotationCenterY=cy * bitmap_resolution)
        editing.prune_unused_assets(h.project, h.assets)
    return {"costume": entry["name"], "format": "png", "pixels": [int(w * bitmap_resolution), int(hh * bitmap_resolution)]}


@action(G)
def to_vector(ctx: Ctx, costume: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Convert a bitmap costume to vector form by wrapping the image in an SVG (the pixels are embedded, not traced) so shapes/text can be drawn over it; convert back with to_bitmap."""
    session = ctx.session(project)
    with ctx.store.edit(project, "convert to vector") as h:
        t = ctx.target(h.project, session, sprite)
        _, entry = _find_costume(t, costume)
        if entry["dataFormat"] == "svg":
            raise WorkspaceError("Already a vector costume.")
        data = h.assets[entry["md5ext"]]
        _, pw, ph = editing.image_info(data)
        res = entry.get("bitmapResolution", 1) or 1
        w, hh = pw / res, ph / res
        mime = "image/png" if entry["dataFormat"] == "png" else "image/jpeg"
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{fnum(w)}" height="{fnum(hh)}" '
               f'viewBox="0 0 {fnum(w)} {fnum(hh)}"><image id="bitmap" x="0" y="0" width="{fnum(w)}" height="{fnum(hh)}" '
               f'href="data:{mime};base64,{base64.b64encode(data).decode()}"/></svg>')
        cx, cy = entry["rotationCenterX"] / res, entry["rotationCenterY"] / res
        entry.pop("bitmapResolution", None)
        _set_svg(h, entry, svg)
        entry.update(rotationCenterX=cx, rotationCenterY=cy, bitmapResolution=1)
    return {"costume": entry["name"], "format": "svg", "note": "pixels embedded as an <image> element with id 'bitmap'"}
