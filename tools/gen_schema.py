"""Generate src/scratch_mcp/schema.json from Scratch's real sources.

Inputs (all official Scratch code):
  --blocks   scratch-blocks src/blocks folder (npm package scratch-blocks)   -> shapes, input/field names, dropdown values
  --toolbox  scratch-gui src/lib/make-toolbox-xml.js                          -> shadow block types and defaults per input
  --ext      JSON written by tools/dump_extensions.js (from scratch-vm)       -> extension blocks, arguments, menus

    python tools/gen_schema.py --blocks .../package/src/blocks --toolbox make-toolbox-xml.js \
        --ext ext_dump.json --out src/scratch_mcp/schema.json
"""

from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path

SHAPES = {"shape_hat": "hat", "shape_bowler_hat": "hat", "shape_end": "cap", "shape_statement": "statement",
          "output_boolean": "boolean", "output_number": "reporter", "output_string": "reporter"}
CATEGORIES = {"colours_motion": "motion", "colours_looks": "looks", "colours_sounds": "sound", "colours_event": "events",
              "colours_control": "control", "colours_sensing": "sensing", "colours_operators": "operators",
              "colours_data": "variables", "colours_data_lists": "lists", "colours_more": "myblocks",
              "colours_pen": "pen", "colours_textfield": "primitive"}


# ---------------------------------------------------------------- scratch-blocks

def parse_blocks(folder: Path) -> dict:
    out: dict = {}
    for ts in sorted(folder.glob("*.ts")):
        src = ts.read_text()
        parts = re.split(r"\nBlockly\.Blocks(?:\.|\[')([A-Za-z0-9_]+)(?:'\])?", src)
        for i in range(1, len(parts), 2):
            op, body = parts[i], parts[i + 1]
            ext = re.findall(r"extensions: \[([^\]]*)\]", body)
            ext_tokens = re.findall(r"'(\w+)'", ext[0]) if ext else []
            shape = next((SHAPES[t] for t in ext_tokens if t in SHAPES), None)
            category = next((CATEGORIES[t] for t in ext_tokens if t in CATEGORIES), None)
            inputs, fields = {}, {}
            for m in re.finditer(r"\{\s*type: '(input_value|input_statement|field_[a-z_]+)',\s*name: '(\w+)'([^{}]*?)(?:options: \[(.*?)\n\s*\],?)?\s*\}", body, re.S):
                kind, name, rest, options = m.group(1), m.group(2), m.group(3), m.group(4)
                if kind == "input_statement":
                    inputs[name] = {"type": "statement"}
                elif kind == "input_value":
                    inputs[name] = {"type": "value", "boolean": "check: 'Boolean'" in rest}
                else:
                    ftype = kind[len("field_"):]
                    entry = {"type": ftype}
                    if ftype == "dropdown":
                        vals = re.findall(r",\s*'([^']*)'\s*\]", options or "")
                        entry["options"] = vals or None
                    fields[name] = entry
            out[op] = {"shape": shape, "category": category, "inputs": inputs, "fields": fields, "source": ts.name}
    return out


# ---------------------------------------------------------------- toolbox XML

