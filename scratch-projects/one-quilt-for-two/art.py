"""Original artwork for 'One Quilt for Two' (SVG, generated)."""
import math, os
OUT = os.path.join(os.path.dirname(__file__), "art")
os.makedirs(OUT, exist_ok=True)

def save(name, body, W, H, defs=""):
    with open(f"{OUT}/{name}.svg", "w") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><defs>{defs}</defs>{body}</svg>')

# ---------- quilt (Grandma's heart quilt) ----------
QC = ["#d9534f", "#f7f1e1", "#3aa6a0", "#f4c542"]
def heart(cx, cy, s, col="#d9534f"):
    return (f'<path d="M{cx} {cy+s*0.9} C{cx-s*1.4} {cy-s*0.1} {cx-s*0.6} {cy-s*1.1} {cx} {cy-s*0.35} '
            f'C{cx+s*0.6} {cy-s*1.1} {cx+s*1.4} {cy-s*0.1} {cx} {cy+s*0.9} Z" fill="{col}"/>')
def quilt_grid(x, y, cols, rows, s):
    o = ""
    for r in range(rows):
        for c in range(cols):
            col = QC[(r + c * 3) % 4]
            o += f'<rect x="{x+c*s}" y="{y+r*s}" width="{s}" height="{s}" fill="{col}"/>'
            if col == "#f7f1e1":
                o += heart(x + c*s + s/2, y + r*s + s/2, s*0.22)
            o += f'<rect x="{x+c*s+3}" y="{y+r*s+3}" width="{s-6}" height="{s-6}" fill="none" stroke="#ffffff" stroke-opacity=".7" stroke-width="1.5" stroke-dasharray="4 3"/>'
    return o

# ---------- bears ----------
PAL = {
    "bramble": dict(fur="#8a4a24", belly="#b8774a", muz="#e0b088", ear="#c98a5a", stk="#4f270f", nose="#2b1a12"),
    "frost": dict(fur="#f3eee2", belly="#ffffff", muz="#e9e1cc", ear="#e3d9c0", stk="#bdb398", nose="#2b2b33"),
}

def mouth(kind, nose):
    m = {
        "smile": f'<path d="M100 89 V97" stroke="{nose}" stroke-width="3"/><path d="M86 96 Q100 110 114 96" stroke="{nose}" stroke-width="3" fill="none" stroke-linecap="round"/>',
        "open": f'<path d="M100 89 V95" stroke="{nose}" stroke-width="3"/><ellipse cx="100" cy="103" rx="9" ry="8" fill="#6e2424"/><ellipse cx="100" cy="107" rx="5" ry="3" fill="#e57a7a"/>',
        "grin": f'<path d="M100 89 V95" stroke="{nose}" stroke-width="3"/><path d="M84 96 Q100 124 116 96 Z" fill="#6e2424"/><ellipse cx="100" cy="109" rx="7" ry="3.5" fill="#e57a7a"/>',
        "flat": f'<path d="M100 89 V97" stroke="{nose}" stroke-width="3"/><path d="M90 100 Q100 97 110 100" stroke="{nose}" stroke-width="3" fill="none" stroke-linecap="round"/>',
        "osmall": f'<path d="M100 89 V96" stroke="{nose}" stroke-width="3"/><circle cx="100" cy="102" r="4.5" fill="#6e2424"/>',
        "obig": f'<path d="M100 89 V94" stroke="{nose}" stroke-width="3"/><ellipse cx="100" cy="105" rx="9" ry="11" fill="#6e2424"/>',
        "yawn": f'<ellipse cx="100" cy="104" rx="14" ry="16" fill="#6e2424"/><ellipse cx="100" cy="112" rx="8" ry="5" fill="#e57a7a"/>',
        "shiver": f'<path d="M84 100 l5 -5 l5 5 l5 -5 l5 5 l5 -5 l5 5" stroke="{nose}" stroke-width="3" fill="none" stroke-linejoin="round"/>',
        "shiver_o": f'<rect x="83" y="94" width="34" height="14" rx="6" fill="#6e2424"/><path d="M85 97 l4 4 l4 -4 l4 4 l4 -4 l4 4 l4 -4 l4 4" stroke="#fff" stroke-width="2.5" fill="none"/>',
        "sad": f'<path d="M100 89 V97" stroke="{nose}" stroke-width="3"/><path d="M88 104 Q100 95 112 104" stroke="{nose}" stroke-width="3" fill="none" stroke-linecap="round"/>',
    }
    return m[kind]

