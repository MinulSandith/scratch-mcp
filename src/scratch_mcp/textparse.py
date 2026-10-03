"""Parse scratchblocks-style text into Scratch 3 blocks.

One block per line. Arguments use the usual scratchblocks brackets:

    (10)            number                [hello]       text
    (x position)    reporter block        <mouse down?> boolean block
    (score)         variable              [edge v]      dropdown (also (edge v))
    [#ff0000]       colour

C blocks (repeat, forever, if, ...) are closed with ``end``; ``else`` splits an
if/else. If no ``end`` lines are used at all, indentation decides nesting
instead. A blank line starts a new script. Custom blocks: ``define jump (height)``.
"""

from __future__ import annotations

import difflib
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

from .workspace import WorkspaceError
from .blocks import (
    BOOLEAN, BROADCAST, C, C_CAP, CAP, COLOR_PICKER, HAT, KIND_TO_PRIMITIVE,
    LIST, MENUS, PARSE_SPECS, REPORTER, SPECS, SPRITE_ONLY_OPCODES, STAGE_ONLY_OPCODES,
    TEXT, VAR, BlockSpec, Slot, extension_of, menu_value, normalize_word, option_value,
)

_NUMBER_RE = re.compile(r"^-?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$", re.IGNORECASE)
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_STOP_CHARS = set("()[]<>?")
_NUMBER_KINDS = {"num", "pos", "whole", "int", "angle", "note"}

# Same alphabet and length scratch-vm uses for block / variable ids.
_ID_SOUP = "!#%()*+,-./:;=?@[]^_`{|}~ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


class ParseError(WorkspaceError):
    def __init__(self, message: str, line: int | None = None):
        self.line = line
        super().__init__(f"Line {line}: {message}" if line else message)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


@dataclass
class Word:
    text: str


@dataclass
class Arg:
    bracket: str  # "(", "[" or "<"
    raw: str  # unescaped inner text
    children: list[Word | Arg] = field(default_factory=list)

    @property
    def is_dropdown(self) -> bool:
        if self.bracket == "<" or not self.raw.endswith(" v"):
            return False
        return self.bracket == "[" or all(isinstance(c, Word) for c in self.children)

    @property
    def dropdown_value(self) -> str:
        return self.raw[:-2].strip()

    @property
    def is_number(self) -> bool:
        return self.bracket == "(" and bool(_NUMBER_RE.match(self.raw.strip()))

    @property
    def is_empty(self) -> bool:
        return self.raw.strip() == ""

    @property
    def is_hex(self) -> bool:
        return bool(_HEX_RE.match(self.raw.strip()))

    def __str__(self) -> str:
        closer = {"(": ")", "[": "]", "<": ">"}[self.bracket]
        return f"{self.bracket}{self.raw}{closer}"


def _is_literal_op(s: str, i: int) -> bool:
    """'<' / '>' surrounded by spaces is a comparison operator, not a bracket."""
    return 0 < i < len(s) - 1 and s[i - 1].isspace() and s[i + 1].isspace()


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def tokenize(line: str) -> tuple[list[Word | Arg], str]:
    """Split a line into words and bracketed args. Returns (tokens, // comment)."""
    tokens, i, comment = _parse_seq(line, 0, None)
    return tokens, comment


