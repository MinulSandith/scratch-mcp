"""MCP server exposing Scratch 3 project tools over stdio."""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from .render import ScriptRenderer, summarize_project
from .template import blank_project
from .textparse import ParseError, ScriptBuilder, find_target
from .validate import parse_project_json, validate_project
from .workspace import Sb3, Workspace, WorkspaceError

log = logging.getLogger("scratch_mcp")

DEFAULT_ROOT = "~/ScratchProjects"
ENV_ROOT = "SCRATCH_PROJECTS_DIR"

SCRIPT_SYNTAX = """\
Script text format (scratchblocks style, one block per line):
  (10)             number              [hello]         text
  (x position)     reporter block      <mouse down?>   boolean block
  (score)          variable            [edge v]        dropdown / menu (also (edge v))
  [#ff0000]        colour
C blocks (repeat, forever, if, repeat until) are closed with a line `end`;
`else` splits an if/else. A blank line starts a separate script. Hat blocks
(when flag clicked, when [space v] key pressed, when I receive [go v], ...)
must be the first line of a script. Custom blocks: `define jump (height) <fast>`
then call them as `jump (10) <mouse down?>`. Unknown variables, lists and
broadcast messages are created automatically (variables/lists for all sprites).
Comparison operators need spaces: <(x position) > (100)>.
Example:
  when flag clicked
  set [score v] to (0)
  forever
    move (10) steps
    if <touching (edge v)?> then
      turn right (180) degrees
      change [score v] by (1)
    end
  end
"""


class ScratchTools:
    """The tool implementations, independent of MCP so they are easy to test."""

    def __init__(self, root: str | os.PathLike[str]):
        self.ws = Workspace(root)

    # 1 ---------------------------------------------------------------------
    def list_projects(self) -> str:
        projects = self.ws.list_projects()
        if not projects:
            return f"No .sb3 projects in {self.ws.root} yet. Use create_project to make one."
        lines = [f"{len(projects)} project(s) in {self.ws.root}:"]
        for path in projects:
            stat = path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"- {self.ws.display(path)}  ({stat.st_size / 1024:.1f} KB, modified {modified})")
        return "\n".join(lines)

    # 2 ---------------------------------------------------------------------
    def read_project(self, project: str) -> str:
        path = self.ws.resolve(project)
        sb3 = self.ws.load(path)
        return summarize_project(self.ws.display(path), sb3.project)

    # 3 ---------------------------------------------------------------------
    def get_project_json(self, project: str, pretty: bool = True) -> str:
        path = self.ws.resolve(project)
        sb3 = self.ws.load(path)
        if pretty:
            return json.dumps(sb3.project, indent=2, ensure_ascii=False)
        return json.dumps(sb3.project, ensure_ascii=False, separators=(",", ":"))

    # 4 ---------------------------------------------------------------------
    def save_project_json(self, project: str, project_json: str | dict[str, Any]) -> str:
        path = self.ws.resolve(project)
        if isinstance(project_json, str):
            try:
                data = parse_project_json(project_json)
            except ValueError as exc:
                raise WorkspaceError(f"Not saved. {exc}") from exc
        elif isinstance(project_json, dict):
            data = copy.deepcopy(project_json)
        else:
            raise WorkspaceError("Not saved. project_json must be a JSON string or object.")
        old = self.ws.load(path)
        result = validate_project(data, set(old.assets))
        if not result.ok:
            raise WorkspaceError(f"Not saved - the project has problems:\n{result.format()}")
        backup = self.ws.write(path, Sb3(data, old.assets), overwrite=True)
        msg = [f"Saved {self.ws.display(path)}."]
        if backup:
            msg.append(f"Previous version backed up to {self.ws.display(backup)}.")
        if result.warnings:
            msg.append(result.format())
        return "\n".join(msg)

    # 5 ---------------------------------------------------------------------
    def create_project(self, name: str, sprite_name: str = "Sprite1") -> str:
        path = self.ws.resolve(name, must_exist=False)
        if path.exists():
            raise WorkspaceError(
                f"{self.ws.display(path)} already exists. Pick another name (existing projects are never overwritten)."
            )
        sprite_name = sprite_name.strip() or "Sprite1"
        if sprite_name.lower() == "stage":
            raise WorkspaceError("A sprite can't be called 'Stage'.")
        project, assets = blank_project(sprite_name)
        self.ws.write(path, Sb3(project, assets), overwrite=False)
        return (
            f"Created {self.ws.display(path)} with the Stage and one sprite '{sprite_name}' "
            "(the Scratch cat, 2 costumes, 'Meow' sound) and a global variable 'my variable'."
        )

    # 6 ---------------------------------------------------------------------
    def add_script(
        self, project: str, sprite: str, script: str, x: float | None = None, y: float | None = None
    ) -> str:
        path = self.ws.resolve(project)
        sb3 = self.ws.load(path)
        data = copy.deepcopy(sb3.project)
        try:
            target = find_target(data, sprite)
            builder = ScriptBuilder(data, target)
            report = builder.add_scripts(script, x, y)
        except ParseError as exc:
            raise WorkspaceError(f"Not saved. {exc}\n\n{SCRIPT_SYNTAX}") from exc
        result = validate_project(data, set(sb3.assets))
        if not result.ok:  # should not happen; refuse rather than write a broken file
            raise WorkspaceError(f"Not saved - generated blocks failed validation:\n{result.format()}")
        backup = self.ws.write(path, Sb3(data, sb3.assets), overwrite=True)

        renderer = ScriptRenderer(target["blocks"])
        label = "the Stage" if target.get("isStage") else f"sprite '{target['name']}'"
        n = len(report.top_ids)
        out = [f"Added {n} script{'s' if n != 1 else ''} to {label} in {self.ws.display(path)}:"]
        for top in report.top_ids:
            out.append("")
            out.extend(renderer.render_stack(top))
        out.append("")
        if report.created_variables:
            out.append("Created variables (for all sprites): " + ", ".join(report.created_variables))
        if report.created_lists:
            out.append("Created lists (for all sprites): " + ", ".join(report.created_lists))
        if report.created_broadcasts:
            out.append("Created broadcast messages: " + ", ".join(report.created_broadcasts))
        if report.extensions_added:
            out.append("Enabled extensions: " + ", ".join(report.extensions_added))
        if backup:
            out.append(f"Previous version backed up to {self.ws.display(backup)}.")
        return "\n".join(out).rstrip()