def eyes(kind, stk):
    o = ""
    for ex in (80, 120):
        if kind == "open":
            o += f'<circle cx="{ex}" cy="66" r="9" fill="#fff"/><circle cx="{ex+1}" cy="68" r="5.5" fill="#1d1d24"/><circle cx="{ex+3}" cy="65" r="2" fill="#fff"/>'
        elif kind == "wide":
            o += f'<circle cx="{ex}" cy="65" r="11.5" fill="#fff"/><circle cx="{ex}" cy="66" r="4" fill="#1d1d24"/>'
        elif kind == "happy":
            o += f'<path d="M{ex-9} 70 Q{ex} 56 {ex+9} 70" stroke="#1d1d24" stroke-width="4" fill="none" stroke-linecap="round"/>'
        elif kind == "closed":
            o += f'<path d="M{ex-9} 66 Q{ex} 74 {ex+9} 66" stroke="#1d1d24" stroke-width="4" fill="none" stroke-linecap="round"/>'
        elif kind == "worry":
            a, b = (52, 58) if ex == 80 else (58, 52)
            o += f'<circle cx="{ex}" cy="68" r="9" fill="#fff"/><circle cx="{ex}" cy="71" r="5" fill="#1d1d24"/><path d="M{ex-11} {a} L{ex+11} {b}" stroke="{stk}" stroke-width="4" stroke-linecap="round"/>'
        elif kind == "sleepy":
            o += f'<circle cx="{ex}" cy="67" r="8" fill="#fff"/><circle cx="{ex}" cy="70" r="4.5" fill="#1d1d24"/><rect x="{ex-10}" y="56" width="20" height="10" fill="CURFUR"/><path d="M{ex-9} 66 H{ex+9}" stroke="#1d1d24" stroke-width="3"/>'
        elif kind == "look":   # looking sideways (to the right)
            o += f'<circle cx="{ex}" cy="66" r="9" fill="#fff"/><circle cx="{ex+4}" cy="67" r="5" fill="#1d1d24"/>'
    return o

def arm(cx, cy, rot, p):
    return f'<ellipse cx="{cx}" cy="{cy}" rx="15" ry="40" transform="rotate({rot} {cx} {cy})" fill="{p["fur"]}" stroke="{p["stk"]}" stroke-width="3"/>'

def bear(who, legs="stand", arms="down", eye="open", mth="smile", cold=False, wrap=False, blush=True):
    p = PAL[who]
    o = ""
    if legs in ("stand", "step1", "step2"):
        ll, rl = (68, 208), (132, 208)
        if legs == "step1": ll, rl = (60, 200), (138, 214)
        if legs == "step2": ll, rl = (72, 214), (130, 200)
        for cx, cy in (ll, rl):
            o += f'<ellipse cx="{cx}" cy="{cy}" rx="21" ry="26" fill="{p["fur"]}" stroke="{p["stk"]}" stroke-width="3"/><ellipse cx="{cx}" cy="{cy+18}" rx="12" ry="6" fill="{p["ear"]}"/>'
    o += f'<ellipse cx="100" cy="150" rx="58" ry="62" fill="{p["fur"]}" stroke="{p["stk"]}" stroke-width="3"/><ellipse cx="100" cy="164" rx="36" ry="42" fill="{p["belly"]}"/>'
    if legs == "sitfloor":
        for cx in (66, 134):
            o += f'<ellipse cx="{cx}" cy="212" rx="24" ry="18" fill="{p["fur"]}" stroke="{p["stk"]}" stroke-width="3"/><ellipse cx="{cx}" cy="214" rx="13" ry="10" fill="{p["ear"]}"/>'
    A = {"down": [(42, 152, 12), (158, 152, -12)], "wave": [(42, 152, 12), (168, 102, -155)],
         "open": [(34, 128, 55), (166, 128, -55)], "hug": [(72, 158, -55), (128, 158, 55)],
         "hold": [(64, 150, -28), (136, 150, 28)], "up": [(40, 96, 160), (160, 96, -160)]}[arms]
    if wrap:
        o += ('<path d="M38 112 Q100 92 162 112 L170 222 Q100 236 30 222 Z" fill="#f7f1e1" stroke="#b5413d" stroke-width="3"/>'
              '<g clip-path="url(#wq)">' + quilt_grid(26, 96, 6, 5, 26) + '</g>')
    else:
        for a in A:
            o += arm(*a, p)
    o += f'<circle cx="62" cy="36" r="15" fill="{p["fur"]}" stroke="{p["stk"]}" stroke-width="3"/><circle cx="62" cy="36" r="8" fill="{p["ear"]}"/><circle cx="138" cy="36" r="15" fill="{p["fur"]}" stroke="{p["stk"]}" stroke-width="3"/><circle cx="138" cy="36" r="8" fill="{p["ear"]}"/>'
    o += f'<circle cx="100" cy="72" r="45" fill="{p["fur"]}" stroke="{p["stk"]}" stroke-width="3"/>'
    if who == "bramble":   # mustard knitted scarf
        o += ('<path d="M57 110 Q100 132 143 110 L146 128 Q100 152 54 128 Z" fill="#e2a72e" stroke="#a8730f" stroke-width="2.5"/>'
              '<path d="M68 118 v14 M84 124 v14 M100 126 v14 M116 124 v14 M132 118 v14" stroke="#f7d77a" stroke-width="4"/>'
              '<path d="M60 126 l-14 50 l16 4 l12 -48 Z" fill="#e2a72e" stroke="#a8730f" stroke-width="2.5"/>'
              '<path d="M48 176 l-2 9 M54 178 l-1 9 M60 180 l0 9" stroke="#a8730f" stroke-width="3"/>')
    o += f'<ellipse cx="100" cy="92" rx="23" ry="17" fill="{p["muz"]}"/><ellipse cx="100" cy="83" rx="9" ry="6.5" fill="{p["nose"]}"/>'
    if blush and not cold:
        o += '<ellipse cx="66" cy="88" rx="8" ry="5" fill="#f29a9a" opacity=".55"/><ellipse cx="134" cy="88" rx="8" ry="5" fill="#f29a9a" opacity=".55"/>'
    if cold:
        o += '<ellipse cx="66" cy="88" rx="9" ry="6" fill="#8fc0ee" opacity=".7"/><ellipse cx="134" cy="88" rx="9" ry="6" fill="#8fc0ee" opacity=".7"/>'
    o += mouth(mth, p["nose"])
    o += eyes(eye, p["stk"]).replace("CURFUR", p["fur"])
    if who == "frost":     # blue earmuffs
        o += ('<path d="M52 44 Q100 -8 148 44" stroke="#2f6fd0" stroke-width="9" fill="none" stroke-linecap="round"/>'
              '<circle cx="56" cy="44" r="17" fill="#4b8ef0" stroke="#2559a8" stroke-width="3"/><circle cx="144" cy="44" r="17" fill="#4b8ef0" stroke="#2559a8" stroke-width="3"/>'
              '<circle cx="51" cy="39" r="5" fill="#a9cbff"/><circle cx="139" cy="39" r="5" fill="#a9cbff"/>')
    if cold:
        o += '<path d="M12 96 l-9 6 l9 6 M188 96 l9 6 l-9 6 M14 150 l-9 6 l9 6 M186 150 l9 6 l-9 6" stroke="#5b9de0" stroke-width="3" fill="none" stroke-linecap="round"/>'
    defs = '<clipPath id="wq"><path d="M38 112 Q100 92 162 112 L170 222 Q100 236 30 222 Z"/></clipPath>' if wrap else ""
    return o, defs