def _parse_seq(s: str, i: int, closer: str | None) -> tuple[list[Word | Arg], int, str]:
    tokens: list[Word | Arg] = []
    while i < len(s):
        c = s[i]
        if closer and c == closer and not (closer == ">" and _is_literal_op(s, i)):
            return tokens, i + 1, ""
        if c.isspace():
            i += 1
        elif closer is None and s.startswith("//", i) and (i == 0 or s[i - 1].isspace()):
            return tokens, len(s), s[i + 2:].strip()
        elif c == "(" or (c == "<" and not _is_literal_op(s, i)):
            close = ")" if c == "(" else ">"
            children, j, _ = _parse_seq(s, i + 1, close)
            tokens.append(Arg(c, _unescape(s[i + 1:j - 1]).strip(), children))
            i = j
        elif c == "[":
            j = i + 1
            while j < len(s) and s[j] != "]":
                j += 2 if s[j] == "\\" else 1
            if j >= len(s):
                raise ParseError("missing ']'")
            tokens.append(Arg("[", _unescape(s[i + 1:j])))
            i = j + 1
        elif c in ")]" or (c == ">" and not _is_literal_op(s, i)):
            raise ParseError(f"unexpected '{c}'")
        elif c in "?<>":
            tokens.append(Word(c))
            i += 1
        else:
            j = i
            while j < len(s) and not s[j].isspace() and s[j] not in _STOP_CHARS:
                j += 2 if s[j] == "\\" else 1
            tokens.append(Word(_unescape(s[i:j])))
            i = j
    if closer:
        raise ParseError(f"missing '{closer}'")
    return tokens, i, ""


def _words_only(tokens: list[Word | Arg]) -> list[Word | Arg]:
    return [t for t in tokens if not isinstance(t, Word) or normalize_word(t.text)]


# ---------------------------------------------------------------------------
# Matching tokens against templates (pure: no side effects)
# ---------------------------------------------------------------------------


def _accepts(slot: Slot, arg: Arg) -> bool:
    kind = slot.kind
    if kind in _NUMBER_KINDS or kind == "text":
        return not arg.is_dropdown
    if kind == "color":
        if arg.is_hex:
            return True
        return arg.bracket == "(" and not arg.is_dropdown and not arg.is_number and not arg.is_empty
    if kind == "bool":
        return arg.bracket == "<"
    if kind == "menu":
        menu = MENUS[slot.arg]
        if arg.is_dropdown:
            return menu_value(menu, arg.dropdown_value) is not None
        if arg.bracket == "<":
            return True
        if arg.bracket == "(" and not arg.is_empty:
            return not arg.is_number or menu.optset is None
        return False
    if kind == "field":
        if not arg.is_dropdown:
            return False
        return slot.arg == "free" or option_value(slot.arg, arg.dropdown_value) is not None
    if kind in ("var", "list", "bcast_field"):
        return arg.is_dropdown
    if kind == "bcast_input":
        return arg.bracket in "([" and not arg.is_empty
    raise AssertionError(kind)


def match_template(tokens: list[Word | Arg], template: list[str | Slot]) -> list[tuple[Slot, Arg]] | None:
    tokens = _words_only(tokens)
    if len(tokens) != len(template):
        return None
    pairs = []
    for tok, tt in zip(tokens, template):
        if isinstance(tt, Slot):
            if not isinstance(tok, Arg) or not _accepts(tt, tok):
                return None
            pairs.append((tt, tok))
        elif not isinstance(tok, Word) or normalize_word(tok.text) != tt:
            return None
    return pairs


def match_spec(tokens: list[Word | Arg], shapes: set[str]) -> tuple[BlockSpec, list[tuple[Slot, Arg]]] | None:
    for spec in PARSE_SPECS:
        if spec.shape not in shapes:
            continue
        for template in spec.tokens:
            pairs = match_template(tokens, template)
            if pairs is not None:
                return spec, pairs
    return None


STATEMENT_SHAPES = {HAT, "stack", CAP, C, C_CAP}
REPORTER_SHAPES = {REPORTER, BOOLEAN}


# ---------------------------------------------------------------------------
# Custom blocks (procedures)
# ---------------------------------------------------------------------------


@dataclass
class Procedure:
    proccode: str
    argument_ids: list[str]
    argument_names: list[str]
    warp: bool = False

    @property
    def template(self) -> list[str | Slot]:
        out: list[str | Slot] = []
        i = 0
        for part in self.proccode.split(" "):
            if part in ("%s", "%n", "%b"):
                out.append(Slot(self.argument_ids[i], "bool" if part == "%b" else "text"))
                i += 1
            elif normalize_word(part):
                out.append(normalize_word(part))
        return out


