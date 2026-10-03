# scratch-mcp: let an AI operate Scratch like a person does

A local [MCP](https://modelcontextprotocol.io) server that gives an AI agent (Claude Desktop, Claude Code, ...) the
abilities a person has in the Scratch editor: **create** projects, sprites, drawings, sounds and scripts, **run** the
project in the real Scratch engine, **press keys and click**, **look at the stage**, **test and debug**, and **export** a
finished `.sb3` (or a recorded MP4).

> "Create a 30-second cartoon about a robot and an alien fighting over a cookie" - the agent plans it, draws the
> characters and backdrops with the vector tools, adds sounds and music, writes the scripts, runs the project, looks
> at screenshots, fixes what is wrong, saves the project and exports it.

It works only inside one folder you choose, backs up before every overwrite, and every edit can be undone.

* **17 tools, 206 actions** (full list: [docs/TOOLS.md](docs/TOOLS.md)) - [audit and design notes](docs/AUDIT.md)
* **293 Scratch blocks** incl. 11 built-in extensions, taken from Scratch's own source (nothing hand-written)
* **Real Scratch VM + renderer** (headless Chromium), simulated time at 30 fps - deterministic and fast
* **149 automated tests** on Python 3.10, 3.11 and 3.13, including a full "build an adventure game through MCP" run

## Install

You need Python 3.10+ and Claude Desktop (or any MCP client).

```bash
git clone https://github.com/minulsandith/scratch-mcp.git
cd scratch-mcp
python3 -m venv .venv
.venv/bin/pip install -e ".[runtime]"        # adds Playwright for screenshots / running projects
.venv/bin/playwright install chromium         # the headless browser (or set SCRATCH_MCP_CHROMIUM)
mkdir -p ~/ScratchProjects
```

Windows: `py -m venv .venv`, `.venv\Scripts\pip install -e ".[runtime]"`, `.venv\Scripts\playwright install chromium`.

Optional but recommended: **Node.js** (one-time download of the Scratch engine; the server does it for you, see below) and
**ffmpeg** (video recording, importing mp3/ogg). Without the runtime pieces everything that edits projects still works;
only *run / screenshot / test / video / costume previews* need them.

### Claude Desktop configuration

Open **Settings -> Developer -> Edit Config** and add this to `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`). Use full paths.

**macOS / Linux**
```json
{
  "mcpServers": {
    "scratch": {
      "command": "/Users/YOUR_NAME/scratch-mcp/.venv/bin/scratch-mcp",
      "args": ["--root", "/Users/YOUR_NAME/ScratchProjects"],
      "env": {
        "SCRATCH_MCP_RUNTIME": "/Users/YOUR_NAME/.cache/scratch-mcp/runtime"
      }
    }
  }
}
```

**Windows** (double backslashes)
```json
{
  "mcpServers": {
    "scratch": {
      "command": "C:\\Users\\YOUR_NAME\\scratch-mcp\\.venv\\Scripts\\scratch-mcp.exe",
      "args": ["--root", "C:\\Users\\YOUR_NAME\\ScratchProjects"],
      "env": {
        "SCRATCH_MCP_RUNTIME": "C:\\Users\\YOUR_NAME\\.cache\\scratch-mcp\\runtime"
      }
    }
  }
}
```

Important: **MCP clients start servers with a minimal environment.** Anything the server needs from your shell must be
listed under `env`. Useful settings:

| Variable | Purpose |
| --- | --- |
| `SCRATCH_PROJECTS_DIR` | projects folder (alternative to `--root`; default `~/ScratchProjects`) |
| `SCRATCH_MCP_RUNTIME` | where the Scratch engine files live (default `~/.cache/scratch-mcp/runtime`) |
| `SCRATCH_MCP_CHROMIUM` | path of a Chrome/Chromium to use if Playwright's own browser isn't installed |
| `SCRATCH_MCP_CACHE` | cache for downloaded library assets |
| `SCRATCH_MCP_ALLOW_NETWORK` | `1` lets the run-time browser reach the internet (needed only for text-to-speech / translate); default: blocked |
| `SCRATCH_MCP_NO_SANDBOX` | `1` starts Chromium without its sandbox (done automatically when running as root, e.g. in containers) |
| `SCRATCH_MCP_BACKUPS` | how many backups to keep per project (default 100, `0` = keep all) |
| `HTTPS_PROXY`, `SSL_CERT_FILE` | if you are behind a proxy (for the one-time runtime install and library downloads) |

