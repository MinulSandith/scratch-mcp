#!/usr/bin/env python3
"""Pastel notebook labels (half of an A4 sheet each) for Economics, Accounting, English and Statistics.

Every label is drawn as one SVG (units: 0.1 mm, so the canvas is 2100 x 1485 = 210 x 148.5 mm),
rendered with headless Chromium at 300 dpi, and two labels are put on each A4 page of the print PDF.

    python3 build_labels.py                 # all labels -> output/*.png + output/subject-labels-A4.pdf
    python3 build_labels.py --only english  # one label
"""
import argparse
import asyncio
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FONTS = Path(os.environ.get("LABEL_FONTS", ROOT / "fonts")).resolve()
OUT = Path(os.environ.get("LABEL_OUT", ROOT / "output")).resolve()

W, H = 2100, 1485          # 210 x 148.5 mm
PX_W = 2480                # 300 dpi
CHROME = os.environ.get("LABEL_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

INK = "#2e2846"
TEXT = "#2d2852"
STEM = "#5d5a6e"
LAV = "#c3b2f1"
LAV_D = "#9d86e0"
PINK = "#f4a9c4"
PINK_D = "#cf7b9c"
GOLD = "#f3c766"
CREAM = "#fbf4e4"
PAPER = "#fffcf9"

SUBJECTS = {
    "economics": dict(
        title="Economics",
        quote=("An investment in knowledge", "pays the best interest."),
        books=["Microeconomics", "Macroeconomics", "Demand & Supply", "Money & Banking"],
        checklist=["Demand", "Supply", "Equilibrium", "Inflation", "GDP"],
        screen="econ",
    ),
    "accounting": dict(
        title="Accounting",
        quote=("Keep calm and", "balance the books."),
        books=["Journal", "Ledger", "Trial Balance", "Final Accounts"],
        checklist=["Debit", "Credit", "Balance", "Audit", "Report"],
        screen="acct",
    ),
    "english": dict(
        title="English",
        quote=("Small words lead", "to big stories."),
        books=["Grammar", "Literature", "Poetry", "Creative Writing"],
        checklist=["Read", "Write", "Speak", "Listen", "Imagine"],
        screen="eng",
    ),
    "statistics": dict(
        title="Statistics",
        quote=("Every data point", "tells a story."),
        books=["Probability", "Data Analysis", "Distributions", "Hypothesis Testing"],
        checklist=["Collect", "Organize", "Analyze", "Interpret", "Present"],
        screen="stats",
    ),
    "git": dict(
        title="Git",
        title_font="Damion",   # Norican's G reads like a small g
        title_fs=400,
        quote=("Small commits", "lead to big progress."),
        books=["Version Control", "Branches", "Merge", "Pull Requests"],
        checklist=["Stage", "Commit", "Push", "Pull", "Merge"],
        screen="git",
    ),
}


# ----------------------------------------------------------------------------------------------- helpers
def f(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def poly(points, close=True):
    return "M" + " L".join(f"{f(x)},{f(y)}" for x, y in points) + (" Z" if close else "")


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Layer:
    """One drawn object: watercolour fills under hand-drawn ink lines, crisp text on top."""

    def __init__(self):
        self.base, self.fill, self.ink, self.top = [], [], [], []

    def shape(self, d, fill=None, stroke=INK, sw=4.0, tf="", fill_extra="", ink_extra=""):
        t = f' transform="{tf}"' if tf else ""
        if fill:
            self.base.append(f'<path d="{d}"{t}/>')
            self.fill.append(f'<path d="{d}" fill="{fill}"{t}{fill_extra}/>')
        if stroke:
            self.ink.append(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{f(sw)}"{t}{ink_extra}/>')

    def svg(self):
        out = []
        if self.base:   # opaque paper under the see-through watercolour, so objects hide what is behind them
            out.append(f'<g filter="url(#rough)" fill="{PAPER}">{"".join(self.base)}</g>')
        if self.fill:
            out.append(f'<g filter="url(#paint)">{"".join(self.fill)}</g>')
        if self.ink:
            out.append(f'<g filter="url(#rough)" stroke-linecap="round" stroke-linejoin="round">{"".join(self.ink)}</g>')
        out += self.top
        return "".join(out)


def bez(p, t):
    p0, p1, p2, p3 = p
    m = 1 - t
    return tuple(m**3 * p0[i] + 3 * m * m * t * p1[i] + 3 * m * t * t * p2[i] + t**3 * p3[i] for i in (0, 1))


def bez_tan(p, t):
    p0, p1, p2, p3 = p
    m = 1 - t
    d = [3 * m * m * (p1[i] - p0[i]) + 6 * m * t * (p2[i] - p1[i]) + 3 * t * t * (p3[i] - p2[i]) for i in (0, 1)]
    n = math.hypot(*d) or 1
    return d[0] / n, d[1] / n


def bez_d(p):
    return "M{},{} C{},{} {},{} {},{}".format(*(f(c) for pt in p for c in pt))


def wavy_rrect(x0, y0, x1, y1, r, amp, wl, inset=0.0, phase=0.0, step=3.0):
    """Rounded rectangle whose outline waves along its normal; `inset` gives a parallel copy inside."""
    la = math.pi * r / 2

    def line(ax, ay, bx, by, nx, ny):
        return math.hypot(bx - ax, by - ay), lambda t: (ax + (bx - ax) * t, ay + (by - ay) * t, nx, ny)

    def arc(cx, cy, a0):
        def fn(t):
            a = a0 + t * math.pi / 2
            return cx + r * math.cos(a), cy + r * math.sin(a), math.cos(a), math.sin(a)
        return la, fn

    segs = [line(x0 + r, y0, x1 - r, y0, 0, -1), arc(x1 - r, y0 + r, -math.pi / 2),
            line(x1, y0 + r, x1, y1 - r, 1, 0), arc(x1 - r, y1 - r, 0),
            line(x1 - r, y1, x0 + r, y1, 0, 1), arc(x0 + r, y1 - r, math.pi / 2),
            line(x0, y1 - r, x0, y0 + r, -1, 0), arc(x0 + r, y0 + r, math.pi)]
    per = sum(s[0] for s in segs)
    wl = per / max(1, round(per / wl))
    pts, s0 = [], 0.0
    for length, fn in segs:
        k = max(1, int(length / step))
        for i in range(k):
            t = i / k
            px, py, nx, ny = fn(t)
            off = amp * math.sin(2 * math.pi * (s0 + t * length) / wl + phase) - inset
            pts.append((px + nx * off, py + ny * off))
        s0 += length
    return poly(pts)


# ----------------------------------------------------------------------------------------------- shapes
def heart_d():
    return "M0,30 C-6,24 -40,6 -40,-15 C-40,-36 -18,-42 0,-24 C18,-42 40,-36 40,-15 C40,6 6,24 0,30 Z"


def heart(layer, x, y, size, fill, stroke, rot=0):
    k = size / 80
    layer.shape(heart_d(), fill, stroke, 3.2 / k, f"translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(k)})")


def sparkle(layer, x, y, s, rot=0):
    a, b = s, s * 0.78
    c = s * 0.1
    d = (f"M0,{f(-a)} C{f(c)},{f(-c)} {f(c)},{f(-c)} {f(b)},0 C{f(c)},{f(c)} {f(c)},{f(c)} 0,{f(a)} "
         f"C{f(-c)},{f(c)} {f(-c)},{f(c)} {f(-b)},0 C{f(-c)},{f(-c)} {f(-c)},{f(-c)} 0,{f(-a)} Z")
    layer.shape(d, "#fffdfa", INK, 3.4, f"translate({f(x)},{f(y)}) rotate({f(rot)})")


def leaf_d(length, width):
    L, w = length, width
    return (f"M0,0 C{f(L*.3)},{f(-w)} {f(L*.75)},{f(-w)} {f(L)},0 "
            f"C{f(L*.75)},{f(w)} {f(L*.3)},{f(w)} 0,0 Z")


def leaf(layer, x, y, ang, length, width=None, fill="#a9bb8b"):
    width = width or length * 0.36
    tf = f"translate({f(x)},{f(y)}) rotate({f(ang)})"
    layer.shape(leaf_d(length, width), fill, "#6d7a57", 2.8, tf)
    layer.shape(f"M{f(length*.1)},0 Q{f(length*.5)},{f(width*.12)} {f(length*.86)},0", None, "#6d7a57", 2, tf)


def bud(layer, x, y, ang, size, kind="pink"):
    L, w = size, size * 0.42
    grad, stroke = ("url(#budPink)", "#b8698c") if kind == "pink" else ("url(#budPurple)", "#7b64bb")
    tf = f"translate({f(x)},{f(y)}) rotate({f(ang)})"
    d = f"M0,0 C{f(-w)},{f(-L*.02)} {f(-w)},{f(-L*.6)} 0,{f(-L)} C{f(w)},{f(-L*.6)} {f(w)},{f(-L*.02)} 0,0 Z"
    layer.shape(d, grad, stroke, 2.8, tf)
    layer.shape(f"M{f(-w*.15)},{f(-L*.1)} C{f(-w*.45)},{f(-L*.45)} {f(-w*.2)},{f(-L*.8)} 0,{f(-L*.96)}",
                None, stroke, 2, tf)
    layer.shape(f"M{f(-w*.55)},{f(-L*.12)} L0,{f(L*.1)} L{f(w*.55)},{f(-L*.12)} L0,{f(-L*.2)} Z",
                "#9fb487", "#6d7a57", 2.2, tf)


def sprig(stem, items, stem_color=STEM):
    """A drawn branch: `items` are (t, kind, side, size) along the cubic `stem`."""
    lay = Layer()
    lay.shape(bez_d(stem), None, stem_color, 4)
    flowers = []
    for t, kind, side, size in items:
        px, py = bez(stem, t)
        tx, ty = bez_tan(stem, t)
        if side == 0:
            dx, dy, bx, by = tx, ty, px, py
        else:
            nx, ny = -ty * side, tx * side
            dx, dy = nx * 0.8 + tx * 0.6, ny * 0.8 + ty * 0.6
            n = math.hypot(dx, dy)
            dx, dy = dx / n, dy / n
            if kind == "leaf":
                bx, by = px, py
            else:
                bx, by = px + dx * size * 0.4, py + dy * size * 0.4
                lay.shape(f"M{f(px)},{f(py)} Q{f(px+tx*size*.2+dx*size*.1)},{f(py+ty*size*.2+dy*size*.1)} "
                          f"{f(bx)},{f(by)}", None, stem_color, 3)
        ang = math.degrees(math.atan2(dy, dx))
        if kind == "leaf":
            leaf(lay, bx, by, ang, size, fill="#a9bb8b" if int(t * 10) % 2 else "#c4c381")
        else:
            flowers.append((bx, by, ang + 90, size, kind))
    for bx, by, ang, size, kind in flowers:
        bud(lay, bx, by, ang, size, kind)
    return lay.svg()


def flower(x, y, r):
    lay = Layer()
    petal = (f"M0,0 C{f(-r*.75)},{f(-r*.3)} {f(-r*.6)},{f(-r*1.05)} {f(-r*.13)},{f(-r*.98)} "
             f"Q0,{f(-r*.88)} {f(r*.13)},{f(-r*.98)} C{f(r*.6)},{f(-r*1.05)} {f(r*.75)},{f(-r*.3)} 0,0 Z")
    for i in range(5):
        tf = f"translate({f(x)},{f(y)}) rotate({i*72-8})"
        lay.shape(petal, "url(#petal)", "#6f58b0", 3, tf)
        lay.shape(f"M0,{f(-r*.25)} L0,{f(-r*.6)}", None, "#8a72cc", 2.2, tf)
    lay.shape(f"M{f(x-r*.2)},{f(y)} a{f(r*.2)},{f(r*.2)} 0 1 0 {f(r*.4)},0 a{f(r*.2)},{f(r*.2)} 0 1 0 {f(-r*.4)},0 Z",
              GOLD, "#8d6a2b", 3)
    for a in range(0, 360, 60):
        cx, cy = x + math.cos(math.radians(a)) * r * .09, y + math.sin(math.radians(a)) * r * .09
        lay.top.append(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="3.2" fill="#8d6a2b"/>')
    return lay.svg()


def divider(cx, y, half, heart_fill=PINK):
    lay = Layer()
    lay.shape(f"M{f(cx-half)},{f(y)} L{f(cx-62)},{f(y)}", None, INK, 3)
    lay.shape(f"M{f(cx+62)},{f(y)} L{f(cx+half)},{f(y)}", None, INK, 3)
    for dx in (-44, 44):
        lay.top.append(f'<circle cx="{f(cx+dx)}" cy="{f(y)}" r="6" fill="{INK}"/>')
    heart(lay, cx, y - 2, 52, heart_fill, PINK_D)
    return lay.svg()


# ----------------------------------------------------------------------------------------------- pieces
def border():
    outer = wavy_rrect(78, 78, 2022, 1407, 95, 10, 104)
    inner = wavy_rrect(78, 78, 2022, 1407, 95, 10, 104, inset=36)
    return (f'<path d="{outer}" fill="none" stroke="{LAV}" stroke-width="22" filter="url(#paint)"/>'
            f'<path d="{outer}" fill="none" stroke="{LAV_D}" stroke-width="4" stroke-opacity=".55" '
            f'transform="translate(0,-5)" filter="url(#rough)"/>'
            f'<path d="{inner}" fill="none" stroke="#8a7cc2" stroke-width="3.4" stroke-dasharray="14 10" '
            f'stroke-linecap="round"/>')


def washi_tape(cx, cy, ang):
    hl, hh = 178, 44
    top = [(-hl, -hh), (hl, -hh)]
    right = [(hl + (7 if i % 2 else -2), -hh + i * 2 * hh / 8) for i in range(9)]
    left = [(-hl + (-7 if i % 2 else 2), hh - i * 2 * hh / 8) for i in range(9)]
    d = poly(top + right + [(-hl, hh)] + left)
    hearts = []
    for row, yy in enumerate((-20, 20)):
        for i in range(-4, 5):
            xx = i * 42 + (21 if row else 0)
            if abs(xx) < hl - 10:
                k = 22 / 80
                hearts.append(f'<path d="{heart_d()}" transform="translate({xx},{yy}) rotate({(i*17)%30-15}) '
                              f'scale({f(k)})" fill="#fff" fill-opacity=".9"/>')
    return (f'<g transform="translate({cx},{cy}) rotate({ang})"><clipPath id="tapeclip"><path d="{d}"/></clipPath>'
            f'<g filter="url(#paint)"><path d="{d}" fill="#f6b3c9" fill-opacity=".92"/></g>'
            f'<g clip-path="url(#tapeclip)">{"".join(hearts)}</g>'
            f'<path d="{d}" fill="none" stroke="#e595b2" stroke-width="2" stroke-opacity=".6"/></g>')


def title_block(title, x=1262, y=488, fs=270, maxw=890):
    rays_l = ('<g id="rays-left" fill="none" stroke="#a88ee8" stroke-width="16" stroke-linecap="round" '
              'filter="url(#paint)"><path d="M-20,-38 L-80,-64"/><path d="M-28,6 L-106,10"/>'
              '<path d="M-20,50 L-74,86"/></g>')
    extra = Layer()                    # these travel with the right-hand rays, whatever the title width
    heart(extra, 52, 118, 50, "#b7a0ea", "#6f58b0", 12)
    sparkle(extra, 150, 30, 22)
    rays_r = ('<g id="rays-right"><g fill="none" stroke="#a88ee8" stroke-width="16" stroke-linecap="round" '
              'filter="url(#paint)"><path d="M16,-52 L48,-100"/><path d="M32,-6 L100,-34"/>'
              f'<path d="M30,42 L98,50"/></g>{extra.svg()}</g>')
    t = esc(title)
    return (f'{rays_l}{rays_r}'
            f'<text id="title-shadow" x="{x}" y="{y}" text-anchor="middle" class="title" font-size="{fs}" '
            f'fill="#bba8f0" transform="translate({f(fs*.044)},{f(fs*.037)})">{t}</text>'
            f'<text id="title" x="{x}" y="{y}" text-anchor="middle" class="title" font-size="{fs}" '
            f'fill="#1e1931" data-maxw="{maxw}">{t}</text>')


def quote_block(lines, cx=580, y=218, gap=66, fs=54, maxw=470, div_gap=61, div_half=165):
    a, b = (esc(s) for s in lines)
    return (f'<text x="{cx}" y="{y}" text-anchor="middle" class="hand" font-size="{fs}" fill="{TEXT}" '
            f'data-maxw="{maxw}" data-fit="quote">“{a}</text>'
            f'<text x="{cx}" y="{y+gap}" text-anchor="middle" class="hand" font-size="{fs}" fill="{TEXT}" '
            f'data-maxw="{maxw}" data-fit="quote">{b}”</text>' + divider(cx, y + gap + div_gap, div_half))


LID = (1.0, -0.097, 0.114, 1.0, 165.0, 560.0)   # laptop lid: local 460 x 340 -> page


def lid_pt(x, y):
    a, b, c, d, e, f_ = LID
    return e + a * x + c * y, f_ + b * x + d * y


def screen_content(kind):
    """Drawing on the laptop screen, in screen coordinates (0..416 x 0..296)."""
    g = []
    g.append('<path d="M0,10 Q0,0 10,0 L406,0 Q416,0 416,10 L416,40 L0,40 Z" fill="#e9e1fd"/>')
    for i, c in enumerate(("#f4a3c0", "#f5d48c", "#b9a3ee")):
        g.append(f'<circle cx="{24+i*24}" cy="20" r="7.5" fill="{c}" stroke="{INK}" stroke-width="2"/>')
    if kind == "econ":
        dcur = ((100, 84), (170, 135), (250, 205), (360, 238))
        scur = ((100, 238), (190, 222), (280, 156), (360, 86))
        best = min(((bez(dcur, i / 400), bez(scur, j / 400)) for i in range(401) for j in range(0, 401, 4)),
                   key=lambda pq: math.dist(*pq))[0]
        ex, ey = best
        g.append(f'<path d="M70,60 L70,258 L392,258" fill="none" stroke="{INK}" stroke-width="5" '
                 f'stroke-linecap="round" stroke-linejoin="round"/>'
                 f'<path d="M61,74 L70,58 L79,74 M378,249 L394,258 L378,267" fill="none" stroke="{INK}" '
                 f'stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
                 f'<path d="M70,{f(ey)} L{f(ex)},{f(ey)} L{f(ex)},258" fill="none" stroke="#8d82b5" '
                 f'stroke-width="3.5" stroke-dasharray="9 8"/>'
                 f'<path d="{bez_d(dcur)}" fill="none" stroke="#ec7ea6" stroke-width="9" stroke-linecap="round"/>'
                 f'<path d="{bez_d(scur)}" fill="none" stroke="#8a6fdb" stroke-width="9" stroke-linecap="round"/>'
                 f'<circle cx="{f(ex)}" cy="{f(ey)}" r="11" fill="{GOLD}" stroke="{INK}" stroke-width="3"/>'
                 f'<text x="372" y="236" class="hand" font-size="40" fill="#d2557f">D</text>'
                 f'<text x="370" y="96" class="hand" font-size="40" fill="#6f52c6">S</text>'
                 f'<text x="40" y="96" class="hand" font-size="34" fill="{INK}">P</text>'
                 f'<text x="374" y="292" class="hand" font-size="34" fill="{INK}">Q</text>')
    elif kind == "acct":
        g.append(f'<path d="M58,104 L358,104 M208,104 L208,282" fill="none" stroke="{INK}" stroke-width="6" '
                 f'stroke-linecap="round"/>'
                 f'<text x="133" y="92" text-anchor="middle" class="hand" font-size="44" fill="#d2557f">Dr</text>'
                 f'<text x="283" y="92" text-anchor="middle" class="hand" font-size="44" fill="#6f52c6">Cr</text>')
        for x, vals in ((133, ("1,200", "800")), (283, ("1,500", "500"))):
            for i, v in enumerate(vals):
                g.append(f'<text x="{x}" y="{150+i*44}" text-anchor="middle" class="hand" font-size="36" '
                         f'fill="{INK}">{v}</text>')
            g.append(f'<path d="M{x-55},{208} L{x+55},208" stroke="{INK}" stroke-width="3"/>'
                     f'<text x="{x}" y="250" text-anchor="middle" class="hand" font-size="40" '
                     f'fill="#6f52c6">2,000</text>'
                     f'<path d="M{x-55},262 L{x+55},262 M{x-55},270 L{x+55},270" stroke="#6f52c6" '
                     f'stroke-width="3"/>')
    elif kind == "eng":
        g.append(f'<text x="34" y="214" class="serif" font-size="158" fill="{INK}">Aa</text>'
                 '<path d="M44,244 q17,-14 34,0 t34,0 t34,0 t34,0 t34,0" fill="none" stroke="#ec7ea6" '
                 'stroke-width="7" stroke-linecap="round"/>')
        for i, wdt in enumerate((140, 118, 132, 86)):
            g.append(f'<rect x="258" y="{92+i*42}" width="{wdt}" height="15" rx="7.5" '
                     f'fill="{"#cbbcf4" if i % 2 == 0 else "#f6bfd3"}"/>')
    elif kind == "git":
        g.append('<path d="M120,200 C152,200 150,112 186,112 L264,112 C300,112 298,200 330,200" fill="none" '
                 'stroke="#ec7ea6" stroke-width="9" stroke-linecap="round"/>'
                 '<path d="M48,200 L382,200" stroke="#8a6fdb" stroke-width="9" stroke-linecap="round"/>')
        for cx, cy, col in ((60, 200, "#cdbcf5"), (120, 200, "#cdbcf5"), (226, 200, "#cdbcf5"),
                            (186, 112, "#f6bad0"), (264, 112, "#f6bad0"), (330, 200, GOLD), (380, 200, "#cdbcf5")):
            g.append(f'<circle cx="{cx}" cy="{cy}" r="16" fill="{col}" stroke="{INK}" stroke-width="3.5"/>')
        g.append(f'<text x="44" y="262" class="hand" font-size="38" fill="#6f52c6">main</text>'
                 f'<text x="180" y="78" class="hand" font-size="34" fill="#d2557f">feature</text>'
                 f'<text x="300" y="262" class="hand" font-size="34" fill="{INK}">merge</text>')
    elif kind == "stats":
        cols = ("#cdbcf5", "#f6bad0", "#b9c6f5", "#a98fe6", "#b9c6f5", "#f6bad0", "#cdbcf5")
        x0, bw = 62, 44
        for i, z in enumerate((-1.8, -1.2, -0.6, 0, 0.6, 1.2, 1.8)):
            h = 172 * math.exp(-z * z / 2)
            g.append(f'<rect x="{x0+i*(bw+4)}" y="{f(258-h)}" width="{bw}" height="{f(h)}" rx="4" '
                     f'fill="{cols[i]}" stroke="{INK}" stroke-width="3"/>')
        cx = x0 + 3.5 * (bw + 4) - 2
        sig = (bw + 4) / 0.6
        pts = [(x, 258 - 190 * math.exp(-((x - cx) / sig) ** 2 / 2)) for x in range(44, 394, 4)]
        g.append(f'<path d="M{f(cx)},258 L{f(cx)},62" stroke="#6f52c6" stroke-width="3.5" stroke-dasharray="9 8"/>'
                 f'<path d="{poly(pts, False)}" fill="none" stroke="#ec7ea6" stroke-width="8" '
                 f'stroke-linecap="round" stroke-linejoin="round"/>'
                 f'<path d="M40,258 L398,258" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>')
    return "".join(g)


def laptop(kind):
    a, b, c, d, e, f_ = LID
    bl, br = lid_pt(0, 340), lid_pt(460, 340)
    dv = (215, 118)
    fl, fr = (bl[0] + dv[0], bl[1] + dv[1]), (br[0] + dv[0], br[1] + dv[1])

    def q(u, v):
        return (bl[0] + u * (br[0] - bl[0]) + v * dv[0], bl[1] + u * (br[1] - bl[1]) + v * dv[1])

    base = Layer()
    base.shape(poly([fl, fr, (fr[0], fr[1] + 20), (fl[0], fl[1] + 20)]), "#a995e3", INK, 4)
    base.shape(poly([bl, br, fr, fl]), "#cec0f5", INK, 4.5)
    rows, cols = 4, 12
    u0, u1, v0, v1 = 0.07, 0.93, 0.1, 0.56
    for r in range(rows):
        va, vb = v0 + (v1 - v0) * r / rows, v0 + (v1 - v0) * (r + 0.78) / rows
        col = 0
        while col < cols:
            span = 5 if (r == rows - 1 and col == 3) else 1
            ua = u0 + (u1 - u0) * col / cols
            ub = u0 + (u1 - u0) * (col + span - 0.22) / cols
            base.shape(poly([q(ua, va), q(ub, va), q(ub, vb), q(ua, vb)]), "#a491df", "#7663b8", 1.8)
            col += span
    base.shape(poly([q(.4, .66), q(.68, .66), q(.68, .91), q(.4, .91)]), "#bba9f0", "#7663b8", 2.4)

    lid = Layer()
    tf = f"matrix({a},{b},{c},{d},{e},{f_})"
    lid.shape("M24,0 L436,0 Q460,0 460,24 L460,340 L0,340 L0,24 Q0,0 24,0 Z", "#c9b8f3", INK, 4.5, tf)
    lid.shape("M30,22 L430,22 Q438,22 438,30 L438,318 L22,318 L22,30 Q22,22 30,22 Z", "#f7f3ff", INK, 3.4, tf)
    lid.top.append(f'<g transform="{tf} translate(22,22)"><clipPath id="scr"><rect width="416" height="296" '
                   f'rx="8"/></clipPath><g clip-path="url(#scr)">{screen_content(kind)}</g></g>')
    lid.top.append(f'<circle cx="{f(lid_pt(230, 11)[0])}" cy="{f(lid_pt(230, 11)[1])}" r="4" fill="{INK}"/>')
    return base.svg() + lid.svg()


def mug(x, y):
    plant = Layer()
    tf = f"translate({x},{y})"
    for dd in ("M62,0 C58,-40 52,-84 36,-122", "M62,0 C68,-40 82,-82 104,-112", "M62,0 C62,-52 64,-96 70,-146"):
        plant.shape(dd, None, "#6d7a57", 4, tf)
    for lx, ly, ang, ln, col in ((36, -122, -122, 74, "#a9bb8b"), (104, -112, -52, 72, "#c4c381"),
                                 (70, -146, -86, 78, "#b3c690"), (48, -64, -152, 58, "#c4c381"),
                                 (82, -70, -24, 56, "#a9bb8b"), (60, -100, -110, 50, "#9fb487")):
        leaf(plant, x + lx, y + ly, ang, ln, fill=col)
    cup = Layer()
    plant.top.append(f'<ellipse cx="{x+70}" cy="{y+152}" rx="88" ry="11" fill="#d9cff5" fill-opacity=".7" '
                   f'filter="url(#paint)"/>')
    cup.shape("M116,30 C178,20 180,114 112,118 L113,100 C158,98 160,48 117,48 Z", "#fffaf5", INK, 4, tf)
    cup.shape("M0,0 L8,128 Q11,152 36,152 L88,152 Q113,152 116,128 L124,0 A62,14 0 0 1 0,0 Z",
              "#fffaf5", INK, 4.5, tf)
    cup.shape("M0,0 A62,14 0 0 1 124,0 A62,14 0 0 1 0,0 Z", "#fffaf5", INK, 4, tf)
    cup.shape("M10,2 A52,9 0 0 1 114,2 A52,9 0 0 1 10,2 Z", "#86685a", None, 0, tf)
    heart(cup, x + 62, y + 84, 40, PINK, PINK_D)
    return plant.svg() + cup.svg()


def books(titles):
    cols = (("#f7b4cc", "#e48daf"), ("#cab4f3", "#a78fe1"), ("#b4c2f4", "#8ea0e6"), ("#f9dca2", "#e8bd6e"))
    specs = [(140, 1198, 480, 96, 0.0), (160, 1105, 452, 92, -1.6), (172, 1013, 432, 92, 1.4),
             (188, 920, 408, 93, -2.8)]           # bottom -> top
    out = []
    dx, dy = -32, -19
    for k, (x, y, w, h, rot) in enumerate(specs):
        idx = 3 - k                       # titles listed top -> bottom
        col, dark = cols[idx]
        lay = Layer()
        tf = f"rotate({rot},{x + w / 2},{y + h / 2})"
        lay.shape(poly([(x, y), (x + w, y), (x + w + dx, y + dy), (x + dx, y + dy)]), col, INK, 4, tf)
        lay.shape(poly([(x, y), (x + dx, y + dy), (x + dx, y + h + dy), (x, y + h)]), CREAM, INK, 3.6, tf)
        for yy in range(16, h - 8, 10):
            lay.shape(f"M{f(x - 2)},{f(y + yy)} L{f(x + dx + 2)},{f(y + yy + dy)}", None, "#cdbb9c", 1.6, tf)
        for yy in (0, h - 9):
            lay.shape(poly([(x, y + yy), (x + dx, y + yy + dy), (x + dx, y + yy + dy + 9), (x, y + yy + 9)]),
                      dark, None, 0, tf)
        front = (f"M{f(x)},{f(y)} L{f(x+w-16)},{f(y)} Q{f(x+w)},{f(y)} {f(x+w)},{f(y+16)} L{f(x+w)},{f(y+h-16)} "
                 f"Q{f(x+w)},{f(y+h)} {f(x+w-16)},{f(y+h)} L{f(x)},{f(y+h)} Z")
        lay.shape(front, col, INK, 4.2, tf)
        for bx in (x + 16, x + w - 44):
            lay.shape(f"M{f(bx)},{f(y+3)} L{f(bx+12)},{f(y+3)} L{f(bx+12)},{f(y+h-3)} L{f(bx)},{f(y+h-3)} Z",
                      dark, None, 0, tf, fill_extra=' fill-opacity=".55"')
        lay.top.append(f'<text x="{f(x + w / 2 - 6)}" y="{f(y + h / 2 + 16)}" text-anchor="middle" class="hand" '
                       f'font-size="48" fill="{TEXT}" data-maxw="{w - 110}" transform="{tf}">{esc(titles[idx])}</text>')
        out.append(lay.svg())
    return "".join(out)


def notebook(items):
    lay = Layer()
    tf = "translate(694,948) rotate(7)"
    lay.shape("M18,10 L304,10 Q314,10 314,20 L314,346 Q314,356 304,356 L18,356 Q8,356 8,346 L8,20 Q8,10 18,10 Z",
              "#ece5fc", INK, 3.6, tf)
    lay.shape("M10,0 L292,0 Q302,0 302,10 L302,334 Q302,344 292,344 L10,344 Q0,344 0,334 L0,10 Q0,0 10,0 Z",
              "#fffdf8", INK, 4.2, tf)
    rows = [74 + i * 58 for i in range(5)]
    for y in rows:
        lay.shape(f"M40,{y+14} L284,{y+14}", None, "#d9cff2", 2.4, tf)
    for y in range(30, 330, 33):
        lay.shape(f"M18,{y} C4,{y-15} -22,{y-13} -20,{y+2} C-19,{y+9} -10,{y+11} -4,{y+8}", None, INK, 4, tf)
        lay.top.append(f'<circle cx="18" cy="{y}" r="5" fill="#4b4463" transform="{tf}"/>')
    texts = []
    for y, it in zip(rows, items):
        lay.shape(f"M50,{y-30} L80,{y-30} Q84,{y-30} 84,{y-26} L84,{y+2} Q84,{y+6} 80,{y+6} L50,{y+6} "
                  f"Q46,{y+6} 46,{y+2} L46,{y-26} Q46,{y-30} 50,{y-30} Z", "#fff", INK, 3.2, tf)
        lay.shape(f"M52,{y-12} L62,{y-1} L86,{y-36}", None, INK, 4.6, tf)
        texts.append(f'<text x="100" y="{y}" class="hand" font-size="44" fill="{TEXT}" data-maxw="176" '
                     f'data-fit="check">{esc(it)}</text>')
    lay.top.append(f'<g transform="{tf}">{"".join(texts)}</g>')
    h = Layer()
    heart(h, 0, 0, 46, PINK, PINK_D)
    lay.top.append(f'<g transform="{tf} translate(266,34) rotate(10)">{h.svg()}</g>')
    return lay.svg()


def pen(x, y, ang):
    lay = Layer()
    tf = f"translate({x},{y}) rotate({ang})"
    lay.shape("M0,0 L36,-12 L44,0 L36,12 Z", "#ead08a", INK, 3.4, tf)
    lay.shape("M8,0 L30,0", None, INK, 2.2, tf)
    lay.shape("M40,-13 L70,-14 L70,14 L40,13 Z", "#46405e", INK, 3.4, tf)
    lay.shape("M70,-18 L270,-18 Q292,-18 292,0 Q292,18 270,18 L70,18 Z", "#2b2540", INK, 3.6, tf)
    lay.shape("M150,-18 L162,-18 L162,18 L150,18 Z", GOLD, INK, 2.6, tf)
    lay.shape("M196,-18 L196,-27 Q196,-30 200,-30 L262,-30 Q268,-30 266,-24 L262,-18", GOLD, INK, 3, tf)
    lay.top.append(f'<path d="M84,-8 L262,-8" stroke="#fff" stroke-opacity=".45" stroke-width="5" '
                   f'stroke-linecap="round" transform="{tf}"/>')
    return lay.svg()


def bow(x, y, s=1.0):
    lay = Layer()
    tf = f"translate({x},{y}) scale({s})"
    st = "#cf7d9c"
    for d in ("M-6,8 C-18,40 -40,72 -58,98 L-40,93 L-30,110 C-14,76 -2,42 6,12 Z",
              "M6,8 C18,40 36,70 50,100 L34,95 L22,108 C10,76 0,42 -6,12 Z",
              "M0,0 C-30,-48 -98,-52 -104,-8 C-108,30 -50,34 0,0 Z",
              "M0,0 C30,-48 98,-52 104,-8 C108,30 50,34 0,0 Z"):
        lay.shape(d, "#f8c3d6", st, 3.6, tf)
    for d in ("M-12,-6 C-38,-24 -72,-26 -86,-6", "M12,-6 C38,-24 72,-26 86,-6",
              "M-14,6 C-40,16 -66,14 -80,8", "M14,6 C40,16 66,14 80,8"):
        lay.shape(d, None, st, 2.4, tf)
    lay.shape("M0,-21 C12,-21 17,-10 17,0 C17,10 12,21 0,21 C-12,21 -17,10 -17,0 C-17,-10 -12,-21 0,-21 Z",
              "#f4a9c4", st, 3.6, tf)
    return lay.svg()


def info_box():
    x0, y0, x1, y1 = 1118, 616, 1956, 1300
    d = wavy_rrect(x0, y0, x1, y1, 46, 7, 68)
    out = [f'<path d="{d}" fill="#fffdff" fill-opacity=".75"/>',
           f'<path d="{d}" fill="none" stroke="#ddd3f7" stroke-width="12" filter="url(#paint)"/>',
           f'<path d="{d}" fill="none" stroke="#9a88d8" stroke-width="3.8" stroke-dasharray="15 11" '
           f'stroke-linecap="round"/>']
    fields = ["Name", "Class", "Section", "Subject Teacher", "School", "Session"]
    for i, name in enumerate(fields):
        y = 748 + i * 97
        out.append(f'<g class="row" data-colon="1428">'
                   f'<text class="hand lab" x="1196" y="{y}" font-size="54" fill="{TEXT}">{name}</text>'
                   f'<text class="hand colon" x="1428" y="{y}" font-size="54" fill="{TEXT}">:</text>'
                   f'<line class="line" x1="1460" y1="{y+6}" x2="1884" y2="{y+6}" stroke="#3a3462" '
                   f'stroke-width="2.6" stroke-linecap="round"/></g>')
    return "".join(out)


def decorations(style):
    lay = Layer()
    if style == "fields":
        sparkles = ((330, 430, 30), (262, 520, 20), (128, 640, 17), (842, 238, 22), (1188, 205, 20), (1642, 262, 27),
                    (1940, 520, 19), (1880, 578, 15), (842, 640, 19), (1080, 1180, 22), (1990, 1180, 17),
                    (565, 470, 16), (1260, 1360, 16), (690, 1360, 15))
        hearts = ((372, 520, 50, "p", -10), (128, 760, 44, "p", 8), (965, 662, 44, "k", 10), (1065, 750, 56, "p", -6),
                  (1058, 1282, 44, "p", 6), (1600, 1352, 32, "k", -8), (520, 420, 30, "k", 10))
        dots = ((600, 390), (238, 560), (1150, 1300), (1330, 1350), (1470, 545), (1990, 940), (905, 860))
    else:
        sparkles = ((300, 600, 26), (128, 640, 17), (700, 158, 20), (1430, 152, 18), (842, 640, 19),
                    (1940, 520, 19), (1300, 690, 24), (1945, 790, 17), (1210, 1110, 20), (1080, 1180, 22),
                    (1990, 1180, 17), (1260, 1360, 16), (690, 1360, 15))
        hearts = ((128, 760, 44, "p", 8), (965, 662, 44, "k", 10), (1065, 750, 56, "p", -6), (1058, 1282, 44, "p", 6),
                  (1600, 1352, 32, "k", -8), (1790, 700, 46, "p", 10), (1700, 1150, 38, "k", -8),
                  (1380, 1170, 30, "p", 6))
        dots = ((238, 560), (1150, 1300), (1330, 1350), (1990, 940), (905, 860), (1500, 1110), (1250, 820))
    for x, y, s in sparkles:
        sparkle(lay, x, y, s)
    for x, y, s, c, r in hearts:
        heart(lay, x, y, s, "#b7a0ea" if c == "p" else PINK, "#6f58b0" if c == "p" else PINK_D, r)
    for x, y in dots:
        lay.top.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{INK}" fill-opacity=".7"/>')
    return lay.svg()


DEFS = f"""
<defs>
  <filter id="rough" x="-10%" y="-10%" width="120%" height="120%">
    <feTurbulence type="fractalNoise" baseFrequency="0.022" numOctaves="2" seed="4" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="4.5" xChannelSelector="R" yChannelSelector="G"/>
  </filter>
  <filter id="paint" x="-10%" y="-10%" width="120%" height="120%" color-interpolation-filters="sRGB">
    <feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="11" result="warp"/>
    <feDisplacementMap in="SourceGraphic" in2="warp" scale="7" xChannelSelector="R" yChannelSelector="G" result="shape"/>
    <feTurbulence type="fractalNoise" baseFrequency="0.05" numOctaves="3" seed="5" result="blot"/>
    <feColorMatrix in="blot" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0.7 0 0 0 0.5" result="blotA"/>
    <feComposite in="shape" in2="blotA" operator="in" result="tex"/>
    <feMorphology in="shape" operator="erode" radius="3" result="er"/>
    <feComposite in="shape" in2="er" operator="out" result="edge"/>
    <feGaussianBlur in="edge" stdDeviation="1.3" result="edgeb"/>
    <feMerge><feMergeNode in="tex"/><feMergeNode in="edgeb"/></feMerge>
  </filter>
  <linearGradient id="budPink" x1="0" y1="1" x2="0" y2="0">
    <stop offset="0" stop-color="#fcd5e3"/><stop offset=".55" stop-color="#f3a6c4"/><stop offset="1" stop-color="#d886b5"/>
  </linearGradient>
  <linearGradient id="budPurple" x1="0" y1="1" x2="0" y2="0">
    <stop offset="0" stop-color="#e4dafc"/><stop offset=".55" stop-color="#c2abf2"/><stop offset="1" stop-color="#9c83e0"/>
  </linearGradient>
  <linearGradient id="petal" x1="0" y1="1" x2="0" y2="0">
    <stop offset="0" stop-color="#efe8ff"/><stop offset=".5" stop-color="#c3aaf3"/><stop offset="1" stop-color="#a185e3"/>
  </linearGradient>
</defs>"""


def label_svg(sub, style="title"):
    parts = [f'<rect width="{W}" height="{H}" fill="{PAPER}"/>', border()]
    # corner and side sprigs (behind everything else)
    parts.append(sprig(((112, 268), (175, 182), (268, 140), (392, 152)),
                       [(0.18, "pink", -1, 50), (0.32, "leaf", 1, 44), (0.42, "purple", -1, 50),
                        (0.6, "pink", -1, 52), (0.7, "leaf", 1, 40), (0.82, "purple", -1, 46), (1.0, "pink", 0, 42)]))
    parts.append(sprig(((196, 178), (150, 258), (128, 362), (150, 478)),
                       [(0.2, "purple", 1, 46), (0.36, "pink", -1, 48), (0.5, "leaf", 1, 42),
                        (0.62, "pink", 1, 50), (0.78, "purple", -1, 46), (1.0, "pink", 0, 44)]))
    parts.append(sprig(((150, 925), (122, 860), (128, 800), (170, 745)),
                       [(0.25, "leaf", 1, 48), (0.45, "leaf", -1, 46), (0.7, "leaf", 1, 44), (1.0, "leaf", 0, 42)]))
    parts.append(sprig(((992, 1078), (958, 960), (1046, 830), (1010, 700)),
                       [(0.12, "leaf", -1, 46), (0.22, "purple", 1, 48), (0.36, "pink", -1, 46),
                        (0.5, "leaf", 1, 44), (0.58, "pink", -1, 46), (0.72, "purple", 1, 44),
                        (0.84, "leaf", -1, 40), (1.0, "pink", 0, 40)]))
    parts.append(washi_tape(1905, 214, 31))
    parts.append(decorations(style))
    if style == "fields":
        parts.append(title_block(sub["title"]))
        parts.append(quote_block(sub["quote"]))
    else:   # subject name only: big title across the top, quote + bow take the old info-box space
        parts.append(title_block(sub["title"], x=1060, y=470, fs=sub.get("title_fs", 340), maxw=1130))
        parts.append(quote_block(sub["quote"], cx=1545, y=910, gap=88, fs=76, maxw=700, div_gap=72, div_half=235))
        parts.append(bow(1545, 720, 1.1))
    parts.append(laptop(sub["screen"]))
    parts.append(mug(708, 694))
    parts.append(books(sub["books"]))
    parts.append(notebook(sub["checklist"]))
    parts.append(pen(918, 1322, -50.6))
    if style == "fields":
        parts.append(info_box())
        parts.append(bow(1537, 620, 0.95))
    parts.append(sprig(((1872, 1296), (1772, 1336), (1650, 1316), (1500, 1338)),
                       [(0.15, "leaf", 1, 42), (0.3, "purple", -1, 42), (0.45, "pink", 1, 42),
                        (0.6, "leaf", -1, 38), (0.72, "purple", 1, 40), (0.88, "leaf", -1, 36), (1.0, "pink", 0, 36)]))
    parts.append(sprig(((1944, 1214), (1966, 1150), (1946, 1090), (1972, 1018)),
                       [(0.25, "leaf", -1, 40), (0.45, "pink", 1, 38), (0.65, "leaf", -1, 36), (1.0, "purple", 0, 38)]))
    parts.append(flower(1904, 1258, 64))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            f'{DEFS}{"".join(parts)}</svg>')


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: "LabelTitle"; src: url("{fonts}/{title_font}.ttf"); }}
@font-face {{ font-family: "LabelHand"; src: url("{fonts}/PatrickHand.ttf"); }}
@font-face {{ font-family: "LabelSerif"; src: url("{fonts}/DMSerifDisplay.ttf"); }}
html, body {{ margin: 0; padding: 0; background: #fff; }}
svg {{ display: block; }}
.title {{ font-family: "LabelTitle"; }}
.hand {{ font-family: "LabelHand"; }}
.serif {{ font-family: "LabelSerif"; }}
</style></head><body>{svg}
<script>
function fit(el, maxw) {{
  let fs = parseFloat(el.getAttribute('font-size'));
  while (el.getComputedTextLength() > maxw && fs > 6) {{ fs -= 0.5; el.setAttribute('font-size', fs); }}
  return fs;
}}
async function layout() {{
  await document.fonts.load('40px LabelTitle'); await document.fonts.load('40px LabelHand');
  await document.fonts.load('40px LabelSerif'); await document.fonts.ready;
  const groups = {{}};
  document.querySelectorAll('[data-maxw]').forEach(el => {{
    const fs = fit(el, +el.dataset.maxw);
    if (el.dataset.fit) groups[el.dataset.fit] = Math.min(groups[el.dataset.fit] ?? 1e9, fs);
  }});
  document.querySelectorAll('[data-fit]').forEach(el => el.setAttribute('font-size', groups[el.dataset.fit]));
  const t = document.getElementById('title');
  document.getElementById('title-shadow').setAttribute('font-size', t.getAttribute('font-size'));
  const bb = t.getBBox(), fs = parseFloat(t.getAttribute('font-size'));
  const mid = bb.y + bb.height * 0.5;
  document.getElementById('rays-left').setAttribute('transform', `translate(${{bb.x - 10}},${{mid + fs * 0.2}})`);
  document.getElementById('rays-right').setAttribute('transform', `translate(${{bb.x + bb.width + 6}},${{mid - fs * 0.08}})`);
  document.querySelectorAll('.row').forEach(r => {{
    const lab = r.querySelector('.lab');
    const cx = Math.max(+r.dataset.colon, +lab.getAttribute('x') + lab.getComputedTextLength() + 18);
    r.querySelector('.colon').setAttribute('x', cx);
    r.querySelector('.line').setAttribute('x1', cx + 30);
  }});
  document.body.dataset.ready = '1';
}}
layout();
</script></body></html>"""


async def render(names, title_font, style="title"):
    from playwright.async_api import async_playwright
    OUT.mkdir(exist_ok=True)
    pages = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME)
        ctx = await browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=PX_W / W)
        page = await ctx.new_page()
        for name in names:
            html = OUT / f"{name}.html"
            html.write_text(PAGE.format(fonts=FONTS.as_uri(), title_font=SUBJECTS[name].get("title_font", title_font), svg=label_svg(SUBJECTS[name], style)), encoding="utf-8")
            await page.goto(html.as_uri())
            await page.wait_for_function("document.body.dataset.ready === '1'", timeout=60000)
            png = OUT / f"label-{name}.png"
            await page.screenshot(path=str(png), clip={"x": 0, "y": 0, "width": W, "height": H})
            html.unlink()
            pages.append(png)
            print("rendered", png.name)
        await browser.close()
    return pages


def make_pdf(pngs, path):
    """Two half-A4 labels per portrait A4 page, with a dashed cut line between them."""
    from PIL import Image
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    pw, ph = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle("Subject labels - Economics, Accounting, English, Statistics")
    tmp = []
    for i in range(0, len(pngs), 2):
        for slot, png in enumerate(pngs[i:i + 2]):
            jpg = png.with_suffix(".print.jpg")
            Image.open(png).convert("RGB").save(jpg, quality=93, subsampling=0, dpi=(300, 300))
            tmp.append(jpg)
            c.drawImage(str(jpg), 0, ph / 2 if slot == 0 else 0, width=pw, height=ph / 2)
        c.setStrokeColorRGB(0.72, 0.70, 0.78)
        c.setLineWidth(0.5)
        c.setDash(4, 3)
        c.line(14 * mm, ph / 2, pw - 6 * mm, ph / 2)
        c.setDash()
        # small scissors drawn as paths (no symbol font needed)
        sx, sy = 6 * mm, ph / 2
        c.setStrokeColorRGB(0.55, 0.53, 0.65)
        c.setLineWidth(0.7)
        for k in (1, -1):
            c.circle(sx + 1.3 * mm, sy + k * 1.7 * mm, 1.15 * mm, stroke=1, fill=0)
            c.line(sx + 2.3 * mm, sy + k * 1.15 * mm, sx + 7.2 * mm, sy - k * 0.9 * mm)
        c.showPage()
    c.save()
    for t in tmp:
        t.unlink()
    print("wrote", path.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=list(SUBJECTS))
    ap.add_argument("--title-font", default="Norican")
    ap.add_argument("--style", choices=["title", "fields"], default="title",
                    help="title = subject name only (default); fields = with Name/Class/... write-in box")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--pdf-only", action="store_true", help="rebuild the PDF from existing PNGs")
    args = ap.parse_args()
    names = args.only or list(SUBJECTS)
    if args.pdf_only:
        pngs = [OUT / f"label-{n}.png" for n in names]
    else:
        pngs = asyncio.run(render(names, args.title_font, args.style))
    if not args.no_pdf and len(names) == len(SUBJECTS):
        make_pdf(pngs, OUT / "subject-labels-A4.pdf")


if __name__ == "__main__":
    main()
