"""Builds 'One Quilt for Two' by calling the scratch MCP server's tools over stdio (no hand-written project files).

Story, characters, dialogue, art and sounds are original. Run: python3 build.py
"""
import asyncio, json, math, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # scratch-projects/
ART = os.path.join(HERE, "art")
PROJECT = "One Quilt for Two"

def T(text):  # speaking time for a line
    return round(max(1.6, 1.0 + 0.06 * len(text)), 1)

class Scene:
    def __init__(self, key, backdrop, music=None):
        self.key, self.backdrop, self.music = key, backdrop, music
        self.setup, self.cues, self.end = {}, [], 0.0
    def put(self, sprite, x, y, size=None, costume=None, dir=None, front=False):
        self.setup[sprite] = dict(x=x, y=y, size=size, costume=costume, dir=dir, front=front)
    def at(self, t, sprite, lines, dur=0.0):
        t = max(0.1, round(t, 2))
        self.cues.append((t, sprite, lines))
        self.end = max(self.end, t + dur)
        return t + dur
    def talk(self, t, sprite, text, pose, gap=0.35):
        s = T(text)
        return self.at(t, sprite, [f"talk [{text}] ({s}) [{pose}]"], s) + gap
    def think(self, t, sprite, text, gap=0.35):
        s = T(text)
        return self.at(t, sprite, [f"think [{text}] for ({s}) seconds"], s) + gap
    def say(self, t, sprite, text, gap=0.35):
        s = T(text)
        return self.at(t, sprite, [f"say [{text}] for ({s}) seconds"], s) + gap
    def length(self, pad=1.0):
        return round(self.end + pad, 1)

BEARS = ["Bramble", "Frost"]
PUFFINS = ["Pip", "Tip", "Kip"]
ALL = ["Snowman", "Sled", "Drift", "Frost", "Bramble", "Pip", "Tip", "Kip", "Jar", "CupA", "CupB",
       "Shovel1", "Shovel2", "Quilt", "Snowball", "Heart", "Flake", "Card", "Card2"]