def build_server(root: str | os.PathLike[str]) -> FastMCP:
    tools = ScratchTools(root)
    mcp = FastMCP(
        "scratch",
        instructions=(
            "Read and edit Scratch 3 projects (.sb3) in the user's Scratch projects folder "
            f"({tools.ws.root}). Use read_project to see scripts as text, add_script to add "
            "scripts from text, and get_project_json/save_project_json for other edits. "
            "Every save backs up the previous version into the 'backups' folder.\n\n" + SCRIPT_SYNTAX
        ),
    )

    def run(fn, *args):
        try:
            return fn(*args)
        except WorkspaceError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    def list_projects() -> str:
        """List the Scratch (.sb3) projects in the Scratch projects folder."""
        return run(tools.list_projects)

    @mcp.tool()
    def read_project(project: str) -> str:
        """Summarise a project: sprites, costumes, sounds, variables, lists and
        every script as indented block text (e.g. 'when flag clicked' / 'move (10) steps').

        project: file name relative to the projects folder, e.g. "My Game.sb3" (".sb3" optional).
        """
        return run(tools.read_project, project)

    @mcp.tool()
    def get_project_json(project: str, pretty: bool = True) -> str:
        """Return the raw project.json of a project (for edits read_project/add_script can't do).
        Set pretty=false for compact output on big projects."""
        return run(tools.get_project_json, project, pretty)

    @mcp.tool()
    def save_project_json(project: str, project_json: str | dict[str, Any]) -> str:
        """Replace a project's project.json with an edited version.

        The JSON is validated first (valid JSON, unique block IDs, consistent
        parent/next/input links, known opcodes, costume/sound files present).
        Nothing is written if validation fails. The old .sb3 is backed up with a
        timestamp, then the project is re-zipped with its existing costumes and sounds.
        """
        return run(tools.save_project_json, project, project_json)

    @mcp.tool()
    def create_project(name: str, sprite_name: str = "Sprite1") -> str:
        """Create a new blank Scratch project with a Stage and one sprite wearing
        the default Scratch cat costume. Fails if the file already exists."""
        return run(tools.create_project, name, sprite_name)

    @mcp.tool(description=(
        "Add one or more scripts to a sprite (or the Stage, sprite=\"Stage\") from a text "
        "description of blocks. Block IDs and parent/next links are generated automatically; "
        "the project is validated and the old version backed up before saving. Optional x/y "
        "place the script on the canvas.\n\n" + SCRIPT_SYNTAX
    ))
    def add_script(project: str, sprite: str, script: str, x: float | None = None, y: float | None = None) -> str:
        return run(tools.add_script, project, sprite, script, x, y)

    return mcp


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Scratch 3 MCP server (stdio)")
    parser.add_argument(
        "--root",
        default=os.environ.get(ENV_ROOT, DEFAULT_ROOT),
        help=f"Folder with your .sb3 files (default: ${ENV_ROOT} or {DEFAULT_ROOT})",
    )
    args = parser.parse_args(argv)
    # stdout is the MCP channel - log to stderr only.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(name)s: %(message)s")
    server = build_server(args.root)
    log.info("Serving Scratch projects from %s", Workspace(args.root).root)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
