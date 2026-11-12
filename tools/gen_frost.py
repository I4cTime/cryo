#!/usr/bin/env python3
"""Generate the frost growth map used by src/cryo/gui/fx/FrostOverlay.qml.

Offline art tool, not a runtime dependency. Run it with:

    uv run --with numpy --with pillow --with scipy python tools/gen_frost.py

It writes two committed files:

- src/cryo/gui/fx/frost_growth.png (RGB)
    R = freeze order (0 freezes first at the edges and corners, 1 last at
        the window centre), following a dendritic front
    G = crystal detail (fern spines, feather veins, grains)
    B = sparse sparkle specks
- src/cryo/gui/fx/frost_static.png (RGBA, straight alpha): the frost as
  frost.frag draws it at amount 0.4 over nothing, for the software renderer
  fallback.

How the art is made: frost ferns are grown as a time-ordered simulation.
Nucleation seeds sit along the edges (denser, earlier and longer from the
corners); each grows a stem that throws side branches at about 60 degrees,
which throw short feathers of their own, and every branch stops when it runs
into ice that is already there. Every stroke sample carries the time it
crystallised. The freeze order of an empty pixel is then the earliest time
the ice could spread to it from any stroke (a slower fill), so the frozen
area at any threshold is a set of feathered ferns rather than a smooth band.
Finally the order is remapped through its histogram so the coverage per
`amount` hits fixed targets (outer band only at idle, whole pane at 1.0).
"""

from __future__ import annotations

import argparse
import heapq
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
FX_DIR = ROOT / "src" / "cryo" / "gui" / "fx"

DEG = math.pi / 180.0

# Fraction of the window that is frozen at a given amount (before feather).
COVERAGE_AMOUNT = [0.0, 0.05, 0.15, 0.30, 0.45, 0.60, 0.75, 0.90, 1.0]
COVERAGE_TARGET = [0.0, 0.012, 0.05, 0.13, 0.24, 0.40, 0.60, 0.85, 1.0]

# Stroke classes: half-width in map pixels, brightness.
LEVEL_HALF_WIDTH = [1.05, 0.70, 0.45]
LEVEL_BRIGHT = [1.0, 0.78, 0.58]
LEVEL_SPEED = [1.0, 0.75, 0.55]

STEP = 1.5  # growth step in map pixels
FILL_SPEED = 0.22  # how fast ice spreads sideways from a stroke (px per time)
EDGE_FILL_SPEED = 0.16  # background creep from the frame (px per time)


