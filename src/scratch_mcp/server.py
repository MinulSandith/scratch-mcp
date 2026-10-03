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

from . import editing, sounds, stock_art
from .blocks import MENUS
from . import registry
from .ctx import Ctx
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

    # 7-13: assets and sprites ----------------------------------------------
    def _edit(self, project: str, fn) -> tuple[str, str]:
        """Load a project, apply ``fn(data, assets)`` to a copy, validate, back up and save.

        Returns (message from fn, backup note)."""
        path = self.ws.resolve(project)
        sb3 = self.ws.load(path)
        data, assets = copy.deepcopy(sb3.project), dict(sb3.assets)
        try:
            message = fn(data, assets)
        except editing.EditError as exc:
            raise WorkspaceError(f"Not saved. {exc}") from exc
        result = validate_project(data, set(assets))
        if not result.ok:
            raise WorkspaceError(f"Not saved - the project would be invalid:\n{result.format()}")
        backup = self.ws.write(path, Sb3(data, assets), overwrite=True)
        note = f"Previous version backed up to {self.ws.display(backup)}." if backup else ""
        return message, note

    @staticmethod
    def _done(message: str, note: str) -> str:
        return f"{message}\n{note}".rstrip()

    def list_stock_assets(self) -> str:
        lines = ["Stock art for add_stock_art (original drawings, ready to animate):"]
        for name in stock_art.STOCK_NAMES:
            description, costumes, is_backdrop = stock_art.stock_art(name)
            kind = "backdrop (Stage)" if is_backdrop else "sprite"
            lines.append(f"- {name} [{kind}]: {description}")
        lines += ["", "Sound presets for add_sound(preset=...):"]
        lines += [f"- {name}: {desc}" for name, desc in sounds.PRESETS.items()]
        lines += ["", "You can also draw your own: add_costume takes any SVG, add_sound takes base64 WAV data."]
        return "\n".join(lines)

    def add_stock_art(
        self, project: str, art: str, sprite: str | None = None, text: str | None = None,
        x: float = 0, y: float = 0, size: float = 100, replace: bool = False,
    ) -> str:
        if art not in stock_art.STOCK_NAMES:
            raise WorkspaceError(f"Unknown stock art '{art}'. Choose from: {', '.join(stock_art.STOCK_NAMES)}.")
        _, costumes, is_backdrop = stock_art.stock_art(art, text)

        def fn(data, assets):
            created = False
            if is_backdrop:
                if sprite and sprite.strip().lower() != "stage":
                    raise editing.EditError(f"'{art}' is a backdrop; it can only go on the Stage.")
                target = editing.find_target(data, "Stage")
            else:
                name = sprite or art.capitalize()
                try:
                    target = editing.find_target(data, name)
                    if target.get("isStage"):
                        raise editing.EditError(f"'{art}' is a sprite costume set; it can't go on the Stage.")
                except editing.EditError as exc:
                    if "No sprite named" not in str(exc):
                        raise
                    target = editing.new_sprite(data, name, x, y, size)
                    created = True
            if replace:
                target["costumes"], target["currentCostume"] = [], 0
            for cname, svg, cx, cy in costumes:
                editing.add_costume(data, assets, target, cname, svg, (cx, cy))
            editing.prune_unused_assets(data, assets)
            names = ", ".join(c["name"] for c in target["costumes"])
            where = "the Stage" if target.get("isStage") else f"sprite '{target['name']}'"
            return (f"{'Created ' + where + ' and added' if created else 'Added'} the '{art}' art to "
                    f"{where}. Costumes now: {names}.")

        return self._done(*self._edit(project, fn))

    def add_sprite(
        self, project: str, name: str, svg: str | None = None, costume_name: str = "costume1",
        x: float = 0, y: float = 0, size: float = 100, direction: float = 90, visible: bool = True,
    ) -> str:
        def fn(data, assets):
            sprite = editing.new_sprite(data, name, x, y, size, direction, visible)
            editing.add_costume(data, assets, sprite, costume_name, svg or editing.BLANK_SVG)
            return (f"Added sprite '{sprite['name']}' at ({x}, {y}) with "
                    f"{'your costume' if svg else 'a blank costume'} '{costume_name}'. "
                    "Add more poses with add_costume.")

        return self._done(*self._edit(project, fn))

    def add_costume(
        self, project: str, sprite: str, name: str, svg: str,
        rotation_center_x: float | None = None, rotation_center_y: float | None = None,
    ) -> str:
        def fn(data, assets):
            target = editing.find_target(data, sprite)
            entry = editing.add_costume(data, assets, target, name, svg, (rotation_center_x, rotation_center_y))
            kind = "backdrop" if target.get("isStage") else "costume"
            return (f"Added {kind} '{entry['name']}' to {'the Stage' if target.get('isStage') else sprite} "
                    f"(rotation centre {entry['rotationCenterX']}, {entry['rotationCenterY']}). "
                    f"It now has {len(target['costumes'])} {kind}s.")

        return self._done(*self._edit(project, fn))

    def add_sound(
        self, project: str, sprite: str, name: str, preset: str | None = None,
        wav_base64: str | None = None, seconds: float | None = None, tempo: float | None = None,
    ) -> str:
        if bool(preset) == bool(wav_base64):
            raise WorkspaceError("Give exactly one of preset (see list_stock_assets) or wav_base64.")
        if preset and preset not in sounds.PRESETS:
            raise WorkspaceError(f"Unknown sound preset '{preset}'. Choose from: {', '.join(sounds.PRESETS)}.")

        def fn(data, assets):
            target = editing.find_target(data, sprite)
            wav = sounds.render_preset(preset, seconds, tempo) if preset else editing.decode_base64(wav_base64, "wav_base64")
            entry = editing.add_sound(assets, target, name, wav)
            length = entry["sampleCount"] / entry["rate"]
            return f"Added sound '{entry['name']}' ({length:.2f} s) to {'the Stage' if target.get('isStage') else sprite}."

        return self._done(*self._edit(project, fn))

    def update_sprite(
        self, project: str, sprite: str, x: float | None = None, y: float | None = None,
        size: float | None = None, direction: float | None = None, visible: bool | None = None,
        costume: str | None = None, new_name: str | None = None, rotation_style: str | None = None,
        bring_to_front: bool = False,
    ) -> str:
        def fn(data, assets):
            target = editing.find_target(data, sprite)
            changed = []
            if target.get("isStage"):
                if any(v is not None for v in (x, y, size, direction, visible, new_name, rotation_style)) or bring_to_front:
                    raise editing.EditError("The Stage only supports the 'costume' (backdrop) option.")
            for key, value in (("x", x), ("y", y), ("size", size), ("direction", direction), ("visible", visible)):
                if value is not None:
                    target[key] = value
                    changed.append(f"{key}={value}")
            if rotation_style is not None:
                if rotation_style not in ("all around", "left-right", "don't rotate"):
                    raise editing.EditError("rotation_style must be 'all around', 'left-right' or 'don't rotate'.")
                target["rotationStyle"] = rotation_style
                changed.append(f"rotationStyle={rotation_style}")
            if costume is not None:
                names = [c.get("name") for c in target.get("costumes") or []]
                if costume in names:
                    target["currentCostume"] = names.index(costume)
                elif costume.isdigit() and int(costume) < len(names):
                    target["currentCostume"] = int(costume)
                else:
                    raise editing.EditError(f"No costume '{costume}'. Available: {', '.join(names)}")
                changed.append(f"costume={names[target['currentCostume']]}")
            if bring_to_front:
                target["layerOrder"] = max(t.get("layerOrder", 0) for t in data["targets"]) + 1
                changed.append("moved to front")
            if new_name is not None and new_name != target["name"]:
                wanted = new_name.strip()
                if not wanted or wanted.lower() == "stage":
                    raise editing.EditError("Invalid new_name.")
                if any(t is not target and str(t.get("name", "")).lower() == wanted.lower() for t in data["targets"]):
                    raise editing.EditError(f"A sprite named '{wanted}' already exists.")
                old = target["name"]
                for t in data["targets"]:  # keep menus like "touching (Cat v)" pointing at the sprite
                    for block in (t.get("blocks") or {}).values():
                        if isinstance(block, dict) and block.get("opcode") in MENUS:
                            for fld in (block.get("fields") or {}).values():
                                if isinstance(fld, list) and fld and fld[0] == old:
                                    fld[0] = wanted
                target["name"] = wanted
                changed.append(f"renamed from '{old}'")
            if not changed:
                raise editing.EditError("Nothing to change: pass at least one property.")
            return f"Updated sprite '{target['name']}': " + ", ".join(changed) + "."

        return self._done(*self._edit(project, fn))

    def remove_asset(self, project: str, sprite: str, kind: str, name: str) -> str:
        if kind not in ("costume", "sound"):
            raise WorkspaceError("kind must be 'costume' or 'sound'.")

        def fn(data, assets):
            target = editing.find_target(data, sprite)
            key = "costumes" if kind == "costume" else "sounds"
            items = target.get(key) or []
            idx = next((i for i, a in enumerate(items) if a.get("name") == name), None)
            if idx is None:
                raise editing.EditError(f"No {kind} '{name}' on {sprite}. Available: {', '.join(a.get('name', '') for a in items)}")
            if kind == "costume" and len(items) == 1:
                raise editing.EditError("A sprite must keep at least one costume.")
            del items[idx]
            if kind == "costume":
                cur = target.get("currentCostume", 0)
                if cur >= idx and cur > 0:
                    target["currentCostume"] = cur - 1
            editing.prune_unused_assets(data, assets)
            return f"Removed {kind} '{name}' from {sprite}."

        return self._done(*self._edit(project, fn))

    def delete_sprite(self, project: str, sprite: str) -> str:
        def fn(data, assets):
            target = editing.find_target(data, sprite)
            if target.get("isStage"):
                raise editing.EditError("The Stage can't be deleted.")
            data["targets"].remove(target)
            editing.prune_unused_assets(data, assets)
            return f"Deleted sprite '{target['name']}' and its scripts."

        return self._done(*self._edit(project, fn))


