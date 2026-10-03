import json

import pytest

from scratch_mcp.engine import EngineError, Graph
from scratch_mcp.template import blank_project
from scratch_mcp.validate import validate_project
from scratch_mcp.workspace import WorkspaceError

from .conftest import call


@pytest.fixture
def g():
    project, assets = blank_project()
    graph = Graph(project, project["targets"][1])
    graph.assets = assets
    return graph


def check(g):
    r = validate_project(g.project, set(g.assets))
    assert r.ok, r.format()
    assert g.validate() == [] or all("never runs" in p for p in g.validate()), g.validate()


def op(opcode, inputs=None, fields=None, nxt=None):
    t = {"opcode": opcode}
    if inputs:
        t["inputs"] = inputs
    if fields:
        t["fields"] = fields
    if nxt:
        t["next"] = nxt
    return t


def script(g, x=0, y=0):
    ids = g.add(op("event_whenflagclicked", nxt=[
        op("motion_movesteps", {"STEPS": 10}),
        op("control_repeat", {"TIMES": 3, "SUBSTACK": [op("looks_nextcostume"), op("motion_turnright", {"DEGREES": 15})]}),
        op("looks_hide"),
    ]), x=x, y=y)
    return ids[0]


def stack(g, first):
    return [g.blocks[i]["opcode"] for i in g.stack_ids(first)]


def test_build_links_and_shadows(g):
    top = script(g)
    check(g)
    b = g.blocks
    assert stack(g, top) == ["event_whenflagclicked", "motion_movesteps", "control_repeat", "looks_hide"]
    move = b[b[top]["next"]]
    assert move["inputs"]["STEPS"] == [1, [4, "10"]] and move["parent"] == top
    rep = b[move["next"]]
    assert rep["inputs"]["TIMES"] == [1, [6, "3"]]
    inner = rep["inputs"]["SUBSTACK"][1]
    assert stack(g, inner) == ["looks_nextcostume", "motion_turnright"] and b[inner]["parent"] == move["next"]
    assert b[top]["topLevel"] and not b[inner]["topLevel"]


def test_literals_menus_fields_and_variables(g):
    g.add(op("looks_switchcostumeto", {"COSTUME": "costume2"}))
    g.add(op("motion_goto", {"TO": "_mouse_"}))
    g.add(op("looks_seteffectto", {"VALUE": 50}, {"EFFECT": "ghost"}))
    g.add(op("data_setvariableto", {"VALUE": {"opcode": "operator_add", "inputs": {"NUM1": 1, "NUM2": {"variable": "score"}}}},
             {"VARIABLE": "score"}))
    g.add(op("event_broadcast", {"BROADCAST_INPUT": "go"}))
    g.add(op("pen_setPenColorToColor", {"COLOR": "#FF8800"}))
    g.add(op("music_playNoteForBeats", {"NOTE": 64, "BEATS": 0.5}))
    check(g)
    blocks = g.blocks
    sw = next(b for b in blocks.values() if b["opcode"] == "looks_switchcostumeto")
    assert blocks[sw["inputs"]["COSTUME"][1]]["fields"] == {"COSTUME": ["costume2", None]}
    gt = next(b for b in blocks.values() if b["opcode"] == "motion_goto")
    assert blocks[gt["inputs"]["TO"][1]]["fields"]["TO"] == ["_mouse_", None]
    assert next(b for b in blocks.values() if b["opcode"] == "looks_seteffectto")["fields"]["EFFECT"] == ["GHOST", None]
    setv = next(b for b in blocks.values() if b["opcode"] == "data_setvariableto")
    vid = setv["fields"]["VARIABLE"][1]
    assert g.stage["variables"][vid] == ["score", 0]
    add = blocks[setv["inputs"]["VALUE"][1]]
    assert add["inputs"]["NUM2"] == [3, [12, "score", vid], [4, ""]] or add["inputs"]["NUM2"][1] == [12, "score", vid]
    assert next(b for b in blocks.values() if b["opcode"] == "event_broadcast")["inputs"]["BROADCAST_INPUT"][1][0] == 11
    assert "pen" in g.project["extensions"] and "music" in g.project["extensions"]
    assert next(b for b in blocks.values() if b["opcode"] == "pen_setPenColorToColor")["inputs"]["COLOR"] == [1, [9, "#ff8800"]]