class ToolboxParser(HTMLParser):
    """Collect, per block type, the shadow type / default value used for each input and field defaults."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[dict] = []
        self.blocks: dict[str, dict] = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        node = {"tag": tag, "attrs": a, "children": [], "text": ""}
        if self.stack:
            self.stack[-1]["children"].append(node)
        self.stack.append(node)

    def handle_endtag(self, tag):
        # tolerate unbalanced fragments from the JS template literals
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                node = self.stack[i]
                del self.stack[i:]
                if tag == "block" and node["attrs"].get("type") and not any(s["tag"] in ("value", "statement") for s in self.stack):
                    self.record(node)
                return

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]["text"] += data.strip()

    def record(self, node):
        op = node["attrs"]["type"]
        info = self.blocks.setdefault(op, {"inputs": {}, "fields": {}})
        for ch in node["children"]:
            if ch["tag"] == "value":
                name = ch["attrs"].get("name")
                shadow = next((c for c in ch["children"] if c["tag"] == "shadow"), None)
                block = next((c for c in ch["children"] if c["tag"] == "block"), None)
                entry = info["inputs"].setdefault(name, {})
                if shadow is not None:
                    entry["shadow"] = shadow["attrs"].get("type")
                    fld = next((c for c in shadow["children"] if c["tag"] == "field"), None)
                    if fld is not None and fld["text"] != "":
                        entry["default"] = fld["text"]
                if block is not None:
                    entry["default_block"] = block["attrs"].get("type")
            elif ch["tag"] == "field":
                info["fields"][ch["attrs"].get("name")] = ch["text"]
            elif ch["tag"] == "mutation":
                info["mutation"] = {k: v for k, v in ch["attrs"].items() if v is not None and "${" not in str(v)}


def parse_toolbox(path: Path) -> dict:
    p = ToolboxParser()
    p.feed(path.read_text())
    return p.blocks


# ---------------------------------------------------------------- manual knowledge scratch-blocks keeps in code

MENU_BLOCKS = {  # menu shadow opcode -> (field name, option values or 'dynamic:<what>')
    "motion_goto_menu": ("TO", "dynamic:sprites+_random_+_mouse_"),
    "motion_glideto_menu": ("TO", "dynamic:sprites+_random_+_mouse_"),
    "motion_pointtowards_menu": ("TOWARDS", "dynamic:sprites+_mouse_+_random_"),
    "looks_costume": ("COSTUME", "dynamic:costumes"),
    "looks_backdrops": ("BACKDROP", "dynamic:backdrops"),
    "sound_sounds_menu": ("SOUND_MENU", "dynamic:sounds"),
    "control_create_clone_of_menu": ("CLONE_OPTION", "dynamic:sprites+_myself_"),
    "sensing_touchingobjectmenu": ("TOUCHINGOBJECTMENU", "dynamic:sprites+_mouse_+_edge_"),
    "event_touchingobjectmenu": ("TOUCHINGOBJECTMENU", "dynamic:sprites+_mouse_+_edge_"),
    "sensing_distancetomenu": ("DISTANCETOMENU", "dynamic:sprites+_mouse_"),
    "sensing_of_object_menu": ("OBJECT", "dynamic:sprites+_stage_"),
    "sensing_keyoptions": ("KEY_OPTION", None),  # filled from key list
    "event_broadcast_menu": ("BROADCAST_OPTION", "dynamic:broadcasts"),
}
KEYS = (["space", "up arrow", "down arrow", "right arrow", "left arrow", "any"]
        + [chr(c) for c in range(ord("a"), ord("z") + 1)] + [str(d) for d in range(10)])
PRIMITIVES = {"math_number": "NUM", "math_integer": "NUM", "math_whole_number": "NUM", "math_positive_number": "NUM",
              "math_angle": "NUM", "colour_picker": "COLOUR", "text": "TEXT", "note": "NOTE", "matrix": "MATRIX"}


def build(blocks_dir: Path, toolbox: Path, ext_dump: Path) -> dict:
    sb = parse_blocks(blocks_dir)
    tb = parse_toolbox(toolbox)
    core: dict = {}
    for op, b in sb.items():
        if op.startswith(("colour_", "math_", "matrix", "note", "text")) and op in PRIMITIVES:
            continue
        entry = {"category": b["category"], "shape": b["shape"], "inputs": {}, "fields": dict(b["fields"])}
        tbi = tb.get(op, {})
        for name, inp in b["inputs"].items():
            item = dict(inp)
            if inp["type"] == "value":
                t = tbi.get("inputs", {}).get(name, {})
                if inp["boolean"]:
                    item["shadow"] = None
                else:
                    item["shadow"] = t.get("shadow") or "text"
                    if "default" in t:
                        item["default"] = t["default"]
            entry["inputs"][name] = item
        for fname, default in tbi.get("fields", {}).items():
            entry["fields"].setdefault(fname, {"type": "dropdown", "options": None})
            if default:
                entry["fields"][fname]["default"] = default
        if any(i["type"] == "statement" for i in entry["inputs"].values()) and entry["shape"] == "statement":
            entry["shape"] = "c"
        if "mutation" in tbi:
            entry["mutation"] = tbi["mutation"]
        entry["in_toolbox"] = op in tb
        core[op] = entry

    # menu shadow blocks
    for op, (fname, opts) in MENU_BLOCKS.items():
        e = core.setdefault(op, {"category": None, "shape": "menu", "inputs": {}, "fields": {}})
        e["shape"] = "menu"
        e["fields"] = {fname: {"type": "dropdown", "options": KEYS if opts is None else None,
                               **({"dynamic": opts[len("dynamic:"):]} if isinstance(opts, str) else {})}}
    # primitives (shadow-only blocks)
    for op, fname in PRIMITIVES.items():
        core[op] = {"category": "primitive", "shape": "primitive", "inputs": {}, "fields": {fname: {"type": "text"}}}

    # hand-written special cases (blocks whose fields are built from project data)
    core["control_stop"].update(fields={"STOP_OPTION": {"type": "dropdown", "options": ["all", "this script", "other scripts in sprite"]}},
                                mutation={"hasnext": "false"}, shape="cap")
    core["event_whenbroadcastreceived"]["fields"] = {"BROADCAST_OPTION": {"type": "broadcast"}}
    core["event_whenbackdropswitchesto"].update(fields={"BACKDROP": {"type": "dropdown", "options": None, "dynamic": "backdrops"}}, shape="hat")
    core["event_whengreaterthan"]["fields"]["WHENGREATERTHANMENU"].update(options=["LOUDNESS", "TIMER"])
    core["sensing_of"] = {"category": "sensing", "shape": "reporter", "in_toolbox": True,
                          "inputs": {"OBJECT": {"type": "value", "boolean": False, "shadow": "sensing_of_object_menu"}},
                          "fields": {"PROPERTY": {"type": "dropdown", "options": None, "dynamic": "properties of OBJECT"}}}
    for v in ("data_variable",):
        core[v]["fields"] = {"VARIABLE": {"type": "variable"}}
    core["data_listcontents"]["fields"] = {"LIST": {"type": "list"}}
    for op, e in core.items():
        if op.startswith("data_") and op != "data_variable" and op != "data_listcontents":
            for fname, f in e["fields"].items():
                if fname == "VARIABLE":
                    f["type"] = "variable"
                elif fname == "LIST":
                    f["type"] = "list"
    core["control_for_each"]["fields"] = {"VARIABLE": {"type": "variable"}}
    for op, e in core.items():
        e["fields"] = {k: v for k, v in e["fields"].items() if not (v.get("type") in ("image", "label", "label_serializable") and op.startswith(("argument_",)) is False)}
    core["argument_reporter_string_number"] = {"category": "myblocks", "shape": "reporter", "inputs": {}, "fields": {"VALUE": {"type": "text"}}}
    core["argument_reporter_boolean"] = {"category": "myblocks", "shape": "boolean", "inputs": {}, "fields": {"VALUE": {"type": "text"}}}
    for op in ("procedures_definition", "procedures_prototype", "procedures_call", "procedures_declaration",
               "argument_editor_boolean", "argument_editor_string_number"):
        core.setdefault(op, {"category": "myblocks", "shape": "special", "inputs": {}, "fields": {}})
    core["procedures_definition"].update(shape="hat", inputs={"custom_block": {"type": "value", "boolean": False, "shadow": "procedures_prototype"}})
    core["procedures_call"].update(shape="statement")
    core["event_broadcast"]["inputs"]["BROADCAST_INPUT"]["shadow"] = "event_broadcast_menu"
    core["event_broadcastandwait"]["inputs"]["BROADCAST_INPUT"]["shadow"] = "event_broadcast_menu"

    # blocks the toolbox builds dynamically (variables/lists) or doesn't list: shadows per input
    OVERRIDES = {
        ("data_setvariableto", "VALUE"): ("text", "0"), ("data_changevariableby", "VALUE"): ("math_number", "1"),
        ("data_addtolist", "ITEM"): ("text", "thing"), ("data_deleteoflist", "INDEX"): ("math_integer", "1"),
        ("data_insertatlist", "ITEM"): ("text", "thing"), ("data_insertatlist", "INDEX"): ("math_integer", "1"),
        ("data_replaceitemoflist", "INDEX"): ("math_integer", "1"), ("data_replaceitemoflist", "ITEM"): ("text", "thing"),
        ("data_itemoflist", "INDEX"): ("math_integer", "1"), ("data_itemnumoflist", "ITEM"): ("text", "thing"),
        ("data_listcontainsitem", "ITEM"): ("text", "thing"),
        ("control_for_each", "VALUE"): ("math_whole_number", "10"),
        ("event_whentouchingobject", "TOUCHINGOBJECTMENU"): ("event_touchingobjectmenu", None),
        ("looks_changestretchby", "CHANGE"): ("math_number", "10"), ("looks_setstretchto", "STRETCH"): ("math_number", "100"),
        ("motion_scroll_right", "DISTANCE"): ("math_number", "10"), ("motion_scroll_up", "DISTANCE"): ("math_number", "10"),
    }
    for (op, name), (shadow, default) in OVERRIDES.items():
        item = core[op]["inputs"][name]
        item["shadow"] = shadow
        if default is not None:
            item["default"] = default
    PLACEHOLDERS = {"${hello}": "Hello!", "${hmm}": "Hmm...", "${apple}": "apple", "${banana}": "banana",
                    "${letter}": "a", "${name}": "What's your name?"}
    for e in core.values():
        for item in e["inputs"].values():
            d = item.get("default")
            if isinstance(d, str) and d.startswith("${"):
                if d in PLACEHOLDERS:
                    item["default"] = PLACEHOLDERS[d]
                else:
                    del item["default"]  # costume / backdrop / sound names depend on the sprite
    for op in ("data_showvariable", "data_hidevariable"):
        core[op]["shape"] = "statement"
    for op in ("data_itemoflist", "data_itemnumoflist"):
        core[op]["shape"] = "reporter"
    core["control_stop"]["category"] = "control"
    for op in ("looks_backdrops", "looks_costume", "sound_sounds_menu"):
        core[op]["category"] = "menu"

    # extensions
    ext_data = json.loads(ext_dump.read_text())
    extensions: dict = {}
    for ext_id, ext in ext_data.items():
        if "error" in ext:
            continue
        exts_blocks = {}
        for b in ext["blocks"]:
            btype = {"command": "statement", "reporter": "reporter", "Boolean": "boolean", "hat": "hat",
                     "event": "hat", "conditional": "c", "loop": "c"}.get(b["blockType"], b["blockType"])
            if b["blockType"] == "command" and b.get("isTerminal"):
                btype = "cap"
            inputs, fields = {}, {}
            for aname, a in b["arguments"].items():
                menu = ext["menus"].get(a["menu"]) if a.get("menu") else None
                if menu is not None and not menu["acceptReporters"]:
                    fields[aname] = {"type": "dropdown", "options": menu["items"] if isinstance(menu["items"], list) else None}
                    if a.get("default") is not None:
                        fields[aname]["default"] = str(a["default"])
                elif menu is not None:
                    inputs[aname] = {"type": "value", "boolean": False, "shadow": menu["opcode"], "menu": a["menu"]}
                    if a.get("default") is not None:
                        inputs[aname]["default"] = str(a["default"])
                else:
                    t = a["type"]
                    shadow = {"number": "math_number", "string": "text", "color": "colour_picker", "angle": "math_angle",
                              "note": "note", "matrix": "matrix", "boolean": None}.get(t, "text")
                    inputs[aname] = {"type": "value", "boolean": t == "boolean", "shadow": shadow}
                    if a.get("default") is not None:
                        inputs[aname]["default"] = str(a["default"])
            exts_blocks[b["opcode"]] = {"category": ext_id, "shape": btype, "inputs": inputs, "fields": fields, "text": b["text"], "ext": ext_id}
        menus = {}
        for mname, m in ext["menus"].items():
            menus[m["opcode"]] = {"category": ext_id, "shape": "menu", "inputs": {}, "ext": ext_id,
                                  "fields": {mname: {"type": "dropdown", "options": m["items"] if isinstance(m["items"], list) else None}}}
        extensions[ext_id] = {"name": ext["name"], "blocks": sorted(exts_blocks), "menus": sorted(menus)}
        core.update(exts_blocks)
        core.update(menus)

    return {"generated_from": {"scratch-blocks": "npm scratch-blocks", "toolbox": "scratch-gui make-toolbox-xml.js",
                               "extensions": "scratch-vm extension getInfo()"},
            "blocks": dict(sorted(core.items())), "extensions": extensions}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", required=True)
    ap.add_argument("--toolbox", required=True)
    ap.add_argument("--ext", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    schema = build(Path(a.blocks), Path(a.toolbox), Path(a.ext))
    Path(a.out).write_text(json.dumps(schema, indent=1, ensure_ascii=False) + "\n")
    n = len(schema["blocks"])
    print(f"wrote {a.out}: {n} opcodes, {len(schema['extensions'])} extensions")
