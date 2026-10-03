"""Capture one real-VM screenshot per moment (via the MCP runtime tools) and tile them into a contact sheet."""
import asyncio, base64, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
TIMES = [float(x) for x in sys.argv[2:]]
OUT = sys.argv[1]
async def main():
    env = dict(os.environ, SCRATCH_MCP_RUNTIME=os.path.expanduser("~/.cache/scratch-mcp/runtime"))
    p = StdioServerParameters(command=sys.executable, args=["-m", "scratch_mcp", "--root", ROOT], env=env)
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            call = lambda t, a, **k: s.call_tool(t, {"action": a, "args": k})
            await call("project_manager", "open", name="One Quilt for Two", reload=True)
            await call("runtime_manager", "start", green_flag=True)
            now, files = 0.0, []
            for t in TIMES:
                await call("runtime_manager", "run", seconds=round(t - now, 3)); now = t
                res = await call("runtime_manager", "screenshot")
                img = next(c for c in res.content if c.type == "image")
                f = f"/tmp/shot_{int(t*10)}.png"; open(f, "wb").write(base64.b64decode(img.data)); files.append((t, f))
            err = await call("debug_manager", "errors")
            print("errors:", "".join(c.text for c in err.content if c.type == "text")[:300])
    from PIL import Image, ImageDraw
    cols = 4; W, H = 240, 180
    sheet = Image.new("RGB", (cols * W, ((len(files) + cols - 1) // cols) * (H + 14)), "white")
    for i, (t, f) in enumerate(files):
        im = Image.open(f).convert("RGB").resize((W, H)); x, y = (i % cols) * W, (i // cols) * (H + 14)
        sheet.paste(im, (x, y + 14)); ImageDraw.Draw(sheet).text((x + 4, y + 1), f"t={t}s", fill="black")
    sheet.save(OUT); print("saved", OUT)
asyncio.run(main())
