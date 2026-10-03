# Tool reference

Generated from the running server by `tools/gen_tool_docs.py` - do not edit by hand. Call a tool with `action=<name>` and `args={...}`; `action="help"` returns the exact JSON schema of any action. Parameters marked * are required.

## project_manager

Manage Scratch project files (.sb3) in the projects folder: create, open, save, save as, duplicate, rename, delete (moves to backups/deleted), import, inspect, undo/redo, unsaved-change tracking. One project is 'active' (the last opened/created); other tools default to it.

### project_manager.list

List .sb3 projects in the folder (subfolders included, backups excluded) with open/dirty state.

### project_manager.create

Create a new project (Stage + one sprite with the default cat) and make it active.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string | file name, e.g. "My Game" (".sb3" optional; subfolders allowed). |
| `sprite_name` | string | name of the first sprite. |
| `empty` | boolean | true = Stage only, no sprites (add sprites with sprite_manager). |

### project_manager.open

Open a project (load it into memory) and make it the active project.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string | project file name. |
| `reload` | boolean | true = discard in-memory state and re-read the file from disk. |

### project_manager.close

Close an open project. Refuses if it has unsaved changes unless discard=true.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `discard` | boolean |  |

### project_manager.save

Write the open project to disk (the previous file is backed up with a timestamp first).

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### project_manager.save_as

Save under a new name; the session then points at the new file.

| parameter | type | description |
| --- | --- | --- |
| `new_name`* | string | new project name. |
| `project` | string |  |
| `overwrite` | boolean | replace an existing file of that name (it is backed up first). |

### project_manager.duplicate

Copy a project to a new file (the active project does not change).

| parameter | type | description |
| --- | --- | --- |
| `new_name`* | string |  |
| `project` | string |  |

### project_manager.rename

Rename a project file (must have no unsaved changes).

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `new_name`* | string |  |

### project_manager.delete

'Delete' a project by moving it to backups/deleted/<name>.<timestamp>.sb3 so it can be restored.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |

### project_manager.import_sb3

Import an .sb3 as a new project (validated first).

| parameter | type | description |
| --- | --- | --- |
| `name`* | string | name for the imported project. |
| `source_path` | string | .sb3 file inside the projects folder to import (for example one saved from the Scratch app). |
| `data_base64` | string | alternatively the raw bytes of an .sb3 file, base64 encoded. |
| `overwrite` | boolean | replace an existing project of that name (backed up first). |

### project_manager.info

Project metadata, sprite list, counts, extensions, dirty/undo state.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### project_manager.status

All open projects with their unsaved-change flags.

### project_manager.summary

Readable text summary: sprites, costumes, sounds, variables, lists and every script as block text.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### project_manager.update_metadata

Merge string values into project.json 'meta' (keys: semver, vm, agent, platform...).

| parameter | type | description |
| --- | --- | --- |
| `meta`* | object | e.g. {"agent": "my tool"}. 'semver' must stay "3.0.0" for Scratch 3. |
| `project` | string |  |

### project_manager.set_autosave

autosave on (default): every edit is saved with a backup. Off: edits stay in memory until 'save'.

| parameter | type | description |
| --- | --- | --- |
| `enabled`* | boolean |  |
| `project` | string |  |

### project_manager.undo

Undo the last edit(s) (history holds the last 100 edits per open project).

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `steps` | integer |  |

### project_manager.redo

Redo edits that were undone.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `steps` | integer |  |

### project_manager.history

List undoable edits, newest last.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### project_manager.reset

Discard unsaved changes and history; reload the project from disk.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### project_manager.list_backups

List timestamped backups of a project (restore one with import_sb3 or by copying it back).

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### project_manager.validate

Structural validation: JSON shape, unique ids, links, opcodes, assets, variable references.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### project_manager.save_json

Replace the project's whole project.json with an edited version (validated first: valid JSON, unique block ids, consistent parent/next/input links, known opcodes, costume/sound files present). Nothing changes if validation fails. Costume/sound files already in the project are kept.

| parameter | type | description |
| --- | --- | --- |
| `project_json`* | string\|object | the full project.json as text or an object. |
| `project` | string |  |

### project_manager.restore_backup

Bring a backup back (see list_backups). Without as_name it replaces the project it was made from - the current file is backed up first, so the restore itself can be undone by restoring again.

| parameter | type | description |
| --- | --- | --- |
| `backup`* | string | path from list_backups, e.g. "backups/Game.20261003-063847.sb3". |
| `as_name` | string | restore as a new project with this name instead. |
| `overwrite` | boolean | required to replace an existing project when as_name names one. |

## sprite_manager

Create and manage sprites and their properties (position, size, direction, rotation style, visibility, draggable, layer, volume, current costume). 'select' sets the default sprite for other tools. Clone creation/inspection happens at run time: see runtime_manager (create_clone, list_clones). Costumes: costume_manager. Sounds: sound_manager. Scripts: script_manager. The Stage is not a sprite - use backdrop_manager.

### sprite_manager.list

List all sprites (back to front) with their properties.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### sprite_manager.get

All properties of one sprite.

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `project` | string |  |

### sprite_manager.create

Create a sprite. Its first costume comes from one of: svg (SVG text), stock ('robot', 'alien', 'cookie', 'title' - all poses), image_path (png/jpg/svg file inside the projects folder) or image_base64. With none of them it gets a blank costume.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string | sprite name (unique). |
| `svg` | string |  |
| `stock` | string | stock art name, see costume_manager stock_list. |
| `image_path` | string | image file inside the projects folder. |
| `image_base64` | string |  |
| `x` | number |  |
| `y` | number |  |
| `size` | number |  |
| `direction` | number |  |
| `visible` | boolean |  |
| `bitmap_resolution` | integer | 2 (default, image shown at half size) or 1 (native pixels) for png/jpg. |
| `project` | string |  |

### sprite_manager.delete

Delete a sprite, its scripts and any files nothing else uses.

| parameter | type | description |
| --- | --- | --- |
| `sprite`* | string |  |
| `project` | string |  |

### sprite_manager.duplicate

Duplicate a sprite with all costumes, sounds, scripts and local variables (new block ids). It is placed in front and selected.

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `new_name` | string |  |
| `project` | string |  |

### sprite_manager.rename

Rename a sprite (menus like 'touching (Cat v)' that name it are updated).

| parameter | type | description |
| --- | --- | --- |
| `new_name`* | string |  |
| `sprite` | string |  |
| `project` | string |  |

### sprite_manager.select

Select the sprite other tools use by default (no project change, not undoable).

| parameter | type | description |
| --- | --- | --- |
| `sprite`* | string |  |
| `project` | string |  |

### sprite_manager.set

Change sprite properties. Use visible=false/true to hide/show. costume = name or number.

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `x` | number |  |
| `y` | number |  |
| `size` | number | percent (100 = normal). |
| `direction` | number | degrees (90 = right, 0 = up). |
| `visible` | boolean |  |
| `draggable` | boolean |  |
| `rotation_style` | string | 'all around', 'left-right' or "don't rotate". |
| `volume` | number | 0-100. |
| `costume` | string |  |
| `project` | string |  |

### sprite_manager.layer

Change drawing order among sprites.

| parameter | type | description |
| --- | --- | --- |
| `mode`* | string | 'front', 'back', 'forward' or 'backward' (by `steps`). |
| `sprite` | string |  |
| `steps` | integer |  |
| `project` | string |  |

### sprite_manager.import_sprite

Import a .sprite3 file (exported from Scratch or by export_manager) into the project.

| parameter | type | description |
| --- | --- | --- |
| `source_path` | string | .sprite3 file inside the projects folder. |
| `data_base64` | string | alternatively its bytes, base64 encoded. |
| `name` | string |  |
| `project` | string |  |

## script_manager

Create and manage whole scripts on a sprite or the Stage ('Stage'). Two ways to write blocks: (1) add_text - scratchblocks-style text, quick for common blocks; (2) add_tree - JSON block trees that can express ANY Scratch block (inputs, dropdown fields, nested reporters, C-block bodies, custom blocks, extensions). See block_manager catalog for opcodes and their inputs/fields. Tree example: {"opcode":"control_repeat","inputs":{"TIMES":10,"SUBSTACK":[{"opcode":"motion_movesteps","inputs":{"STEPS":5}}]}}. Input values: literal | {"variable":name} | {"list":name} | {"menu":value} | a nested block tree. Variables, lists and broadcast messages are created on first use.

