"""Talk to the real server over stdio, the way Claude Desktop does."""

import json
import sys

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from scratch_mcp.runtime.browser import find_chromium

EXPECTED_TOOLS = {
    "project_manager", "sprite_manager", "script_manager", "block_manager", "variable_manager", "costume_manager",
    "backdrop_manager", "sound_manager", "asset_manager", "runtime_manager", "input_manager", "extension_manager",
    "inspection_manager", "debug_manager", "testing_manager", "export_manager", "online_manager",
}


def run_session(root, steps):
    params = StdioServerParameters(command=sys.executable, args=["-m", "scratch_mcp", "--root", str(root)])

    async def main():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await steps(session)

    return anyio.run(main)


def text_of(result):
    return "".join(c.text for c in result.content if c.type == "text")


def data_of(result):
    return json.loads(text_of(result))


def test_tools_schema_and_instructions(root):
    async def steps(session):
        return await session.list_tools(), session.get_server_capabilities()

    tools, _ = run_session(root, steps)
    by_name = {t.name: t for t in tools.tools}
    assert set(by_name) == EXPECTED_TOOLS
    schema = by_name["project_manager"].inputSchema
    assert schema["required"] == ["action"] and "create" in schema["properties"]["action"]["enum"] and "help" in schema["properties"]["action"]["enum"]
    assert "undo" in by_name["project_manager"].description and "Args" not in by_name["project_manager"].description
    assert "draw" in by_name["costume_manager"].description and "any block" in by_name["script_manager"].description.lower()
    assert all(len(t.description) < 9000 for t in tools.tools)


def test_stdio_session_end_to_end(root):
    async def steps(session):
        async def call(tool, action, /, **args):
            return await session.call_tool(tool, {"action": action, "args": args})

        out = {}
        out["list"] = await call("project_manager", "list")
        out["created"] = await call("project_manager", "create", name="From Claude", sprite_name="Hero")
        out["added"] = await call("script_manager", "add_text", script="when flag clicked\nforever\n  move (10) steps\n  if on edge, bounce\nend")
        out["tree"] = await call("script_manager", "add_tree", scripts=[{"opcode": "event_whenkeypressed", "fields": {"KEY_OPTION": "space"},
                                                                         "next": [{"opcode": "looks_say", "inputs": {"MESSAGE": "hi"}}]}])
        out["summary"] = await call("project_manager", "summary")
        out["undo"] = await call("project_manager", "undo")
        out["overview"] = await call("inspection_manager", "overview")
        out["denied"] = await call("project_manager", "open", name="../../etc/passwd")
        out["bad_action"] = await call("project_manager", "explode")
        out["bad_args"] = await call("project_manager", "create")
        out["bad_block"] = await call("block_manager", "add", blocks=[{"opcode": "motion_teleport"}])
        out["help"] = await call("sprite_manager", "help", action="set")
        out["art"] = await call("sprite_manager", "create", name="Robot", stock="robot")
        out["preview"] = await call("costume_manager", "preview", sprite="Robot", costume="happy")
        return out

    out = run_session(root, steps)
    assert not out["created"].isError and data_of(out["created"])["created"] == "From Claude.sb3"
    assert data_of(out["added"])["scripts_added"] == 1
    assert not out["tree"].isError
    assert "forever\n  move (10) steps\n  if on edge, bounce\nend" in text_of(out["summary"])
    assert data_of(out["undo"])["undone"] == ["add scripts (tree)"]
    assert data_of(out["overview"])["sprites"][0]["scripts"] == 1
    assert out["denied"].isError and "outside the Scratch projects folder" in text_of(out["denied"])
    assert out["bad_action"].isError and "Input should be" in text_of(out["bad_action"]) and "explode" in text_of(out["bad_action"])
    assert out["bad_args"].isError and "Invalid args" in text_of(out["bad_args"])
    assert out["bad_block"].isError and "Unknown opcode" in text_of(out["bad_block"])
    assert "rotation_style" in text_of(out["help"])
    assert not out["art"].isError
    assert len(list((root / "backups").glob("From Claude.*.sb3"))) >= 2
    if find_chromium() is not None:
        try:
            import playwright  # noqa: F401
        except ImportError:
            pytest.skip("playwright missing")
        images = [c for c in out["preview"].content if c.type == "image"]
        assert images and images[0].mimeType == "image/png" and len(images[0].data) > 1000   # a real MCP image block
