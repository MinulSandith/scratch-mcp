"""A new project, matching the one Scratch 3 creates (Stage + Sprite1 with the cat)."""

from __future__ import annotations

import secrets
from importlib import resources
from typing import Any

from . import __version__

CAT_A = "bcf454acf82e4504149f7ffe07081dbc.svg"
CAT_B = "0fb9be3e8397c983338cb71dc84d0b25.svg"
BACKDROP = "cd21514d0531fdffb22204e0ec5ed84a.svg"
POP = "83a9787d4cb6f3b7632b4ddfebf74367.wav"
MEOW = "83c36d806dc92327b9e7049a565c6bff.wav"


def _asset(name: str) -> bytes:
    return resources.files("scratch_mcp").joinpath("assets", name).read_bytes()


def _var_id() -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(20))


def blank_project(sprite_name: str = "Sprite1") -> tuple[dict[str, Any], dict[str, bytes]]:
    project = {
        "targets": [
            {
                "isStage": True,
                "name": "Stage",
                "variables": {_var_id(): ["my variable", 0]},
                "lists": {},
                "broadcasts": {},
                "blocks": {},
                "comments": {},
                "currentCostume": 0,
                "costumes": [
                    {
                        "name": "backdrop1",
                        "dataFormat": "svg",
                        "assetId": BACKDROP.split(".")[0],
                        "md5ext": BACKDROP,
                        "rotationCenterX": 240,
                        "rotationCenterY": 180,
                    }
                ],
                "sounds": [
                    {
                        "name": "pop",
                        "assetId": POP.split(".")[0],
                        "dataFormat": "wav",
                        "format": "",
                        "rate": 11025,
                        "sampleCount": 258,
                        "md5ext": POP,
                    }
                ],
                "volume": 100,
                "layerOrder": 0,
                "tempo": 60,
                "videoTransparency": 50,
                "videoState": "on",
                "textToSpeechLanguage": None,
            },
            {
                "isStage": False,
                "name": sprite_name,
                "variables": {},
                "lists": {},
                "broadcasts": {},
                "blocks": {},
                "comments": {},
                "currentCostume": 0,
                "costumes": [
                    {
                        "name": "costume1",
                        "bitmapResolution": 1,
                        "dataFormat": "svg",
                        "assetId": CAT_A.split(".")[0],
                        "md5ext": CAT_A,
                        "rotationCenterX": 48,
                        "rotationCenterY": 50,
                    },
                    {
                        "name": "costume2",
                        "bitmapResolution": 1,
                        "dataFormat": "svg",
                        "assetId": CAT_B.split(".")[0],
                        "md5ext": CAT_B,
                        "rotationCenterX": 46,
                        "rotationCenterY": 53,
                    },
                ],
                "sounds": [
                    {
                        "name": "Meow",
                        "assetId": MEOW.split(".")[0],
                        "dataFormat": "wav",
                        "format": "",
                        "rate": 22050,
                        "sampleCount": 18688,
                        "md5ext": MEOW,
                    }
                ],
                "volume": 100,
                "layerOrder": 1,
                "visible": True,
                "x": 0,
                "y": 0,
                "size": 100,
                "direction": 90,
                "draggable": False,
                "rotationStyle": "all around",
            },
        ],
        "monitors": [],
        "extensions": [],
        "meta": {"semver": "3.0.0", "vm": "0.2.0", "agent": f"scratch-mcp/{__version__}"},
    }
    assets = {name: _asset(name) for name in (BACKDROP, POP, CAT_A, CAT_B, MEOW)}
    return project, assets
