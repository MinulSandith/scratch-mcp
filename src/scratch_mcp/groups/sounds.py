"""sound_manager: sounds of a sprite or the Stage - import, synthesize, edit (trim/cut/reverse/volume/effects), preview."""

from __future__ import annotations

import base64
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .. import audio, editing, sounds
from ..ctx import Ctx
from ..registry import GROUP_DOCS, Reply, action
from ..workspace import WorkspaceError

G = "sound_manager"
GROUP_DOCS[G] = (
    "Sounds of a sprite or the Stage (sprite='Stage'). Import WAV (or mp3/ogg/flac/m4a when ffmpeg is installed), "
    "generate sounds (presets: pop, boing, bloop, squeak, alien_warble, crack, munch, chime, whoosh, sad_trombone, "
    "music_cheerful/calm/sneaky - length and tempo adjustable - or pure tones), rename/duplicate/delete, and edit audio: "
    "trim, cut/copy/paste segments, silence, reverse, volume, normalize, fades, echo, speed (faster/slower), robot voice. "
    "'preview' returns the audio itself (as MCP audio content) so you can listen. Play sounds at run time with the "
    "'start sound' blocks, and test them with runtime_manager / testing_manager (sound plays are logged). Recording from a "
    "microphone is not possible in this headless server - synthesize or import instead."
)

AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma"}


def _find(target: dict[str, Any], sound: str | int | None) -> tuple[int, dict[str, Any]]:
    items = target.get("sounds") or []
    if not items:
        raise WorkspaceError("This target has no sounds.")
    names = [s["name"] for s in items]
    if sound is None:
        if len(items) == 1:
            return 0, items[0]
        raise WorkspaceError(f"Specify which sound. Available: {', '.join(names)}")
    if sound in names:
        return names.index(sound), items[names.index(sound)]
    if isinstance(sound, int) or (isinstance(sound, str) and sound.isdigit()):
        n = int(sound)
        if 1 <= n <= len(items):
            return n - 1, items[n - 1]
    raise WorkspaceError(f"No sound '{sound}'. Available: {', '.join(names)}")


def _wav_of(assets: dict[str, bytes], entry: dict[str, Any]) -> bytes:
    if entry.get("dataFormat") != "wav":
        raise WorkspaceError(f"'{entry['name']}' is {entry.get('dataFormat')}; only WAV sounds can be edited.")
    return assets[entry["md5ext"]]


def _replace(h, entry: dict[str, Any], p: audio.Pcm) -> None:
    wav = audio.encode(p)
    md5 = editing.md5_of(wav)
    h.assets[f"{md5}.wav"] = wav
    entry.update(assetId=md5, md5ext=f"{md5}.wav", dataFormat="wav", format="", rate=p.rate, sampleCount=p.frames)
    editing.prune_unused_assets(h.project, h.assets)


def to_wav(data: bytes, filename: str) -> bytes:
    """Return WAV bytes: pass WAV through, convert other formats with ffmpeg if available."""
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return data
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise WorkspaceError("Only WAV files can be imported directly. Install ffmpeg to import mp3/ogg/flac/m4a, "
                             "or convert the file to WAV first.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / ("in" + (Path(filename).suffix or ".bin"))
        dst = Path(tmp) / "out.wav"
        src.write_bytes(data)
        r = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "22050", "-sample_fmt", "s16", str(dst)],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0 or not dst.exists():
            raise WorkspaceError(f"ffmpeg could not convert the file: {r.stderr.strip()[:200]}")
        return dst.read_bytes()


@action(G, "list")
def list_sounds(ctx: Ctx, sprite: str | None = None, project: str | None = None) -> dict:
    """List sounds with duration, sample rate and size."""
    s = ctx.session(project)
    t = ctx.target(s.project, s, sprite)
    return {"target": "Stage" if t.get("isStage") else t["name"], "sounds": [
        {"number": i + 1, "name": x["name"], "seconds": round(x["sampleCount"] / x["rate"], 3) if x.get("rate") else None,
         "rate": x.get("rate"), "format": x["dataFormat"], "bytes": len(s.assets.get(x["md5ext"], b""))}
        for i, x in enumerate(t.get("sounds") or [])]}


@action(G)
def add_preset(ctx: Ctx, name: str, preset: str, seconds: float | None = None, tempo: float | None = None,
               sprite: str | None = None, project: str | None = None) -> dict:
    """Generate a sound from a built-in preset (see tool description). For music_* presets 'seconds' sets the length (up to 120) and 'tempo' the bpm; a track as long as your animation ends with a final chord.

    Args:
        name: name for the new sound.
        preset: pop, boing, bloop, squeak, alien_warble, crack, munch, chime, whoosh, sad_trombone, music_cheerful, music_calm, music_sneaky.
    """
    if preset not in sounds.PRESETS:
        raise WorkspaceError(f"Unknown preset '{preset}'. Choose from: {', '.join(sounds.PRESETS)}.")
    wav = sounds.render_preset(preset, seconds, tempo)
    return _add(ctx, project, sprite, name, wav)


