#!/usr/bin/env python3
"""Screenshot tour of the real Cryo GUI against the scripted demo daemon.

    tools/tour.py OUTDIR [--only scene,...] [--software] [--width 480 --height 860]
                         [--perf SECONDS] [--list]

Loads src/cryo/gui/qml/Main.qml through cryo.gui.main.build_engine with a
DemoDaemon whose timeline is paused, so every frame the window sees is fed
explicitly and every shot is deterministic. Per scene it writes
OUTDIR/<scene>.png and OUTDIR/<scene>.masks.json (window-pixel rectangles
[x, y, w, h] of the regions that animate on their own: fan rotors, badge
pulses, the keyboard preview), plus OUTDIR/tour.json with a summary.

Platforms (never the live desktop):
- default: re-executes itself inside a headless gamescope with Qt on xcb,
  so the scene graph runs on OpenGL and MultiEffect / ShaderEffect render.
- --software: Qt's offscreen platform (software renderer, what CI has).
  MultiEffect and ShaderEffect do not render there.

--perf SECONDS samples this process's CPU time (os.times) with the idle
scene on screen and the demo ticking at 1 Hz, and prints the percentage of
one core. Without --only, --perf runs alone (plus the idle-cold shot).

Adding a scene: write a function taking the Tour and decorate it with
@scene("name"). The runner resets the daemon, scrolls to the top and closes
the curve editor before each scene, then waits for animations to settle and
grabs the window after it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[1]
QML_MAIN = REPO / "src" / "cryo" / "gui" / "qml" / "Main.qml"
INNER_ENV = "CRYO_TOUR_INNER"
SETTLE_MS = 1500          # longest UI easing is 700 ms (gauge glide)
RAMP_FRAMES = 40          # telemetry frames fed per scene (sparkline history)
HOLD_FRAMES = 8           # of which the last ones sit at the target

# objectNames of the self-driven animations, and how far their pixels reach
# beyond the item that owns them (halo/blur radius).
ANIMATED = {
    "cpuFanSpin": 4, "gpuFanSpin": 4,
    "guardPulse": 26, "gamingPulse": 26,
    "kbdAnim": 40,
}


# -- scene registry ----------------------------------------------------------

@dataclass
class Scene:
    name: str
    run: Callable[["Tour"], None]


SCENES: dict[str, Scene] = {}


def scene(name: str) -> Callable:
    def register(fn: Callable[["Tour"], None]) -> Callable[["Tour"], None]:
        SCENES[name] = Scene(name, fn)
        return fn
    return register


IDLE = {"cpu": 41, "gpu": 38}
WARM = {"cpu": 66, "gpu": 58, "gpu_util": 55, "vram_used_mb": 4200}
HOT = {"cpu": 88, "gpu": 79, "gpu_util": 92, "vram_used_mb": 7600}


@scene("idle-cold")
def _idle_cold(tour: "Tour") -> None:
    tour.ramp(**IDLE)


@scene("warm")
def _warm(tour: "Tour") -> None:
    tour.ramp(**WARM)


@scene("hot")
def _hot(tour: "Tour") -> None:
    tour.ramp(**HOT)


@scene("guard-held")
def _guard_held(tour: "Tour") -> None:
    tour.ramp(cpu=91, gpu=80, gpu_util=95, vram_used_mb=7000)
    tour.daemon.set_state(guard=True)


@scene("gaming")
def _gaming(tour: "Tour") -> None:
    tour.ramp(cpu=74, gpu=72, gpu_util=96, vram_used_mb=9200, gaming=True, profile="gmode")


@scene("disconnected")
def _disconnected(tour: "Tour") -> None:
    tour.ramp(**IDLE)
    tour.daemon.set_state(connected=False)


def _section(title: str, temps: dict) -> Callable[["Tour"], None]:
    def run(tour: "Tour") -> None:
        tour.ramp(**temps)
        tour.scroll_to_title(title)
    return run


for _name, _title, _temps in (
    ("sec-modes", "POWER MODES", IDLE),
    ("sec-telemetry", "TELEMETRY", WARM),
    ("sec-fans", "FAN CONTROL", WARM),
    ("sec-cpu", "CPU POWER", WARM),
    ("sec-automation", "AUTOMATION", WARM),
    ("sec-lighting", "LIGHTING", IDLE),
):
    scene(_name)(_section(_title, _temps))


@scene("sec-curve-editor")
def _curve_editor(tour: "Tour") -> None:
    tour.ramp(**WARM)
    tour.set_editor_open(True)
    tour.scroll_to(tour.find_object("curveBody"))


# -- the driver ----------------------------------------------------------------

class Tour:
    def __init__(self, app, engine, daemon, window) -> None:
        from PySide6.QtCore import QObject
        from PySide6.QtQuick import QQuickItem

        self.app, self.engine, self.daemon, self.window = app, engine, daemon, window
        self._QObject, self._QQuickItem = QObject, QQuickItem
        self.scroller = self.find_object("scroller")
        if self.scroller is None:
            raise SystemExit("tour: no Flickable named 'scroller' in Main.qml")

    # Qt helpers
    def wait(self, ms: int) -> None:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def find_object(self, name: str):
        return self.window.findChild(self._QObject, name)

    def items(self, root=None):
        root = root or self.window.contentItem()
        stack = [root]
        while stack:
            item = stack.pop()
            yield item
            stack.extend(item.childItems())

    def find_title(self, text: str):
        for item in self.items():
            if item.property("text") == text and item.isVisible():
                return item
        raise SystemExit(f"tour: no visible item with text {text!r}")

    # state
    def reset(self) -> None:
        self.daemon.pause()
        self.daemon.reset()
        self.set_editor_open(False)
        self.scroller.setProperty("contentY", 0)

    def ramp(self, cpu: float, gpu: float, **extra) -> None:
        """Feed RAMP_FRAMES frames gliding from the cold start to the target,
        holding at the target for the last HOLD_FRAMES, so the sparklines and
        peaks are the same on every run."""
        start_cpu, start_gpu = 40.0, 36.0
        n = RAMP_FRAMES - HOLD_FRAMES
        for i in range(RAMP_FRAMES):
            f = min(1.0, (i + 1) / n)
            self.daemon.set_state(
                cpu_temp=round(start_cpu + (cpu - start_cpu) * f, 1),
                gpu_temp=round(start_gpu + (gpu - start_gpu) * f, 1),
                **extra,
            )

    def set_editor_open(self, open_: bool) -> None:
        body = self.find_object("curveBody")
        if body is not None:
            body.setProperty("visible", open_)

    def scroll_to_title(self, text: str) -> None:
        self.scroll_to(self.find_title(text))

    def scroll_to(self, item) -> None:
        self.wait(50)       # let layouts settle so positions are final
        content = self.scroller.property("contentItem")
        y = item.mapToItem(content, 0, 0).y() - 12
        top = max(0.0, self.scroller.property("contentHeight") - self.scroller.height())
        self.scroller.setProperty("contentY", max(0.0, min(y, top)))

    # output
    def masks(self) -> list[list[int]]:
        dpr = self.window.devicePixelRatio()
        out = []
        for name, pad in ANIMATED.items():
            for obj in self.window.findChildren(self._QObject, name):
                item = obj
                while item is not None and not isinstance(item, self._QQuickItem):
                    item = item.parent()
                if item is None:
                    continue
                r = item.mapRectToScene(item.boundingRect())
                out.append([
                    int((r.x() - pad) * dpr), int((r.y() - pad) * dpr),
                    int((r.width() + 2 * pad) * dpr) + 1, int((r.height() + 2 * pad) * dpr) + 1,
                ])
        return out

    def shoot(self, sc: Scene, outdir: Path) -> dict:
        self.reset()
        sc.run(self)
        self.wait(SETTLE_MS)
        image = self.window.grabWindow()
        path = outdir / f"{sc.name}.png"
        if not image.save(str(path)):
            raise SystemExit(f"tour: could not write {path}")
        masks = self.masks()
        (outdir / f"{sc.name}.masks.json").write_text(json.dumps(masks))
        print(f"  {sc.name:<18} {image.width()}x{image.height()}  -> {path}", flush=True)
        return {"scene": sc.name, "file": path.name, "masks": masks}

    def perf(self, seconds: float) -> float:
        self.reset()
        _idle_cold(self)
        self.daemon.set_scenario("idle")
        self.daemon.clear_state()
        self.daemon.resume()
        self.wait(2000)                      # warm up: first frames, caches
        t0, c0 = time.monotonic(), os.times()
        self.wait(int(seconds * 1000))
        t1, c1 = time.monotonic(), os.times()
        self.daemon.pause()
        used = (c1.user - c0.user) + (c1.system - c0.system)
        return 100.0 * used / (t1 - t0)


# -- entry points ----------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tour.py", description=__doc__.split("\n\n")[0])
    p.add_argument("outdir", type=Path, nargs="?")
    p.add_argument("--only", default="", help="comma-separated scene names")
    p.add_argument("--software", action="store_true", help="offscreen software renderer")
    p.add_argument("--width", type=int, default=480)
    p.add_argument("--height", type=int, default=860)
    p.add_argument("--perf", type=float, metavar="SECONDS", help="sample idle CPU use")
    p.add_argument("--list", action="store_true", help="print scene names and exit")
    p.add_argument("--qml", type=Path, help="load this Main.qml instead (baselines)")
    args = p.parse_args(argv)
    if not args.list and args.outdir is None:
        p.error("OUTDIR is required")
    return args


# gamescope chatter (xkbcomp keymap warnings, vulkan modifier notes, info
# lines, the broken pipe on shutdown); real errors still come through.
NOISE = re.compile(r"^>\s|zero modifiers|xkbcomp|Unsupported maximum keycode|"
                   r"X11 cannot support keycodes|^\[gamescope\] \[\S*Info|"
                   r"failed to read Wayland events: Broken pipe")


def relaunch_under_gamescope(argv: list[str], args: argparse.Namespace) -> int:
    """GPU recipe: headless gamescope, Qt on its Xwayland (never the desktop)."""
    if shutil.which("gamescope") is None:
        print("tour: gamescope not found - install it or pass --software", file=sys.stderr)
        return 2
    cmd = [
        "gamescope", "--backend", "headless", "-W", str(args.width), "-H", str(args.height),
        "--", "env", "-u", "WAYLAND_DISPLAY", "QT_QPA_PLATFORM=xcb", f"{INNER_ENV}=1",
        sys.executable, str(Path(__file__).resolve()), *argv,
    ]
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, errors="replace")
    assert proc.stderr is not None
    for line in proc.stderr:
        if not NOISE.search(line):
            sys.stderr.write(line)
    proc.wait()
    summary = args.outdir / "tour.json"
    try:
        ok = json.loads(summary.read_text()).get("ok", False)
    except (OSError, ValueError):
        ok = False
    return 0 if ok else 1


def run_inner(args: argparse.Namespace) -> int:
    if args.software:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    elif os.environ.get("QT_QPA_PLATFORM") != "xcb" or os.environ.get("WAYLAND_DISPLAY"):
        # Safety: only ever draw inside gamescope or offscreen.
        print("tour: refusing to open a window outside gamescope/offscreen", file=sys.stderr)
        return 2
    sys.path.insert(0, str(REPO / "src"))

    from PySide6.QtCore import QObject  # noqa: F401  (findChild wrappers)
    from PySide6.QtQml import QJSValue
    from PySide6.QtQuick import QQuickItem, QQuickWindow  # noqa: F401
    from PySide6.QtWidgets import QApplication

    app = QApplication([sys.argv[0]])
    app.setApplicationName("Cryo-demo")

    from cryo.gui.demo import DemoDaemon
    from cryo.gui.main import build_engine

    daemon = DemoDaemon(scenario="idle", autostart=False)
    engine = build_engine(daemon, args.qml.resolve() if args.qml else None)
    if not engine.rootObjects():
        print("tour: Main.qml failed to load", file=sys.stderr)
        return 1
    window = engine.rootObjects()[0]
    window.setWidth(args.width)
    window.setHeight(args.height)

    # Offscreen windows are never active: force the ambient animations on so
    # shots show the app as a focused user sees it (absent before the split).
    forced = False
    qml_dir = (args.qml.resolve() if args.qml else QML_MAIN).parent
    if (qml_dir / "Cryo" / "qmldir").exists():   # pre-module QML has no Ambient
        ambient = engine.singletonInstance("Cryo", "Ambient")
        if isinstance(ambient, QJSValue):
            ambient = ambient.toQObject() if ambient.isQObject() else None
        if ambient is not None:
            ambient.setProperty("forceLive", True)
            forced = bool(ambient.property("forceLive"))

    tour = Tour(app, engine, daemon, window)
    tour.wait(500)
    api = window.rendererInterface().graphicsApi()
    api_name = getattr(api, "name", str(api))
    print(f"tour: graphics API {api_name}, platform {app.platformName()}, "
          f"dpr {window.devicePixelRatio()}, active {window.isActive()}, "
          f"forceLive {forced}", flush=True)

    outdir: Path = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    if args.only:
        names = [n.strip() for n in args.only.split(",") if n.strip()]
    elif args.perf:
        names = ["idle-cold"]
    else:
        names = list(SCENES)
    unknown = [n for n in names if n not in SCENES]
    if unknown:
        print(f"tour: unknown scene(s) {unknown}; known: {list(SCENES)}", file=sys.stderr)
        return 2

    summary: dict = {
        "ok": False, "graphics_api": api_name, "platform": app.platformName(),
        "dpr": window.devicePixelRatio(), "size": [args.width, args.height],
        "force_live": forced, "scenes": [],
    }
    for name in names:
        summary["scenes"].append(tour.shoot(SCENES[name], outdir))
    if args.perf:
        pct = tour.perf(args.perf)
        summary["perf"] = {"seconds": args.perf, "cpu_percent_of_one_core": round(pct, 2)}
        print(f"tour: perf idle {args.perf:g} s: {pct:.2f} % of one core", flush=True)
    summary["ok"] = True
    (outdir / "tour.json").write_text(json.dumps(summary, indent=2))

    # Engine before the bridge, or every daemon.* binding spams TypeError.
    del tour
    engine.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    del engine
    daemon.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)
    if args.list:
        print("\n".join(SCENES))
        return 0
    if args.software or os.environ.get(INNER_ENV):
        return run_inner(args)
    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "tour.json").unlink(missing_ok=True)
    return relaunch_under_gamescope(argv, args)


if __name__ == "__main__":
    sys.exit(main())
