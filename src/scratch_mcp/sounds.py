"""Tiny dependency-free sound synthesizer for cartoon sound effects and music.

Everything is rendered as 16-bit mono 22050 Hz WAV, which Scratch loads natively.
"""

from __future__ import annotations

import io
import math
import random
import struct
import wave

RATE = 22050
MAX_SECONDS = 120

# name -> description
PRESETS = {
    "pop": "short bubble pop (appearing / popping)",
    "boing": "springy boing (surprise, bounce)",
    "bloop": "quick friendly blip (footsteps, button)",
    "squeak": "rubber squeak (straining, tugging)",
    "alien_warble": "wobbly alien arrival sound",
    "crack": "crisp snap (something breaking)",
    "munch": "short crunchy bite",
    "chime": "happy rising three-note chime (success, happy ending)",
    "whoosh": "fast swoosh (quick movement)",
    "sad_trombone": "descending wah-wah (disappointment)",
    "music_cheerful": "bouncy upbeat looping tune for kids' cartoons (params: seconds, tempo)",
    "music_calm": "slow gentle tune (params: seconds, tempo)",
    "music_sneaky": "tip-toe pizzicato tune (params: seconds, tempo)",
}


def _tri(phase: float) -> float:
    return 2 * abs(2 * (phase - math.floor(phase + 0.5))) - 1


def _sq(phase: float, duty: float = 0.5) -> float:
    return 1.0 if (phase % 1.0) < duty else -1.0


def _env(i: int, n: int, attack: float = 0.005, release: float = 0.3) -> float:
    t = i / RATE
    dur = n / RATE
    a = min(1.0, t / attack) if attack else 1.0
    r = min(1.0, (dur - t) / (dur * release)) if release else 1.0
    return max(0.0, a * r)


def _sweep(seconds: float, f0: float, f1: float, wave_fn=math.sin, vibrato=(0.0, 0.0), decay=3.0, amp=0.7):
    n = int(seconds * RATE)
    out, phase = [], 0.0
    for i in range(n):
        t = i / n
        f = f0 + (f1 - f0) * t
        if vibrato[0]:
            f += vibrato[0] * math.sin(2 * math.pi * vibrato[1] * i / RATE)
        phase += f / RATE
        s = wave_fn(2 * math.pi * phase) if wave_fn is math.sin else wave_fn(phase)
        out.append(amp * s * math.exp(-decay * t) * _env(i, n, 0.003, 0.1))
    return out


def _noise(seconds: float, decay: float, amp=0.8, lowpass=0.0, seed=1):
    rnd = random.Random(seed)
    n = int(seconds * RATE)
    out, prev = [], 0.0
    for i in range(n):
        x = rnd.uniform(-1, 1)
        if lowpass:
            prev = prev + lowpass * (x - prev)
            x = prev * 2.0
        out.append(amp * x * math.exp(-decay * i / n) * _env(i, n, 0.001, 0.05))
    return out


def _mix(*tracks):
    n = max(len(t) for t in tracks)
    out = [0.0] * n
    for t in tracks:
        for i, v in enumerate(t):
            out[i] += v
    return out