def parse_define(tokens: list[Word | Arg], comment: str, line: int) -> tuple[str, list[tuple[str, str]], bool]:
    """'define jump (height) <fast>' -> ("jump %s %b", [("height", "%s"), ("fast", "%b")], warp)."""
    parts, args = [], []
    for tok in tokens[1:]:
        if isinstance(tok, Word):
            parts.append(tok.text)
        else:
            name = tok.raw.strip()
            if not name:
                raise ParseError("custom block inputs need a name, e.g. define jump (height)", line)
            kind = "%b" if tok.bracket == "<" else "%s"
            parts.append(kind)
            args.append((name, kind))
    if all(p in ("%s", "%b") for p in parts):
        raise ParseError("'define' needs a block name, e.g. define jump (height)", line)
    if len({a[0] for a in args}) != len(args):
        raise ParseError("custom block input names must be different from each other", line)
    warp = "without screen refresh" in comment.lower()
    return " ".join(parts), args, warp


def existing_procedures(blocks: dict[str, Any]) -> dict[str, Procedure]:
    procs = {}
    for block in blocks.values():
        if isinstance(block, dict) and block.get("opcode") == "procedures_prototype":
            m = block.get("mutation") or {}
            try:
                ids = json.loads(m.get("argumentids") or "[]")
                names = json.loads(m.get("argumentnames") or "[]")
            except (TypeError, json.JSONDecodeError):
                continue
            procs[m.get("proccode", "")] = Procedure(
                m.get("proccode", ""), ids, names, str(m.get("warp")).lower() == "true"
            )
    return procs


# ---------------------------------------------------------------------------
# Statement tree
# ---------------------------------------------------------------------------


@dataclass
class Stmt:
    line: int
    spec: BlockSpec | None = None
    pairs: list[tuple[Slot, Arg]] = field(default_factory=list)
    proc: Procedure | None = None  # procedures_call
    define: Procedure | None = None  # procedures_definition
    define_args: list[tuple[str, str]] = field(default_factory=list)
    substacks: list[list["Stmt"]] = field(default_factory=list)
    in_else: bool = False

    @property
    def opcode(self) -> str:
        if self.define:
            return "procedures_definition"
        if self.proc:
            return "procedures_call"
        assert self.spec
        return self.spec.opcode

    @property
    def shape(self) -> str:
        if self.define:
            return HAT
        if self.proc:
            return "stack"
        assert self.spec
        if self.spec.opcode == "control_stop":
            value = next((a.dropdown_value for s, a in self.pairs if s.name == "STOP_OPTION"), "")
            return "stack" if value.lower().startswith("other scripts") else CAP
        return self.spec.shape


@dataclass
class _Frame:
    stmt: Stmt
    indent: int


