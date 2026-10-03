"""Talk to the real server over stdio, the way Claude Desktop does."""

import json
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = {
    "list_projects", "read_project", "get_project_json",
    "save_project_json", "create_project", "add_script",
    "list_stock_assets", "add_stock_art", "add_sprite", "add_costume", "add_sound",
    "update_sprite", "remove_asset", "delete_sprite",
}


def run_session(root, steps):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "scratch_mcp", "--root", str(root)]
    )

    async def main():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await steps(session)

    return anyio.run(main)


def text_of(result):
    return "".join(c.text for c in result.content if c.type == "text")


def test_stdio_server_end_to_end(root):
    async def steps(session):
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        add_desc = next(t for t in tools.tools if t.name == "add_script").description

        listing = await session.call_tool("list_projects", {})
        created = await session.call_tool("create_project", {"name": "From Claude"})
        added = await session.call_tool("add_script", {
            "project": "From Claude", "sprite": "Sprite1",
            "script": "when flag clicked\nforever\n  move (10) steps\n  if on edge, bounce\nend",
        })
        summary = await session.call_tool("read_project", {"project": "From Claude"})
        raw = await session.call_tool("get_project_json", {"project": "From Claude", "pretty": False})
        saved = await session.call_tool("save_project_json", {
            "project": "From Claude", "project_json": text_of(raw),
        })
        denied = await session.call_tool("read_project", {"project": "../../etc/passwd"})
        bad = await session.call_tool("add_script", {
            "project": "From Claude", "sprite": "Sprite1", "script": "fly to the moon",
        })
        return names, add_desc, listing, created, added, summary, raw, saved, denied, bad

    names, add_desc, listing, created, added, summary, raw, saved, denied, bad = run_session(root, steps)

    assert names == EXPECTED_TOOLS
    assert "Script text format" in add_desc
    assert "sample.sb3" in text_of(listing)
    assert not created.isError and "Created From Claude.sb3" in text_of(created)
    assert not added.isError and "Added 1 script" in text_of(added)
    assert "forever\n  move (10) steps\n  if on edge, bounce\nend" in text_of(summary)
    assert json.loads(text_of(raw))["targets"][1]["name"] == "Sprite1"
    assert not saved.isError and "backed up" in text_of(saved)
    assert denied.isError and "outside the Scratch projects folder" in text_of(denied)
    assert bad.isError and "Unknown block" in text_of(bad)
    assert len(list((root / "backups").glob("From Claude.*.sb3"))) == 2
