"""Turn project.json into readable text.

Scripts are rendered in scratchblocks-style text, the same notation
``add_script`` accepts, e.g.::

    when flag clicked
    forever
      move (10) steps
      if <touching (edge v)?> then
        turn right (180) degrees
      end
    end
"""

from __future__ import annotations

import json
import re
from typing import Any

from .blocks import (
    BOOLEAN, BROADCAST, C, C_CAP, IF_ELSE, KIND_TO_PRIMITIVE, LIST, MENUS,
    PRIMITIVE_OPCODES, REPORTER, SLOT_RE, SPECS, VAR, Slot, menu_display,
    option_display,
)

INDENT = "  "
_NUMBER_RE = re.compile(r"^-?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$", re.IGNORECASE)


def escape(text: str, closer: str = "]") -> str:
    """Backslash-escape the closing bracket so the text parses back unchanged."""
    return text.replace("\\", "\\\\").replace(closer, "\\" + closer)


class ScriptRenderer:
    def __init__(self, blocks: dict[str, Any]):
        self.blocks = blocks

    # -- stacks ----------------------------------------------------------

    def render_stack(self, block_id: str | None, depth: int = 0) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()
        while block_id:
            if block_id in seen:
                lines.append(INDENT * depth + "... (loop in next links)")
                break
            seen.add(block_id)
            block = self.blocks.get(block_id)
            if not isinstance(block, dict):
                lines.append(INDENT * depth + f"(missing block {block_id})")
                break
            lines.extend(self.render_statement(block, depth))
            block_id = block.get("next")
        return lines

    def render_statement(self, block: dict[str, Any], depth: int) -> list[str]:
        opcode = block.get("opcode", "?")
        pad = INDENT * depth
        if opcode == "procedures_definition":
            return [pad + "define " + self.render_prototype(block)]
        spec = SPECS.get(opcode)
        head = self.render_inline(block)
        if spec and spec.shape in (C, C_CAP, IF_ELSE):
            lines = [pad + head]
            lines += self.render_stack(self.input_block(block, "SUBSTACK"), depth + 1)
            if spec.shape == IF_ELSE:
                lines.append(pad + "else")
                lines += self.render_stack(self.input_block(block, "SUBSTACK2"), depth + 1)
            lines.append(pad + "end")
            return lines
        return [pad + head]

    # -- single blocks ---------------------------------------------------

    def render_inline(self, block: dict[str, Any]) -> str:
        opcode = block.get("opcode", "?")
        if opcode == "procedures_call":
            return self.render_call(block)
        if opcode in ("argument_reporter_string_number", "argument_reporter_boolean"):
            return self.field_value(block, "VALUE")
        if opcode == "data_variable":
            return self.field_value(block, "VARIABLE")
        if opcode == "data_listcontents":
            return self.field_value(block, "LIST")
        if opcode in MENUS:
            menu = MENUS[opcode]
            return menu_display(menu, self.field_value(block, menu.field)) + " v"
        if opcode in PRIMITIVE_OPCODES.values() or opcode == "note":
            fields = block.get("fields") or {}
            first = next(iter(fields.values()), [""])
            return str(first[0] if isinstance(first, list) else first)
        spec = SPECS.get(opcode)
        if spec is None:
            return self.render_generic(block)
        return SLOT_RE.sub(
            lambda m: self.render_slot(block, Slot(m.group(1), m.group(2), m.group(3))),
            spec.templates[0],
        )

    def render_slot(self, block: dict[str, Any], slot: Slot) -> str:
        kind = slot.kind
        if kind == "field":
            optset = None if slot.arg == "free" else slot.arg
            return f"[{escape(option_display(optset, self.field_value(block, slot.name)))} v]"
        if kind in ("var", "list", "bcast_field"):
            return f"[{escape(self.field_value(block, slot.name))} v]"
        return self.render_input(block, slot.name, kind)

    def render_input(self, block: dict[str, Any], name: str, kind: str = "text") -> str:
        """Render one input with bracket style matching its kind."""
        inp = (block.get("inputs") or {}).get(name)
        empty = {"bool": "<>", "text": "[]", "color": "[#000000]"}.get(kind, "()")
        if not isinstance(inp, list) or len(inp) < 2:
            return empty
        value = inp[1]
        if value is None:
            return empty
        return self.render_value(value, kind)

    def render_value(self, value: Any, kind: str) -> str:
        if isinstance(value, list):  # compressed primitive
            code = value[0] if value else None
            if code in (VAR, LIST) and len(value) >= 2:
                return f"({escape(str(value[1]), ')')})"
            if code == BROADCAST and len(value) >= 2:
                return f"({escape(str(value[1]), ')')} v)"
            text = str(value[1]) if len(value) > 1 else ""
            if code == KIND_TO_PRIMITIVE["color"] or (code == KIND_TO_PRIMITIVE["text"] and not _NUMBER_RE.match(text)):
                return f"[{escape(text)}]"
            return f"({escape(text, ')')})"
        target = self.blocks.get(value)
        if isinstance(target, list):  # top-level primitive referenced by id (rare)
            return self.render_value(target, kind)
        if not isinstance(target, dict):
            return f"(missing block {value})"
        opcode = target.get("opcode", "")
        inner = self.render_inline(target)
        if opcode in MENUS:
            return f"({inner})"
        if opcode == "colour_picker" or (opcode == "text" and not _NUMBER_RE.match(inner)):
            return f"[{escape(inner)}]"
        if opcode in PRIMITIVE_OPCODES.values() or opcode == "note":
            return f"({escape(inner, ')')})"
        if self.is_boolean(target):
            return f"<{inner}>"
        return f"({inner})"

    def is_boolean(self, block: dict[str, Any]) -> bool:
        opcode = block.get("opcode", "")
        if opcode == "argument_reporter_boolean":
            return True
        spec = SPECS.get(opcode)
        return bool(spec and spec.shape == "boolean")

    def input_block(self, block: dict[str, Any], name: str) -> str | None:
        inp = (block.get("inputs") or {}).get(name)
        if isinstance(inp, list) and len(inp) >= 2 and isinstance(inp[1], str):
            return inp[1]
        return None

    @staticmethod
    def field_value(block: dict[str, Any], name: str) -> str:
        f = (block.get("fields") or {}).get(name)
        if isinstance(f, list) and f:
            return str(f[0])
        return "" if f is None else str(f)

    # -- custom blocks ---------------------------------------------------

    def render_prototype(self, definition: dict[str, Any]) -> str:
        proto_id = self.input_block(definition, "custom_block")
        proto = self.blocks.get(proto_id) if proto_id else None
        if not isinstance(proto, dict):
            return "(missing prototype)"
        mutation = proto.get("mutation") or {}
        names = _json_list(mutation.get("argumentnames"))
        out, i = [], 0
        for part in _split_proccode(mutation.get("proccode", "")):
            if part in ("%s", "%n", "%b"):
                name = names[i] if i < len(names) else "?"
                out.append(f"<{name}>" if part == "%b" else f"({name})")
                i += 1
            else:
                out.append(part)
        text = " ".join(out)
        if str(mutation.get("warp")).lower() == "true":
            text += "  // run without screen refresh"
        return text

    def render_call(self, block: dict[str, Any]) -> str:
        mutation = block.get("mutation") or {}
        arg_ids = _json_list(mutation.get("argumentids"))
        out, i = [], 0
        for part in _split_proccode(mutation.get("proccode", "")):
            if part in ("%s", "%n", "%b"):
                arg = arg_ids[i] if i < len(arg_ids) else None
                kind = "bool" if part == "%b" else "text"
                out.append(self.render_input(block, arg, kind) if arg else "()")
                i += 1
            else:
                out.append(part)
        return " ".join(out)

    def render_generic(self, block: dict[str, Any]) -> str:
        """Fallback for blocks without a template (hardware extensions etc.)."""
        parts = [block.get("opcode", "?")]
        for name in block.get("inputs") or {}:
            parts.append(f"{name}: {self.render_input(block, name)}")
        for name in block.get("fields") or {}:
            parts.append(f"{name}: [{escape(self.field_value(block, name))} v]")
        return " ".join(parts)