@pytest.mark.parametrize("tree, message", [
    ({"opcode": "motion_teleport"}, "Unknown opcode"),
    ({"opcode": "motion_movesteps", "inputs": {"STEPS": "lots"}}, "expects a number"),
    ({"opcode": "motion_movesteps", "inputs": {"SPEED": 1}}, "no input"),
    ({"opcode": "looks_seteffectto", "fields": {"EFFECT": "sparkle"}, "inputs": {"VALUE": 1}}, "not a valid value"),
    ({"opcode": "control_if", "inputs": {"CONDITION": 5}}, "needs a boolean"),
    ({"opcode": "control_if", "inputs": {"CONDITION": {"opcode": "operator_add"}}}, "needs a boolean block"),
    ({"opcode": "motion_movesteps", "inputs": {"STEPS": {"opcode": "looks_hide"}}}, "needs a reporter"),
    ({"opcode": "control_forever", "next": [{"opcode": "looks_hide"}]}, "cap block"),
    ({"opcode": "looks_hide", "next": [{"opcode": "event_whenflagclicked"}]}, "can't be placed"),
    ({"opcode": "control_repeat", "inputs": {"SUBSTACK": [{"opcode": "event_whenflagclicked"}]}}, "can't start a C-block"),
    ({"opcode": "pen_setPenColorToColor", "inputs": {"COLOR": "red"}}, "colour like"),
    ({"opcode": "control_stop", "fields": {"STOP_OPTION": "later"}}, "not a valid value"),
    ({"opcode": "procedures_call"}, "procedure helpers|Unknown|special"),
])
def test_invalid_trees_are_rejected_and_leave_no_residue(g, tree, message):
    before = json.dumps(g.blocks, sort_keys=True)
    with pytest.raises(EngineError, match=message):
        g.add(tree)
    assert json.dumps(g.blocks, sort_keys=True) == before


def test_stage_rules(g):
    stage = Graph(g.project, g.stage)
    with pytest.raises(EngineError, match="only works on sprites"):
        stage.add(op("motion_movesteps", {"STEPS": 1}))
    with pytest.raises(EngineError, match="only works on the Stage"):
        g.add(op("event_whenstageclicked"))


def test_insert_after_keeps_tail(g):
    top = script(g)
    mv = g.blocks[top]["next"]
    g.add(op("looks_show", nxt=[op("looks_say", {"MESSAGE": "hi"})]), after=top)
    check(g)
    assert stack(g, top) == ["event_whenflagclicked", "looks_show", "looks_say", "motion_movesteps", "control_repeat", "looks_hide"]
    assert g.blocks[mv]["parent"] == g.stack_ids(top)[2]


def test_insert_into_c_block_pushes_existing_blocks_down(g):
    top = script(g)
    rep = g.stack_ids(top)[2]
    g.add(op("looks_think", {"MESSAGE": "hm"}), into=rep)
    check(g)
    inner = g.blocks[rep]["inputs"]["SUBSTACK"][1]
    assert stack(g, inner) == ["looks_think", "looks_nextcostume", "motion_turnright"]
    with pytest.raises(EngineError, match="no statement input"):
        g.add(op("looks_show"), into=rep, input="SUBSTACK2")


def test_replace_input_with_reporter_keeps_shadow(g):
    top = script(g)
    mv = g.blocks[top]["next"]
    g.add(op("motion_xposition"), replace_input_of=mv, input="STEPS")
    check(g)
    inp = g.blocks[mv]["inputs"]["STEPS"]
    assert inp[0] == 3 and g.blocks[inp[1]]["opcode"] == "motion_xposition" and inp[2] == [4, "10"]
    # and boolean slots need booleans
    g.add(op("control_wait_until"), x=300, y=300)
    wid = next(i for i, b in g.blocks.items() if b["opcode"] == "control_wait_until")
    with pytest.raises(EngineError, match="boolean"):
        g.add(op("motion_xposition"), replace_input_of=wid, input="CONDITION")
    g.add(op("sensing_mousedown"), replace_input_of=wid, input="CONDITION")
    check(g)
    assert g.blocks[wid]["inputs"]["CONDITION"][0] == 2


def test_delete_modes(g):
    top = script(g)
    ids = g.stack_ids(top)
    g.delete(ids[1], mode="single")  # remove move steps; the rest reconnects
    check(g)
    assert stack(g, top) == ["event_whenflagclicked", "control_repeat", "looks_hide"]
    rep = g.stack_ids(top)[1]
    removed = g.delete(rep, mode="stack")
    assert len(removed) >= 4
    check(g)
    assert stack(g, top) == ["event_whenflagclicked"]
    assert not any(b["opcode"] in ("looks_nextcostume", "motion_turnright", "looks_hide") for b in g.blocks.values())


