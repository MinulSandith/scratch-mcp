# Implementation audit and architecture changes

This is the Phase-1 audit of the original server (v0.1.0, commit `32c0fea` plus the asset tools added right after it)
and what was changed to reach v0.2.0. "Original" below always means that starting point.

## 1. What existed (v0.1.0)

| Item | Finding |
| --- | --- |
| Language / MCP | Python 3.10+, official MCP SDK `FastMCP`, stdio transport, `mcp` 1.x (2.x renames FastMCP, so it is pinned `<2`). |
| Tools (14) | `list_projects`, `read_project`, `get_project_json`, `save_project_json`, `create_project`, `add_script`, `list_stock_assets`, `add_stock_art`, `add_sprite`, `add_costume`, `add_sound`, `update_sprite`, `remove_asset`, `delete_sprite`. All flat, one operation each, loosely typed arguments. |
| Project model | Stateless: every call re-read the `.sb3` and (for edits) re-wrote it. No open-project concept, no undo/redo, no dirty tracking, no history. |
| SB3 import/export | Reading/writing the zip (`workspace.py`) was solid: path sandboxing, atomic write, timestamped backup before every overwrite. No import of `.sprite3`, no export other than "the project file itself". |
| Blocks | A **template-driven** text parser for ~190 block shapes (`blocks.SPECS`) plus a hand-written opcode list. Anything outside the templates (many menus/fields, hidden blocks, extension blocks, arbitrary nesting through JSON) could not be built except by editing raw JSON. No generic graph operations (move, connect, disconnect, duplicate, set one input). |
| Assets | Add costume (SVG text), add sound (preset or base64 WAV), stock art. No import of PNG/JPG, no editing of artwork or audio. |
| Runtime | **None.** Nothing could run a project, press a key, take a screenshot or read a variable. |
| Introspection | `read_project` text summary and raw JSON only. |
| Validation | Structural validator (unique ids, parent/next/input links, known opcodes, assets present). Good, kept. |
| Tests | 81 (sandboxing, backups, validation, parser round trips, a stdio session). |
| Dependencies | `mcp` only. |

### Existing capability vs. the target

| Capability | Status in v0.1.0 |
| --- | --- |
| Project create / save / backup | Partial (create, whole-file save; no open/save-as/duplicate/rename/delete/import, no undo) |
| Sprite management | Partial (create, update, delete) |
| Block programming | **Partial / limited** - template DSL only |
| Costume & vector editor | Missing (add whole SVG only) |
| Backdrop & stage | Missing (backdrops = costumes of the Stage, no properties) |
| Sound management | Partial (add preset/WAV) |
| Runtime execution, input simulation | Missing |
| Screenshots / visual feedback | Missing |
| Extensions | Partial (opcodes known; no discovery/management) |
| Debugging & testing | Missing |
| Online Scratch | Missing |
| Export (sprite, assets, screenshot, video) | Missing |

### Weaknesses found

* The template DSL hid a hard ceiling: a block with no template was unreachable (`SPECS` had to be written by hand per block).
* Per-call full read/write made multi-step work slow and made undo impossible.
* The block data was typed by hand; nothing guaranteed it matched Scratch's real definitions.
* Nothing could observe behaviour, so correctness of anything created was only structural.

No broken capabilities were found; the 81 original tests passed.

## 2. Architectural changes

1. **Session store (`store.py`)** - projects are opened into memory. Every edit goes through
   `ProjectStore.edit`, which works on a copy, validates, then commits with an undo snapshot. Autosave is on by default
   (each write to an existing file is preceded by a timestamped backup, and every response lists `backups_made`);
   turning it off gives real *unsaved-changes* tracking (`dirty`) until `save`. History: 100 steps per project.
2. **Action registry (`registry.py`)** - 18 tools, each a *group* with many `action`s (214 in total) instead of 200 flat
   tools. Each action has a strict pydantic model built from its type hints (unknown arguments are rejected), validated
   server-side with precise errors, plus a built-in `help` action that returns the exact JSON schema. Tool descriptions
   are generated from the same source, so docs cannot drift (`docs/TOOLS.md` is generated too).