def lying(who, eye="closed", quilt=False, cold=False):
    p = PAL[who]
    o = (f'<ellipse cx="120" cy="86" rx="92" ry="34" fill="{p["fur"]}" stroke="{p["stk"]}" stroke-width="3"/>'
         f'<circle cx="206" cy="70" r="32" fill="{p["fur"]}" stroke="{p["stk"]}" stroke-width="3"/>'
         f'<circle cx="190" cy="42" r="11" fill="{p["fur"]}" stroke="{p["stk"]}" stroke-width="3"/>'
         f'<ellipse cx="226" cy="82" rx="14" ry="11" fill="{p["muz"]}"/><ellipse cx="236" cy="78" rx="6" ry="4.5" fill="{p["nose"]}"/>')
    if who == "bramble":
        o += '<path d="M176 92 Q186 70 180 50 L192 52 Q198 74 188 96 Z" fill="#e2a72e" stroke="#a8730f" stroke-width="2"/>'
    else:
        o += '<path d="M184 46 Q206 22 228 40" stroke="#2f6fd0" stroke-width="7" fill="none"/><circle cx="190" cy="48" r="12" fill="#4b8ef0" stroke="#2559a8" stroke-width="2.5"/>'
    if eye == "closed":
        o += '<path d="M200 68 Q208 75 216 68" stroke="#1d1d24" stroke-width="3.5" fill="none" stroke-linecap="round"/>'
    else:
        o += '<circle cx="208" cy="66" r="8" fill="#fff"/><circle cx="210" cy="68" r="4" fill="#1d1d24"/>'
    if cold:
        o += ('<path d="M10 70 l-8 6 l8 6 M20 110 l-8 6 l8 6 M150 24 l-4 -9 l9 -4" stroke="#5b9de0" stroke-width="3" fill="none" stroke-linecap="round"/>'
              '<ellipse cx="200" cy="84" rx="7" ry="5" fill="#8fc0ee" opacity=".7"/><path d="M214 88 l3 -3 l3 3 l3 -3" stroke="#222" stroke-width="2" fill="none"/>')
    else:
        o += '<ellipse cx="200" cy="84" rx="7" ry="5" fill="#f29a9a" opacity=".55"/>'
    if quilt:
        o += '<g clip-path="url(#lq)">' + quilt_grid(30, 50, 7, 3, 26) + '</g><path d="M30 54 Q110 44 196 54" stroke="#b5413d" stroke-width="3" fill="none"/>'
        return o, '<clipPath id="lq"><path d="M30 54 Q110 44 196 54 L200 128 L26 128 Z"/></clipPath>'
    return o, ""

