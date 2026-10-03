"""The acceptance run: 'Robot's First Adventure' built, tested, exported and recorded purely through MCP calls."""

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import anyio
import pytest

from scratch_mcp.runtime.browser import find_chromium
from scratch_mcp.runtime.manager import installed, runtime_dir

try:
    import playwright  # noqa: F401
    HAVE = find_chromium() is not None
except ImportError:
    HAVE = False

pytestmark = pytest.mark.skipif(not (HAVE and shutil.which("ffmpeg")), reason="needs playwright + Chromium + ffmpeg")

SCRIPT = Path(__file__).parent.parent / "scripts" / "e2e_robots_first_adventure.py"


def test_robots_first_adventure(tmp_path):
    if not installed(runtime_dir()):
        pytest.skip("Scratch runtime not installed (run runtime_manager setup)")
    spec = importlib.util.spec_from_file_location("e2e", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["e2e"] = mod
    spec.loader.exec_module(mod)
    os.environ.setdefault("SCRATCH_MCP_RUNTIME", str(runtime_dir()))
    report = anyio.run(mod.main_async, tmp_path, 3)
    assert report["failed_calls"] == [], report["failed_calls"]
    assert all(report["tests"].values()), {k: v for k, v in report["tests"].items() if not v}
    assert report["dirty_before_save"] is True                      # unsaved changes were tracked while building
    assert report["export"]["ok"] and report["export"]["loads_in_scratch_vm"] is True
    assert report["reopened"]["validation_ok"]
    assert sorted(report["reopened"]["sprites"]) == ["Battery", "Fader", "Robo", "Zorp"]
    assert "city" in report["reopened"]["backdrops"] and "kitchen1" in report["reopened"]["backdrops"]
    v = report["video"]["verified"]
    assert (v["width"], v["height"]) == (480, 360) and v["audio_stream"] and abs(v["video_seconds"] - 3) < 0.2
    assert len(list(tmp_path.glob("shot-*.png"))) >= 5               # screenshots really arrived as images
    assert json.loads((tmp_path / "e2e_report.json").read_text())["total_calls"] == report["total_calls"]
