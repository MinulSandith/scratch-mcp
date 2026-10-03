#!/bin/bash
# Prepares a Claude Code *cloud* session so the "scratch" MCP server (.mcp.json) works:
# installs the package, downloads the Scratch engine once, makes sure the projects folder exists.
# Runs only in cloud sessions; idempotent (safe to run on resume).
set -euo pipefail
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi
cd "${CLAUDE_PROJECT_DIR:-$(pwd)}"
mkdir -p scratch-projects

# 1. the Python package (editable, with the headless-browser client)
if ! python3 -c "import scratch_mcp, playwright" >/dev/null 2>&1; then
  python3 -m pip install -q -e ".[runtime]"
fi

# 2. a Chromium for screenshots/running projects (cloud images usually ship one; install only if none is found)
if ! python3 -c "from scratch_mcp.runtime.browser import find_chromium; raise SystemExit(0 if find_chromium() else 1)"; then
  python3 -m playwright install chromium || echo "warning: could not install Chromium; run/screenshot features will be unavailable" >&2
fi

# 3. the Scratch engine (scratch-vm + scratch-render from npm), cached outside the repo
python3 -m scratch_mcp --root scratch-projects --setup-runtime >/dev/null \
  || echo "warning: Scratch runtime install failed (npm/network?). Editing tools still work; run runtime_manager setup to retry." >&2

echo "scratch-mcp ready: projects in $(pwd)/scratch-projects (commit them to keep them)"