GROUP_MODULES = ["project", "scripts", "blocks", "variables", "sprites", "costumes"]  # modules under scratch_mcp.groups, imported to register their actions


def register_groups(mcp: FastMCP, ctx: Ctx) -> None:
    import importlib
    import logging
    import traceback

    from .editing import EditError
    from .textparse import ParseError

    for mod in GROUP_MODULES:
        importlib.import_module(f"scratch_mcp.groups.{mod}")

    def make(group: str):
        async def tool(action: str, args: dict[str, Any] | None = None):
            try:
                result = await registry.dispatch(group, ctx, action, args)
            except (WorkspaceError, EditError, ParseError) as exc:
                raise ToolError(str(exc)) from exc
            except ToolError:
                raise
            except Exception as exc:  # unexpected: report it, keep the server alive
                logging.getLogger("scratch_mcp").error("%s.%s failed:\n%s", group, action, traceback.format_exc())
                raise ToolError(f"Internal error in {group}.{action}: {type(exc).__name__}: {exc}") from exc
            return registry.to_content(result)

        import typing as _t

        from pydantic import Field as _F

        names = tuple(registry.GROUPS[group]) + ("help",)
        tool.__name__ = group
        tool.__annotations__ = {
            "action": _t.Annotated[_t.Literal[names], _F(description="Which operation to run (see the tool description).")],
            "args": _t.Annotated[_t.Optional[dict], _F(description="Parameters for the action, as a JSON object.")],
            "return": list,
        }
        return tool

    for group in registry.GROUPS:
        mcp.add_tool(make(group), name=group, description=registry.describe_group(group))


