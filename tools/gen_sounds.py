#!/usr/bin/env python3
"""Synthesize the Cryo UI sound sets (ice, glass, deep) with the stdlib only.

    python tools/gen_sounds.py              # write into src/cryo/gui/assets/sounds
    python tools/gen_sounds.py --out DIR    # write somewhere else
    python tools/gen_sounds.py --check      # fail if the committed files are stale

Output is deterministic: every file uses its own fixed-seed RNG and plain
float math, so two runs produce byte-identical WAVs.
"""

from __future__ import annotations

import argparse
import array
import math
import random
import sys
import tempfile
import wave
from pathlib import Path

RATE = 44100
TAU = 2.0 * math.pi
REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "src" / "cryo" / "gui" / "assets" / "sounds"

SETS = ("ice", "glass", "deep")
EVENTS = (
    "tap", "toggle_on", "toggle_off", "mode", "freeze",
    "thaw", "connect", "disconnect", "error",
)

# Buffer length in seconds, kept just under the documented maximum.
LENGTH = {
    "tap": 0.11, "toggle_on": 0.17, "toggle_off": 0.17, "mode": 0.34,
    "freeze": 1.38, "thaw": 1.18, "connect": 0.48, "disconnect": 0.48,
    "error": 0.39,
}
# Target peak in linear full scale (-6 dBFS, or -3 dBFS for the long ones).
PEAK = {"freeze": 10 ** (-3 / 20), "thaw": 10 ** (-3 / 20)}
DEFAULT_PEAK = 10 ** (-6 / 20)


# --------------------------------------------------------------------------
# Primitives. A buffer is a plain list of floats at RATE.
# --------------------------------------------------------------------------

def new_buf(seconds: float) -> list[float]:
    return [0.0] * int(seconds * RATE)


def add_modal(buf, t, freq, amp, decay, ratios, amps, *, spread=0.6, attack=0.0015):
    """Sum of decaying sine partials; higher partials die faster."""
    start = int(t * RATE)
    for i, (ratio, a) in enumerate(zip(ratios, amps)):
        f = freq * ratio
        if f >= RATE / 2.2:
            continue
        tau = decay / (1.0 + spread * i)
        n = min(len(buf) - start, int(tau * 7 * RATE))
        w = TAU * f / RATE
        for k in range(max(n, 0)):
            x = k / RATE
            env = math.exp(-x / tau) * min(1.0, x / attack)
            buf[start + k] += amp * a * env * math.sin(w * k)


def add_thump(buf, t, freq, amp, decay, *, glide=1.08, glide_tau=0.03, attack=0.004):
    """Soft low sine with a slight downward pitch settle and a faint 2nd harmonic."""
    start = int(t * RATE)
    n = min(len(buf) - start, int(decay * 7 * RATE))
    phase = 0.0
    for k in range(max(n, 0)):
        x = k / RATE
        f = freq * (1.0 + (glide - 1.0) * math.exp(-x / glide_tau))
        phase += TAU * f / RATE
        env = math.exp(-x / decay) * min(1.0, x / attack)
        buf[start + k] += amp * env * (math.sin(phase) + 0.12 * math.sin(2 * phase))


def add_noise(buf, t, dur, amp, rng, *, decay=None, lp=None, hp=None, attack=0.001):
    """Filtered noise burst (one-pole low-pass and/or high-pass)."""
    start = int(t * RATE)
    n = min(len(buf) - start, int(dur * RATE))
    a_lp = 1.0 - math.exp(-TAU * lp / RATE) if lp else 1.0
    a_hp = 1.0 - math.exp(-TAU * hp / RATE) if hp else 0.0
    y = z = 0.0
    for k in range(max(n, 0)):
        x = k / RATE
        s = rng.uniform(-1.0, 1.0)
        y += a_lp * (s - y)
        v = y
        if hp:
            z += a_hp * (v - z)
            v -= z
        env = (math.exp(-x / decay) if decay else 1.0) * min(1.0, x / attack)
        buf[start + k] += amp * env * v


def add_swell(buf, t, dur, amp, freqs, peak_at, *, trem_hz=0.0, trem_depth=0.0):
    """Sine stack under a slow rise and fall envelope."""
    start = int(t * RATE)
    n = min(len(buf) - start, int(dur * RATE))
    for j, f in enumerate(freqs):
        w = TAU * f / RATE
        ph = 0.7 * j
        for k in range(max(n, 0)):
            x = k / RATE / dur
            if x < peak_at:
                env = (x / peak_at) ** 2
            else:
                env = math.cos(0.5 * math.pi * (x - peak_at) / (1.0 - peak_at)) ** 2
            tr = 1.0 - trem_depth + trem_depth * math.sin(TAU * trem_hz * k / RATE + j)
            buf[start + k] += amp * env * tr * math.sin(w * k + ph) / len(freqs)


