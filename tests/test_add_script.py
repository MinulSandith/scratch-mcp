import json

import pytest

from scratch_mcp.render import render_target_scripts
from scratch_mcp.textparse import tokenize
from scratch_mcp.validate import validate_project
from scratch_mcp.workspace import WorkspaceError

from .conftest import read_sb3, target


@pytest.fixture
def blank(tools):
    tools.create_project("blank")
    return tools


def add(tools, script, sprite="Sprite1", project="blank", **kw):
    tools.add_script(project, sprite, script, **kw)
    data, assets = read_sb3(tools.ws.root / f"{project}.sb3")
    result = validate_project(data, assets)
    assert result.ok, result.format()
    return data


def blocks_of(project, name="Sprite1"):
    return target(project, name)["blocks"]


def by_opcode(blocks, opcode):
    found = [(k, v) for k, v in blocks.items() if v["opcode"] == opcode]
    assert found, f"no {opcode}"
    return found[0]


def chain(blocks, start):
    out = []
    while start:
        out.append(blocks[start]["opcode"])
        start = blocks[start]["next"]
    return out


# -- structure ---------------------------------------------------------------

def test_simple_script_links(blank):
    data = add(blank, "when flag clicked\nmove (10) steps\nsay [Hello!] for (2) seconds", x=100, y=-20)
    blocks = blocks_of(data)
    hat_id, hat = by_opcode(blocks, "event_whenflagclicked")
    assert hat["topLevel"] and hat["parent"] is None and (hat["x"], hat["y"]) == (100, -20)
    assert chain(blocks, hat_id) == ["event_whenflagclicked", "motion_movesteps", "looks_sayforsecs"]
    move_id, move = by_opcode(blocks, "motion_movesteps")
    assert move["parent"] == hat_id and move["inputs"] == {"STEPS": [1, [4, "10"]]}
    _, say = by_opcode(blocks, "looks_sayforsecs")
    assert say["parent"] == move_id
    assert say["inputs"] == {"MESSAGE": [1, [10, "Hello!"]], "SECS": [1, [4, "2"]]}
    assert len(set(blocks)) == len(blocks) == 3


def test_c_blocks_and_if_else(blank):
    data = add(blank, """when flag clicked
forever
  if <mouse down?> then
    turn right (15) degrees
  else
    turn left (15) degrees
    next costume
  end
end""")
    blocks = blocks_of(data)
    forever_id, forever = by_opcode(blocks, "control_forever")
    ifelse_id, ifelse = by_opcode(blocks, "control_if_else")
    assert forever["inputs"]["SUBSTACK"] == [2, ifelse_id] and ifelse["parent"] == forever_id
    assert forever["next"] is None
    cond_id = ifelse["inputs"]["CONDITION"][1]
    assert blocks[cond_id]["opcode"] == "sensing_mousedown" and blocks[cond_id]["parent"] == ifelse_id
    assert chain(blocks, ifelse["inputs"]["SUBSTACK"][1]) == ["motion_turnright"]
    assert chain(blocks, ifelse["inputs"]["SUBSTACK2"][1]) == ["motion_turnleft", "looks_nextcostume"]
    assert blocks[ifelse["inputs"]["SUBSTACK"][1]]["parent"] == ifelse_id


def test_indentation_without_end(blank):
    data = add(blank, """when flag clicked
repeat (3)
    move (5) steps
    turn right (5) degrees
say [done]""")
    blocks = blocks_of(data)
    rep_id, rep = by_opcode(blocks, "control_repeat")
    assert chain(blocks, rep["inputs"]["SUBSTACK"][1]) == ["motion_movesteps", "motion_turnright"]
    assert blocks[rep["next"]]["opcode"] == "looks_say"
    assert rep["inputs"]["TIMES"] == [1, [6, "3"]]


def test_multiple_scripts_and_empty_c_block(blank):
    data = add(blank, "when flag clicked\nforever\nend\n\nwhen this sprite clicked\nhide")
    blocks = blocks_of(data)
    tops = [b for b in blocks.values() if b["topLevel"]]
    assert len(tops) == 2
    assert "SUBSTACK" not in by_opcode(blocks, "control_forever")[1]["inputs"]


