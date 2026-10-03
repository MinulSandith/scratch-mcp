"""extension_manager: discover, enable, disable and verify Scratch extensions."""

from __future__ import annotations

from typing import Any

from .. import schema
from ..ctx import Ctx
from ..registry import GROUP_DOCS, action
from ..workspace import WorkspaceError

G = "extension_manager"
GROUP_DOCS[G] = (
    "Scratch's built-in extensions: pen, music, videoSensing, text2speech, translate, makeymakey, microbit, ev3 (LEGO "
    "MINDSTORMS), boost (LEGO BOOST), wedo2 (LEGO WeDo 2.0), gdxfor (Go Direct Force & Acceleration). 'enable' adds the "
    "extension to the project (its blocks are then usable; adding a block also enables it automatically). The block "
    "definitions come from scratch-vm itself. 'verify' loads the project in the real VM to prove the extensions load. "
    "Honest limits: pen/music/makeymakey run fully in the simulated runtime (music/sound OUTPUT is not audible); "
    "text2speech/translate need internet access to Scratch's servers at run time; videoSensing needs a webcam (none here, so it "
    "reads no video); microbit/ev3/boost/wedo2/gdxfor need physical hardware and the Scratch Link app - hardware "
    "connectivity is NOT supported by this server (you can still author and save projects that use them). "
    "LEGO SPIKE / SPIKE Prime is not a built-in Scratch 3 extension (it lives in LEGO's own app), so it is unsupported."
)

REQUIREMENTS: dict[str, dict[str, Any]] = {
    "pen": {"hardware": False, "service": None, "runtime_support": "full", "note": "Draws on the stage; screenshots include pen trails."},
    "music": {"hardware": False, "service": None, "runtime_support": "logic only",
              "note": "Notes/drums/tempo blocks run and are logged, but no audio is produced in the headless runtime."},
    "videoSensing": {"hardware": "webcam", "service": None, "runtime_support": "none",
                     "note": "Needs a camera; in the headless runtime the video is empty, so motion/direction read 0."},
    "text2speech": {"hardware": False, "service": "Scratch speech synthesis server (internet)", "runtime_support": "partial",
                    "note": "Blocks run; speech is fetched online and not audible here."},
    "translate": {"hardware": False, "service": "Scratch translate server (internet)", "runtime_support": "partial",
                  "note": "Needs internet access at run time."},
    "makeymakey": {"hardware": "Makey Makey board (acts as a keyboard)", "service": None, "runtime_support": "full",
                   "note": "Triggered by keyboard events, so input_manager key presses exercise it."},
    "microbit": {"hardware": "micro:bit", "service": "Scratch Link", "runtime_support": "none", "note": "Authoring only."},
    "ev3": {"hardware": "LEGO MINDSTORMS EV3", "service": "Scratch Link", "runtime_support": "none", "note": "Authoring only."},
    "boost": {"hardware": "LEGO BOOST", "service": "Scratch Link", "runtime_support": "none", "note": "Authoring only."},
    "wedo2": {"hardware": "LEGO WeDo 2.0", "service": "Scratch Link", "runtime_support": "none", "note": "Authoring only."},
    "gdxfor": {"hardware": "Go Direct Force & Acceleration", "service": "Scratch Link", "runtime_support": "none", "note": "Authoring only."},
}


def _used(project: dict[str, Any], ext: str) -> int:
    prefix = ext + "_"
    return sum(1 for t in project["targets"] for b in (t.get("blocks") or {}).values()
               if isinstance(b, dict) and b.get("opcode", "").startswith(prefix))


@action(G, "list")
def list_extensions(ctx: Ctx, project: str | None = None) -> dict:
    """All built-in extensions with what they need to run, and (if a project is open) whether it uses them."""
    try:
        s = ctx.session(project)
        enabled = set(s.project.get("extensions") or [])
    except WorkspaceError:
        s, enabled = None, set()
    out = []
    for ext_id, ext in schema.extensions().items():
        item = {"id": ext_id, "name": ext["name"], "blocks": len(ext["blocks"]), **REQUIREMENTS.get(ext_id, {})}
        if s is not None:
            item["enabled"] = ext_id in enabled
            item["blocks_used"] = _used(s.project, ext_id)
        out.append(item)
    return {"extensions": out}