Quit Claude Desktop completely and reopen it. First message to try:

> *Use the scratch tools. Call runtime_manager setup, then create a project called "Hello" with a cat that moves when
> I press the arrow keys, run it, take a screenshot and test it.*

`runtime_manager setup` downloads the pinned `scratch-vm` / `scratch-render` from npm once (needs `npm` and internet).
Logs: macOS `~/Library/Logs/Claude/mcp-server-scratch.log`, Windows `%APPDATA%\Claude\logs\mcp-server-scratch.log`.
Sanity check from a terminal: `.venv/bin/scratch-mcp --root ~/ScratchProjects` prints `Serving Scratch projects from ...`.

## The tools

Each tool is a group; call it with `action` and `args`. `action="help"` returns the exact schema of any action.

| Tool | What it does |
| --- | --- |
| `project_manager` | create, open, save, save as, duplicate, rename, delete (to `backups/deleted`), import `.sb3`, metadata, unsaved-change tracking, undo/redo, reset, validate, raw `project.json` replace |
| `sprite_manager` | create (blank / SVG / image / stock / `.sprite3`), delete, duplicate, rename, select, position/size/direction/rotation style/visibility/draggable/layer/volume |
| `script_manager` | whole scripts from scratchblocks text **or JSON trees**, list/inspect/move/copy/delete/arrange scripts, custom blocks |
| `block_manager` | catalog of all opcodes, add/insert/delete/move/connect/disconnect/duplicate any block, set inputs and dropdowns, comments, rule checking |
| `variable_manager` | variables (global/local, cloud flag), lists, broadcasts, monitors; safe rename/delete |
| `costume_manager` | costumes **and backdrops**: import PNG/JPG/SVG, draw shapes/lines/curves/text, select + move/resize/rotate/flip, group, layers, fill/outline, path nodes, copy/paste, crop, centre, bitmap<->vector, preview, export |
| `backdrop_manager` | backdrop shortcuts + stage settings (volume, tempo, video, text-to-speech language) |
| `sound_manager` | import WAV (and mp3/ogg with ffmpeg), synthesize effects/music/tones, trim/cut/paste/reverse/volume/fade/echo/speed/robot, preview as audio |
| `asset_manager` | files inside the project, prune unused, **search and add from Scratch's library** |
| `runtime_manager` | run the project in the real VM: green flag, stop, run/step simulated time, state, variables, clones, run log, **screenshots**, snapshot + pixel diff |
| `input_manager` | keys (press/hold/release), mouse move/click/drag, click a sprite, answer prompts |
| `extension_manager` | list/describe/enable/disable extensions, verify they load, what each needs (hardware, internet) |
| `inspection_manager` | overview of everything, per-component views, block search, block graph, "who uses this", raw JSON |
| `debug_manager` | static check (broken references, dead broadcasts, orphan blocks, hang risks), scripts that never start, errors, hang check, `diagnose` |
| `testing_manager` | scenario tests (input -> expectation), ready-made `quick` tests, saved scenarios, `rerun_failed` |
| `export_manager` | verified `.sb3`, `.sprite3`, costume/sound files, stage PNG, **MP4 recording** (with sound effects mixed in) |
| `online_manager` | read-only: look up a shared project/user, download a shared project |

Typical loop for the agent: `inspection_manager overview` -> build with the managers -> `runtime_manager start` +
`screenshot` -> `debug_manager diagnose` / `testing_manager quick` -> fix -> `testing_manager rerun_failed` ->
`export_manager sb3` / `video`.

## Safety

* **One folder only.** Every path is resolved and checked; `..`, absolute paths elsewhere and symlinks out of the folder
  are rejected. Downloads and exports go to `exports/` inside it.
* **Backups.** Before an existing file is overwritten it is copied to `backups/<name>.<YYYYMMDD-HHMMSS>.sb3` (the newest
  100 are kept per project); each response says which backups it made. "Delete" moves a project to `backups/deleted/`.
* **Undo/redo** for every edit (100 steps per open project), including drawing and audio edits.
* **Validation before commit.** A change that would make the project invalid is refused and nothing is changed.
* SVG costumes are checked (no scripts, no external links). The browser that runs a project is locked down: every http(s)
  request is blocked by default, it cannot read your files, and `extensionURLs` in a project (custom JavaScript extensions)
  are stripped before the engine sees them (`test_runtime_refuses_outside_code_and_network`). Chromium's own sandbox stays on
  unless you run as root.
