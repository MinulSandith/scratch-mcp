"""MCP server: sixteen tool groups that together operate Scratch the way a person using the editor would."""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
import traceback
import typing as t
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

from . import registry
from .ctx import Ctx
from .workspace import Workspace, WorkspaceError

log = logging.getLogger("scratch_mcp")

DEFAULT_ROOT = "~/ScratchProjects"
ENV_ROOT = "SCRATCH_PROJECTS_DIR"

# modules under scratch_mcp.groups; importing one registers its actions
GROUP_MODULES = ["project", "sprites", "scripts", "blocks", "variables", "costumes", "backdrops", "sounds", "assets",
                 "runtime", "inputs", "extensions", "inspection", "debug", "testing", "export", "online"]

INSTRUCTIONS = """\
You operate Scratch 3 projects (.sb3) in the user's Scratch folder, like a person using the Scratch editor - but through tools.
Each tool is a GROUP with many actions: call it with action=<name> and args={...}; action='help' returns exact schemas.

How to work:
1. Orient first: project_manager list/open (or create), then inspection_manager overview. Never edit blind.
2. Build with the managers: sprite_manager, costume_manager / backdrop_manager (draw vector art), sound_manager,
   variable_manager, script_manager / block_manager (any block via JSON trees; scratchblocks-style text for quick scripts).
3. LOOK at your work: runtime_manager (start, green_flag, run, screenshot, state) runs the REAL Scratch VM in simulated time;
   input_manager simulates keys/mouse/answers. You only 'verified visually' if you actually received a screenshot.
4. Test and debug: debug_manager diagnose, testing_manager quick / run_scenario; fix, then rerun_failed.
5. Deliver: export_manager sb3 (verified) / video / sprite.
Every edit is undoable (project_manager undo/redo) and every write to an existing file makes a timestamped backup in backups/.
The first time the runtime is used, runtime_manager setup installs scratch-vm (needs npm + internet) and a Chromium browser is required.
Be honest in reports: say what you verified (tool output) and what you did not.
"""


def register_groups(mcp: FastMCP, ctx: Ctx) -> None:
    for mod in GROUP_MODULES:
        importlib.import_module(f"scratch_mcp.groups.{mod}")

    def make(group: str):
        async def tool(action: str, args: dict[str, Any] | None = None):
            try:
                result = await registry.dispatch(group, ctx, action, args)
            except WorkspaceError as exc:
                raise ToolError(str(exc)) from exc
            except ToolError:
                raise
            except Exception as exc:  # unexpected: report it, keep the server alive
                log.error("%s.%s failed:\n%s", group, action, traceback.format_exc())
                raise ToolError(f"Internal error in {group}.{action}: {type(exc).__name__}: {exc}") from exc
            return registry.to_content(result)

        names = tuple(registry.GROUPS[group]) + ("help",)
        tool.__name__ = group
        tool.__annotations__ = {
            "action": t.Annotated[t.Literal[names], Field(description="Which operation to run (listed in the tool description).")],
            "args": t.Annotated[t.Optional[dict], Field(description="Parameters for the action, as a JSON object.")],
            "return": list,
        }
        return tool

    for group in registry.GROUPS:
        mcp.add_tool(make(group), name=group, description=registry.describe_group(group))


def build_server(root: str | os.PathLike[str]) -> FastMCP:
    ctx = Ctx(root)
    mcp = FastMCP("scratch", instructions=INSTRUCTIONS + f"\nProjects folder: {ctx.ws.root}")
    register_groups(mcp, ctx)
    mcp._scratch_ctx = ctx  # type: ignore[attr-defined]  # for tests and clean shutdown
    return mcp


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Scratch 3 MCP server (stdio)")
    parser.add_argument("--root", default=os.environ.get(ENV_ROOT, DEFAULT_ROOT),
                        help=f"Folder with your .sb3 files (default: ${ENV_ROOT} or {DEFAULT_ROOT})")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(name)s: %(message)s")  # stdout is the MCP channel
    server = build_server(args.root)
    log.info("Serving Scratch projects from %s", Workspace(args.root).root)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
