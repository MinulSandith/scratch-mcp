"""Original stock art (SVG) that add_stock_art can drop into a project:
a cute robot, a tiny alien, a cookie, a futuristic kitchen backdrop and a title card."""

from __future__ import annotations

from xml.sax.saxutils import escape as esc

HEAD = "#8fd3ff"
HEAD_LINE = "#2d6fa8"
BODY = "#ffb84d"
BODY_LINE = "#b8741a"
GLOW = "#7ff3ff"


def _svg(w: int, h: int, inner: str, defs: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f"<defs>{defs}</defs>{inner}</svg>"
    )


def _limb(x1, y1, x2, y2, fill, line, width=12):
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{line}" stroke-width="{width + 5}" stroke-linecap="round"/>'
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{fill}" stroke-width="{width}" stroke-linecap="round"/>'
    )


# ---------------------------------------------------------------------------
# Robot: canvas 170x140, rotation centre (60, 70)
# ---------------------------------------------------------------------------

ROBOT_CENTER = (60, 70)


def robot(variant: str) -> str:
    def _line(width=4, fill="none"):
        return f'stroke="{GLOW}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round" fill="{fill}"'

    stroke = _line()
    blush = '<circle cx="37" cy="65" r="5" fill="#ff9db3" opacity=".75"/><circle cx="83" cy="65" r="5" fill="#ff9db3" opacity=".75"/>'
    eye = lambda cx, cy, r=8, px=0, py=0: (  # noqa: E731
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{GLOW}"/>'
        f'<circle cx="{cx + px}" cy="{cy + py}" r="{r * 0.45:.1f}" fill="#14264a"/>'
        f'<circle cx="{cx + px - 2}" cy="{cy + py - 2}" r="2" fill="#fff"/>'
    )
    smile = f'<path d="M48 64 Q60 73 72 64" {stroke}/>'
    left_arm = _limb(34, 92, 20, 114, BODY, BODY_LINE)
    right_arm = _limb(86, 92, 100, 114, BODY, BODY_LINE)
    face, tilt = "", ""

    if variant == "idle":
        face = eye(46, 53) + eye(74, 53) + smile + blush
    elif variant == "blink":
        face = (f'<path d="M38 54 L54 54 M66 54 L82 54" {stroke}/>' + smile + blush)
    elif variant == "wow":
        face = (eye(46, 52, 11) + eye(74, 52, 11)
                + f'<ellipse cx="60" cy="68" rx="5" ry="6" fill="none" stroke="{GLOW}" stroke-width="3"/>')
        left_arm = _limb(34, 90, 12, 66, BODY, BODY_LINE)
        right_arm = _limb(86, 90, 108, 66, BODY, BODY_LINE)
    elif variant == "reach":
        face = eye(46, 53, 8, 3, 0) + eye(74, 53, 8, 3, 0) + f'<path d="M46 63 Q60 77 74 63 Z" {_line(4, "#14264a")}/>' + blush
        right_arm = _limb(86, 92, 128, 62, BODY, BODY_LINE) + f'<circle cx="132" cy="60" r="9" fill="{HEAD}" stroke="{HEAD_LINE}" stroke-width="3"/>'
    elif variant == "stare":
        face = (f'<ellipse cx="46" cy="55" rx="8" ry="5" fill="{GLOW}"/><ellipse cx="74" cy="55" rx="8" ry="5" fill="{GLOW}"/>'
                '<circle cx="49" cy="55" r="3" fill="#14264a"/><circle cx="77" cy="55" r="3" fill="#14264a"/>'
                '<path d="M35 43 L55 49 M85 43 L65 49" stroke="#ff7a7a" stroke-width="4" stroke-linecap="round"/>'
                f'<path d="M50 69 Q60 62 70 69" {stroke}/>')
        right_arm = _limb(86, 92, 128, 62, BODY, BODY_LINE) + f'<circle cx="132" cy="60" r="9" fill="{HEAD}" stroke="{HEAD_LINE}" stroke-width="3"/>'
    elif variant == "tug":
        face = (f'<path d="M38 46 L54 54 L38 62 M82 46 L66 54 L82 62" {stroke}/>'
                f'<path d="M47 68 L51 63 L55 68 L59 63 L63 68 L67 63 L71 68 L73 65" {_line(3)}/>')
        right_arm = _limb(86, 92, 128, 62, BODY, BODY_LINE) + f'<circle cx="132" cy="60" r="9" fill="{HEAD}" stroke="{HEAD_LINE}" stroke-width="3"/>'
        tilt = ' transform="rotate(-10 60 130)"'
    elif variant == "happy":
        face = (f'<path d="M37 57 Q46 45 55 57 M65 57 Q74 45 83 57" {stroke}/>'
                f'<path d="M46 63 Q60 82 74 63 Z" fill="#ff7a8a" stroke="{GLOW}" stroke-width="3" stroke-linejoin="round"/>' + blush)
        left_arm = _limb(34, 90, 14, 64, BODY, BODY_LINE)
        right_arm = _limb(86, 90, 106, 64, BODY, BODY_LINE)
    else:
        raise ValueError(variant)

    body = (
        '<ellipse cx="60" cy="137" rx="34" ry="3" fill="#000" opacity=".12"/>'
        f'<rect x="36" y="120" width="18" height="14" rx="6" fill="{HEAD_LINE}"/><rect x="66" y="120" width="18" height="14" rx="6" fill="{HEAD_LINE}"/>'
        f'{left_arm}{right_arm}'
        f'<rect x="32" y="82" width="56" height="42" rx="16" fill="{BODY}" stroke="{BODY_LINE}" stroke-width="3"/>'
        f'<circle cx="60" cy="104" r="10" fill="#fff3d6" stroke="{BODY_LINE}" stroke-width="2"/><circle cx="60" cy="104" r="4.5" fill="#ff5a6e"/>'
        f'<line x1="60" y1="26" x2="60" y2="12" stroke="{HEAD_LINE}" stroke-width="4"/><circle cx="60" cy="9" r="6" fill="#ff5a6e" stroke="#b83a4c" stroke-width="2"/>'
        f'<rect x="11" y="44" width="11" height="20" rx="5" fill="{BODY}" stroke="{BODY_LINE}" stroke-width="2"/>'
        f'<rect x="98" y="44" width="11" height="20" rx="5" fill="{BODY}" stroke="{BODY_LINE}" stroke-width="2"/>'
        f'<rect x="20" y="24" width="80" height="58" rx="20" fill="{HEAD}" stroke="{HEAD_LINE}" stroke-width="3"/>'
        '<path d="M30 32 Q40 27 52 28" stroke="#fff" stroke-width="4" stroke-linecap="round" fill="none" opacity=".7"/>'
        '<rect x="29" y="34" width="62" height="40" rx="14" fill="#14264a"/>'
        f'{face}'
    )
    return _svg(170, 140, f"<g{tilt}>{body}</g>")


