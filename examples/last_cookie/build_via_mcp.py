"""Build "The Last Cookie" (a 30 second Scratch cartoon) using ONLY scratch-mcp tool calls.

This is what Claude does through Claude Desktop: it starts the real server over stdio and calls
the tools. Nothing here edits the .sb3 directly.

    python examples/last_cookie/build_via_mcp.py PROJECTS_DIR

Timeline (the Stage broadcasts scene1..scene6 on a timer so the scenes can't drift apart):
  0-5 kitchen, robot notices cookie | 5-10 robot approaches | 10-15 alien pops in
  15-20 stare-down | 20-25 tug of war | 25-30 cookie breaks, they share it
"""

from __future__ import annotations

import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT = "The Last Cookie"

# Positions (Scratch stage: 480x360, centre 0,0).
ROBOT_Y, COOKIE_Y, ALIEN_Y = -60, -50, -32

STAGE_SCRIPTS = [
    """when flag clicked
switch backdrop to (kitchen1 v)
reset timer
start sound (music v)
wait (0.2) seconds
broadcast (scene1 v)
wait until <(timer) > (5)>
broadcast (scene2 v)
wait until <(timer) > (10)>
broadcast (scene3 v)
wait until <(timer) > (15)>
broadcast (scene4 v)
wait until <(timer) > (20)>
broadcast (scene5 v)
wait until <(timer) > (25)>
broadcast (scene6 v)
wait until <(timer) > (30)>
stop [all v]

when flag clicked
forever
  switch backdrop to (kitchen1 v)
  wait (0.5) seconds
  switch backdrop to (kitchen2 v)
  wait (0.5) seconds
end

when I receive [scene6 v]
wait (2) seconds
start sound (chime v)""",
]

TITLE_SCRIPT = f"""when flag clicked
set [ghost v] effect to (0)
go to x: (0) y: (125)
show
wait (1.8) seconds
repeat (10)
  change [ghost v] effect by (10)
  wait (0.05) seconds
end
hide"""

ROBOT_SCRIPT = f"""when flag clicked
go to x: (-150) y: ({ROBOT_Y})
point in direction (90)
set size to (100) %
switch costume to (idle v)
show

when I receive [scene1 v]
wait (1) seconds
repeat (2)
  switch costume to (idle v)
  wait (0.5) seconds
  switch costume to (blink v)
  wait (0.12) seconds
end
switch costume to (idle v)
say [Beep boop... so quiet.] for (1.1) seconds
switch costume to (wow v)
start sound (boing v)
say [A COOKIE!] for (1.3) seconds

when I receive [scene2 v]
switch costume to (idle v)
glide (4.5) secs to x: (45) y: ({ROBOT_Y})

when I receive [scene2 v]
turn left (6) degrees
repeat (9)
  start sound (bloop v)
  turn right (12) degrees
  wait (0.25) seconds
  turn left (12) degrees
  wait (0.25) seconds
end
turn right (6) degrees

when I receive [scene2 v]
wait (1) seconds
say [Mmm... cookie!] for (2.5) seconds

when I receive [scene3 v]
switch costume to (reach v)
glide (1.8) secs to x: (58) y: ({ROBOT_Y})

when I receive [scene3 v]
wait (2.6) seconds
switch costume to (wow v)
start sound (boing v)
say [WHAT?!] for (1.8) seconds

when I receive [scene4 v]
switch costume to (stare v)
say [That is MY cookie!] for (2.2) seconds
say [I saw it first!] for (2.2) seconds

when I receive [scene4 v]
repeat (8)
  turn right (3) degrees
  wait (0.3) seconds
  turn left (3) degrees
  wait (0.3) seconds
end

when I receive [scene5 v]
switch costume to (tug v)
repeat (5)
  start sound (squeak v)
  glide (0.5) secs to x: (40) y: ({ROBOT_Y})
  glide (0.5) secs to x: (76) y: ({ROBOT_Y})
end

when I receive [scene5 v]
say [Heave!] for (1.2) seconds
say [Hnnng!] for (1.2) seconds
say [Mine mine mine!] for (1.2) seconds
say [Almost...] for (1.2) seconds

when I receive [scene6 v]
switch costume to (wow v)
glide (0.3) secs to x: (62) y: ({ROBOT_Y})
switch costume to (happy v)
say [Yay! Half each!] for (1.3) seconds
say [Mmm! Yummy!] for (1.4) seconds
say [Sharing is best!] for (1.7) seconds

when I receive [scene6 v]
wait (0.8) seconds
repeat (8)
  change y by (8)
  wait (0.2) seconds
  change y by (-8)
  wait (0.2) seconds
end"""