def _add(ctx: Ctx, project: str | None, sprite: str | None, name: str, wav: bytes) -> dict:
    session = ctx.session(project)
    with ctx.store.edit(project, f"add sound {name}") as h:
        t = ctx.target(h.project, session, sprite)
        entry = editing.add_sound(h.assets, t, name, wav)
    return {"added": entry["name"], "seconds": round(entry["sampleCount"] / entry["rate"], 3), "rate": entry["rate"]}


@action(G)
def add_tone(ctx: Ctx, name: str, frequency: float, seconds: float = 0.5, wave: str = "sine", volume: float = 0.6,
             sprite: str | None = None, project: str | None = None) -> dict:
    """Generate a pure tone (sine, square, saw or triangle wave) as a sound."""
    return _add(ctx, project, sprite, name, audio.encode(audio.tone(frequency, seconds, wave, volume=volume)))


@action(G)
def import_sound(ctx: Ctx, name: str, source_path: str | None = None, data_base64: str | None = None,
                 sprite: str | None = None, project: str | None = None) -> dict:
    """Import an audio file (WAV directly; mp3/ogg/flac/m4a via ffmpeg) from the projects folder or base64 data."""
    if bool(source_path) == bool(data_base64):
        raise WorkspaceError("Give exactly one of source_path or data_base64.")
    if source_path:
        path = ctx.ws.resolve_file(source_path)
        data, fname = path.read_bytes(), path.name
    else:
        data, fname = base64.b64decode(data_base64 or ""), "upload.wav"
    return _add(ctx, project, sprite, name, to_wav(data, fname))


@action(G)
def rename(ctx: Ctx, sound: str | int, new_name: str, sprite: str | None = None, project: str | None = None) -> dict:
    """Rename a sound (blocks that name it in a 'start sound' menu are updated)."""
    session = ctx.session(project)
    with ctx.store.edit(project, "rename sound") as h:
        t = ctx.target(h.project, session, sprite)
        _, entry = _find(t, sound)
        if not new_name.strip():
            raise WorkspaceError("New name is empty.")
        if any(x is not entry and x["name"] == new_name for x in t["sounds"]):
            raise WorkspaceError(f"A sound named '{new_name}' already exists.")
        old = entry["name"]
        entry["name"] = new_name
        for b in (t.get("blocks") or {}).values():
            if isinstance(b, dict) and b.get("opcode") == "sound_sounds_menu":
                f = (b.get("fields") or {}).get("SOUND_MENU")
                if f and f[0] == old:
                    f[0] = new_name
    return {"renamed": f"{old} -> {new_name}"}


@action(G)
def delete(ctx: Ctx, sound: str | int, sprite: str | None = None, project: str | None = None) -> dict:
    """Delete a sound."""
    session = ctx.session(project)
    with ctx.store.edit(project, "delete sound") as h:
        t = ctx.target(h.project, session, sprite)
        i, entry = _find(t, sound)
        del t["sounds"][i]
        editing.prune_unused_assets(h.project, h.assets)
    return {"deleted": entry["name"]}


