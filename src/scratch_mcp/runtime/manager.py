"""Runs a project in the real Scratch VM + renderer inside headless Chromium, with a deterministic virtual clock.

``RuntimeManager.setup`` installs the pinned scratch-vm / scratch-render bundles from npm into a cache folder
(needs node + npm + internet once). After that everything is offline.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from ..workspace import WorkspaceError

SCRATCH_VM_VERSION = "5.0.300"
SCRATCH_RENDER_VERSION = "2.2.84"
FRAME_MS = 1000 / 30
STEP_CHUNK = 150  # frames per browser call (5 simulated seconds) so a hung script is noticed quickly
CHUNK_TIMEOUT = 25.0  # real seconds a chunk may take before the script is declared stuck

CLOCK_INIT = """
(() => {
  const real = {date: Date.now.bind(Date), perf: performance.now.bind(performance),
                st: window.setTimeout.bind(window), ct: window.clearTimeout.bind(window)};
  const clock = window.__clock = {virtual: false, base: 0, ticks: 0, tickMs: 0.002, timers: [], seq: 1e9};
  const virt = () => clock.base + (clock.ticks++) * clock.tickMs;
  Date.now = () => clock.virtual ? virt() : real.date();
  performance.now = () => clock.virtual ? virt() : real.perf();
  // Scratch uses setTimeout for 'say ... for N secs' etc.: while simulating, timers run on the simulated clock
  window.setTimeout = (fn, ms, ...args) => {
    if (!clock.virtual) return real.st(fn, ms, ...args);
    const id = ++clock.seq; clock.timers.push({id, due: clock.base + (Number(ms) || 0), fn, args}); return id;
  };
  window.clearTimeout = id => { if (id >= 1e9) clock.timers = clock.timers.filter(t => t.id !== id); else real.ct(id); };
  clock.fireDue = () => {
    const due = clock.timers.filter(t => t.due <= clock.base).sort((a, b) => a.due - b.due);
    clock.timers = clock.timers.filter(t => t.due > clock.base);
    for (const t of due) { try { t.fn(...t.args); } catch (e) { console.error(e); } }
    return due.length;
  };
})();
"""


def runtime_dir() -> Path:
    base = os.environ.get("SCRATCH_MCP_RUNTIME") or os.path.join(os.path.expanduser("~"), ".cache", "scratch-mcp", "runtime")
    return Path(base)


def installed(d: Path | None = None) -> bool:
    d = d or runtime_dir()
    return (d / "scratch-vm.js").is_file() and (d / "scratch-render.js").is_file()


SETUP_HELP = ("The Scratch runtime is not installed. Run runtime_manager setup once (needs node/npm and internet), or "
              "set SCRATCH_MCP_RUNTIME to a folder containing scratch-vm.js and scratch-render.js.")


def sb3_bytes(project: dict[str, Any], assets: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", json.dumps(project, ensure_ascii=False, separators=(",", ":")))
        for n, d in assets.items():
            zf.writestr(n, d)
    return buf.getvalue()


@dataclass
class RuntimeSession:
    key: str
    page: Any
    console: list[dict[str, str]] = field(default_factory=list)
    dead: str | None = None  # reason, if the page had to be killed
    flagged: bool = False
    booted_hash: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


NOISE = ("GL Driver Message", "GPU stall", "willReadFrequently", "No audio engine present", "Canvas2D", "favicon",
         "cannot load sound", "Failed to load resource")


class RuntimeManager:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.sessions: dict[str, RuntimeSession] = {}

    # -- installation ------------------------------------------------------

    def status(self) -> dict[str, Any]:
        d = runtime_dir()
        from .browser import find_chromium

        try:
            import playwright  # noqa: F401
            pw = True
        except ImportError:
            pw = False
        return {"installed": installed(d), "runtime_dir": str(d), "scratch_vm": SCRATCH_VM_VERSION, "scratch_render": SCRATCH_RENDER_VERSION,
                "playwright": pw, "chromium": find_chromium(), "node": shutil.which("node"), "npm": shutil.which("npm"),
                "ffmpeg": shutil.which("ffmpeg")}

    async def setup(self, force: bool = False) -> dict[str, Any]:
        d = runtime_dir()
        if installed(d) and not force:
            return {"already_installed": True, **self.status()}
        npm = shutil.which("npm")
        if not npm:
            raise WorkspaceError("npm is needed once to download the Scratch runtime (install Node.js from nodejs.org), "
                                 "or set SCRATCH_MCP_RUNTIME to a folder that already has scratch-vm.js and scratch-render.js.")
        d.mkdir(parents=True, exist_ok=True)
        (d / "package.json").write_text(json.dumps({"name": "scratch-mcp-runtime", "private": True, "version": "0.0.0"}))
        cmd = [npm, "install", "--no-audit", "--no-fund", "--loglevel=error", "--fetch-retries=1", "--fetch-timeout=45000",
               f"scratch-vm@{SCRATCH_VM_VERSION}",
               f"scratch-render@{SCRATCH_RENDER_VERSION}"]
        proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(d), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=240)
        except asyncio.TimeoutError:
            proc.kill()
            raise WorkspaceError("npm install timed out after 4 minutes - is the internet (or your proxy) reachable from this server? "
                                 "MCP clients start servers with a minimal environment: put HTTPS_PROXY / SCRATCH_MCP_RUNTIME in the \"env\" "
                                 "section of the server config, or install once by hand and point SCRATCH_MCP_RUNTIME at the folder.") from None
        if proc.returncode != 0:
            raise WorkspaceError(f"npm install failed:\n{out.decode(errors='replace')[-800:]}")
        nm = d / "node_modules"
        shutil.copy(nm / "scratch-vm" / "dist" / "web" / "scratch-vm.js", d / "scratch-vm.js")
        shutil.copy(nm / "scratch-render" / "dist" / "web" / "scratch-render.js", d / "scratch-render.js")
        return {"installed_now": True, **self.status()}

    def _prepare_harness(self) -> Path:
        d = runtime_dir()
        if not installed(d):
            raise WorkspaceError(SETUP_HELP)
        html = resources.files("scratch_mcp.runtime").joinpath("harness.html").read_text(encoding="utf-8")
        (d / "harness.html").write_text(html, encoding="utf-8")
        return d / "harness.html"

    # -- sessions ----------------------------------------------------------

    async def start(self, key: str, project: dict[str, Any], assets: dict[str, bytes]) -> RuntimeSession:
        """(Re)load the in-memory project into a fresh page."""
        await self.stop(key)
        harness = self._prepare_harness()
        page = await self.ctx.browser.new_page(480, 360)
        rs = RuntimeSession(key, page)
        page.on("console", lambda m: rs.console.append({"type": m.type, "text": m.text[:500]}) if not any(n in m.text for n in NOISE) else None)
        page.on("pageerror", lambda e: rs.console.append({"type": "pageerror", "text": str(e)[:500]}))
        await page.add_init_script(CLOCK_INIT)
        await page.goto(harness.as_uri())
        await page.wait_for_function("typeof window.sm !== 'undefined'", timeout=30000)
        data = base64.b64encode(sb3_bytes(project, assets)).decode()
        try:
            names = await asyncio.wait_for(page.evaluate("b => window.sm.boot(b)", data), timeout=60)
        except Exception as exc:  # noqa: BLE001
            await page.close()
            raise WorkspaceError(f"The Scratch VM could not load this project: {str(exc).splitlines()[0]}") from exc
        self.sessions[key] = rs
        rs.booted_hash = str(hash(data))
        rs.targets = names  # type: ignore[attr-defined]
        return rs

    def get(self, key: str) -> RuntimeSession:
        rs = self.sessions.get(key)
        if rs is None:
            raise WorkspaceError("The project is not running in the runtime yet. Call runtime_manager start first.")
        if rs.dead:
            raise WorkspaceError(f"The runtime for this project was stopped: {rs.dead} Call runtime_manager start to reload it.")
        return rs

    async def call(self, key: str, fn: str, *args: Any, timeout: float = CHUNK_TIMEOUT) -> Any:
        rs = self.get(key)
        async with rs.lock:
            try:
                return await asyncio.wait_for(rs.page.evaluate(f"a => window.sm.{fn}(...a)", list(args)), timeout=timeout)
            except asyncio.TimeoutError:
                rs.dead = (f"a script kept the VM busy for more than {timeout:.0f} s of real time - it is probably an endless loop "
                           "that never yields (for example a loop inside a custom block set to 'run without screen refresh').")
                try:
                    await rs.page.close()
                except Exception:  # noqa: BLE001
                    pass
                raise WorkspaceError(f"Infinite loop detected: {rs.dead}") from None
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                first = msg.splitlines()[0] if msg else type(exc).__name__
                if "Error:" in first:
                    first = first.split("Error:", 1)[1].strip()
                raise WorkspaceError(first) from exc

    async def run_frames(self, key: str, frames: int, until: dict[str, Any] | None = None) -> dict[str, Any]:
        done, met, actual = 0, None, None
        while done < frames:
            n = min(STEP_CHUNK, frames - done)
            r = await self.call(key, "run", n, FRAME_MS, until)
            done += r["frames"]
            if until is not None and r["met"]:
                return {"frames": done, "met": True, "actual": r["actual"]}
            met, actual = r["met"], r["actual"]
        return {"frames": done, "met": met, "actual": actual}

    async def screenshot(self, key: str, scale: int = 1) -> bytes:
        rs = self.get(key)
        async with rs.lock:
            if scale != 1:
                await rs.page.evaluate("s => window.sm.setResolution(s)", scale)
            else:
                await rs.page.evaluate("() => window.sm.draw()")
            png = await rs.page.locator("#stage").screenshot(type="png")
            if scale != 1:
                await rs.page.evaluate("() => window.sm.setResolution(1)")
            return png

    async def stop(self, key: str) -> bool:
        rs = self.sessions.pop(key, None)
        if rs is None:
            return False
        try:
            await rs.page.close()
        except Exception:  # noqa: BLE001
            pass
        return True

    async def close_all(self) -> None:
        for k in list(self.sessions):
            await self.stop(k)
        await self.ctx.browser.close()

    def errors(self, key: str) -> list[dict[str, str]]:
        rs = self.sessions.get(key)
        if rs is None:
            return []
        return [c for c in rs.console if c["type"] in ("error", "pageerror")]