### script_manager.add_text

Add scripts written in scratchblocks-style text (see tool description for syntax). Blank line separates scripts.

| parameter | type | description |
| --- | --- | --- |
| `script`* | string | the block text. One block per line; C blocks closed with 'end'. |
| `sprite` | string |  |
| `project` | string |  |
| `x` | number | canvas x of the first script (default: below existing scripts). |
| `y` | number | canvas y of the first script. |

### script_manager.add_tree

Add scripts as JSON block trees (any opcode). Each tree is one script: a hat block with a 'next' list.

| parameter | type | description |
| --- | --- | --- |
| `scripts`* | [object] | list of trees, e.g. [{"opcode":"event_whenflagclicked","next":[{"opcode":"motion_movesteps","inputs":{"STEPS":10}}]}]. |
| `sprite` | string |  |
| `project` | string |  |
| `x` | number | canvas x of the first script. |
| `y` | number | canvas y of the first script. |

### script_manager.list_scripts

List a sprite's scripts (top-level stacks) with position, block count and readable text.

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `project` | string |  |
| `include_text` | boolean |  |

### script_manager.get_script

One script (or any block and what follows it) as a JSON tree (re-addable with add_tree) plus readable text.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string | id of the first block of the script (from list_scripts) or any block inside it. |
| `sprite` | string |  |
| `project` | string |  |
| `with_ids` | boolean | include block ids in the tree. |

### script_manager.delete_script

Delete a whole top-level script (every block in it).

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `sprite` | string |  |
| `project` | string |  |

### script_manager.duplicate_script

Copy a script (all blocks get new ids) - within the sprite or to another sprite/Stage.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string | first block of the script. |
| `sprite` | string |  |
| `project` | string |  |
| `to_sprite` | string | destination sprite (default: same sprite). Variables/lists/broadcasts and custom blocks it needs are created there. |
| `x` | number |  |
| `y` | number |  |

### script_manager.move_script

Move a top-level script to canvas position (x, y).

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `x`* | number |  |
| `y`* | number |  |
| `sprite` | string |  |
| `project` | string |  |

### script_manager.arrange

Tidy all scripts of a sprite into a clean column layout (like 'Clean up blocks').

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `project` | string |  |
| `columns` | integer |  |

### script_manager.define_procedure

Create a custom block ('My Blocks') definition hat. Add its body with block_manager add (after=<definition id>).

| parameter | type | description |
| --- | --- | --- |
| `proccode`* | string | label with %s (text/number input) and %b (boolean input) slots, e.g. "jump %s times %b". |
| `argument_names` | [string] | one name per slot, in order, e.g. ["height", "fast"]. Use {"opcode":"argument_reporter_string_number","fields":{"VALUE":"height"}} in the body. |
| `warp` | boolean | run without screen refresh. |
| `sprite` | string |  |
| `project` | string |  |
| `x` | number |  |
| `y` | number |  |

### script_manager.list_procedures

List a sprite's custom blocks with their argument names and definition ids.

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `project` | string |  |

## block_manager