def test_nested_reporters_and_operators(blank):
    data = add(blank, "say (join [x is ] ((x position) + (1)))\nif <<(x position) > (100)> and <not <(y position) < (0)>>> then\nend")
    blocks = blocks_of(data)
    join_id, join = by_opcode(blocks, "operator_join")
    assert join["inputs"]["STRING1"] == [1, [10, "x is "]]
    add_id = join["inputs"]["STRING2"][1]
    assert join["inputs"]["STRING2"] == [3, add_id, [10, ""]]
    assert blocks[add_id]["opcode"] == "operator_add" and blocks[add_id]["parent"] == join_id
    xpos = blocks[blocks[add_id]["inputs"]["NUM1"][1]]
    assert xpos["opcode"] == "motion_xposition"
    _, and_ = by_opcode(blocks, "operator_and")
    assert blocks[and_["inputs"]["OPERAND1"][1]]["opcode"] == "operator_gt"
    not_ = blocks[and_["inputs"]["OPERAND2"][1]]
    assert not_["opcode"] == "operator_not"
    assert blocks[not_["inputs"]["OPERAND"][1]]["opcode"] == "operator_lt"


def test_menus_and_fields(blank):
    data = add(blank, """go to (mouse-pointer v)
go to (pick random (1) to (2))
set rotation style [left-right v]
set [ghost v] effect to (50)
set [pitch v] effect to (100)
switch costume to (costume2 v)
start sound (Meow v)
stop [other scripts in sprite v]
stop [all v]""")
    blocks = blocks_of(data)
    gotos = [b for b in blocks.values() if b["opcode"] == "motion_goto"]
    first, second = sorted(gotos, key=lambda b: b["inputs"]["TO"][0])
    shadow = blocks[first["inputs"]["TO"][1]]
    assert first["inputs"]["TO"][0] == 1
    assert shadow == {**shadow, "opcode": "motion_goto_menu", "shadow": True, "fields": {"TO": ["_mouse_", None]}}
    assert second["inputs"]["TO"][0] == 3
    assert blocks[second["inputs"]["TO"][1]]["opcode"] == "operator_random"
    assert blocks[second["inputs"]["TO"][2]]["fields"] == {"TO": ["_random_", None]}
    assert by_opcode(blocks, "motion_setrotationstyle")[1]["fields"] == {"STYLE": ["left-right", None]}
    assert by_opcode(blocks, "looks_seteffectto")[1]["fields"] == {"EFFECT": ["GHOST", None]}
    assert by_opcode(blocks, "sound_seteffectto")[1]["fields"] == {"EFFECT": ["PITCH", None]}
    stops = {b["fields"]["STOP_OPTION"][0]: b["mutation"]["hasnext"] for b in blocks.values() if b["opcode"] == "control_stop"}
    assert stops == {"other scripts in sprite": "true", "all": "false"}


def test_ambiguous_templates_resolved(blank):
    data = add(blank, """say ([sqrt v] of (9))
say ([x position v] of (Sprite1 v))
say (length of [hello])
say (length of [items v])
say <[abc] contains [b]?>
say <[items v] contains [b]?>""")
    blocks = blocks_of(data)
    ops = {b["opcode"] for b in blocks.values()}
    assert {"operator_mathop", "sensing_of", "operator_length", "data_lengthoflist",
            "operator_contains", "data_listcontainsitem"} <= ops
    _, of = by_opcode(blocks, "sensing_of")
    assert of["fields"]["PROPERTY"] == ["x position", None]
    assert blocks[of["inputs"]["OBJECT"][1]]["fields"]["OBJECT"] == ["Sprite1", None]


def test_hat_with_comparison_and_keys(blank):
    data = add(blank, "when [loudness v] > (10)\nhide\n\nwhen [up arrow v] key pressed\nchange y by (10)")
    blocks = blocks_of(data)
    assert by_opcode(blocks, "event_whengreaterthan")[1]["fields"] == {"WHENGREATERTHANMENU": ["LOUDNESS", None]}
    assert by_opcode(blocks, "event_whenkeypressed")[1]["fields"] == {"KEY_OPTION": ["up arrow", None]}


