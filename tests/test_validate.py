import copy
import json

import pytest

from scratch_mcp.blocks import KNOWN_OPCODES, SPECS, MENUS
from scratch_mcp.validate import DuplicateKeyError, parse_project_json, validate_project

from .conftest import SAMPLE, read_sb3, target


@pytest.fixture
def sample():
    return read_sb3(SAMPLE)


def errors(project, assets=None):
    return validate_project(project, assets).errors


def test_sample_is_valid(sample):
    project, assets = sample
    result = validate_project(project, assets)
    assert result.ok, result.format()
    assert result.warnings == []


def test_catalog_is_consistent():
    for opcode in SPECS:
        assert opcode in KNOWN_OPCODES, opcode
    for opcode in MENUS:
        assert opcode in KNOWN_OPCODES, opcode


def test_duplicate_keys_detected():
    with pytest.raises(DuplicateKeyError, match="'abc'"):
        parse_project_json('{"targets": [{"blocks": {"abc": {}, "abc": {}}}]}')
    with pytest.raises(ValueError, match="Invalid JSON"):
        parse_project_json("{nope")
    with pytest.raises(ValueError, match="JSON object"):
        parse_project_json("[1, 2]")


def test_block_id_shared_between_sprites(sample):
    project, _ = sample
    cat, ball = target(project, "Cat"), target(project, "Ball")
    bid, block = next((k, v) for k, v in ball["blocks"].items() if v["opcode"] == "event_whenflagclicked")
    cat["blocks"][bid] = copy.deepcopy(block)
    cat["blocks"][bid]["next"] = None
    assert any("used in both" in e for e in errors(project))


def _cat_blocks(project):
    return target(project, "Cat")["blocks"]


def _find(blocks, opcode):
    return next((k, v) for k, v in blocks.items() if v["opcode"] == opcode)


def test_next_must_point_back(sample):
    project, _ = sample
    blocks = _cat_blocks(project)
    _, move = _find(blocks, "motion_movesteps")
    turn_id, turn = _find(blocks, "motion_turnright")
    # A second block also claims 'turn right' as its next.
    _, other = _find(blocks, "looks_nextcostume")
    other["next"] = turn_id
    errs = errors(project)
    assert any("linked from 2 places" in e for e in errs)
    assert any("that block's parent is" in e for e in errs)


def test_parent_must_link_back(sample):
    project, _ = sample
    blocks = _cat_blocks(project)
    move_id, move = _find(blocks, "motion_movesteps")
    hat_id, _ = _find(blocks, "event_whenbroadcastreceived")
    move["parent"] = hat_id
    assert any("does not link back" in e for e in errors(project))


def test_input_reference_must_exist_and_point_back(sample):
    project, _ = sample
    blocks = _cat_blocks(project)
    _, block = _find(blocks, "motion_movesteps")
    block["inputs"]["STEPS"] = [3, "ghost", [4, "10"]]
    assert any("points to missing block 'ghost'" in e for e in errors(project))


def test_toplevel_rules(sample):
    project, _ = sample
    blocks = _cat_blocks(project)
    _, move = _find(blocks, "motion_movesteps")
    move["topLevel"] = True
    assert any("must have parent null" in e for e in errors(project))
    project2, _ = read_sb3(SAMPLE)
    _, move2 = _find(_cat_blocks(project2), "motion_movesteps")
    move2["parent"] = None
    assert any("not topLevel but has no parent" in e for e in errors(project2))


def test_parent_loop_detected(sample):
    project, _ = sample
    blocks = _cat_blocks(project)
    a_id, a = _find(blocks, "motion_movesteps")
    b_id, b = _find(blocks, "motion_turnright")
    a["parent"], b["parent"] = b_id, a_id
    assert any("loop" in e for e in errors(project))


def test_primitives_checked(sample):
    project, _ = sample
    _, move = _find(_cat_blocks(project), "motion_movesteps")
    move["inputs"]["STEPS"] = [1, [99, "x"]]
    assert any("unknown primitive type 99" in e for e in errors(project))
    move["inputs"]["STEPS"] = [7]
    assert any("must look like [1|2|3" in e for e in errors(project))


def test_project_structure(sample):
    project, _ = sample
    assert errors([]) == ["project.json must be a JSON object"]
    assert errors({"targets": []}) == ["'targets' must be a non-empty list"]
    two_stages = copy.deepcopy(project)
    two_stages["targets"][1]["isStage"] = True
    assert any("exactly one Stage" in e for e in errors(two_stages))
    same_name = copy.deepcopy(project)
    same_name["targets"][2]["name"] = "Cat"
    assert any("must be unique" in e for e in errors(same_name))
    bad_costume = copy.deepcopy(project)
    bad_costume["targets"][1]["currentCostume"] = 5
    assert any("out of range" in e for e in errors(bad_costume))
    no_costumes = copy.deepcopy(project)
    no_costumes["targets"][1]["costumes"] = []
    assert any("at least one costume" in e for e in errors(no_costumes))


def test_missing_assets(sample):
    project, assets = sample
    assert any("not in the .sb3" in e for e in errors(project, assets - {"bcf454acf82e4504149f7ffe07081dbc.svg"}))


def test_warnings_for_undeclared_extension_and_variable(sample):
    project, assets = sample
    project = copy.deepcopy(project)
    project["extensions"] = []
    _, setvar = _find(target(project, "Ball")["blocks"], "data_setvariableto")
    setvar["fields"]["VARIABLE"] = ["nope", "missingVarId"]
    result = validate_project(project, assets)
    assert result.ok
    assert any("extension 'pen'" in w for w in result.warnings)
    assert any("variable 'nope'" in w for w in result.warnings)


def test_validation_message_is_readable(sample):
    project, _ = sample
    _find(_cat_blocks(project), "motion_movesteps")[1]["opcode"] = "bogus"
    text = validate_project(project).format()
    assert text.startswith("1 error(s):") and "unknown opcode 'bogus'" in text
    json.dumps(text)  # plain string
