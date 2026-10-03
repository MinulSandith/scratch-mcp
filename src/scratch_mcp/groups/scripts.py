"""script_manager: whole scripts - from text or JSON block trees; list, inspect, move, copy, delete, procedures."""

from __future__ import annotations

from typing import Any

from ..ctx import Ctx
from ..engine import EngineError, Graph
from ..registry import GROUP_DOCS, action
from ..render import ScriptRenderer
from ..textparse import ParseError, ScriptBuilder
from ..workspace import WorkspaceError
from ._common import graph_edit, graph_read

G = "script_manager"
GROUP_DOCS[G] = (
    "Create and manage whole scripts on a sprite or the Stage ('Stage'). Two ways to write blocks: "
    "(1) add_text - scratchblocks-style text, quick for common blocks; (2) add_tree - JSON block trees that can express "
    "ANY Scratch block (inputs, dropdown fields, nested reporters, C-block bodies, custom blocks, extensions). "
    "See block_manager catalog for opcodes and their inputs/fields. Tree example: "
    '{"opcode":"control_repeat","inputs":{"TIMES":10,"SUBSTACK":[{"opcode":"motion_movesteps","inputs":{"STEPS":5}}]}}. '
    "Input values: literal | {\"variable\":name} | {\"list\":name} | {\"menu\":value} | a nested block tree. "
    "Variables, lists and broadcast messages are created on first use."
)

TEXT_SYNTAX = """Text syntax: one block per line; (10) number, [text], (reporter block), <boolean block>, [option v], [#ff0000]. C blocks end with 'end'; 'else' splits if/else; blank line = new script.
Example: when flag clicked / forever / move (10) steps / if <touching (edge v)?> then / turn right (15) degrees / end / end"""


@action(G)
def add_text(ctx: Ctx, script: str, sprite: str | None = None, project: str | None = None,
             x: float | None = None, y: float | None = None) -> dict:
    """Add scripts written in scratchblocks-style text (see tool description for syntax). Blank line separates scripts.

    Args:
        script: the block text. One block per line; C blocks closed with 'end'.
        x: canvas x of the first script (default: below existing scripts).
        y: canvas y of the first script.
    """
    def fn(g: Graph):
        try:
            report = ScriptBuilder(g.project, g.target).add_scripts(script, x, y)
        except ParseError as exc:
            raise EngineError(f"{exc}\n\n{TEXT_SYNTAX}") from exc
        notes = []
        if report.created_variables:
            notes.append("created variables: " + ", ".join(report.created_variables))
        if report.created_lists:
            notes.append("created lists: " + ", ".join(report.created_lists))
        if report.created_broadcasts:
            notes.append("created broadcasts: " + ", ".join(report.created_broadcasts))
        if report.extensions_added:
            notes.append("enabled extensions: " + ", ".join(report.extensions_added))
        g.notes.extend(notes)
        r = ScriptRenderer(g.blocks)
        return {"scripts_added": len(report.top_ids), "script_ids": report.top_ids,
                "text": "\n\n".join("\n".join(r.render_stack(t)) for t in report.top_ids)}

    return graph_edit(ctx, project, sprite, "add scripts (text)", fn)


@action(G)
def add_tree(ctx: Ctx, scripts: list[dict[str, Any]], sprite: str | None = None, project: str | None = None,
             x: float | None = None, y: float | None = None) -> dict:
    """Add scripts as JSON block trees (any opcode). Each tree is one script: a hat block with a 'next' list.

    Args:
        scripts: list of trees, e.g. [{"opcode":"event_whenflagclicked","next":[{"opcode":"motion_movesteps","inputs":{"STEPS":10}}]}].
        x: canvas x of the first script.
        y: canvas y of the first script.
    """
    def fn(g: Graph):
        ids = g.add(scripts, x=x, y=y)
        r = ScriptRenderer(g.blocks)
        return {"scripts_added": len(ids), "script_ids": ids,
                "text": "\n\n".join("\n".join(r.render_stack(t)) for t in ids)}

    return graph_edit(ctx, project, sprite, "add scripts (tree)", fn)


@action(G)
def list_scripts(ctx: Ctx, sprite: str | None = None, project: str | None = None, include_text: bool = True) -> dict:
    """List a sprite's scripts (top-level stacks) with position, block count and readable text."""
    g, name = graph_read(ctx, project, sprite)
    r = ScriptRenderer(g.blocks)
    out = []
    for tid in sorted(g.top_levels(), key=lambda i: (g.blocks[i].get("y", 0), g.blocks[i].get("x", 0))):
        b = g.blocks[tid]
        item: dict[str, Any] = {"id": tid, "opcode": b["opcode"], "x": b.get("x"), "y": b.get("y"),
                                "blocks": len(g.subtree_ids(tid, include_next=True))}
        if include_text:
            item["text"] = "\n".join(r.render_stack(tid))
        out.append(item)
    return {"sprite": name, "scripts": out}