BEAR_POSES = {   # pose: (legs, arms, eyes, closed mouth, open mouth, cold)
    "idle": ("stand", "down", "open", "smile", "open", False),
    "happy": ("stand", "open", "happy", "smile", "grin", False),
    "worry": ("stand", "down", "worry", "sad", "osmall", False),
    "wave": ("stand", "wave", "happy", "smile", "grin", False),
    "carry": ("stand", "hold", "open", "smile", "open", False),
    "surprised": ("stand", "down", "wide", "osmall", "obig", False),
    "yawn": ("stand", "up", "closed", "flat", "yawn", False),
    "cold": ("stand", "hug", "wide", "shiver", "shiver_o", True),
    "sip": ("stand", "hold", "closed", "smile", "open", False),
    "sit": ("none", "down", "happy", "smile", "grin", False),
    "look": ("stand", "down", "look", "smile", "open", False),
}

def make_bears():
    for who in ("bramble", "frost"):
        for pose, (lg, ar, ey, mc, mo, cold) in BEAR_POSES.items():
            for suffix, m in (("", mc), ("_o", mo)):
                b, d = bear(who, lg, ar, ey, m, cold)
                save(f"{who}_{pose}{suffix}", b, 200, 240, d)
        for name, kw in {"walk1": dict(legs="step1"), "walk2": dict(legs="step2"),
                         "skate1": dict(legs="step1", arms="open", eye="happy", mth="grin"),
                         "skate2": dict(legs="step2", arms="open", eye="happy", mth="smile"),
                         "fall": dict(legs="sitfloor", arms="up", eye="wide", mth="obig"),
                         "sitsleep": dict(legs="none", arms="down", eye="closed", mth="smile"),
                         "wrap": dict(legs="stand", eye="happy", mth="smile", wrap=True)}.items():
            b, d = bear(who, **kw)
            save(f"{who}_{name}", b, 200, 240, d)
        for name, kw in {"sleep": dict(), "sleep_quilt": dict(quilt=True), "sleep_quilt_open": dict(eye="open", quilt=True),
                         "lie_cold": dict(eye="open", cold=True)}.items():
            b, d = lying(who, **kw)
            save(f"{who}_{name}", b, 250, 130, d)

# ---------- puffins ----------
def puffin(kind):
    wing = lambda cx, rot: f'<ellipse cx="{cx}" cy="40" rx="7" ry="17" transform="rotate({rot} {cx} 40)" fill="#23232e"/>'
    up = 0
    if kind == "hop": up = -7
    wings = (wing(15, 8) + wing(49, -8)) if kind != "flap" else (wing(10, -55) + wing(54, 55))
    feet = '<ellipse cx="25" cy="66" rx="7" ry="3.5" fill="#f08a24"/><ellipse cx="39" cy="66" rx="7" ry="3.5" fill="#f08a24"/>'
    body = (f'<g transform="translate(0 {up})">{wings}<ellipse cx="32" cy="42" rx="18" ry="21" fill="#2b2b3a"/>'
            '<ellipse cx="32" cy="48" rx="12" ry="15" fill="#fff"/><circle cx="32" cy="21" r="14" fill="#2b2b3a"/>'
            '<ellipse cx="32" cy="23" rx="10.5" ry="9" fill="#fff"/><circle cx="27.5" cy="20" r="2.6" fill="#111"/><circle cx="36.5" cy="20" r="2.6" fill="#111"/>'
            '<path d="M24 17 l4 -2 M40 17 l-4 -2" stroke="#9a9aa8" stroke-width="1.5"/>'
            '<path d="M32 23 L43 27 L32 33 Z" fill="#f08a24"/><path d="M36 25 L36 31" stroke="#f4c542" stroke-width="2"/>'
            '<ellipse cx="23" cy="27" rx="3" ry="2" fill="#f29a9a"/><ellipse cx="41" cy="27" rx="3" ry="2" fill="#f29a9a"/></g>')
    if kind == "slide":
        return f'<g transform="rotate(80 36 40) translate(4 6)">{body}</g>'
    return feet + body

def make_puffins():
    for k in ("stand", "hop", "flap", "slide"):
        save(f"puffin_{k}", puffin(k), 72, 76)

