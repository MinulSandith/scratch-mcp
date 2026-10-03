"""block_manager: opcode catalog and per-block operations (add, delete, move, connect, edit inputs/fields) + comments."""

from __future__ import annotations

from typing import Any

from .. import schema
from ..ctx import Ctx
from ..engine import EngineError, Graph
from ..registry import GROUP_DOCS, action
from ..render import ScriptRenderer
from ..workspace import WorkspaceError
from ._common import graph_edit, graph_read

G = "block_manager"
GROUP_DOCS[G] = (
    "Work with individual blocks (any of Scratch's 290+ opcodes, incl. extensions). Browse with 'catalog'/'describe'. "
    "Edit the block graph: add blocks into existing scripts (after / into a C block / into an input), delete, move, "
    "connect, disconnect, duplicate, change inputs and dropdown fields, add comments. Block ids come from "
    "script_manager list_scripts / get_script (with_ids) or from the ids returned by add actions. All placements are "
    "checked against Scratch's rules (hat blocks start scripts, cap blocks end them, boolean slots take boolean blocks)."
)


@action(G)
def catalog(ctx: Ctx, category: str | None = None, query: str | None = None) -> dict:
    """List opcodes with their inputs (and shadow/menu types) and fields (dropdown options).

    Args:
        category: motion, looks, sound, events, control, sensing, operators, variables, lists, myblocks, or an extension id (pen, music, videoSensing, text2speech, translate, makeymakey, microbit, ev3, boost, wedo2, gdxfor).
        query: substring of opcode or block text.
    """
    items = schema.opcode_catalog(category, query)
    return {"count": len(items), "blocks": items}


@action(G)
def describe(ctx: Ctx, opcode: str) -> dict:
    """Full schema of one opcode: shape, inputs (shadow type, default, boolean/statement), fields (options), extension."""
    s = schema.spec(opcode)
    if s is None:
        near = [o for o in schema.blocks() if opcode.lower() in o.lower()][:8]
        raise WorkspaceError(f"Unknown opcode '{opcode}'." + (f" Similar: {near}" if near else ""))
    return {"opcode": opcode, **s}


@action(G)
def add(ctx: Ctx, blocks: list[dict[str, Any]], sprite: str | None = None, project: str | None = None,
        after: str | None = None, into: str | None = None, input: str | None = None,
        replace_input_of: str | None = None, x: float | None = None, y: float | None = None) -> dict:
    """Create blocks from JSON trees and place them in the graph.

    Args:
        blocks: block trees, e.g. [{"opcode":"motion_movesteps","inputs":{"STEPS":10}}].
        after: insert after this block id (blocks that followed move to the end of the inserted stack).
        into: put the stack inside this C block id; 'input' = SUBSTACK (default) or SUBSTACK2 (else branch).
        input: input name for 'into' / 'replace_input_of'.
        replace_input_of: put one reporter/boolean block into this block id's value input named 'input'.
        x: canvas position for a new free-standing script (when no placement is given).
        y: canvas position for a new free-standing script.
    """
    def fn(g: Graph):
        firsts = g.add(blocks, x=x, y=y, after=after, into=into, input=input, replace_input_of=replace_input_of)
        r = ScriptRenderer(g.blocks)
        text = [ "\n".join(r.render_stack(f)) if not (schema.spec(g.blocks[f]["opcode"]) or {}).get("shape") in schema.REPORTER_SHAPES
                 else r.render_value(f, "text") for f in firsts]
        return {"ids": firsts, "created_blocks": len(g.created), "text": text}

    return graph_edit(ctx, project, sprite, "add blocks", fn)


@action(G)
def get(ctx: Ctx, id: str, sprite: str | None = None, project: str | None = None) -> dict:
    """Detailed view of one block: opcode, raw inputs/fields, parent, next, shape, readable text."""
    g, name = graph_read(ctx, project, sprite)
    try:
        b = g.get(id)
    except EngineError as exc:
        raise WorkspaceError(str(exc)) from exc
    spec = schema.spec(b["opcode"]) or {}
    r = ScriptRenderer(g.blocks)
    return {"sprite": name, "id": id, "opcode": b["opcode"], "shape": spec.get("shape"), "shadow": b.get("shadow"),
            "top_level": b.get("topLevel"), "parent": b.get("parent"), "next": b.get("next"), "inputs": b.get("inputs"),
            "fields": b.get("fields"), "mutation": b.get("mutation"), "comment": b.get("comment"),
            "text": r.render_inline(b) if not b.get("shadow") else None}


@action(G)
def delete(ctx: Ctx, id: str, mode: str = "stack", sprite: str | None = None, project: str | None = None) -> dict:
    """Delete a block. Blocks nested inside its inputs go with it.

    Args:
        id: block id.
        mode: 'stack' = this block and all blocks after it; 'single' = only this block (following blocks reconnect to the previous one).
    """
    return graph_edit(ctx, project, sprite, "delete block", lambda g: {"deleted_ids": g.delete(id, mode=mode)})


