"""The files that make the server usable in a Claude Code cloud session."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_mcp_json_launches_this_server():
    cfg = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]["scratch"]
    assert cfg["command"] == "python3" and cfg["args"][:2] == ["-m", "scratch_mcp"] and "--root" in cfg["args"]
    assert "SCRATCH_MCP_RUNTIME" in cfg["env"]


def test_session_hook_is_registered_executable_and_cloud_only():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    cmd = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    script = ROOT / ".claude" / "hooks" / "session-start.sh"
    assert "session-start.sh" in cmd and script.stat().st_mode & 0o111
    # outside a cloud session the hook must do nothing at all
    out = subprocess.run(["bash", str(script)], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"}, cwd=ROOT)
    assert out.returncode == 0 and out.stdout == "" and out.stderr == ""


def test_check_flag_reports_installation(tmp_path):
    out = subprocess.run([sys.executable, "-m", "scratch_mcp", "--root", str(tmp_path), "--check"], capture_output=True, text=True, timeout=60)
    status = json.loads(out.stdout)
    assert {"installed", "playwright", "chromium", "node", "ffmpeg", "runtime_dir"} <= set(status)