# ---------- props ----------
def make_props():
    snow = lambda cx, cy, r: f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffffff" stroke="#b7d3e6" stroke-width="3"/>'
    base = snow(80, 150, 46)
    mid = snow(80, 88, 32)
    top = snow(80, 44, 22)
    face = ('<circle cx="73" cy="40" r="3" fill="#333"/><circle cx="87" cy="40" r="3" fill="#333"/>'
            '<path d="M80 46 L104 50 L80 52 Z" fill="#f08a24"/><circle cx="80" cy="80" r="3" fill="#333"/><circle cx="80" cy="92" r="3" fill="#333"/>'
            '<path d="M50 88 L22 70 M30 75 l-6 -9 M110 88 L138 70 M130 75 l6 -9" stroke="#7a4a22" stroke-width="4" stroke-linecap="round"/>'
            '<rect x="62" y="14" width="36" height="10" rx="3" fill="#3aa6a0"/><rect x="68" y="0" width="24" height="18" rx="3" fill="#3aa6a0"/>')
    save("snowman_1", base, 160, 200); save("snowman_2", base + mid, 160, 200); save("snowman_3", base + mid + top + face, 160, 200)
    save("sled", '<path d="M10 70 Q4 84 20 86 H150 Q166 86 162 72" stroke="#8a5a2b" stroke-width="6" fill="none"/>'
         '<rect x="22" y="54" width="128" height="14" rx="4" fill="#c98a4a" stroke="#8a5a2b" stroke-width="3"/>'
         '<path d="M30 54 Q40 10 86 14 Q130 18 138 54 Z" fill="#8c6b4a" stroke="#5e4428" stroke-width="3"/>'
         '<path d="M84 14 V54" stroke="#5e4428" stroke-width="3"/><rect x="100" y="26" width="22" height="28" rx="5" fill="#6a3d9a" stroke="#40205f" stroke-width="2"/>'
         '<path d="M40 34 Q56 28 70 36 L68 50 Q54 44 42 48 Z" fill="#d9534f"/><path d="M170 72 Q190 60 200 64" stroke="#7a4a22" stroke-width="3" fill="none"/>', 204, 92)
    save("jar", '<rect x="6" y="14" width="40" height="46" rx="10" fill="#6a3d9a" stroke="#40205f" stroke-width="3"/>'
         '<path d="M4 14 Q26 0 48 14 Z" fill="#d9534f" stroke="#9a2d2a" stroke-width="2"/><rect x="12" y="28" width="28" height="18" rx="3" fill="#f7f1e1"/>'
         '<circle cx="21" cy="37" r="4" fill="#3b4fb0"/><circle cx="30" cy="37" r="4" fill="#3b4fb0"/>', 52, 62)
    for nm, col in (("cup_red", "#e86a4a"), ("cup_blue", "#4a9be8")):
        save(nm, f'<path d="M14 6 q-4 -6 0 -10 M24 6 q-4 -6 0 -10" stroke="#ffffff" stroke-width="2.5" fill="none" opacity=".9"/>'
             f'<rect x="6" y="10" width="28" height="30" rx="6" fill="{col}" stroke="#333" stroke-width="2"/>'
             f'<path d="M34 16 q12 2 0 16" stroke="#333" stroke-width="3" fill="none"/><ellipse cx="20" cy="13" rx="11" ry="3" fill="#7a4a22"/>', 50, 44)
    save("snowball", snow(14, 14, 11), 28, 28)
    save("splat", '<path d="M30 6 l6 12 l14 -6 l-6 14 l14 6 l-14 6 l6 14 l-14 -6 l-6 14 l-6 -14 l-14 6 l6 -14 l-14 -6 l14 -6 l-6 -14 l14 6 Z" fill="#ffffff" stroke="#b7d3e6" stroke-width="2"/>', 64, 64)
    save("shovel", '<g transform="rotate(25 40 70)"><rect x="36" y="0" width="8" height="96" rx="4" fill="#9a6a3a" stroke="#5e4428" stroke-width="2"/>'
         '<path d="M22 92 H58 V124 Q40 138 22 124 Z" fill="#9aa8b6" stroke="#5a6672" stroke-width="3"/></g>', 100, 150)
    q = quilt_grid
    save("quilt_folded", '<rect x="4" y="10" width="92" height="56" rx="10" fill="#f7f1e1" stroke="#b5413d" stroke-width="3"/>'
         '<g clip-path="url(#f)">' + q(4, 10, 4, 3, 23) + '</g><path d="M4 30 H96 M4 48 H96" stroke="#b5413d" stroke-width="2.5"/>', 100, 70,
         '<clipPath id="f"><rect x="4" y="10" width="92" height="56" rx="10"/></clipPath>')
    save("quilt_wide", '<path d="M10 22 Q140 -4 270 22 L282 116 Q140 138 -2 116 Z" fill="#f7f1e1" stroke="#b5413d" stroke-width="3"/>'
         '<g clip-path="url(#w)">' + q(-4, 4, 10, 5, 30) + '</g>', 284, 132,
         '<clipPath id="w"><path d="M10 22 Q140 -4 270 22 L282 116 Q140 138 -2 116 Z"/></clipPath>')
    save("drift", '<path d="M0 220 Q-4 90 60 50 Q100 0 150 40 Q214 70 210 220 Z" fill="#f8fcff" stroke="#bcd7ea" stroke-width="4"/>'
         '<path d="M40 120 q30 -20 60 0 M90 170 q30 -20 70 -4 M30 190 q24 -14 50 0" stroke="#cfe3f2" stroke-width="4" fill="none"/>', 212, 224)
    save("heart", heart(20, 20, 16, "#e8505b"), 40, 40)
    save("flake", '<circle cx="6" cy="6" r="5" fill="#ffffff" opacity=".95"/>', 12, 12)
    save("bigflake", '<circle cx="9" cy="9" r="8" fill="#ffffff" opacity=".9"/>', 18, 18)
    save("star", '<path d="M8 0 L10 6 L16 8 L10 10 L8 16 L6 10 L0 8 L6 6 Z" fill="#fff6c8"/>', 16, 16)

