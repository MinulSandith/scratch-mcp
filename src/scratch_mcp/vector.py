"""SVG costume editor: an element-level document model (draw, select, transform, group, layers, paths).

Scratch costumes are plain SVG files, so "the Scratch vector editor" is implemented as operations on the
SVG tree. Coordinates are costume pixels with the origin at the top-left (the rotation centre uses the same
coordinates). Every drawable element gets a stable ``id`` that the other operations refer to.
"""

from __future__ import annotations

import copy
import math
import re
import xml.etree.ElementTree as ET
from typing import Any

from .workspace import WorkspaceError

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

SHAPES = {"rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "text", "image", "g"}
CONTAINERS = {"g", "svg"}
SKIP = {"defs", "style", "title", "desc", "metadata", "clippath", "mask", "lineargradient", "radialgradient", "filter", "pattern", "symbol"}
_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

Matrix = tuple[float, float, float, float, float, float]  # a b c d e f
IDENTITY: Matrix = (1, 0, 0, 1, 0, 0)


class VectorError(WorkspaceError):
    """User-facing problem with a vector edit."""


def tag(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""


def q(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def fnum(v: float) -> str:
    v = round(float(v), 3)
    return str(int(v)) if v == int(v) else repr(v)


# ---------------------------------------------------------------------------
# matrices
# ---------------------------------------------------------------------------

def mmul(m: Matrix, n: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + e, b * E + d * F + f)


def apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def parse_transform(text: str | None) -> Matrix:
    m = IDENTITY
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text or ""):
        v = [float(x) for x in _NUM.findall(args)]
        name = name.lower()
        if name == "translate":
            t: Matrix = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate":
            r = math.radians(v[0])
            c, s = math.cos(r), math.sin(r)
            t = (c, s, -s, c, 0, 0)
            if len(v) >= 3:
                t = mmul(mmul((1, 0, 0, 1, v[1], v[2]), t), (1, 0, 0, 1, -v[1], -v[2]))
        elif name == "skewx":
            t = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == "skewy":
            t = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        elif name == "matrix" and len(v) == 6:
            t = tuple(v)  # type: ignore[assignment]
        else:
            continue
        m = mmul(m, t)
    return m


def matrix_text(m: Matrix) -> str:
    return "matrix(" + " ".join(fnum(x) for x in m) + ")"


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

def parse_path(d: str) -> list[dict[str, Any]]:
    """Path data -> list of segments with ABSOLUTE coordinates: M/L/C/Q/A/Z ('S','T','H','V' and relative forms are expanded)."""
    tokens = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", d or "")
    segs: list[dict[str, Any]] = []
    i, cx, cy, sx, sy = 0, 0.0, 0.0, 0.0, 0.0
    cmd = ""
    last_ctrl: tuple[str, float, float] | None = None
    counts = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}

    def take(n: int) -> list[float]:
        nonlocal i
        if i + n > len(tokens) or any(t.isalpha() for t in tokens[i:i + n]):
            raise VectorError(f"Malformed path data near '{' '.join(tokens[i:i + 3])}'.")
        vals = [float(t) for t in tokens[i:i + n]]
        i += n
        return vals

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
        elif not cmd:
            raise VectorError("Path data must start with a command letter (M, L, C, ...).")
        up, rel = cmd.upper(), cmd.islower()
        if up == "Z":
            segs.append({"cmd": "Z", "pts": []})
            cx, cy = sx, sy
            last_ctrl = None
            continue
        v = take(counts[up])
        ox, oy = (cx, cy) if rel else (0.0, 0.0)
        if up == "M":
            cx, cy = v[0] + ox, v[1] + oy
            sx, sy = cx, cy
            segs.append({"cmd": "M", "pts": [[cx, cy]]})
            cmd = "l" if rel else "L"
            last_ctrl = None
        elif up == "L":
            cx, cy = v[0] + ox, v[1] + oy
            segs.append({"cmd": "L", "pts": [[cx, cy]]})
            last_ctrl = None
        elif up == "H":
            cx = v[0] + (cx if rel else 0)
            segs.append({"cmd": "L", "pts": [[cx, cy]]})
            last_ctrl = None
        elif up == "V":
            cy = v[0] + (cy if rel else 0)
            segs.append({"cmd": "L", "pts": [[cx, cy]]})
            last_ctrl = None
        elif up == "C":
            p = [[v[0] + ox, v[1] + oy], [v[2] + ox, v[3] + oy], [v[4] + ox, v[5] + oy]]
            segs.append({"cmd": "C", "pts": p})
            cx, cy = p[2]
            last_ctrl = ("C", *p[1])
        elif up == "S":
            c1 = (2 * cx - last_ctrl[1], 2 * cy - last_ctrl[2]) if last_ctrl and last_ctrl[0] == "C" else (cx, cy)
            p = [list(c1), [v[0] + ox, v[1] + oy], [v[2] + ox, v[3] + oy]]
            segs.append({"cmd": "C", "pts": p})
            cx, cy = p[2]
            last_ctrl = ("C", *p[1])
        elif up == "Q":
            p = [[v[0] + ox, v[1] + oy], [v[2] + ox, v[3] + oy]]
            segs.append({"cmd": "Q", "pts": p})
            cx, cy = p[1]
            last_ctrl = ("Q", *p[0])
        elif up == "T":
            c1 = (2 * cx - last_ctrl[1], 2 * cy - last_ctrl[2]) if last_ctrl and last_ctrl[0] == "Q" else (cx, cy)
            p = [list(c1), [v[0] + ox, v[1] + oy]]
            segs.append({"cmd": "Q", "pts": p})
            cx, cy = p[1]
            last_ctrl = ("Q", *p[0])
        elif up == "A":
            cx, cy = v[5] + ox, v[6] + oy
            segs.append({"cmd": "A", "pts": [[cx, cy]], "arc": v[:5]})
            last_ctrl = None
    return segs


def path_text(segs: list[dict[str, Any]]) -> str:
    out = []
    for s in segs:
        c = s["cmd"]
        if c == "Z":
            out.append("Z")
        elif c == "A":
            out.append("A " + " ".join(fnum(x) for x in s["arc"]) + f" {fnum(s['pts'][0][0])} {fnum(s['pts'][0][1])}")
        else:
            out.append(c + " " + " ".join(f"{fnum(p[0])} {fnum(p[1])}" for p in s["pts"]))
    return " ".join(out)


def _bez(p0, p1, p2, p3, n=24):
    for k in range(n + 1):
        t = k / n
        u = 1 - t
        yield (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
               u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])