def story():
    S = []
    # 1 title
    s = Scene("title", "sunrise", "m_day"); S.append(s)
    s.put("Card", 0, 70, 100, "title")
    s.at(0.8, "Card", ["fade in"], 0.7); s.at(8.5, "Card", ["fade out"], 0.7)
    for i, p in enumerate(PUFFINS):
        s.put(p, -280 - i * 40, 40 + i * 25, 60, "flap")
        s.at(1.5 + i * 0.4, p, ["glide (6) secs to x: (" + str(300 + i * 30) + ") y: (" + str(110 - i * 20) + ")"], 6)
        s.at(1.5 + i * 0.4, p, ["flap (24)"], 6)
    s.at(3, "Pip", ["start sound (squeak v)"])
    s.end = max(s.end, 10.5)

    # 2 snowman
    s = Scene("snowman", "outside", "m_day"); S.append(s)
    s.put("Snowman", -170, -45, 80, "snowman_1")
    s.put("Frost", -60, -50, 70, "carry", -90)
    s.put("Pip", 70, -112, 75, "stand"); s.put("Tip", 120, -118, 75, "stand"); s.put("Kip", 170, -110, 75, "stand")
    t = s.talk(0.5, "Frost", "One big snowball for the bottom...", "carry")
    s.at(t - 0.2, "Snowman", ["switch costume to (snowman_2 v)", "start sound (pop v)"])
    t = s.talk(t + 0.4, "Frost", "...one middle snowball...", "carry")
    t = s.talk(t, "Frost", "...and a little head with a carrot nose!", "carry")
    s.at(t - 0.2, "Snowman", ["switch costume to (snowman_3 v)", "start sound (pop v)"])
    t = s.talk(t + 0.3, "Frost", "Ta-da! Meet Mister Snow!", "happy")
    s.at(t, "Pip", ["chirp [Peep!]"], 1.2); s.at(t, "Tip", ["hop (5)"], 1.4); s.at(t + 0.3, "Kip", ["hop (5)"], 1.4)
    t += 1.6
    s.at(t, "Pip", ["switch costume to (flap v)", "glide (1) secs to x: (-165) y: (62)", "switch costume to (stand v)", "start sound (squeak v)"], 1.1)
    s.at(t, "Pip", ["flap (4)"], 1)
    t = s.talk(t + 1.3, "Frost", "Ha ha! Pip likes him too!", "happy")
    t = s.talk(t, "Frost", "What a perfect, chilly day.", "idle")

    # 3 arrival
    s = Scene("arrival", "outside", "m_day"); S.append(s)
    s.put("Snowman", -170, -45, 80, "snowman_3"); s.put("Pip", -165, 62, 75, "stand")
    s.put("Tip", 140, -118, 75, "stand"); s.put("Kip", 190, -110, 75, "stand")
    s.put("Frost", 100, -50, 70, "idle", -90)
    s.put("Bramble", -330, -50, 70, "walk1", 90); s.put("Sled", -430, -95, 80, "sled")
    s.at(0.3, "Bramble", ["walk (9) (13)"], 2.7); s.at(0.3, "Sled", ["glide (2.7) secs to x: (-196) y: (-95)"], 2.7)
    s.at(1.4, "Frost", ["switch costume to (surprised v)"])
    t = s.talk(3.2, "Bramble", "Hello there! Is this where Frost lives?", "wave")
    t = s.talk(t, "Frost", "That's me! Who are you?", "surprised")
    t = s.talk(t, "Bramble", "I'm Bramble, from the big forest.", "idle")
    t = s.talk(t, "Bramble", "My cave is so dark in winter. I wanted to see the bright snow!", "worry")
    t = s.talk(t, "Frost", "Then stay with me! My igloo has room for two.", "happy")
    t = s.talk(t, "Bramble", "Hooray! And I brought treats from home.", "happy")
    s.at(t, "Pip", ["chirp [Peep peep!]"], 1.2); s.at(t, "Tip", ["hop (4)"], 1.1); s.at(t, "Kip", ["hop (4)"], 1.1)
    t = s.talk(t + 1.3, "Frost", "Come in, come in! It's cocoa time!", "wave")
    s.at(t, "Frost", ["walk (3) (-12)", "hide"], 0.9)
    s.at(t + 0.4, "Bramble", ["walk (4) (16)", "hide"], 1.2)

    # 4 cocoa
    s = Scene("cocoa", "inside_day", "m_cocoa"); S.append(s)
    s.put("Bramble", -115, -40, 65, "carry", 90); s.put("Frost", 115, -40, 65, "idle", -90)
    s.at(0.4, "Jar", ["go to x: (-40) y: (-50)", "set size to (80) %", "show", "go to [front v] layer"])
    t = s.talk(0.5, "Bramble", "Blueberry jam, from my forest!", "carry")
    t = s.talk(t, "Frost", "Yum! I'll make hot cocoa. Jam cocoa!", "happy")
    s.at(t, "CupA", ["switch costume to (cup_red v)", "go to x: (-8) y: (-56)", "show", "go to [front v] layer", "start sound (bloop v)"])
    s.at(t + 0.5, "CupB", ["switch costume to (cup_blue v)", "go to x: (36) y: (-56)", "show", "go to [front v] layer", "start sound (bloop v)"])
    t += 1.2
    s.at(t, "Bramble", ["switch costume to (sip v)", "start sound (munch v)", "wait (1) seconds", "start sound (munch v)"], 2)
    s.at(t + 0.2, "Frost", ["switch costume to (sip v)", "wait (0.6) seconds", "start sound (munch v)"], 1)
    t = s.talk(t + 2.2, "Bramble", "Mmm. Sweet and warm, all the way to my toes.", "sip")
    t = s.talk(t, "Frost", "The best cocoa ever!", "happy")
    s.at(t, "Pip", ["go to x: (168) y: (88)", "set size to (70) %", "switch costume to (stand v)", "show",
                    "repeat (3)", "  start sound (pop v)", "  change y by (4)", "  wait (0.15) seconds", "  change y by (-4)", "  wait (0.15) seconds", "end"], 1)
    t = s.talk(t + 1.1, "Frost", "Ha ha! Pip wants some too.", "happy")
    t = s.at(t, "Pip", ["chirp [Peep!]"], 1.2) + 0.3
    t = s.talk(t, "Bramble", "Frost, will you teach me to skate tomorrow?", "idle")
    t = s.talk(t, "Frost", "Of course! But first... a snowball fight!", "happy")

    # 5 snowballs
    s = Scene("snowballs", "evening", "m_snow"); S.append(s)
    s.put("Snowman", -228, -45, 80, "snowman_3")
    s.put("Frost", -150, -50, 70, "idle", 90); s.put("Bramble", 150, -50, 70, "idle", -90)
    s.put("Tip", -40, -118, 75, "stand"); s.put("Kip", 10, -122, 75, "stand"); s.put("Pip", 60, -116, 75, "stand")
    t = s.talk(0.4, "Frost", "Catch!", "wave")
    s.at(t - 0.4, "Snowball", ["throw (-120) (10) (150) (-15)"], 1.1)
    t = s.talk(t + 0.5, "Bramble", "Hey!", "surprised")
    t = s.talk(t, "Bramble", "My turn!", "wave")
    s.at(t - 0.4, "Snowball", ["throw (120) (10) (-150) (-15)"], 1.1)
    t = s.talk(t + 0.5, "Frost", "Ha ha ha!", "happy")
    t = s.talk(t, "Frost", "Here comes another one!", "wave")
    s.at(t - 0.4, "Snowball", ["throw (-120) (10) (10) (-110)"], 1.1)
    t += 0.4
    for i, (p, gx) in enumerate((("Tip", -120), ("Kip", 60), ("Pip", 200))):
        s.at(t + i * 0.15, p, ["switch costume to (flap v)", "start sound (squeak v)", f"glide (0.8) secs to x: ({gx}) y: ({-112 - i * 4})", "switch costume to (stand v)"], 1)
    t = s.talk(t + 1.2, "Bramble", "Ha ha! Sorry, little ones!", "happy")
    t = s.talk(t, "Bramble", "Brrr... it's getting dark. And so cold!", "worry")
    t = s.talk(t, "Frost", "Cold? This is my favourite weather!", "happy")

    # 6 bedtime
    s = Scene("bedtime", "inside_night", "m_bed"); S.append(s)
    s.put("Bramble", -150, -40, 65, "idle", 90); s.put("Frost", 150, -40, 65, "idle", -90)
    s.at(0.3, "Bramble", ["start sound (yawn v)"])
    t = s.talk(0.4, "Bramble", "Yaaawn...", "yawn")
    s.at(t, "Quilt", ["switch costume to (quilt_folded v)", "set size to (90) %", "go to x: (-132) y: (-58)", "show", "go to [front v] layer"])
    t = s.talk(t, "Bramble", "Time for bed. Good thing I brought this!", "carry")
    t = s.talk(t, "Bramble", "My grandma made this quilt. It's the coziest thing in the world.", "carry")
    t = s.talk(t, "Frost", "A blanket? Polar bears don't need blankets!", "idle")
    t = s.talk(t, "Frost", "We love the cold. Goodnight, Bramble!", "happy")
    t = s.talk(t, "Bramble", "Goodnight, Frost.", "happy")
    s.at(t, "Quilt", ["hide"])
    s.at(t, "Bramble", ["switch costume to (sleep_quilt v)", "set size to (60) %", "go to x: (-150) y: (-78)", "start sound (whoosh v)"])
    s.at(t + 0.6, "Frost", ["switch costume to (sleep v)", "set size to (60) %", "go to x: (150) y: (-78)"])
    s.at(t + 1.2, "Bramble", ["snore (3)"], 4.5)

    # 7 storm
    s = Scene("storm", "storm", None); S.append(s)
    s.put("Card", 0, 100, 100, "storm")
    s.at(0.6, "Card", ["fade in"], 0.7); s.at(6.5, "Card", ["fade out"], 0.7)
    s.at(0.2, "Flake", ["set [fall v] to (7)", "set [wind v] to (4)", "switch costume to (bigflake v)", "snow (75) (0.1)"], 7.5)
    s.at(0.1, "Stage", ["repeat (5)", "  start sound (wind v)", "  wait (1.5) seconds", "end"], 7.5)
    s.end = max(s.end, 8.5)

    # 8 cold night
    s = Scene("coldnight", "inside_night", "m_cold"); S.append(s)
    s.put("Bramble", -150, -78, 60, "sleep_quilt", 90); s.put("Frost", 150, -78, 60, "lie_cold", -90)
    s.at(0.2, "Stage", ["repeat (8)", "  start sound (wind v)", "  wait (3) seconds", "end"], 24)
    s.at(0.3, "Frost", ["shiver (15)"], 3)
    t = s.think(0.5, "Frost", "Brrr... Why is it so cold tonight?")
    s.at(t, "Frost", ["shiver (12)"], 2.4); t += 2.6
    s.at(t, "Frost", ["switch costume to (cold v)", "set size to (65) %", "go to x: (150) y: (-40)"])
    t = s.think(t + 0.2, "Frost", "Maybe I could ask Bramble for a corner of his quilt...")
    s.at(t, "Frost", ["switch costume to (worry v)"])
    t = s.think(t + 0.1, "Frost", "No, no. Polar bears don't need blankets!")
    s.at(t, "Frost", ["switch costume to (lie_cold v)", "set size to (60) %", "go to x: (150) y: (-78)", "shiver (30)"], 6)
    wake = t + 2.5
    s.at(0.3, "Bramble", [f"snore ({int((wake - 0.5) // 1.5)})"], wake - 0.5)
    s.at(wake, "Bramble", ["switch costume to (sleep_quilt_open v)"])
    t = s.think(wake + 0.3, "Bramble", "What's that clicking noise?")
    t = s.think(t, "Bramble", "Oh! It's Frost's teeth. He's freezing!")

    # 9 the gift
    s = Scene("gift", "inside_night", "m_cold"); S.append(s)
    s.put("Bramble", -150, -78, 60, "sleep_quilt_open", 90); s.put("Frost", 150, -78, 60, "lie_cold", -90)
    s.at(0.4, "Bramble", ["switch costume to (carry v)", "set size to (65) %", "go to x: (-150) y: (-40)"])
    s.at(0.4, "Quilt", ["switch costume to (quilt_folded v)", "set size to (90) %", "go to x: (-132) y: (-58)", "show", "go to [front v] layer"])
    t = s.think(0.8, "Bramble", "He's too proud to ask...")
    s.at(t, "Bramble", ["walk (7) (13)", "switch costume to (carry v)"], 2.1)
    s.at(t, "Quilt", ["glide (2.1) secs to x: (50) y: (-58)"], 2.1)
    give = t + 2.3
    s.at(0.3, "Frost", [f"shiver ({int((give - 0.3) * 5)})"], give - 0.3)
    s.at(give, "Quilt", ["start sound (whoosh v)", "hide"])
    s.at(give, "Frost", ["switch costume to (sleep_quilt v)"])
    t = s.talk(give + 0.3, "Bramble", "Sleep tight, my friend.", "happy")
    s.at(t, "Bramble", ["point in direction (-90)", "walk (7) (-13)", "switch costume to (lie_cold v)", "set size to (60) %", "go to x: (-150) y: (-78)"], 2.2)
    t += 2.4
    s.at(t, "Bramble", ["shiver (40)"], 8)
    t = s.think(t + 0.2, "Bramble", "Brrr! It really IS cold...")
    t = s.think(t, "Bramble", "But my friend is warm. That's what matters.")
    s.at(t - 3, "Frost", ["snore (2)"], 3)

    # 10 frost wakes
    s = Scene("wakes", "inside_night", "m_wake"); S.append(s)
    s.put("Bramble", -150, -78, 60, "lie_cold", 90); s.put("Frost", 150, -78, 60, "sleep_quilt", -90)
    t = s.think(0.6, "Frost", "Mmm, so warm... Wait. Is this Bramble's quilt?")
    s.at(t, "Frost", ["switch costume to (carry v)", "set size to (65) %", "go to x: (150) y: (-40)"])
    s.at(t, "Quilt", ["switch costume to (quilt_folded v)", "set size to (90) %", "go to x: (132) y: (-58)", "show", "go to [front v] layer"])
    t = s.talk(t + 0.3, "Frost", "Bramble! You gave me your quilt... and now YOU are freezing!", "carry")
    s.at(0.3, "Bramble", [f"shiver ({int((t + 3) * 5)})"], t + 3)
    t = s.say(t, "Bramble", "I'm f-f-fine...")
    t = s.talk(t, "Frost", "Silly bear. This quilt is big enough for two!", "happy")

    # 11 sharing
    s = Scene("sharing", "inside_warm", "m_wake"); S.append(s)
    s.put("Bramble", -35, -16, 62, "sit", 90); s.put("Frost", 85, -16, 62, "sit", -90)
    s.put("Quilt", 25, -104, 84, "quilt_wide", front=True)
    s.at(0.2, "Quilt", ["start sound (chime v)"])
    t = s.talk(0.6, "Bramble", "Ahh... warm at last.", "sit")
    t = s.talk(t, "Frost", "Thank you for sharing, Bramble.", "sit")
    t = s.talk(t, "Bramble", "Thank YOU for sharing back!", "sit")
    s.at(t, "Heart", ["pop (25) (45)"], 1.6)
    t += 1.2
    s.at(t, "Bramble", ["switch costume to (sitsleep v)", "snore (3)"], 4.5)
    s.at(t + 0.6, "Frost", ["switch costume to (sitsleep v)", "snore (3)"], 4.5)

    # 12 morning card
    s = Scene("morning", "sunrise", "m_morning"); S.append(s)
    s.put("Card", 0, 80, 100, "morning")
    s.at(0.5, "Card", ["fade in"], 0.7); s.at(5, "Card", ["fade out"], 0.7)
    for i, p in enumerate(PUFFINS):
        s.put(p, -280 - i * 45, 10 + i * 30, 60, "flap")
        s.at(0.8 + i * 0.4, p, [f"glide (5) secs to x: ({300 + i * 30}) y: ({90 - i * 15})"], 5)
        s.at(0.8 + i * 0.4, p, ["flap (20)"], 5)
    s.at(2, "Tip", ["start sound (squeak v)"])
    s.end = max(s.end, 6.5)

    # 13 snowed in
    s = Scene("dig", "door", "m_morning"); S.append(s)
    s.put("Drift", 0, -12, 100, "drift")
    s.put("Bramble", -150, -45, 65, "idle", 90); s.put("Frost", 150, -45, 65, "idle", -90)
    t = s.talk(0.4, "Frost", "Oh no! The storm buried our door!", "surprised")
    t = s.talk(t, "Bramble", "Don't worry. We'll dig our way out together!", "happy")
    s.at(t, "Shovel1", ["point in direction (90)", "go to x: (-95) y: (-55)", "set size to (70) %", "show", "go to [front v] layer"])
    s.at(t, "Shovel2", ["point in direction (-90)", "go to x: (95) y: (-55)", "set size to (70) %", "show", "go to [front v] layer"])
    dig = ["repeat (8)", "  switch costume to (carry v)", "  wait (0.25) seconds", "  switch costume to (idle v)", "  wait (0.25) seconds", "end", "switch costume to (idle v)"]
    s.at(t, "Bramble", ["go to x: (-115) y: (-45)"] + dig, 4)
    s.at(t, "Frost", ["go to x: (115) y: (-45)"] + dig, 4)
    sh = ["repeat (8)", "  change y by (10)", "  start sound (dig v)", "  wait (0.25) seconds", "  change y by (-10)", "  wait (0.25) seconds", "end", "hide"]
    s.at(t, "Shovel1", sh, 4); s.at(t + 0.12, "Shovel2", sh, 4)
    s.at(t + 0.3, "Drift", ["repeat (8)", "  change size by (-11)", "  change y by (-12)", "  wait (0.45) seconds", "end", "hide"], 3.8)
    t += 4.3
    s.at(t, "Stage", ["start sound (sparkle v)"])
    for i, p in enumerate(PUFFINS):
        s.at(t + i * 0.3, p, ["switch costume to (stand v)", "set size to (75) %", f"go to x: ({-20 + i * 25}) y: (-60)", "show", "go to [front v] layer",
                              f"glide (0.6) secs to x: ({-40 + i * 40}) y: ({-112 - (i % 2) * 6})", "hop (3)"], 1.6)
    t = s.at(t + 1.2, "Pip", ["chirp [Peep peep!]"], 1.2) + 0.3
    t = s.talk(t, "Bramble", "We did it! Good morning, little friends!", "happy")
    t = s.talk(t, "Frost", "Now... let's go skating!", "wave")

    # 14 skating
    s = Scene("skating", "rink", "m_skate"); S.append(s)
    s.put("Frost", -160, -75, 65, "skate1", 90); s.put("Bramble", -40, -80, 65, "idle", 90)
    s.at(0.2, "Frost", ["skate (11)", "switch costume to (idle v)"], 6.6)
    s.at(0.2, "Frost", ["glide (2.4) secs to x: (170) y: (-92)", "point in direction (-90)", "glide (2.4) secs to x: (-170) y: (-82)",
                        "point in direction (90)", "glide (1.6) secs to x: (40) y: (-86)"], 6.6)
    t = s.talk(0.5, "Bramble", "Whoa... whoa... it's slippery!", "worry")
    s.at(0.5, "Bramble", ["repeat (8)", "  change x by (4)", "  wait (0.15) seconds", "  change x by (-4)", "  wait (0.15) seconds", "end"], 2.4)
    s.at(t, "Bramble", ["switch costume to (skate1 v)", "glide (1.2) secs to x: (110) y: (-82)", "switch costume to (fall v)", "start sound (boing v)", "go to x: (110) y: (-92)"], 1.3)
    t += 1.5
    s.at(t, "Pip", ["switch costume to (stand v)", "go to x: (205) y: (-112)", "set size to (75) %", "show", "chirp [Peep peep!]"], 1.2)
    s.at(t + 0.2, "Tip", ["switch costume to (hop v)", "go to x: (235) y: (-116)", "set size to (75) %", "show", "hop (4)"], 1.2)
    t = s.say(t, "Bramble", "Oof!") 
    t = max(t, 7.0)
    s.at(t - 0.3, "Frost", ["point in direction (90)", "glide (0.6) secs to x: (40) y: (-86)", "switch costume to (wave v)"], 0.6)
    t = s.talk(t + 0.4, "Frost", "Hold my paw, Bramble!", "wave")
    s.at(t, "Bramble", ["switch costume to (idle v)", "go to x: (110) y: (-80)", "point in direction (-90)"])
    t += 0.4
    s.at(t, "Bramble", ["skate (5)"], 3); s.at(t, "Frost", ["point in direction (-90)", "skate (5)"], 3)
    s.at(t, "Bramble", ["glide (3) secs to x: (-60) y: (-82)"], 3); s.at(t, "Frost", ["glide (3) secs to x: (-170) y: (-80)"], 3)
    t = s.talk(t + 0.2, "Bramble", "I'm skating! I'm really skating!", "happy")
    t = s.talk(t, "Frost", "Ha ha! You're a natural!", "happy")
    for i, p in enumerate(PUFFINS):
        s.at(t + i * 0.5, p, ["switch costume to (slide v)", "set size to (75) %", f"go to x: (-280) y: ({-128 - i * 6})", "show", "start sound (whoosh v)",
                              f"glide (2) secs to x: (290) y: ({-122 - i * 6})", "hide"], 2)
    s.end = max(s.end, t + 3.2)

    # 15 goodbye
    s = Scene("goodbye", "outside", "m_bye"); S.append(s)
    s.put("Snowman", -228, -45, 80, "snowman_3"); s.put("Sled", -160, -95, 80, "sled")
    s.put("Bramble", -60, -50, 70, "idle", 90); s.put("Frost", 80, -50, 70, "idle", -90)
    s.put("Tip", 150, -118, 75, "stand"); s.put("Kip", 195, -110, 75, "stand"); s.put("Pip", 175, -128, 75, "stand")
    t = s.talk(0.4, "Bramble", "It's time for me to go home, Frost.", "worry")
    t = s.talk(t, "Frost", "I'll miss you, Bramble.", "worry")
    s.at(t, "Quilt", ["switch costume to (quilt_folded v)", "set size to (90) %", "go to x: (98) y: (-58)", "show", "go to [front v] layer"])
    t = s.talk(t, "Frost", "Wait! Don't forget your quilt!", "carry")
    t = s.talk(t, "Bramble", "Keep it. On cold nights, it will remind you of our friendship.", "happy")
    s.at(t, "Quilt", ["hide"]); s.at(t, "Frost", ["switch costume to (wrap v)", "start sound (whoosh v)"])
    t = s.talk(t + 0.4, "Frost", "Thank you... Will you come back next winter?", "happy")
    t = s.talk(t, "Bramble", "I promise!", "wave")
    s.at(t, "Bramble", ["switch costume to (happy v)", "glide (0.8) secs to x: (-5) y: (-50)"], 0.8)
    s.at(t, "Frost", ["glide (0.8) secs to x: (55) y: (-50)", "switch costume to (happy v)"], 0.8)
    s.at(t + 0.8, "Heart", ["pop (25) (60)"], 1.6)
    t += 2.6
    s.at(t, "Bramble", ["point in direction (-90)", "walk (11) (-15)", "hide"], 3.4)
    s.at(t, "Sled", ["glide (3.3) secs to x: (-420) y: (-95)"], 3.3)
    s.at(t + 0.4, "Frost", ["talk [Bye-bye, Bramble! See you next winter!] (3.2) [wave]"], 3.2)
    for i, p in enumerate(PUFFINS):
        s.at(t + 0.5 + i * 0.2, p, ["flap (8)"], 2)
    s.at(t + 1, "Pip", ["chirp [Peep!]"], 1.2)
    s.end = max(s.end, t + 4)

    # 16 aurora
    s = Scene("aurora", "aurora", "m_end"); S.append(s)
    s.put("Frost", -115, -48, 30, "wrap", 90); s.put("Bramble", 128, -88, 26, "idle", -90)
    s.at(0.2, "Stage", ["start sound (sparkle v)"])
    t = s.think(1.2, "Frost", "Goodnight, Bramble.")
    t = s.think(t + 0.3, "Bramble", "Goodnight, Frost.")
    s.end = max(s.end, t + 1.5)

    # 17 the end
    s = Scene("end", "credits", "m_end"); S.append(s)
    s.put("Card", 0, 95, 100, "end"); s.put("Card2", 0, -15, 100, "credits")
    s.at(0.3, "Card", ["fade in"], 0.7); s.at(1.6, "Card2", ["fade in"], 0.7)
    for i, p in enumerate(PUFFINS):
        s.put(p, -60 + i * 60, -140, 75, "stand")
        s.at(2.5 + i * 0.3, p, ["hop (6)"], 1.7)
    s.end = max(s.end, 8.5)
    return S