def card(name, lines, size=40, color="#ffffff", W=440, H=150):
    t = ""
    y0 = H/2 - (len(lines)-1)*size*0.62 + size*0.35
    for i, (txt, sz) in enumerate(lines):
        y = y0 + i*size*1.25
        t += (f'<text x="{W/2}" y="{y}" text-anchor="middle" font-family="Sans Serif" font-weight="bold" font-size="{sz}" '
              f'fill="{color}" stroke="#1d3c6e" stroke-width="7" stroke-linejoin="round" paint-order="stroke">{txt}</text>')
    save(name, t, W, H)

def make_cards():
    card("card_title", [("One Quilt", 54), ("for Two", 54)], size=52)
    card("card_storm", [("That night,", 34), ("a big storm came...", 34)], size=36)
    card("card_morning", [("The next morning...", 34)], size=36, H=90)
    card("card_end", [("The End", 60)], size=60, H=110)
    card("card_credits", [("Made in Scratch", 30), ("with scratch-mcp", 26), ("Thanks for watching!", 26)], size=32, H=170)

# ---------- backdrops ----------
def grad(id_, stops, vertical=True):
    s = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return f'<linearGradient id="{id_}" x1="0" y1="0" x2="{0 if vertical else 1}" y2="{1 if vertical else 0}">{s}</linearGradient>'

def mountains(c1, c2):
    return (f'<path d="M0 230 L60 150 L110 200 L170 120 L240 210 L300 140 L360 205 L420 130 L480 190 V260 H0Z" fill="{c1}"/>'
            f'<path d="M170 120 L190 150 L178 148 L160 165 L150 140 Z M420 130 L440 160 L425 156 L410 170 L404 150 Z M60 150 L74 170 L50 172 Z" fill="{c2}"/>')

def igloo(fill, line, door):
    o = (f'<path d="M300 268 Q300 150 390 150 Q480 150 480 268 Z" fill="{fill}" stroke="{line}" stroke-width="4"/>'
         f'<path d="M318 210 H470 M306 240 H478 M330 182 H452 M362 160 H420" stroke="{line}" stroke-width="2.5" opacity=".7"/>'
         f'<path d="M350 182 v28 M410 182 v28 M380 210 v30 M440 210 v30 M330 240 v28 M400 240 v28 M460 240 v28 M392 160 v22" stroke="{line}" stroke-width="2.5" opacity=".7"/>'
         f'<path d="M250 268 V226 Q250 196 284 196 H318 V268 Z" fill="{fill}" stroke="{line}" stroke-width="4"/>'
         f'<path d="M258 268 V234 Q258 214 280 214 Q302 214 302 234 V268 Z" fill="{door}"/>')
    return o

def outside(sky, sun, ground1, ground2, mt1, mt2, igfill, igline, door, extra=""):
    return ('<rect width="480" height="360" fill="url(#sky)"/>' + sun + mountains(mt1, mt2) +
            f'<path d="M0 250 Q120 222 250 246 T480 240 V360 H0Z" fill="{ground1}"/>' + igloo(igfill, igline, door) +
            f'<path d="M0 300 Q140 272 300 296 T480 292 V360 H0Z" fill="{ground2}"/>'
            '<ellipse cx="70" cy="318" rx="34" ry="9" fill="#5c8fb0"/><path d="M98 318 V286" stroke="#7a4a22" stroke-width="3"/><path d="M98 286 L118 292 L98 298 Z" fill="#d9534f"/>' + extra)