def path_points(d: str) -> list[tuple[float, float]]:
    """Points that bound the path (curves are sampled)."""
    pts: list[tuple[float, float]] = []
    cur: tuple[float, float] | None = None
    start = None
    for s in parse_path(d):
        c = s["cmd"]
        if c == "M":
            cur = tuple(s["pts"][0])  # type: ignore[assignment]
            start = cur
            pts.append(cur)
        elif c == "L" and cur:
            cur = tuple(s["pts"][0])  # type: ignore[assignment]
            pts.append(cur)
        elif c == "C" and cur:
            pts.extend(_bez(cur, *s["pts"]))
            cur = tuple(s["pts"][2])  # type: ignore[assignment]
        elif c == "Q" and cur:
            p1, p2 = s["pts"]
            c1 = (cur[0] + 2 / 3 * (p1[0] - cur[0]), cur[1] + 2 / 3 * (p1[1] - cur[1]))
            c2 = (p2[0] + 2 / 3 * (p1[0] - p2[0]), p2[1] + 2 / 3 * (p1[1] - p2[1]))
            pts.extend(_bez(cur, c1, c2, p2))
            cur = tuple(p2)  # type: ignore[assignment]
        elif c == "A" and cur:
            cur = tuple(s["pts"][0])  # type: ignore[assignment]
            pts.append(cur)
        elif c == "Z" and start:
            cur = start
    return pts