def test_variables_lists_broadcasts(tools, root):
    out = tools.add_script("sample", "Ball", """when I receive [Game Over v]
set [speed v] to (0)
change [lives v] by (-1)
add (lives) to [history v]
broadcast [restart v]""")
    assert "Created variables (for all sprites): lives" in out
    assert "Created lists (for all sprites): history" in out
    assert "Created broadcast messages: restart" in out
    assert "game over" not in out.split("Created broadcast")[1]  # reused, case-insensitive
    data, assets = read_sb3(root / "sample.sb3")
    assert validate_project(data, assets).ok
    stage, ball = target(data, "Stage"), target(data, "Ball")
    blocks = ball["blocks"]
    setvar = [b for b in blocks.values() if b["opcode"] == "data_setvariableto"
              and b["fields"]["VARIABLE"][1] == "ballSpeedVarId0001"]
    assert setvar, "should use Ball's local 'speed' variable"
    lives_id = next(k for k, v in stage["variables"].items() if v[0] == "lives")
    _, addl = by_opcode(blocks, "data_addtolist")
    assert addl["inputs"]["ITEM"] == [3, [12, "lives", lives_id], [10, ""]]
    assert "history" in [v[0] for v in stage["lists"].values()]
    hat = by_opcode(blocks, "event_whenbroadcastreceived")[1]
    assert hat["fields"]["BROADCAST_OPTION"][0] == "game over"
    assert stage["broadcasts"][hat["fields"]["BROADCAST_OPTION"][1]] == "game over"


def test_custom_blocks(blank):
    data = add(blank, """define jump (height) <spin>  // run without screen refresh
change y by (height)
if <spin> then
  turn right (360) degrees
end

when flag clicked
jump (10) <mouse down?>
jump ((5) * (2)) <>""")
    blocks = blocks_of(data)
    def_id, definition = by_opcode(blocks, "procedures_definition")
    proto_id = definition["inputs"]["custom_block"][1]
    proto = blocks[proto_id]
    assert proto["opcode"] == "procedures_prototype" and proto["shadow"] and proto["parent"] == def_id
    m = proto["mutation"]
    assert m["proccode"] == "jump %s %b" and m["warp"] == "true"
    arg_ids = json.loads(m["argumentids"])
    assert json.loads(m["argumentnames"]) == ["height", "spin"]
    assert json.loads(m["argumentdefaults"]) == ["", "false"]
    for arg_id in arg_ids:
        assert blocks[proto["inputs"][arg_id][1]]["parent"] == proto_id
    _, change = by_opcode(blocks, "motion_changeyby")
    reporter = blocks[change["inputs"]["DY"][1]]
    assert reporter["opcode"] == "argument_reporter_string_number" and reporter["fields"]["VALUE"] == ["height", None]
    calls = [b for b in blocks.values() if b["opcode"] == "procedures_call"]
    assert len(calls) == 2
    for call in calls:
        assert call["mutation"]["proccode"] == "jump %s %b"
        assert json.loads(call["mutation"]["argumentids"]) == arg_ids
    first = next(c for c in calls if arg_ids[1] in c["inputs"])
    assert first["inputs"][arg_ids[0]] == [1, [10, "10"]]
    assert blocks[first["inputs"][arg_ids[1]][1]]["opcode"] == "sensing_mousedown"


def test_call_existing_custom_block(tools, root):
    tools.add_script("sample", "Cat", "when [d v] key pressed\ndraw square (100)")
    data, _ = read_sb3(root / "sample.sb3")
    calls = [b for b in target(data, "Cat")["blocks"].values() if b["opcode"] == "procedures_call"]
    assert len(calls) == 2


def test_extension_is_enabled(blank):
    data = add(blank, "pen down\nset pen (color v) to (50)\nplay note (60) for (0.5) beats")
    assert data["extensions"] == ["pen", "music"]
    blocks = blocks_of(data)
    _, setp = by_opcode(blocks, "pen_setPenColorParamTo")
    assert blocks[setp["inputs"]["COLOR_PARAM"][1]]["fields"] == {"colorParam": ["color", None]}
    _, note = by_opcode(blocks, "music_playNoteForBeats")
    assert blocks[note["inputs"]["NOTE"][1]]["fields"] == {"NOTE": ["60", None]}


def test_stage_scripts(blank):
    data = add(blank, "when stage clicked\nswitch backdrop to (backdrop1 v)", sprite="Stage")
    assert by_opcode(blocks_of(data, "Stage"), "event_whenstageclicked")