PROCS = {
    "bear": """define talk (text) (secs) (pose)
switch costume to (pose)
say (text)
repeat ((secs) * (4))
  switch costume to (join (pose) [_o])
  start sound (pick random (1) to (3))
  wait (0.12) seconds
  switch costume to (pose)
  wait (0.13) seconds
end
say []

define walk (steps) (dx)
repeat (steps)
  switch costume to (walk1 v)
  change x by (dx)
  start sound (step v)
  wait (0.15) seconds
  switch costume to (walk2 v)
  change x by (dx)
  wait (0.15) seconds
end
switch costume to (idle v)

define shiver (n)
repeat (n)
  change x by (3)
  start sound (chatter v)
  wait (0.1) seconds
  change x by (-3)
  wait (0.1) seconds
end

define snore (n)
repeat (n)
  think [Zzz...]
  start sound (snore v)
  wait (1) seconds
  think []
  wait (0.5) seconds
end

define skate (n)
repeat (n)
  switch costume to (skate1 v)
  wait (0.3) seconds
  switch costume to (skate2 v)
  wait (0.3) seconds
end""",
    "puffin": """define hop (n)
repeat (n)
  switch costume to (hop v)
  change y by (10)
  wait (0.12) seconds
  change y by (-10)
  switch costume to (stand v)
  wait (0.15) seconds
end

define chirp (text)
say (text)
start sound (squeak v)
wait (1.2) seconds
say []

define flap (n)
repeat (n)
  switch costume to (flap v)
  wait (0.12) seconds
  switch costume to (stand v)
  wait (0.12) seconds
end""",
    "card": """define fade in
set [ghost v] effect to (100)
show
repeat (20)
  change [ghost v] effect by (-5)
  wait (0.03) seconds
end

define fade out
repeat (20)
  change [ghost v] effect by (5)
  wait (0.03) seconds
end
hide
clear graphic effects""",
    "Snowball": """define throw (x1) (y1) (x2) (y2)
switch costume to (snowball v)
go to x: (x1) y: (y1)
show
go to [front v] layer
start sound (whoosh v)
glide (0.35) secs to x: (((x1) + (x2)) / (2)) y: ((y1) + (70))
glide (0.35) secs to x: (x2) y: (y2)
start sound (crack v)
switch costume to (splat v)
wait (0.35) seconds
hide""",
    "Heart": """define pop (x) (y)
go to x: (x) y: (y)
set [ghost v] effect to (0)
show
go to [front v] layer
start sound (chime v)
repeat (25)
  change y by (2)
  change [ghost v] effect by (4)
  wait (0.05) seconds
end
hide
clear graphic effects""",
    "Flake": """when I start as a clone
go to x: (pick random (-260) to (240)) y: (190)
show
go to [front v] layer
repeat until <(y position) < (-175)>
  change y by ((0) - (fall))
  change x by (wind)
end
delete this clone

define snow (n) (gap)
repeat (n)
  create clone of (myself v)
  wait (gap) seconds
end""",
}