# ---------------------------------------------------------------------------
# bounding boxes
# ---------------------------------------------------------------------------

def _f(el: ET.Element, name: str, default: float = 0.0) -> float:
    m = _NUM.match(el.get(name) or "")
    return float(m.group(0)) if m else default


def local_points(el: ET.Element) -> list[tuple[float, float]]:
    t = tag(el)
    if t == "rect" or t == "image":
        x, y, w, h = _f(el, "x"), _f(el, "y"), _f(el, "width"), _f(el, "height")
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    if t == "circle":
        cx, cy, r = _f(el, "cx"), _f(el, "cy"), _f(el, "r")
        return [(cx - r, cy - r), (cx + r, cy + r)]
    if t == "ellipse":
        cx, cy, rx, ry = _f(el, "cx"), _f(el, "cy"), _f(el, "rx"), _f(el, "ry")
        return [(cx - rx, cy - ry), (cx + rx, cy + ry)]
    if t == "line":
        return [(_f(el, "x1"), _f(el, "y1")), (_f(el, "x2"), _f(el, "y2"))]
    if t in ("polyline", "polygon"):
        v = [float(x) for x in _NUM.findall(el.get("points") or "")]
        return list(zip(v[0::2], v[1::2]))
    if t == "path":
        return path_points(el.get("d") or "")
    if t == "text":
        size = _f(el, "font-size", 16)
        text = "".join(el.itertext())
        w, h = max(len(text), 1) * size * 0.55, size * 1.2
        x, y = _f(el, "x"), _f(el, "y")
        anchor = el.get("text-anchor", "start")
        x0 = x - (w / 2 if anchor == "middle" else w if anchor == "end" else 0)
        return [(x0, y - size), (x0 + w, y - size + h)]
    return []


def bbox_in_parent(el: ET.Element) -> tuple[float, float, float, float] | None:
    """Axis-aligned bounding box (x0, y0, x1, y1) of ``el`` in its parent's coordinates (own transform applied)."""
    t = tag(el)
    if t in SKIP:
        return None
    m = parse_transform(el.get("transform"))
    if t in CONTAINERS:
        boxes = [b for b in (bbox_in_parent(c) for c in el) if b]
        if not boxes:
            return None
        pts = [(b[0], b[1]) for b in boxes] + [(b[2], b[3]) for b in boxes]
        pts += [(b[0], b[3]) for b in boxes] + [(b[2], b[1]) for b in boxes]
    else:
        pts = local_points(el)
    if not pts:
        return None
    pts = [apply(m, x, y) for x, y in pts]
    sw = _f(el, "stroke-width", 1) / 2 if el.get("stroke") not in (None, "none") else 0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs) - sw, min(ys) - sw, max(xs) + sw, max(ys) + sw


# ---------------------------------------------------------------------------
# document
# ---------------------------------------------------------------------------