def _split_proccode(proccode: str) -> list[str]:
    return [p for p in proccode.replace("%s", " %s ").replace("%b", " %b ").replace("%n", " %n ").split(" ") if p]


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


# ---------------------------------------------------------------------------
# Whole-project summary
# ---------------------------------------------------------------------------


def top_level_scripts(target: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    blocks = target.get("blocks") or {}
    tops = [
        (bid, b) for bid, b in blocks.items()
        if isinstance(b, dict) and b.get("topLevel") and not b.get("shadow")
    ]
    tops.sort(key=lambda kv: (kv[1].get("y") or 0, kv[1].get("x") or 0))
    return tops


def render_target_scripts(target: dict[str, Any]) -> list[str]:
    blocks = target.get("blocks") or {}
    renderer = ScriptRenderer(blocks)
    scripts = []
    for bid, block in top_level_scripts(target):
        spec = SPECS.get(block.get("opcode", ""))
        if spec and spec.shape in (REPORTER, BOOLEAN):
            scripts.append(f"{renderer.render_value(bid, 'text')}  // loose reporter")
        else:
            scripts.append("\n".join(renderer.render_stack(bid)))
    # Loose variable/list reporters stored as top-level arrays
    for value in blocks.values():
        if isinstance(value, list) and len(value) >= 2 and value[0] in (VAR, LIST):
            scripts.append(f"({value[1]})  // loose reporter")
    return scripts


def _format_value(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False) if isinstance(v, str) else str(v)


def summarize_project(name: str, project: dict[str, Any]) -> str:
    targets = project.get("targets") or []
    stage = next((t for t in targets if t.get("isStage")), None)
    sprites = [t for t in targets if not t.get("isStage")]
    out: list[str] = [f"# Project: {name}"]
    exts = project.get("extensions") or []
    out.append(f"Sprites: {len(sprites)} | Extensions: {', '.join(exts) if exts else 'none'}")
    total_blocks = sum(len(t.get("blocks") or {}) for t in targets)
    out.append(f"Total blocks: {total_blocks}")

    if stage is not None:
        broadcasts = list((stage.get("broadcasts") or {}).values())
        if broadcasts:
            out.append("Broadcasts: " + ", ".join(broadcasts))

    for target in ([stage] if stage else []) + sprites:
        out.append("")
        if target.get("isStage"):
            out.append("## Stage")
        else:
            out.append(f"## Sprite: {target.get('name')}")
            out.append(
                f"position ({target.get('x', 0)}, {target.get('y', 0)}), "
                f"direction {target.get('direction', 90)}, size {target.get('size', 100)}%, "
                f"{'visible' if target.get('visible', True) else 'hidden'}"
            )
        label = "Backdrops" if target.get("isStage") else "Costumes"
        costumes = [c.get("name", "?") for c in target.get("costumes") or []]
        current = target.get("currentCostume", 0)
        if costumes:
            marked = [f"{c} (current)" if i == current else c for i, c in enumerate(costumes)]
            out.append(f"{label}: " + ", ".join(marked))
        sounds = [s.get("name", "?") for s in target.get("sounds") or []]
        if sounds:
            out.append("Sounds: " + ", ".join(sounds))

        scope = "global, for all sprites" if target.get("isStage") else "this sprite only"
        variables = target.get("variables") or {}
        if variables:
            out.append(f"Variables ({scope}):")
            for var in variables.values():
                cloud = " [cloud]" if len(var) > 2 and var[2] else ""
                out.append(f"  - {var[0]} = {_format_value(var[1])}{cloud}")
        lists = target.get("lists") or {}
        if lists:
            out.append(f"Lists ({scope}):")
            for lst in lists.values():
                items = lst[1] if len(lst) > 1 and isinstance(lst[1], list) else []
                preview = ", ".join(_format_value(i) for i in items[:5])
                more = f", ... (+{len(items) - 5} more)" if len(items) > 5 else ""
                out.append(f"  - {lst[0]}: {len(items)} items [{preview}{more}]")

        scripts = render_target_scripts(target)
        if scripts:
            out.append(f"Scripts ({len(scripts)}):")
            for i, script in enumerate(scripts, 1):
                out.append(f"### Script {i}")
                out.append(script)
        else:
            out.append("Scripts: none")
        comments = [c.get("text", "") for c in (target.get("comments") or {}).values() if isinstance(c, dict)]
        if comments:
            out.append("Comments:")
            out.extend(f"  - {c}" for c in comments)
    return "\n".join(out)