# --------------------------------------------------------------------------
# Voices: one timbre per set.
# --------------------------------------------------------------------------

class Ice:
    base = 2700.0
    ratios = (1.0, 2.76, 5.40, 8.93)
    amps = (1.0, 0.6, 0.35, 0.2)
    decay = 0.035

    def hit(self, buf, t, f, amp, rng, d=1.0):
        add_modal(buf, t, f, amp, self.decay * d, self.ratios, self.amps)
        add_noise(buf, t, 0.008, amp * 0.18, rng, decay=0.002, hp=4500)

    def chime(self, buf, t, f, amp, rng, d=1.0):
        # Soft settled chime: harmonic and warmer than the ticks.
        add_modal(buf, t, f, amp, 0.22 * d, (1.0, 2.0, 3.0), (1.0, 0.25, 0.08),
                  attack=0.004)

    def knock(self, buf, t, amp, rng):
        add_modal(buf, t, 520.0, amp, 0.035, (1.0, 2.76), (1.0, 0.35), attack=0.003)
        add_noise(buf, t, 0.03, amp * 0.25, rng, decay=0.01, lp=1200)


class Glass:
    base = 1100.0
    ratios = (1.0, 1.003, 2.0, 3.0, 4.0)
    amps = (1.0, 0.45, 0.28, 0.10, 0.04)
    decay = 0.16

    def hit(self, buf, t, f, amp, rng, d=1.0):
        add_modal(buf, t, f, amp, self.decay * d, self.ratios, self.amps,
                  spread=0.35, attack=0.003)

    def chime(self, buf, t, f, amp, rng, d=1.0):
        add_modal(buf, t, f, amp, 0.3 * d, (1.0, 1.003, 2.0, 3.0), (1.0, 0.4, 0.2, 0.06),
                  spread=0.3, attack=0.005)

    def knock(self, buf, t, amp, rng):
        add_modal(buf, t, 330.0, amp, 0.07, (1.0, 2.0), (1.0, 0.2), attack=0.004)


class Deep:
    base = 100.0
    decay = 0.09

    def hit(self, buf, t, f, amp, rng, d=1.0):
        add_thump(buf, t, f, amp, self.decay * d)
        add_noise(buf, t, 0.08, amp * 0.22, rng, decay=0.03, lp=380, attack=0.004)

    def chime(self, buf, t, f, amp, rng, d=1.0):
        add_thump(buf, t, f, amp, 0.25 * d, glide=1.0, attack=0.02)
        add_thump(buf, t, f * 1.5, amp * 0.5, 0.2 * d, glide=1.0, attack=0.02)

    def knock(self, buf, t, amp, rng):
        add_thump(buf, t, 75.0, amp, 0.05, glide=1.1)
        add_noise(buf, t, 0.05, amp * 0.2, rng, decay=0.015, lp=300, attack=0.003)


VOICES = {"ice": Ice(), "glass": Glass(), "deep": Deep()}


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------

def _notes(v, buf, rng, notes, base, amp=1.0, d=1.0):
    for t, mult, a in notes:
        v.hit(buf, t, base * mult, amp * a, rng, d)


def _freeze(name, v, buf, rng):
    if name == "ice":
        # Rising swarm of crackles.
        for _ in range(46):
            t = 0.88 * math.sqrt(rng.random())
            f = rng.uniform(3000.0, 7500.0)
            a = (0.12 + 0.4 * rng.random()) * (0.4 + t)
            add_modal(buf, t, f, a, 0.012, (1.0, 2.76), (1.0, 0.4))
            add_noise(buf, t, 0.006, a * 0.5, rng, decay=0.002, hp=5000)
        # Shimmer swell.
        add_swell(buf, 0.0, 1.38, 0.5, (4010.0, 5383.0, 6200.0, 7110.0, 9330.0),
                  0.62, trem_hz=9.0, trem_depth=0.3)
        v.chime(buf, 0.88, 2093.0, 0.7, rng)
        v.chime(buf, 0.93, 3136.0, 0.3, rng, 0.8)
    elif name == "glass":
        for i in range(9):
            t = 0.1 + 0.8 * (i / 9.0) ** 0.8
            v.hit(buf, t, rng.choice((2093.0, 2637.0, 3136.0)), 0.12 + 0.05 * i, rng, 0.4)
        add_swell(buf, 0.0, 1.38, 0.55, (1046.5, 1568.0, 2093.0, 1048.0, 1570.0),
                  0.62, trem_hz=5.0, trem_depth=0.15)
        v.chime(buf, 0.86, 1568.0, 0.7, rng, 1.6)
        v.chime(buf, 0.92, 2093.0, 0.5, rng, 1.6)
    else:
        add_noise(buf, 0.0, 1.0, 0.35, rng, lp=420, attack=0.2)
        # Rising low drone, then a settling thump.
        phase = 0.0
        for k in range(int(1.2 * RATE)):
            x = k / RATE
            f = 62.0 + 40.0 * min(x / 0.95, 1.0)
            phase += TAU * f / RATE
            env = (x / 0.95) ** 2 if x < 0.95 else math.exp(-(x - 0.95) / 0.12)
            buf[k] += 0.6 * env * math.sin(phase)
        add_thump(buf, 0.95, 82.0, 0.9, 0.16, glide=1.06)
        v.chime(buf, 1.02, 110.0, 0.35, rng, 0.9)