def setup_lines(sprite, d):
    if d is None:
        return ["hide", "say []"] if sprite != "Flake" else ["hide"]
    L = ["say []", "clear graphic effects"]
    if d.get("dir") is not None: L.append(f"point in direction ({d['dir']})")
    if d.get("size") is not None: L.append(f"set size to ({d['size']}) %")
    if d.get("costume"): L.append(f"switch costume to ({d['costume']} v)")
    L.append(f"go to x: ({d['x']}) y: ({d['y']})")
    if sprite.startswith("Card"):
        L.append("set [ghost v] effect to (100)")
    L.append("show")
    if d.get("front"): L.append("go to [front v] layer")
    return L

def compile_scripts(scenes):
    per = {sp: [] for sp in ALL + ["Stage"]}
    for n, sc in enumerate(scenes, 1):
        hat = f"when I receive (scene {n} v)"
        for sp in ALL:
            if sp == "Flake":
                per[sp].append(f"{hat}\ndelete this clone")
                continue
            per[sp].append("\n".join([hat] + setup_lines(sp, sc.setup.get(sp))))
        for t, sp, lines in sc.cues:
            per[sp].append("\n".join([hat, f"wait ({t}) seconds"] + lines))
    return per

class Client:
    def __init__(self, s): self.s, self.n = s, 0
    async def __call__(self, tool, action, **args):
        self.n += 1
        r = await self.s.call_tool(tool, {"action": action, "args": args})
        txt = "".join(c.text for c in r.content if c.type == "text")
        if r.isError:
            raise RuntimeError(f"{tool}.{action} failed: {txt[:1500]}")
        try: return json.loads(txt)
        except Exception: return txt

