"""asset_manager: files inside the project (costume/sound assets) and the Scratch library."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from .. import editing
from ..ctx import Ctx
from ..registry import GROUP_DOCS, action
from ..textparse import make_id_factory

G = "asset_manager"
GROUP_DOCS[G] = (
    "Project asset files and Scratch's online library. 'list' shows every costume/backdrop/sound file in the .sb3 and "
    "who uses it; 'prune' removes unused files. 'library_search' browses Scratch's built-in sprites, costumes, backdrops "
    "and sounds; 'library_add' puts one into the project (needs internet access to Scratch's public asset servers; "
    "results are cached on disk). To make your own art or sounds use costume_manager / sound_manager."
)


def _usage(project: dict[str, Any]) -> dict[str, list[str]]:
    use: dict[str, list[str]] = {}
    for t in project["targets"]:
        who = "Stage" if t.get("isStage") else t["name"]
        for key, label in (("costumes", "backdrop" if t.get("isStage") else "costume"), ("sounds", "sound")):
            for a in t.get(key) or []:
                use.setdefault(a.get("md5ext") or f"{a['assetId']}.{a['dataFormat']}", []).append(f"{who}:{label}:{a['name']}")
    return use


@action(G, "list")
def list_assets(ctx: Ctx, project: str | None = None) -> dict:
    """Every file inside the .sb3 (besides project.json) with size and users; flags files nothing uses and references to missing files."""
    s = ctx.session(project)
    use = _usage(s.project)
    files = [{"file": n, "bytes": len(d), "used_by": use.get(n, [])} for n, d in sorted(s.assets.items())]
    return {"files": files, "unused": [f["file"] for f in files if not f["used_by"]],
            "missing": sorted(set(use) - set(s.assets)), "total_bytes": sum(len(d) for d in s.assets.values())}


@action(G)
def prune(ctx: Ctx, project: str | None = None) -> dict:
    """Remove asset files no costume or sound refers to (reduces file size)."""
    with ctx.store.edit(project, "prune unused assets") as h:
        removed = editing.prune_unused_assets(h.project, h.assets)
    return {"removed": removed}


@action(G)
def library_search(ctx: Ctx, kind: str, query: str | None = None, tag: str | None = None, limit: int = 40) -> dict:
    """Search Scratch's library.

    Args:
        kind: sprites, costumes, backdrops or sounds.
        query: part of a name or tag (e.g. 'cat', 'space', 'animals').
        tag: exact tag filter.
    """
    return {"kind": kind, "results": ctx.library.search(kind, query, tag, limit)}


@action(G)
def library_add(ctx: Ctx, kind: str, name: str, sprite: str | None = None, new_name: str | None = None,
                project: str | None = None) -> dict:
    """Add a library item. sprites: creates a new sprite with all its costumes, sounds and starter scripts. costumes: adds to `sprite`. backdrops: adds to the Stage. sounds: adds to `sprite` (or the Stage).

    Args:
        kind: sprites, costumes, backdrops or sounds.
        name: exact library name (see library_search).
        sprite: target sprite for costumes/sounds.
        new_name: name to give the new sprite/costume/sound.
    """
    lib = ctx.library
    item = lib.find(kind, name)
    session = ctx.session(project)
    with ctx.store.edit(project, f"add library {kind[:-1]} {name}") as h:
        if kind == "sprites":
            files, sprite_json = {}, json.loads(json.dumps(item))
            for a in (sprite_json.get("costumes") or []) + (sprite_json.get("sounds") or []):
                fn = a.get("md5ext") or f"{a['assetId']}.{a['dataFormat']}"
                a["md5ext"] = fn
                files[fn] = lib.asset(fn)
            sprite_json.pop("tags", None)
            sprite_json.pop("json", None)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("sprite.json", json.dumps(sprite_json))
                for fn, d in files.items():
                    zf.writestr(fn, d)
            sp = editing.import_sprite3(h.project, h.assets, buf.getvalue(), make_id_factory(h.project), new_name)
            session.selected_sprite = sp["name"]
            result = {"created_sprite": sp["name"], "costumes": len(sp["costumes"]), "sounds": len(sp["sounds"])}
        elif kind in ("costumes", "backdrops"):
            target = ctx.target(h.project, session, "Stage" if kind == "backdrops" else sprite)
            data = lib.asset(item["md5ext"])
            entry = editing.import_image(h.project, h.assets, target, new_name or item["name"], data, item.get("bitmapResolution", 1) or 1)
            if "rotationCenterX" in item and entry["dataFormat"] == "svg":
                entry["rotationCenterX"], entry["rotationCenterY"] = item["rotationCenterX"], item["rotationCenterY"]
            result = {"added": entry["name"], "to": "Stage" if target.get("isStage") else target["name"]}
        else:
            target = ctx.target(h.project, session, sprite)
            data = lib.asset(item["md5ext"])
            entry = editing.add_sound(h.assets, target, new_name or item["name"], data)
            result = {"added": entry["name"], "seconds": round(entry["sampleCount"] / entry["rate"], 2)}
    return result