class ScriptParser:
    def __init__(self, procedures: dict[str, Procedure], new_id):
        self.procedures = dict(procedures)
        self.new_id = new_id

    def parse(self, text: str) -> list[list[Stmt]]:
        lines = text.replace("\t", "    ").splitlines()
        self._collect_defines(lines)
        use_end = any(l.strip().lower() in ("end", "else") for l in lines)
        scripts: list[list[Stmt]] = []
        current: list[Stmt] = []
        frames: list[_Frame] = []

        def finish():
            nonlocal current
            if current:
                scripts.append(current)
            current = []
            frames.clear()

        for lineno, raw in enumerate(lines, 1):
            stripped = raw.strip()
            if not stripped:
                if not use_end or not frames:
                    finish()
                continue
            if stripped.startswith("//"):
                continue
            indent = len(raw) - len(raw.lstrip())
            low = stripped.lower()
            if not use_end:
                while frames and indent <= frames[-1].indent:
                    frames.pop()
            if low == "end":
                if not frames:
                    raise ParseError("'end' without a matching C block (repeat, forever, if...)", lineno)
                frames.pop()
                continue
            if low == "else":
                top = frames[-1].stmt if frames else None
                if not top or top.opcode != "control_if" or top.in_else:
                    raise ParseError("'else' must follow an 'if <...> then' block", lineno)
                top.spec = SPECS["control_if_else"]
                top.substacks.append([])
                top.in_else = True
                continue
            stmt = self.parse_line(stripped, lineno)
            container = frames[-1].stmt.substacks[-1] if frames else current
            if stmt.shape == HAT and (frames or current):
                raise ParseError(
                    f"'{stripped}' is a hat block and must start a script (leave a blank line before it)",
                    lineno,
                )
            if container and container[-1].shape in (CAP, C_CAP):
                raise ParseError(
                    f"nothing can come after '{container[-1].opcode}' (it is a cap block); "
                    "close the C block with 'end' or start a new script",
                    lineno,
                )
            container.append(stmt)
            if stmt.substacks:
                frames.append(_Frame(stmt, indent))
        finish()
        if not scripts:
            raise ParseError("No blocks found in the script text.")
        return scripts

    def _collect_defines(self, lines: list[str]) -> None:
        for lineno, raw in enumerate(lines, 1):
            stripped = raw.strip()
            if not stripped.lower().startswith("define "):
                continue
            tokens, comment = self._tokenize(stripped, lineno)
            proccode, args, warp = parse_define(tokens, comment, lineno)
            if proccode in self.procedures:
                raise ParseError(f"custom block '{proccode}' is already defined in this sprite", lineno)
            self.procedures[proccode] = Procedure(
                proccode, [self.new_id() for _ in args], [a[0] for a in args], warp
            )

    @staticmethod
    def _tokenize(text: str, lineno: int) -> tuple[list[Word | Arg], str]:
        try:
            tokens, comment = tokenize(text)
        except ParseError as exc:
            raise ParseError(str(exc), lineno) from None
        return _words_only(tokens), comment

    def parse_line(self, text: str, lineno: int) -> Stmt:
        tokens, comment = self._tokenize(text, lineno)
        if not tokens:
            raise ParseError("empty line", lineno)
        first = tokens[0]
        if isinstance(first, Word) and first.text.lower() == "define":
            proccode, args, _ = parse_define(tokens, comment, lineno)
            return Stmt(lineno, define=self.procedures[proccode], define_args=args)
        for proc in self.procedures.values():
            pairs = match_template(tokens, proc.template)
            if pairs is not None:
                return Stmt(lineno, proc=proc, pairs=pairs)
        found = match_spec(tokens, STATEMENT_SHAPES)
        if found:
            spec, pairs = found
            substacks = [[]] if spec.shape in (C, C_CAP) else []
            return Stmt(lineno, spec=spec, pairs=pairs, substacks=substacks)
        if match_spec(tokens, REPORTER_SHAPES):
            raise ParseError(
                f"'{text}' is a reporter block; it must go inside another block's input", lineno
            )
        raise ParseError(f"Unknown block: '{text}'.{_suggest(text)}", lineno)


def _plain_template(template: str) -> str:
    return re.sub(r"\{[^}]*\}", "()", template)


_ALL_TEMPLATES = [
    (_plain_template(t), t) for s in PARSE_SPECS for t in s.templates
]


def _suggest(text: str) -> str:
    plain = re.sub(r"\([^()]*\)|\[[^\]]*\]|<[^<>]*>", "()", text)
    names = difflib.get_close_matches(plain, [p for p, _ in _ALL_TEMPLATES], n=3, cutoff=0.5)
    if not names:
        return " Check the spelling and brackets: (number/reporter), [text], [option v], <boolean>."
    examples = []
    for p, t in _ALL_TEMPLATES:
        if p in names and p not in [e[0] for e in examples]:
            examples.append((p, _example(t)))
    return " Did you mean: " + "; ".join(e for _, e in examples)