ROBOT_VARIANTS = ["idle", "blink", "wow", "reach", "stare", "tug", "happy"]

# ---------------------------------------------------------------------------
# Alien: canvas 130x120, rotation centre (70, 60), faces left (towards the cookie)
# ---------------------------------------------------------------------------

ALIEN_CENTER = (70, 60)
SKIN, SKIN_LINE, SUIT, SUIT_LINE = "#8ee08e", "#3c9a3c", "#ff9ad5", "#c2559a"


def alien(variant: str) -> str:
    big_eye = lambda cx, cy, rx=9, ry=12: (  # noqa: E731
        f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="#1b1030"/>'
        f'<ellipse cx="{cx - 3}" cy="{cy - 4}" rx="3.5" ry="4.5" fill="#fff"/>'
    )
    mouth_smile = '<path d="M60 58 Q70 66 80 58" stroke="#1b1030" stroke-width="3" fill="none" stroke-linecap="round"/>'
    left_arm = _limb(52, 86, 40, 104, SUIT, SUIT_LINE, 10)
    right_arm = _limb(88, 86, 100, 104, SUIT, SUIT_LINE, 10)
    face, tilt = "", ""
    reach = _limb(52, 86, 10, 72, SUIT, SUIT_LINE, 10) + f'<circle cx="8" cy="71" r="7" fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="2.5"/>'

    if variant == "smug":
        face = big_eye(56, 42) + big_eye(84, 42) + '<path d="M58 57 Q70 70 82 57" stroke="#1b1030" stroke-width="3" fill="#ff7a8a" stroke-linecap="round"/>'
        left_arm = _limb(52, 86, 30, 62, SUIT, SUIT_LINE, 10)
        right_arm = _limb(88, 86, 112, 66, SUIT, SUIT_LINE, 10)
    elif variant == "stare":
        face = (big_eye(56, 44, 9, 8) + big_eye(84, 44, 9, 8)
                + '<path d="M44 30 L66 38 M96 30 L74 38" stroke="#1b1030" stroke-width="4" stroke-linecap="round"/>'
                '<path d="M62 62 Q70 56 78 62" stroke="#1b1030" stroke-width="3" fill="none" stroke-linecap="round"/>')
        left_arm = reach
    elif variant == "tug":
        face = ('<path d="M46 34 L64 43 L46 52 M94 34 L76 43 L94 52" stroke="#1b1030" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
                '<path d="M60 62 L64 57 L68 62 L72 57 L76 62 L80 57" stroke="#1b1030" stroke-width="3" fill="none" stroke-linejoin="round"/>')
        left_arm = reach
        tilt = ' transform="rotate(10 70 108)"'
    elif variant == "happy":
        face = ('<path d="M46 46 Q56 32 66 46 M74 46 Q84 32 94 46" stroke="#1b1030" stroke-width="4" fill="none" stroke-linecap="round"/>'
                '<path d="M56 56 Q70 76 84 56 Z" fill="#ff7a8a" stroke="#1b1030" stroke-width="3" stroke-linejoin="round"/>'
                '<circle cx="46" cy="56" r="5" fill="#ff9db3" opacity=".75"/><circle cx="94" cy="56" r="5" fill="#ff9db3" opacity=".75"/>')
        left_arm = _limb(52, 86, 32, 62, SUIT, SUIT_LINE, 10)
        right_arm = _limb(88, 86, 108, 62, SUIT, SUIT_LINE, 10)
    else:
        raise ValueError(variant)
    _ = mouth_smile

    body = (
        '<ellipse cx="70" cy="116" rx="26" ry="3" fill="#000" opacity=".12"/>'
        f'<ellipse cx="58" cy="110" rx="9" ry="6" fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="2.5"/><ellipse cx="82" cy="110" rx="9" ry="6" fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="2.5"/>'
        f'{left_arm}{right_arm}'
        f'<ellipse cx="70" cy="92" rx="23" ry="20" fill="{SUIT}" stroke="{SUIT_LINE}" stroke-width="3"/>'
        '<circle cx="62" cy="90" r="4" fill="#fff" opacity=".6"/><circle cx="76" cy="98" r="5" fill="#fff" opacity=".6"/>'
        f'<line x1="56" y1="18" x2="48" y2="4" stroke="{SKIN_LINE}" stroke-width="3.5"/><circle cx="47" cy="4" r="5.5" fill="#ffd34d" stroke="#c99a10" stroke-width="2"/>'
        f'<line x1="84" y1="18" x2="92" y2="4" stroke="{SKIN_LINE}" stroke-width="3.5"/><circle cx="93" cy="4" r="5.5" fill="#ffd34d" stroke="#c99a10" stroke-width="2"/>'
        f'<ellipse cx="70" cy="42" rx="38" ry="31" fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="3"/>'
        '<path d="M42 28 Q50 20 62 20" stroke="#fff" stroke-width="4" stroke-linecap="round" fill="none" opacity=".6"/>'
        f'{face}'
    )
    return _svg(130, 120, f"<g{tilt}>{body}</g>")


