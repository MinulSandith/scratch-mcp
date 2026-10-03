"""Static check + verified .sb3 export + MP4 recording, all through the MCP tools (no client-side time limit)."""
import asyncio, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
async def main():
    env = dict(os.environ, SCRATCH_MCP_RUNTIME=os.path.expanduser("~/.cache/scratch-mcp/runtime"))
    p = StdioServerParameters(command=sys.executable, args=["-m", "scratch_mcp", "--root", ROOT], env=env)
    secs = json.load(open(os.path.join(HERE, "scenes.json")))["total_seconds"]
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            async def call(t, a, **k):
                res = await s.call_tool(t, {"action": a, "args": k})
                txt = "".join(c.text for c in res.content if c.type == "text")
                print(f"== {t}.{a}{' ERROR' if res.isError else ''}\n{txt[:900]}\n", flush=True)
            await call("project_manager", "open", name="One Quilt for Two", reload=True)
            await call("debug_manager", "check", include_info=False)
            await call("export_manager", "sb3", name="One Quilt for Two", overwrite=True)
            await call("export_manager", "video", seconds=secs + 0.5, name="One Quilt for Two", fps=30, with_audio=True, overwrite=True)
asyncio.run(main())