def build_server(root: str | os.PathLike[str]) -> FastMCP:
    tools = ScratchTools(root)
    ctx = Ctx(root)
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

    @mcp.tool()
    def list_stock_assets() -> str:
        """List the ready-made art (robot, alien, cookie, kitchen backdrop, title card) and
        sound presets (effects and looping music) that add_stock_art / add_sound can add."""
        return run(tools.list_stock_assets)

    @mcp.tool()
    def add_stock_art(
        project: str, art: str, sprite: str | None = None, text: str | None = None,
        x: float = 0, y: float = 0, size: float = 100, replace: bool = False,
    ) -> str:
        """Add ready-made art to a project. art is one of: robot, alien, cookie, kitchen, title
        (see list_stock_assets). Sprite art creates the sprite if needed (named after the art unless
        sprite= is given) with all its poses as costumes; 'kitchen' adds two animated backdrops to the
        Stage; 'title' draws text=... as a title card. replace=true swaps out existing costumes."""
        return run(tools.add_stock_art, project, art, sprite, text, x, y, size, replace)

    @mcp.tool()
    def add_sprite(
        project: str, name: str, svg: str | None = None, costume_name: str = "costume1",
        x: float = 0, y: float = 0, size: float = 100, direction: float = 90, visible: bool = True,
    ) -> str:
        """Create a new sprite. svg is its first costume (plain SVG text with width/height or a
        viewBox; stage is 480x360, centre (0,0)); without svg it gets a blank costume."""
        return run(tools.add_sprite, project, name, svg, costume_name, x, y, size, direction, visible)

    @mcp.tool()
    def add_costume(
        project: str, sprite: str, name: str, svg: str,
        rotation_center_x: float | None = None, rotation_center_y: float | None = None,
    ) -> str:
        """Add a costume (or a backdrop, when sprite is "Stage") drawn as SVG text. The rotation
        centre defaults to the middle of the image; keep it consistent across a character's poses
        so it doesn't jump when the costume changes. Scripts, external links and fonts that Scratch
        can't load are rejected."""
        return run(tools.add_costume, project, sprite, name, svg, rotation_center_x, rotation_center_y)

    @mcp.tool()
    def add_sound(
        project: str, sprite: str, name: str, preset: str | None = None, wav_base64: str | None = None,
        seconds: float | None = None, tempo: float | None = None,
    ) -> str:
        """Add a sound to a sprite or the Stage. Either preset (pop, boing, bloop, squeak, alien_warble,
        crack, munch, chime, whoosh, sad_trombone, music_cheerful, music_calm, music_sneaky) or your
        own PCM WAV as wav_base64. For music_* presets, seconds sets the length (up to 120) and tempo
        the bpm - a track exactly as long as the animation ends with a final chord."""
        return run(tools.add_sound, project, sprite, name, preset, wav_base64, seconds, tempo)

    @mcp.tool()
    def update_sprite(
        project: str, sprite: str, x: float | None = None, y: float | None = None,
        size: float | None = None, direction: float | None = None, visible: bool | None = None,
        costume: str | None = None, new_name: str | None = None, rotation_style: str | None = None,
        bring_to_front: bool = False,
    ) -> str:
        """Change a sprite's starting state: position, size (%), direction, visibility, current
        costume (name or number), name, rotation style or layer. For the Stage only costume works."""
        return run(tools.update_sprite, project, sprite, x, y, size, direction, visible, costume,
                   new_name, rotation_style, bring_to_front)

    @mcp.tool()
    def remove_asset(project: str, sprite: str, kind: str, name: str) -> str:
        """Remove one costume/backdrop (kind="costume") or sound (kind="sound") by name."""
        return run(tools.remove_asset, project, sprite, kind, name)

    @mcp.tool()
    def delete_sprite(project: str, sprite: str) -> str:
        """Delete a sprite, its scripts and any costume/sound files nothing else uses
        (for example to drop the default cat from a new project)."""
        return run(tools.delete_sprite, project, sprite)

    register_groups(mcp, ctx)
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