ALIEN_VARIANTS = ["smug", "stare", "tug", "happy"]

# ---------------------------------------------------------------------------
# Cookie: canvas 60x60, centre (30, 30)
# ---------------------------------------------------------------------------

COOKIE_CENTER = (30, 30)
_ZIG = "30,0 34,10 26,20 34,30 26,40 34,50 30,60"


def cookie(part: str) -> str:
    chips = "".join(
        f'<ellipse cx="{x}" cy="{y}" rx="4.5" ry="3.5" transform="rotate({r} {x} {y})" fill="#5a3216"/>'
        for x, y, r in [(20, 20, 20), (38, 18, -15), (28, 34, 40), (42, 36, 10), (17, 40, -30), (32, 47, 15), (46, 24, 60)]
    )
    disc = (
        '<circle cx="30" cy="30" r="27" fill="#e0a24a" stroke="#a8671c" stroke-width="3"/>'
        '<path d="M12 22 Q18 10 32 8" stroke="#f4c675" stroke-width="3.5" fill="none" stroke-linecap="round"/>'
        f"{chips}"
    )
    if part == "whole":
        return _svg(60, 60, disc)
    if part == "left":
        clip = f'<clipPath id="c"><polygon points="0,0 {_ZIG} 0,60"/></clipPath>'
    elif part == "right":
        clip = f'<clipPath id="c"><polygon points="60,0 {_ZIG} 60,60"/></clipPath>'
    else:
        raise ValueError(part)
    return _svg(60, 60, f'<g clip-path="url(#c)">{disc}</g>', clip)