* Project files are exchanged with the Scratch app through the folder: if you edit a project in the Scratch app, reopen
  it (`project_manager open reload=true`); the server also notices that the file changed on disk.

## What is verified, and what is not

Status uses only these words: **Implemented** (works, tested), **Partial** (works with stated limits), **Unsupported**.
"Evidence" names real tests in `tests/` (149 pass; see "Development").

| Feature | Status | Evidence |
| --- | --- | --- |
| Project management (create/open/save/save as/duplicate/rename/delete/import/metadata/undo/redo/reset/dirty tracking) | Implemented | `test_groups_assets.py::test_project_lifecycle`, `::test_save_as_duplicate_rename_delete_import`, `test_tools.py`, `test_workspace.py` |
| Sprite management (create/delete/duplicate/rename/select/properties/layers/import `.sprite3`) | Implemented | `test_groups_assets.py::test_sprite_crud`, `::test_sprite_import_round_trip`, `::test_rename_sprite_updates_menus` |
| Clones (create / delete / inspect) | Implemented at run time only (clones are not saved in `.sb3`) | `test_runtime.py::test_clone_count_at_the_right_time`, `::test_broadcast_jump_click_ask_clones_sounds` |
| Block engine (any of 293 opcodes, nesting, insert/move/connect/disconnect/duplicate/inputs/fields/comments/custom blocks) | Implemented | `test_engine.py` (30 tests) + scripts executed in the real VM (`test_runtime.py`) |
| Text script syntax | Partial: covers ~190 common blocks; JSON trees cover all | `test_add_script.py` |
| Costume vector editor | Implemented | `test_groups_assets.py::test_vector_editor`, pen-line pixels in `test_runtime.py::test_pen_extension_draws_and_snapshot_compare` |
| Bitmap costumes | Partial: import/export/preview, vector<->bitmap conversion; **no pixel-painting tools** and no auto-tracing | `::test_preview_and_bitmap_round_trip` |
| Backdrops and stage | Implemented | `::test_backdrops_and_stage` |
| Sounds (import/synthesize/edit/preview) | Implemented; mp3/ogg need ffmpeg; **microphone recording Unsupported** | `::test_sound_management_and_editing`, `::test_import_mp3_via_ffmpeg` |
| Scratch library (search + add) | Partial: search verified live against the real catalogue; asset download verified only with a mocked network (this build environment cannot reach Scratch's asset CDN) | `::test_library_with_mock_network`; the live search was checked by hand during development (the automated suite needs no internet) |
| Runtime control (flag/stop/run/step/state/variables/threads/events) | Implemented in simulated time | `test_runtime.py` (19 tests) |
| Real-time execution and audible audio | **Unsupported** (sound plays are logged and mixed into recorded video, not played) | - |
| Input simulation (keys, mouse, drag, clicks, answers) | Implemented | `::test_keyboard_collision_variables_and_screenshot`, `::test_broadcast_jump_click_ask_clones_sounds` |
| Screenshots / visual feedback (returned as MCP image content) | Implemented; the code area (block editor) cannot be pictured - use `script_manager`/`inspection_manager` text | `::test_keyboard_collision_*`, `test_mcp_server.py` (real image block over stdio) |
| Before/after comparison | Implemented (pixel diff + diff image) | `::test_pen_extension_draws_and_snapshot_compare` |
| Extensions: discovery, enable/disable, load verification | Implemented | `::test_pen_extension_draws_and_snapshot_compare` |
| Extensions: execution | Pen (pixels verified) and Makey Makey (keyboard-triggered hat verified) fully; Music: blocks run with correct beat timing but **no sound output** (verified); Text-to-Speech/Translate need internet; Video Sensing has no camera; **micro:bit, EV3, BOOST, WeDo 2, Force & Acceleration: authoring only - no hardware connectivity**; **LEGO SPIKE is not a built-in Scratch extension - Unsupported** | `::test_pen_extension_draws_and_snapshot_compare`, `::test_music_and_makey_makey_extensions_run` |
| Debugging (static analysis, dead scripts, errors, hang watchdog) | Implemented; Scratch itself caps "run without screen refresh" loops, so real freezes are rare - the watchdog is verified by forcing a timeout | `::test_static_check_finds_seeded_bugs`, `::test_dead_scripts_and_diagnose`, `::test_watchdog_kills_a_stuck_runtime_and_it_can_be_restarted` |
| Automated testing (scenarios, quick tests, rerun failed) | Implemented | `::test_quick_tests_pass_and_fail_with_evidence`, `::test_scenario_save_fix_rerun`, `::test_ask_scenario_and_conditions` |
| Export (`.sb3` verified, `.sprite3`, assets, screenshot) | Implemented | `::test_exports_are_verified_and_video_is_real` |
| Video recording | Implemented (needs ffmpeg): 480x360 MP4, duration/frames checked with ffprobe, sound effects mixed; Music-extension notes and speech not included | same test; end-to-end 15 s run |
| Online Scratch | Partial: **read-only** (project/user info, download shared project); logging in, saving online, sharing, remixing, comments, cloud-variable sync are **Unsupported** on purpose (no official API; this server never handles Scratch passwords/cookies). Verified with a mocked network only | `::test_online_manager_with_mocked_network` |
| End-to-end "Robot's First Adventure" through MCP | Implemented | `tests/test_e2e_adventure.py`, `scripts/e2e_robots_first_adventure.py` |

### The end-to-end acceptance run

`python scripts/e2e_robots_first_adventure.py OUT_DIR` starts the real server over stdio and plays the agent: it draws a
night-city backdrop shape by shape, adds a robot, an alien, a battery and a fade sprite, animates walking and jumping,
adds music and sound effects, writes keyboard controls, dialogue, two scenes with a fade transition, a score variable,
a collectible and collision detection, runs the project, simulates input, takes screenshots, runs 10 tests, exports the
`.sb3`, reopens it, and records an MP4. Last run: **275 of 275 tool calls succeeded, 10 of 10 tests passed, the export
loaded in the real Scratch VM, the video was 480x360, 15.0 s, 450 frames with an audio stream** (28 s wall clock).
During development the same run failed 3 tests and exposed three runtime bugs (timers, blocking sounds, speech
bubbles) that are now fixed and have regression tests.

## Honest limits

* The tool descriptions are long (about 60 KB of schema text for 17 tools). Use `help` for exact schemas.
* Time is simulated, not real: `run(seconds=5)` means 5 simulated seconds.
* Drawing is vector-first. There is no freehand bitmap painting.
* Block editor visuals (colours, layout of the code area) are not rendered; scripts are returned as text/JSON.
* Hardware extensions cannot connect to devices; they can be authored and saved.
* Scratch-the-website features that need a login are intentionally out of scope.

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/playwright install chromium
SCRATCH_MCP_RUNTIME=~/.cache/scratch-mcp/runtime .venv/bin/pytest       # runtime tests install the engine if npm is available
```

Tests that need the browser/runtime/ffmpeg skip themselves when those are missing. Regenerate generated files:

```bash
python tools/gen_schema.py --blocks <scratch-blocks>/src/blocks --toolbox <scratch-gui>/src/lib/make-toolbox-xml.js \
       --ext ext_dump.json --out src/scratch_mcp/schema.json      # ext_dump.json: node tools/dump_extensions.js
python tools/gen_tool_docs.py > docs/TOOLS.md
```

Layout (`src/scratch_mcp/`): `server.py` (MCP wiring) · `registry.py` (action framework) · `store.py` (sessions, undo) ·
`workspace.py` (sandbox, files, backups) · `schema.py`+`schema.json` · `engine.py` (block graph) · `textparse.py` / `render.py`
(text syntax) · `vector.py` · `audio.py` / `sounds.py` · `library.py` · `analysis.py` · `groups/` (the 17 tools) ·
`runtime/` (`browser.py`, `manager.py`, `harness.html`).

## Credits and licences

The default cat, backdrop and sounds in `src/scratch_mcp/assets/` come from
[scratch-gui](https://github.com/scratchfoundation/scratch-gui) v4.1.7 (BSD 3-Clause, see `assets/LICENSE-scratch-gui.txt`).
The runtime executes the unmodified `scratch-vm` and `scratch-render` packages (BSD-3-Clause); block definitions come
from `scratch-blocks`, `scratch-gui` and `scratch-vm`. The Scratch library is fetched on demand from Scratch's public
servers and cached. Scratch and the Scratch Cat are trademarks of MIT; this project is not affiliated with or
endorsed by Scratch, the Scratch Foundation or MIT.
