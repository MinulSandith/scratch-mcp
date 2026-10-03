"""Helpers shared by tool groups."""

from __future__ import annotations

from typing import Any, Callable

from ..ctx import Ctx
from ..engine import EngineError, Graph
from ..workspace import WorkspaceError


def graph_edit(ctx: Ctx, project: str | None, sprite: str | None, label: str,
               fn: Callable[[Graph], dict[str, Any] | None]) -> dict[str, Any]:
    """Run ``fn(graph)`` on a working copy of a sprite's blocks; validate and commit; return its result + notes."""
    session = ctx.session(project)
    result: dict[str, Any] = {}
    with ctx.store.edit(project, label) as h:
        target = ctx.target(h.project, session, sprite)
        graph = Graph(h.project, target)
        try:
            out = fn(graph)
        except EngineError as exc:
            raise WorkspaceError(f"Not applied. {exc}") from exc
        result = dict(out or {})
        if graph.notes:
            result["notes"] = graph.notes
        result["sprite"] = "Stage" if target.get("isStage") else target["name"]
    result["autosaved"] = session.autosave
    return result


def graph_read(ctx: Ctx, project: str | None, sprite: str | None) -> tuple[Graph, str]:
    session = ctx.session(project)
    import copy

    data = copy.deepcopy(session.project)
    target = ctx.target(data, session, sprite)
    return Graph(data, target), ("Stage" if target.get("isStage") else target["name"])