ALIEN_SCRIPT = f"""when flag clicked
hide
go to x: (164) y: ({ALIEN_Y})
point in direction (90)
set size to (65) %
switch costume to (smug v)
set [ghost v] effect to (0)

when I receive [scene3 v]
set [ghost v] effect to (100)
set size to (8) %
show
wait (2.5) seconds
start sound (alien_warble v)
repeat (10)
  change size by (6)
  change [ghost v] effect by (-10)
  turn right (36) degrees
  wait (0.05) seconds
end
set size to (65) %
point in direction (90)
switch costume to (smug v)
say [Bleep bloop!] for (1.8) seconds

when I receive [scene4 v]
switch costume to (stare v)
wait (2.3) seconds
say [No no no! MINE!] for (2.2) seconds

when I receive [scene4 v]
repeat (8)
  turn left (3) degrees
  wait (0.3) seconds
  turn right (3) degrees
  wait (0.3) seconds
end

when I receive [scene5 v]
switch costume to (tug v)
repeat (5)
  glide (0.5) secs to x: (146) y: ({ALIEN_Y})
  glide (0.5) secs to x: (182) y: ({ALIEN_Y})
end

when I receive [scene5 v]
wait (0.6) seconds
say [Bleep!] for (1.2) seconds
say [Blorp blorp!] for (1.2) seconds
say [Let go!] for (1.2) seconds

when I receive [scene6 v]
switch costume to (happy v)
glide (0.3) secs to x: (172) y: ({ALIEN_Y})
say [Bleep yay!] for (1.3) seconds
say [Yum yum yum!] for (1.4) seconds
say [Best friends!] for (1.7) seconds

when I receive [scene6 v]
wait (0.9) seconds
repeat (8)
  change y by (6)
  wait (0.2) seconds
  change y by (-6)
  wait (0.2) seconds
end"""

COOKIE_SCRIPT = f"""when flag clicked
go to x: (125) y: ({COOKIE_Y})
set size to (70) %
point in direction (90)
switch costume to (whole v)
clear graphic effects
show

when I receive [scene1 v]
repeat (5)
  turn right (8) degrees
  wait (0.25) seconds
  turn left (8) degrees
  wait (0.25) seconds
end

when I receive [scene1 v]
repeat (8)
  set [brightness v] effect to (35)
  wait (0.3) seconds
  set [brightness v] effect to (0)
  wait (0.3) seconds
end

when I receive [scene5 v]
repeat (5)
  glide (0.5) secs to x: (107) y: ({COOKIE_Y})
  glide (0.5) secs to x: (143) y: ({COOKIE_Y})
end

when I receive [scene6 v]
start sound (crack v)
switch costume to (half left v)
glide (0.3) secs to x: (126) y: ({COOKIE_Y})
wait (0.9) seconds
repeat (10)
  start sound (munch v)
  change size by (-5)
  wait (0.3) seconds
end
hide"""

HALF_SCRIPT = f"""when flag clicked
hide
set size to (70) %
switch costume to (half right v)

when I receive [scene6 v]
go to x: (143) y: ({COOKIE_Y})
show
glide (0.3) secs to x: (146) y: ({COOKIE_Y})
wait (0.9) seconds
repeat (10)
  change size by (-5)
  wait (0.3) seconds
end
hide"""


async def build(root: Path) -> list[tuple[str, bool, str]]:
    log: list[tuple[str, bool, str]] = []
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "scratch_mcp", "--root", str(root)]
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def call(tool: str, **args):
                result = await session.call_tool(tool, args)
                text = "".join(c.text for c in result.content if c.type == "text")
                short = ", ".join(f"{k}={str(v)[:24]!r}" for k, v in args.items() if k != "project")
                log.append((f"{tool}({short})", not result.isError, text.splitlines()[0] if text else ""))
                if result.isError:
                    raise RuntimeError(f"{tool} failed: {text}")
                return text

            p = {"project": PROJECT}
            await call("create_project", name=PROJECT)
            await call("delete_sprite", sprite="Sprite1", **p)  # drop the default cat
            await call("add_stock_art", art="kitchen", replace=True, **p)
            await call("add_stock_art", art="robot", x=-150, y=ROBOT_Y, **p)
            await call("add_stock_art", art="alien", x=164, y=ALIEN_Y, size=65, **p)
            await call("add_stock_art", art="cookie", x=125, y=COOKIE_Y, size=70, **p)
            await call("add_stock_art", art="cookie", sprite="CookieHalf", x=143, y=COOKIE_Y, size=70, **p)
            await call("add_stock_art", art="title", text="The Last Cookie", y=125, **p)

            sound_plan = {
                "Stage": [("music", "music_cheerful", {"seconds": 30, "tempo": 120}), ("chime", "chime", {})],
                "Robot": [("boing", "boing", {}), ("bloop", "bloop", {}), ("squeak", "squeak", {})],
                "Alien": [("alien_warble", "alien_warble", {})],
                "Cookie": [("crack", "crack", {}), ("munch", "munch", {})],
            }
            for sprite, items in sound_plan.items():
                for name, preset, extra in items:
                    await call("add_sound", sprite=sprite, name=name, preset=preset, **extra, **p)

            for sprite, script in [("Stage", STAGE_SCRIPTS[0]), ("Title", TITLE_SCRIPT), ("Robot", ROBOT_SCRIPT),
                                   ("Alien", ALIEN_SCRIPT), ("Cookie", COOKIE_SCRIPT), ("CookieHalf", HALF_SCRIPT)]:
                await call("add_script", sprite=sprite, script=script, **p)

            summary = await call("read_project", **p)
            (root / "last_cookie_summary.txt").write_text(summary)
    return log


def main() -> None:
    root = Path(sys.argv[1]).expanduser()
    log = anyio.run(build, root)
    ok = sum(1 for _, good, _ in log if good)
    print(f"{ok}/{len(log)} tool calls succeeded")
    for name, good, first_line in log:
        print(f"  {'OK  ' if good else 'FAIL'} {name} -> {first_line}")


if __name__ == "__main__":
    main()