@action(G)
def move(ctx: Ctx, id: str, sprite: str | None = None, project: str | None = None, x: float | None = None,
         y: float | None = None, after: str | None = None, into: str | None = None, input: str | None = None,
         replace_input_of: str | None = None, single: bool = False) -> dict:
    """Move a block (with the blocks after it) to a new place: free canvas (x,y), after another block, into a C block, or into an input.

    Args:
        single: move only this block; the blocks after it stay where they were.
    """
    def fn(g: Graph):
        g.move(id, x=x, y=y, after=after, into=into, input=input, replace_input_of=replace_input_of, single=single)
        return {"moved": id}

    return graph_edit(ctx, project, sprite, "move block", fn)


@action(G)
def connect(ctx: Ctx, id: str, after: str | None = None, into: str | None = None, input: str | None = None,
            replace_input_of: str | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Connect a (free) block/stack to another: below 'after', inside C block 'into' (+input), or into a value input."""
    if after is None and into is None and replace_input_of is None:
        raise WorkspaceError("Give one of after / into / replace_input_of.")

    def fn(g: Graph):
        g.move(id, after=after, into=into, input=input, replace_input_of=replace_input_of)
        return {"connected": id}

    return graph_edit(ctx, project, sprite, "connect blocks", fn)


@action(G)
def disconnect(ctx: Ctx, id: str, sprite: str | None = None, project: str | None = None,
               x: float | None = None, y: float | None = None) -> dict:
    """Pull a block (and the blocks after it) out of its script into a free-standing stack."""
    def fn(g: Graph):
        g.detach(id, x, y)
        return {"detached": id}

    return graph_edit(ctx, project, sprite, "disconnect block", fn)


@action(G)
def duplicate(ctx: Ctx, id: str, include_next: bool = True, sprite: str | None = None, project: str | None = None,
              x: float | None = None, y: float | None = None) -> dict:
    """Duplicate a block (with its inner blocks; optionally the blocks after it) as a free-standing stack."""
    return graph_edit(ctx, project, sprite, "duplicate block",
                      lambda g: {"new_id": g.duplicate(id, include_next=include_next, x=x, y=y)})


@action(G)
def set_input(ctx: Ctx, id: str, name: str, value: Any, sprite: str | None = None, project: str | None = None) -> dict:
    """Change a block input. value = literal | {"variable":n} | {"list":n} | {"menu":v} | nested block tree | list of trees (C-block body) | null (reset to default)."""
    return graph_edit(ctx, project, sprite, f"set input {name}", lambda g: (g.set_input(id, name, value), {"updated": id})[1])


@action(G)
def set_field(ctx: Ctx, id: str, name: str, value: str, sprite: str | None = None, project: str | None = None) -> dict:
    """Change a dropdown/variable/list/broadcast field, e.g. name='EFFECT' value='ghost'. Values are checked against the allowed options."""
    return graph_edit(ctx, project, sprite, f"set field {name}", lambda g: (g.set_field(id, name, value), {"updated": id})[1])


@action(G)
def validate(ctx: Ctx, sprite: str | None = None, project: str | None = None) -> dict:
    """Check a sprite's blocks against Scratch's block definitions: shapes, inputs, field values, stack rules."""
    g, name = graph_read(ctx, project, sprite)
    problems = g.validate()
    hard = [p for p in problems if "never runs on its own" not in p]
    soft = [p for p in problems if "never runs on its own" in p]
    return {"sprite": name, "ok": not hard, "problems": hard, "notes": soft}


@action(G)
def add_comment(ctx: Ctx, text: str, block_id: str | None = None, sprite: str | None = None, project: str | None = None,
                x: float = 0, y: float = 0, width: int = 200, height: int = 200, minimized: bool = False) -> dict:
    """Add a comment - attached to a block (block_id) or free-floating at (x, y) on the workspace."""
    return graph_edit(ctx, project, sprite, "add comment", lambda g: {"comment_id": g.add_comment(
        text, block=block_id, x=x, y=y, width=width, height=height, minimized=minimized)})


@action(G)
def edit_comment(ctx: Ctx, comment_id: str, text: str | None = None, minimized: bool | None = None,
                 sprite: str | None = None, project: str | None = None, x: float | None = None, y: float | None = None,
                 width: int | None = None, height: int | None = None) -> dict:
    """Change a comment's text, size, position or minimized state."""
    def fn(g: Graph):
        g.edit_comment(comment_id, text=text, minimized=minimized, x=x, y=y, width=width, height=height)
        return {"updated": comment_id}

    return graph_edit(ctx, project, sprite, "edit comment", fn)


@action(G)
def delete_comment(ctx: Ctx, comment_id: str, sprite: str | None = None, project: str | None = None) -> dict:
    """Delete a comment."""
    return graph_edit(ctx, project, sprite, "delete comment", lambda g: (g.delete_comment(comment_id), {"deleted": comment_id})[1])


@action(G)
def list_comments(ctx: Ctx, sprite: str | None = None, project: str | None = None) -> dict:
    """List a sprite's comments (id, text, attached block)."""
    g, name = graph_read(ctx, project, sprite)
    return {"sprite": name, "comments": [{"id": k, **v} for k, v in (g.target.get("comments") or {}).items()]}
