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

LAUNCH_ARGS = ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist", "--allow-file-access-from-files",
               "--autoplay-policy=no-user-gesture-required", "--no-sandbox"]


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
                kwargs: dict[str, Any] = {"args": LAUNCH_ARGS}
                if exe:
                    kwargs["executable_path"] = exe
                self._browser = await self._pw.chromium.launch(**kwargs)
                return self._browser
            except Exception as exc:  # noqa: BLE001 - report all launch failures together
                errors.append(f"{exe or 'default'}: {str(exc).splitlines()[0]}")
        raise WorkspaceError("Could not start Chromium (" + "; ".join(errors) + ").\n" + INSTALL_HELP)

    async def new_page(self, width: int = 480, height: int = 360, **kw):
        b = await self.browser()
        return await b.new_page(viewport={"width": width, "height": height}, **kw)

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

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None
