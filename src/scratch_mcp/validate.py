"""Validation of project.json before anything is written to disk."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .blocks import BROADCAST, KNOWN_OPCODES, LIST, VAR, extension_of

PRIMITIVE_LENGTHS = {4: 2, 5: 2, 6: 2, 7: 2, 8: 2, 9: 2, 10: 2, 11: 3, 12: 3, 13: 3}
MAX_REPORTED = 50


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def format(self) -> str:
        lines = []
        if self.errors:
            lines.append(f"{len(self.errors)} error(s):")
            lines += [f"  - {e}" for e in self.errors[:MAX_REPORTED]]
            if len(self.errors) > MAX_REPORTED:
                lines.append(f"  ... and {len(self.errors) - MAX_REPORTED} more")
        if self.warnings:
            lines.append(f"{len(self.warnings)} warning(s):")
            lines += [f"  - {w}" for w in self.warnings[:MAX_REPORTED]]
            if len(self.warnings) > MAX_REPORTED:
                lines.append(f"  ... and {len(self.warnings) - MAX_REPORTED} more")
        return "\n".join(lines) if lines else "No problems found."


class DuplicateKeyError(ValueError):
    pass


def parse_project_json(text: str) -> dict[str, Any]:
    """json.loads that refuses duplicate keys (duplicate block IDs would
    otherwise be silently dropped)."""
    duplicates: list[str] = []

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        counts = Counter(k for k, _ in pairs)
        duplicates.extend(k for k, n in counts.items() if n > 1)
        return dict(pairs)

    try:
        data = json.loads(text, object_pairs_hook=hook)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if duplicates:
        shown = ", ".join(repr(d) for d in sorted(set(duplicates))[:10])
        raise DuplicateKeyError(
            f"Duplicate keys in JSON (block IDs must be unique): {shown}"
        )
    if not isinstance(data, dict):
        raise ValueError("project.json must be a JSON object")
    return data


def _asset_file(asset: dict[str, Any]) -> str | None:
    if isinstance(asset.get("md5ext"), str):
        return asset["md5ext"]
    if isinstance(asset.get("assetId"), str) and isinstance(asset.get("dataFormat"), str):
        return f"{asset['assetId']}.{asset['dataFormat']}"
    return None


def validate_project(project: Any, asset_names: set[str] | None = None) -> ValidationResult:
    """Check structure, block links, opcodes and asset references.

    ``asset_names``: files available in the .sb3; if given, every costume and
    sound must refer to one of them.
    """
    r = ValidationResult()
    if not isinstance(project, dict):
        r.errors.append("project.json must be a JSON object")
        return r
    targets = project.get("targets")
    if not isinstance(targets, list) or not targets:
        r.errors.append("'targets' must be a non-empty list")
        return r
    if not isinstance(project.get("meta"), dict):
        r.warnings.append("'meta' is missing (Scratch expects {\"semver\": \"3.0.0\", ...})")

    stages = [t for t in targets if isinstance(t, dict) and t.get("isStage") is True]
    if len(stages) != 1:
        r.errors.append(f"There must be exactly one Stage target (found {len(stages)})")

    names = [t.get("name") for t in targets if isinstance(t, dict) and not t.get("isStage")]
    for name, n in Counter(names).items():
        if n > 1:
            r.errors.append(f"Sprite name '{name}' is used {n} times; sprite names must be unique")

    extensions = project.get("extensions") or []
    if not isinstance(extensions, list):
        r.errors.append("'extensions' must be a list")
        extensions = []

    stage = stages[0] if stages else {}
    global_vars = stage.get("variables") or {} if isinstance(stage, dict) else {}
    global_lists = stage.get("lists") or {} if isinstance(stage, dict) else {}
    broadcasts = stage.get("broadcasts") or {} if isinstance(stage, dict) else {}

    seen_block_ids: dict[str, str] = {}
    used_extensions: set[str] = set()
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            r.errors.append(f"targets[{index}] is not an object")
            continue
        label = "Stage" if target.get("isStage") else f"sprite '{target.get('name', index)}'"
        _validate_target_basics(target, label, asset_names, r)
        blocks = target.get("blocks")
        if not isinstance(blocks, dict):
            r.errors.append(f"{label}: 'blocks' must be an object")
            continue
        for block_id in blocks:
            if block_id in seen_block_ids:
                r.errors.append(
                    f"Block ID '{block_id}' is used in both {seen_block_ids[block_id]} and {label}; "
                    "block IDs must be unique"
                )
            else:
                seen_block_ids[block_id] = label
        vars_in_scope = {**global_vars, **(target.get("variables") or {})}
        lists_in_scope = {**global_lists, **(target.get("lists") or {})}
        _validate_blocks(blocks, label, r, used_extensions, vars_in_scope, lists_in_scope, broadcasts)

    for ext in sorted(used_extensions - set(extensions)):
        r.warnings.append(f"Blocks from extension '{ext}' are used but '{ext}' is not in 'extensions'")
    return r


def _validate_target_basics(
    target: dict[str, Any], label: str, asset_names: set[str] | None, r: ValidationResult
) -> None:
    if not isinstance(target.get("name"), str):
        r.errors.append(f"{label}: 'name' must be a string")
    for key in ("variables", "lists", "broadcasts"):
        if key in target and not isinstance(target[key], dict):
            r.errors.append(f"{label}: '{key}' must be an object")
    for vid, var in (target.get("variables") or {}).items() if isinstance(target.get("variables"), dict) else []:
        if not isinstance(var, list) or len(var) < 2 or not isinstance(var[0], str):
            r.errors.append(f"{label}: variable '{vid}' must look like [name, value]")
    for lid, lst in (target.get("lists") or {}).items() if isinstance(target.get("lists"), dict) else []:
        if not isinstance(lst, list) or len(lst) < 2 or not isinstance(lst[0], str) or not isinstance(lst[1], list):
            r.errors.append(f"{label}: list '{lid}' must look like [name, [items...]]")

    costumes = target.get("costumes")
    if not isinstance(costumes, list) or not costumes:
        r.errors.append(f"{label}: needs at least one {'backdrop' if target.get('isStage') else 'costume'}")
        costumes = []
    current = target.get("currentCostume", 0)
    if costumes and (not isinstance(current, int) or not 0 <= current < len(costumes)):
        r.errors.append(f"{label}: currentCostume {current!r} is out of range (0..{len(costumes) - 1})")
    sounds = target.get("sounds") or []
    if not isinstance(sounds, list):
        r.errors.append(f"{label}: 'sounds' must be a list")
        sounds = []
    for kind, assets in (("costume", costumes), ("sound", sounds)):
        for asset in assets:
            if not isinstance(asset, dict):
                r.errors.append(f"{label}: {kind} entry is not an object")
                continue
            filename = _asset_file(asset)
            if filename is None:
                r.errors.append(f"{label}: {kind} '{asset.get('name')}' has no md5ext/assetId")
            elif asset_names is not None and filename not in asset_names:
                r.errors.append(
                    f"{label}: {kind} '{asset.get('name')}' refers to '{filename}', which is not in the .sb3"
                )


def _validate_blocks(
    blocks: dict[str, Any],
    label: str,
    r: ValidationResult,
    used_extensions: set[str],
    variables: dict[str, Any],
    lists: dict[str, Any],
    broadcasts: dict[str, Any],
) -> None:
    referenced: Counter[str] = Counter()  # how many places point at each block

    def where(bid: str) -> str:
        return f"{label}, block '{bid}'"

    def check_ref(bid: str, ref: str, how: str) -> None:
        referenced[ref] += 1
        child = blocks.get(ref)
        if child is None:
            r.errors.append(f"{where(bid)}: {how} points to missing block '{ref}'")
        elif isinstance(child, dict) and child.get("parent") != bid:
            r.errors.append(
                f"{where(bid)}: {how} points to '{ref}', but that block's parent is {child.get('parent')!r}"
            )
        elif isinstance(child, list):
            r.errors.append(f"{where(bid)}: {how} points to '{ref}', which is a loose top-level reporter")

    for bid, block in blocks.items():
        if isinstance(block, list):
            # Loose variable/list reporter on the canvas: [12|13, name, id, x, y]
            if len(block) < 5 or block[0] not in (VAR, LIST):
                r.errors.append(f"{where(bid)}: top-level array must be [12 or 13, name, id, x, y]")
            continue
        if not isinstance(block, dict):
            r.errors.append(f"{where(bid)}: must be an object")
            continue

        opcode = block.get("opcode")
        if not isinstance(opcode, str):
            r.errors.append(f"{where(bid)}: missing 'opcode'")
        elif opcode not in KNOWN_OPCODES:
            r.errors.append(f"{where(bid)}: unknown opcode '{opcode}'")
        else:
            ext = extension_of(opcode)
            if ext:
                used_extensions.add(ext)

        top = block.get("topLevel")
        if not isinstance(top, bool):
            r.errors.append(f"{where(bid)}: 'topLevel' must be true or false")
        parent = block.get("parent")
        if top:
            if parent is not None:
                r.errors.append(f"{where(bid)}: topLevel block must have parent null (has {parent!r})")
            if not isinstance(block.get("x"), (int, float)) or not isinstance(block.get("y"), (int, float)):
                r.warnings.append(f"{where(bid)}: topLevel block has no x/y position")
        elif top is False:
            if parent is None:
                r.errors.append(f"{where(bid)}: block is not topLevel but has no parent")

        if parent is not None:
            p = blocks.get(parent) if isinstance(parent, str) else None
            if not isinstance(p, dict):
                r.errors.append(f"{where(bid)}: parent '{parent}' does not exist")
            elif p.get("next") != bid and not _input_mentions(p, bid):
                r.errors.append(
                    f"{where(bid)}: parent '{parent}' does not link back to it (neither via 'next' nor an input)"
                )

        nxt = block.get("next")
        if nxt is not None:
            if not isinstance(nxt, str):
                r.errors.append(f"{where(bid)}: 'next' must be a block ID or null")
            else:
                check_ref(bid, nxt, "'next'")
                child = blocks.get(nxt)
                if isinstance(child, dict) and child.get("topLevel"):
                    r.errors.append(f"{where(bid)}: 'next' block '{nxt}' is marked topLevel")

        inputs = block.get("inputs", {})
        if not isinstance(inputs, dict):
            r.errors.append(f"{where(bid)}: 'inputs' must be an object")
            inputs = {}
        for name, inp in inputs.items():
            if not isinstance(inp, list) or not inp or inp[0] not in (1, 2, 3):
                r.errors.append(f"{where(bid)}: input '{name}' must look like [1|2|3, ...]")
                continue
            for value in inp[1:]:
                if isinstance(value, str):
                    check_ref(bid, value, f"input '{name}'")
                elif isinstance(value, list):
                    _check_primitive(value, f"{where(bid)}: input '{name}'", r, variables, lists, broadcasts)
                elif value is not None:
                    r.errors.append(f"{where(bid)}: input '{name}' has an invalid value {value!r}")

        fields = block.get("fields", {})
        if not isinstance(fields, dict):
            r.errors.append(f"{where(bid)}: 'fields' must be an object")
            fields = {}
        for name, value in fields.items():
            if not isinstance(value, list) or not value:
                r.errors.append(f"{where(bid)}: field '{name}' must look like [value, id-or-null]")
        _check_field_refs(block, where(bid), r, variables, lists, broadcasts)

    for ref, n in referenced.items():
        if n > 1:
            r.errors.append(f"{label}: block '{ref}' is linked from {n} places (a block can only be in one spot)")

    # Every block must lead up to a top-level block without looping.
    for bid, block in blocks.items():
        if not isinstance(block, dict):
            continue
        seen = {bid}
        cur = block
        while isinstance(cur, dict) and cur.get("parent") is not None:
            pid = cur.get("parent")
            if pid in seen:
                r.errors.append(f"{label}: block '{bid}' is part of a loop of parent links")
                break
            seen.add(pid)
            cur = blocks.get(pid)


def _input_mentions(block: dict[str, Any], child_id: str) -> bool:
    for inp in (block.get("inputs") or {}).values():
        if isinstance(inp, list) and child_id in inp[1:]:
            return True
    return False


def _check_primitive(
    value: list[Any], where: str, r: ValidationResult,
    variables: dict[str, Any], lists: dict[str, Any], broadcasts: dict[str, Any],
) -> None:
    code = value[0] if value else None
    expected = PRIMITIVE_LENGTHS.get(code) if isinstance(code, int) else None
    if expected is None:
        r.errors.append(f"{where}: unknown primitive type {code!r}")
        return
    if len(value) < expected:
        r.errors.append(f"{where}: primitive {value!r} is too short")
        return
    if code == VAR and value[2] not in variables:
        r.warnings.append(f"{where}: variable '{value[1]}' (id {value[2]}) is not defined; Scratch will create it")
    if code == LIST and value[2] not in lists:
        r.warnings.append(f"{where}: list '{value[1]}' (id {value[2]}) is not defined; Scratch will create it")
    if code == BROADCAST and value[2] not in broadcasts:
        r.warnings.append(f"{where}: broadcast '{value[1]}' (id {value[2]}) is not defined; Scratch will create it")


def _check_field_refs(
    block: dict[str, Any], where: str, r: ValidationResult,
    variables: dict[str, Any], lists: dict[str, Any], broadcasts: dict[str, Any],
) -> None:
    fields = block.get("fields") or {}
    for name, table, kind in (("VARIABLE", variables, "variable"), ("LIST", lists, "list"),
                              ("BROADCAST_OPTION", broadcasts, "broadcast")):
        value = fields.get(name)
        if isinstance(value, list) and len(value) >= 2 and value[1] is not None and value[1] not in table:
            r.warnings.append(f"{where}: {kind} '{value[0]}' (id {value[1]}) is not defined; Scratch will create it")
