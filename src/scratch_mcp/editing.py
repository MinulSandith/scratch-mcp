"""Adding and removing sprites, costumes, backdrops and sounds in a project dict."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import re
import wave
import xml.etree.ElementTree as ET
from typing import Any

MAX_ASSET_BYTES = 8 * 1024 * 1024
BLANK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2" viewBox="0 0 2 2"></svg>'

_FORBIDDEN_TAGS = {"script", "foreignobject", "iframe", "object", "embed", "audio", "video", "style"}
_NUM = re.compile(r"^\s*([0-9]*\.?[0-9]+)")


class EditError(ValueError):
    """User-facing problem with an edit request."""


def md5_of(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def check_svg(svg: str) -> tuple[float, float]:
    """Validate an SVG costume and return its (width, height) in Scratch pixels."""
    if not isinstance(svg, str) or not svg.strip():
        raise EditError("svg is empty.")
    if len(svg.encode("utf-8")) > MAX_ASSET_BYTES:
        raise EditError("svg is too large (max 8 MB).")
    if "<!DOCTYPE" in svg or "<!ENTITY" in svg:
        raise EditError("svg must not contain a DOCTYPE or entities.")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise EditError(f"svg is not well-formed XML: {exc}") from exc
    if _local(root.tag) != "svg":
        raise EditError("The root element must be <svg>.")
    for el in root.iter():
        if _local(el.tag) in _FORBIDDEN_TAGS:
            raise EditError(f"<{_local(el.tag)}> is not allowed in a costume (Scratch SVGs must be plain shapes).")
        for name, value in el.attrib.items():
            lname = _local(name)
            if lname.startswith("on"):
                raise EditError(f"Event attribute '{name}' is not allowed in an svg.")
            if lname == "href" and not value.startswith("#") and not value.startswith("data:image/"):
                raise EditError("External references are not allowed in an svg (use #id or data:image URIs).")
    width, height = _size(root)
    if width <= 0 or height <= 0:
        raise EditError("svg needs a width/height or a viewBox, e.g. viewBox=\"0 0 100 100\".")
    return width, height


def _size(root: ET.Element) -> tuple[float, float]:
    def px(value: str | None) -> float | None:
        if not value or value.strip().endswith("%"):
            return None
        m = _NUM.match(value)
        return float(m.group(1)) if m else None

    w, h = px(root.get("width")), px(root.get("height"))
    vb = root.get("viewBox")
    if vb:
        parts = [p for p in re.split(r"[\s,]+", vb.strip()) if p]
        if len(parts) == 4:
            try:
                vw, vh = float(parts[2]), float(parts[3])
            except ValueError:
                vw = vh = 0.0
            if vw > 0 and vh > 0:
                w = w if w else vw
                h = h if h else vh
    return (w or 0.0), (h or 0.0)


def check_wav(data: bytes) -> tuple[int, int]:
    """Validate a PCM WAV and return (sample rate, sample count)."""
    if len(data) > MAX_ASSET_BYTES:
        raise EditError("WAV is too large (max 8 MB).")
    try:
        with wave.open(io.BytesIO(data)) as w:
            if w.getcomptype() != "NONE":
                raise EditError("Only uncompressed PCM WAV files are supported.")
            return w.getframerate(), w.getnframes()
    except wave.Error as exc:
        raise EditError(f"Not a valid PCM WAV file: {exc}") from exc
    except EOFError as exc:
        raise EditError("The WAV file is truncated.") from exc


def decode_base64(text: str, what: str) -> bytes:
    try:
        return base64.b64decode(text, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise EditError(f"{what} is not valid base64.") from exc


# ---------------------------------------------------------------------------


def find_target(project: dict[str, Any], name: str) -> dict[str, Any]:
    targets = project.get("targets") or []
    if name.strip().lower() == "stage":
        for t in targets:
            if t.get("isStage"):
                return t
    for t in targets:
        if t.get("name") == name:
            return t
    for t in targets:
        if str(t.get("name", "")).lower() == name.strip().lower():
            return t
    raise EditError(f"No sprite named '{name}'. Available: {', '.join(str(t.get('name')) for t in targets)}")


def _unique(name: str, taken: list[str]) -> str:
    if name not in taken:
        return name
    m = re.match(r"^(.*?)(\d+)$", name)
    base, n = (m.group(1), int(m.group(2)) + 1) if m else (name, 2)
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def add_costume(
    project: dict[str, Any], assets: dict[str, bytes], target: dict[str, Any], name: str, svg: str,
    center: tuple[float | None, float | None] = (None, None),
) -> dict[str, Any]:
    width, height = check_svg(svg)
    name = (name or "").strip()
    if not name:
        raise EditError("costume name is empty.")
    data = svg.encode("utf-8")
    md5 = md5_of(data)
    cx = width / 2 if center[0] is None else center[0]
    cy = height / 2 if center[1] is None else center[1]
    costumes = target.setdefault("costumes", [])
    final = _unique(name, [c.get("name", "") for c in costumes])
    entry: dict[str, Any] = {"name": final, "dataFormat": "svg", "assetId": md5, "md5ext": f"{md5}.svg",
                             "rotationCenterX": round(cx, 2), "rotationCenterY": round(cy, 2),
                             "bitmapResolution": 1}
    costumes.append(entry)
    assets[f"{md5}.svg"] = data
    return entry


def add_sound(
    assets: dict[str, bytes], target: dict[str, Any], name: str, wav: bytes
) -> dict[str, Any]:
    rate, count = check_wav(wav)
    name = (name or "").strip()
    if not name:
        raise EditError("sound name is empty.")
    md5 = md5_of(wav)
    sounds = target.setdefault("sounds", [])
    final = _unique(name, [s.get("name", "") for s in sounds])
    entry = {"name": final, "assetId": md5, "dataFormat": "wav", "format": "",
             "rate": rate, "sampleCount": count, "md5ext": f"{md5}.wav"}
    sounds.append(entry)
    assets[f"{md5}.wav"] = wav
    return entry


def new_sprite(
    project: dict[str, Any], name: str, x: float = 0, y: float = 0, size: float = 100,
    direction: float = 90, visible: bool = True,
) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise EditError("sprite name is empty.")
    if name.lower() == "stage":
        raise EditError("A sprite can't be called 'Stage'.")
    if any(str(t.get("name", "")).lower() == name.lower() for t in project["targets"]):
        raise EditError(f"A sprite named '{name}' already exists.")
    layer = max((t.get("layerOrder", 0) for t in project["targets"]), default=0) + 1
    sprite = {
        "isStage": False, "name": name, "variables": {}, "lists": {}, "broadcasts": {}, "blocks": {},
        "comments": {}, "currentCostume": 0, "costumes": [], "sounds": [], "volume": 100,
        "layerOrder": layer, "visible": bool(visible), "x": x, "y": y, "size": size,
        "direction": direction, "draggable": False, "rotationStyle": "all around",
    }
    project["targets"].append(sprite)
    return sprite


def prune_unused_assets(project: dict[str, Any], assets: dict[str, bytes]) -> list[str]:
    used = {a.get("md5ext") or f"{a.get('assetId')}.{a.get('dataFormat')}"
            for t in project["targets"] for key in ("costumes", "sounds") for a in t.get(key) or []}
    removed = [n for n in assets if n not in used]
    for n in removed:
        del assets[n]
    return removed