class VectorDoc:
    def __init__(self, svg: str):
        try:
            self.root = ET.fromstring(svg)
        except ET.ParseError as exc:
            raise VectorError(f"The costume is not valid SVG: {exc}") from exc
        if tag(self.root) != "svg":
            raise VectorError("Root element must be <svg>.")
        self._counter = 0
        self.ensure_ids()

    # -- basics ----------------------------------------------------------

    @classmethod
    def blank(cls, width: float = 100, height: float = 100, background: str | None = None) -> "VectorDoc":
        bg = f'<rect id="bg" x="0" y="0" width="{fnum(width)}" height="{fnum(height)}" fill="{background}"/>' if background else ""
        return cls(f'<svg xmlns="{SVG_NS}" width="{fnum(width)}" height="{fnum(height)}" viewBox="0 0 {fnum(width)} {fnum(height)}">{bg}</svg>')

    def to_string(self) -> str:
        return ET.tostring(self.root, encoding="unicode")

    @property
    def size(self) -> tuple[float, float]:
        w, h = _f(self.root, "width"), _f(self.root, "height")
        vb = [float(x) for x in _NUM.findall(self.root.get("viewBox") or "")]
        if len(vb) == 4:
            w, h = w or vb[2], h or vb[3]
        return w, h

    def ensure_ids(self) -> None:
        used = {e.get("id") for e in self.root.iter() if e.get("id")}
        for el in self.root.iter():
            if el is self.root or tag(el) in SKIP or (el.get("id")):
                continue
            if tag(el) in SHAPES:
                self._counter += 1
                while f"e{self._counter}" in used:
                    self._counter += 1
                el.set("id", f"e{self._counter}")
                used.add(f"e{self._counter}")

    def new_id(self) -> str:
        used = {e.get("id") for e in self.root.iter() if e.get("id")}
        self._counter += 1
        while f"e{self._counter}" in used:
            self._counter += 1
        return f"e{self._counter}"

    def find(self, eid: str) -> ET.Element:
        for el in self.root.iter():
            if el.get("id") == eid and el is not self.root:
                return el
        raise VectorError(f"No element '{eid}' in this costume. Use costume_manager elements to list ids.")

    def parent_of(self, el: ET.Element) -> ET.Element:
        for p in self.root.iter():
            for c in p:
                if c is el:
                    return p
        raise VectorError("Element has no parent.")

    def drawable_children(self, parent: ET.Element | None = None):
        return [c for c in (parent if parent is not None else self.root) if tag(c) in SHAPES]

    # -- listing ---------------------------------------------------------

    def describe(self, el: ET.Element, depth: int = 0, max_depth: int = 6) -> dict[str, Any]:
        b = bbox_in_parent(el)
        info: dict[str, Any] = {"id": el.get("id"), "type": tag(el)}
        if b:
            info["bbox"] = {"x": round(b[0], 2), "y": round(b[1], 2), "width": round(b[2] - b[0], 2), "height": round(b[3] - b[1], 2)}
        for a in ("fill", "stroke", "stroke-width", "opacity", "transform"):
            if el.get(a):
                info[a] = el.get(a)
        if tag(el) == "text":
            info["text"] = "".join(el.itertext())
        if tag(el) == "path":
            info["d"] = (el.get("d") or "")[:200]
        if tag(el) == "g" and depth < max_depth:
            info["children"] = [self.describe(c, depth + 1, max_depth) for c in self.drawable_children(el)]
        return info

    def content_bbox(self) -> tuple[float, float, float, float] | None:
        boxes = [b for b in (bbox_in_parent(c) for c in self.drawable_children()) if b]
        if not boxes:
            return None
        return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)

    # -- drawing -----------------------------------------------------------

    def add_shape(self, shape: str, a: dict[str, Any], style: dict[str, Any], parent: ET.Element | None = None) -> ET.Element:
        shape = shape.lower()
        el = ET.Element(q(shape if shape not in ("curve", "star", "arrow", "triangle") else "path"))
        req = {"rect": ("x", "y", "width", "height"), "circle": ("cx", "cy", "r"), "ellipse": ("cx", "cy", "rx", "ry"),
               "line": ("x1", "y1", "x2", "y2")}
        if shape in req:
            for k in req[shape]:
                if k not in a:
                    raise VectorError(f"'{shape}' needs {', '.join(req[shape])}; missing '{k}'.")
                el.set(k, fnum(a[k]))
            if shape == "rect" and a.get("rx") is not None:
                el.set("rx", fnum(a["rx"]))
        elif shape in ("polyline", "polygon"):
            pts = a.get("points")
            if not pts or len(pts) < 2:
                raise VectorError(f"'{shape}' needs points: [[x,y], [x,y], ...].")
            el.set("points", " ".join(f"{fnum(p[0])},{fnum(p[1])}" for p in pts))
        elif shape == "path":
            if not a.get("d"):
                raise VectorError("'path' needs d (SVG path data).")
            parse_path(a["d"])  # validate
            el.set("d", a["d"])
        elif shape == "curve":
            pts = a.get("points")
            if not pts or len(pts) not in (3, 4):
                raise VectorError("'curve' needs points: 3 (quadratic) or 4 (cubic) [x,y] pairs: start, control(s), end.")
            letter = "Q" if len(pts) == 3 else "C"
            el.set("d", f"M {fnum(pts[0][0])} {fnum(pts[0][1])} {letter} " + " ".join(f"{fnum(p[0])} {fnum(p[1])}" for p in pts[1:]))
            style.setdefault("fill", "none")
        elif shape == "star":
            cx, cy, r = a.get("cx"), a.get("cy"), a.get("r")
            if None in (cx, cy, r):
                raise VectorError("'star' needs cx, cy, r (outer radius); optional spikes, inner_ratio.")
            n = int(a.get("spikes", 5))
            inner = float(a.get("inner_ratio", 0.45)) * r
            pts = []
            for k in range(n * 2):
                ang = -math.pi / 2 + k * math.pi / n
                rr = r if k % 2 == 0 else inner
                pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
            el.set("d", "M " + " L ".join(f"{fnum(x)} {fnum(y)}" for x, y in pts) + " Z")
        elif shape == "triangle":
            pts = a.get("points")
            if not pts or len(pts) != 3:
                raise VectorError("'triangle' needs points: three [x,y] pairs.")
            el.set("d", "M " + " L ".join(f"{fnum(x)} {fnum(y)}" for x, y in pts) + " Z")
        elif shape == "text":
            if not a.get("text"):
                raise VectorError("'text' needs the text to draw.")
            el.set("x", fnum(a.get("x", 0)))
            el.set("y", fnum(a.get("y", 0)))
            el.set("font-size", fnum(a.get("font_size", 24)))
            el.set("font-family", a.get("font_family", "Sans Serif"))
            if a.get("bold"):
                el.set("font-weight", "bold")
            if a.get("anchor") in ("start", "middle", "end"):
                el.set("text-anchor", a["anchor"])
            el.text = str(a["text"])
            style.setdefault("fill", "#000000")
        else:
            raise VectorError(f"Unknown shape '{shape}'. Shapes: rect, circle, ellipse, line, polyline, polygon, path, curve, "
                              "triangle, star, text.")
        if shape in ("line", "polyline", "curve") and "stroke" not in style:
            style["stroke"] = "#000000"
        self.apply_style(el, style)
        el.set("id", self.new_id())
        (parent if parent is not None else self.root).append(el)
        return el

    def apply_style(self, el: ET.Element, style: dict[str, Any]) -> None:
        mapping = {"fill": "fill", "stroke": "stroke", "stroke_width": "stroke-width", "opacity": "opacity",
                   "fill_opacity": "fill-opacity", "stroke_opacity": "stroke-opacity", "linecap": "stroke-linecap",
                   "linejoin": "stroke-linejoin", "dash": "stroke-dasharray"}
        targets = [el] if tag(el) != "g" else [e for e in el.iter() if tag(e) in SHAPES - {"g"}]
        for k, v in style.items():
            if v is None:
                continue
            if k not in mapping:
                raise VectorError(f"Unknown style '{k}'. Styles: {', '.join(mapping)}.")
            for t in targets:
                if k == "opacity" and tag(el) == "g":
                    el.set("opacity", str(v))
                else:
                    t.set(mapping[k], fnum(v) if isinstance(v, (int, float)) else str(v))
        if "fill" in style or "stroke" in style:
            for t in targets:
                t.attrib.pop("style", None)

    # -- transforms --------------------------------------------------------

    def center_of(self, el: ET.Element) -> tuple[float, float]:
        b = bbox_in_parent(el)
        if b is None:
            raise VectorError("This element has no visible bounds.")
        return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2

    def transform(self, el: ET.Element, *, dx: float = 0, dy: float = 0, scale_x: float | None = None,
                  scale_y: float | None = None, rotate: float | None = None, flip: str | None = None,
                  skew_x: float | None = None, skew_y: float | None = None) -> None:
        """Apply (in the order: scale/flip, rotate, skew, move) around the element's own centre."""
        cx, cy = self.center_of(el)
        m = IDENTITY
        sx = 1.0 if scale_x is None else scale_x
        sy = (sx if scale_y is None and scale_x is not None else (1.0 if scale_y is None else scale_y))
        if flip == "horizontal":
            sx = -sx
        elif flip == "vertical":
            sy = -sy
        elif flip not in (None, ""):
            raise VectorError("flip must be 'horizontal' or 'vertical'.")
        if sx == 0 or sy == 0:
            raise VectorError("Scale can't be zero.")

        def about(t: Matrix) -> Matrix:
            return mmul(mmul((1, 0, 0, 1, cx, cy), t), (1, 0, 0, 1, -cx, -cy))

        if sx != 1 or sy != 1:
            m = mmul(about((sx, 0, 0, sy, 0, 0)), m)
        if rotate:
            r = math.radians(rotate)
            m = mmul(about((math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)), m)
        if skew_x:
            m = mmul(about((1, 0, math.tan(math.radians(skew_x)), 1, 0, 0)), m)
        if skew_y:
            m = mmul(about((1, math.tan(math.radians(skew_y)), 0, 1, 0, 0)), m)
        if dx or dy:
            m = mmul((1, 0, 0, 1, dx, dy), m)
        if m == IDENTITY:
            return
        el.set("transform", matrix_text(mmul(m, parse_transform(el.get("transform")))))

    def move_to(self, el: ET.Element, x: float, y: float, anchor: str = "top-left") -> None:
        b = bbox_in_parent(el)
        if b is None:
            raise VectorError("This element has no visible bounds.")
        ax = {"top-left": b[0], "center": (b[0] + b[2]) / 2, "top-right": b[2], "bottom-left": b[0], "bottom-right": b[2]}
        ay = {"top-left": b[1], "center": (b[1] + b[3]) / 2, "top-right": b[1], "bottom-left": b[3], "bottom-right": b[3]}
        if anchor not in ax:
            raise VectorError(f"anchor must be one of {list(ax)}.")
        self.transform(el, dx=x - ax[anchor], dy=y - ay[anchor])

    def resize_to(self, el: ET.Element, width: float | None, height: float | None, keep_aspect: bool = True) -> None:
        b = bbox_in_parent(el)
        if b is None:
            raise VectorError("This element has no visible bounds.")
        w, h = max(b[2] - b[0], 1e-6), max(b[3] - b[1], 1e-6)
        sx = (width / w) if width else None
        sy = (height / h) if height else None
        if keep_aspect and sx and not sy:
            sy = sx
        if keep_aspect and sy and not sx:
            sx = sy
        self.transform(el, scale_x=sx or 1, scale_y=sy or 1)

    # -- structure ---------------------------------------------------------

    def group(self, ids: list[str]) -> ET.Element:
        if len(ids) < 2:
            raise VectorError("Group needs at least two elements.")
        els = [self.find(i) for i in ids]
        parent = self.parent_of(els[0])
        order = [c for c in parent if c in els]
        if len(order) != len(els):
            raise VectorError("Elements to group must share the same parent (ungroup first).")
        index = list(parent).index(order[0])
        g = ET.Element(q("g"))
        g.set("id", self.new_id())
        for e in order:
            parent.remove(e)
            g.append(e)
        parent.insert(index, g)
        return g

    def ungroup(self, el: ET.Element) -> list[str]:
        if tag(el) != "g":
            raise VectorError("Only groups can be ungrouped.")
        parent = self.parent_of(el)
        gm = parse_transform(el.get("transform"))
        index = list(parent).index(el)
        parent.remove(el)
        ids = []
        for k, c in enumerate(list(el)):
            if tag(c) in SKIP:
                continue
            if gm != IDENTITY:
                c.set("transform", matrix_text(mmul(gm, parse_transform(c.get("transform")))))
            if el.get("opacity") and not c.get("opacity"):
                c.set("opacity", el.get("opacity"))  # type: ignore[arg-type]
            parent.insert(index + k, c)
            ids.append(c.get("id"))
        return [i for i in ids if i]

    def reorder(self, el: ET.Element, mode: str, steps: int = 1) -> None:
        parent = self.parent_of(el)
        sibs = list(parent)
        draw = [c for c in sibs if tag(c) in SHAPES]
        i = draw.index(el)
        j = {"front": len(draw) - 1, "back": 0, "forward": min(len(draw) - 1, i + steps), "backward": max(0, i - steps)}.get(mode)
        if j is None:
            raise VectorError("mode must be front, back, forward or backward.")
        draw.remove(el)
        draw.insert(j, el)
        others = [c for c in sibs if tag(c) not in SHAPES]
        for c in sibs:
            parent.remove(c)
        for c in others + draw:  # defs/styles first, then drawables in the new z-order
            parent.append(c)

    def delete(self, el: ET.Element) -> None:
        self.parent_of(el).remove(el)

    # -- clipboard -----------------------------------------------------------

    def export_elements(self, ids: list[str]) -> list[str]:
        out = []
        for i in ids:
            el = self.find(i)
            blob = ET.tostring(el, encoding="unicode")
            refs = set(re.findall(r"url\(#([^)]+)\)|href=\"#([^\"]+)\"", blob))
            defs = []
            for ref in {r for pair in refs for r in pair if r}:
                for d in self.root.iter():
                    if d.get("id") == ref and tag(d) in SKIP:
                        defs.append(ET.tostring(d, encoding="unicode"))
            out.append(blob if not defs else "<!--defs-->" + "".join(defs) + "<!--el-->" + blob)
        return out

    def paste_elements(self, blobs: list[str], dx: float = 10, dy: float = 10) -> list[str]:
        new_ids = []
        for blob in blobs:
            defs_part, _, el_part = blob.partition("<!--el-->") if blob.startswith("<!--defs-->") else ("", "", blob)
            frag = ET.fromstring(el_part or blob)
            mapping: dict[str, str] = {}
            for e in frag.iter():
                if e.get("id"):
                    mapping[e.get("id")] = self.new_id()  # type: ignore[index]
                    e.set("id", mapping[e.get("id")])  # type: ignore[index]
            if defs_part:
                defs_root = ET.fromstring("<root xmlns=\"%s\">%s</root>" % (SVG_NS, defs_part.replace("<!--defs-->", "")))
                defs_el = next((c for c in self.root if tag(c) == "defs"), None)
                if defs_el is None:
                    defs_el = ET.Element(q("defs"))
                    self.root.insert(0, defs_el)
                for d in defs_root:
                    old = d.get("id")
                    nid = f"d{self.new_id()}"
                    mapping[old] = nid  # type: ignore[index]
                    d.set("id", nid)
                    defs_el.append(d)
            text = ET.tostring(frag, encoding="unicode")
            for old, new in mapping.items():
                text = text.replace(f"url(#{old})", f"url(#{new})").replace(f'href="#{old}"', f'href="#{new}"')
            frag = ET.fromstring(text)
            self.root.append(frag)
            self.transform(frag, dx=dx, dy=dy)
            new_ids.append(frag.get("id"))
        return [i for i in new_ids if i]

    # -- paths ----------------------------------------------------------------

    def path_nodes(self, el: ET.Element) -> list[dict[str, Any]]:
        if tag(el) != "path":
            raise VectorError("Not a path. Draw shapes as 'path' (or use curve/star/triangle) to edit nodes.")
        nodes = []
        for k, s in enumerate(parse_path(el.get("d") or "")):
            if s["cmd"] == "Z":
                nodes.append({"index": k, "cmd": "Z"})
                continue
            node = {"index": k, "cmd": s["cmd"], "anchor": [round(s["pts"][-1][0], 2), round(s["pts"][-1][1], 2)]}
            if s["cmd"] in ("C", "Q"):
                node["handles"] = [[round(p[0], 2), round(p[1], 2)] for p in s["pts"][:-1]]
            nodes.append(node)
        return nodes

    def path_edit(self, el: ET.Element, index: int, x: float, y: float, handles: bool = True) -> None:
        segs = parse_path(el.get("d") or "")
        if not 0 <= index < len(segs) or segs[index]["cmd"] == "Z":
            raise VectorError(f"No path node {index}.")
        s = segs[index]
        old = s["pts"][-1]
        ddx, ddy = x - old[0], y - old[1]
        s["pts"][-1] = [x, y]
        if handles and s["cmd"] in ("C", "Q") and len(s["pts"]) >= 2 and s["cmd"] == "C":
            s["pts"][1] = [s["pts"][1][0] + ddx, s["pts"][1][1] + ddy]  # the handle that arrives at this anchor follows it
        if handles and index + 1 < len(segs) and segs[index + 1]["cmd"] == "C":
            p = segs[index + 1]["pts"][0]
            segs[index + 1]["pts"][0] = [p[0] + ddx, p[1] + ddy]
        el.set("d", path_text(segs))

    def path_add(self, el: ET.Element, after_index: int, x: float, y: float) -> None:
        segs = parse_path(el.get("d") or "")
        if not 0 <= after_index < len(segs):
            raise VectorError(f"No path node {after_index}.")
        segs.insert(after_index + 1, {"cmd": "L", "pts": [[x, y]]})
        el.set("d", path_text(segs))

    def path_delete(self, el: ET.Element, index: int) -> None:
        segs = parse_path(el.get("d") or "")
        if not 0 <= index < len(segs):
            raise VectorError(f"No path node {index}.")
        if segs[index]["cmd"] == "M":
            raise VectorError("The first node (M) can't be deleted; move it instead.")
        del segs[index]
        el.set("d", path_text(segs))

    # -- canvas -----------------------------------------------------------------

    def set_canvas(self, width: float, height: float) -> None:
        if width <= 0 or height <= 0:
            raise VectorError("Canvas width and height must be positive.")
        self.root.set("width", fnum(width))
        self.root.set("height", fnum(height))
        self.root.set("viewBox", f"0 0 {fnum(width)} {fnum(height)}")

    def crop_to_content(self, pad: float = 0) -> tuple[float, float]:
        """Shrink the canvas to the artwork; returns the (dx, dy) the artwork moved (to adjust the rotation centre)."""
        b = self.content_bbox()
        if b is None:
            raise VectorError("The costume is empty; nothing to crop to.")
        x0, y0 = b[0] - pad, b[1] - pad
        w, h = (b[2] - b[0]) + 2 * pad, (b[3] - b[1]) + 2 * pad
        content = [c for c in self.root if tag(c) not in SKIP]
        g = ET.Element(q("g"))
        g.set("id", self.new_id())
        g.set("transform", f"translate({fnum(-x0)} {fnum(-y0)})")
        for c in content:
            self.root.remove(c)
            g.append(c)
        self.root.append(g)
        self.set_canvas(max(w, 1), max(h, 1))
        return -x0, -y0


def deepcopy_el(el: ET.Element) -> ET.Element:
    return copy.deepcopy(el)