Work with individual blocks (any of Scratch's 290+ opcodes, incl. extensions). Browse with 'catalog'/'describe'. Edit the block graph: add blocks into existing scripts (after / into a C block / into an input), delete, move, connect, disconnect, duplicate, change inputs and dropdown fields, add comments. Block ids come from script_manager list_scripts / get_script (with_ids) or from the ids returned by add actions. All placements are checked against Scratch's rules (hat blocks start scripts, cap blocks end them, boolean slots take boolean blocks).

### block_manager.catalog

List opcodes with their inputs (and shadow/menu types) and fields (dropdown options).

| parameter | type | description |
| --- | --- | --- |
| `category` | string | motion, looks, sound, events, control, sensing, operators, variables, lists, myblocks, or an extension id (pen, music, videoSensing, text2speech, translate, makeymakey, microbit, ev3, boost, wedo2, gdxfor). |
| `query` | string | substring of opcode or block text. |

### block_manager.describe

Full schema of one opcode: shape, inputs (shadow type, default, boolean/statement), fields (options), extension.

| parameter | type | description |
| --- | --- | --- |
| `opcode`* | string |  |

### block_manager.add

Create blocks from JSON trees and place them in the graph.

| parameter | type | description |
| --- | --- | --- |
| `blocks`* | [object] | block trees, e.g. [{"opcode":"motion_movesteps","inputs":{"STEPS":10}}]. |
| `sprite` | string |  |
| `project` | string |  |
| `after` | string | insert after this block id (blocks that followed move to the end of the inserted stack). |
| `into` | string | put the stack inside this C block id; 'input' = SUBSTACK (default) or SUBSTACK2 (else branch). |
| `input` | string | input name for 'into' / 'replace_input_of'. |
| `replace_input_of` | string | put one reporter/boolean block into this block id's value input named 'input'. |
| `x` | number | canvas position for a new free-standing script (when no placement is given). |
| `y` | number | canvas position for a new free-standing script. |

### block_manager.get

Detailed view of one block: opcode, raw inputs/fields, parent, next, shape, readable text.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `sprite` | string |  |
| `project` | string |  |

### block_manager.delete

Delete a block. Blocks nested inside its inputs go with it.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string | block id. |
| `mode` | string | 'stack' = this block and all blocks after it; 'single' = only this block (following blocks reconnect to the previous one). |
| `sprite` | string |  |
| `project` | string |  |

### block_manager.move

Move a block (with the blocks after it) to a new place: free canvas (x,y), after another block, into a C block, or into an input.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `sprite` | string |  |
| `project` | string |  |
| `x` | number |  |
| `y` | number |  |
| `after` | string |  |
| `into` | string |  |
| `input` | string |  |
| `replace_input_of` | string |  |
| `single` | boolean | move only this block; the blocks after it stay where they were. |

### block_manager.connect

Connect a (free) block/stack to another: below 'after', inside C block 'into' (+input), or into a value input.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `after` | string |  |
| `into` | string |  |
| `input` | string |  |
| `replace_input_of` | string |  |
| `sprite` | string |  |
| `project` | string |  |

### block_manager.disconnect

Pull a block (and the blocks after it) out of its script into a free-standing stack.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `sprite` | string |  |
| `project` | string |  |
| `x` | number |  |
| `y` | number |  |

### block_manager.duplicate

Duplicate a block (with its inner blocks; optionally the blocks after it) as a free-standing stack.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `include_next` | boolean |  |
| `sprite` | string |  |
| `project` | string |  |
| `x` | number |  |
| `y` | number |  |

### block_manager.set_input

Change a block input. value = literal | {"variable":n} | {"list":n} | {"menu":v} | nested block tree | list of trees (C-block body) | null (reset to default).

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `name`* | string |  |
| `value`* | Any |  |
| `sprite` | string |  |
| `project` | string |  |

### block_manager.set_field

Change a dropdown/variable/list/broadcast field, e.g. name='EFFECT' value='ghost'. Values are checked against the allowed options.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `name`* | string |  |
| `value`* | string |  |
| `sprite` | string |  |
| `project` | string |  |

### block_manager.validate

Check a sprite's blocks against Scratch's block definitions: shapes, inputs, field values, stack rules.

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `project` | string |  |

### block_manager.add_comment

Add a comment - attached to a block (block_id) or free-floating at (x, y) on the workspace.

| parameter | type | description |
| --- | --- | --- |
| `text`* | string |  |
| `block_id` | string |  |
| `sprite` | string |  |
| `project` | string |  |
| `x` | number |  |
| `y` | number |  |
| `width` | integer |  |
| `height` | integer |  |
| `minimized` | boolean |  |

### block_manager.edit_comment

Change a comment's text, size, position or minimized state.

| parameter | type | description |
| --- | --- | --- |
| `comment_id`* | string |  |
| `text` | string |  |
| `minimized` | boolean |  |
| `sprite` | string |  |
| `project` | string |  |
| `x` | number |  |
| `y` | number |  |
| `width` | integer |  |
| `height` | integer |  |

### block_manager.delete_comment

Delete a comment.

| parameter | type | description |
| --- | --- | --- |
| `comment_id`* | string |  |
| `sprite` | string |  |
| `project` | string |  |

### block_manager.list_comments

List a sprite's comments (id, text, attached block).

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `project` | string |  |

## variable_manager

Manage variables (global = Stage, or local to one sprite), lists, broadcast messages and on-screen monitors. Renaming updates every block that uses the variable; deleting refuses while blocks still use it unless force=true.

### variable_manager.list

All variables, lists and broadcast messages with scope, values and how many blocks use each.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### variable_manager.create_variable

Create a variable.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string | variable name (unique within its scope; a cloud variable's name is stored with the '☁ ' prefix). |
| `value` | string\|number\|integer | initial value. |
| `sprite` | string | omit for a global variable ('for all sprites'); give a sprite name for 'this sprite only'. |
| `cloud` | boolean | cloud variable (must be global; numbers only). Stored in the file; syncing needs the online Scratch site. |
| `project` | string |  |

### variable_manager.set_variable

Set a variable's stored (starting) value.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `value`* | string\|number\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### variable_manager.rename_variable

Rename a variable everywhere it is used.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `new_name`* | string |  |
| `sprite` | string |  |
| `project` | string |  |

### variable_manager.delete_variable

Delete a variable. Refuses while blocks use it unless force=true (those blocks then re-create it when run).

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `sprite` | string |  |
| `force` | boolean |  |
| `project` | string |  |

### variable_manager.create_list

Create a list (global unless sprite is given) with optional starting items.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `items` | [string\|number\|integer] |  |
| `sprite` | string |  |
| `project` | string |  |

### variable_manager.set_list

Replace a list's starting contents.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `items`* | [string\|number\|integer] |  |
| `sprite` | string |  |
| `project` | string |  |

### variable_manager.rename_list

Rename a list everywhere it is used.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `new_name`* | string |  |
| `sprite` | string |  |
| `project` | string |  |

### variable_manager.delete_list

Delete a list (refuses while blocks use it unless force=true).

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `sprite` | string |  |
| `force` | boolean |  |
| `project` | string |  |

### variable_manager.create_broadcast

Create a broadcast message (they are also created automatically when a block uses a new name).

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `project` | string |  |

### variable_manager.rename_broadcast

Rename a broadcast message everywhere (senders and receivers).

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `new_name`* | string |  |
| `project` | string |  |

### variable_manager.delete_broadcast

Delete an unused broadcast message (unused ones are also dropped by Scratch on save).

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `force` | boolean |  |
| `project` | string |  |

### variable_manager.set_monitor

Show/hide the stage monitor of a variable or list and choose its style.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string | variable or list name. |
| `visible` | boolean |  |
| `mode` | string | 'default' (name + value), 'large' (value only), 'slider', or 'list'. |
| `x` | integer |  |
| `y` | integer |  |
| `slider_min` | number |  |
| `slider_max` | number |  |
| `sprite` | string | sprite owning a local variable (omit for global). |
| `project` | string |  |

## costume_manager

Costumes of a sprite - or backdrops when sprite='Stage'. Manage them (add, import png/jpg/svg, duplicate, rename, reorder, delete, set centre, export, preview) and draw/edit them as vectors: shapes, lines, curves, text, select + transform (move/resize/rotate/flip/skew), group/ungroup, layers, fill/outline, path nodes, copy/paste, canvas size, crop. Elements are addressed by id (see 'elements'). A costume is addressed by name or 1-based number. Coordinates: costume pixels, origin top-left; Scratch's stage is 480x360 (a sprite's rotation centre is the point that sits at its x/y position). Bitmap costumes can be switched to vector with to_vector and back with to_bitmap (needs the headless browser, see runtime_manager setup). Edits are undoable (project_manager undo).

### costume_manager.list

List costumes (or backdrops for the Stage) with format, size and rotation centre.

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.add_blank

Add an empty vector costume of a given size (optionally filled with a background colour); draw on it with 'draw'.

| parameter | type | description |
| --- | --- | --- |
| `name` | string |  |
| `width` | number | canvas width in pixels (backdrops are 480x360). |
| `height` | number |  |
| `background` | string | e.g. '#87ceeb' or omit for transparent. |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.add_svg

Add a costume from SVG text (checked: no scripts/external links).

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `svg`* | string |  |
| `center_x` | number |  |
| `center_y` | number |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.import_image

Import a PNG, JPEG or SVG as a costume/backdrop.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `source_path` | string | image file inside the projects folder. |
| `data_base64` | string | alternatively the file bytes, base64 encoded. |
| `bitmap_resolution` | integer | for png/jpg: 2 = shown at half pixel size (Scratch default), 1 = native pixels. |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.add_stock

Add all costumes of a stock art set (robot, alien, cookie, title - or kitchen backdrops on the Stage). replace=true removes the existing ones first.

| parameter | type | description |
| --- | --- | --- |
| `art`* | string |  |
| `replace` | boolean |  |
| `sprite` | string |  |
| `project` | string |  |
| `text` | string |  |

### costume_manager.stock_list

List the built-in stock art sets.

### costume_manager.delete

Delete a costume/backdrop (a sprite must keep at least one).

| parameter | type | description |
| --- | --- | --- |
| `costume`* | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.duplicate

Duplicate a costume (placed right after the original).

| parameter | type | description |
| --- | --- | --- |
| `costume` | string\|integer |  |
| `new_name` | string |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.rename

Rename a costume/backdrop (blocks that name it in a 'switch costume' menu are updated).

| parameter | type | description |
| --- | --- | --- |
| `costume`* | string\|integer |  |
| `new_name`* | string |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.reorder

Move a costume to a 1-based position in the list.

| parameter | type | description |
| --- | --- | --- |
| `costume`* | string\|integer |  |
| `position`* | integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.set_current

Choose which costume/backdrop is shown when the project starts.

| parameter | type | description |
| --- | --- | --- |
| `costume`* | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.set_center

Set the rotation centre (the point that sits at the sprite's x/y).

| parameter | type | description |
| --- | --- | --- |
| `costume` | string\|integer |  |
| `x` | number | centre x in costume pixels. |
| `y` | number | centre y in costume pixels. |
| `mode` | string | instead of x/y: 'center' (middle of the image), 'content' (middle of the artwork), 'bottom' (bottom middle - feet). |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.svg

Return the costume's SVG source text.

| parameter | type | description |
| --- | --- | --- |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.preview

Render a costume/backdrop as a PNG image you can look at (needs the headless browser for vector costumes).

| parameter | type | description |
| --- | --- | --- |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |
| `scale` | number | pixel density multiplier. |
| `background` | string | CSS colour behind transparent areas (null = transparent). |

### costume_manager.export

Write the costume file (svg/png/jpg) to <projects folder>/exports/ and return its path.

| parameter | type | description |
| --- | --- | --- |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |
| `include_base64` | boolean |  |

### costume_manager.draw

Draw a shape on a vector costume. shape: rect(x,y,width,height[,rx]), circle(cx,cy,r), ellipse(cx,cy,rx,ry), line(x1,y1,x2,y2), polyline(points), polygon(points), triangle(points), path(d), curve(points: 3 quadratic/4 cubic), star(cx,cy,r[,spikes,inner_ratio]), text(text,x,y[,font_size,font_family,bold,anchor]).

| parameter | type | description |
| --- | --- | --- |
| `shape`* | string | one of rect, circle, ellipse, line, polyline, polygon, triangle, path, curve, star, text. |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |
| `x` | number |  |
| `y` | number |  |
| `width` | number |  |
| `height` | number |  |
| `cx` | number |  |
| `cy` | number |  |
| `r` | number |  |
| `rx` | number |  |
| `ry` | number |  |
| `x1` | number |  |
| `y1` | number |  |
| `x2` | number |  |
| `y2` | number |  |
| `points` | [[number]] | [[x,y],...] for polyline/polygon/triangle/curve. |
| `d` | string | SVG path data for 'path'. |
| `text` | string |  |
| `font_size` | number |  |
| `font_family` | string |  |
| `bold` | boolean |  |
| `anchor` | string |  |
| `spikes` | integer |  |
| `inner_ratio` | number |  |
| `fill` | string | CSS colour or 'none' (shapes default to black fill if omitted; lines/curves default to a black outline). |
| `stroke` | string | outline colour. |
| `stroke_width` | number |  |
| `opacity` | number |  |
| `into_group` | string | id of a group to draw into. |

### costume_manager.elements

List the drawing's elements (with ids, bounding boxes, styles; groups nested) and canvas size/centre.

| parameter | type | description |
| --- | --- | --- |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.transform

Move / resize / rotate / flip / skew an element or group (select = reference by id). Scale, rotate, flip and skew act around the element's own centre.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string | element id. |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |
| `move_x` | number | shift right by this many pixels. |
| `move_y` | number |  |
| `scale` | number | uniform scale factor (2 = twice as big). |
| `scale_x` | number |  |
| `scale_y` | number |  |
| `width` | number | resize to this width in pixels (keeps aspect unless height also given). |
| `height` | number |  |
| `rotate` | number | degrees clockwise. |
| `flip` | string | 'horizontal' or 'vertical'. |
| `skew_x` | number |  |
| `skew_y` | number |  |
| `position_x` | number | move so the element's anchor point is at this x. |
| `position_y` | number |  |
| `anchor` | string | which point position_x/position_y refer to: top-left, center, top-right, bottom-left, bottom-right. |

### costume_manager.set_style

Change fill / outline colour and width, opacity, line caps/joins, dashes (groups apply to every shape inside).

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |
| `fill` | string |  |
| `stroke` | string |  |
| `stroke_width` | number |  |
| `opacity` | number |  |
| `fill_opacity` | number |  |
| `stroke_opacity` | number |  |
| `linecap` | string |  |
| `linejoin` | string |  |
| `dash` | string |  |

### costume_manager.group

Group several elements (they must share a parent) so they move/transform together.

| parameter | type | description |
| --- | --- | --- |
| `ids`* | [string] |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.ungroup

Dissolve a group; its children keep their look and position.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.layer

Change an element's z-order: mode = front | back | forward | backward (by steps).

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `mode`* | string |  |
| `steps` | integer |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.delete_elements

Delete elements by id.

| parameter | type | description |
| --- | --- | --- |
| `ids`* | [string] |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.edit_text

Change a text element's content, size, font (Sans Serif, Serif, Handwriting, Marker, Curly, Pixel, Scratch), weight, alignment.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `text` | string |  |
| `font_size` | number |  |
| `font_family` | string |  |
| `bold` | boolean |  |
| `anchor` | string |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.path_nodes

List a path's nodes (index, command, anchor point and Bezier handles) for node editing.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.path_edit

Move one path node's anchor to (x, y); its curve handles follow when move_handles is true.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `index`* | integer |  |
| `x`* | number |  |
| `y`* | number |  |
| `move_handles` | boolean |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.path_add

Insert a straight-line node after node `after_index`.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `after_index`* | integer |  |
| `x`* | number |  |
| `y`* | number |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.path_delete

Delete a path node.

| parameter | type | description |
| --- | --- | --- |
| `id`* | string |  |
| `index`* | integer |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.copy

Copy elements to the clipboard (including gradients they use). Paste into any costume with 'paste'.

| parameter | type | description |
| --- | --- | --- |
| `ids`* | [string] |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.paste

Paste the clipboard into a vector costume (works across costumes and sprites).

| parameter | type | description |
| --- | --- | --- |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |
| `offset_x` | number |  |
| `offset_y` | number |  |

### costume_manager.clear

Erase all artwork (keeps canvas size and rotation centre).

| parameter | type | description |
| --- | --- | --- |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.set_canvas

Resize the canvas (artwork stays where it is, top-left anchored).

| parameter | type | description |
| --- | --- | --- |
| `width`* | number |  |
| `height`* | number |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.crop

Shrink the canvas to the artwork's bounds (rotation centre keeps pointing at the same spot of the art).

| parameter | type | description |
| --- | --- | --- |
| `padding` | number |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.replace_svg

Replace a costume's whole SVG (checked). Use for edits the other actions can't express.

| parameter | type | description |
| --- | --- | --- |
| `svg`* | string |  |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.to_bitmap

Convert a vector costume to a PNG bitmap (rasterized in the headless browser at the given resolution).

| parameter | type | description |
| --- | --- | --- |
| `costume` | string\|integer |  |
| `bitmap_resolution` | integer |  |
| `sprite` | string |  |
| `project` | string |  |

### costume_manager.to_vector

Convert a bitmap costume to vector form by wrapping the image in an SVG (the pixels are embedded, not traced) so shapes/text can be drawn over it; convert back with to_bitmap.

| parameter | type | description |
| --- | --- | --- |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

## backdrop_manager

Backdrops and the Stage. Backdrops are costumes of the Stage: create (blank / SVG / import / stock 'kitchen'), rename, duplicate, reorder, delete, set the starting backdrop, preview, export - and draw on them with costume_manager draw/transform/... using sprite='Stage'. 'stage_get'/'stage_set' read and change stage settings (volume, tempo, video, text-to-speech language). Stage scripts: script_manager with sprite='Stage'. Switching backdrops at run time uses the 'switch backdrop to' blocks.

### backdrop_manager.list

List backdrops (number, name, format, size, rotation centre, which one is current).

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### backdrop_manager.add_blank

Add a blank vector backdrop (default 480x360, white).

| parameter | type | description |
| --- | --- | --- |
| `name` | string |  |
| `background` | string |  |
| `width` | number |  |
| `height` | number |  |
| `project` | string |  |

### backdrop_manager.add_svg

Add a backdrop from SVG text (480x360 fills the stage; centre defaults to the middle).

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `svg`* | string |  |
| `project` | string |  |

### backdrop_manager.import_image

Import a PNG/JPEG/SVG as a backdrop.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `source_path` | string |  |
| `data_base64` | string |  |
| `bitmap_resolution` | integer |  |
| `project` | string |  |

### backdrop_manager.add_stock

Add stock backdrops (currently: kitchen = futuristic kitchen, 2 animated frames).

| parameter | type | description |
| --- | --- | --- |
| `art` | string |  |
| `replace` | boolean |  |
| `project` | string |  |

### backdrop_manager.delete

Delete a backdrop (the Stage keeps at least one).

| parameter | type | description |
| --- | --- | --- |
| `backdrop`* | string\|integer |  |
| `project` | string |  |

### backdrop_manager.duplicate

Duplicate a backdrop.

| parameter | type | description |
| --- | --- | --- |
| `backdrop` | string\|integer |  |
| `new_name` | string |  |
| `project` | string |  |

### backdrop_manager.rename

Rename a backdrop (blocks that name it are updated).

| parameter | type | description |
| --- | --- | --- |
| `backdrop`* | string\|integer |  |
| `new_name`* | string |  |
| `project` | string |  |

### backdrop_manager.reorder

Move a backdrop to a 1-based position (affects 'next backdrop').

| parameter | type | description |
| --- | --- | --- |
| `backdrop`* | string\|integer |  |
| `position`* | integer |  |
| `project` | string |  |

### backdrop_manager.set_initial

Choose the backdrop shown when the project starts (also saved as the current one).

| parameter | type | description |
| --- | --- | --- |
| `backdrop`* | string\|integer |  |
| `project` | string |  |

### backdrop_manager.preview

Render a backdrop as a PNG image (480x360 at scale 1).

| parameter | type | description |
| --- | --- | --- |
| `backdrop` | string\|integer |  |
| `project` | string |  |
| `scale` | number |  |

### backdrop_manager.export

Write the backdrop file to the exports folder.

| parameter | type | description |
| --- | --- | --- |
| `backdrop` | string\|integer |  |
| `project` | string |  |
| `include_base64` | boolean |  |

### backdrop_manager.stage_get

Stage settings and counts.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### backdrop_manager.stage_set

Change stage settings. volume 0-100; tempo 20-500 bpm (Music extension); video_state on|off|on-flipped; video_transparency 0-100; text_to_speech_language e.g. 'en'.

| parameter | type | description |
| --- | --- | --- |
| `volume` | number |  |
| `tempo` | number |  |
| `video_state` | string |  |
| `video_transparency` | number |  |
| `text_to_speech_language` | string |  |
| `project` | string |  |

## sound_manager

Sounds of a sprite or the Stage (sprite='Stage'). Import WAV (or mp3/ogg/flac/m4a when ffmpeg is installed), generate sounds (presets: pop, boing, bloop, squeak, alien_warble, crack, munch, chime, whoosh, sad_trombone, music_cheerful/calm/sneaky - length and tempo adjustable - or pure tones), rename/duplicate/delete, and edit audio: trim, cut/copy/paste segments, silence, reverse, volume, normalize, fades, echo, speed (faster/slower), robot voice. 'preview' returns the audio itself (as MCP audio content) so you can listen. Play sounds at run time with the 'start sound' blocks, and test them with runtime_manager / testing_manager (sound plays are logged). Recording from a microphone is not possible in this headless server - synthesize or import instead.

### sound_manager.list

List sounds with duration, sample rate and size.

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `project` | string |  |

### sound_manager.add_preset

Generate a sound from a built-in preset (see tool description). For music_* presets 'seconds' sets the length (up to 120) and 'tempo' the bpm; a track as long as your animation ends with a final chord.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string | name for the new sound. |
| `preset`* | string | pop, boing, bloop, squeak, alien_warble, crack, munch, chime, whoosh, sad_trombone, music_cheerful, music_calm, music_sneaky. |
| `seconds` | number |  |
| `tempo` | number |  |
| `sprite` | string |  |
| `project` | string |  |

### sound_manager.add_tone

Generate a pure tone (sine, square, saw or triangle wave) as a sound.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `frequency`* | number |  |
| `seconds` | number |  |
| `wave` | string |  |
| `volume` | number |  |
| `sprite` | string |  |
| `project` | string |  |

### sound_manager.import_sound

Import an audio file (WAV directly; mp3/ogg/flac/m4a via ffmpeg) from the projects folder or base64 data.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `source_path` | string |  |
| `data_base64` | string |  |
| `sprite` | string |  |
| `project` | string |  |

### sound_manager.rename

Rename a sound (blocks that name it in a 'start sound' menu are updated).

| parameter | type | description |
| --- | --- | --- |
| `sound`* | string\|integer |  |
| `new_name`* | string |  |
| `sprite` | string |  |
| `project` | string |  |

### sound_manager.delete

Delete a sound.

| parameter | type | description |
| --- | --- | --- |
| `sound`* | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### sound_manager.duplicate

Duplicate a sound (placed after the original).

| parameter | type | description |
| --- | --- | --- |
| `sound`* | string\|integer |  |
| `new_name` | string |  |
| `sprite` | string |  |
| `project` | string |  |

### sound_manager.edit

Edit a WAV sound in place (or into a new sound with save_as). operation: trim (keep start..end seconds) | cut (remove start..end) | silence (mute start..end) | reverse (whole sound or start..end) | volume (multiply by factor; 2 = louder, 0.5 = softer; optionally only start..end) | normalize | fade_in / fade_out (over 'seconds') | echo (delay seconds, decay 0-1) | faster / slower (speed factor, changes pitch; default 1.25 / 0.8) | robot (ring-mod at frequency Hz).

| parameter | type | description |
| --- | --- | --- |
| `sound`* | string\|integer |  |
| `operation`* | string | one of the names above. |
| `sprite` | string |  |
| `project` | string |  |
| `start` | number | range start in seconds. |
| `end` | number | range end in seconds. |
| `factor` | number | volume or speed multiplier. |
| `seconds` | number |  |
| `delay` | number |  |
| `decay` | number |  |
| `frequency` | number |  |
| `save_as` | string | write the result as a new sound with this name and keep the original. |

### sound_manager.copy_segment

Copy part of a sound to the audio clipboard (paste with paste_segment into any sound).

| parameter | type | description |
| --- | --- | --- |
| `sound`* | string\|integer |  |
| `start`* | number |  |
| `end`* | number |  |
| `sprite` | string |  |
| `project` | string |  |

### sound_manager.paste_segment

Insert the copied segment at a time position (seconds) in a sound.

| parameter | type | description |
| --- | --- | --- |
| `sound`* | string\|integer |  |
| `at`* | number |  |
| `sprite` | string |  |
| `project` | string |  |

### sound_manager.preview

Return the sound as audio content (first max_seconds) so it can be listened to, plus its stats (peak level, duration).

| parameter | type | description |
| --- | --- | --- |
| `sound` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |
| `max_seconds` | number |  |

### sound_manager.export

Write the sound file to <projects folder>/exports/.

| parameter | type | description |
| --- | --- | --- |
| `sound` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

## asset_manager

Project asset files and Scratch's online library. 'list' shows every costume/backdrop/sound file in the .sb3 and who uses it; 'prune' removes unused files. 'library_search' browses Scratch's built-in sprites, costumes, backdrops and sounds; 'library_add' puts one into the project (needs internet access to Scratch's public asset servers; results are cached on disk). To make your own art or sounds use costume_manager / sound_manager.

### asset_manager.list

Every file inside the .sb3 (besides project.json) with size and users; flags files nothing uses and references to missing files.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### asset_manager.prune

Remove asset files no costume or sound refers to (reduces file size).

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### asset_manager.library_search

Search Scratch's library.

| parameter | type | description |
| --- | --- | --- |
| `kind`* | string | sprites, costumes, backdrops or sounds. |
| `query` | string | part of a name or tag (e.g. 'cat', 'space', 'animals'). |
| `tag` | string | exact tag filter. |
| `limit` | integer |  |

### asset_manager.library_add

Add a library item. sprites: creates a new sprite with all its costumes, sounds and starter scripts. costumes: adds to `sprite`. backdrops: adds to the Stage. sounds: adds to `sprite` (or the Stage).

| parameter | type | description |
| --- | --- | --- |
| `kind`* | string | sprites, costumes, backdrops or sounds. |
| `name`* | string | exact library name (see library_search). |
| `sprite` | string | target sprite for costumes/sounds. |
| `new_name` | string | name to give the new sprite/costume/sound. |
| `project` | string |  |

## runtime_manager

Run the active project in the REAL Scratch VM and renderer (headless Chromium) and observe it. Time is simulated deterministically at 30 frames/second: the project only advances when you call run/step (so it is 'paused' between calls, and 'run' seconds are simulated seconds, not real ones). Typical loop: start -> green_flag -> run(seconds) -> screenshot / state -> edit the project -> start again (reload picks up your edits; unsaved edits included). Needs a one-time 'setup' (downloads scratch-vm/scratch-render via npm) and a Chromium browser. Not supported: real audio output (sound plays are logged, see events), webcam, microphone, hardware extensions, cloud variables.

### runtime_manager.setup

Install the Scratch runtime (scratch-vm + scratch-render from npm) into the cache folder. One time; needs node/npm and internet.

| parameter | type | description |
| --- | --- | --- |
| `force` | boolean |  |

### runtime_manager.status

What is installed (runtime files, playwright, Chromium, ffmpeg, node) and which projects are running.

### runtime_manager.start

Load the project's CURRENT in-memory state into a fresh VM (resets the simulation). Optionally press the green flag and run.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `green_flag` | boolean | press the green flag right after loading. |
| `run_seconds` | number | simulated seconds to run after the flag. |

### runtime_manager.stop

Close the runtime page for the project (frees memory).

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### runtime_manager.green_flag

Press the green flag (starts all 'when flag clicked' scripts). Optionally run some simulated seconds afterwards.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `run_seconds` | number |  |

### runtime_manager.stop_all

Press the red stop sign: stops all scripts and deletes clones.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### runtime_manager.restart

Reload the project from its current state, press the green flag and optionally run.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `run_seconds` | number |  |

### runtime_manager.run

Advance the simulation by `seconds` (simulated; 30 fps). With `until`, stop early as soon as the condition holds.

| parameter | type | description |
| --- | --- | --- |
| `seconds`* | number | simulated seconds to advance (max 600). |
| `project` | string |  |
| `until` | object | optional condition. Examples: {"type":"variable","name":"score","op":">=","value":3}; {"type":"sprite","sprite":"Robot","property":"x","op":">","value":100}; {"type":"touching","a":"Robot","b":"Alien"}; {"type":"count","event":"sound_play","arg":"pop"}; {"type":"clones","sprite":"Bullet","op":">=","value":2}. Properties: x y size direction visible costume say. Ops: == != > >= < <= contains. |

### runtime_manager.step

Advance a small number of frames (1 frame = 1/30 s) - for stepping through execution frame by frame.

| parameter | type | description |
| --- | --- | --- |
| `frames` | integer |  |
| `project` | string |  |

### runtime_manager.state

Current runtime state: project time, every sprite's position/size/direction/costume/visibility/speech bubble, variables and lists, pending question, clone count, running scripts.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `include_clones` | boolean |  |

### runtime_manager.sprite_state

One sprite's current runtime state.

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `project` | string |  |

### runtime_manager.variables

Runtime values of all variables and lists (lists show up to 200 items).

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### runtime_manager.threads

Scripts that are running right now (sprite, top block, opcode).

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### runtime_manager.events

The run log: green flag, key/mouse input, sounds started (sound_play), broadcasts, say/think, clone creation, questions, costume switches ... with project time.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `type` | string | filter by event type, e.g. sound_play, event_broadcast, say, create_clone_of, key_down. |
| `last` | integer | how many of the most recent matching events to return. |
| `clear` | boolean | empty the log afterwards. |

### runtime_manager.screenshot

Capture the stage as a PNG image (what a player would see: sprites, backdrop, speech bubbles, pen drawings).

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `scale` | integer | 1 (480x360) or 2 (960x720). |

### runtime_manager.create_clone

Create a clone of a sprite at run time (as the 'create clone of' block would).

| parameter | type | description |
| --- | --- | --- |
| `sprite`* | string |  |
| `project` | string |  |

### runtime_manager.list_clones

List all current clones with their state.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### runtime_manager.delete_clones

Delete clones (of one sprite, or all).

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `project` | string |  |

### runtime_manager.set_variable

Change a variable's value in the running simulation (for tests; does not edit the project).

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `value`* | Any |  |
| `sprite` | string |  |
| `project` | string |  |

### runtime_manager.set_sprite

Move/resize a sprite in the running simulation (for tests; does not edit the project).

| parameter | type | description |
| --- | --- | --- |
| `sprite`* | string |  |
| `x` | number |  |
| `y` | number |  |
| `direction` | number |  |
| `size` | number |  |
| `visible` | boolean |  |
| `project` | string |  |

### runtime_manager.console

Browser/VM console output for the running project (errors by default).

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `errors_only` | boolean |  |
| `last` | integer |  |

### runtime_manager.snapshot

Remember the current stage picture under a name, to compare with later (before/after an edit or a run).

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `project` | string |  |

### runtime_manager.compare

Compare the current stage with a saved snapshot. Returns how much changed (percent of pixels, bounding box) and a diff image with the changed pixels in red.

| parameter | type | description |
| --- | --- | --- |
| `against`* | string | snapshot name from 'snapshot'. |
| `project` | string |  |
| `threshold` | integer | colour difference (0-765) above which a pixel counts as changed. |

## input_manager

Simulate user input in the running project (starts it automatically if needed). Keys use Scratch's names: a-z, 0-9, 'space', 'up arrow', 'down arrow', 'left arrow', 'right arrow', 'enter'. Mouse positions are Scratch stage coordinates (x -240..240, y -180..180, 0,0 = centre). Every action accepts 'then_run' - simulated seconds to keep running afterwards so the effect can play out - and returns a short state summary. Time only advances when you run it (see runtime_manager).

### input_manager.key_press

Press and release a key (held for `hold_seconds` of simulated time).

| parameter | type | description |
| --- | --- | --- |
| `key`* | string |  |
| `hold_seconds` | number |  |
| `then_run` | number |  |
| `project` | string |  |

### input_manager.key_down

Press a key and keep holding it (until key_up / release_all).

| parameter | type | description |
| --- | --- | --- |
| `key`* | string |  |
| `then_run` | number |  |
| `project` | string |  |

### input_manager.key_up

Release a held key.

| parameter | type | description |
| --- | --- | --- |
| `key`* | string |  |
| `then_run` | number |  |
| `project` | string |  |

### input_manager.release_all

Release every key and mouse button that is being held.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### input_manager.type_keys

Press several keys one after another (e.g. ['right arrow','right arrow','space']).

| parameter | type | description |
| --- | --- | --- |
| `keys`* | [string] |  |
| `seconds_each` | number |  |
| `then_run` | number |  |
| `project` | string |  |

### input_manager.mouse_move

Move the mouse pointer to stage coordinates (x, y).

| parameter | type | description |
| --- | --- | --- |
| `x`* | number |  |
| `y`* | number |  |
| `then_run` | number |  |
| `project` | string |  |

### input_manager.mouse_down

Press and hold the mouse button (at x,y if given). Clicking a sprite this way triggers 'when this sprite clicked' and starts dragging a draggable sprite.

| parameter | type | description |
| --- | --- | --- |
| `x` | number |  |
| `y` | number |  |
| `then_run` | number |  |
| `project` | string |  |

### input_manager.mouse_up

Release the mouse button.

| parameter | type | description |
| --- | --- | --- |
| `then_run` | number |  |
| `project` | string |  |

### input_manager.click

Click at stage coordinates: move there, press, hold, release.

| parameter | type | description |
| --- | --- | --- |
| `x`* | number |  |
| `y`* | number |  |
| `hold_seconds` | number |  |
| `then_run` | number |  |
| `project` | string |  |

### input_manager.click_sprite

Click on a sprite (at its current position) - triggers its 'when this sprite clicked' scripts. Fails if the sprite is hidden or off stage.

| parameter | type | description |
| --- | --- | --- |
| `sprite`* | string |  |
| `hold_seconds` | number |  |
| `then_run` | number |  |
| `project` | string |  |

### input_manager.drag

Press at one point, move to another over `seconds`, release (drags draggable sprites, moves sliders...).

| parameter | type | description |
| --- | --- | --- |
| `from_x`* | number |  |
| `from_y`* | number |  |
| `to_x`* | number |  |
| `to_y`* | number |  |
| `seconds` | number |  |
| `then_run` | number |  |
| `project` | string |  |

### input_manager.answer

Type a response into an 'ask ... and wait' prompt (the project must be waiting for one: see state.question).

| parameter | type | description |
| --- | --- | --- |
| `text`* | string |  |
| `then_run` | number |  |
| `project` | string |  |

## extension_manager

Scratch's built-in extensions: pen, music, videoSensing, text2speech, translate, makeymakey, microbit, ev3 (LEGO MINDSTORMS), boost (LEGO BOOST), wedo2 (LEGO WeDo 2.0), gdxfor (Go Direct Force & Acceleration). 'enable' adds the extension to the project (its blocks are then usable; adding a block also enables it automatically). The block definitions come from scratch-vm itself. 'verify' loads the project in the real VM to prove the extensions load. Honest limits: pen/music/makeymakey run fully in the simulated runtime (music/sound OUTPUT is not audible); text2speech/translate need internet access to Scratch's servers at run time; videoSensing needs a webcam (none here, so it reads no video); microbit/ev3/boost/wedo2/gdxfor need physical hardware and the Scratch Link app - hardware connectivity is NOT supported by this server (you can still author and save projects that use them). LEGO SPIKE / SPIKE Prime is not a built-in Scratch 3 extension (it lives in LEGO's own app), so it is unsupported.

### extension_manager.list

All built-in extensions with what they need to run, and (if a project is open) whether it uses them.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### extension_manager.describe

An extension's blocks (opcode, shape, text, inputs, fields) and menus, straight from scratch-vm's definition.

| parameter | type | description |
| --- | --- | --- |
| `extension`* | string |  |

### extension_manager.enable

Add an extension to the project (blocks from it can then be used; it appears in the editor's block palette).

| parameter | type | description |
| --- | --- | --- |
| `extension`* | string |  |
| `project` | string |  |

### extension_manager.disable

Remove an extension from the project. Refuses while its blocks are used unless remove_blocks=true (which deletes those blocks and their scripts' following blocks).

| parameter | type | description |
| --- | --- | --- |
| `extension`* | string |  |
| `remove_blocks` | boolean |  |
| `project` | string |  |

### extension_manager.verify

Load the project in the real Scratch VM and run the green flag for a moment: proves each enabled extension loads, and reports VM errors.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `run_seconds` | number |  |

## animation_manager

Generate common cartoon/animation scripts in one call: costume cycles (walk/run/idle), blinking, jumps, entrances/exits/paths, multi-character dialogue, scene transitions (fade/wipe) and a scene timeline on the Stage. 'on' says what starts the script: "flag" | "clicked" | {"key": "space"} | {"broadcast": "name"} | {"while_key": "right arrow"} (repeats while the key is held; for cycles). Everything is ordinary Scratch blocks you can inspect and edit afterwards. Animation timing is in seconds; Scratch runs at 30 frames/second.

### animation_manager.cycle

Loop through costumes (a walk, run, idle or any frame-by-frame animation), optionally moving a little each frame.

| parameter | type | description |
| --- | --- | --- |
| `costumes`* | [string] | costume names in order, e.g. ["walk1", "walk2"]. |
| `delay` | number | seconds each frame is shown. |
| `times` | integer | repeat this many times; omit to repeat forever. |
| `on` | Any | what starts it. With {"while_key": "right arrow"} it plays only while the key is held. |
| `move_x` | number | pixels to move per frame (negative = left). |
| `move_y` | number |  |
| `face` | integer | point in this direction first (90 = right, -90 = left). |
| `rest_costume` | string | costume to show after a finite cycle ends. |
| `sprite` | string |  |
| `project` | string |  |

### animation_manager.blink

Random blinking: wait a random time, show the closed-eyes costume briefly, go back. Runs forever from the green flag. (If you also run a walk cycle on the same sprite, give the cycle only costumes that already have open eyes, or blink via a separate eyes sprite.)

| parameter | type | description |
| --- | --- | --- |
| `open_costume`* | string |  |
| `closed_costume`* | string |  |
| `min_wait` | number |  |
| `max_wait` | number |  |
| `closed_time` | number |  |
| `sprite` | string |  |
| `project` | string |  |

### animation_manager.jump

A jump arc (up then down, frame by frame), with optional pose, landing pose and sound. By default triggered by the space key; a guard variable (created for you) stops double jumps.

| parameter | type | description |
| --- | --- | --- |
| `height` | number | pixels to rise. |
| `seconds` | number | total time up + down. |
| `on` | Any | trigger (default {"key": "space"}). |
| `ground_y` | number | y to return to (default: the sprite's current y). |
| `jump_costume` | string | costume shown while in the air. |
| `land_costume` | string | costume to return to afterwards. |
| `sound` | string | name of one of the sprite's sounds to play at take-off. |
| `guard_variable` | string |  |
| `sprite` | string |  |
| `project` | string |  |

### animation_manager.move

Movement choreography. kind: 'path' (glide through `points`), 'entrance' (appear from off-screen `side` and glide to to_x/to_y), 'exit' (glide off-screen `side` then hide). With `costumes` the sprite also animates (a walk cycle) while it moves.

| parameter | type | description |
| --- | --- | --- |
| `kind` | string | path \| entrance \| exit. |
| `points` | [[number]] | [[x,y], ...] for 'path'. |
| `seconds_each` | number |  |
| `side` | string | left \| right \| top \| bottom, for entrance/exit. |
| `to_x` | number |  |
| `to_y` | number |  |
| `seconds` | number | duration for entrance/exit. |
| `on` | Any |  |
| `costumes` | [string] | optional frames to cycle while moving. |
| `delay` | number |  |
| `sprite` | string |  |
| `project` | string |  |

### animation_manager.dialogue

A conversation between sprites. Each line is {"sprite": "Robo", "text": "Hello!", "seconds": 2, "costume": "happy"(optional), "sound": "name"(optional), "return_costume": optional}. Lines play one after another across sprites using broadcasts '<channel> 1', '<channel> 2', ... ('<channel> done' at the end - hook other scripts to it).

| parameter | type | description |
| --- | --- | --- |
| `lines`* | [object] | the lines in order. |
| `on` | Any | what starts the first line. |
| `channel` | string | prefix for the broadcast names. |
| `pause` | number | seconds between lines. |
| `project` | string |  |

### animation_manager.transition

A scene transition. kind 'fade' (screen fades to a colour, backdrop changes, fades back) or 'wipe' (a colour sweeps across). Creates a full-screen cover sprite (default name 'Transition') if it doesn't exist. Default trigger: broadcast 'transition'. Broadcasts '<cover> midpoint' when the screen is fully covered, so scenes can swap sprites there.

| parameter | type | description |
| --- | --- | --- |
| `kind` | string | fade \| wipe. |
| `on` | Any | trigger (default {"broadcast": "transition"}). |
| `to_backdrop` | string | backdrop to switch to while covered. |
| `seconds` | number | length of each half. |
| `color` | string | cover colour. |
| `cover_sprite` | string |  |
| `project` | string |  |

### animation_manager.timeline

A Stage script that runs a sequence of scenes on a timer (no drift): for each scene it switches the backdrop (optional), broadcasts '<prefix> N' and '<prefix> <name>', and waits until the scene's end time. Sprites react with `when I receive`. A final '<prefix> end' marks the end.

| parameter | type | description |
| --- | --- | --- |
| `scenes`* | [object] | [{"name": "intro", "seconds": 5, "backdrop": "city"(optional)}, ...]. |
| `on` | Any | what starts the timeline (default green flag). |
| `broadcast_prefix` | string | prefix for broadcast names. |
| `stop_at_end` | boolean | stop all scripts when the last scene finishes. |
| `project` | string |  |

## inspection_manager

Read-only views of a project for planning edits. 'overview' = the whole structure in one call; 'component' = one part in detail (sprite, costumes, sounds, scripts, variables, lists, broadcasts, monitors, extensions, stage, meta); 'find_blocks' searches every script; 'block_graph' shows how blocks connect (parent/next/inputs); 'references' says what uses a variable/list/broadcast/costume/sound/sprite/custom block; 'json' returns raw project.json (optionally one part). Live run-time state: runtime_manager state / screenshot.

### inspection_manager.overview

The complete project structure: metadata, extensions, stage, every sprite (properties, costumes, sounds, script counts and trigger types), global variables/lists, broadcasts, monitors, asset totals.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### inspection_manager.component

One part in detail.

| parameter | type | description |
| --- | --- | --- |
| `kind`* | string | sprite \| costumes \| sounds \| scripts \| variables \| lists \| broadcasts \| monitors \| extensions \| stage \| meta \| comments. |
| `sprite` | string | which sprite (default: selected); for 'stage' not needed. |
| `project` | string |  |

### inspection_manager.find_blocks

Search all blocks (or one sprite's).

| parameter | type | description |
| --- | --- | --- |
| `opcode` | string | exact opcode or prefix ending in '*', e.g. 'motion_*'. |
| `text` | string | substring of the block's readable text (e.g. 'score'). |
| `field_value` | string | a dropdown/variable field value, e.g. 'game over'. |
| `sprite` | string |  |
| `project` | string |  |
| `limit` | integer |  |

### inspection_manager.block_graph

Connections between blocks: for each block its opcode, parent, next, input children (and shadows) and fields. Give a script id for one script, else all blocks of the sprite (large!).

| parameter | type | description |
| --- | --- | --- |
| `script` | string |  |
| `sprite` | string |  |
| `project` | string |  |

### inspection_manager.references

Where something is used.

| parameter | type | description |
| --- | --- | --- |
| `kind`* | string | variable \| list \| broadcast \| costume \| sound \| sprite \| procedure. |
| `name`* | string | its name (for procedure: the label, e.g. 'jump %s'). |
| `project` | string |  |

### inspection_manager.json

Raw project.json (or part of it). section examples: 'targets[1].blocks', 'targets[0].costumes', 'meta', 'extensions', 'monitors'. Output is cut at max_chars with a note.

| parameter | type | description |
| --- | --- | --- |
| `section` | string | path into project.json using keys and [index]; omit for everything. |
| `project` | string |  |
| `pretty` | boolean |  |
| `max_chars` | integer | truncate the text beyond this length. |

## debug_manager

Find and explain problems. 'check' is static (no running): structure, block rules, broken references (missing costumes/sounds/sprites/custom blocks), broadcasts nobody sends or receives, unused/write-only variables, empty loops, orphan blocks, hang risks. 'dead_scripts' and 'hang_check' RUN the project. 'errors' shows VM/browser errors. 'diagnose' does all of it and returns a prioritised list with hints. After fixing, run it again to verify the fix.

### debug_manager.check

Static analysis of the whole project (nothing is run). Returns issues with severity error/warning/info, the sprite, block id and a hint.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `include_info` | boolean | also list low-priority notes (unused variables, orphan blocks...). |

### debug_manager.errors

Errors the Scratch VM or browser reported while the project ran (empty list = none).

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `clear` | boolean |  |

### debug_manager.dead_scripts

Reload the project, press the green flag, run, optionally press keys / click sprites, then list scripts whose hat never fired. 'when flag clicked' scripts that never start are bugs; event scripts only fire when their trigger happened (use press_keys / click_sprites to trigger them).

| parameter | type | description |
| --- | --- | --- |
| `seconds` | number | simulated seconds to run after the flag. |
| `press_keys` | [string] | keys to press afterwards, e.g. ['space', 'a']. |
| `click_sprites` | [string] | sprites to click afterwards. |
| `project` | string |  |

### debug_manager.hang_check

Run the project for `seconds` and report whether it froze (a script that never yields), with static hang risks.

| parameter | type | description |
| --- | --- | --- |
| `seconds` | number |  |
| `project` | string |  |

### debug_manager.diagnose

Everything at once: static check, then a short run (flag) looking for run-time errors, scripts that never start and hangs. Returns problems sorted by severity with hints.

| parameter | type | description |
| --- | --- | --- |
| `seconds` | number |  |
| `project` | string |  |

## testing_manager

Automated tests for the running project. A scenario is a list of steps: actions {"do": ...} and checks {"expect": ...}. Actions: start (reload project fresh), flag, run{seconds}, key_press{key,hold,then_run}, key_down{key}, key_up{key}, click{x,y}, click_sprite{sprite}, mouse_move{x,y}, drag{from_x,from_y,to_x,to_y}, answer{text}, set_variable{name,value}, set_sprite{sprite,x,y,...}, move_onto{sprite,other}, remember{as,sprite,property | variable}, stop. Checks (add "within": seconds to wait for it to become true): {"sprite":"Robot","property":"x","op":">","value":10} (properties x y size direction visible costume say; ops == != > >= < <= contains; or "than":"<remembered name>" to compare with a remembered value); {"variable":"score","op":">=","value":3}; {"touching":["A","B"]}; {"sound_played":"pop"}; {"broadcast_sent":"jump"}; {"costume_changed":"Robot"}; {"clones":{"sprite":"Bullet","op":">=","value":2}}; {"say":{"sprite":"Cat","contains":"Hi"}}; {"asking":"name"}. Use 'quick' for common tests (keyboard, click, collision, variable, broadcast, clones, animation, audio). A failing run returns a screenshot and the state so you can fix and 'rerun_failed'. Audio: plays are verified from the VM's run log (nothing is audible here).

### testing_manager.run_scenario

Run one scenario (a fresh project start is added automatically). Returns pass/fail per step; on failure also a screenshot and the final state.

| parameter | type | description |
| --- | --- | --- |
| `steps`* | [object] | list of {"do": ...} / {"expect": ...} steps (see tool description). |
| `name` | string | label for the report / when saving. |
| `save` | boolean | remember the scenario under `name` (also written to <projects>/tests/) so it can be re-run later. |
| `project` | string |  |

### testing_manager.define

Save a scenario under a name without running it.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `steps`* | [object] |  |
| `project` | string |  |

### testing_manager.list

Saved scenarios and whether their last run passed.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### testing_manager.delete

Delete a saved scenario.

| parameter | type | description |
| --- | --- | --- |
| `name`* | string |  |
| `project` | string |  |

### testing_manager.run_all

Run every saved scenario (or only those whose last run failed) against the project's current state.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |
| `only_failed` | boolean |  |

### testing_manager.rerun_failed

Re-run only the scenarios that failed last time - use after fixing the project.

| parameter | type | description |
| --- | --- | --- |
| `project` | string |  |

### testing_manager.quick

Ready-made tests. kind: keyboard (sprite, key, property, change=increase|decrease|differ) - hold a key, the property must change; click (sprite, + say text / variable+value) - click the sprite and expect `text` to be said or `variable` op value; collision (sprite, other, + variable/value optional) - move `sprite` onto `other`, expect touching (and variable check); variable (variable, op, value, seconds) - after the flag the variable must reach op value within seconds; broadcast (message, seconds) - after the flag the message must be sent within seconds; clones (sprite, minimum, seconds) - at least `minimum` clones of sprite appear within seconds; animation (sprite, minimum) - the sprite switches costume at least `minimum` times within seconds; audio (sound) - the sound is started within seconds; say (sprite, text) - the sprite says text within seconds.

| parameter | type | description |
| --- | --- | --- |
| `kind`* | string | one of the kinds above. |
| `project` | string |  |
| `sprite` | string |  |
| `key` | string |  |
| `property` | string |  |
| `change` | string |  |
| `hold` | number |  |
| `value` | Any |  |
| `op` | string |  |
| `name` | string |  |
| `other` | string |  |
| `variable` | string |  |
| `message` | string |  |
| `seconds` | number |  |
| `minimum` | integer |  |
| `sound` | string |  |
| `text` | string |  |
| `save` | boolean |  |

## export_manager

Deliver the work. Everything is written under <projects folder>/exports/. 'sb3' writes a verified copy of the project (then reopens it, validates it, compares it with the in-memory project and - if the runtime is installed - loads it in the real Scratch VM); 'sprite' writes a .sprite3; 'costume' / 'sound' write the asset file; 'screenshot' saves a stage PNG; 'video' RECORDS the running project to an MP4 (needs ffmpeg + the runtime; audio = the sounds the project started, mixed in at the right moment; Music-extension notes and text-to-speech are not included); 'verify' re-checks any exported .sb3. Scratch has no built-in video export - this one is produced by stepping the real VM frame by frame.

### export_manager.sb3

Write the project's CURRENT state (saved or not) to exports/<name>.sb3 and verify it (reopen, validate, compare, load in the VM).

| parameter | type | description |
| --- | --- | --- |
| `name` | string | file name without extension (default: project name + timestamp). |
| `project` | string |  |
| `overwrite` | boolean | replace an existing export of that name. |

### export_manager.verify

Re-check an exported .sb3 inside the projects folder: reopen, validate structure/assets, and load it in the VM.

| parameter | type | description |
| --- | --- | --- |
| `path`* | string |  |

### export_manager.sprite

Export one sprite as exports/<name>.sprite3 (costumes, sounds, scripts, local variables) and check that it imports back.

| parameter | type | description |
| --- | --- | --- |
| `sprite` | string |  |
| `project` | string |  |
| `name` | string |  |
| `overwrite` | boolean |  |

### export_manager.costume

Export a costume file (svg/png/jpg) to exports/. Use sprite='Stage' for a backdrop.

| parameter | type | description |
| --- | --- | --- |
| `costume` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### export_manager.sound

Export a sound file (wav) to exports/.

| parameter | type | description |
| --- | --- | --- |
| `sound` | string\|integer |  |
| `sprite` | string |  |
| `project` | string |  |

### export_manager.screenshot

Save the running stage as exports/<name>.png and also return the image.

| parameter | type | description |
| --- | --- | --- |
| `name` | string |  |
| `project` | string |  |
| `scale` | integer |  |

### export_manager.video

Record the project as an MP4: reload it, press the green flag, step the real VM frame by frame, capture the stage each frame (480x360), mix in the sounds the project started, encode with ffmpeg, then verify duration/resolution with ffprobe.

| parameter | type | description |
| --- | --- | --- |
| `seconds` | number | length of the recording in simulated seconds (max 900). |
| `name` | string | output name (exports/<name>.mp4). |
| `project` | string |  |
| `fps` | integer | 15-60 (the project itself always runs at 30 frames/second; other values repeat/skip frames). |
| `with_audio` | boolean | mix in sound-effect starts (no Music-extension notes or speech). |
| `inputs` | [object] | optional timed inputs while recording, e.g. [{"at": 2.5, "key": "space"}, {"at": 4, "click": [100, 50]}, {"at": 6, "answer": "Ada"}]. |
| `overwrite` | boolean |  |

## online_manager

Public, read-only Scratch website access: look up a shared project (title, author, stats, instructions, notes), a user's profile, and download a shared project as a local .sb3 you can edit. 'capabilities' lists what is and is NOT supported. NOT implemented, on purpose: logging in, saving/publishing to scratch.mit.edu, sharing/unsharing, remixing, posting comments, cloud variables. Scratch has no official, authorized API for those (only the website itself), and this server will not handle your Scratch password or session cookies or work around Scratch's security. To publish: export a .sb3 with export_manager and upload it yourself in the Scratch editor (File > Load from your computer, then Share).

### online_manager.capabilities

What this group can and cannot do.

### online_manager.project_info

Public metadata of a shared project: title, author, instructions, notes, dates, stats.

| parameter | type | description |
| --- | --- | --- |
| `project_id`* | string | the number, or a scratch.mit.edu/projects/<n> link. |

### online_manager.user_info

Public profile of a Scratch user.

| parameter | type | description |
| --- | --- | --- |
| `username`* | string |  |

### online_manager.import_project

Download a SHARED project (project.json + every costume/sound) as a new local project and open it. Scratch 2 (.sb2) projects are not supported.

| parameter | type | description |
| --- | --- | --- |
| `project_id`* | string | the number or link. |
| `name` | string | local name (default: 'scratch-<id>'). |


_18 tools, 214 actions._