def _thaw(name, v, buf, rng):
    if name == "ice":
        freqs = (3400.0, 3000.0, 2600.0, 2150.0)
    elif name == "glass":
        freqs = (1760.0, 1568.0, 1318.5, 1175.0)
    else:
        freqs = (200.0, 170.0, 145.0, 120.0)
    times = (0.0, 0.17, 0.37, 0.62)
    for i, (t, f) in enumerate(zip(times, freqs)):
        v.hit(buf, t, f, 0.6 - 0.1 * i, rng, 1.4)
    chime_f = {"ice": 880.0, "glass": 784.0, "deep": 110.0}[name]
    v.chime(buf, 0.78, chime_f, 0.8, rng, 1.6)
    v.chime(buf, 0.86, chime_f * 1.5, 0.45, rng, 1.6)


def render(set_name: str, event: str) -> list[float]:
    """Raw (un-normalized) float samples for one sound."""
    v = VOICES[set_name]
    rng = random.Random(f"cryo-sound/{set_name}/{event}")
    buf = new_buf(LENGTH[event])
    b = v.base
    if event == "tap":
        v.hit(buf, 0.0, b * (1.15 if set_name == "ice" else 1.0), 1.0, rng)
    elif event == "toggle_on":
        _notes(v, buf, rng, [(0.0, 1.0, 0.8), (0.065, 1.5, 1.0)], b)
    elif event == "toggle_off":
        _notes(v, buf, rng, [(0.0, 1.5, 0.8), (0.065, 1.0, 1.0)], b * 0.9)
    elif event == "mode":
        _notes(v, buf, rng, [(0.0, 1.0, 0.7), (0.09, 1.25, 0.85), (0.18, 1.5, 1.0)], b, d=1.2)
    elif event == "connect":
        _notes(v, buf, rng, [(0.0, 1.0, 0.7), (0.12, 1.5, 0.85), (0.24, 2.0, 1.0)], b, d=1.3)
    elif event == "disconnect":
        _notes(v, buf, rng, [(0.0, 2.0, 0.7), (0.12, 1.5, 0.85), (0.24, 1.0, 1.0)], b * 0.9, d=1.3)
    elif event == "error":
        v.knock(buf, 0.0, 1.0, rng)
        v.knock(buf, 0.15, 0.8, rng)
    elif event == "freeze":
        _freeze(set_name, v, buf, rng)
    elif event == "thaw":
        _thaw(set_name, v, buf, rng)
    else:
        raise KeyError(event)
    return buf


def finish(buf: list[float], event: str) -> bytes:
    """Remove DC, fade in/out, normalize, quantize to 16-bit little endian."""
    n = len(buf)
    mean = sum(buf) / n
    out = [s - mean for s in buf]
    fade_in = int(0.005 * RATE)
    fade_out = int(min(0.18 if n > RATE else 0.03, 0.3 * n / RATE) * RATE)
    for k in range(min(fade_in, n)):
        out[k] *= (k / fade_in) ** 2
    for k in range(min(fade_out, n)):
        g = math.sin(0.5 * math.pi * k / fade_out) ** 2
        out[n - 1 - k] *= g
    out[-1] = 0.0
    peak = max(abs(s) for s in out) or 1.0
    scale = PEAK.get(event, DEFAULT_PEAK) * 32767.0 / peak
    pcm = array.array("h", (int(round(s * scale)) for s in out))
    if sys.byteorder == "big":
        pcm.byteswap()
    return pcm.tobytes()


def write_wav(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data)


def generate(out: Path) -> list[Path]:
    paths = []
    for s in SETS:
        for e in EVENTS:
            p = out / s / f"{e}.wav"
            write_wav(p, finish(render(s, e), e))
            paths.append(p)
    return paths


def check(out: Path) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        bad = 0
        for p in generate(fresh):
            rel = p.relative_to(fresh)
            committed = out / rel
            if not committed.is_file():
                print(f"missing: {rel}")
                bad += 1
            elif committed.read_bytes() != p.read_bytes():
                print(f"stale:   {rel}")
                bad += 1
    print("sounds up to date" if not bad else f"{bad} file(s) need regenerating")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if committed files differ from a fresh render")
    args = ap.parse_args(argv)
    if args.check:
        return check(args.out)
    paths = generate(args.out)
    print(f"wrote {len(paths)} files to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
