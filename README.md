# scratch-mcp: a Scratch connector for Claude Desktop

A local [MCP](https://modelcontextprotocol.io) server that lets Claude read and edit
Scratch 3 projects (`.sb3` files) on your computer. It works only inside one folder
you choose, and it backs up a project before every change.

You can ask Claude things like:

- "What does the Cat sprite in *Maze Game* do?"
- "Make a new project called *Pong* and add a script so the ball bounces off the edges."
- "Add a score variable that goes up by 1 every time the sprite is clicked."
- "Rename the sprite *Sprite1* to *Hero* in *Maze Game*."

Open the `.sb3` files in the [Scratch app](https://scratch.mit.edu/download) or at
scratch.mit.edu (**File → Load from your computer**) to see and run the result.

## Tools

| Tool | What it does |
| --- | --- |
| `list_projects` | Lists the `.sb3` files in the folder, including subfolders but not `backups/`. |
| `read_project` | Gives a readable summary: sprites, costumes, sounds, variables, lists, broadcasts, and every script as indented block text. |
| `get_project_json` | Returns the raw `project.json`. |
| `save_project_json` | Takes an edited `project.json` and validates it: the JSON must be valid, block IDs unique, parent/next/input links consistent, every opcode known, and every costume or sound file present. If that passes, it backs up the old `.sb3` and writes the new one. If validation fails, nothing is written. |
| `create_project` | Creates a new project with a Stage and one sprite that has the default Scratch cat costumes. It never overwrites an existing file. |
| `add_script` | Adds scripts to a sprite or the Stage from a text description. Block IDs and links are generated, the result is validated, and the old file is backed up. |

## Setup

You need **Python 3.10 or newer** and **Claude Desktop**.

### 1. Install

macOS / Linux:

```bash
git clone https://github.com/minulsandith/scratch-mcp.git
cd scratch-mcp
python3 -m venv .venv
.venv/bin/pip install -e .
mkdir -p ~/ScratchProjects
```

Windows (PowerShell):

```powershell
git clone https://github.com/minulsandith/scratch-mcp.git
cd scratch-mcp
py -m venv .venv
.venv\Scripts\pip install -e .
mkdir $HOME\ScratchProjects
```

If the projects folder doesn't exist, the server creates it on startup.

Get the full path of the server program, because you need it in the next step:

```bash
echo "$(pwd)/.venv/bin/scratch-mcp"        # macOS / Linux
```
```powershell
"$(Get-Location)\.venv\Scripts\scratch-mcp.exe"   # Windows
```

### 2. Add it to `claude_desktop_config.json`

In Claude Desktop, open **Settings → Developer → Edit Config**. The file is here:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add this JSON, replacing `YOUR_NAME` and the paths with your own. Use full paths;
`~` is not expanded in `command`.

**macOS**

```json
{
  "mcpServers": {
    "scratch": {
      "command": "/Users/YOUR_NAME/scratch-mcp/.venv/bin/scratch-mcp",
      "args": ["--root", "/Users/YOUR_NAME/ScratchProjects"]
    }
  }
}
```

**Windows** (use double backslashes)

```json
{
  "mcpServers": {
    "scratch": {
      "command": "C:\\Users\\YOUR_NAME\\scratch-mcp\\.venv\\Scripts\\scratch-mcp.exe",
      "args": ["--root", "C:\\Users\\YOUR_NAME\\ScratchProjects"]
    }
  }
}
```

If the file already has an `"mcpServers"` section, add the `"scratch": { ... }` entry
to it instead of creating a second section.

You can also leave out `args` and set the folder with an environment variable
(`"env": {"SCRATCH_PROJECTS_DIR": "/Users/YOUR_NAME/ScratchProjects"}`). If neither is
set, the server uses `~/ScratchProjects`.

### 3. Restart Claude Desktop

Quit Claude Desktop completely (on macOS, use ⌘Q; closing the window is not enough)
and open it again. "scratch" should then be listed in the tools/connectors menu.
If it isn't, check the logs:

- macOS: `~/Library/Logs/Claude/mcp-server-scratch.log`
- Windows: `%APPDATA%\Claude\logs\mcp-server-scratch.log`

To check the install from a terminal, run
`.venv/bin/scratch-mcp --root ~/ScratchProjects`. It should print
`Serving Scratch projects from ...` and then wait. Press Ctrl+C to stop it.

## Safety

- **One folder only.** Every path is resolved and checked. Paths outside the projects
  folder are rejected, including `..`, absolute paths elsewhere, and symlinks that
  point outside it.
- **Backups.** Before any existing project is changed, the current file is copied to
  `backups/<name>.<YYYYMMDD-HHMMSS>.sb3` inside the projects folder. To restore a
  version, copy that file back. Backups are never overwritten, and the tools can't
  modify them.
- **Atomic writes.** The new `.sb3` is written to a temporary file first and then
  swapped in, so a crash can't leave you with a half-written project.
- **Validation.** Nothing is written if the project doesn't pass validation.

If a project is open in the Scratch app while Claude edits it, reload it in Scratch
(File → Load from your computer) to see the changes. If you save from Scratch
without reloading, Scratch overwrites Claude's changes, but they remain in the
backups folder.

## Script text format

`read_project` shows scripts in this format, and `add_script` accepts the same
format. It is the [scratchblocks](https://scratchblocks.github.io) style used on
the Scratch forums: one block per line.

| Write | Meaning |
| --- | --- |
| `(10)` | number |
| `[hello]` | text |
| `(x position)` | reporter block |
| `<mouse down?>` | boolean block |
| `(score)` | variable |
| `[edge v]` or `(edge v)` | dropdown / menu choice |
| `[#ff0000]` | colour |

```
when flag clicked
set [score v] to (0)
go to x: (0) y: (0)
forever
  move (10) steps
  if <touching (edge v)?> then
    turn right (pick random (90) to (180)) degrees
    change [score v] by (1)
  else
    say (join [Score: ] (score)) for (0.5) seconds
  end
end

when [space v] key pressed
broadcast (jump v)

define jump (height)
repeat (10)
  change y by ((height) / (10))
end
```

- C blocks (`repeat`, `forever`, `if … then`, `repeat until`) are closed with `end`.
  `else` splits an if/else. If you don't use `end` anywhere, indentation decides
  nesting instead.
- A blank line starts a new script. Hat blocks (`when …`, `define …`) must be the
  first line of a script.
- Custom blocks: `define name (number or text input) <boolean input>`. Add
  `// run without screen refresh` to the end of the define line to turn that
  option on. Call a custom block by writing its text with values filled in, e.g.
  `jump (50)`.
- If a variable, list, or broadcast message doesn't exist yet, it is created
  automatically. New variables and lists are "for all sprites", and the tool
  reports what it created. A sprite's own local variables are used when the
  names match.
- Comparison operators need spaces around them: `<(x position) > (100)>`.
- Text containing `]` is escaped with a backslash: `[a \] b]`.
- Supported blocks: all of Motion, Looks, Sound, Events, Control, Sensing,
  Operators, Variables, Lists, My Blocks, and the Pen, Music, Video Sensing,
  Text to Speech, and Translate extensions. Extensions are switched on
  automatically when you use their blocks.

## Limitations

- `add_script` can't create hardware-extension blocks (micro:bit, LEGO, Makey Makey,
  Force & Acceleration). `read_project` shows them in a generic form, and they're
  preserved when you edit other parts of the project.
- The tools don't add new costume or sound files. You can rename, reorder, or reuse
  existing ones by editing `project.json`. To add new artwork, use the Scratch editor.
- To add a new sprite, use `save_project_json` with a copy of an existing sprite.
  `save_project_json` keeps all the costume and sound files that are already in the
  `.sb3`.

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

The tests use `tests/fixtures/sample.sb3`, a project serialized by Scratch's own
scratch-vm (see `tests/fixtures/README.md`). They cover path sandboxing, backups,
validation, every tool, a render → `add_script` round trip of every script in the
sample, and a full session with the real server over stdio using the MCP client.

Code layout (`src/scratch_mcp/`):

| File | Purpose |
| --- | --- |
| `server.py` | FastMCP server and the six tools |
| `workspace.py` | folder sandbox, `.sb3` reading/writing, backups |
| `blocks.py` | opcode catalog and block text templates |
| `render.py` | project.json → readable text |
| `textparse.py` | text → blocks for `add_script` |
| `validate.py` | project.json validation |
| `template.py` | the blank project used by `create_project` |

## Credits

The default cat costumes, backdrop and sounds in `src/scratch_mcp/assets/` come from
[scratch-gui](https://github.com/scratchfoundation/scratch-gui) v4.1.7 (BSD 3-Clause;
see `assets/LICENSE-scratch-gui.txt`). Scratch and the Scratch Cat are trademarks of
MIT. This project is not affiliated with or endorsed by Scratch, the Scratch
Foundation, or MIT.
