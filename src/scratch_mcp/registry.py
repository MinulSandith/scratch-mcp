"""Action registry: groups of tools (project_manager, sprite_manager, ...) each exposing
many ``action``s.

Why not one MCP tool per operation? With well over a hundred operations that would bury the
useful ones. Instead every group is ONE tool ``(action, args)``; each action has a strict
pydantic model built from its handler's type hints, validated server side, and the tool
description lists every action with its parameters. ``action="help"`` returns the exact
JSON schema of any action.
"""

from __future__ import annotations

import inspect
import json
import re
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Callable, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from .workspace import WorkspaceError


@dataclass
class Reply:
    """Handler return value with optional images/audio (returned as real MCP image/audio content)."""

    text: str | dict | list | None = None
    images: list[tuple[bytes, str]] = field(default_factory=list)  # (data, mime type)
    audio: list[tuple[bytes, str]] = field(default_factory=list)


@dataclass
class Action:
    group: str
    name: str
    fn: Callable
    model: type[BaseModel]
    summary: str
    params: list[tuple[str, str, bool, str]]  # name, type text, required, description


GROUPS: dict[str, dict[str, Action]] = {}
GROUP_DOCS: dict[str, str] = {}


def _type_text(tp: Any) -> str:
    origin = get_origin(tp)
    if tp is type(None):
        return "null"
    if origin is typing.Literal:
        return "|".join(json.dumps(a) if isinstance(a, str) else str(a) for a in get_args(tp))
    if origin in (Union, types.UnionType):
        parts = [_type_text(a) for a in get_args(tp) if a is not type(None)]
        return "|".join(parts) if parts else "null"
    if origin in (list, typing.List):
        args = get_args(tp)
        return f"[{_type_text(args[0])}]" if args else "list"
    if origin in (dict, typing.Dict):
        return "object"
    if isinstance(tp, type):
        return {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "dict": "object", "list": "list"}.get(tp.__name__, tp.__name__)
    return "any"


def _parse_doc(fn: Callable) -> tuple[str, dict[str, str]]:
    doc = inspect.getdoc(fn) or ""
    summary_lines, arg_docs, in_args, current = [], {}, False, None
    for line in doc.splitlines():
        if re.match(r"^\s*Args:\s*$", line):
            in_args = True
            continue
        if in_args:
            m = re.match(r"^\s{0,4}(\w+):\s*(.*)$", line)
            if m:
                current = m.group(1)
                arg_docs[current] = m.group(2).strip()
            elif current and line.strip():
                arg_docs[current] += " " + line.strip()
        else:
            summary_lines.append(line)
    summary = " ".join(l.strip() for l in summary_lines if l.strip())
    return summary, arg_docs


def action(group: str, name: str | None = None):
    """Register ``fn(ctx, **params)`` as ``group``'s action ``name`` (default: function name)."""

    def deco(fn: Callable) -> Callable:
        act_name = name or fn.__name__
        hints = typing.get_type_hints(fn)
        sig = inspect.signature(fn)
        summary, arg_docs = _parse_doc(fn)
        fields: dict[str, Any] = {}
        params = []
        for pname, p in list(sig.parameters.items())[1:]:  # skip ctx
            tp = hints.get(pname, Any)
            required = p.default is inspect.Parameter.empty
            default = ... if required else p.default
            desc = arg_docs.get(pname, "")
            fields[pname] = (tp, Field(default, description=desc) if desc else default)
            params.append((pname, _type_text(tp), required, desc))
        model = create_model(
            f"{group}_{act_name}", __config__=ConfigDict(extra="forbid", arbitrary_types_allowed=True), **fields
        )
        GROUPS.setdefault(group, {})[act_name] = Action(group, act_name, fn, model, summary, params)
        return fn

    return deco


def describe_group(group: str) -> str:
    lines = [GROUP_DOCS.get(group, ""), "", "Call with action=<name> and args={...}. Parameters ending in * are required; "
             "'project' (default: the active project) and 'sprite' (default: the selected sprite) are optional where listed. "
             "action='help' (args {'action': name}) returns the exact JSON schema.", "", "Actions:"]
    for act in GROUPS[group].values():
        ps = ", ".join(f"{n}{'*' if req else ''}: {t}" for n, t, req, _ in act.params)
        lines.append(f"- {act.name}({ps}) - {act.summary}")
    return "\n".join(l for l in lines)


def _json_default(o: Any) -> Any:
    if isinstance(o, (bytes, bytearray)):
        return f"<{len(o)} bytes>"
    return str(o)


def to_content(value: Any):
    """Convert a handler's return value to MCP content blocks."""
    from mcp.types import AudioContent, ImageContent, TextContent
    import base64

    if isinstance(value, Reply):
        blocks: list[Any] = []
        if value.text is not None:
            blocks.extend(to_content(value.text))
        for data, mime in value.images:
            blocks.append(ImageContent(type="image", data=base64.b64encode(data).decode(), mimeType=mime))
        for data, mime in value.audio:
            blocks.append(AudioContent(type="audio", data=base64.b64encode(data).decode(), mimeType=mime))
        return blocks
    if isinstance(value, str):
        return [TextContent(type="text", text=value)]
    return [TextContent(type="text", text=json.dumps(value, indent=1, ensure_ascii=False, default=_json_default))]


async def dispatch(group: str, ctx: Any, action_name: str, args: dict[str, Any] | None):
    acts = GROUPS[group]
    args = dict(args or {})
    if action_name == "help":
        target = args.get("action")
        if target and target not in acts:
            raise WorkspaceError(f"Unknown action '{target}'. Actions: {', '.join(acts)}")
        chosen = [acts[target]] if target else list(acts.values())
        return {a.name: {"summary": a.summary, "schema": a.model.model_json_schema()} for a in chosen}
    act = acts.get(action_name)
    if act is None:
        near = [n for n in acts if action_name.lower() in n.lower() or n.lower() in action_name.lower()]
        hint = f" Did you mean: {', '.join(near)}?" if near else ""
        raise WorkspaceError(f"Unknown action '{action_name}' for {group}.{hint} Available: {', '.join(acts)}")
    try:
        parsed = act.model.model_validate(args)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(x) for x in e['loc']) or 'args'}: {e['msg']}" for e in exc.errors())
        ps = ", ".join(f"{n}{'*' if req else ''}: {t}" for n, t, req, _ in act.params)
        raise WorkspaceError(f"Invalid args for {group}.{act.name}: {problems}. Expected: {ps or 'no arguments'}") from exc
    kwargs = {name: getattr(parsed, name) for name in act.model.model_fields}
    result = act.fn(ctx, **kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result