class Grower:
    """Event-driven growth of all fern branches, earliest tip first."""

    def __init__(self, w: int, h: int, rng: np.random.Generator, cell: int = 3):
        self.w, self.h = w, h
        self.rng = rng
        self.cell = cell
        self.owner = np.full((h // cell + 2, w // cell + 2), -1, np.int32)
        self.heap: list[tuple[float, int, int]] = []
        self.br: list[list] = []
        self.counter = 0
        # Recorded segments: x0, y0, x1, y1, t0, t1, level, taper0, taper1
        self.segs: list[tuple] = []

    def add(self, x, y, ang, t, length, level, parent=-1, grace=2):
        bid = len(self.br)
        rng = self.rng
        spacing = [rng.uniform(5.0, 8.0), rng.uniform(2.6, 4.0), 0.0][level]
        state = [
            x,
            y,
            ang,
            t,
            length,
            length,
            level,
            parent,
            0.0,  # traveled
            spacing * rng.uniform(0.5, 1.0),  # next branch at
            1 if rng.random() < 0.5 else -1,  # side for alternate branching
            0,  # steps
            spacing,
            rng.random() < (0.75 if level == 0 else 0.5),  # paired branching
            rng.normal(0.0, [0.0025, 0.006, 0.0][level]),  # steady sweep per px
            grace,  # steps that may cross older ice (to escape the frame lace)
        ]
        self.br.append(state)
        heapq.heappush(self.heap, (t, self.counter, bid))
        self.counter += 1
        return bid

    def run(self):
        rng = self.rng
        owner = self.owner
        cell = self.cell
        curl = [0.02, 0.035, 0.06]
        while self.heap:
            t, _, bid = heapq.heappop(self.heap)
            s = self.br[bid]
            x, y, ang, _, rem, length, level, parent = s[:8]
            if rem <= 0:
                continue
            nx = x + math.cos(ang) * STEP
            ny = y + math.sin(ang) * STEP
            if nx < -1 or ny < -1 or nx > self.w + 1 or ny > self.h + 1:
                continue
            cx = min(max(int(nx / cell), 0), owner.shape[1] - 1)
            cy = min(max(int(ny / cell), 0), owner.shape[0] - 1)
            o = owner[cy, cx]
            if o != -1 and o != bid and o != parent and s[11] > s[15]:
                continue  # ran into older ice
            if o == -1:
                owner[cy, cx] = bid
            nt = t + STEP / LEVEL_SPEED[level]
            frac0 = 1.0 - (length - rem) / length
            rem -= STEP
            frac1 = max(rem, 0.0) / length
            self.segs.append((x, y, nx, ny, t, nt, level, frac0, frac1))
            s[0], s[1], s[3], s[4] = nx, ny, nt, rem
            s[8] += STEP
            s[11] += 1
            s[2] = ang + s[14] * STEP + rng.normal(0.0, curl[level])
            if level < 2 and s[8] >= s[9] and rem > 4:
                self._branch(s, bid, nx, ny, ang, nt, rem, length, level)
            if rem > 0:
                heapq.heappush(self.heap, (nt, self.counter, bid))
                self.counter += 1

    def _branch(self, s, bid, x, y, ang, t, rem, length, level):
        rng = self.rng
        s[9] = s[8] + s[12] * rng.uniform(0.75, 1.3)
        sides = (1, -1) if s[13] else (s[10],)
        s[10] = -s[10]
        # Fern taper: long side branches near the base, short near the tip.
        base = rem * (0.35 if level == 0 else 0.45) + (5.0 if level == 0 else 2.0)
        for side in sides:
            child_len = base * rng.uniform(0.45, 1.0)
            if level == 0 and rng.random() < 0.06 and rem > 80:
                # a side plume that is a fern in its own right
                a = ang + side * rng.normal(55.0, 8.0) * DEG
                self.add(x, y, a, t + 1.0, rem * rng.uniform(0.35, 0.6), 0, bid)
                continue
            if level == 0:
                child_len = min(child_len, 64.0)
            else:
                child_len = min(child_len, 13.0)
            if child_len < 3.0:
                continue
            a = ang + side * rng.normal(60.0, 5.0) * DEG
            self.add(x, y, a, t + rng.uniform(0.0, 2.0), child_len, level + 1, bid)


def edge_seeds(g: Grower, w: int, h: int, rng: np.random.Generator):
    corners = [
        (0.0, 0.0, 0.0),  # x, y, angle of the edge running away from it
        (w, 0.0, 90.0),
        (w, h, 180.0),
        (0.0, h, 270.0),
    ]
    diag = math.hypot(w, h)
    # Corners: a fan of long early stems.
    for cx, cy, a0 in corners:
        n = rng.integers(5, 8)
        fan = np.sort(rng.uniform(10.0, 80.0, n))
        for k, off in enumerate(fan):
            ang = (a0 + off) * DEG
            along = rng.uniform(0.0, 40.0)
            edge_ang = a0 * DEG if rng.random() < 0.5 else (a0 + 90.0) * DEG
            x = cx + math.cos(edge_ang) * along
            y = cy + math.sin(edge_ang) * along
            length = rng.uniform(0.22, 0.38) * diag
            g.add(x, y, ang, rng.uniform(0.0, 18.0) + along * 0.4, length, 0, grace=30)

    # Edges: seeds get sparser, later and shorter towards the middle.
    edges = [
        ((0.0, 0.0), (w, 0.0), 90.0),
        ((w, 0.0), (w, h), 180.0),
        ((w, h), (0.0, h), 270.0),
        ((0.0, h), (0.0, 0.0), 0.0),
    ]
    for (x0, y0), (x1, y1), inward in edges:
        elen = math.hypot(x1 - x0, y1 - y0)
        u = rng.uniform(30.0, 60.0)
        while u < elen - 30.0:
            dc = min(u, elen - u)  # distance to the nearest corner
            centre = min(dc / (0.5 * min(w, h) * 1.6), 1.0)
            fx = u / elen
            x = x0 + (x1 - x0) * fx
            y = y0 + (y1 - y0) * fx
            ang = (inward + rng.normal(0.0, 22.0)) * DEG
            length = (0.30 - 0.14 * centre) * diag * rng.uniform(0.55, 1.15)
            t0 = 14.0 + dc * rng.uniform(0.30, 0.6)
            g.add(x, y, ang, t0, length, 0, grace=24)
            u += rng.uniform(34.0, 60.0) + 40.0 * centre

        # Frame lace: short early ferns hugging every edge, so the idle band
        # is continuous instead of four corner patches.
        u = rng.uniform(8.0, 20.0)
        while u < elen - 8.0:
            dc = min(u, elen - u)
            fx = u / elen
            x = x0 + (x1 - x0) * fx
            y = y0 + (y1 - y0) * fx
            ang = (inward + rng.choice([-1.0, 1.0]) * rng.uniform(15.0, 70.0)) * DEG
            t0 = 18.0 + dc * rng.uniform(0.10, 0.22)
            g.add(x, y, ang, t0, rng.uniform(22.0, 60.0), 0)
            u += rng.uniform(16.0, 34.0)


def interior_seeds(g: Grower, t_prov: np.ndarray, rng: np.random.Generator, count: int):
    """Late nucleation ahead of the front so the full pane is fern, not haze."""
    h, w = t_prov.shape
    placed = 0
    tries = 0
    while placed < count and tries < count * 40:
        tries += 1
        x = rng.uniform(20, w - 20)
        y = rng.uniform(20, h - 20)
        cy, cx = int(y // g.cell), int(x // g.cell)
        if g.owner[max(cy - 2, 0) : cy + 3, max(cx - 2, 0) : cx + 3].max() != -1:
            continue
        t0 = float(t_prov[int(y), int(x)]) * rng.uniform(0.7, 0.9)
        length = rng.uniform(70.0, 170.0)
        ang = rng.uniform(0, 2 * math.pi)
        g.add(x, y, ang, t0, length, 0)
        # a second arm the other way: frost stars often grow both directions
        if rng.random() < 0.6:
            g.add(
                x,
                y,
                ang + math.pi + rng.normal(0, 0.3),
                t0 + 1.0,
                length * rng.uniform(0.5, 0.9),
                0,
            )
        placed += 1


def densify(segs: np.ndarray, scale: float, spacing: float):
    """Turn segments into dense points (in a grid of `scale` x map pixels)."""
    x0, y0, x1, y1, t0, t1, lev, f0, f1 = (segs[:, i] for i in range(9))
    seglen = np.hypot(x1 - x0, y1 - y0) * scale
    n = np.maximum(np.ceil(seglen / spacing).astype(int), 1)
    idx = np.repeat(np.arange(len(segs)), n)
    start = np.repeat(np.cumsum(n) - n, n)
    k = np.arange(idx.size) - start
    u = (k + 0.5) / n[idx]
    px = (x0[idx] + (x1[idx] - x0[idx]) * u) * scale
    py = (y0[idx] + (y1[idx] - y0[idx]) * u) * scale
    pt = t0[idx] + (t1[idx] - t0[idx]) * u
    pf = f0[idx] + (f1[idx] - f0[idx]) * u
    return px, py, pt, lev[idx].astype(int), pf


def render_detail(segs: np.ndarray, w: int, h: int, ss: int) -> np.ndarray:
    """Antialiased stroke brightness at map resolution (rendered at ss x)."""
    W, H = w * ss, h * ss
    out = np.zeros((H, W), np.float32)
    px, py, _, lev, frac = densify(segs, ss, 0.45)
    for level in range(3):
        m = lev == level
        if not m.any():
            continue
        ix = np.clip(np.round(px[m] - 0.5).astype(int), 0, W - 1)
        iy = np.clip(np.round(py[m] - 0.5).astype(int), 0, H - 1)
        taper = 0.35 + 0.65 * np.clip(frac[m], 0, 1)
        hw = np.zeros((H, W), np.float32)
        np.maximum.at(
            hw, (iy, ix), (LEVEL_HALF_WIDTH[level] * ss * taper).astype(np.float32)
        )
        mask = hw > 0
        dist, (ny, nx) = ndimage.distance_transform_edt(~mask, return_indices=True)
        r = hw[ny, nx]
        core = np.clip(r - dist + 0.5, 0.0, 1.0)
        # Thin luminous falloff so lines read as ice, not as ink.
        halo = np.exp(-np.maximum(dist - r, 0.0) / (1.0 * ss)) * 0.14
        val = np.maximum(core, halo) * LEVEL_BRIGHT[level]
        out = np.maximum(out, val.astype(np.float32))
    # Box downsample to map resolution.
    out = out.reshape(h, ss, w, ss).mean(axis=(1, 3))
    return out


def grain_layer(w, h, rng, density_map: np.ndarray, count: int) -> np.ndarray:
    """Tiny six-armed hoarfrost grains, stamped where ice is old and thick."""
    ss = 2
    img = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(img)
    flat = density_map.ravel() / density_map.sum()
    picks = rng.choice(flat.size, size=count, p=flat)
    for p in picks:
        y, x = divmod(int(p), w)
        x += rng.uniform(-0.5, 0.5)
        y += rng.uniform(-0.5, 0.5)
        rot = rng.uniform(0, math.pi / 3)
        arm = rng.uniform(1.5, 4.5) * ss
        val = int(rng.uniform(70, 150))
        for k in range(6 if rng.random() < 0.5 else 3):
            a = rot + k * math.pi / 3
            if k >= 3 or rng.random() < 0.85:
                d.line(
                    [
                        (x * ss, y * ss),
                        (x * ss + math.cos(a) * arm, y * ss + math.sin(a) * arm),
                    ],
                    fill=val,
                    width=1,
                )
    arr = np.asarray(img, np.float32) / 255.0
    return arr.reshape(h, ss, w, ss).mean(axis=(1, 3)) * 1.6


def time_field(segs: np.ndarray, w: int, h: int, bins: int = 40) -> np.ndarray:
    """Earliest time ice reaches each pixel: min over strokes of t + d / FILL_SPEED."""
    px, py, pt, _, _ = densify(segs, 1.0, 0.7)
    ix = np.clip(px.astype(int), 0, w - 1)
    iy = np.clip(py.astype(int), 0, h - 1)
    tmin = np.full((h, w), np.inf, np.float32)
    np.minimum.at(tmin, (iy, ix), pt.astype(np.float32))
    finite = np.isfinite(tmin)
    edges = np.quantile(tmin[finite], np.linspace(0, 1, bins + 1))
    best = np.full((h, w), np.inf, np.float32)
    for k in range(bins):
        lo, hi = edges[k], edges[k + 1]
        m = finite & (tmin >= lo) & ((tmin < hi) if k < bins - 1 else (tmin <= hi))
        if not m.any():
            continue
        dist, (ny, nx) = ndimage.distance_transform_edt(~m, return_indices=True)
        cand = tmin[ny, nx] + dist / FILL_SPEED
        np.minimum(best, cand, out=best)
    return best


def frame_prior(w: int, h: int) -> np.ndarray:
    """Rough edge-first arrival time; only used to time interior nucleation."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = np.minimum(xx, w - 1 - xx)
    dy = np.minimum(yy, h - 1 - yy)
    d_edge = np.minimum(dx, dy)
    # Soft-min towards corners: a corner pixel is close to two edges.
    corner = np.sqrt(dx * dx + dy * dy)
    d = np.minimum(d_edge, corner * 0.8 + d_edge * 0.2)
    return 60.0 + d / EDGE_FILL_SPEED


def remap_coverage(t: np.ndarray) -> np.ndarray:
    """Histogram-remap freeze times so coverage per amount follows COVERAGE_*."""
    flat = t.ravel()
    order = np.argsort(flat, kind="stable")
    cdf = np.empty(flat.size, np.float64)
    cdf[order] = (np.arange(flat.size) + 0.5) / flat.size
    r = np.interp(cdf, COVERAGE_TARGET, COVERAGE_AMOUNT)
    return r.reshape(t.shape).astype(np.float32)


def sparkle_layer(segs: np.ndarray, w: int, h: int, rng, count: int) -> np.ndarray:
    px, py, _, lev, frac = densify(segs, 1.0, 1.5)
    keep = lev < 2
    px, py, frac = px[keep], py[keep], frac[keep]
    weight = 0.3 + (1.0 - np.clip(frac, 0, 1))  # tips glint more
    weight /= weight.sum()
    pick = rng.choice(px.size, size=count, p=weight, replace=False)
    acc = np.zeros((h, w), np.float32)
    yy, xx = np.mgrid[-3:4, -3:4]
    for i in pick:
        cx, cy = px[i], py[i]
        val = rng.uniform(0.45, 1.0)
        sig = rng.uniform(0.55, 0.95)
        x0, y0 = int(cx), int(cy)
        gx = xx + x0
        gy = yy + y0
        ok = (gx >= 0) & (gx < w) & (gy >= 0) & (gy < h)
        dd = ((gx + 0.5 - cx) ** 2 + (gy + 0.5 - cy) ** 2) / (2 * sig * sig)
        # four-point star: gaussian core plus faint cross
        cross = np.exp(
            -(np.minimum(np.abs(gx + 0.5 - cx), np.abs(gy + 0.5 - cy)) ** 2) / 0.18
        )
        cross *= np.exp(-np.sqrt(dd * 2 * sig * sig) / 2.2) * 0.45
        v = (np.exp(-dd) + cross) * val
        np.maximum.at(acc, (gy[ok], gx[ok]), v[ok].astype(np.float32))
    return np.clip(acc, 0, 1)


# --- Shader emulation (keep in sync with src/cryo/gui/fx/frost.frag) -------


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


CRYSTAL_LEAD = 0.02  # crystal lines freeze a hair before the ice around them

DEFAULTS = {
    "intensity": 0.9,
    "feather": 0.025,
    "rimWidth": 0.03,
    "rimStrength": 0.9,
    "shadeStrength": 0.0,
    "tint": (0xBF / 255, 0xEF / 255, 0xFF / 255, 1.0),
    "rimColor": (1.0, 1.0, 1.0, 1.0),
    "shade": (0x4A / 255, 0x64 / 255, 0x78 / 255, 1.0),
}


def shade_frame(growth: np.ndarray, amount: float, p: dict | None = None) -> np.ndarray:
    """Premultiplied RGBA float frame, same maths as frost.frag."""
    q = dict(DEFAULTS)
    q.update(p or {})
    r, g, b = growth[..., 0], growth[..., 1], growth[..., 2]
    f = max(q["feather"], 0.001)
    a = amount * (1.0 + f)
    d = a - (r - g * CRYSTAL_LEAD)
    frozen = smoothstep(0.0, f, d)
    age = smoothstep(0.0, 0.45, d)
    body = frozen * (0.015 + 0.15 * age)
    cryst = frozen * g * (0.72 + 0.28 * age)
    alpha = np.clip(body + cryst - body * cryst, 0, 1) * q["intensity"]
    hl = np.clip(g * g * 0.9 + 0.08, 0, 1)
    tint = np.array(q["tint"][:3])
    sh = np.array(q["shade"])
    ink = min(max(q["shadeStrength"], 0.0), 1.0)
    col = tint * (1 - hl[..., None]) + hl[..., None]
    col = col * (1 - ink * 0.8) + sh[:3] * ink * 0.8
    out = np.concatenate([col * alpha[..., None], alpha[..., None]], axis=-1)
    rw = max(q["rimWidth"], 0.001)
    rim = (
        smoothstep(-f, 0.0, d)
        * (1.0 - smoothstep(0.0, rw, d))
        * (0.06 + 0.94 * g)
        * q["rimStrength"]
    )
    rc = np.array(q["rimColor"]) * (1 - ink * 0.6) + sh * ink * 0.6
    out = out + rc[None, None, :] * rim[..., None] * 0.9
    sp = frozen * b * b
    out = out + sp[..., None] * 0.95
    out = np.clip(out, 0, 1)
    sa = np.clip(frozen * q["shadeStrength"] * (0.10 + 0.18 * age), 0, 1)
    under = sh[None, None, :] * sa[..., None]
    out = out + under * (1.0 - out[..., 3:4])
    return np.clip(out, 0, 1)


def generate(seed: int, w: int, h: int):
    rng = np.random.default_rng(seed)
    g = Grower(w, h, rng)
    edge_seeds(g, w, h, rng)
    g.run()
    segs1 = np.array(g.segs, np.float64)
    t1 = np.minimum(time_field(segs1, w, h, bins=24), frame_prior(w, h))
    interior_seeds(g, t1, rng, count=int(w * h / 9000))
    g.run()
    segs = np.array(g.segs, np.float64)
    print(f"segments: {len(segs)}")

    # The frame prior only steers interior nucleation; in the final order it
    # would draw straight bands parallel to the edges.
    t = time_field(segs, w, h)
    r = remap_coverage(t)

    detail = render_detail(segs, w, h, 2)
    age = np.clip(1.0 - r / 0.75, 0.0, 1.0) ** 1.5
    grains = grain_layer(
        w,
        h,
        rng,
        age * (1.0 - np.clip(detail * 2, 0, 1)) + 1e-6,
        count=int(w * h / 160),
    )
    detail = np.clip(np.maximum(detail, grains * 0.55), 0.0, 1.0)

    sparkle = sparkle_layer(segs, w, h, rng, count=int(w * h / 2600))

    return r, detail, sparkle


def to_u8(x: np.ndarray, rng, dither: bool) -> np.ndarray:
    v = x * 255.0
    if dither:
        v = v + rng.uniform(-0.5, 0.5, x.shape)
    return np.clip(np.round(v), 0, 255).astype(np.uint8)


def _squeeze(path: Path) -> None:
    """Lossless recompression with oxipng when it is installed (optional)."""
    exe = shutil.which("oxipng") or str(Path.home() / ".cargo" / "bin" / "oxipng")
    if Path(exe).exists():
        subprocess.run(
            [exe, "-o", "4", "--strip", "safe", "-q", str(path)], check=False
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--width", type=int, default=768)
    ap.add_argument("--height", type=int, default=1376)
    ap.add_argument("--static-amount", type=float, default=0.4)
    ap.add_argument("--out", type=Path, default=FX_DIR)
    args = ap.parse_args()

    r, gch, bch = generate(args.seed, args.width, args.height)
    rng = np.random.default_rng(args.seed + 1)
    # Size budget: R is softened slightly (the shader's crystal lead puts the
    # fine dendritic edge back from G), G drops its faintest halo and keeps
    # 16 levels. Lines at 16 levels are indistinguishable at display scale.
    r_soft = ndimage.gaussian_filter(r, 1.5)
    g_cut = np.where(gch < 0.12, 0.0, gch)
    g4 = (np.round(g_cut * 15.0) * 17.0).astype(np.uint8)
    rgb = np.stack([to_u8(r_soft, rng, False), g4, to_u8(bch, rng, False)], axis=-1)
    args.out.mkdir(parents=True, exist_ok=True)
    growth_path = args.out / "frost_growth.png"
    Image.fromarray(rgb, "RGB").save(growth_path, optimize=True)
    _squeeze(growth_path)

    growth = rgb.astype(np.float32) / 255.0
    pm = shade_frame(growth, args.static_amount)
    alpha = pm[..., 3:4]
    straight = np.where(alpha > 1e-4, pm[..., :3] / np.maximum(alpha, 1e-4), 0.0)
    rgba = np.concatenate([straight, alpha], axis=-1)
    static = Image.fromarray(
        np.clip(np.round(rgba * 255), 0, 255).astype(np.uint8), "RGBA"
    )
    static = static.resize(
        (args.width * 5 // 8, args.height * 5 // 8), Image.Resampling.LANCZOS
    )
    static_path = args.out / "frost_static.png"
    static.save(static_path, optimize=True)
    _squeeze(static_path)
    for p in (growth_path, static_path):
        print(
            f"{p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}: {p.stat().st_size // 1024} KB"
        )


if __name__ == "__main__":
    main()