def _note_freq(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _tone(midi, seconds, wave_fn=_tri, amp=0.3, attack=0.01, release=0.5):
    n = int(seconds * RATE)
    f = _note_freq(midi)
    return [amp * wave_fn(i * f / RATE) * _env(i, n, attack, release) for i in range(n)]


def _place(buf, start_sec, samples):
    s = int(start_sec * RATE)
    if s >= len(buf):
        return
    for i, v in enumerate(samples):
        if s + i >= len(buf):
            break
        buf[s + i] += v


def _music(seconds: float, tempo: float, mood: str):
    seconds = max(1.0, min(float(seconds), MAX_SECONDS))
    beat = 60.0 / tempo
    buf = [0.0] * int(seconds * RATE)
    rnd = random.Random({"cheerful": 7, "calm": 3, "sneaky": 11}[mood])
    major = [0, 2, 4, 7, 9, 12, 14]  # pentatonic-ish
    progression = [(60, 0), (57, 2), (53, 4), (55, 5)]  # C, Am, F, G roots (midi), degree offsets for melody
    last_bar_start = max(0.0, seconds - 4 * beat)
    bar = 0
    t = 0.0
    while t < seconds - 0.01:
        root, _ = progression[bar % 4]
        if t >= last_bar_start:  # final held chord
            for off in (0, 4, 7):
                _place(buf, t, _tone(60 + off, min(seconds - t, 4 * beat), _tri, 0.16, 0.02, 0.3))
            _place(buf, t, _tone(48, min(seconds - t, 4 * beat), _sq, 0.08, 0.01, 0.3))
            break
        # bass
        for b in range(4):
            bass = root - 12 + (7 if b % 2 else 0)
            if mood == "sneaky":
                _place(buf, t + b * beat, _tone(bass, beat * 0.25, _tri, 0.22, 0.003, 0.8))
            else:
                _place(buf, t + b * beat, _tone(bass, beat * 0.8, _sq, 0.07 if mood == "cheerful" else 0.05, 0.005, 0.5))
        # chord pad
        if mood != "sneaky":
            for off in (0, 4 if root not in (57,) else 3, 7):
                _place(buf, t, _tone(root + off, 4 * beat, _tri, 0.045, 0.05, 0.4))
        # melody
        pos = 0.0
        while pos < 4 * beat - 0.01:
            step = rnd.choice([0.5, 0.5, 1.0] if mood != "calm" else [1.0, 2.0])
            if rnd.random() < (0.12 if mood != "sneaky" else 0.35):
                pos += step * beat
                continue
            note = root + 12 + rnd.choice(major) % 12 + (12 if rnd.random() < 0.25 else 0)
            length = step * beat * (0.9 if mood != "sneaky" else 0.3)
            _place(buf, t + pos * beat, _tone(note, length, _tri if mood != "sneaky" else math.sin, 0.2, 0.005, 0.6))
            pos += step
        # hi-hat
        if mood == "cheerful":
            for b in range(8):
                _place(buf, t + b * beat / 2, _noise(0.04, 8, 0.07, seed=bar * 8 + b))
        bar += 1
        t += 4 * beat
    return buf


def synth(preset: str, seconds: float | None = None, tempo: float | None = None) -> list[float]:
    if preset == "pop":
        return _mix(_sweep(0.14, 700, 220, decay=4), _noise(0.02, 6, 0.3))
    if preset == "boing":
        return _sweep(0.5, 180, 420, vibrato=(120, 14), decay=3.2, amp=0.65)
    if preset == "bloop":
        return _sweep(0.12, 520, 760, decay=2.5, amp=0.6)
    if preset == "squeak":
        return _sweep(0.18, 900, 1500, vibrato=(60, 30), decay=2, amp=0.35)
    if preset == "alien_warble":
        return _mix(_sweep(0.7, 700, 1000, vibrato=(350, 11), decay=2, amp=0.4), _sweep(0.12, 900, 200, decay=5, amp=0.35))
    if preset == "crack":
        return _mix(_noise(0.18, 14, 0.9, seed=5), _sweep(0.1, 140, 60, decay=6, amp=0.7))
    if preset == "munch":
        return _mix(_noise(0.11, 9, 0.75, lowpass=0.35, seed=2), _sweep(0.06, 200, 120, decay=6, amp=0.3))
    if preset == "whoosh":
        n = int(0.35 * RATE)
        base = _noise(0.35, 0.5, 0.6, lowpass=0.15, seed=9)
        return [v * math.sin(math.pi * i / n) for i, v in enumerate(base)]
    if preset == "chime":
        out = [0.0] * int(1.1 * RATE)
        for k, m in enumerate((72, 76, 79)):
            _place(out, k * 0.17, _tone(m, 0.7, math.sin, 0.33, 0.003, 0.9))
            _place(out, k * 0.17, _tone(m + 12, 0.5, math.sin, 0.08, 0.003, 0.9))
        return out
    if preset == "sad_trombone":
        out = [0.0] * int(1.4 * RATE)
        for k, (m, d) in enumerate([(58, 0.3), (57, 0.3), (56, 0.3), (53, 0.55)]):
            _place(out, sum(x[1] for x in [(58, 0.3), (57, 0.3), (56, 0.3), (53, 0.55)][:k]),
                   _tone(m, d, _sq, 0.18, 0.02, 0.4))
        return out
    if preset.startswith("music_"):
        mood = preset.split("_", 1)[1]
        default_tempo = {"cheerful": 124, "calm": 80, "sneaky": 104}[mood]
        return _music(seconds or 16, tempo or default_tempo, mood)
    raise KeyError(preset)


def to_wav(samples: list[float]) -> bytes:
    peak = max((abs(v) for v in samples), default=0.0)
    gain = 0.89 / peak if peak > 0.89 else 1.0
    pcm = struct.pack("<%dh" % len(samples), *[int(max(-1.0, min(1.0, v * gain)) * 32767) for v in samples])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def render_preset(preset: str, seconds: float | None = None, tempo: float | None = None) -> bytes:
    return to_wav(synth(preset, seconds, tempo))