def _example(template: str) -> str:
    def repl(m: re.Match) -> str:
        kind = m.group(2)
        if kind == "bool":
            return "<>"
        if kind in ("text", "color"):
            return "[]"
        if kind in ("field", "var", "list", "bcast_field"):
            return "[ v]"
        if kind in ("menu", "bcast_input"):
            return "( v)"
        return "()"

    return re.sub(r"\{([A-Za-z0-9_]+):([a-z_]+)(?::[A-Za-z0-9_]+)?\}", repl, template)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


def make_id_factory(project: dict[str, Any]):
    used: set[str] = set()
    for target in project.get("targets") or []:
        used.update((target.get("blocks") or {}).keys())
        for key in ("variables", "lists", "broadcasts", "comments"):
            used.update((target.get(key) or {}).keys())

    def new_id() -> str:
        while True:
            candidate = "".join(secrets.choice(_ID_SOUP) for _ in range(20))
            if candidate not in used:
                used.add(candidate)
                return candidate

    return new_id


@dataclass
class BuildReport:
    top_ids: list[str] = field(default_factory=list)
    created_variables: list[str] = field(default_factory=list)
    created_lists: list[str] = field(default_factory=list)
    created_broadcasts: list[str] = field(default_factory=list)
    extensions_added: list[str] = field(default_factory=list)