def interior(top, bot, wall, line, lamp_on, floor, bed, window_fill, glow=""):
    lamp = ('<circle cx="240" cy="96" r="70" fill="#ffd36a" opacity=".22"/><circle cx="240" cy="96" r="38" fill="#ffd36a" opacity=".3"/>' if lamp_on else "")
    return (f'<rect width="480" height="360" fill="url(#bg)"/>'
            f'<path d="M0 0 H480 V270 H0 Z" fill="{wall}" opacity=".35"/>'
            + "".join(f'<path d="M0 {y} Q240 {y-40} 480 {y}" stroke="{line}" stroke-width="2.5" fill="none" opacity=".55"/>' for y in (60, 115, 170, 225))
            + "".join(f'<path d="M{x} {y} v-48" stroke="{line}" stroke-width="2.5" opacity=".45"/>' for x, y in ((80, 105), (200, 92), (320, 92), (430, 108), (130, 160), (260, 150), (380, 160), (60, 215), (190, 205), (300, 205), (420, 215)))
            + glow + lamp +
            f'<circle cx="405" cy="88" r="34" fill="{window_fill}" stroke="{line}" stroke-width="6"/><path d="M405 54 V122 M371 88 H439" stroke="{line}" stroke-width="3" opacity=".6"/>'
            '<rect x="214" y="104" width="52" height="8" rx="3" fill="#b9a27a"/><path d="M228 104 Q240 80 252 104 Z" fill="#c98a4a"/><path d="M240 84 q-5 -8 0 -14 q5 6 0 14" fill="' + ("#ffb02e" if lamp_on else "#7f6a4a") + '"/>'
            '<rect x="40" y="70" width="90" height="8" rx="3" fill="#b9a27a"/><rect x="50" y="52" width="16" height="18" rx="3" fill="#e86a4a"/><rect x="74" y="48" width="14" height="22" rx="3" fill="#4a9be8"/><circle cx="104" cy="62" r="9" fill="#f4c542"/>'
            f'<rect y="290" width="480" height="70" fill="{floor}"/>'
            f'<rect x="12" y="250" width="156" height="48" rx="22" fill="{bed}" stroke="{line}" stroke-width="3"/>'
            f'<rect x="312" y="250" width="156" height="48" rx="22" fill="{bed}" stroke="{line}" stroke-width="3"/>'
            f'<rect x="186" y="255" width="108" height="16" rx="6" fill="{bed}" stroke="{line}" stroke-width="3"/><rect x="204" y="270" width="14" height="24" fill="{bed}" stroke="{line}" stroke-width="2"/><rect x="262" y="270" width="14" height="24" fill="{bed}" stroke="{line}" stroke-width="2"/>')

