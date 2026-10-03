"""Catalog of Scratch 3 blocks.

Two things live here:

* ``KNOWN_OPCODES`` - every opcode Scratch 3 can load (core blocks, menu/shadow
  blocks and the official extensions). Used by the validator.
* ``SPECS`` - a text template for each block, used both to render scripts as
  readable text and to parse text back into blocks (``add_script``).

Opcode, input and field names were taken from scratch-blocks and scratch-vm.

Template syntax: plain words are literal block text and ``{NAME:kind}`` is a
slot. Slot kinds:

    num pos whole int angle   number inputs (math_number, math_positive_number, ...)
    text                      text input
    color                     colour picker input ([#ff0000])
    note                      music note input
    bool                      boolean input (no shadow)
    menu:<menu opcode>        input holding a menu shadow block (accepts reporters)
    field:<option set>        dropdown field on the block itself ("free" = any value)
    var / list                variable / list field
    bcast_field / bcast_input broadcast field (hat) / broadcast input
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Compressed primitive codes used inside "inputs" in project.json
# ---------------------------------------------------------------------------

MATH_NUM, POSITIVE_NUM, WHOLE_NUM, INTEGER_NUM, ANGLE_NUM = 4, 5, 6, 7, 8
COLOR_PICKER, TEXT, BROADCAST, VAR, LIST = 9, 10, 11, 12, 13

PRIMITIVE_OPCODES = {
    MATH_NUM: "math_number",
    POSITIVE_NUM: "math_positive_number",
    WHOLE_NUM: "math_whole_number",
    INTEGER_NUM: "math_integer",
    ANGLE_NUM: "math_angle",
    COLOR_PICKER: "colour_picker",
    TEXT: "text",
    BROADCAST: "event_broadcast_menu",
    VAR: "data_variable",
    LIST: "data_listcontents",
}

KIND_TO_PRIMITIVE = {
    "num": MATH_NUM,
    "pos": POSITIVE_NUM,
    "whole": WHOLE_NUM,
    "int": INTEGER_NUM,
    "angle": ANGLE_NUM,
    "color": COLOR_PICKER,
    "text": TEXT,
}

# ---------------------------------------------------------------------------
# Known opcodes
# ---------------------------------------------------------------------------

_CORE_OPCODES = """
colour_picker math_number math_integer math_whole_number math_positive_number
math_angle text note matrix

motion_movesteps motion_turnright motion_turnleft motion_pointindirection
motion_pointtowards_menu motion_pointtowards motion_goto_menu motion_gotoxy
motion_goto motion_glidesecstoxy motion_glideto_menu motion_glideto
motion_changexby motion_setx motion_changeyby motion_sety motion_ifonedgebounce
motion_setrotationstyle motion_xposition motion_yposition motion_direction
motion_scroll_right motion_scroll_up motion_align_scene motion_xscroll
motion_yscroll

looks_sayforsecs looks_say looks_thinkforsecs looks_think looks_show looks_hide
looks_hideallsprites looks_changeeffectby looks_seteffectto
looks_cleargraphiceffects looks_changesizeby looks_setsizeto looks_size
looks_changestretchby looks_setstretchto looks_costume looks_switchcostumeto
looks_nextcostume looks_switchbackdropto looks_backdrops looks_gotofrontback
looks_goforwardbackwardlayers looks_backdropnumbername looks_costumenumbername
looks_switchbackdroptoandwait looks_nextbackdrop

sound_sounds_menu sound_play sound_playuntildone sound_stopallsounds
sound_seteffectto sound_changeeffectby sound_cleareffects sound_changevolumeby
sound_setvolumeto sound_volume

event_whentouchingobject event_touchingobjectmenu event_whenflagclicked
event_whenthisspriteclicked event_whenstageclicked event_whenbroadcastreceived
event_whenbackdropswitchesto event_whengreaterthan event_broadcast_menu
event_broadcast event_broadcastandwait event_whenkeypressed

control_forever control_repeat control_if control_if_else control_stop
control_wait control_wait_until control_repeat_until control_while
control_for_each control_start_as_clone control_create_clone_of_menu
control_create_clone_of control_delete_this_clone control_get_counter
control_incr_counter control_clear_counter control_all_at_once