class ScriptBuilder:
    def __init__(self, project: dict[str, Any], target: dict[str, Any]):
        self.project = project
        self.target = target
        self.stage = next(t for t in project["targets"] if t.get("isStage"))
        self.blocks: dict[str, Any] = target.setdefault("blocks", {})
        self.new_id = make_id_factory(project)
        self.report = BuildReport()
        self.proc_args: dict[str, str] = {}  # name -> "%s" / "%b" while building a define
        self.line = 0

    # -- entry point -----------------------------------------------------

    def add_scripts(self, text: str, x: float | None = None, y: float | None = None) -> BuildReport:
        parser = ScriptParser(existing_procedures(self.blocks), self.new_id)
        scripts = parser.parse(text)
        if x is None or y is None:
            x0, y0 = self._free_position()
            x = x0 if x is None else x
            y = y0 if y is None else y
        for stmts in scripts:
            self.proc_args = {}
            if stmts[0].define:
                self.proc_args = {name: kind for name, kind in stmts[0].define_args}
            top = self.build_stack(stmts, parent=None)
            assert top
            self.blocks[top].update({"topLevel": True, "x": round(x), "y": round(y)})
            self.report.top_ids.append(top)
            y += self._stack_height(top) + 40
        return self.report

    def _free_position(self) -> tuple[float, float]:
        tops = [b for b in self.blocks.values() if isinstance(b, dict) and b.get("topLevel")]
        if not tops:
            return 48, 48
        bottom = max((b.get("y") or 0) + self._stack_height_of(b) for b in tops)
        left = min(b.get("x") or 0 for b in tops)
        return left, bottom + 48

    def _stack_height_of(self, block: dict[str, Any]) -> float:
        bid = next((k for k, v in self.blocks.items() if v is block), None)
        return self._stack_height(bid) if bid else 48

    def _stack_height(self, block_id: str | None) -> float:
        height = 0.0
        seen = set()
        while block_id and block_id not in seen and isinstance(self.blocks.get(block_id), dict):
            seen.add(block_id)
            block = self.blocks[block_id]
            height += 48
            for name in ("SUBSTACK", "SUBSTACK2"):
                inp = (block.get("inputs") or {}).get(name)
                if isinstance(inp, list) and len(inp) > 1 and isinstance(inp[1], str):
                    height += self._stack_height(inp[1]) + 24
            block_id = block.get("next")
        return height

    # -- statements --------------------------------------------------------

    def build_stack(self, stmts: list[Stmt], parent: str | None) -> str | None:
        first = prev = None
        for stmt in stmts:
            self.line = stmt.line
            bid = self.build_statement(stmt, parent=prev or parent)
            if prev:
                self.blocks[prev]["next"] = bid
            else:
                first = bid
            prev = bid
        return first

    def build_statement(self, stmt: Stmt, parent: str | None) -> str:
        if stmt.define:
            return self.build_define(stmt, parent)
        if stmt.proc:
            return self.build_call(stmt, parent)
        assert stmt.spec
        bid = self.new_block(stmt.spec.opcode, parent)
        self.fill_slots(bid, stmt.pairs)
        if stmt.spec.opcode == "control_stop":
            self.blocks[bid]["mutation"] = {
                "tagName": "mutation", "children": [],
                "hasnext": "true" if stmt.shape == "stack" else "false",
            }
        for name, body in zip(("SUBSTACK", "SUBSTACK2"), stmt.substacks):
            child = self.build_stack(body, parent=bid)
            if child:
                self.blocks[bid]["inputs"][name] = [2, child]
            self.line = stmt.line
        return bid

    def build_define(self, stmt: Stmt, parent: str | None) -> str:
        proc = stmt.define
        assert proc
        def_id = self.new_block("procedures_definition", parent)
        proto_id = self.new_block("procedures_prototype", def_id, shadow=True)
        self.blocks[def_id]["inputs"]["custom_block"] = [1, proto_id]
        defaults = []
        for arg_id, (name, kind) in zip(proc.argument_ids, stmt.define_args):
            opcode = "argument_reporter_boolean" if kind == "%b" else "argument_reporter_string_number"
            shadow = self.new_block(opcode, proto_id, shadow=True)
            self.blocks[shadow]["fields"]["VALUE"] = [name, None]
            self.blocks[proto_id]["inputs"][arg_id] = [1, shadow]
            defaults.append("false" if kind == "%b" else "")
        self.blocks[proto_id]["mutation"] = {
            "tagName": "mutation", "children": [],
            "proccode": proc.proccode,
            "argumentids": json.dumps(proc.argument_ids),
            "argumentnames": json.dumps(proc.argument_names),
            "argumentdefaults": json.dumps(defaults),
            "warp": "true" if proc.warp else "false",
        }
        return def_id

    def build_call(self, stmt: Stmt, parent: str | None) -> str:
        proc = stmt.proc
        assert proc
        bid = self.new_block("procedures_call", parent)
        for slot, arg in stmt.pairs:
            if slot.kind == "bool":
                if not arg.is_empty:
                    self.blocks[bid]["inputs"][slot.name] = [2, self.build_reporter(arg, bid)]
            else:
                self.blocks[bid]["inputs"][slot.name] = self.value_input(arg, "text", bid)
        self.blocks[bid]["mutation"] = {
            "tagName": "mutation", "children": [],
            "proccode": proc.proccode,
            "argumentids": json.dumps(proc.argument_ids),
            "warp": "true" if proc.warp else "false",
        }
        return bid

    # -- block helpers -------------------------------------------------------

    def new_block(self, opcode: str, parent: str | None, *, shadow: bool = False) -> str:
        self._check_target(opcode)
        bid = self.new_id()
        self.blocks[bid] = {
            "opcode": opcode, "next": None, "parent": parent,
            "inputs": {}, "fields": {}, "shadow": shadow, "topLevel": False,
        }
        ext = extension_of(opcode)
        if ext:
            exts = self.project.setdefault("extensions", [])
            if ext not in exts:
                exts.append(ext)
                self.report.extensions_added.append(ext)
        return bid

    def _check_target(self, opcode: str) -> None:
        if self.target.get("isStage") and opcode in SPRITE_ONLY_OPCODES:
            raise ParseError(f"'{opcode}' only works on sprites, not on the Stage", self.line)
        if not self.target.get("isStage") and opcode in STAGE_ONLY_OPCODES:
            raise ParseError(f"'{opcode}' only works on the Stage, not on sprites", self.line)

    def fill_slots(self, bid: str, pairs: list[tuple[Slot, Arg]]) -> None:
        block = self.blocks[bid]
        for slot, arg in pairs:
            kind = slot.kind
            if kind == "field":
                value = arg.dropdown_value if slot.arg == "free" else option_value(slot.arg, arg.dropdown_value)
                block["fields"][slot.name] = [value, None]
            elif kind == "var":
                block["fields"][slot.name] = list(self.variable(arg.dropdown_value))
            elif kind == "list":
                block["fields"][slot.name] = list(self.list_(arg.dropdown_value))
            elif kind == "bcast_field":
                name, bc_id = self.broadcast(arg.dropdown_value)
                block["fields"][slot.name] = [name, bc_id]
            elif kind == "bcast_input":
                if arg.is_dropdown or arg.bracket == "[":
                    name = arg.dropdown_value if arg.is_dropdown else arg.raw
                    block["inputs"][slot.name] = [1, [BROADCAST, *self.broadcast(name)]]
                else:
                    default = self.broadcast(self._default_broadcast_name())
                    block["inputs"][slot.name] = [3, self.build_reporter(arg, bid), [BROADCAST, *default]]
            elif kind == "bool":
                if not arg.is_empty:
                    block["inputs"][slot.name] = [2, self.build_reporter(arg, bid)]
            elif kind == "menu":
                block["inputs"][slot.name] = self.menu_input(slot.arg, arg, bid)
            elif kind == "note":
                block["inputs"][slot.name] = self.note_input(arg, bid)
            else:
                block["inputs"][slot.name] = self.value_input(arg, kind, bid)

    def value_input(self, arg: Arg, kind: str, parent: str) -> list[Any]:
        code = KIND_TO_PRIMITIVE.get(kind, TEXT)
        if kind == "color":
            if arg.is_hex:
                return [1, [COLOR_PICKER, arg.raw.strip().lower()]]
            return [3, self.build_reporter(arg, parent), [COLOR_PICKER, "#000000"]]
        if arg.bracket == "[" or arg.is_empty or arg.is_number:
            value = arg.raw if arg.bracket == "[" else arg.raw.strip()
            return [1, [code, value]]
        child = self.build_reporter(arg, parent)
        return [3, child, [code, ""]]

    def note_input(self, arg: Arg, parent: str) -> list[Any]:
        value = arg.raw.strip() if arg.is_number else "60"
        shadow = self.new_block("note", parent, shadow=True)
        self.blocks[shadow]["fields"]["NOTE"] = [value, None]
        if arg.is_number or arg.is_empty:
            return [1, shadow]
        return [3, self.build_reporter(arg, parent), shadow]

    def menu_input(self, menu_opcode: str, arg: Arg, parent: str) -> list[Any]:
        menu = MENUS[menu_opcode]
        if arg.is_dropdown:
            value = menu_value(menu, arg.dropdown_value)
        elif arg.is_number:
            value = arg.raw.strip()
        else:
            value = None
        shadow = self.new_block(menu_opcode, parent, shadow=True)
        self.blocks[shadow]["fields"][menu.field] = [value if value is not None else self._menu_default(menu_opcode), None]
        if value is not None:
            return [1, shadow]
        return [3, self.build_reporter(arg, parent), shadow]

    def _menu_default(self, menu_opcode: str) -> str:
        menu = MENUS[menu_opcode]
        if menu.default is not None:
            return menu.default
        source = self.stage if menu_opcode == "looks_backdrops" else self.target
        key = "sounds" if menu_opcode == "sound_sounds_menu" else "costumes"
        items = source.get(key) or []
        return items[0].get("name", "") if items else ""

    # -- reporters -----------------------------------------------------------

    def build_reporter(self, arg: Arg, parent: str) -> Any:
        """Build a reporter for a ( ) or < > arg. Returns a block id or a
        compressed variable/list primitive."""
        name = arg.raw.strip()
        if arg.bracket == "<":
            if self.proc_args.get(name) == "%b":
                return self._arg_reporter("argument_reporter_boolean", name, parent)
            found = match_spec(arg.children, {BOOLEAN}) or match_spec(arg.children, {REPORTER})
            if not found:
                raise ParseError(f"Unknown boolean block: {arg}.{_suggest(name)}", self.line)
            return self._build_matched(found, parent)
        if self.proc_args.get(name) == "%s":
            return self._arg_reporter("argument_reporter_string_number", name, parent)
        found = match_spec(arg.children, {REPORTER}) or match_spec(arg.children, {BOOLEAN})
        if found:
            return self._build_matched(found, parent)
        if arg.is_dropdown:
            raise ParseError(f"A dropdown {arg} can't be used here", self.line)
        list_ref = self._lookup_list(name)
        var_ref = self._lookup_var(name)
        if var_ref is None and list_ref is not None:
            return [LIST, *list_ref]
        return [VAR, *self.variable(name)]

    def _build_matched(self, found: tuple[BlockSpec, list[tuple[Slot, Arg]]], parent: str) -> str:
        spec, pairs = found
        bid = self.new_block(spec.opcode, parent)
        self.fill_slots(bid, pairs)
        return bid

    def _arg_reporter(self, opcode: str, name: str, parent: str) -> str:
        bid = self.new_block(opcode, parent)
        self.blocks[bid]["fields"]["VALUE"] = [name, None]
        return bid

    # -- variables, lists, broadcasts -----------------------------------------

    def _scopes(self) -> list[dict[str, Any]]:
        return [self.target] if self.target is self.stage else [self.target, self.stage]

    def _lookup(self, key: str, name: str) -> tuple[str, str] | None:
        for scope in self._scopes():
            for vid, entry in (scope.get(key) or {}).items():
                if entry and entry[0] == name:
                    return entry[0], vid
        return None

    def _lookup_var(self, name: str) -> tuple[str, str] | None:
        return self._lookup("variables", name)

    def _lookup_list(self, name: str) -> tuple[str, str] | None:
        return self._lookup("lists", name)

    def variable(self, name: str) -> tuple[str, str]:
        if not name:
            raise ParseError("variable name is empty", self.line)
        found = self._lookup_var(name)
        if found:
            return found
        vid = self.new_id()
        self.stage.setdefault("variables", {})[vid] = [name, 0]
        self.report.created_variables.append(name)
        return name, vid

    def list_(self, name: str) -> tuple[str, str]:
        if not name:
            raise ParseError("list name is empty", self.line)
        found = self._lookup_list(name)
        if found:
            return found
        lid = self.new_id()
        self.stage.setdefault("lists", {})[lid] = [name, []]
        self.report.created_lists.append(name)
        return name, lid

    def broadcast(self, name: str) -> tuple[str, str]:
        broadcasts = self.stage.setdefault("broadcasts", {})
        for bid, existing in broadcasts.items():
            if existing == name:
                return existing, bid
        for bid, existing in broadcasts.items():
            if existing.lower() == name.lower():
                return existing, bid
        bc_id = self.new_id()
        broadcasts[bc_id] = name
        self.report.created_broadcasts.append(name)
        return name, bc_id

    def _default_broadcast_name(self) -> str:
        broadcasts = self.stage.get("broadcasts") or {}
        return next(iter(broadcasts.values()), "message1")


def find_target(project: dict[str, Any], name: str) -> dict[str, Any]:
    targets = project.get("targets") or []
    if name.strip().lower() == "stage":
        stage = next((t for t in targets if t.get("isStage")), None)
        if stage:
            return stage
    for t in targets:
        if t.get("name") == name:
            return t
    for t in targets:
        if str(t.get("name", "")).lower() == name.strip().lower():
            return t
    names = ", ".join(str(t.get("name")) for t in targets)
    raise ParseError(f"No sprite named '{name}'. Available: {names}")
