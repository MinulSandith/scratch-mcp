"""A single lazily-started headless Chromium (via Playwright) shared by rasterizing and the runtime."""

from __future__ import annotations

import base64
import glob
import os
from typing import Any

from ..workspace import WorkspaceError

INSTALL_HELP = (
    "This feature needs a headless browser. Install it once with:\n"
    "    pip install 'scratch-mcp[runtime]'   (or: pip install playwright)\n"
    "    playwright install chromium\n"
    "or point SCRATCH_MCP_CHROMIUM at a Chrome/Chromium executable."
)

def launch_args() -> list[str]:
    args = ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"]
    # Chromium refuses to start its sandbox as root (typical in containers); otherwise keep the sandbox on.
    if (hasattr(os, "geteuid") and os.geteuid() == 0) or os.environ.get("SCRATCH_MCP_NO_SANDBOX") == "1":
        args.append("--no-sandbox")
    return args




def find_chromium() -> str | None:
    env = os.environ.get("SCRATCH_MCP_CHROMIUM")
    if env and os.path.exists(env):
        return env
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), os.path.expanduser("~/.cache/ms-playwright"), "/opt/pw-browsers"]
    for root in filter(None, roots):
        for pattern in ("chromium-*/chrome-linux*/chrome", "chromium-*/chrome-win/chrome.exe", "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"):
            hits = sorted(glob.glob(os.path.join(root, pattern)))
            if hits:
                return hits[-1]
    return None


class BrowserService:
    def __init__(self) -> None:
        self._pw: Any = None
        self._browser: Any = None
        self.blocked: list[str] = []  # network requests the sandbox refused (for diagnostics)

    async def browser(self):
        if self._browser is not None and self._browser.is_connected():
            return self._browser
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise WorkspaceError("The 'playwright' package is not installed.\n" + INSTALL_HELP) from exc
        if self._pw is None:
            self._pw = await async_playwright().start()
        errors = []
        for exe in (None, find_chromium()):  # playwright's own browser first, then any Chromium we can find
            try:
                kwargs: dict[str, Any] = {"args": launch_args()}
                if exe:
                    kwargs["executable_path"] = exe
                self._browser = await self._pw.chromium.launch(**kwargs)
                return self._browser
            except Exception as exc:  # noqa: BLE001 - report all launch failures together
                errors.append(f"{exe or 'default'}: {str(exc).splitlines()[0]}")
        raise WorkspaceError("Could not start Chromium (" + "; ".join(errors) + ").\n" + INSTALL_HELP)

    async def new_page(self, width: int = 480, height: int = 360, *, lock_network: bool = True, **kw):
        """A fresh page. By default every http(s) request is blocked: a project being run can't phone home, and a
        malicious one can't load code. Set SCRATCH_MCP_ALLOW_NETWORK=1 to let text-to-speech/translate reach Scratch."""
        b = await self.browser()
        page = await b.new_page(viewport={"width": width, "height": height}, **kw)
        if lock_network and os.environ.get("SCRATCH_MCP_ALLOW_NETWORK") != "1":
            async def gate(route):
                if route.request.url.startswith(("file:", "data:", "blob:", "about:")):
                    await route.continue_()
                else:
                    self.blocked.append(route.request.url[:200])
                    await route.abort()

            await page.route("**/*", gate)
        return page

    async def rasterize_svg(self, svg: str, width: int, height: int, scale: float = 1.0, background: str | None = None) -> bytes:
        """Render SVG text to PNG bytes (transparent background unless given)."""
        b = await self.browser()
        ctx = await b.new_context(viewport={"width": max(1, int(width)), "height": max(1, int(height))}, device_scale_factor=scale)
        try:
            page = await ctx.new_page()
            uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode()
            bg = background or "transparent"
            await page.set_content(f'<html><body style="margin:0;background:{bg}"><img id="i" src="{uri}" '
                                   f'style="display:block;width:{int(width)}px;height:{int(height)}px"></body></html>')
            await page.wait_for_function("document.getElementById('i').complete")
            return await page.locator("#i").screenshot(omit_background=background is None)
        finally:
            await ctx.close()

    async def diff_images(self, png_a: bytes, png_b: bytes, threshold: int = 24) -> tuple[dict, bytes]:
        """Compare two PNGs of the same size. Returns (stats, diff image: changed pixels in red over the faded second image)."""
        b = await self.browser()
        page = await b.new_page()
        try:
            js = """async ([a, b, thr]) => {
              const load = src => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
              const A = await load('data:image/png;base64,' + a), B = await load('data:image/png;base64,' + b);
              if (A.width !== B.width || A.height !== B.height) return {error: `size differs: ${A.width}x${A.height} vs ${B.width}x${B.height}`};
              const w = A.width, h = A.height;
              const get = img => { const c = document.createElement('canvas'); c.width = w; c.height = h;
                const x = c.getContext('2d', {willReadFrequently: true}); x.drawImage(img, 0, 0); return x.getImageData(0, 0, w, h); };
              const da = get(A), db = get(B);
              const out = document.createElement('canvas'); out.width = w; out.height = h;
              const ox = out.getContext('2d'); const od = ox.createImageData(w, h);
              let changed = 0, minx = w, miny = h, maxx = -1, maxy = -1;
              for (let i = 0; i < da.data.length; i += 4) {
                const d = Math.abs(da.data[i] - db.data[i]) + Math.abs(da.data[i+1] - db.data[i+1]) + Math.abs(da.data[i+2] - db.data[i+2]);
                const px = (i / 4) % w, py = Math.floor(i / 4 / w);
                if (d > thr) { changed++; od.data[i] = 255; od.data[i+1] = 0; od.data[i+2] = 0; od.data[i+3] = 255;
                  if (px < minx) minx = px; if (px > maxx) maxx = px; if (py < miny) miny = py; if (py > maxy) maxy = py; }
                else { od.data[i] = db.data[i]; od.data[i+1] = db.data[i+1]; od.data[i+2] = db.data[i+2]; od.data[i+3] = 70; }
              }
              ox.putImageData(od, 0, 0);
              return {width: w, height: h, changed, pct: +(100 * changed / (w * h)).toFixed(3),
                      bbox: changed ? {x: minx, y: miny, width: maxx - minx + 1, height: maxy - miny + 1} : null,
                      png: out.toDataURL('image/png').split(',')[1]};
            }"""
            r = await page.evaluate(js, [base64.b64encode(png_a).decode(), base64.b64encode(png_b).decode(), threshold])
        finally:
            await page.close()
        if "error" in r:
            raise WorkspaceError("Can't compare: " + r["error"])
        png = base64.b64decode(r.pop("png"))
        return r, png

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None
