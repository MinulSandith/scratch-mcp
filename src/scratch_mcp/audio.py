"""PCM WAV editing in pure Python: trim, cut, reverse, volume, fades, echo, speed, robot, silence.

Scratch loads WAV natively. Samples are handled as 16-bit signed ints per channel.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from array import array
from dataclasses import dataclass

from .editing import EditError


@dataclass
class Pcm:
    rate: int
    channels: int
    data: list[list[int]]  # data[channel][frame]

    @property
    def frames(self) -> int:
        return len(self.data[0]) if self.data else 0

    @property
    def seconds(self) -> float:
        return self.frames / self.rate if self.rate else 0.0

    def copy(self) -> "Pcm":
        return Pcm(self.rate, self.channels, [list(c) for c in self.data])


def decode(wav: bytes) -> Pcm:
    try:
        with wave.open(io.BytesIO(wav)) as w:
            ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError) as exc:
        raise EditError(f"Can't read this WAV: {exc}") from exc
    if width == 1:
        vals = [(b - 128) << 8 for b in raw]
    elif width == 2:
        a = array("h")
        a.frombytes(raw[: n * ch * 2])
        vals = list(a)
    else:
        raise EditError(f"Only 8-bit and 16-bit PCM WAV can be edited (this one is {width * 8}-bit).")
    chans = [vals[c::ch] for c in range(ch)]
    return Pcm(rate, ch, chans)


def encode(p: Pcm) -> bytes:
    frames = p.frames
    inter = [0] * (frames * p.channels)
    for c in range(p.channels):
        inter[c::p.channels] = [max(-32768, min(32767, int(v))) for v in p.data[c]]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(p.channels)
        w.setsampwidth(2)
        w.setframerate(p.rate)
        w.writeframes(struct.pack("<%dh" % len(inter), *inter))
    return buf.getvalue()


def _span(p: Pcm, start: float | None, end: float | None) -> tuple[int, int]:
    a = 0 if start is None else int(round(start * p.rate))
    b = p.frames if end is None else int(round(end * p.rate))
    if a < 0 or b > p.frames or a >= b:
        raise EditError(f"Invalid time range {start}-{end} s (the sound is {p.seconds:.3f} s long).")
    return a, b


def trim(p: Pcm, start: float | None, end: float | None) -> Pcm:
    a, b = _span(p, start, end)
    return Pcm(p.rate, p.channels, [c[a:b] for c in p.data])


def cut(p: Pcm, start: float, end: float) -> tuple[Pcm, Pcm]:
    """(remaining sound, the removed segment)."""
    a, b = _span(p, start, end)
    if b - a >= p.frames:
        raise EditError("That would remove the whole sound.")
    return (Pcm(p.rate, p.channels, [c[:a] + c[b:] for c in p.data]), Pcm(p.rate, p.channels, [c[a:b] for c in p.data]))


def insert(p: Pcm, seg: Pcm, at: float) -> Pcm:
    if seg.channels != p.channels:
        raise EditError("Channel count differs between the sound and the inserted segment.")
    seg = resample(seg, p.rate) if seg.rate != p.rate else seg
    i = int(round(at * p.rate))
    if not 0 <= i <= p.frames:
        raise EditError(f"Insert position {at} s is outside the sound (0-{p.seconds:.3f} s).")
    return Pcm(p.rate, p.channels, [c[:i] + s + c[i:] for c, s in zip(p.data, seg.data)])


def silence(p: Pcm, start: float, end: float) -> Pcm:
    a, b = _span(p, start, end)
    out = p.copy()
    for c in out.data:
        c[a:b] = [0] * (b - a)
    return out


def reverse(p: Pcm, start: float | None = None, end: float | None = None) -> Pcm:
    a, b = _span(p, start, end)
    out = p.copy()
    for c in out.data:
        c[a:b] = c[a:b][::-1]
    return out


def gain(p: Pcm, factor: float, start: float | None = None, end: float | None = None) -> Pcm:
    if factor < 0:
        raise EditError("Volume factor can't be negative.")
    a, b = _span(p, start, end)
    out = p.copy()
    for c in out.data:
        c[a:b] = [max(-32768, min(32767, int(v * factor))) for v in c[a:b]]
    return out


def normalize(p: Pcm, peak: float = 0.95) -> Pcm:
    m = max((abs(v) for c in p.data for v in c), default=0)
    if m == 0:
        raise EditError("The sound is silent; nothing to normalize.")
    return gain(p, peak * 32767 / m)


def fade(p: Pcm, seconds: float, mode: str) -> Pcm:
    n = int(seconds * p.rate)
    if n <= 0 or n > p.frames:
        raise EditError(f"Fade length must be between 0 and {p.seconds:.3f} s.")
    out = p.copy()
    for c in out.data:
        for i in range(n):
            f = i / n
            if mode == "in":
                c[i] = int(c[i] * f)
            else:
                c[p.frames - 1 - i] = int(c[p.frames - 1 - i] * f)
    return out


def echo(p: Pcm, delay: float = 0.25, decay: float = 0.5, repeats: int = 4) -> Pcm:
    d = int(delay * p.rate)
    if d <= 0:
        raise EditError("Echo delay must be positive.")
    out_len = p.frames + d * repeats
    chans = []
    for c in p.data:
        o = [0.0] * out_len
        for i, v in enumerate(c):
            o[i] += v
            for r in range(1, repeats + 1):
                o[i + d * r] += v * decay ** r
        chans.append(o)
    m = max((abs(v) for c in chans for v in c), default=0)
    scale = 32767 / m if m > 32767 else 1.0
    return Pcm(p.rate, p.channels, [[int(v * scale) for v in c] for c in chans])


def resample(p: Pcm, new_rate: int) -> Pcm:
    """Change the sample rate while keeping duration and pitch (linear interpolation)."""
    n = int(p.frames * new_rate / p.rate)
    out = []
    for c in p.data:
        o = []
        for i in range(n):
            pos = i * p.rate / new_rate
            j = int(pos)
            frac = pos - j
            a = c[j] if j < len(c) else 0
            b = c[j + 1] if j + 1 < len(c) else a
            o.append(int(a + (b - a) * frac))
        out.append(o)
    return Pcm(new_rate, p.channels, out)


def speed(p: Pcm, factor: float) -> Pcm:
    """Play faster (>1) or slower (<1); pitch changes too, like Scratch's 'faster'/'slower'."""
    if not 0.1 <= factor <= 8:
        raise EditError("Speed factor must be between 0.1 and 8.")
    n = int(p.frames / factor)
    out = []
    for c in p.data:
        o = []
        for i in range(n):
            pos = i * factor
            j = int(pos)
            frac = pos - j
            a = c[j] if j < len(c) else 0
            b = c[j + 1] if j + 1 < len(c) else a
            o.append(int(a + (b - a) * frac))
        out.append(o)
    return Pcm(p.rate, p.channels, out)


def robot(p: Pcm, freq: float = 50.0) -> Pcm:
    """Ring-modulate with a sine for a robotic voice."""
    out = p.copy()
    for c in out.data:
        for i in range(len(c)):
            c[i] = int(c[i] * math.sin(2 * math.pi * freq * i / p.rate))
    return gain(out, 1.6)


def tone(freq: float, seconds: float, wave_kind: str = "sine", rate: int = 22050, volume: float = 0.6) -> Pcm:
    if not 20 <= freq <= 10000 or not 0.01 <= seconds <= 60:
        raise EditError("freq must be 20-10000 Hz and seconds 0.01-60.")
    n = int(seconds * rate)
    out = []
    for i in range(n):
        ph = (i * freq / rate) % 1.0
        v = {"sine": math.sin(2 * math.pi * ph), "square": 1.0 if ph < 0.5 else -1.0,
             "saw": 2 * ph - 1, "triangle": 4 * abs(ph - 0.5) - 1}.get(wave_kind)
        if v is None:
            raise EditError("wave must be sine, square, saw or triangle.")
        env = min(1.0, i / (0.005 * rate), (n - i) / (0.02 * rate))
        out.append(int(32767 * volume * v * env))
    return Pcm(rate, 1, [out])