async def build():
    scenes = story()
    lengths = [sc.length() for sc in scenes]
    total = sum(lengths)
    print("scene lengths:", lengths, "total", round(total, 1), "s")
    env = dict(os.environ, SCRATCH_MCP_RUNTIME=os.path.expanduser("~/.cache/scratch-mcp/runtime"))
    params = StdioServerParameters(command=sys.executable, args=["-m", "scratch_mcp", "--root", ROOT], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            c = Client(session)
            listing = await c("project_manager", "list")
            if PROJECT + ".sb3" in json.dumps(listing):
                await c("project_manager", "close", project=PROJECT, discard=True) if False else None
                await c("project_manager", "delete", name=PROJECT)   # moved to backups/deleted, not lost
            await c("project_manager", "create", name=PROJECT, empty=True, sprite_name="x")
            await c("project_manager", "set_autosave", enabled=False)
            img = lambda n: os.path.join(ART, n + ".svg")
            # backdrops
            bds = ["sunrise", "outside", "evening", "storm", "inside_day", "inside_night", "inside_warm", "door", "rink", "aurora", "credits"]
            for b in bds:
                await c("backdrop_manager", "import_image", name=b, source_path=img("bg_" + b))
            await c("backdrop_manager", "delete", backdrop=1)
            # sprites: (name, [(costume, file)])
            bear_costumes = lambda who: ([(p + sfx, f"{who}_{p}{sfx}") for p in ["idle", "happy", "worry", "wave", "carry", "surprised", "yawn", "cold", "sip", "sit", "look"] for sfx in ("", "_o")]
                                         + [(k, f"{who}_{k}") for k in ["walk1", "walk2", "skate1", "skate2", "fall", "sitsleep", "wrap", "sleep", "sleep_quilt", "sleep_quilt_open", "lie_cold"]])
            puff = [(k, "puffin_" + k) for k in ("stand", "hop", "flap", "slide")]
            specs = {
                "Snowman": [("snowman_1", "snowman_1"), ("snowman_2", "snowman_2"), ("snowman_3", "snowman_3")],
                "Sled": [("sled", "sled")], "Drift": [("drift", "drift")],
                "Frost": bear_costumes("frost"), "Bramble": bear_costumes("bramble"),
                "Pip": puff, "Tip": puff, "Kip": puff,
                "Jar": [("jar", "jar")], "CupA": [("cup_red", "cup_red"), ("cup_blue", "cup_blue")], "CupB": [("cup_red", "cup_red"), ("cup_blue", "cup_blue")],
                "Shovel1": [("shovel", "shovel")], "Shovel2": [("shovel", "shovel")],
                "Quilt": [("quilt_folded", "quilt_folded"), ("quilt_wide", "quilt_wide")],
                "Snowball": [("snowball", "snowball"), ("splat", "splat")], "Heart": [("heart", "heart")],
                "Flake": [("flake", "flake"), ("bigflake", "bigflake")],
                "Card": [("title", "card_title"), ("storm", "card_storm"), ("morning", "card_morning"), ("end", "card_end")],
                "Card2": [("credits", "card_credits")],
            }
            for name in ALL:
                cos = specs[name]
                await c("sprite_manager", "create", name=name, image_path=img(cos[0][1]), visible=False)
                await c("costume_manager", "rename", sprite=name, costume=1, new_name=cos[0][0])
                for cn, f in cos[1:]:
                    await c("costume_manager", "import_image", sprite=name, name=cn, source_path=img(f))
            for name in BEARS + PUFFINS + ["Shovel1", "Shovel2"]:
                await c("sprite_manager", "set", sprite=name, rotation_style="left-right")
            # sounds
            async def tone(sp, nm, f, sec, wave="square", vol=0.3):
                await c("sound_manager", "add_tone", sprite=sp, name=nm, frequency=f, seconds=sec, wave=wave, volume=vol)
            async def pre(sp, nm, preset, **kw):
                await c("sound_manager", "add_preset", sprite=sp, name=nm, preset=preset, **kw)
            for sp, base in (("Bramble", 150), ("Frost", 300)):
                for i, k in enumerate((1.0, 1.18, 0.86), 1):
                    await tone(sp, f"talk{i}", round(base * k), 0.08, "square", 0.28)
                await tone(sp, "step", 110 if sp == "Bramble" else 135, 0.06, "triangle", 0.7)
                await tone(sp, "chatter", 950, 0.04, "square", 0.25)
                await tone(sp, "snore", 80 if sp == "Bramble" else 105, 0.7, "saw", 0.4)
                await tone(sp, "yawn", 190, 0.9, "sine", 0.5)
                await pre(sp, "boing", "boing")
            for p in PUFFINS:
                await pre(p, "squeak", "squeak"); await pre(p, "pop", "pop"); await pre(p, "whoosh", "whoosh")
            await pre("Snowman", "pop", "pop")
            await pre("Snowball", "whoosh", "whoosh"); await pre("Snowball", "crack", "crack")
            for cup in ("CupA", "CupB"):
                await pre(cup, "bloop", "bloop")
            for b in BEARS:
                await pre(b, "munch", "munch"); await pre(b, "whoosh", "whoosh")
            for sh in ("Shovel1", "Shovel2"):
                await pre(sh, "dig", "crack")
            await pre("Quilt", "whoosh", "whoosh"); await pre("Quilt", "chime", "chime")
            await pre("Heart", "chime", "chime")
            await pre("Stage", "wind", "whoosh")
            await c("sound_manager", "edit", sprite="Stage", sound="wind", operation="slower", factor=0.45)
            await c("sound_manager", "edit", sprite="Stage", sound="wind", operation="fade_out", seconds=0.4)
            await pre("Stage", "sparkle", "chime")
            # music: one track per run of scenes sharing a music key (split if > 115 s)
            presets = {"m_day": ("music_cheerful", 104), "m_cocoa": ("music_calm", 84), "m_snow": ("music_cheerful", 120), "m_bed": ("music_calm", 72),
                       "m_cold": ("music_sneaky", 70), "m_wake": ("music_calm", 76), "m_morning": ("music_cheerful", 100), "m_skate": ("music_cheerful", 126),
                       "m_bye": ("music_calm", 80), "m_end": ("music_calm", 68)}
            music_cues = []   # (scene index, sound name)
            i = 0
            while i < len(scenes):
                key = scenes[i].music
                if not key:
                    i += 1; continue
                j, dur = i, 0.0
                while j < len(scenes) and scenes[j].music == key and dur + lengths[j] <= 115:
                    dur += lengths[j]; j += 1
                if j == i: dur, j = min(lengths[i], 115), i + 1
                nm = f"{key}_{i + 1}"
                preset, tempo = presets[key]
                await pre("Stage", nm, preset, seconds=round(dur, 1), tempo=tempo)
                await c("sound_manager", "edit", sprite="Stage", sound=nm, operation="volume", factor=0.5)
                music_cues.append((i, nm))
                i = j
            # scripts
            for kind, sprites in (("bear", BEARS), ("puffin", PUFFINS), ("card", ["Card", "Card2"])):
                for sp in sprites:
                    await c("script_manager", "add_text", sprite=sp, script=PROCS[kind])
            for sp in ("Snowball", "Heart", "Flake"):
                await c("script_manager", "add_text", sprite=sp, script=PROCS[sp])
            await c("script_manager", "add_text", sprite="Flake", script="when flag clicked\nset [fall v] to (4)\nset [wind v] to (1)\nhide")
            per = compile_scripts(scenes)
            for idx, nm in music_cues:
                per["Stage"].append(f"when I receive (scene {idx + 1} v)\nstart sound ({nm} v)")
            for sp, scripts in per.items():
                for k in range(0, len(scripts), 40):
                    await c("script_manager", "add_text", sprite=sp, script="\n\n".join(scripts[k:k + 40]))
            await c("animation_manager", "timeline", on="flag", broadcast_prefix="scene", stop_at_end=True,
                    scenes=[{"name": sc.key, "seconds": L, "backdrop": sc.backdrop} for sc, L in zip(scenes, lengths)])
            for sp in ALL:
                await c("script_manager", "arrange", sprite=sp)
            v = await c("project_manager", "validate")
            await c("project_manager", "save")
            info = await c("project_manager", "info")
            print("validate:", v if isinstance(v, str) else json.dumps(v)[:300])
            print("tool calls:", c.n, "| counts:", info["counts"])
            json.dump({"scenes": [{"n": n, "key": sc.key, "backdrop": sc.backdrop, "seconds": L} for n, (sc, L) in enumerate(zip(scenes, lengths), 1)],
                       "total_seconds": round(total, 1)}, open(os.path.join(HERE, "scenes.json"), "w"), indent=1)

if __name__ == "__main__":
    asyncio.run(build())