3. **Schema generated from Scratch itself (`schema.json`, `tools/gen_schema.py`)** - 293 opcodes with inputs, shadow types,
   defaults, fields, dropdown values and shapes, built from `scratch-blocks` (block definitions), `scratch-gui`
   (`make-toolbox-xml.js`: shadow types/defaults) and `scratch-vm` (`getInfo()` of all 11 built-in extensions,
   dumped by `tools/dump_extensions.js`). A coverage check confirms it contains every opcode the validator knows.
4. **Generic block-graph engine (`engine.py`)** - builds any block from JSON trees and edits the graph with Scratch's real
   rules (hat/cap/reporter/boolean shapes, statement inputs, shadows kept under reporters, block ids, `parent`/`next`/
   `topLevel`, mutations, comments, custom blocks). The old text DSL remains, as one front-end among two.
5. **Vector editor (`vector.py`)** - an element-level SVG model (shapes, text, transforms with real matrices, groups,
   z-order, path nodes, bounding boxes, copy/paste, crop) behind `costume_manager`.
6. **Real runtime (`runtime/`)** - the unmodified `scratch-vm` + `scratch-render` bundles run in a headless Chromium
   (Playwright) with a **virtual clock**: simulated time at 30 fps, deterministic, much faster than real time. The virtual
   clock also covers `setTimeout` (used by `say ... for N secs`) and lets promise-based blocks resume between frames.
   Input is injected through the VM's own IO devices; screenshots are real renderer output (pen, effects, bubbles).
7. **Distribution of heavy dependencies** - `runtime_manager setup` installs the pinned VM/renderer from npm into a cache
   folder; Playwright/Chromium and ffmpeg are optional extras. Nothing in the original install changes (`pip install`).
8. **Run-time sandbox** - http(s) blocked in the browser by default, no file access, custom extension URLs stripped, Chromium sandbox kept unless root.
9. **Error model** - all user-facing errors derive from `WorkspaceError`; failed edits never leave partial changes.

### Preserved
Path sandboxing, atomic writes, backup-before-overwrite, the validator, the text block syntax (`script_manager add_text`),
stock art and sound presets. Every original tool maps to an action:

| Original tool | Now |
| --- | --- |
| `list_projects` / `read_project` | `project_manager list` / `summary` |
| `get_project_json` / `save_project_json` | `inspection_manager json` / `project_manager save_json` |
| `create_project` | `project_manager create` |
| `add_script` | `script_manager add_text` (and `add_tree`) |
| `add_stock_art` | `sprite_manager create(stock=...)`, `costume_manager add_stock`, `backdrop_manager add_stock` |
| `add_sprite`, `update_sprite`, `delete_sprite` | `sprite_manager create`, `set`, `delete` |
| `add_costume`, `remove_asset` | `costume_manager add_svg`, `delete`; `sound_manager delete` |
| `add_sound` | `sound_manager add_preset`, `add_tone`, `import_sound` |

## 3. Dependencies and compatibility

* Python 3.10, 3.11, 3.13 tested (same 154-test suite). `mcp>=1.2,<2`.
* Optional: `playwright` + a Chromium (screenshots, previews, running projects, video); `node`/`npm` once (runtime install);
  `ffmpeg` (video, mp3/ogg import).
* `scratch-vm` 5.0.300 and `scratch-render` 2.2.84 are pinned (the combination tested). The npm `scratch-storage` package has no
  browser build, so the harness contains a small in-page asset store.
* A project written by the original tools was loaded and re-saved by Scratch's own serializer (checked by hand during development: scripts render identically before and after); the automated suite instead loads every runtime test project in the real VM.
* Claude Desktop starts servers with a **minimal environment** - settings such as `SCRATCH_MCP_RUNTIME` or `HTTPS_PROXY`
  must go in the server's `env` block (found by the end-to-end run; see the README).
