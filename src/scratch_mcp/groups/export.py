"""export_manager: .sb3 / .sprite3 / assets / screenshots / video out of a project, with verification."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import shutil
import zipfile
from datetime import datetime
from typing import Any

from .. import audio, editing
from ..ctx import Ctx
from ..registry import GROUP_DOCS, Reply, action
from ..runtime.manager import FRAME_MS, installed
from ..textparse import make_id_factory
from ..validate import validate_project
from ..workspace import Sb3, WorkspaceError
from . import costumes as C
from . import sounds as S
from .runtime import ensure, frames_for

G = "export_manager"
GROUP_DOCS[G] = (
    "Deliver the work. Everything is written under <projects folder>/exports/. 'sb3' writes a verified copy of the project "
    "(then reopens it, validates it, compares it with the in-memory project and - if the runtime is installed - loads it "
    "in the real Scratch VM); 'sprite' writes a .sprite3; 'costume' / 'sound' write the asset file; 'screenshot' saves a "
    "stage PNG; 'video' RECORDS the running project to an MP4 (needs ffmpeg + the runtime; audio = the sounds the project "
    "started, mixed in at the right moment; Music-extension notes and text-to-speech are not included); 'verify' re-checks any "
    "exported .sb3. Scratch has no built-in video export - this one is produced by stepping the real VM frame by frame."
)


def _exports(ctx: Ctx):
    d = ctx.ws.root / "exports"
    d.mkdir(exist_ok=True)
    return d


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_ ." else "_" for ch in name).strip() or "export"


def _summary(project: dict[str, Any], assets: set[str]) -> dict[str, Any]:
    return {"sprites": sorted(t["name"] for t in project["targets"] if not t.get("isStage")),
            "blocks": sum(len(t.get("blocks") or {}) for t in project["targets"]),
            "costumes": sum(len(t.get("costumes") or []) for t in project["targets"]),
            "sounds": sum(len(t.get("sounds") or []) for t in project["targets"]),
            "extensions": sorted(project.get("extensions") or []), "asset_files": sorted(assets)}


async def _verify_file(ctx: Ctx, path, reference: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"file": ctx.ws.display(path), "bytes": path.stat().st_size}
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            names = set(zf.namelist())
            project = json.loads(zf.read("project.json").decode("utf-8"))
            assets = {n for n in names if n != "project.json"}
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        return {**out, "ok": False, "problems": [f"cannot be reopened: {exc}"]}
    result = validate_project(project, assets)
    problems = list(result.errors)
    if bad:
        problems.append(f"corrupt zip member {bad}")
    now = _summary(project, assets)
    out["summary"] = {k: v for k, v in now.items() if k != "asset_files"} | {"asset_files": len(assets)}
    if reference is not None:
        for k in ("sprites", "blocks", "costumes", "sounds", "extensions", "asset_files"):
            if now[k] != reference[k]:
                problems.append(f"{k} differ between the exported file and the project in memory")
    out["warnings"] = result.warnings[:10]
    st = ctx.runtime.status() if installed() else None
    if st and st["playwright"] and st["chromium"]:
        key = f"__verify__{path.name}"
        try:
            await ctx.runtime.start(key, project, {n: zipfile.ZipFile(path).read(n) for n in assets})
            out["loads_in_scratch_vm"] = True
        except WorkspaceError as exc:
            out["loads_in_scratch_vm"] = False
            problems.append(f"the Scratch VM could not load it: {exc}")
        finally:
            await ctx.runtime.stop(key)
    else:
        out["loads_in_scratch_vm"] = None  # runtime not installed - not verified
    out["ok"] = not problems
    out["problems"] = problems
    return out


@action(G)
async def sb3(ctx: Ctx, name: str | None = None, project: str | None = None, overwrite: bool = False) -> dict:
    """Write the project's CURRENT state (saved or not) to exports/<name>.sb3 and verify it (reopen, validate, compare, load in the VM).

    Args:
        name: file name without extension (default: project name + timestamp).
        overwrite: replace an existing export of that name.
    """
    session = ctx.session(project)
    base = _safe(name or f"{session.name.rsplit('.', 1)[0]}-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    path = _exports(ctx) / f"{base}.sb3"
    if path.exists() and not overwrite:
        raise WorkspaceError(f"exports/{base}.sb3 already exists. Pass overwrite=true or choose another name.")
    ctx.ws.write(path, Sb3(session.project, session.assets), overwrite=overwrite)
    return await _verify_file(ctx, path, _summary(session.project, set(session.assets)))


@action(G)
async def verify(ctx: Ctx, path: str) -> dict:
    """Re-check an exported .sb3 inside the projects folder: reopen, validate structure/assets, and load it in the VM."""
    p = ctx.ws.resolve_file(path)
    return await _verify_file(ctx, p, None)


@action(G)
def sprite(ctx: Ctx, sprite: str | None = None, project: str | None = None, name: str | None = None, overwrite: bool = False) -> dict:
    """Export one sprite as exports/<name>.sprite3 (costumes, sounds, scripts, local variables) and check that it imports back."""
    import copy

    session = ctx.session(project)
    t = ctx.target(session.project, session, sprite)
    if t.get("isStage"):
        raise WorkspaceError("The Stage can't be exported as a sprite.")
    path = _exports(ctx) / f"{_safe(name or t['name'])}.sprite3"
    if path.exists() and not overwrite:
        raise WorkspaceError(f"{ctx.ws.display(path)} already exists. Pass overwrite=true or choose another name.")
    data = copy.deepcopy(t)
    global_vars = {vid for tt in session.project["targets"] if tt.get("isStage") for vid in (tt.get("variables") or {})}
    uses_global = any(isinstance(b, dict) and any(isinstance(f, list) and len(f) > 1 and f[1] in global_vars for f in (b.get("fields") or {}).values())
                      for b in (t.get("blocks") or {}).values())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sprite.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        for a in (data.get("costumes") or []) + (data.get("sounds") or []):
            zf.writestr(a["md5ext"], session.assets[a["md5ext"]])
    path.write_bytes(buf.getvalue())
    # round-trip check: import into a scratch copy of the project
    probe = copy.deepcopy(session.project)
    probe_assets = dict(session.assets)
    back = editing.import_sprite3(probe, probe_assets, buf.getvalue(), make_id_factory(probe))
    ok = len(back["blocks"]) == len(t.get("blocks") or {}) and validate_project(probe, set(probe_assets)).ok
    return {"exported_to": ctx.ws.display(path), "bytes": path.stat().st_size, "reimport_ok": ok,
            **({"note": "The scripts use global ('for all sprites') variables; recreate them in the destination project."} if uses_global else {})}


@action(G)
def costume(ctx: Ctx, costume: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Export a costume file (svg/png/jpg) to exports/. Use sprite='Stage' for a backdrop."""
    return C.export(ctx, costume, sprite, project, False)


