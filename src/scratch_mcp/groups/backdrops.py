"""backdrop_manager: backdrops and stage properties (wrappers over costume_manager with sprite='Stage')."""

from __future__ import annotations

from ..ctx import Ctx
from ..registry import GROUP_DOCS, Reply, action
from ..workspace import WorkspaceError
from . import costumes as C

G = "backdrop_manager"
GROUP_DOCS[G] = (
    "Backdrops and the Stage. Backdrops are costumes of the Stage: create (blank / SVG / import / stock 'kitchen'), "
    "rename, duplicate, reorder, delete, set the starting backdrop, preview, export - and draw on them with "
    "costume_manager draw/transform/... using sprite='Stage'. 'stage_get'/'stage_set' read and change stage settings "
    "(volume, tempo, video, text-to-speech language). Stage scripts: script_manager with sprite='Stage'. "
    "Switching backdrops at run time uses the 'switch backdrop to' blocks."
)

S = "Stage"


@action(G, "list")
def list_backdrops(ctx: Ctx, project: str | None = None) -> dict:
    """List backdrops (number, name, format, size, rotation centre, which one is current)."""
    return C.list_costumes(ctx, sprite=S, project=project)


@action(G)
def add_blank(ctx: Ctx, name: str = "backdrop", background: str | None = "#ffffff", width: float = 480, height: float = 360,
              project: str | None = None) -> dict:
    """Add a blank vector backdrop (default 480x360, white)."""
    return C.add_blank(ctx, name, width, height, background, S, project)


@action(G)
def add_svg(ctx: Ctx, name: str, svg: str, project: str | None = None) -> dict:
    """Add a backdrop from SVG text (480x360 fills the stage; centre defaults to the middle)."""
    return C.add_svg(ctx, name, svg, None, None, S, project)


@action(G)
def import_image(ctx: Ctx, name: str, source_path: str | None = None, data_base64: str | None = None,
                 bitmap_resolution: int = 2, project: str | None = None) -> dict:
    """Import a PNG/JPEG/SVG as a backdrop."""
    return C.import_image(ctx, name, source_path, data_base64, bitmap_resolution, S, project)


@action(G)
def add_stock(ctx: Ctx, art: str = "kitchen", replace: bool = False, project: str | None = None) -> dict:
    """Add stock backdrops (currently: kitchen = futuristic kitchen, 2 animated frames)."""
    return C.add_stock(ctx, art, replace, S, project)


@action(G)
def delete(ctx: Ctx, backdrop: str | int, project: str | None = None) -> dict:
    """Delete a backdrop (the Stage keeps at least one)."""
    return C.delete(ctx, backdrop, S, project)


@action(G)
def duplicate(ctx: Ctx, backdrop: str | int | None = None, new_name: str | None = None, project: str | None = None) -> dict:
    """Duplicate a backdrop."""
    return C.duplicate(ctx, backdrop, new_name, S, project)


@action(G)
def rename(ctx: Ctx, backdrop: str | int, new_name: str, project: str | None = None) -> dict:
    """Rename a backdrop (blocks that name it are updated)."""
    return C.rename(ctx, backdrop, new_name, S, project)


@action(G)
def reorder(ctx: Ctx, backdrop: str | int, position: int, project: str | None = None) -> dict:
    """Move a backdrop to a 1-based position (affects 'next backdrop')."""
    return C.reorder(ctx, backdrop, position, S, project)


@action(G)
def set_initial(ctx: Ctx, backdrop: str | int, project: str | None = None) -> dict:
    """Choose the backdrop shown when the project starts (also saved as the current one)."""
    return C.set_current(ctx, backdrop, S, project)


@action(G)
async def preview(ctx: Ctx, backdrop: str | int | None = None, project: str | None = None, scale: float = 1.0) -> Reply:
    """Render a backdrop as a PNG image (480x360 at scale 1)."""
    return await C.preview(ctx, backdrop, S, project, scale, None)


@action(G)
def export(ctx: Ctx, backdrop: str | int | None = None, project: str | None = None, include_base64: bool = False) -> dict:
    """Write the backdrop file to the exports folder."""
    return C.export(ctx, backdrop, S, project, include_base64)


@action(G)
def stage_get(ctx: Ctx, project: str | None = None) -> dict:
    """Stage settings and counts."""
    s = ctx.session(project)
    st = ctx.target(s.project, s, S)
    cur = st.get("currentCostume", 0)
    return {"current_backdrop": st["costumes"][cur]["name"], "backdrops": len(st["costumes"]), "volume": st.get("volume"),
            "tempo": st.get("tempo"), "video_state": st.get("videoState"), "video_transparency": st.get("videoTransparency"),
            "text_to_speech_language": st.get("textToSpeechLanguage"), "scripts_blocks": len(st.get("blocks") or {}),
            "sounds": [x["name"] for x in st.get("sounds") or []],
            "global_variables": [v[0] for v in (st.get("variables") or {}).values()],
            "global_lists": [v[0] for v in (st.get("lists") or {}).values()],
            "broadcasts": list((st.get("broadcasts") or {}).values())}


@action(G)
def stage_set(ctx: Ctx, volume: float | None = None, tempo: float | None = None, video_state: str | None = None,
              video_transparency: float | None = None, text_to_speech_language: str | None = None,
              project: str | None = None) -> dict:
    """Change stage settings. volume 0-100; tempo 20-500 bpm (Music extension); video_state on|off|on-flipped; video_transparency 0-100; text_to_speech_language e.g. 'en'."""
    changes = {}
    if volume is not None:
        if not 0 <= volume <= 100:
            raise WorkspaceError("volume must be 0-100.")
        changes["volume"] = volume
    if tempo is not None:
        if not 20 <= tempo <= 500:
            raise WorkspaceError("tempo must be 20-500.")
        changes["tempo"] = tempo
    if video_state is not None:
        if video_state not in ("on", "off", "on-flipped"):
            raise WorkspaceError("video_state must be on, off or on-flipped.")
        changes["videoState"] = video_state
    if video_transparency is not None:
        if not 0 <= video_transparency <= 100:
            raise WorkspaceError("video_transparency must be 0-100.")
        changes["videoTransparency"] = video_transparency
    if text_to_speech_language is not None:
        changes["textToSpeechLanguage"] = text_to_speech_language
    if not changes:
        raise WorkspaceError("Nothing to change: pass at least one setting.")
    session = ctx.session(project)
    with ctx.store.edit(project, "stage settings") as h:
        ctx.target(h.project, session, S).update(changes)
    return {"updated": changes}