# ---------------------------------------------------------------------------
# Title card
# ---------------------------------------------------------------------------

def title(text: str = "The Last Cookie") -> str:
    text = (
        'font-family="Sans Serif, Arial Rounded MT Bold, Arial" font-weight="bold" font-size="46" '
        'text-anchor="middle"'
    )
    return _svg(
        360, 80,
        f'<text x="180" y="52" {text} stroke="#5a2a8a" stroke-width="12" stroke-linejoin="round" fill="#5a2a8a">{esc(text)}</text>'
        f'<text x="180" y="52" {text} fill="#ffd34d">{esc(text)}</text>',
    )


# ---------------------------------------------------------------------------
# Futuristic kitchen backdrop (480x360). Two frames differ in blinking lights.
# ---------------------------------------------------------------------------

def kitchen(frame: int) -> str:
    a, b = ("#ff5ac8", "#5af0ff") if frame == 1 else ("#5af0ff", "#ff5ac8")
    twinkle = [(70, 85, 2), (150, 70, 1.5), (95, 140, 1.5), (160, 120, 2), (60, 120, 1.2)]
    stars = "".join(
        f'<circle cx="{x}" cy="{y}" r="{r * (1.6 if (i + frame) % 2 else 1)}" fill="#fff"/>' for i, (x, y, r) in enumerate(twinkle)
    )
    jars = "".join(
        f'<rect x="{285 + i * 38}" y="{70}" width="26" height="34" rx="8" fill="{c}" stroke="#fff" stroke-opacity=".6" stroke-width="2"/>'
        f'<rect x="{289 + i * 38}" y="{64}" width="18" height="8" rx="3" fill="#ffffff" opacity=".85"/>'
        for i, c in enumerate(["#ffd34d", "#7dffb0", "#ff9ad5", "#8fd3ff", "#ffb84d"])
    )
    lights = "".join(
        f'<circle cx="{x}" cy="{y}" r="5" fill="{a if i % 2 else b}"/><circle cx="{x}" cy="{y}" r="9" fill="{a if i % 2 else b}" opacity=".25"/>'
        for i, (x, y) in enumerate([(290, 175), (312, 175), (334, 175), (356, 175), (378, 175)])
    )
    defs = (
        '<linearGradient id="wall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2b2a7a"/><stop offset="1" stop-color="#3fb6d8"/></linearGradient>'
        '<linearGradient id="floor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f3f0ff"/><stop offset="1" stop-color="#b9b4ee"/></linearGradient>'
        '<radialGradient id="planet" cx=".35" cy=".35" r=".8"><stop offset="0" stop-color="#ffcf70"/><stop offset="1" stop-color="#e0562e"/></radialGradient>'
        '<radialGradient id="glow" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#fff" stop-opacity=".9"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        '<clipPath id="win"><circle cx="105" cy="130" r="62"/></clipPath>'
    )
    inner = (
        '<rect width="480" height="360" fill="url(#wall)"/>'
        # neon wall strips
        f'<rect x="0" y="212" width="480" height="6" fill="{a}" opacity=".85"/><rect x="0" y="222" width="480" height="3" fill="{b}" opacity=".7"/>'
        '<g opacity=".16" fill="#fff"><rect x="200" y="20" width="12" height="190"/><rect x="236" y="20" width="12" height="190"/><rect x="272" y="20" width="12" height="190"/></g>'
        # ceiling lights
        + "".join(f'<ellipse cx="{x}" cy="6" rx="62" ry="22" fill="url(#glow)" opacity=".75"/>' for x in (90, 240, 390))
        # round window to space
        + '<circle cx="105" cy="130" r="70" fill="#e9e6ff" stroke="#ff9ad5" stroke-width="6"/>'
        '<g clip-path="url(#win)"><rect x="30" y="60" width="150" height="150" fill="#120a3c"/>'
        f'{stars}<circle cx="120" cy="150" r="30" fill="url(#planet)"/>'
        '<ellipse cx="120" cy="152" rx="48" ry="9" fill="none" stroke="#ffe29a" stroke-width="4" transform="rotate(-18 120 152)"/></g>'
        '<line x1="105" y1="68" x2="105" y2="192" stroke="#e9e6ff" stroke-width="4"/><line x1="43" y1="130" x2="167" y2="130" stroke="#e9e6ff" stroke-width="4"/>'
        # shelf with jars and appliance
        f'{jars}<rect x="270" y="104" width="205" height="8" rx="4" fill="#e9e6ff"/>'
        '<rect x="270" y="142" width="130" height="46" rx="12" fill="#2a2370" stroke="#8fd3ff" stroke-width="3"/>'
        f'{lights}'
        # floor
        '<rect x="0" y="292" width="480" height="68" fill="url(#floor)"/><rect x="0" y="288" width="480" height="6" fill="#ffffff" opacity=".6"/>'
        '<g stroke="#9a94de" stroke-width="2" opacity=".7"><line x1="0" y1="326" x2="480" y2="326"/><line x1="120" y1="294" x2="60" y2="360"/><line x1="240" y1="294" x2="240" y2="360"/><line x1="360" y1="294" x2="420" y2="360"/></g>'
        # table
        '<ellipse cx="362" cy="312" rx="125" ry="9" fill="#000" opacity=".15"/>'
        '<rect x="266" y="262" width="12" height="46" rx="4" fill="#d9559f"/><rect x="446" y="262" width="12" height="46" rx="4" fill="#d9559f"/>'
        '<rect x="252" y="248" width="224" height="16" rx="8" fill="#ff7ab6" stroke="#b83a82" stroke-width="3"/>'
        f'<rect x="262" y="251" width="204" height="3" rx="1.5" fill="{b}" opacity=".9"/>'
        # plate
        '<ellipse cx="365" cy="248" rx="30" ry="5" fill="#fff" stroke="#c9c4f0" stroke-width="2"/>'
    )
    return _svg(480, 360, inner, defs)