@action(G)
def sound(ctx: Ctx, sound: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Export a sound file (wav) to exports/."""
    return S.export(ctx, sound, sprite, project)


@action(G)
async def screenshot(ctx: Ctx, name: str | None = None, project: str | None = None, scale: int = 1) -> Reply:
    """Save the running stage as exports/<name>.png and also return the image."""
    session, rm = await ensure(ctx, project)
    png = await rm.screenshot(session.name, scale)
    path = _exports(ctx) / f"{_safe(name or session.name.rsplit('.', 1)[0] + '-' + datetime.now().strftime('%H%M%S'))}.png"
    path.write_bytes(png)
    return Reply(text={"saved_to": ctx.ws.display(path), "bytes": len(png)}, images=[(png, "image/png")])


def _mix_audio(project: dict[str, Any], assets: dict[str, bytes], events: list[dict[str, Any]], seconds: float, rate: int = 22050) -> tuple[bytes | None, int]:
    total = int(seconds * rate)
    buf = [0.0] * total
    used = 0
    stops = sorted(e["t"] for e in events if e["type"] == "sound_stopallsounds")
    for e in events:
        if e["type"] not in ("sound_play", "sound_playuntildone"):
            continue
        name = (e.get("args") or {}).get("SOUND_MENU")
        t = next((t for t in project["targets"] if ("Stage" if t.get("isStage") else t["name"]) == e.get("sprite")), None)
        entry = next((x for x in (t or {}).get("sounds") or [] if x["name"] == name), None)
        if entry is None or entry.get("dataFormat") != "wav":
            continue
        try:
            pcm = audio.decode(assets[entry["md5ext"]])
        except WorkspaceError:
            continue
        pcm = audio.resample(pcm, rate) if pcm.rate != rate else pcm
        mono = [sum(c[i] for c in pcm.data) // pcm.channels for i in range(pcm.frames)] if pcm.channels > 1 else pcm.data[0]
        start = int(e["t"] * rate)
        cut = next((int(s * rate) for s in stops if s > e["t"]), None)
        for i, v in enumerate(mono):
            j = start + i
            if j >= total or (cut is not None and j >= cut):
                break
            buf[j] += v * 0.8
        used += 1
    if not used:
        return None, 0
    pcm = audio.Pcm(rate, 1, [[max(-32768, min(32767, int(v))) for v in buf]])
    return audio.encode(pcm), used


@action(G)
async def video(ctx: Ctx, seconds: float = 10, name: str | None = None, project: str | None = None, fps: int = 30,
                with_audio: bool = True, inputs: list[dict[str, Any]] | None = None, overwrite: bool = False) -> dict:
    """Record the project as an MP4: reload it, press the green flag, step the real VM frame by frame, capture the stage each frame (480x360), mix in the sounds the project started, encode with ffmpeg, then verify duration/resolution with ffprobe.

    Args:
        seconds: length of the recording in simulated seconds (max 300).
        name: output name (exports/<name>.mp4).
        fps: 15-60 (the project itself always runs at 30 frames/second; other values repeat/skip frames).
        with_audio: mix in sound-effect starts (no Music-extension notes or speech).
        inputs: optional timed inputs while recording, e.g. [{"at": 2.5, "key": "space"}, {"at": 4, "click": [100, 50]}, {"at": 6, "answer": "Ada"}].
    """
    if not 1 <= seconds <= 300:
        raise WorkspaceError("seconds must be 1-300.")
    if not 15 <= fps <= 60:
        raise WorkspaceError("fps must be 15-60.")
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg:
        raise WorkspaceError("ffmpeg is needed to encode video. Install it (apt install ffmpeg / brew install ffmpeg) and try again.")
    session = ctx.session(project)
    rm = ctx.runtime
    await rm.start(session.name, session.project, session.assets)
    key = session.name
    base = _safe(name or f"{session.name.rsplit('.', 1)[0]}-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    out_path = _exports(ctx) / f"{base}.mp4"
    if out_path.exists() and not overwrite:
        raise WorkspaceError(f"{ctx.ws.display(out_path)} already exists. Pass overwrite=true or choose another name.")
    timed = sorted((inputs or []), key=lambda i: i.get("at", 0))
    sim_frames = frames_for(seconds)
    tmp_video = out_path.with_suffix(".video.mp4")
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", "30", "-vcodec", "mjpeg", "-i", "-",
           "-vf", f"fps={fps}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(tmp_video)]
    proc = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await rm.call(key, "flag")
    ti = 0
    try:
        for f in range(sim_frames):
            t_now = f * FRAME_MS / 1000
            while ti < len(timed) and timed[ti].get("at", 0) <= t_now:
                step = timed[ti]
                ti += 1
                if "key" in step:
                    await rm.call(key, "key", step["key"], True)
                    await rm.call(key, "advance", 2, FRAME_MS)
                    await rm.call(key, "key", step["key"], False)
                elif "click" in step:
                    x, y = step["click"]
                    await rm.call(key, "mouse", x, y, True)
                    await rm.call(key, "advance", 2, FRAME_MS)
                    await rm.call(key, "mouse", x, y, False)
                elif "answer" in step:
                    await rm.call(key, "answer", step["answer"])
            b64 = await rm.call(key, "shoot", FRAME_MS, 0.95, timeout=60)
            proc.stdin.write(base64.b64decode(b64))
            if f % 30 == 0:
                await proc.stdin.drain()
        proc.stdin.close()
        err = (await proc.stderr.read()).decode(errors="replace")
        rc = await proc.wait()
    except Exception:
        proc.kill()
        raise
    if rc != 0:
        raise WorkspaceError(f"ffmpeg failed: {err[-400:]}")
    events = (await rm.call(key, "eventsSince", 0, None, 0))["events"]
    mixed, n_sounds = (None, 0)
    if with_audio:
        mixed, n_sounds = _mix_audio(session.project, session.assets, events, seconds)
    if mixed:
        wav_path = out_path.with_suffix(".audio.wav")
        wav_path.write_bytes(mixed)
        mux = await asyncio.create_subprocess_exec(ffmpeg, "-y", "-loglevel", "error", "-i", str(tmp_video), "-i", str(wav_path), "-c:v", "copy",
                                                   "-c:a", "aac", "-b:a", "128k", "-shortest", str(out_path), stderr=asyncio.subprocess.PIPE)
        merr = (await mux.stderr.read()).decode(errors="replace")
        if await mux.wait() != 0:
            raise WorkspaceError(f"ffmpeg could not add audio: {merr[-300:]}")
        wav_path.unlink(missing_ok=True)
        tmp_video.unlink(missing_ok=True)
    else:
        tmp_video.replace(out_path)
    info: dict[str, Any] = {"saved_to": ctx.ws.display(out_path), "bytes": out_path.stat().st_size, "requested_seconds": seconds,
                            "sound_effects_mixed": n_sounds, "has_audio": bool(mixed), "inputs_applied": ti}
    if ffprobe:
        pr = await asyncio.create_subprocess_exec(ffprobe, "-v", "error", "-show_entries", "stream=codec_type,width,height,duration,nb_frames",
                                                  "-of", "json", str(out_path), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        raw, _ = await pr.communicate()
        try:
            streams = json.loads(raw)["streams"]
            v = next(s for s in streams if s["codec_type"] == "video")
            info["verified"] = {"width": v["width"], "height": v["height"], "video_seconds": round(float(v.get("duration", 0)), 3),
                                "frames": int(v.get("nb_frames", 0)), "audio_stream": any(s["codec_type"] == "audio" for s in streams)}
        except (ValueError, KeyError, StopIteration):
            info["verified"] = "ffprobe could not read the file"
    else:
        info["verified"] = "ffprobe not installed - duration/resolution not verified"
    return info