@action(G)
def duplicate(ctx: Ctx, sound: str | int, new_name: str | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Duplicate a sound (placed after the original)."""
    import copy

    session = ctx.session(project)
    with ctx.store.edit(project, "duplicate sound") as h:
        t = ctx.target(h.project, session, sprite)
        i, entry = _find(t, sound)
        new = copy.deepcopy(entry)
        new["name"] = editing._unique(new_name or entry["name"], [x["name"] for x in t["sounds"]])
        t["sounds"].insert(i + 1, new)
    return {"created": new["name"]}


@action(G)
def edit(ctx: Ctx, sound: str | int, operation: str, sprite: str | None = None, project: str | None = None,
         start: float | None = None, end: float | None = None, factor: float | None = None, seconds: float | None = None,
         delay: float = 0.25, decay: float = 0.5, frequency: float = 50.0, save_as: str | None = None) -> dict:
    """Edit a WAV sound in place (or into a new sound with save_as). operation:
    trim (keep start..end seconds) | cut (remove start..end) | silence (mute start..end) | reverse (whole sound or start..end) |
    volume (multiply by factor; 2 = louder, 0.5 = softer; optionally only start..end) | normalize | fade_in / fade_out (over 'seconds') |
    echo (delay seconds, decay 0-1) | faster / slower (speed factor, changes pitch; default 1.25 / 0.8) | robot (ring-mod at frequency Hz).

    Args:
        operation: one of the names above.
        start: range start in seconds.
        end: range end in seconds.
        factor: volume or speed multiplier.
        save_as: write the result as a new sound with this name and keep the original.
    """
    session = ctx.session(project)
    with ctx.store.edit(project, f"{operation} sound") as h:
        t = ctx.target(h.project, session, sprite)
        _, entry = _find(t, sound)
        p = audio.decode(_wav_of(h.assets, entry))
        if operation == "trim":
            out = audio.trim(p, start, end)
        elif operation == "cut":
            if start is None or end is None:
                raise WorkspaceError("cut needs start and end.")
            out, _ = audio.cut(p, start, end)
        elif operation == "silence":
            if start is None or end is None:
                raise WorkspaceError("silence needs start and end.")
            out = audio.silence(p, start, end)
        elif operation == "reverse":
            out = audio.reverse(p, start, end)
        elif operation == "volume":
            if factor is None:
                raise WorkspaceError("volume needs factor (e.g. 2 or 0.5).")
            out = audio.gain(p, factor, start, end)
        elif operation == "normalize":
            out = audio.normalize(p)
        elif operation in ("fade_in", "fade_out"):
            out = audio.fade(p, seconds if seconds is not None else 0.5, operation[5:])
        elif operation == "echo":
            out = audio.echo(p, delay, decay)
        elif operation == "faster":
            out = audio.speed(p, factor or 1.25)
        elif operation == "slower":
            out = audio.speed(p, factor or 0.8)
        elif operation == "robot":
            out = audio.robot(p, frequency)
        else:
            raise WorkspaceError("Unknown operation. Use trim, cut, silence, reverse, volume, normalize, fade_in, fade_out, "
                                 "echo, faster, slower or robot.")
        if save_as:
            e = editing.add_sound(h.assets, t, save_as, audio.encode(out))
            target_entry = e
        else:
            _replace(h, entry, out)
            target_entry = entry
    return {"sound": target_entry["name"], "seconds": round(out.seconds, 3), "was_seconds": round(p.seconds, 3)}


@action(G)
def copy_segment(ctx: Ctx, sound: str | int, start: float, end: float, sprite: str | None = None, project: str | None = None) -> dict:
    """Copy part of a sound to the audio clipboard (paste with paste_segment into any sound)."""
    s = ctx.session(project)
    t = ctx.target(s.project, s, sprite)
    _, entry = _find(t, sound)
    seg = audio.trim(audio.decode(_wav_of(s.assets, entry)), start, end)
    ctx.audio_clipboard = audio.encode(seg)
    return {"copied_seconds": round(seg.seconds, 3)}


@action(G)
def paste_segment(ctx: Ctx, sound: str | int, at: float, sprite: str | None = None, project: str | None = None) -> dict:
    """Insert the copied segment at a time position (seconds) in a sound."""
    if not ctx.audio_clipboard:
        raise WorkspaceError("The audio clipboard is empty. Use copy_segment first.")
    session = ctx.session(project)
    with ctx.store.edit(project, "paste audio segment") as h:
        t = ctx.target(h.project, session, sprite)
        _, entry = _find(t, sound)
        out = audio.insert(audio.decode(_wav_of(h.assets, entry)), audio.decode(ctx.audio_clipboard), at)
        _replace(h, entry, out)
    return {"sound": entry["name"], "seconds": round(out.seconds, 3)}


@action(G)
def preview(ctx: Ctx, sound: str | int | None = None, sprite: str | None = None, project: str | None = None,
            max_seconds: float = 15) -> Reply:
    """Return the sound as audio content (first max_seconds) so it can be listened to, plus its stats (peak level, duration)."""
    s = ctx.session(project)
    t = ctx.target(s.project, s, sprite)
    _, entry = _find(t, sound)
    wav = _wav_of(s.assets, entry)
    p = audio.decode(wav)
    peak = max((abs(v) for c in p.data for v in c), default=0) / 32767
    clip = audio.trim(p, 0, min(p.seconds, max_seconds)) if p.seconds > max_seconds else p
    return Reply(text={"sound": entry["name"], "seconds": round(p.seconds, 3), "rate": p.rate, "channels": p.channels,
                       "peak": round(peak, 3), "silent": peak == 0, "truncated": p.seconds > max_seconds},
                 audio=[(audio.encode(clip), "audio/wav")])


@action(G)
def export(ctx: Ctx, sound: str | int | None = None, sprite: str | None = None, project: str | None = None) -> dict:
    """Write the sound file to <projects folder>/exports/."""
    s = ctx.session(project)
    t = ctx.target(s.project, s, sprite)
    _, entry = _find(t, sound)
    safe = "".join(ch if ch.isalnum() or ch in "-_ ." else "_" for ch in f"{t['name']}-{entry['name']}")
    folder = ctx.ws.root / "exports"
    folder.mkdir(exist_ok=True)
    path = folder / f"{safe}.{entry['dataFormat']}"
    path.write_bytes(s.assets[entry["md5ext"]])
    return {"exported_to": ctx.ws.display(path)}