def make_backdrops():
    sun_low = '<circle cx="240" cy="236" r="70" fill="#fff1c9" opacity=".45"/><circle cx="240" cy="236" r="42" fill="#ffe7a0"/>'
    save("bg_sunrise", '<rect width="480" height="360" fill="url(#sky)"/>' + sun_low +
         '<path d="M0 240 Q120 200 260 236 T480 226 V360 H0Z" fill="#f6e3ec"/><path d="M0 286 Q160 250 320 280 T480 272 V360 H0Z" fill="#fdf6f8"/>'
         '<path d="M400 238 Q400 214 418 214 Q436 214 436 238 Z" fill="#fff" stroke="#e3c4d4" stroke-width="2"/>', 480, 360,
         grad("sky", [(0, "#8fb5e8"), (0.55, "#f4b6c2"), (1, "#ffd9a8")]))
    sun = '<circle cx="90" cy="70" r="44" fill="#fff6c8" opacity=".55"/><circle cx="90" cy="70" r="26" fill="#fffbe2"/>'
    save("bg_outside", outside("", sun, "#eaf4fa", "#f9fcfe", "#cfe3f1", "#ffffff", "#f6fbff", "#9cc1d8", "#4f8fb0"), 480, 360,
         grad("sky", [(0, "#8fcbe8"), (1, "#e6f5fb")]))
    sun_e = '<circle cx="110" cy="200" r="54" fill="#ffd0a0" opacity=".5"/><circle cx="110" cy="200" r="30" fill="#ffe2b8"/>'
    save("bg_evening", outside("", sun_e, "#f3e1e4", "#fbf0f0", "#c9b6d8", "#efe6f6", "#fbf2f4", "#c7a7bd", "#7a5f8c"), 480, 360,
         grad("sky", [(0, "#6f7fc8"), (0.6, "#e9a3b4"), (1, "#ffcf9e")]))
    streaks = "".join(f'<path d="M{x} {y} l60 18" stroke="#ffffff" stroke-width="2" opacity=".35"/>' for x, y in ((20, 40), (140, 90), (300, 30), (380, 120), (60, 170), (220, 150), (400, 210), (120, 250)))
    save("bg_storm", outside("", '<circle cx="80" cy="60" r="20" fill="#9fb0cc" opacity=".5"/>', "#8fa3c4", "#a7b8d4", "#4f6188", "#7d8fb4", "#a9b9d3", "#5f7196", "#1d2a44", streaks), 480, 360,
         grad("sky", [(0, "#1a2442"), (1, "#3d5482")]))
    save("bg_inside_day", interior("", "", "#e7f3fa", "#8fb6d3", True, "#cfe2ef", "#f4f9fc", "#bfe6ff"), 480, 360,
         grad("bg", [(0, "#cfe8f6"), (1, "#a9cfe6")]))
    save("bg_inside_night", interior("", "", "#2a4d7a", "#6f97c4", False, "#2e5a86", "#a9c4e0", "#0f1f3d",
         '<circle cx="405" cy="88" r="60" fill="#9cc7ff" opacity=".18"/>') + "", 480, 360,
         grad("bg", [(0, "#152d55"), (1, "#24477a")]))
    save("bg_inside_warm", interior("", "", "#f2c38f", "#c98a5a", True, "#c98a62", "#f7e3c9", "#26395f",
         '<circle cx="240" cy="200" r="230" fill="#ffcf7a" opacity=".18"/>'), 480, 360,
         grad("bg", [(0, "#e9a86a"), (1, "#b6714e")]))
    # door seen from inside (opening shows the morning outside)
    save("bg_door", '<rect width="480" height="360" fill="url(#bg)"/>'
         + "".join(f'<path d="M0 {y} Q240 {y-40} 480 {y}" stroke="#8fb6d3" stroke-width="2.5" fill="none" opacity=".55"/>' for y in (60, 115, 170, 225))
         + '<path d="M130 300 V170 Q130 70 240 70 Q350 70 350 170 V300 Z" fill="#d8eef9" stroke="#8fb6d3" stroke-width="10"/>'
         '<path d="M140 300 V172 Q140 82 240 82 Q340 82 340 172 V300 Z" fill="url(#out)"/>'
         '<circle cx="290" cy="130" r="22" fill="#fffbe2"/><path d="M140 250 Q240 225 340 250 V300 H140 Z" fill="#ffffff"/>'
         '<rect y="290" width="480" height="70" fill="#cfe2ef"/>', 480, 360,
         grad("bg", [(0, "#cfe8f6"), (1, "#a9cfe6")]) + grad("out", [(0, "#9fd3f0"), (1, "#e8f7ff")]))
    refl = "".join(f'<path d="M{x} {y} q40 -10 80 0" stroke="#ffffff" stroke-width="2.5" fill="none" opacity=".6"/>' for x, y in ((20, 270), (160, 300), (300, 280), (380, 330), (90, 340), (240, 330)))
    save("bg_rink", '<rect width="480" height="360" fill="url(#sky)"/><circle cx="380" cy="80" r="30" fill="#fffbe2"/>' + mountains("#c9dcef", "#ffffff")
         + '<path d="M0 225 Q240 205 480 225 V360 H0Z" fill="#f4f9fc"/><path d="M0 245 Q240 228 480 245 V360 H0Z" fill="#b6e1ea"/>' + refl
         + '<path d="M0 245 Q240 228 480 245" stroke="#ffffff" stroke-width="4" fill="none"/>', 480, 360,
         grad("sky", [(0, "#a8c8f0"), (1, "#f6d6e4")]))
    stars = "".join(f'<circle cx="{(i*97)%480}" cy="{(i*53)%200}" r="{1 + (i % 3) * 0.6}" fill="#fff" opacity=".8"/>' for i in range(40))
    save("bg_aurora", '<rect width="480" height="360" fill="url(#sky)"/>' + stars +
         '<path d="M-20 140 Q80 60 180 120 T380 90 T520 110" stroke="#5ff0b0" stroke-width="34" fill="none" opacity=".35"/>'
         '<path d="M-20 110 Q100 40 220 100 T500 60" stroke="#9a7bff" stroke-width="22" fill="none" opacity=".3"/>'
         '<path d="M0 170 Q120 120 240 160 T480 140" stroke="#5ff0b0" stroke-width="14" fill="none" opacity=".25"/>'
         '<path d="M0 290 Q70 230 170 250 Q210 262 240 300 V360 H0Z" fill="#dfe9f7"/>'
         '<path d="M60 248 Q60 222 84 222 Q108 222 108 248 Z" fill="#f4f8ff" stroke="#9fb6d6" stroke-width="2"/>'
         '<path d="M240 300 Q300 200 380 210 Q450 220 480 260 V360 H240Z" fill="#6d5a4a"/><path d="M330 300 Q330 252 362 252 Q394 252 394 300 Z" fill="#ffb560"/>'
         '<path d="M0 320 Q240 296 480 320 V360 H0Z" fill="#eef4fc"/>', 480, 360,
         grad("sky", [(0, "#081733"), (1, "#25407a")]))
    save("bg_credits", '<rect width="480" height="360" fill="url(#sky)"/>' + stars, 480, 360, grad("sky", [(0, "#0d1f40"), (1, "#2b4c86")]))

if __name__ == "__main__":
    make_bears(); make_puffins(); make_props(); make_cards(); make_backdrops()
    print(len(os.listdir(OUT)), "svg files")
