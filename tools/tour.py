#!/usr/bin/env python3
"""Screenshot tour of the real Cryo GUI against the scripted demo daemon.

    tools/tour.py OUTDIR [--only scene,...] [--software] [--width 480 --height 860]
                         [--perf SECONDS] [--list]
                         [--style NAME] [--accent RRGGBB] [--reduce-motion] [--no-effects]

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

--style / --accent / --reduce-motion / --no-effects set the Prefs singleton
for the whole run. Prefs are QtCore Settings: the tour points QSettings at a
throwaway directory, so it never reads or writes real settings.

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
import tempfile
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
    settle: int = SETTLE_MS   # ms between the scene's last step and the grab


SCENES: dict[str, Scene] = {}


def scene(name: str, settle: int = SETTLE_MS) -> Callable:
    def register(fn: Callable[["Tour"], None]) -> Callable[["Tour"], None]:
        SCENES[name] = Scene(name, fn, settle)
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


GUARD = {"cpu": 91, "gpu": 80, "gpu_util": 95, "vram_used_mb": 7000}


@scene("guard-sweep", settle=250)
def _guard_sweep(tour: "Tour") -> None:
    # about 250 ms into the flash freeze (the sweep peaks at 550 ms)
    tour.ramp(**GUARD)
    tour.wait(SETTLE_MS)
    tour.daemon.set_state(guard=True)


@scene("guard-held")
def _guard_held(tour: "Tour") -> None:
    tour.ramp(**GUARD)
    tour.daemon.set_state(guard=True)


@scene("thaw", settle=1000)
def _thaw(tour: "Tour") -> None:
    # guard held, then released after the fans pulled the temps down:
    # about 1 s into the 2.5 s thaw
    tour.ramp(**GUARD)
    tour.daemon.set_state(guard=True)
    tour.wait(SETTLE_MS)
    tour.daemon.set_state(cpu_temp=72, gpu_temp=66, guard=False)


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


@scene("settings")
def _settings(tour: "Tour") -> None:
    tour.ramp(**IDLE)
    tour.window.setProperty("page", "settings")


@scene("sec-curve-editor")
def _curve_editor(tour: "Tour") -> None:
    tour.ramp(**WARM)
    tour.set_editor_open(True)
    tour.scroll_to(tour.find_object("curveBody"))


# ---- piece G: Settings, sound and Frost's line -------------------------------
# prepare_settings_piece() runs once at startup (run_inner): Sfx.dryRun on, so
# the tour never makes a sound (cues still fire Sfx.played); Frost's voice gets
# a seeded rng and a clock only the scenes move, so a line in a shot is the
# same on every run; and every reset also puts the Settings page back at the
# top with sound off (the page stays loaded while it fades out).

class _FrostClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


FROST_CLOCK = _FrostClock()


def _singleton(tour: "Tour", name: str):
    from PySide6.QtQml import QJSValue

    value = tour.engine.singletonInstance("Cryo", name)
    if isinstance(value, QJSValue):
        value = value.toQObject() if value.isQObject() else None
    return value


def prepare_settings_piece(tour: "Tour") -> None:
    import random

    from cryo.gui.voice import FrostVoice

    sfx = _singleton(tour, "Sfx")
    if sfx is not None:
        sfx.setProperty("dryRun", True)
    tour.daemon.set_voice(FrostVoice(rng=random.Random(7), clock=FROST_CLOCK))
    plain_reset = tour.reset

    def reset() -> None:
        plain_reset()
        prefs = _singleton(tour, "Prefs")
        if prefs is not None:
            prefs.setProperty("soundEnabled", False)
        settings_scroller = tour.find_object("settingsScroller")
        if settings_scroller is not None:
            settings_scroller.setProperty("contentY", 0)

    tour.reset = reset


def _open_settings(tour: "Tour"):
    tour.window.setProperty("page", "settings")
    tour.wait(50)
    scroller = tour.find_object("settingsScroller")
    if scroller is None:
        raise SystemExit("tour: no Flickable named 'settingsScroller' on the Settings page")
    scroller.setProperty("contentY", 0)
    return scroller


def _scroll_settings_to(tour: "Tour", scroller, text: str) -> None:
    tour.wait(50)
    item = tour.find_title(text)
    content = scroller.property("contentItem")
    y = item.mapToItem(content, 0, 0).y() - 12
    top = max(0.0, scroller.property("contentHeight") - scroller.height())
    scroller.setProperty("contentY", max(0.0, min(y, top)))


@scene("settings-sound")
def _settings_sound(tour: "Tour") -> None:
    tour.ramp(**IDLE)
    _singleton(tour, "Prefs").setProperty("soundEnabled", True)
    _scroll_settings_to(tour, _open_settings(tour), "SOUND")


@scene("settings-about")
def _settings_about(tour: "Tour") -> None:
    tour.ramp(**IDLE)
    _scroll_settings_to(tour, _open_settings(tour), "ABOUT")


@scene("footer")
def _footer(tour: "Tour") -> None:
    FROST_CLOCK.now += 600          # past greeting, profile and recovered lines
    tour.ramp(**IDLE)
    tour.wait(50)
    top = max(0.0, tour.scroller.property("contentHeight") - tour.scroller.height())
    tour.scroller.setProperty("contentY", top)


@scene("footer-held")
def _footer_held(tour: "Tour") -> None:
    # the bottom of the column with the guard holding (the bottom frost band
    # behind Frost's line and the last section titles)
    FROST_CLOCK.now += 600
    tour.ramp(**GUARD)
    tour.daemon.set_state(guard=True)
    tour.wait(50)
    top = max(0.0, tour.scroller.property("contentHeight") - tour.scroller.height())
    tour.scroller.setProperty("contentY", top)

# ---- end of piece G ----------------------------------------------------------


# -- the driver ----------------------------------------------------------------

class Tour:
    def __init__(self, app, engine, daemon, window) -> None:
        from PySide6.QtCore import QObject
        from PySide6.QtQuick import QQuickItem

        self.app, self.engine, self.daemon, self.window = app, engine, daemon, window
        self._QObject, self._QQuickItem = QObject, QQuickItem
        self.scroller = self.find_object("scroller")
        self.ambient = None          # set by run_inner when the QML has one
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
        from PySide6.QtCore import QMetaObject

        self.daemon.pause()
        self.daemon.reset()
        self.set_editor_open(False)
        self.window.setProperty("page", "home")
        self.scroller.setProperty("contentY", 0)
        if self.ambient is not None:
            QMetaObject.invokeMethod(self.ambient, "snap")

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
        self.wait(sc.settle)
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


# -- alive touches (cryo feel F2): bloom, hover, reveal ------------------------
# Synthetic pointer events go to the tour's own window only (QTest posts them
# straight into Qt), never to the desktop. Every scene starts with the
# pointer parked outside the window, so a hover never leaks into the next.

ANIMATED.update({"markOrbit": 12, "connBreath": 8})


def _pointer(tour: "Tour", x: float, y: float, press: bool = False) -> None:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    pos = QPoint(round(x), round(y))
    QTest.mouseMove(tour.window, pos)
    if press:
        QTest.mousePress(tour.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
        QTest.mouseRelease(tour.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)


def _park_pointer(tour: "Tour") -> None:
    _pointer(tour, -40, -40)


_reset_keeping_pointer = Tour.reset


def _reset_parking_pointer(self: "Tour") -> None:
    _reset_keeping_pointer(self)
    _park_pointer(self)


Tour.reset = _reset_parking_pointer     # type: ignore[method-assign]


def _centre(tour: "Tour", obj) -> tuple[float, float]:
    r = obj.mapRectToScene(obj.boundingRect())
    return r.x() + r.width() / 2, r.y() + r.height() / 2


@scene("bloom", settle=150)
def _bloom(tour: "Tour") -> None:
    # about 150 ms into the frost bloom under a pressed mode button
    tour.ramp(**IDLE)
    tour.wait(SETTLE_MS)
    # Repeater delegates are not QObject children of the window: walk items
    button = next((i for i in tour.items() if i.objectName() == "mode-cool"), None)
    if button is None:
        raise SystemExit("tour: no mode button 'mode-cool'")
    x, y = _centre(tour, button)
    _pointer(tour, x + 6, y - 4, press=True)


@scene("hover-panel", settle=500)
def _hover_panel(tour: "Tour") -> None:
    tour.ramp(**IDLE)
    tour.scroll_to_title("FAN CONTROL")
    tour.wait(SETTLE_MS)
    title = tour.find_title("Automatic fan curves")
    r = title.mapRectToScene(title.boundingRect())
    _pointer(tour, r.x() + r.width() + 40, r.y() + r.height() / 2)


@scene("reveal-mid", settle=200)
def _reveal_mid(tour: "Tour") -> None:
    # the first-show reveal replayed, 200 ms in (the stagger mid-flight)
    from PySide6.QtCore import QMetaObject

    tour.ramp(**IDLE)
    tour.wait(SETTLE_MS)
    if tour.ambient is not None:
        QMetaObject.invokeMethod(tour.ambient, "replayReveal")

# -- end alive touches -----------------------------------------------------------


# -- entry points ----------------------------------------------------------

def _hex_colour(value: str) -> str:
    v = value.lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", v):
        raise argparse.ArgumentTypeError(f"expected RRGGBB, got {value!r}")
    return "#" + v.upper()


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
    p.add_argument("--style", help="Prefs.style (cryo, aurora, glacier, blackout)")
    p.add_argument("--accent", type=_hex_colour, help="Prefs.accent override, RRGGBB")
    p.add_argument("--reduce-motion", action="store_true", help="Prefs.reduceMotion on")
    p.add_argument("--no-effects", action="store_true", help="Prefs.effects off")
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

    from PySide6.QtCore import QObject, QSettings  # noqa: F401  (findChild wrappers)
    from PySide6.QtQml import QJSValue
    from PySide6.QtQuick import QQuickItem, QQuickWindow  # noqa: F401
    from PySide6.QtWidgets import QApplication

    # Prefs (QtCore Settings) go to a throwaway directory: the tour never
    # reads or writes real settings, not even the demo's.
    settings_dir = tempfile.mkdtemp(prefix="cryo-tour-settings-")
    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, settings_dir)
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

    def singleton(name: str):
        value = engine.singletonInstance("Cryo", name)
        if isinstance(value, QJSValue):
            value = value.toQObject() if value.isQObject() else None
        return value

    # Offscreen windows are never active: force the ambient animations on so
    # shots show the app as a focused user sees it (absent before the split).
    forced = False
    prefs_set: dict = {}
    qml_dir = (args.qml.resolve() if args.qml else QML_MAIN).parent
    if (qml_dir / "Cryo" / "qmldir").exists():   # pre-module QML has no Ambient
        ambient = singleton("Ambient")
        if ambient is not None:
            ambient.setProperty("forceLive", True)
            forced = bool(ambient.property("forceLive"))
        wanted = {"style": args.style, "accent": args.accent,
                  "reduceMotion": True if args.reduce_motion else None,
                  "effects": False if args.no_effects else None}
        wanted = {k: v for k, v in wanted.items() if v is not None}
        prefs = singleton("Prefs") if wanted else None
        if wanted and prefs is None:
            print("tour: this QML has no Prefs singleton; style flags ignored", file=sys.stderr)
        for key, value in wanted.items():
            if prefs is not None:
                prefs.setProperty(key, value)
                prefs_set[key] = prefs.property(key)

    tour = Tour(app, engine, daemon, window)
    tour.ambient = singleton("Ambient") if forced else None
    if forced:                      # piece G: silent cues, a repeatable Frost line
        prepare_settings_piece(tour)
    tour.wait(500)
    api = window.rendererInterface().graphicsApi()
    api_name = getattr(api, "name", str(api))
    print(f"tour: graphics API {api_name}, platform {app.platformName()}, "
          f"dpr {window.devicePixelRatio()}, active {window.isActive()}, "
          f"forceLive {forced}, prefs {prefs_set or 'default'}", flush=True)

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
        "force_live": forced, "prefs": prefs_set, "scenes": [],
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
    shutil.rmtree(settings_dir, ignore_errors=True)
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