# ---------------------------------------------------------------------------
# Registry used by the add_stock_art tool
# ---------------------------------------------------------------------------

# art name -> (description, [(costume name, svg, rotation centre x, y)], is_backdrop)
def _build_registry(title_text: str = "The Last Cookie") -> dict[str, tuple[str, list[tuple[str, str, float, float]], bool]]:
    return {
        "robot": (
            "Cute orange/blue robot, 170x140. Costumes: " + ", ".join(ROBOT_VARIANTS)
            + ". Right arm reaches towards the right in reach/stare/tug.",
            [(v, robot(v), *ROBOT_CENTER) for v in ROBOT_VARIANTS], False),
        "alien": (
            "Tiny green alien, 130x120, faces left. Costumes: " + ", ".join(ALIEN_VARIANTS)
            + ". Its left arm reaches left in stare/tug.",
            [(v, alien(v), *ALIEN_CENTER) for v in ALIEN_VARIANTS], False),
        "cookie": (
            "Chocolate-chip cookie, 60x60. Costumes: whole, half left, half right "
            "(the halves interlock when placed at the same position).",
            [("whole", cookie("whole"), *COOKIE_CENTER), ("half left", cookie("left"), *COOKIE_CENTER),
             ("half right", cookie("right"), *COOKIE_CENTER)], False),
        "kitchen": (
            "Futuristic kitchen backdrop with a pink table (top at y=-68, x from 12 to 236), a round "
            "space window and blinking lights. Two backdrops (kitchen1, kitchen2) - alternate them for animation.",
            [("kitchen1", kitchen(1), 240, 180), ("kitchen2", kitchen(2), 240, 180)], True),
        "title": (
            "Title card text (360x80). Pass text=... (default 'The Last Cookie'). One costume called 'title'.",
            [("title", title(), 180, 40)], False),
    }


STOCK_NAMES = ["robot", "alien", "cookie", "kitchen", "title"]


def stock_art(name: str, text: str | None = None):
    registry = _build_registry()
    if name not in registry:
        raise KeyError(name)
    description, costumes, is_backdrop = registry[name]
    if name == "title" and text:
        costumes = [("title", title(text), 180, 40)]
    return description, costumes, is_backdrop
