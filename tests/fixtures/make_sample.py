"""Regenerate tests/fixtures/sample.sb3.

    python tests/fixtures/make_sample.py OUT_DIR

builds OUT_DIR/sample.sb3 with scratch-mcp itself. The committed fixture was then
loaded into scratch-vm and re-saved with ``vm.saveProjectSb3()`` so the file in
the repo is serialized by Scratch's own code (see tests/fixtures/README.md).
"""

from __future__ import annotations

import copy
import json
import sys

from scratch_mcp.server import ScratchTools

CAT_SCRIPTS = """\
when flag clicked
go to x: (0) y: (0)
set [score v] to (0)
delete all of [hits v]
pen down
set pen color to [#ff8800]
repeat (36)
  move (10) steps
  turn right (10) degrees
  add (x position) to [hits v]
end
pen up
say (join [Done: ] (length of [hits v])) for (2) seconds
broadcast (game over v) and wait

when this sprite clicked
change [score v] by (1)
if <(score) > (10)> then
  switch costume to (costume2 v)
else
  next costume
end
play sound (Meow v) until done

when I receive [game over v]
draw square (50)

define draw square (size)
repeat (4)
  move (size) steps
  turn left (90) degrees
end
"""

STAGE_SCRIPT = """\
when flag clicked
reset timer
wait until <(timer) > (5)>
stop [all v]
"""

BALL_SCRIPT = """\
when flag clicked
set [speed v] to (2)
forever
  point towards (Cat v)
  move (speed) steps
  if <touching (Cat v)?> then
    broadcast (game over v)
    set [ghost v] effect to (50)
  end
end
"""


def main(out_dir: str) -> None:
    tools = ScratchTools(out_dir)
    tools.create_project("sample", sprite_name="Cat")
    tools.add_script("sample", "Cat", CAT_SCRIPTS)
    tools.add_script("sample", "Stage", STAGE_SCRIPT)

    # Add a second sprite "Ball" (re-using the cat costume) with a local variable.
    project = json.loads(tools.get_project_json("sample"))
    cat = project["targets"][1]
    ball = copy.deepcopy(cat)
    ball.update(name="Ball", blocks={}, x=120, y=80, layerOrder=2,
                variables={"ballSpeedVarId0001": ["speed", 0]})
    ball["costumes"] = ball["costumes"][:1]
    project["targets"].append(ball)
    stage = project["targets"][0]
    stage["lists"]["hits"] = stage["lists"].pop(next(iter(stage["lists"])))  # stable id
    for target in project["targets"]:
        for block in target["blocks"].values():
            if "LIST" in block.get("fields", {}):
                block["fields"]["LIST"][1] = "hits"
            for inp in block.get("inputs", {}).values():
                for v in inp[1:]:
                    if isinstance(v, list) and v[0] == 13:
                        v[2] = "hits"
    stage["lists"]["hits"] = ["hits", ["3", "7"]]
    tools.save_project_json("sample", json.dumps(project))
    tools.add_script("sample", "Ball", BALL_SCRIPT)


if __name__ == "__main__":
    main(sys.argv[1])