def test_escaped_text(blank):
    data = add(blank, r"say [a \] b \\ c]")
    _, say = by_opcode(blocks_of(data), "looks_say")
    assert say["inputs"]["MESSAGE"] == [1, [10, "a ] b \\ c"]]
    assert render_target_scripts(target(data, "Sprite1")) == [r"say [a \] b \\ c]"]


def test_new_script_placed_below_existing(blank):
    add(blank, "when flag clicked\nmove (1) steps")
    data = add(blank, "when this sprite clicked\nhide")
    tops = sorted((b for b in blocks_of(data).values() if b["topLevel"]), key=lambda b: b["y"])
    assert tops[1]["y"] > tops[0]["y"]


def test_success_makes_backup(tools, root):
    before = (root / "sample.sb3").read_bytes()
    out = tools.add_script("sample", "Cat", "when flag clicked\nshow")
    assert "backed up to backups/sample." in out
    (backup,) = (root / "backups").glob("sample.*.sb3")
    assert backup.read_bytes() == before


# -- round trip --------------------------------------------------------------

@pytest.mark.parametrize("name", ["Stage", "Cat", "Ball"])
def test_round_trip_sample_scripts(tools, root, name):
    """Rendering a sprite's scripts and adding them back gives identical scripts."""
    project = json.loads(tools.get_project_json("sample"))
    original = render_target_scripts(target(project, name))
    target(project, name)["blocks"] = {}
    tools.save_project_json("sample", json.dumps(project))
    tools.add_script("sample", name, "\n\n".join(original))
    data, assets = read_sb3(root / "sample.sb3")
    assert validate_project(data, assets).ok
    assert sorted(render_target_scripts(target(data, name))) == sorted(original)


# -- errors ------------------------------------------------------------------

@pytest.mark.parametrize("script, message", [
    ("move (10) stepz", r"Unknown block.*Did you mean: move \(\) steps"),
    ("when flag clicked\nmove (10) steps\nwhen this sprite clicked", "hat block and must start a script"),
    ("forever\nend\nmove (1) steps", "nothing can come after 'control_forever'"),
    ("move (1) steps\nend", "'end' without a matching C block"),
    ("repeat (2)\nelse\nend", "'else' must follow an 'if"),
    ("x position", "reporter block"),
    ("say (join [a] [b]", "missing '\\)'"),
    ("say [oops", "missing '\\]'"),
    ("if <foo bar?> then\nend", "Unknown boolean block"),
    ("define (x)", "needs a block name"),
    ("define f (a) (a)", "must be different"),
    ("", "No blocks found"),
])
def test_parse_errors_are_reported_and_nothing_saved(blank, script, message):
    path = blank.ws.root / "blank.sb3"
    before = path.read_bytes()
    with pytest.raises(WorkspaceError, match=message):
        blank.add_script("blank", "Sprite1", script)
    assert path.read_bytes() == before
    assert not (blank.ws.root / "backups").exists()


def test_errors_include_line_numbers_and_syntax_help(blank):
    with pytest.raises(WorkspaceError) as exc:
        blank.add_script("blank", "Sprite1", "when flag clicked\njump around")
    assert "Line 2" in str(exc.value) and "Script text format" in str(exc.value)


def test_sprite_only_blocks_rejected_on_stage(blank):
    with pytest.raises(WorkspaceError, match="only works on sprites"):
        blank.add_script("blank", "Stage", "move (10) steps")


def test_unknown_sprite(blank):
    with pytest.raises(WorkspaceError, match="No sprite named 'Dog'. Available: Stage, Sprite1"):
        blank.add_script("blank", "Dog", "move (10) steps")


def test_duplicate_define_rejected(tools):
    with pytest.raises(WorkspaceError, match="already defined"):
        tools.add_script("sample", "Cat", "define draw square (size)\nhide")


def test_tokenizer_brackets():
    tokens, comment = tokenize("if <(a) < (b)> then // note")
    assert comment == "note"
    assert [type(t).__name__ for t in tokens] == ["Word", "Arg", "Word"]
    inner = tokens[1].children
    assert [getattr(t, "text", None) for t in inner] == [None, "<", None]