def test_delete_reporter_restores_shadow(g):
    g.add(op("motion_movesteps", {"STEPS": op("operator_random", {"FROM": 1, "TO": 5})}))
    mv = next(i for i, b in g.blocks.items() if b["opcode"] == "motion_movesteps")
    rid = g.blocks[mv]["inputs"]["STEPS"][1]
    g.delete(rid)
    check(g)
    assert g.blocks[mv]["inputs"]["STEPS"] == [1, [4, ""]] or g.blocks[mv]["inputs"]["STEPS"][0] == 1
    assert not any(b["opcode"] == "operator_random" for b in g.blocks.values())


def test_move_and_disconnect(g):
    top = script(g)
    ids = g.stack_ids(top)
    # move the "hide" block after the hat (moves just itself because it is last)
    g.move(ids[3], after=top)
    check(g)
    assert stack(g, top) == ["event_whenflagclicked", "looks_hide", "motion_movesteps", "control_repeat"]
    # disconnect from "repeat" down
    rep = g.stack_ids(top)[3]
    g.detach(rep, 500, 40)
    check(g)
    assert g.blocks[rep]["topLevel"] and (g.blocks[rep]["x"], g.blocks[rep]["y"]) == (500, 40)
    assert stack(g, top) == ["event_whenflagclicked", "looks_hide", "motion_movesteps"]
    # single move leaves the tail behind
    first_inner = g.blocks[rep]["inputs"]["SUBSTACK"][1]
    g.move(first_inner, x=10, y=10, single=True)
    check(g)
    assert stack(g, g.blocks[rep]["inputs"]["SUBSTACK"][1]) == ["motion_turnright"]
    # a move that breaks a rule rolls back
    before = json.dumps(g.blocks, sort_keys=True)
    with pytest.raises(EngineError, match="cap|hat"):
        g.move(top, after=g.stack_ids(top)[1])
    assert json.dumps(g.blocks, sort_keys=True) == before


def test_cannot_nest_block_inside_itself(g):
    top = script(g)
    rep = g.stack_ids(top)[2]
    with pytest.raises(EngineError):
        g.move(rep, into=rep)
    with pytest.raises(EngineError):
        g.move(top, into=rep)  # a script can't be put inside its own C block


def test_duplicate_gets_fresh_ids(g):
    top = script(g)
    new = g.duplicate(top, x=300, y=50)
    check(g)
    assert new != top and stack(g, new) == stack(g, top)
    assert not set(g.subtree_ids(new, include_next=True)) & set(g.subtree_ids(top, include_next=True))
    assert g.blocks[new]["x"] == 300


def test_set_input_and_field(g):
    top = script(g)
    mv = g.blocks[top]["next"]
    g.set_input(mv, "STEPS", 99)
    assert g.blocks[mv]["inputs"]["STEPS"] == [1, [4, "99"]]
    g.set_input(mv, "STEPS", op("operator_add", {"NUM1": 1, "NUM2": 2}))
    assert g.blocks[g.blocks[mv]["inputs"]["STEPS"][1]]["opcode"] == "operator_add"
    g.set_input(mv, "STEPS", 5)  # replaces the reporter, which is deleted
    assert not any(b["opcode"] == "operator_add" for b in g.blocks.values())
    rep = g.stack_ids(top)[2]
    g.set_input(rep, "SUBSTACK", [op("looks_hide")])
    assert stack(g, g.blocks[rep]["inputs"]["SUBSTACK"][1]) == ["looks_hide"]
    g.add(op("looks_seteffectto", {"VALUE": 1}, {"EFFECT": "ghost"}), x=0, y=0)
    eid = next(i for i, b in g.blocks.items() if b["opcode"] == "looks_seteffectto")
    g.set_field(eid, "EFFECT", "Whirl")
    assert g.blocks[eid]["fields"]["EFFECT"] == ["WHIRL", None]
    with pytest.raises(EngineError):
        g.set_field(eid, "EFFECT", "nope")
    with pytest.raises(EngineError):
        g.set_input(eid, "NOPE", 1)
    check(g)


def test_round_trip_tree(g):
    top = script(g)
    g.add(op("control_if_else", {"CONDITION": op("operator_gt", {"OPERAND1": {"variable": "x"}, "OPERAND2": 5}),
                                 "SUBSTACK": [op("looks_say", {"MESSAGE": "big"})],
                                 "SUBSTACK2": [op("looks_say", {"MESSAGE": {"variable": "x"}})]}), x=0, y=400)
    for tid in g.top_levels():
        tree = g.to_tree(tid)
        project, assets = blank_project()
        g2 = Graph(project, project["targets"][1])
        g2.stage["variables"] = dict(g.stage["variables"])
        new = g2.add(tree)[0]
        assert g2.to_tree(new) == tree


