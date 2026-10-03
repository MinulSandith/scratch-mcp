"""Generic Scratch block-graph engine.

Works on one target's ``blocks`` dict in project.json and understands the real data model:
``next`` / ``parent`` / ``topLevel``, ``inputs`` ([1|2|3, ...] with shadows and compressed
primitives), ``fields``, ``mutation``, comments, variables/lists/broadcasts. Every operation
is driven by ``schema.json`` (the real Scratch block definitions), so any valid program can be
built - there are no script templates.

Block "tree" notation accepted by ``Graph.add``::

    {"opcode": "control_repeat",
     "inputs": {"TIMES": 10,                                     # literal -> default shadow type
                "SUBSTACK": [ {"opcode": "motion_movesteps", "inputs": {"STEPS": 5}} ]},
     "next": [ {"opcode": "looks_hide"} ]}                       # following blocks (a list)

Input values: a literal (number/text), ``{"variable": "score"}``, ``{"list": "items"}``,
``{"menu": "_mouse_"}``, a block tree (reporter / boolean), or ``null`` (default). Statement
inputs take a list of block trees. Fields take the dropdown value (``"fields": {"EFFECT": "ghost"}``).
Custom block calls: ``{"call": "jump %s", "args": [10]}``.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from . import schema
from .schema import (BROADCAST_CODE, LIST_CODE, NUMERIC_SHADOWS, PRIMITIVE_CODE, VARIABLE_CODE)
from .textparse import make_id_factory


class EngineError(ValueError):
    """User-facing problem with a block operation."""


_NUM_RE = re.compile(r"^\s*-?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?\s*$", re.IGNORECASE)


def _is_primitive(v: Any) -> bool:
    return isinstance(v, list) and len(v) >= 2 and isinstance(v[0], int)


class Graph:
    def __init__(self, project: dict[str, Any], target: dict[str, Any]):
        self.project = project
        self.target = target
        self.stage = next(t for t in project["targets"] if t.get("isStage"))
        self.blocks: dict[str, Any] = target.setdefault("blocks", {})
        self.new_id = make_id_factory(project)
        self.created: list[str] = []  # ids created by the current operation
        self.notes: list[str] = []

    # ------------------------------------------------------------------ lookup

    def get(self, bid: str) -> dict[str, Any]:
        b = self.blocks.get(bid)
        if not isinstance(b, dict):
            raise EngineError(f"No block with id '{bid}' in {self._who()}.")
        return b

    def _who(self) -> str:
        return "the Stage" if self.target.get("isStage") else f"sprite '{self.target.get('name')}'"

    def spec_of(self, opcode: str) -> dict[str, Any]:
        s = schema.spec(opcode)
        if s is None:
            near = [o for o in schema.blocks() if opcode.lower() in o.lower()][:6]
            raise EngineError(f"Unknown opcode '{opcode}'." + (f" Similar: {', '.join(near)}" if near else
                              " Use block_manager catalog to browse opcodes."))
        return s

    def top_levels(self) -> list[str]:
        return [i for i, b in self.blocks.items() if isinstance(b, dict) and b.get("topLevel")]

    def stack_ids(self, first: str) -> list[str]:
        out, seen = [], set()
        cur: str | None = first
        while cur and cur not in seen and cur in self.blocks:
            seen.add(cur)
            out.append(cur)
            cur = self.blocks[cur].get("next")
        return out

    def referenced_ids(self, block: dict[str, Any]) -> list[str]:
        ids = []
        for inp in (block.get("inputs") or {}).values():
            if isinstance(inp, list):
                ids += [v for v in inp[1:] if isinstance(v, str)]
        return ids

    def subtree_ids(self, bid: str, *, include_next: bool) -> list[str]:
        """bid, everything inside its inputs, and (optionally) the blocks that follow it."""
        out: list[str] = []
        todo = [bid]
        seen: set[str] = set()
        while todo:
            cur = todo.pop()
            if cur in seen or cur not in self.blocks or not isinstance(self.blocks[cur], dict):
                continue
            seen.add(cur)
            out.append(cur)
            b = self.blocks[cur]
            todo += self.referenced_ids(b)
            if include_next or cur != bid:
                nxt = b.get("next")
                if nxt:
                    todo.append(nxt)
        return out

    # --------------------------------------------------------- variables & co

    def _scopes(self) -> list[dict[str, Any]]:
        return [self.target] if self.target is self.stage else [self.target, self.stage]

    def find_named(self, key: str, name: str) -> tuple[str, str] | None:
        for scope in self._scopes():
            for vid, entry in (scope.get(key) or {}).items():
                if entry and entry[0] == name:
                    return entry[0], vid
        return None

    def variable(self, name: str, create: bool = True) -> tuple[str, str]:
        found = self.find_named("variables", name)
        if found:
            return found
        if not create:
            raise EngineError(f"No variable named '{name}'. Create it with variable_manager create_variable.")
        vid = self.new_id()
        self.stage.setdefault("variables", {})[vid] = [name, 0]
        self.notes.append(f"created variable '{name}' (for all sprites)")
        return name, vid

    def list_(self, name: str, create: bool = True) -> tuple[str, str]:
        found = self.find_named("lists", name)
        if found:
            return found
        if not create:
            raise EngineError(f"No list named '{name}'.")
        lid = self.new_id()
        self.stage.setdefault("lists", {})[lid] = [name, []]
        self.notes.append(f"created list '{name}' (for all sprites)")
        return name, lid

    def broadcast(self, name: str) -> tuple[str, str]:
        broadcasts = self.stage.setdefault("broadcasts", {})
        for bid, existing in broadcasts.items():
            if existing == name:
                return existing, bid
        for bid, existing in broadcasts.items():
            if existing.lower() == name.lower():
                return existing, bid
        bid = self.new_id()
        broadcasts[bid] = name
        self.notes.append(f"created broadcast message '{name}'")
        return name, bid

    # ------------------------------------------------------------- building

    def add(self, trees: list[dict[str, Any]] | dict[str, Any], *, x: float | None = None, y: float | None = None,
            after: str | None = None, into: str | None = None, input: str | None = None,
            replace_input_of: str | None = None) -> list[str]:
        """Create blocks from trees and place them. Returns the ids of the first block of each placed stack.

        Placement (one of): x/y (new top-level script, default: below existing scripts), ``after`` (insert
        after that block), ``into``+``input`` (put into that statement input), ``replace_input_of``+``input``
        (a reporter into a value input).
        """
        if isinstance(trees, dict):
            trees = [trees]
        if not trees:
            raise EngineError("No blocks given.")
        self.created = []
        placements = sum(p is not None for p in (after, into, replace_input_of))
        if placements > 1:
            raise EngineError("Use only one of after / into / replace_input_of.")
        if (after is not None or into is not None) and len(trees) > 1:
            # several blocks placed at one spot are chained into a single stack, in order
            head = dict(trees[0])
            head["next"] = [*(head.get("next") or []), *trees[1:]]
            trees = [head]
        try:
            firsts = [self._build_stack_from_tree(t, None) for t in trees]
            if after is not None:
                if len(firsts) != 1:
                    raise EngineError("'after' takes one script; pass a single tree with a 'next' list.")
                self.insert_after(firsts[0], after)
            elif into is not None:
                if len(firsts) != 1:
                    raise EngineError("'into' takes one stack; pass a single tree with a 'next' list.")
                self.insert_into(firsts[0], into, input or "SUBSTACK")
            elif replace_input_of is not None:
                if len(firsts) != 1:
                    raise EngineError("A value input takes exactly one reporter.")
                self.set_reporter(firsts[0], replace_input_of, input or "")
            else:
                px, py = (x, y) if x is not None and y is not None else self.free_position()
                for first in firsts:
                    self._make_top(first, px, py)
                    py += self.stack_height(first) + 40
        except EngineError:
            for bid in self.created:  # roll back everything this call created
                self.blocks.pop(bid, None)
            raise
        return firsts

    def _build_stack_from_tree(self, tree: dict[str, Any], parent: str | None) -> str:
        first = self.build(tree, parent)
        nxt = tree.get("next")
        prev = first
        if nxt:
            seq = nxt if isinstance(nxt, list) else [nxt]
            for t in seq:
                bid = self.build(t, prev)
                self._link_next(prev, bid)
                prev = bid
        return first

    def _link_next(self, prev: str, nxt: str) -> None:
        pb = self.blocks[prev]
        spec = schema.spec(pb["opcode"]) or {}
        if self._is_cap(pb, spec):
            raise EngineError(f"'{pb['opcode']}' is a cap block; nothing can follow it.")
        nb = self.blocks[nxt]
        nspec = schema.spec(nb["opcode"]) or {}
        if nspec.get("shape") in ("hat",) or nspec.get("shape") in schema.REPORTER_SHAPES:
            raise EngineError(f"'{nb['opcode']}' ({nspec.get('shape')}) can't be placed in a stack after '{pb['opcode']}'.")
        pb["next"] = nxt
        nb["parent"] = prev

    def _is_cap(self, block: dict[str, Any], spec: dict[str, Any]) -> bool:
        if block.get("opcode") == "control_stop":
            return (block.get("mutation") or {}).get("hasnext") != "true"
        return spec.get("shape") == "cap"

    def build(self, tree: dict[str, Any], parent: str | None, *, shadow: bool = False) -> str:
        """Build one block (and everything in its inputs) - not its 'next'. Returns its id."""
        if not isinstance(tree, dict):
            raise EngineError(f"A block must be an object like {{\"opcode\": ...}}, got {tree!r}.")
        if "call" in tree:
            return self._build_call(tree, parent)
        opcode = tree.get("opcode")
        if not opcode:
            raise EngineError(f"Block is missing 'opcode': {json.dumps(tree)[:120]}")
        spec = self.spec_of(opcode)
        if spec["shape"] == "special" or opcode in ("procedures_call", "procedures_definition", "procedures_prototype"):
            raise EngineError(f"'{opcode}' is built with procedure helpers (block_manager define_procedure / {{\"call\": ...}}).")
        bid = tree.get("id") or self.new_id()
        if bid in self.blocks:
            raise EngineError(f"Block id '{bid}' already exists.")
        block: dict[str, Any] = {"opcode": opcode, "next": None, "parent": parent, "inputs": {}, "fields": {},
                                 "shadow": shadow, "topLevel": False}
        self.blocks[bid] = block
        self.created.append(bid)
        unknown_in = set((tree.get("inputs") or {})) - set(spec["inputs"])
        if unknown_in:
            raise EngineError(f"'{opcode}' has no input(s) {sorted(unknown_in)}. Inputs: {sorted(spec['inputs']) or 'none'}.")
        unknown_f = set((tree.get("fields") or {})) - set(spec["fields"])
        if unknown_f:
            raise EngineError(f"'{opcode}' has no field(s) {sorted(unknown_f)}. Fields: {sorted(spec['fields']) or 'none'}.")
        for name, fspec in spec["fields"].items():
            given = (tree.get("fields") or {}).get(name)
            value = self._field_value(opcode, name, fspec, given)
            if value is not None:
                block["fields"][name] = value
        for name, ispec in spec["inputs"].items():
            given = (tree.get("inputs") or {}).get(name)
            inp = self._make_input(bid, opcode, name, ispec, given)
            if inp is not None:
                block["inputs"][name] = inp
        if spec.get("mutation"):
            block["mutation"] = {"tagName": "mutation", "children": [], **tree.get("mutation", spec["mutation"])}
        if opcode == "control_stop":
            hasnext = "true" if (block["fields"]["STOP_OPTION"][0] == "other scripts in sprite") else "false"
            block["mutation"] = {"tagName": "mutation", "children": [], "hasnext": hasnext}
        ext = spec.get("ext")
        if ext:
            exts = self.project.setdefault("extensions", [])
            if ext not in exts:
                exts.append(ext)
                self.notes.append(f"enabled extension '{ext}'")
        self._check_target_kind(opcode)
        return bid

    def _check_target_kind(self, opcode: str) -> None:
        from .blocks import SPRITE_ONLY_OPCODES, STAGE_ONLY_OPCODES

        if self.target.get("isStage") and opcode in SPRITE_ONLY_OPCODES:
            raise EngineError(f"'{opcode}' only works on sprites, not on the Stage.")
        if not self.target.get("isStage") and opcode in STAGE_ONLY_OPCODES:
            raise EngineError(f"'{opcode}' only works on the Stage, not on sprites.")

    def _field_value(self, opcode: str, name: str, fspec: dict[str, Any], given: Any) -> list[Any] | None:
        ftype = fspec["type"]
        if given is None:
            default = fspec.get("default")
            if ftype in ("variable", "list", "broadcast"):
                raise EngineError(f"'{opcode}' needs field '{name}' (a {ftype} name).")
            if ftype == "dropdown" and fspec.get("options") and default is None:
                raise EngineError(f"'{opcode}' needs field '{name}'. Options: {fspec['options']}")
            if default is None and ftype == "dropdown" and fspec.get("dynamic"):
                raise EngineError(f"'{opcode}' needs field '{name}' ({fspec['dynamic']}).")
            if default is None:
                return None
            given = default
        if ftype == "variable":
            n, vid = self.variable(str(given))
            return [n, vid]
        if ftype == "list":
            n, lid = self.list_(str(given))
            return [n, lid]
        if ftype == "broadcast":
            n, bid = self.broadcast(str(given))
            return [n, bid]
        value = str(given)
        options = fspec.get("options")
        if options:
            match = next((o for o in options if o == value), None) or \
                next((o for o in options if o.lower() == value.lower()), None)
            if match is None:
                raise EngineError(f"'{value}' is not a valid value for {opcode}.{name}. Options: {options}")
            value = match
        return [value, None]

    # inputs ------------------------------------------------------------

    def _make_input(self, bid: str, opcode: str, name: str, ispec: dict[str, Any], given: Any) -> list[Any] | None:
        if ispec["type"] == "statement":
            if given is None or given == []:
                return None
            stack = given if isinstance(given, list) else [given]
            first = self._build_chain(stack, bid)
            return [2, first]
        if ispec.get("boolean"):
            if given is None:
                return None
            if not isinstance(given, dict):
                raise EngineError(f"{opcode}.{name} needs a boolean block (e.g. an operator_equals tree), got {given!r}.")
            child = self._reporter_child(given, bid, opcode, name, boolean=True)
            return [2, child]
        # value input
        if given is None:
            return self._default_input(bid, ispec)
        if isinstance(given, dict):
            if "variable" in given:
                n, vid = self.variable(str(given["variable"]))
                return [3, [VARIABLE_CODE, n, vid], self._shadow_value(bid, ispec)]
            if "list" in given:
                n, lid = self.list_(str(given["list"]))
                return [3, [LIST_CODE, n, lid], self._shadow_value(bid, ispec)]
            if "menu" in given:
                return self._literal_input(bid, opcode, name, ispec, given["menu"])
            child = self._reporter_child(given, bid, opcode, name, boolean=False)
            return [3, child, self._shadow_value(bid, ispec)]
        return self._literal_input(bid, opcode, name, ispec, given)

    def _build_chain(self, trees: list[dict[str, Any]], parent: str) -> str:
        first = prev = None
        for t in trees:
            bid = self.build(t, prev or parent)
            if prev:
                self._link_next(prev, bid)
            else:
                first = bid
            prev = bid
            nxt = t.get("next") if isinstance(t, dict) else None
            for extra in (nxt if isinstance(nxt, list) else [nxt] if nxt else []):
                nb = self.build(extra, prev)
                self._link_next(prev, nb)
                prev = nb
        assert first
        spec0 = schema.spec(self.blocks[first]["opcode"]) or {}
        if spec0.get("shape") in ("hat",) or spec0.get("shape") in schema.REPORTER_SHAPES:
            raise EngineError(f"A {spec0.get('shape')} block ('{self.blocks[first]['opcode']}') can't start a C-block's inner stack.")
        return first

    def _reporter_child(self, tree: dict[str, Any], parent: str, opcode: str, name: str, boolean: bool) -> str:
        child = self.build(tree, parent)
        cs = schema.spec(self.blocks[child]["opcode"]) or {}
        shape = cs.get("shape")
        if self.blocks[child]["opcode"] in ("argument_reporter_boolean", "argument_reporter_string_number",
                                            "procedures_call"):
            shape = "boolean" if self.blocks[child]["opcode"] == "argument_reporter_boolean" else "reporter"
        if shape not in schema.REPORTER_SHAPES:
            raise EngineError(f"{opcode}.{name} needs a reporter block, but '{tree.get('opcode')}' is a {shape} block.")
        if boolean and shape != "boolean":
            raise EngineError(f"{opcode}.{name} needs a boolean block, but '{tree.get('opcode')}' is a round reporter.")
        return child

    def _shadow_value(self, bid: str, ispec: dict[str, Any]) -> Any:
        """The shadow kept underneath a reporter: compressed primitive or a shadow block id."""
        shadow = ispec.get("shadow")
        if shadow in PRIMITIVE_CODE:
            return [PRIMITIVE_CODE[shadow], str(ispec.get("default", ""))]
        if shadow == "event_broadcast_menu":
            n, b = self.broadcast(self._default_broadcast())
            return [BROADCAST_CODE, n, b]
        if shadow:
            return self._make_shadow_block(bid, shadow, ispec.get("default"))
        return None

    def _default_broadcast(self) -> str:
        return next(iter((self.stage.get("broadcasts") or {}).values()), "message1")

    def _default_input(self, bid: str, ispec: dict[str, Any]) -> list[Any] | None:
        shadow = ispec.get("shadow")
        if shadow in PRIMITIVE_CODE:
            return [1, [PRIMITIVE_CODE[shadow], str(ispec.get("default", ""))]]
        if shadow == "event_broadcast_menu":
            n, b = self.broadcast(self._default_broadcast())
            return [1, [BROADCAST_CODE, n, b]]
        if shadow:
            return [1, self._make_shadow_block(bid, shadow, ispec.get("default"))]
        return None

    def _literal_input(self, bid: str, opcode: str, name: str, ispec: dict[str, Any], value: Any) -> list[Any]:
        shadow = ispec.get("shadow")
        if isinstance(value, bool):
            value = str(value).lower()
        if not isinstance(value, (str, int, float)):
            raise EngineError(f"{opcode}.{name}: unsupported value {value!r}.")
        text = _fmt_number(value) if isinstance(value, (int, float)) else str(value)
        if shadow in NUMERIC_SHADOWS:
            if text.strip() and not _NUM_RE.match(text):
                raise EngineError(f"{opcode}.{name} expects a number, got {text!r}. "
                                  "To use text or a reporter, pass a block tree instead.")
            return [1, [PRIMITIVE_CODE[shadow], text.strip()]]
        if shadow in PRIMITIVE_CODE:  # text, colour_picker
            if shadow == "colour_picker" and not re.match(r"^#[0-9a-fA-F]{6}$", text):
                raise EngineError(f"{opcode}.{name} expects a colour like '#ff8800', got {text!r}.")
            return [1, [PRIMITIVE_CODE[shadow], text.lower() if shadow == "colour_picker" else text]]
        if shadow == "event_broadcast_menu":
            n, b = self.broadcast(text)
            return [1, [BROADCAST_CODE, n, b]]
        if shadow:
            return [1, self._make_shadow_block(bid, shadow, text, check=(opcode, name))]
        raise EngineError(f"{opcode}.{name} has no literal form; pass a block tree.")

    def _make_shadow_block(self, parent: str, shadow_op: str, value: Any, *, check: tuple[str, str] | None = None) -> str:
        sspec = self.spec_of(shadow_op)
        sid = self.new_id()
        fields: dict[str, Any] = {}
        for fname, fspec in sspec["fields"].items():
            v = value if value is not None else fspec.get("default")
            if v is None:
                v = self._dynamic_default(shadow_op, fspec)
            if fspec.get("options") and v is not None:
                match = next((o for o in fspec["options"] if o.lower() == str(v).lower()), None)
                if match is None:
                    raise EngineError(f"'{v}' is not valid for {check[0]}.{check[1]}. Options: {fspec['options']}" if check
                                      else f"'{v}' is not a valid {shadow_op} value.")
                v = match
            elif v is not None and fspec.get("dynamic"):
                v = self._normalize_dynamic(shadow_op, fspec, str(v))
            fields[fname] = [str(v) if v is not None else "", None]
        self.blocks[sid] = {"opcode": shadow_op, "next": None, "parent": parent, "inputs": {}, "fields": fields,
                            "shadow": True, "topLevel": False}
        self.created.append(sid)
        ext = sspec.get("ext")
        if ext:
            exts = self.project.setdefault("extensions", [])
            if ext not in exts:
                exts.append(ext)
        return sid

    SPECIAL_MENU_VALUES = {"mouse-pointer": "_mouse_", "mouse pointer": "_mouse_", "random position": "_random_",
                           "random direction": "_random_", "edge": "_edge_", "myself": "_myself_", "stage": "_stage_"}

    def _normalize_dynamic(self, shadow_op: str, fspec: dict[str, Any], value: str) -> str:
        v = value.strip()
        if shadow_op in ("sensing_of_object_menu",) and v.lower() == "stage":
            return "_stage_"
        mapped = self.SPECIAL_MENU_VALUES.get(v.lower())
        dyn = fspec.get("dynamic", "")
        if mapped and ("_" + mapped.strip("_") + "_") in dyn.replace("+", " ") .replace(" ", "+") or (mapped and mapped in dyn):
            return mapped
        return value

    def _dynamic_default(self, shadow_op: str, fspec: dict[str, Any]) -> str | None:
        dyn = fspec.get("dynamic", "")
        if "costumes" in dyn:
            c = self.target.get("costumes") or []
            return c[0]["name"] if c else ""
        if "backdrops" in dyn:
            c = self.stage.get("costumes") or []
            return c[0]["name"] if c else ""
        if "sounds" in dyn:
            c = self.target.get("sounds") or []
            return c[0]["name"] if c else ""
        for token in ("_random_", "_mouse_", "_myself_", "_stage_"):
            if token in dyn:
                return token
        if "broadcasts" in dyn:
            return self._default_broadcast()
        return ""

    # custom blocks -------------------------------------------------------

    def procedures(self) -> dict[str, dict[str, Any]]:
        out = {}
        for bid, b in self.blocks.items():
            if isinstance(b, dict) and b.get("opcode") == "procedures_prototype":
                m = b.get("mutation") or {}
                try:
                    out[m.get("proccode", "")] = {
                        "prototype": bid, "definition": b.get("parent"),
                        "argumentids": json.loads(m.get("argumentids") or "[]"),
                        "argumentnames": json.loads(m.get("argumentnames") or "[]"),
                        "argumentdefaults": json.loads(m.get("argumentdefaults") or "[]"),
                        "warp": str(m.get("warp")).lower() == "true"}
                except json.JSONDecodeError:
                    continue
        return out

    def define_procedure(self, proccode: str, argument_names: list[str], argument_types: list[str] | None = None,
                         warp: bool = False, x: float | None = None, y: float | None = None) -> str:
        """Create a 'define' hat. ``proccode`` uses %s (text/number) and %b (boolean) placeholders, e.g. 'jump %s %b'."""
        slots = re.findall(r"%[sb]", proccode)
        if len(slots) != len(argument_names):
            raise EngineError(f"proccode '{proccode}' has {len(slots)} input slot(s) but {len(argument_names)} argument name(s).")
        if proccode in self.procedures():
            raise EngineError(f"A custom block '{proccode}' already exists in {self._who()}.")
        if len(set(argument_names)) != len(argument_names):
            raise EngineError("Argument names must be unique.")
        self.created = []
        arg_ids = [self.new_id() for _ in argument_names]
        def_id, proto_id = self.new_id(), self.new_id()
        self.blocks[def_id] = {"opcode": "procedures_definition", "next": None, "parent": None,
                               "inputs": {"custom_block": [1, proto_id]}, "fields": {}, "shadow": False, "topLevel": False}
        self.blocks[proto_id] = {"opcode": "procedures_prototype", "next": None, "parent": def_id, "inputs": {},
                                 "fields": {}, "shadow": True, "topLevel": False}
        defaults = []
        for aid, aname, slot in zip(arg_ids, argument_names, slots):
            op = "argument_reporter_boolean" if slot == "%b" else "argument_reporter_string_number"
            rid = self.new_id()
            self.blocks[rid] = {"opcode": op, "next": None, "parent": proto_id, "inputs": {}, "fields": {"VALUE": [aname, None]},
                                "shadow": True, "topLevel": False}
            self.blocks[proto_id]["inputs"][aid] = [1, rid]
            defaults.append("false" if slot == "%b" else "")
        self.blocks[proto_id]["mutation"] = {
            "tagName": "mutation", "children": [], "proccode": proccode, "argumentids": json.dumps(arg_ids),
            "argumentnames": json.dumps(argument_names), "argumentdefaults": json.dumps(defaults),
            "warp": "true" if warp else "false"}
        px, py = (x, y) if x is not None and y is not None else self.free_position()
        self._make_top(def_id, px, py)
        self.created = [def_id, proto_id]
        return def_id

    def _build_call(self, tree: dict[str, Any], parent: str | None) -> str:
        proccode = tree["call"]
        proc = self.procedures().get(proccode)
        if proc is None:
            raise EngineError(f"No custom block '{proccode}'. Defined: {sorted(self.procedures()) or 'none'}")
        args = tree.get("args") or []
        slots = re.findall(r"%[sb]", proccode)
        if len(args) != len(slots):
            raise EngineError(f"'{proccode}' takes {len(slots)} argument(s), got {len(args)}.")
        bid = self.new_id()
        block = {"opcode": "procedures_call", "next": None, "parent": parent, "inputs": {}, "fields": {},
                 "shadow": False, "topLevel": False,
                 "mutation": {"tagName": "mutation", "children": [], "proccode": proccode,
                              "argumentids": json.dumps(proc["argumentids"]), "warp": "true" if proc["warp"] else "false"}}
        self.blocks[bid] = block
        self.created.append(bid)
        for aid, slot, val in zip(proc["argumentids"], slots, args):
            ispec = {"type": "value", "boolean": slot == "%b", "shadow": None if slot == "%b" else "text"}
            inp = self._make_input(bid, "procedures_call", aid, ispec, val)
            if inp is not None:
                block["inputs"][aid] = inp
        return bid

    # ------------------------------------------------------------ placement

    def free_position(self) -> tuple[float, float]:
        tops = [self.blocks[t] for t in self.top_levels() if isinstance(self.blocks[t].get("y"), (int, float))]
        if not tops:
            return 48, 48
        left = min(t.get("x", 0) for t in tops)
        bottom = max(t.get("y", 0) + self.stack_height(next(k for k, v in self.blocks.items() if v is t)) for t in tops)
        return left, bottom + 48

    def stack_height(self, first: str) -> float:
        height, seen, cur = 0.0, set(), first
        while cur and cur not in seen and isinstance(self.blocks.get(cur), dict):
            seen.add(cur)
            b = self.blocks[cur]
            height += 48
            for nm in ("SUBSTACK", "SUBSTACK2"):
                inp = (b.get("inputs") or {}).get(nm)
                if isinstance(inp, list) and len(inp) > 1 and isinstance(inp[1], str):
                    height += self.stack_height(inp[1]) + 24
            cur = b.get("next")
        return height

    def _make_top(self, bid: str, x: float, y: float) -> None:
        b = self.blocks[bid]
        b.update(parent=None, topLevel=True, x=round(x), y=round(y))

    def detach(self, bid: str, x: float | None = None, y: float | None = None) -> None:
        """Pull a block (with everything after it) out of wherever it is; it becomes a top-level script."""
        b = self.get(bid)
        if b.get("shadow"):
            raise EngineError("Shadow blocks can't be moved on their own; edit the input instead.")
        parent = b.get("parent")
        if parent is not None:
            p = self.get(parent)
            if p.get("next") == bid:
                p["next"] = None
            else:
                for name, inp in list((p.get("inputs") or {}).items()):
                    if isinstance(inp, list) and bid in inp[1:]:
                        if len(inp) == 3 and inp[0] == 3:
                            p["inputs"][name] = [1, inp[2]]  # the shadow shows again
                        else:
                            del p["inputs"][name]
                        break
        if x is None or y is None:
            x, y = self.free_position()
        self._make_top(bid, x, y)

    def insert_after(self, first: str, after: str) -> None:
        """Place stack ``first`` right after block ``after``; the old tail follows the inserted stack."""
        a = self.get(after)
        aspec = schema.spec(a["opcode"]) or {}
        if a.get("shadow"):
            raise EngineError("Can't attach after a shadow block.")
        if self._is_cap(a, aspec):
            raise EngineError(f"'{a['opcode']}' is a cap block; nothing can follow it.")
        if aspec.get("shape") in schema.REPORTER_SHAPES:
            raise EngineError("Can't attach a stack after a reporter.")
        fb = self.get(first)
        fs = schema.spec(fb["opcode"]) or {}
        if fs.get("shape") in ("hat",) or fs.get("shape") in schema.REPORTER_SHAPES:
            raise EngineError(f"A {fs.get('shape')} block ('{fb['opcode']}') can't go after another block.")
        if first in self.subtree_ids(after, include_next=False) or after in self.stack_ids(first):
            raise EngineError("Can't attach a block inside itself.")
        old_next = a.get("next")
        last = self.stack_ids(first)[-1]
        if old_next:
            if self._is_cap(self.blocks[last], schema.spec(self.blocks[last]["opcode"]) or {}):
                raise EngineError(f"The stack ends in a cap block ('{self.blocks[last]['opcode']}'), so the blocks "
                                  f"that follow '{a['opcode']}' have nowhere to go. Use detach/delete first.")
            self.blocks[last]["next"] = old_next
            self.blocks[old_next]["parent"] = last
        a["next"] = first
        fb.update(parent=after, topLevel=False)
        fb.pop("x", None)
        fb.pop("y", None)

    def insert_into(self, first: str, into: str, input_name: str) -> None:
        p = self.get(into)
        pspec = self.spec_of(p["opcode"])
        ispec = pspec["inputs"].get(input_name)
        if not ispec or ispec["type"] != "statement":
            raise EngineError(f"'{p['opcode']}' has no statement input '{input_name}'. "
                              f"Statement inputs: {[n for n, i in pspec['inputs'].items() if i['type'] == 'statement'] or 'none'}")
        fb = self.get(first)
        fs = schema.spec(fb["opcode"]) or {}
        if fs.get("shape") in ("hat",) or fs.get("shape") in schema.REPORTER_SHAPES:
            raise EngineError(f"A {fs.get('shape')} block ('{fb['opcode']}') can't go inside a C block.")
        if first in self.subtree_ids(into, include_next=False) or into in self.subtree_ids(first, include_next=True):
            raise EngineError("Can't put a block inside itself.")
        existing = (p.get("inputs") or {}).get(input_name)
        old_first = existing[1] if isinstance(existing, list) and len(existing) > 1 and isinstance(existing[1], str) else None
        if old_first:
            last = self.stack_ids(first)[-1]
            if self._is_cap(self.blocks[last], schema.spec(self.blocks[last]["opcode"]) or {}):
                raise EngineError("The new stack ends in a cap block but the C block already has blocks in that slot; "
                                  "detach the old blocks first.")
            self.blocks[last]["next"] = old_first
            self.blocks[old_first]["parent"] = last
        p.setdefault("inputs", {})[input_name] = [2, first]
        fb.update(parent=into, topLevel=False)
        fb.pop("x", None)
        fb.pop("y", None)

    def set_reporter(self, rid: str, parent: str, input_name: str) -> None:
        """Put reporter ``rid`` into value input ``input_name`` of ``parent`` (the old content is removed)."""
        p = self.get(parent)
        pspec = self.spec_of(p["opcode"]) if p["opcode"] != "procedures_call" else None
        rb = self.get(rid)
        shape = (schema.spec(rb["opcode"]) or {}).get("shape")
        if rb["opcode"] in ("argument_reporter_string_number", "procedures_call"):
            shape = "reporter"
        if rb["opcode"] == "argument_reporter_boolean":
            shape = "boolean"
        if shape not in schema.REPORTER_SHAPES:
            raise EngineError(f"'{rb['opcode']}' is not a reporter/boolean block.")
        if pspec is not None:
            ispec = pspec["inputs"].get(input_name)
            if not ispec or ispec["type"] != "value":
                raise EngineError(f"'{p['opcode']}' has no value input '{input_name}'. "
                                  f"Value inputs: {[n for n, i in pspec['inputs'].items() if i['type'] == 'value']}")
            if ispec.get("boolean") and shape != "boolean":
                raise EngineError(f"{p['opcode']}.{input_name} needs a boolean block.")
        if rid in self.subtree_ids(parent, include_next=False) or parent in self.subtree_ids(rid, include_next=False):
            raise EngineError("Can't put a block inside itself.")
        old = (p.get("inputs") or {}).get(input_name)
        shadow: Any = None
        if isinstance(old, list):
            if old[0] == 1:
                shadow = old[1]
            elif old[0] == 3 and len(old) == 3:
                shadow = old[2]
                self._drop_child(old[1])
            elif old[0] == 2 and isinstance(old[1], str):
                self._drop_child(old[1])
        if pspec is not None and pspec["inputs"].get(input_name, {}).get("boolean"):
            p.setdefault("inputs", {})[input_name] = [2, rid]
        elif shadow is not None:
            p.setdefault("inputs", {})[input_name] = [3, rid, shadow]
        else:
            ispec = (pspec or {}).get("inputs", {}).get(input_name, {}) if pspec else {}
            p.setdefault("inputs", {})[input_name] = [3, rid, self._shadow_value(parent, ispec) if ispec else [10, ""]]
        rb.update(parent=parent, topLevel=False)
        rb.pop("x", None)
        rb.pop("y", None)

    def _drop_child(self, bid: str) -> None:
        if bid in self.blocks and isinstance(self.blocks[bid], dict):
            for i in self.subtree_ids(bid, include_next=True):
                self.blocks.pop(i, None)

    # ------------------------------------------------------------ operations

    def delete(self, bid: str, *, mode: str = "stack") -> list[str]:
        """Delete a block. mode='single': just this block (what follows reconnects to what precedes);
        'stack': this block and all blocks after it. Blocks inside its inputs are always deleted."""
        b = self.get(bid)
        if b.get("shadow"):
            raise EngineError("Shadow blocks can't be deleted; replace the input instead.")
        if mode not in ("single", "stack"):
            raise EngineError("mode must be 'single' or 'stack'.")
        parent, nxt = b.get("parent"), b.get("next")
        if mode == "single" and nxt:
            # reconnect following blocks to the previous block / slot
            nb = self.get(nxt)
            if parent is not None and self.blocks[parent].get("next") == bid:
                self.blocks[parent]["next"] = nxt
                nb["parent"] = parent
            elif parent is not None:
                for name, inp in (self.blocks[parent].get("inputs") or {}).items():
                    if isinstance(inp, list) and bid in inp[1:]:
                        inp[inp.index(bid)] = nxt
                        nb["parent"] = parent
                        break
            else:
                nb.update(parent=None, topLevel=True, x=b.get("x", 0), y=b.get("y", 0))
            b["next"] = None
            doomed = self.subtree_ids(bid, include_next=False)
        else:
            self.detach_for_delete(bid)
            doomed = self.subtree_ids(bid, include_next=(mode == "stack"))
            if mode == "single":
                doomed = self.subtree_ids(bid, include_next=False)
        if mode == "single" and not nxt:
            self.detach_for_delete(bid)
        for i in doomed:
            blk = self.blocks.pop(i, None)
            if isinstance(blk, dict) and blk.get("comment"):
                self.target.get("comments", {}).pop(blk["comment"], None)
        return doomed

    def detach_for_delete(self, bid: str) -> None:
        b = self.blocks[bid]
        parent = b.get("parent")
        if parent is None or parent not in self.blocks:
            return
        p = self.blocks[parent]
        if p.get("next") == bid:
            p["next"] = None
            return
        for name, inp in list((p.get("inputs") or {}).items()):
            if isinstance(inp, list) and bid in inp[1:]:
                if len(inp) == 3 and inp[0] == 3:
                    p["inputs"][name] = [1, inp[2]]
                else:
                    del p["inputs"][name]
                return

    def move(self, bid: str, *, x: float | None = None, y: float | None = None, after: str | None = None,
             into: str | None = None, input: str | None = None, replace_input_of: str | None = None,
             single: bool = False) -> None:
        b = self.get(bid)
        if b.get("shadow"):
            raise EngineError("Shadow blocks can't be moved.")
        if sum(p is not None for p in (after, into, replace_input_of)) > 1:
            raise EngineError("Use only one of after / into / replace_input_of.")
        if all(p is None for p in (after, into, replace_input_of)) and (x is None or y is None):
            raise EngineError("Give a destination: x and y, or after, or into+input, or replace_input_of+input.")
        snapshot = copy.deepcopy(self.blocks)
        try:
            tail = None
            slot = self._slot_of(bid)
            if single and b.get("next"):
                tail = b["next"]
                b["next"] = None
                self.blocks[tail]["parent"] = None
            self.detach(bid, x, y)
            if tail:  # reconnect the rest where this block was
                self._reattach_tail(bid, slot, tail)
            if after is not None:
                self.insert_after(bid, after)
            elif into is not None:
                self.insert_into(bid, into, input or "SUBSTACK")
            elif replace_input_of is not None:
                self.set_reporter(bid, replace_input_of, input or "")
        except EngineError:
            self.blocks.clear()
            self.blocks.update(snapshot)
            raise

    def _slot_of(self, bid: str) -> tuple[str, str | None, str | None]:
        """How a block is attached: ('next', parent, None) | ('input', parent, input name) | ('top', None, None)."""
        parent = self.blocks[bid].get("parent")
        if parent is None or parent not in self.blocks:
            return ("top", None, None)
        p = self.blocks[parent]
        if p.get("next") == bid:
            return ("next", parent, None)
        for name, inp in (p.get("inputs") or {}).items():
            if isinstance(inp, list) and bid in inp[1:]:
                return ("input", parent, name)
        return ("top", None, None)

    def _reattach_tail(self, moved: str, slot: tuple[str, str | None, str | None], tail: str) -> None:
        kind, parent, name = slot
        tb = self.blocks[tail]
        if kind == "next":
            self.blocks[parent]["next"] = tail
            tb["parent"] = parent
        elif kind == "input":
            self.blocks[parent]["inputs"][name] = [2, tail]
            tb["parent"] = parent
        else:
            b = self.blocks[moved]
            tb.update(topLevel=True, parent=None, x=b.get("x", 0), y=(b.get("y", 0) or 0) + 60)

    def duplicate(self, bid: str, *, include_next: bool = True, x: float | None = None, y: float | None = None,
                  into_graph: "Graph | None" = None) -> str:
        """Deep copy of a block (and what's inside it, and optionally what follows) with fresh ids."""
        self.get(bid)
        dest = into_graph or self
        ids = self.subtree_ids(bid, include_next=include_next)
        mapping: dict[str, str] = {}
        for i in ids:
            mapping[i] = dest.new_id()
        for i in ids:
            src = copy.deepcopy(self.blocks[i])
            src["parent"] = mapping.get(src.get("parent")) if i != bid else None
            nxt = src.get("next")
            src["next"] = mapping.get(nxt) if nxt in mapping else None
            if i == bid and not include_next:
                src["next"] = None
            for inp in (src.get("inputs") or {}).values():
                for k in range(1, len(inp)):
                    if isinstance(inp[k], str) and inp[k] in mapping:
                        inp[k] = mapping[inp[k]]
                    elif _is_primitive(inp[k]) and into_graph is not None and inp[k][0] in (VARIABLE_CODE, LIST_CODE, BROADCAST_CODE):
                        inp[k] = self._remap_ref(inp[k], dest)
            for fname, fv in (src.get("fields") or {}).items():
                if into_graph is not None and isinstance(fv, list) and len(fv) > 1 and fv[1]:
                    src["fields"][fname] = self._remap_field(fname, fv, dest)
            src.pop("comment", None)
            dest.blocks[mapping[i]] = src
            dest.created.append(mapping[i])
        if x is None or y is None:
            x, y = dest.free_position()
        dest._make_top(mapping[bid], x, y)
        if into_graph is not None:
            self._copy_procedures(ids, dest)
        return mapping[bid]

    def _remap_ref(self, prim: list[Any], dest: "Graph") -> list[Any]:
        code, name = prim[0], prim[1]
        if code == VARIABLE_CODE:
            n, i = dest.variable(name)
        elif code == LIST_CODE:
            n, i = dest.list_(name)
        else:
            n, i = dest.broadcast(name)
        return [code, n, i]

    def _remap_field(self, fname: str, fv: list[Any], dest: "Graph") -> list[Any]:
        if fname in ("VARIABLE",):
            n, i = dest.variable(fv[0])
            return [n, i]
        if fname == "LIST":
            n, i = dest.list_(fv[0])
            return [n, i]
        if fname == "BROADCAST_OPTION":
            n, i = dest.broadcast(fv[0])
            return [n, i]
        return fv

    def _copy_procedures(self, ids: list[str], dest: "Graph") -> None:
        # a copied custom-block call needs its definition in the destination sprite
        wanted = {self.blocks[i]["mutation"]["proccode"] for i in ids
                  if self.blocks[i].get("opcode") == "procedures_call" and self.blocks[i].get("mutation")}
        have = dest.procedures()
        mine = self.procedures()
        for code in wanted - set(have):
            if code in mine:
                d = mine[code]["definition"]
                if d:
                    self.duplicate(d, include_next=True, into_graph=dest)
                    dest.notes.append(f"copied custom block '{code}'")

    # ---------------------------------------------------------- editing in place

    def set_input(self, bid: str, name: str, value: Any) -> None:
        b = self.get(bid)
        if b["opcode"] == "procedures_call":
            m = b.get("mutation") or {}
            ids = json.loads(m.get("argumentids") or "[]")
            if name not in ids:
                raise EngineError(f"'{name}' isn't an argument id of this call. Argument ids: {ids}")
            slots = re.findall(r"%[sb]", m.get("proccode", ""))
            slot = slots[ids.index(name)]
            ispec = {"type": "value", "boolean": slot == "%b", "shadow": None if slot == "%b" else "text"}
        else:
            spec = self.spec_of(b["opcode"])
            ispec = spec["inputs"].get(name)
            if ispec is None:
                raise EngineError(f"'{b['opcode']}' has no input '{name}'. Inputs: {sorted(spec['inputs']) or 'none'}")
        self.created = []
        old = (b.get("inputs") or {}).get(name)
        if ispec["type"] == "statement":
            if old and isinstance(old, list) and len(old) > 1 and isinstance(old[1], str):
                self._drop_child(old[1])
                del b["inputs"][name]
            if value:
                stack = value if isinstance(value, list) else [value]
                b.setdefault("inputs", {})[name] = [2, self._build_chain(stack, bid)]
            return
        if isinstance(old, list):
            for v in old[1:]:
                if isinstance(v, str) and v in self.blocks and not self.blocks[v].get("shadow"):
                    self._drop_child(v)
                elif isinstance(v, str) and v in self.blocks and self.blocks[v].get("shadow") and (
                        ispec.get("shadow") != self.blocks[v]["opcode"]):
                    self.blocks.pop(v, None)
        if value is None:
            inp = self._default_input(bid, ispec)
        else:
            inp = self._make_input(bid, b["opcode"], name, ispec, value)
        if inp is None:
            b.get("inputs", {}).pop(name, None)
        else:
            # keep an existing menu shadow block if the user just changed its value
            b.setdefault("inputs", {})[name] = inp

    def set_field(self, bid: str, name: str, value: Any) -> None:
        b = self.get(bid)
        spec = self.spec_of(b["opcode"])
        fspec = spec["fields"].get(name)
        if fspec is None:
            raise EngineError(f"'{b['opcode']}' has no field '{name}'. Fields: {sorted(spec['fields']) or 'none'}")
        b.setdefault("fields", {})[name] = self._field_value(b["opcode"], name, fspec, value)
        if b["opcode"] == "control_stop":
            b["mutation"] = {"tagName": "mutation", "children": [],
                             "hasnext": "true" if b["fields"][name][0] == "other scripts in sprite" else "false"}

    # ---------------------------------------------------------------- inspect

    def to_tree(self, bid: str, *, include_next: bool = True, ids: bool = False) -> dict[str, Any]:
        """Block as a tree in the same notation ``add`` accepts (round-trippable)."""
        b = self.get(bid)
        tree: dict[str, Any] = {}
        if ids:
            tree["id"] = bid
        if b["opcode"] == "procedures_call":
            m = b.get("mutation") or {}
            arg_ids = json.loads(m.get("argumentids") or "[]")
            tree["call"] = m.get("proccode")
            tree["args"] = [self._input_value(b, a) for a in arg_ids]
        elif b["opcode"] == "procedures_definition":
            proto = self.blocks.get(self.child_of(b, "custom_block") or "", {})
            m = proto.get("mutation") or {}
            tree["opcode"] = "procedures_definition"
            tree["procedure"] = {"proccode": m.get("proccode"), "argument_names": json.loads(m.get("argumentnames") or "[]"),
                                 "warp": str(m.get("warp")).lower() == "true"}
        else:
            tree["opcode"] = b["opcode"]
            inputs = {}
            for name in (b.get("inputs") or {}):
                v = self._input_value(b, name)
                inputs[name] = v
            if inputs:
                tree["inputs"] = inputs
            fields = {n: f[0] for n, f in (b.get("fields") or {}).items()}
            if fields:
                tree["fields"] = fields
        if include_next and b.get("next"):
            tree["next"] = [self.to_tree(i, include_next=False, ids=ids) for i in self.stack_ids(b["next"])]
        return tree

    def child_of(self, block: dict[str, Any], name: str) -> str | None:
        inp = (block.get("inputs") or {}).get(name)
        if isinstance(inp, list):
            for v in inp[1:]:
                if isinstance(v, str):
                    return v
        return None

    def _input_value(self, block: dict[str, Any], name: str) -> Any:
        inp = (block.get("inputs") or {}).get(name)
        if not isinstance(inp, list) or len(inp) < 2:
            return None
        kind, first = inp[0], inp[1]
        spec = schema.spec(block["opcode"]) or {}
        ispec = (spec.get("inputs") or {}).get(name, {})
        if ispec.get("type") == "statement" or name.startswith("SUBSTACK"):
            return [self.to_tree(i, include_next=False) for i in self.stack_ids(first)] if isinstance(first, str) else []
        if kind == 3 and isinstance(first, str):
            return self.to_tree(first, include_next=False)
        if kind == 3 and _is_primitive(first):
            return self._prim_value(first)
        if kind == 2 and isinstance(first, str):
            return self.to_tree(first, include_next=False)
        if isinstance(first, str):  # shadow block (menu etc.)
            sb = self.blocks.get(first)
            if sb:
                fvals = [f[0] for f in (sb.get("fields") or {}).values()]
                return {"menu": fvals[0]} if sb["opcode"] not in PRIMITIVE_CODE and fvals else (fvals[0] if fvals else None)
            return None
        return self._prim_value(first)

    @staticmethod
    def _prim_value(p: list[Any]) -> Any:
        code = p[0]
        if code == VARIABLE_CODE:
            return {"variable": p[1]}
        if code == LIST_CODE:
            return {"list": p[1]}
        if code == BROADCAST_CODE:
            return p[1]
        v = p[1]
        if code in (4, 5, 6, 7, 8) and isinstance(v, str) and _NUM_RE.match(v):
            f = float(v)
            return int(f) if f.is_integer() else f
        return v

    # ---------------------------------------------------------------- validate

    def validate(self) -> list[str]:
        """Schema-level checks beyond structural validation: shapes, inputs, fields, stack rules."""
        problems: list[str] = []
        blocks = self.blocks
        for bid, b in blocks.items():
            if not isinstance(b, dict):
                continue
            op = b.get("opcode", "")
            spec = schema.spec(op)
            if spec is None:
                continue  # unknown opcode is reported by the structural validator
            shape = spec["shape"]
            where = f"block '{bid}' ({op})"
            if shape == "hat" and b.get("parent") is not None:
                problems.append(f"{where}: hat block is not at the start of a script")
            if shape in schema.REPORTER_SHAPES and b.get("next"):
                problems.append(f"{where}: reporter has a 'next' block")
            if self._is_cap(b, spec) and b.get("next") and op != "control_forever":
                problems.append(f"{where}: cap block has blocks after it")
            if op == "control_forever" and b.get("next"):
                problems.append(f"{where}: blocks after 'forever' can never run")
            if shape in schema.STATEMENT_SHAPES | schema.CAP_SHAPES and b.get("topLevel") and not b.get("shadow"):
                problems.append(f"{where}: stack doesn't start with a hat block, so it never runs on its own (fine if it is a helper)")
            for name, inp in (b.get("inputs") or {}).items():
                ispec = spec["inputs"].get(name)
                if ispec is None and op != "procedures_call" and op != "procedures_prototype" and op != "procedures_definition":
                    problems.append(f"{where}: unknown input '{name}'")
                    continue
                if ispec is None or not isinstance(inp, list):
                    continue
                child = next((v for v in inp[1:] if isinstance(v, str) and v in blocks and not blocks[v].get("shadow")), None)
                if child is not None and ispec["type"] == "value":
                    cshape = (schema.spec(blocks[child]["opcode"]) or {}).get("shape")
                    if blocks[child]["opcode"] in ("argument_reporter_boolean",):
                        cshape = "boolean"
                    if blocks[child]["opcode"] in ("argument_reporter_string_number", "procedures_call"):
                        cshape = "reporter"
                    if cshape not in schema.REPORTER_SHAPES:
                        problems.append(f"{where}: input '{name}' holds a {cshape} block, expected a reporter")
                    elif ispec.get("boolean") and cshape != "boolean":
                        problems.append(f"{where}: input '{name}' needs a boolean block but holds a round reporter")
            for name, fspec in spec["fields"].items():
                if fspec["type"] in ("variable", "list", "broadcast") or (fspec["type"] == "dropdown" and not fspec.get("dynamic")):
                    if name not in (b.get("fields") or {}) and not fspec.get("default") and fspec.get("options") is not None:
                        problems.append(f"{where}: missing field '{name}'")
                value = (b.get("fields") or {}).get(name)
                opts = fspec.get("options")
                if opts and isinstance(value, list) and value and value[0] not in opts and not b.get("shadow"):
                    problems.append(f"{where}: field {name}='{value[0]}' is not one of {opts}")
            for name, fv in (b.get("fields") or {}).items():
                if name not in spec["fields"] and op not in ("procedures_prototype", "procedures_call",
                                                              "argument_reporter_boolean", "argument_reporter_string_number"):
                    problems.append(f"{where}: unknown field '{name}'")
        return problems

    # ---------------------------------------------------------------- comments

    def add_comment(self, text: str, *, block: str | None = None, x: float = 0, y: float = 0,
                    width: int = 200, height: int = 200, minimized: bool = False) -> str:
        comments = self.target.setdefault("comments", {})
        cid = self.new_id()
        entry = {"blockId": None, "x": x, "y": y, "width": width, "height": height, "minimized": minimized, "text": text}
        if block:
            b = self.get(block)
            if b.get("comment"):
                raise EngineError(f"Block '{block}' already has a comment; edit it instead.")
            entry["blockId"] = block
            b["comment"] = cid
            if b.get("topLevel"):
                entry["x"], entry["y"] = b.get("x", 0) + 330, b.get("y", 0)
        comments[cid] = entry
        return cid

    def edit_comment(self, cid: str, *, text: str | None = None, minimized: bool | None = None,
                     x: float | None = None, y: float | None = None, width: int | None = None, height: int | None = None) -> None:
        c = (self.target.get("comments") or {}).get(cid)
        if c is None:
            raise EngineError(f"No comment '{cid}'.")
        for k, v in (("text", text), ("minimized", minimized), ("x", x), ("y", y), ("width", width), ("height", height)):
            if v is not None:
                c[k] = v

    def delete_comment(self, cid: str) -> None:
        c = (self.target.get("comments") or {}).pop(cid, None)
        if c is None:
            raise EngineError(f"No comment '{cid}'.")
        if c.get("blockId") and c["blockId"] in self.blocks:
            self.blocks[c["blockId"]].pop("comment", None)

    # ---------------------------------------------------------------- layout

    def arrange(self, columns: int = 1, gap: int = 40) -> int:
        """Tidy top-level scripts into a grid (like Scratch's 'Clean up Blocks')."""
        tops = sorted(self.top_levels(), key=lambda i: (self.blocks[i].get("y", 0), self.blocks[i].get("x", 0)))
        col_y = [48.0] * max(1, columns)
        for n, bid in enumerate(tops):
            col = n % max(1, columns) if columns > 1 else 0
            self.blocks[bid]["x"] = 48 + col * 420
            self.blocks[bid]["y"] = round(col_y[col])
            col_y[col] += self.stack_height(bid) + gap
        return len(tops)


def _fmt_number(v: int | float) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return repr(v) if isinstance(v, float) else str(v)