sensing_touchingobject sensing_touchingobjectmenu sensing_touchingcolor
sensing_coloristouchingcolor sensing_distanceto sensing_distancetomenu
sensing_askandwait sensing_answer sensing_keypressed sensing_keyoptions
sensing_mousedown sensing_mousex sensing_mousey sensing_setdragmode
sensing_loudness sensing_loud sensing_timer sensing_resettimer
sensing_of_object_menu sensing_of sensing_current sensing_dayssince2000
sensing_online sensing_username sensing_userid

operator_add operator_subtract operator_multiply operator_divide operator_random
operator_lt operator_equals operator_gt operator_and operator_or operator_not
operator_join operator_letter_of operator_length operator_contains operator_mod
operator_round operator_mathop

data_variable data_setvariableto data_changevariableby data_showvariable
data_hidevariable data_listcontents data_listindexall data_listindexrandom
data_addtolist data_deleteoflist data_deletealloflist data_insertatlist
data_replaceitemoflist data_itemoflist data_itemnumoflist data_lengthoflist
data_listcontainsitem data_showlist data_hidelist

procedures_definition procedures_call procedures_prototype
procedures_declaration argument_reporter_boolean
argument_reporter_string_number argument_editor_boolean
argument_editor_string_number
"""

# extension id -> (block opcodes, menu names). Menus become "<id>_menu_<name>".
EXTENSIONS: dict[str, tuple[list[str], list[str]]] = {
    "pen": (
        "clear stamp penDown penUp setPenColorToColor changePenColorParamBy "
        "setPenColorParamTo changePenSizeBy setPenSizeTo setPenShadeToNumber "
        "changePenShadeBy setPenHueToNumber changePenHueBy".split(),
        ["colorParam"],
    ),
    "music": (
        "playDrumForBeats midiPlayDrumForBeats restForBeats playNoteForBeats "
        "setInstrument midiSetInstrument setTempo changeTempo getTempo".split(),
        ["DRUM", "INSTRUMENT"],
    ),
    "videoSensing": (
        "whenMotionGreaterThan videoOn videoToggle setVideoTransparency".split(),
        ["ATTRIBUTE", "SUBJECT", "VIDEO_STATE"],
    ),
    "text2speech": ("speakAndWait setVoice setLanguage".split(), ["voices", "languages"]),
    "translate": ("getTranslate getViewerLanguage".split(), ["languages"]),
    "makeymakey": ("whenMakeyKeyPressed whenCodePressed".split(), ["KEY", "SEQUENCE"]),
    "microbit": (
        "whenButtonPressed isButtonPressed whenGesture displaySymbol displayText "
        "displayClear whenTilted isTilted getTiltAngle whenPinConnected".split(),
        ["buttons", "gestures", "pinState", "tiltDirection", "tiltDirectionAny", "touchPins"],
    ),
    "ev3": (
        "motorTurnClockwise motorTurnCounterClockwise motorSetPower getMotorPosition "
        "whenButtonPressed whenDistanceLessThan whenBrightnessLessThan buttonPressed "
        "getDistance getBrightness beep".split(),
        ["motorPorts", "sensorPorts"],
    ),
    "boost": (
        "motorOnFor motorOnForRotation motorOn motorOff setMotorPower "
        "setMotorDirection getMotorPosition whenColor seeingColor whenTilted "
        "getTiltAngle setLightHue".split(),
        ["MOTOR_ID", "MOTOR_REPORTER_ID", "MOTOR_DIRECTION", "TILT_DIRECTION",
         "TILT_DIRECTION_ANY", "COLOR"],
    ),
    "wedo2": (
        "motorOnFor motorOn motorOff startMotorPower setMotorDirection setLightHue "
        "playNoteFor whenDistance whenTilted getDistance isTilted getTiltAngle".split(),
        ["MOTOR_ID", "MOTOR_DIRECTION", "TILT_DIRECTION", "TILT_DIRECTION_ANY", "OP"],
    ),
    "gdxfor": (
        "whenGesture whenForcePushedOrPulled getForce whenTilted isTilted getTilt "
        "isFreeFalling getSpinSpeed getAcceleration".split(),
        ["pushPullOptions", "gestureOptions", "axisOptions", "tiltOptions", "tiltAnyOptions"],
    ),
}


def _build_known() -> frozenset[str]:
    known = set(_CORE_OPCODES.split())
    for ext_id, (opcodes, menus) in EXTENSIONS.items():
        known.update(f"{ext_id}_{op}" for op in opcodes)
        known.update(f"{ext_id}_menu_{m}" for m in menus)
    return frozenset(known)


KNOWN_OPCODES = _build_known()


def extension_of(opcode: str) -> str | None:
    """Return the extension id an opcode belongs to, or None for core blocks."""
    prefix = opcode.split("_", 1)[0]
    return prefix if prefix in EXTENSIONS else None


# ---------------------------------------------------------------------------
# Dropdown options: (display text, stored value)
# ---------------------------------------------------------------------------

_KEYS = (
    ["space", "up arrow", "down arrow", "right arrow", "left arrow", "any"]
    + list(string.ascii_lowercase)
    + list(string.digits)
)

OPTION_SETS: dict[str, list[tuple[str, str]]] = {
    "rotation": [(v, v) for v in ("left-right", "don't rotate", "all around")],
    "looks_effect": [
        (v, v.upper())
        for v in ("color", "fisheye", "whirl", "pixelate", "mosaic", "brightness", "ghost")
    ],
    "sound_effect": [("pitch", "PITCH"), ("pan left/right", "PAN")],
    "front_back": [("front", "front"), ("back", "back")],
    "fwd_back": [("forward", "forward"), ("backward", "backward")],
    "number_name": [("number", "number"), ("name", "name")],
    "stop": [
        (v, v)
        for v in ("all", "this script", "other scripts in sprite", "other scripts in stage")
    ],
    "current": [
        ("year", "YEAR"), ("month", "MONTH"), ("date", "DATE"),
        ("day of week", "DAYOFWEEK"), ("hour", "HOUR"), ("minute", "MINUTE"),
        ("second", "SECOND"),
    ],
    "mathop": [
        (v, v)
        for v in ("abs", "floor", "ceiling", "sqrt", "sin", "cos", "tan", "asin",
                  "acos", "atan", "ln", "log", "e ^", "10 ^")
    ],
    "drag": [("draggable", "draggable"), ("not draggable", "not draggable")],
    "greater": [("loudness", "LOUDNESS"), ("timer", "TIMER")],
    "key": [(k, k) for k in _KEYS],
    "pen_color_param": [(v, v) for v in ("color", "saturation", "brightness", "transparency")],
    "video_attribute": [("motion", "motion"), ("direction", "direction")],
    "video_subject": [("sprite", "this sprite"), ("stage", "Stage")],
    "video_state": [("off", "off"), ("on", "on"), ("on flipped", "on-flipped")],
    "voices": [(v.lower(), v) for v in ("ALTO", "TENOR", "SQUEAK", "GIANT", "KITTEN")],
}


def option_value(optset: str, text: str) -> str | None:
    """Map user text (display or raw value, any case) to the stored value."""
    t = text.strip().lower()
    for display, value in OPTION_SETS[optset]:
        if t in (display.lower(), value.lower()):
            return value
    return None


def option_display(optset: str | None, value: str) -> str:
    if optset and optset in OPTION_SETS:
        for display, v in OPTION_SETS[optset]:
            if v == value:
                return display
    return value


# ---------------------------------------------------------------------------
# Menu shadow blocks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MenuSpec:
    field: str
    default: str | None  # None = first costume / sound / backdrop of the target
    optset: str | None = None  # restrict to these options
    specials: dict[str, str] = field(default_factory=dict)  # stored value -> display


_MOUSE = {"_mouse_": "mouse-pointer"}

MENUS: dict[str, MenuSpec] = {
    "motion_goto_menu": MenuSpec("TO", "_random_", specials={"_random_": "random position", **_MOUSE}),
    "motion_glideto_menu": MenuSpec("TO", "_random_", specials={"_random_": "random position", **_MOUSE}),
    "motion_pointtowards_menu": MenuSpec("TOWARDS", "_mouse_", specials={**_MOUSE, "_random_": "random direction"}),
    "looks_costume": MenuSpec("COSTUME", None),
    "looks_backdrops": MenuSpec("BACKDROP", None),
    "sound_sounds_menu": MenuSpec("SOUND_MENU", None),
    "control_create_clone_of_menu": MenuSpec("CLONE_OPTION", "_myself_", specials={"_myself_": "myself"}),
    "sensing_touchingobjectmenu": MenuSpec("TOUCHINGOBJECTMENU", "_mouse_", specials={**_MOUSE, "_edge_": "edge"}),
    "event_touchingobjectmenu": MenuSpec("TOUCHINGOBJECTMENU", "_mouse_", specials={**_MOUSE, "_edge_": "edge"}),
    "sensing_distancetomenu": MenuSpec("DISTANCETOMENU", "_mouse_", specials=dict(_MOUSE)),
    "sensing_keyoptions": MenuSpec("KEY_OPTION", "space", optset="key"),
    "sensing_of_object_menu": MenuSpec("OBJECT", "_stage_", specials={"_stage_": "Stage"}),
    "pen_menu_colorParam": MenuSpec("colorParam", "color", optset="pen_color_param"),
    "music_menu_DRUM": MenuSpec("DRUM", "1"),
    "music_menu_INSTRUMENT": MenuSpec("INSTRUMENT", "1"),
    "videoSensing_menu_ATTRIBUTE": MenuSpec("ATTRIBUTE", "motion", optset="video_attribute"),
    "videoSensing_menu_SUBJECT": MenuSpec("SUBJECT", "this sprite", optset="video_subject"),
    "videoSensing_menu_VIDEO_STATE": MenuSpec("VIDEO_STATE", "on", optset="video_state"),
    "text2speech_menu_voices": MenuSpec("voices", "ALTO", optset="voices"),
    "text2speech_menu_languages": MenuSpec("languages", "en"),
    "translate_menu_languages": MenuSpec("languages", "en"),
}


def menu_value(menu: MenuSpec, text: str) -> str | None:
    """Map dropdown text to the stored menu value (None if not allowed)."""
    t = text.strip()
    for value, display in menu.specials.items():
        if t.lower() in (display.lower(), value.lower()):
            return value
    if menu.optset:
        return option_value(menu.optset, t)
    return t


def menu_display(menu: MenuSpec, value: str) -> str:
    if value in menu.specials:
        return menu.specials[value]
    return option_display(menu.optset, value)


# ---------------------------------------------------------------------------
# Block specs (templates)
# ---------------------------------------------------------------------------

HAT, STACK, CAP, C, C_CAP, IF_ELSE, REPORTER, BOOLEAN = (
    "hat", "stack", "cap", "c", "c_cap", "if_else", "reporter", "boolean",
)


@dataclass(frozen=True)
class Slot:
    name: str
    kind: str  # e.g. "num", "menu", "field"
    arg: str | None = None  # menu opcode or option-set name


@dataclass
class BlockSpec:
    opcode: str
    shape: str
    templates: list[str]
    parseable: bool = True
    tokens: list[list[str | Slot]] = field(default_factory=list)

    @property
    def slots(self) -> list[Slot]:
        return [t for t in self.tokens[0] if isinstance(t, Slot)]


SLOT_RE = re.compile(r"\{([A-Za-z0-9_]+):([a-z_]+)(?::([A-Za-z0-9_]+))?\}")
_WORD_RE = re.compile(r"\?|[^\s?]+")


def normalize_word(word: str) -> str:
    return word.strip(",").lower()


def tokenize_template(template: str) -> list[str | Slot]:
    out: list[str | Slot] = []
    pos = 0
    for m in SLOT_RE.finditer(template):
        out.extend(normalize_word(w) for w in _WORD_RE.findall(template[pos:m.start()]))
        out.append(Slot(m.group(1), m.group(2), m.group(3)))
        pos = m.end()
    out.extend(normalize_word(w) for w in _WORD_RE.findall(template[pos:]))
    return [t for t in out if t != ""]


def _s(opcode: str, shape: str, *templates: str, parseable: bool = True) -> BlockSpec:
    return BlockSpec(opcode, shape, list(templates), parseable)


# Order matters for parsing: the first matching spec wins.
_SPEC_LIST = [
    # Motion
    _s("motion_movesteps", STACK, "move {STEPS:num} steps"),
    _s("motion_turnright", STACK, "turn right {DEGREES:num} degrees", "turn cw {DEGREES:num} degrees",
       "turn ↻ {DEGREES:num} degrees"),
    _s("motion_turnleft", STACK, "turn left {DEGREES:num} degrees", "turn ccw {DEGREES:num} degrees",
       "turn ↺ {DEGREES:num} degrees"),
    _s("motion_gotoxy", STACK, "go to x: {X:num} y: {Y:num}"),
    _s("motion_goto", STACK, "go to {TO:menu:motion_goto_menu}"),
    _s("motion_glidesecstoxy", STACK, "glide {SECS:num} secs to x: {X:num} y: {Y:num}"),
    _s("motion_glideto", STACK, "glide {SECS:num} secs to {TO:menu:motion_glideto_menu}"),
    _s("motion_pointindirection", STACK, "point in direction {DIRECTION:angle}"),
    _s("motion_pointtowards", STACK, "point towards {TOWARDS:menu:motion_pointtowards_menu}"),
    _s("motion_changexby", STACK, "change x by {DX:num}"),
    _s("motion_setx", STACK, "set x to {X:num}"),
    _s("motion_changeyby", STACK, "change y by {DY:num}"),
    _s("motion_sety", STACK, "set y to {Y:num}"),
    _s("motion_ifonedgebounce", STACK, "if on edge, bounce"),
    _s("motion_setrotationstyle", STACK, "set rotation style {STYLE:field:rotation}"),
    _s("motion_xposition", REPORTER, "x position"),
    _s("motion_yposition", REPORTER, "y position"),
    _s("motion_direction", REPORTER, "direction"),
    # Looks
    _s("looks_sayforsecs", STACK, "say {MESSAGE:text} for {SECS:num} seconds"),
    _s("looks_say", STACK, "say {MESSAGE:text}"),
    _s("looks_thinkforsecs", STACK, "think {MESSAGE:text} for {SECS:num} seconds"),
    _s("looks_think", STACK, "think {MESSAGE:text}"),
    _s("looks_switchcostumeto", STACK, "switch costume to {COSTUME:menu:looks_costume}"),
    _s("looks_nextcostume", STACK, "next costume"),
    _s("looks_switchbackdroptoandwait", STACK, "switch backdrop to {BACKDROP:menu:looks_backdrops} and wait"),
    _s("looks_switchbackdropto", STACK, "switch backdrop to {BACKDROP:menu:looks_backdrops}"),
    _s("looks_nextbackdrop", STACK, "next backdrop"),
    _s("looks_changesizeby", STACK, "change size by {CHANGE:num}"),
    _s("looks_setsizeto", STACK, "set size to {SIZE:num} %"),
    _s("looks_changeeffectby", STACK, "change {EFFECT:field:looks_effect} effect by {CHANGE:num}"),
    _s("looks_seteffectto", STACK, "set {EFFECT:field:looks_effect} effect to {VALUE:num}"),
    _s("looks_cleargraphiceffects", STACK, "clear graphic effects"),
    _s("looks_show", STACK, "show"),
    _s("looks_hide", STACK, "hide"),
    _s("looks_gotofrontback", STACK, "go to {FRONT_BACK:field:front_back} layer"),
    _s("looks_goforwardbackwardlayers", STACK, "go {FORWARD_BACKWARD:field:fwd_back} {NUM:int} layers"),
    _s("looks_costumenumbername", REPORTER, "costume {NUMBER_NAME:field:number_name}"),
    _s("looks_backdropnumbername", REPORTER, "backdrop {NUMBER_NAME:field:number_name}"),
    _s("looks_size", REPORTER, "size"),
    # Sound
    _s("sound_playuntildone", STACK, "play sound {SOUND_MENU:menu:sound_sounds_menu} until done"),
    _s("sound_play", STACK, "start sound {SOUND_MENU:menu:sound_sounds_menu}"),
    _s("sound_stopallsounds", STACK, "stop all sounds"),
    _s("sound_changeeffectby", STACK, "change {EFFECT:field:sound_effect} effect by {VALUE:num}"),
    _s("sound_seteffectto", STACK, "set {EFFECT:field:sound_effect} effect to {VALUE:num}"),
    _s("sound_cleareffects", STACK, "clear sound effects"),
    _s("sound_changevolumeby", STACK, "change volume by {VOLUME:num}"),
    _s("sound_setvolumeto", STACK, "set volume to {VOLUME:num} %"),
    _s("sound_volume", REPORTER, "volume"),
    # Events
    _s("event_whenflagclicked", HAT, "when flag clicked", "when green flag clicked", "when ⚑ clicked"),
    _s("event_whenkeypressed", HAT, "when {KEY_OPTION:field:key} key pressed"),
    _s("event_whenthisspriteclicked", HAT, "when this sprite clicked"),
    _s("event_whenstageclicked", HAT, "when stage clicked"),
    _s("event_whenbackdropswitchesto", HAT, "when backdrop switches to {BACKDROP:field:free}"),
    _s("event_whengreaterthan", HAT, "when {WHENGREATERTHANMENU:field:greater} > {VALUE:num}"),
    _s("event_whenbroadcastreceived", HAT, "when I receive {BROADCAST_OPTION:bcast_field}"),
    _s("event_whentouchingobject", HAT, "when touching {TOUCHINGOBJECTMENU:menu:event_touchingobjectmenu}"),
    _s("event_broadcastandwait", STACK, "broadcast {BROADCAST_INPUT:bcast_input} and wait"),
    _s("event_broadcast", STACK, "broadcast {BROADCAST_INPUT:bcast_input}"),
    # Control
    _s("control_wait", STACK, "wait {DURATION:pos} seconds", "wait {DURATION:pos} secs"),
    _s("control_repeat", C, "repeat {TIMES:whole}"),
    _s("control_forever", C_CAP, "forever"),
    _s("control_if", C, "if {CONDITION:bool} then", "if {CONDITION:bool}"),
    _s("control_if_else", IF_ELSE, "if {CONDITION:bool} then", parseable=False),
    _s("control_wait_until", STACK, "wait until {CONDITION:bool}"),
    _s("control_repeat_until", C, "repeat until {CONDITION:bool}"),
    _s("control_while", C, "while {CONDITION:bool}"),
    _s("control_for_each", C, "for each {VARIABLE:var} in {VALUE:num}"),
    _s("control_stop", CAP, "stop {STOP_OPTION:field:stop}"),
    _s("control_start_as_clone", HAT, "when I start as a clone"),
    _s("control_create_clone_of", STACK, "create clone of {CLONE_OPTION:menu:control_create_clone_of_menu}"),
    _s("control_delete_this_clone", CAP, "delete this clone"),
    _s("control_get_counter", REPORTER, "counter"),
    _s("control_incr_counter", STACK, "increment counter"),
    _s("control_clear_counter", STACK, "clear counter"),
    _s("control_all_at_once", C, "all at once"),
    # Sensing
    _s("sensing_touchingcolor", BOOLEAN, "touching color {COLOR:color}?"),
    _s("sensing_touchingobject", BOOLEAN, "touching {TOUCHINGOBJECTMENU:menu:sensing_touchingobjectmenu}?"),
    _s("sensing_coloristouchingcolor", BOOLEAN, "color {COLOR:color} is touching {COLOR2:color}?"),
    _s("sensing_distanceto", REPORTER, "distance to {DISTANCETOMENU:menu:sensing_distancetomenu}"),
    _s("sensing_askandwait", STACK, "ask {QUESTION:text} and wait"),
    _s("sensing_answer", REPORTER, "answer"),
    _s("sensing_keypressed", BOOLEAN, "key {KEY_OPTION:menu:sensing_keyoptions} pressed?"),
    _s("sensing_mousedown", BOOLEAN, "mouse down?"),
    _s("sensing_mousex", REPORTER, "mouse x"),
    _s("sensing_mousey", REPORTER, "mouse y"),
    _s("sensing_setdragmode", STACK, "set drag mode {DRAG_MODE:field:drag}"),
    _s("sensing_loudness", REPORTER, "loudness"),
    _s("sensing_loud", BOOLEAN, "loud?"),
    _s("sensing_timer", REPORTER, "timer"),
    _s("sensing_resettimer", STACK, "reset timer"),
    _s("sensing_current", REPORTER, "current {CURRENTMENU:field:current}"),
    _s("sensing_dayssince2000", REPORTER, "days since 2000"),
    _s("sensing_username", REPORTER, "username"),
    # Operators (mathop before sensing_of: both are "[x v] of (y)")
    _s("operator_add", REPORTER, "{NUM1:num} + {NUM2:num}"),
    _s("operator_subtract", REPORTER, "{NUM1:num} - {NUM2:num}"),
    _s("operator_multiply", REPORTER, "{NUM1:num} * {NUM2:num}"),
    _s("operator_divide", REPORTER, "{NUM1:num} / {NUM2:num}"),
    _s("operator_random", REPORTER, "pick random {FROM:num} to {TO:num}"),
    _s("operator_gt", BOOLEAN, "{OPERAND1:text} > {OPERAND2:text}"),
    _s("operator_lt", BOOLEAN, "{OPERAND1:text} < {OPERAND2:text}"),
    _s("operator_equals", BOOLEAN, "{OPERAND1:text} = {OPERAND2:text}"),
    _s("operator_and", BOOLEAN, "{OPERAND1:bool} and {OPERAND2:bool}"),
    _s("operator_or", BOOLEAN, "{OPERAND1:bool} or {OPERAND2:bool}"),
    _s("operator_not", BOOLEAN, "not {OPERAND:bool}"),
    _s("operator_join", REPORTER, "join {STRING1:text} {STRING2:text}"),
    _s("operator_letter_of", REPORTER, "letter {LETTER:whole} of {STRING:text}"),
    _s("operator_length", REPORTER, "length of {STRING:text}"),
    _s("operator_contains", BOOLEAN, "{STRING1:text} contains {STRING2:text}?"),
    _s("operator_mod", REPORTER, "{NUM1:num} mod {NUM2:num}"),
    _s("operator_round", REPORTER, "round {NUM:num}"),
    _s("operator_mathop", REPORTER, "{OPERATOR:field:mathop} of {NUM:num}"),
    _s("sensing_of", REPORTER, "{PROPERTY:field:free} of {OBJECT:menu:sensing_of_object_menu}"),
    # Variables & lists
    _s("data_setvariableto", STACK, "set {VARIABLE:var} to {VALUE:text}"),
    _s("data_changevariableby", STACK, "change {VARIABLE:var} by {VALUE:num}"),
    _s("data_showvariable", STACK, "show variable {VARIABLE:var}"),
    _s("data_hidevariable", STACK, "hide variable {VARIABLE:var}"),
    _s("data_addtolist", STACK, "add {ITEM:text} to {LIST:list}"),
    _s("data_deletealloflist", STACK, "delete all of {LIST:list}"),
    _s("data_deleteoflist", STACK, "delete {INDEX:int} of {LIST:list}"),
    _s("data_insertatlist", STACK, "insert {ITEM:text} at {INDEX:int} of {LIST:list}"),
    _s("data_replaceitemoflist", STACK, "replace item {INDEX:int} of {LIST:list} with {ITEM:text}"),
    _s("data_itemoflist", REPORTER, "item {INDEX:int} of {LIST:list}"),
    _s("data_itemnumoflist", REPORTER, "item # of {ITEM:text} in {LIST:list}"),
    _s("data_lengthoflist", REPORTER, "length of {LIST:list}"),
    _s("data_listcontainsitem", BOOLEAN, "{LIST:list} contains {ITEM:text}?"),
    _s("data_showlist", STACK, "show list {LIST:list}"),
    _s("data_hidelist", STACK, "hide list {LIST:list}"),
    # Pen
    _s("pen_clear", STACK, "erase all"),
    _s("pen_stamp", STACK, "stamp"),
    _s("pen_penDown", STACK, "pen down"),
    _s("pen_penUp", STACK, "pen up"),
    _s("pen_setPenColorToColor", STACK, "set pen color to {COLOR:color}"),
    _s("pen_setPenHueToNumber", STACK, "set pen color to {HUE:num}"),
    _s("pen_changePenHueBy", STACK, "change pen color by {HUE:num}"),
    _s("pen_changePenColorParamBy", STACK, "change pen {COLOR_PARAM:menu:pen_menu_colorParam} by {VALUE:num}"),
    _s("pen_setPenColorParamTo", STACK, "set pen {COLOR_PARAM:menu:pen_menu_colorParam} to {VALUE:num}"),
    _s("pen_changePenSizeBy", STACK, "change pen size by {SIZE:num}"),
    _s("pen_setPenSizeTo", STACK, "set pen size to {SIZE:num}"),
    _s("pen_setPenShadeToNumber", STACK, "set pen shade to {SHADE:num}"),
    _s("pen_changePenShadeBy", STACK, "change pen shade by {SHADE:num}"),
    # Music
    _s("music_playDrumForBeats", STACK, "play drum {DRUM:menu:music_menu_DRUM} for {BEATS:num} beats"),
    _s("music_restForBeats", STACK, "rest for {BEATS:num} beats"),
    _s("music_playNoteForBeats", STACK, "play note {NOTE:note} for {BEATS:num} beats"),
    _s("music_setInstrument", STACK, "set instrument to {INSTRUMENT:menu:music_menu_INSTRUMENT}"),
    _s("music_setTempo", STACK, "set tempo to {TEMPO:num}"),
    _s("music_changeTempo", STACK, "change tempo by {TEMPO:num}"),
    _s("music_getTempo", REPORTER, "tempo"),
    # Video sensing
    _s("videoSensing_whenMotionGreaterThan", HAT, "when video motion > {REFERENCE:num}"),
    _s("videoSensing_videoOn", REPORTER,
       "video {ATTRIBUTE:menu:videoSensing_menu_ATTRIBUTE} on {SUBJECT:menu:videoSensing_menu_SUBJECT}"),
    _s("videoSensing_videoToggle", STACK, "turn video {VIDEO_STATE:menu:videoSensing_menu_VIDEO_STATE}"),
    _s("videoSensing_setVideoTransparency", STACK, "set video transparency to {TRANSPARENCY:num}"),
    # Text to speech / translate
    _s("text2speech_speakAndWait", STACK, "speak {WORDS:text}"),
    _s("text2speech_setVoice", STACK, "set voice to {VOICE:menu:text2speech_menu_voices}"),
    _s("text2speech_setLanguage", STACK, "set language to {LANGUAGE:menu:text2speech_menu_languages}"),
    _s("translate_getTranslate", REPORTER, "translate {WORDS:text} to {LANGUAGE:menu:translate_menu_languages}"),
    _s("translate_getViewerLanguage", REPORTER, "language"),
]

for _spec in _SPEC_LIST:
    _spec.tokens = [tokenize_template(t) for t in _spec.templates]

SPECS: dict[str, BlockSpec] = {s.opcode: s for s in _SPEC_LIST}
PARSE_SPECS: list[BlockSpec] = [s for s in _SPEC_LIST if s.parseable]

# Blocks that only make sense on a sprite (not on the Stage).
SPRITE_ONLY_OPCODES = frozenset(
    [op for op in KNOWN_OPCODES if op.startswith("motion_")]
    + """looks_sayforsecs looks_say looks_thinkforsecs looks_think looks_show
    looks_hide looks_changesizeby looks_setsizeto looks_size looks_switchcostumeto
    looks_nextcostume looks_gotofrontback looks_goforwardbackwardlayers
    looks_costumenumbername event_whenthisspriteclicked event_whentouchingobject
    control_start_as_clone control_delete_this_clone sensing_touchingobject
    sensing_touchingcolor sensing_coloristouchingcolor sensing_distanceto
    sensing_setdragmode""".split()
)
STAGE_ONLY_OPCODES = frozenset(["event_whenstageclicked", "looks_switchbackdroptoandwait"])