def test_custom_blocks(g):
    did = g.define_procedure("jump %s %b", ["height", "fast"], warp=True)
    g.add([op("motion_changeyby", {"DY": {"opcode": "argument_reporter_string_number", "fields": {"VALUE": "height"}}}),
           op("control_if", {"CONDITION": {"opcode": "argument_reporter_boolean", "fields": {"VALUE": "fast"}},
                             "SUBSTACK": [op("motion_changeyby", {"DY": 5})]})], after=did)
    g.add({"opcode": "event_whenflagclicked", "next": [{"call": "jump %s %b", "args": [10, op("sensing_mousedown")]}]}, x=400, y=0)
    check(g)
    proc = g.procedures()["jump %s %b"]
    assert proc["argumentnames"] == ["height", "fast"] and proc["warp"]
    call_block = next(b for b in g.blocks.values() if b["opcode"] == "procedures_call")
    aid_text, aid_bool = proc["argumentids"]
    assert call_block["inputs"][aid_text] == [1, [10, "10"]]
    assert call_block["inputs"][aid_bool][0] == 2
    with pytest.raises(EngineError, match="already exists"):
        g.define_procedure("jump %s %b", ["a", "b"])
    with pytest.raises(EngineError, match="takes 2 argument"):
        g.add({"call": "jump %s %b", "args": [1]})
    with pytest.raises(EngineError, match="No custom block"):
        g.add({"call": "fly"})


def test_comments(g):
    top = script(g)
    cid = g.add_comment("hello", block=top)
    assert g.target["comments"][cid]["blockId"] == top and g.blocks[top]["comment"] == cid
    free = g.add_comment("note", x=10, y=20)
    g.edit_comment(free, text="changed", minimized=True)
    assert g.target["comments"][free]["text"] == "changed" and g.target["comments"][free]["minimized"]
    g.delete(top, mode="stack")  # deleting the block removes its comment
    assert cid not in g.target["comments"]
    g.delete_comment(free)
    assert not g.target["comments"]
    check(g)


def test_validate_reports_rule_violations(g):
    g.add(op("looks_hide"), x=0, y=0)
    top = script(g, x=400)
    # sneak in a hat in the middle of a stack
    mid = g.stack_ids(top)[1]
    g.blocks[mid]["opcode"] = "event_whenkeypressed"
    probs = g.validate()
    assert any("hat block is not at the start" in p for p in probs)


# ---- through the MCP-level action layer -------------------------------------

def test_script_and_block_manager_actions(ctx):
    call(ctx, "project_manager", "open", name="sample")
    r = call(ctx, "script_manager", "add_tree", sprite="Ball", scripts=[
        op("event_whenkeypressed", fields={"KEY_OPTION": "space"}, nxt=[op("motion_changeyby", {"DY": 20})])])
    assert r["scripts_added"] == 1 and "when [space v] key pressed" in r["text"]
    tid = r["script_ids"][0]
    got = call(ctx, "script_manager", "get_script", id=tid, sprite="Ball", with_ids=True)
    assert got["tree"]["next"][0]["opcode"] == "motion_changeyby"
    inner = got["tree"]["next"][0]["id"]
    call(ctx, "block_manager", "add", sprite="Ball", blocks=[op("motion_changeyby", {"DY": -20})], after=inner)
    scripts = call(ctx, "script_manager", "list_scripts", sprite="Ball")["scripts"]
    assert any("change y by (-20)" in s["text"] for s in scripts)
    call(ctx, "block_manager", "set_field", sprite="Ball", id=tid, name="KEY_OPTION", value="up arrow")
    assert "up arrow" in call(ctx, "script_manager", "get_script", id=tid, sprite="Ball")["text"]
    with pytest.raises(WorkspaceError, match="Not applied"):
        call(ctx, "block_manager", "add", sprite="Ball", blocks=[op("looks_hide")], after="nonexistent")
    assert call(ctx, "block_manager", "validate", sprite="Ball")["ok"]
    cat = call(ctx, "block_manager", "catalog", category="pen")
    assert cat["count"] >= 13
    assert call(ctx, "block_manager", "describe", opcode="motion_movesteps")["inputs"]["STEPS"]["shadow"] == "math_number"
    with pytest.raises(WorkspaceError, match="Unknown opcode"):
        call(ctx, "block_manager", "describe", opcode="nope_nope")