@action(G)
def describe(ctx: Ctx, extension: str) -> dict:
    """An extension's blocks (opcode, shape, text, inputs, fields) and menus, straight from scratch-vm's definition."""
    ext = schema.extensions().get(extension)
    if ext is None:
        raise WorkspaceError(f"Unknown extension '{extension}'. Available: {', '.join(schema.extensions())}.")
    blocks = schema.blocks()
    return {"id": extension, "name": ext["name"], **REQUIREMENTS.get(extension, {}),
            "blocks": [{"opcode": op, "shape": blocks[op]["shape"], "text": blocks[op].get("text"),
                        "inputs": {n: (i.get("shadow") or "boolean") for n, i in blocks[op]["inputs"].items()},
                        "fields": {n: (f.get("options") or f["type"]) for n, f in blocks[op]["fields"].items()}} for op in ext["blocks"]],
            "menus": {op: {n: f.get("options") for n, f in blocks[op]["fields"].items()} for op in ext["menus"]}}


@action(G)
def enable(ctx: Ctx, extension: str, project: str | None = None) -> dict:
    """Add an extension to the project (blocks from it can then be used; it appears in the editor's block palette)."""
    if extension not in schema.extensions():
        raise WorkspaceError(f"Unknown extension '{extension}'. Available: {', '.join(schema.extensions())}.")
    with ctx.store.edit(project, f"enable {extension}") as h:
        exts = h.project.setdefault("extensions", [])
        if extension not in exts:
            exts.append(extension)
    req = REQUIREMENTS.get(extension, {})
    return {"enabled": extension, "extensions": ctx.session(project).project["extensions"],
            **({"warning": f"Needs {req['hardware']} and {req['service']}; hardware connectivity is not supported here."} if req.get("hardware") and req.get("service") else {})}


@action(G)
def disable(ctx: Ctx, extension: str, remove_blocks: bool = False, project: str | None = None) -> dict:
    """Remove an extension from the project. Refuses while its blocks are used unless remove_blocks=true (which deletes those blocks and their scripts' following blocks)."""
    from ..engine import Graph

    session = ctx.session(project)
    with ctx.store.edit(project, f"disable {extension}") as h:
        used = _used(h.project, extension)
        if used and not remove_blocks:
            raise WorkspaceError(f"{used} block(s) of '{extension}' are in use. Remove them first or pass remove_blocks=true.")
        removed = 0
        if used:
            prefix = extension + "_"
            for t in h.project["targets"]:
                g = Graph(h.project, t)
                for bid, b in list((t.get("blocks") or {}).items()):
                    if isinstance(b, dict) and b.get("opcode", "").startswith(prefix) and not b.get("shadow") and bid in t["blocks"]:
                        removed += len(g.delete(bid, mode="single"))
        h.project["extensions"] = [e for e in h.project.get("extensions") or [] if e != extension]
    _ = session
    return {"disabled": extension, "blocks_removed": removed}


@action(G)
async def verify(ctx: Ctx, project: str | None = None, run_seconds: float = 1.0) -> dict:
    """Load the project in the real Scratch VM and run the green flag for a moment: proves each enabled extension loads, and reports VM errors."""
    from .runtime import frames_for

    session = ctx.session(project)
    exts = list(session.project.get("extensions") or [])
    rm = ctx.runtime
    await rm.start(session.name, session.project, session.assets)
    loaded = await rm.call(session.name, "loadedExtensions")
    await rm.call(session.name, "flag")
    await rm.run_frames(session.name, frames_for(run_seconds))
    errs = rm.errors(session.name)
    return {"declared": exts, "loaded_in_vm": loaded, "all_loaded": all(e in loaded for e in exts),
            "runtime_errors": errs, "hardware_needed": [e for e in exts if REQUIREMENTS.get(e, {}).get("hardware")]}