@action(G)
def get_script(ctx: Ctx, id: str, sprite: str | None = None, project: str | None = None, with_ids: bool = False) -> dict:
    """One script (or any block and what follows it) as a JSON tree (re-addable with add_tree) plus readable text.

    Args:
        id: id of the first block of the script (from list_scripts) or any block inside it.
        with_ids: include block ids in the tree.
    """
    g, name = graph_read(ctx, project, sprite)
    try:
        g.get(id)
        r = ScriptRenderer(g.blocks)
        return {"sprite": name, "tree": g.to_tree(id, ids=with_ids), "text": "\n".join(r.render_stack(id))}
    except EngineError as exc:
        raise WorkspaceError(str(exc)) from exc


@action(G)
def delete_script(ctx: Ctx, id: str, sprite: str | None = None, project: str | None = None) -> dict:
    """Delete a whole top-level script (every block in it)."""
    def fn(g: Graph):
        b = g.get(id)
        if not b.get("topLevel"):
            raise EngineError("That block is not the top of a script. Use block_manager delete for inner blocks.")
        return {"deleted_blocks": len(g.delete(id, mode="stack"))}

    return graph_edit(ctx, project, sprite, "delete script", fn)


@action(G)
def duplicate_script(ctx: Ctx, id: str, sprite: str | None = None, project: str | None = None,
                     to_sprite: str | None = None, x: float | None = None, y: float | None = None) -> dict:
    """Copy a script (all blocks get new ids) - within the sprite or to another sprite/Stage.

    Args:
        id: first block of the script.
        to_sprite: destination sprite (default: same sprite). Variables/lists/broadcasts and custom blocks it needs are created there.
    """
    session = ctx.session(project)
    result: dict[str, Any] = {}
    with ctx.store.edit(project, "duplicate script") as h:
        src = Graph(h.project, ctx.target(h.project, session, sprite))
        dest = src if not to_sprite else Graph(h.project, ctx.target(h.project, session, to_sprite))
        try:
            new_id = src.duplicate(id, include_next=True, x=x, y=y, into_graph=None if dest is src else dest)
        except EngineError as exc:
            raise WorkspaceError(f"Not applied. {exc}") from exc
        result = {"new_script_id": new_id, "to": "Stage" if dest.target.get("isStage") else dest.target["name"],
                  "notes": dest.notes}
    return result


@action(G)
def move_script(ctx: Ctx, id: str, x: float, y: float, sprite: str | None = None, project: str | None = None) -> dict:
    """Move a top-level script to canvas position (x, y)."""
    def fn(g: Graph):
        b = g.get(id)
        if not b.get("topLevel"):
            raise EngineError("Not a top-level script. Use block_manager move to relocate inner blocks.")
        b["x"], b["y"] = round(x), round(y)
        return {"moved": id}

    return graph_edit(ctx, project, sprite, "move script", fn)


@action(G)
def arrange(ctx: Ctx, sprite: str | None = None, project: str | None = None, columns: int = 1) -> dict:
    """Tidy all scripts of a sprite into a clean column layout (like 'Clean up blocks')."""
    return graph_edit(ctx, project, sprite, "arrange scripts", lambda g: {"scripts": g.arrange(columns)})


@action(G)
def define_procedure(ctx: Ctx, proccode: str, argument_names: list[str] | None = None, warp: bool = False,
                     sprite: str | None = None, project: str | None = None,
                     x: float | None = None, y: float | None = None) -> dict:
    """Create a custom block ('My Blocks') definition hat. Add its body with block_manager add (after=<definition id>).

    Args:
        proccode: label with %s (text/number input) and %b (boolean input) slots, e.g. "jump %s times %b".
        argument_names: one name per slot, in order, e.g. ["height", "fast"]. Use {"opcode":"argument_reporter_string_number","fields":{"VALUE":"height"}} in the body.
        warp: run without screen refresh.
    """
    def fn(g: Graph):
        did = g.define_procedure(proccode, argument_names or [], None, warp, x, y)
        return {"definition_id": did, "call_with": {"call": proccode, "args": ["..."]}}

    return graph_edit(ctx, project, sprite, f"define custom block {proccode}", fn)


@action(G)
def list_procedures(ctx: Ctx, sprite: str | None = None, project: str | None = None) -> dict:
    """List a sprite's custom blocks with their argument names and definition ids."""
    g, name = graph_read(ctx, project, sprite)
    return {"sprite": name, "procedures": [{"proccode": k, "definition_id": v["definition"], "arguments": v["argumentnames"],
                                            "warp": v["warp"]} for k, v in g.procedures().items()]}
