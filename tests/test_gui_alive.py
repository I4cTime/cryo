"""Alive touches (cryo feel): rolling digits, the living mark, dormant frost,
the frost bloom, the first-show reveal, and the rule that keeps every loop
off while the window is not live."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # before any Qt application exists

from conftest import require_qt  # noqa: E402

require_qt("PySide6.QtQuick")

from PySide6.QtCore import QObject  # noqa: E402

from conftest import spin  # noqa: E402

QML_DIR = Path(__file__).resolve().parents[1] / "src" / "cryo" / "gui" / "qml"
SECTIONS = ["secModes", "secTelemetry", "secFans", "secCpu", "secAutomation", "secLighting"]


# -- the loop guard (lint) ------------------------------------------------------

LOOP = re.compile(r"\bFrameAnimation\s*\{|loops\s*:\s*Animation\.Infinite")
PROPERTY = re.compile(r"property\s+bool\s+(\w+)\s*:\s*(.*)")


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif line.startswith("//", i):
            break
        out.append(ch)
    return "".join(out)


def _own_text(code: str, open_at: int) -> str:
    """The text directly inside the object whose `{` is at `open_at`
    (nested objects left out)."""
    out, depth = [], 0
    for ch in code[open_at:]:
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                break
            continue
        if depth == 1:
            out.append(ch)
    return "".join(out)


def _enclosing_open(code: str, at: int) -> int:
    depth = 0
    for i in range(at - 1, -1, -1):
        if code[i] == "}":
            depth += 1
        elif code[i] == "{":
            if depth == 0:
                return i
            depth -= 1
    raise AssertionError(f"no enclosing object at offset {at}")


def loop_violations(source: str, name: str = "<qml>") -> list[str]:
    """Every FrameAnimation and every `loops: Animation.Infinite` must have
    a `running:` binding on the object itself whose expression mentions
    `Ambient.motion`, directly or through a `property bool` of the same file
    whose definition does. Returns one message per offender."""
    code = "\n".join(_strip_comment(line) for line in source.splitlines())
    gated = {m.group(1) for m in PROPERTY.finditer(code) if "Ambient.motion" in m.group(2)}
    problems = []
    for m in LOOP.finditer(code):
        open_at = m.end() - 1 if m.group(0).endswith("{") else _enclosing_open(code, m.start())
        running = re.search(r"\brunning\s*:\s*([^;\n]+)", _own_text(code, open_at))
        where = f"{name}:{code.count(chr(10), 0, m.start()) + 1}"
        if running is None:
            problems.append(f"{where}: loop without a `running:` binding")
            continue
        expr = running.group(1).strip()
        if "Ambient.motion" not in expr and not (set(re.findall(r"\w+", expr)) & gated):
            problems.append(f"{where}: `running: {expr}` is not gated on Ambient.motion")
    return problems


def test_lint_catches_ungated_loops():
    bad = """Item {
    FrameAnimation { running: true; onTriggered: x += 1 }
    NumberAnimation on y { loops: Animation.Infinite; to: 10 }
    SequentialAnimation on opacity {
        running: visible
        loops: Animation.Infinite
    }
}"""
    assert len(loop_violations(bad)) == 3
    good = """Item {
    readonly property bool spinning: Ambient.motion && visible
    FrameAnimation {
        running: Ambient.motion && visible   // gated
        onTriggered: x += 1
    }
    SequentialAnimation on opacity {
        running: root.spinning
        loops: Animation.Infinite
        NumberAnimation { to: 1 }
    }
}"""
    assert loop_violations(good) == []


def test_every_loop_is_gated_on_motion():
    files = sorted(QML_DIR.rglob("*.qml"))
    found, problems = 0, []
    for path in files:
        source = path.read_text(encoding="utf-8")
        found += len(LOOP.findall(source))
        problems += loop_violations(source, path.relative_to(QML_DIR).as_posix())
    assert found >= 5          # fan glyphs, badge pulse, keyboard, mark orbit, conn breath
    assert problems == []


# -- helpers ----------------------------------------------------------------------

def _items(root):
    stack = [root]
    while stack:
        item = stack.pop()
        yield item
        stack.extend(item.childItems())


def _find(gui, name):
    for item in _items(gui.window.contentItem()):
        if item.objectName() == name:
            return item
    raise AssertionError(f"no item {name!r}")


def _roll_state(roll):
    """(text the cells show, whether every cell sits still at rest)."""
    cells = sorted((c for c in _items(roll) if c.objectName() == "rollCell" and c.isVisible()),
                   key=lambda c: c.x())
    text = "".join(c.property("cur") for c in cells)
    still = all(c.property("p") == 1 for c in cells)
    for c in cells:
        cur = next(t for t in _items(c) if t.objectName() == "rollCur")
        still = still and cur.y() == 0
    return text, still


@pytest.fixture
def live(gui):
    ambient = gui.singleton("Ambient")
    ambient.setProperty("forceLive", True)
    spin(80)
    return ambient


# -- rolling digits ------------------------------------------------------------

def test_rolling_number_rolls_then_settles(gui, live):
    d = gui.daemon
    d.set_state(cpu_temp=41.0, gpu_temp=38.0, fan_rpm=1300)
    spin(400)
    roll = _find(gui, "cpuTempRoll")
    assert _roll_state(roll) == ("41", True)
    d.set_state(cpu_temp=88.0)
    spin(40)
    assert roll.property("rolling") is True
    assert _roll_state(roll)[1] is False
    spin(400)
    assert roll.property("rolling") is False
    assert _roll_state(roll) == ("88", True)
    rpm = _find(gui, "cpuRpmRoll")
    d.set_state(fan_rpm=4210)
    spin(400)
    assert _roll_state(rpm) == ("4210 rpm", True)
    assert gui.messages == []


def test_rolling_number_is_plain_text_without_motion(gui, live):
    gui.singleton("Prefs").setProperty("reduceMotion", True)
    d = gui.daemon
    d.set_state(cpu_temp=41.0, gpu_temp=38.0)
    spin(20)
    roll = _find(gui, "cpuTempRoll")
    d.set_state(cpu_temp=100.0)
    spin(5)
    assert roll.property("rolling") is False
    assert _roll_state(roll) == ("100", True)
    d.set_state(cpu_temp=9.0)
    spin(5)
    assert _roll_state(roll) == ("9", True)
    assert gui.messages == []


# -- dormant frost and the living mark ------------------------------------------

def test_dormant_frost_holds_a_light_fixed_value(gui, live):
    amb = live
    d = gui.daemon
    d.set_state(cpu_temp=88.0, gpu_temp=80.0)          # hot: no idle frost
    spin(700)
    assert amb.property("frostAmount") == pytest.approx(0.0)
    d.set_state(connected=False)
    spin(30)
    mid = amb.property("frostAmount")
    assert 0.0 < mid < amb.property("dormantFrost")     # eases in
    spin(800)
    assert amb.property("frostAmount") == pytest.approx(amb.property("dormantFrost"))
    assert amb.property("dormantFrost") == pytest.approx(0.34)
    d.set_state(connected=True, cpu_temp=40.0, gpu_temp=38.0)
    spin(800)
    assert amb.property("frostAmount") == pytest.approx(amb.property("idleMax"))
    gui.singleton("Prefs").setProperty("effects", False)
    d.set_state(connected=False)
    spin(20)
    assert amb.property("frostAmount") == 0
    assert gui.messages == []


def test_dormant_frost_jumps_under_reduce_motion(gui, live):
    gui.singleton("Prefs").setProperty("reduceMotion", True)
    gui.daemon.set_state(cpu_temp=88.0, gpu_temp=80.0)
    spin(20)
    gui.daemon.set_state(connected=False)
    spin(5)
    assert live.property("frostAmount") == pytest.approx(live.property("dormantFrost"))


def test_stale_telemetry_dims_when_cryod_is_unreachable(gui, live):
    """Capability honesty: with cryod gone the figures on screen are the last
    reading. They stay shown, but dim, go muted and the fans stop."""
    theme = gui.singleton("Theme")
    d = gui.daemon
    d.set_state(cpu_temp=60.0, gpu_temp=55.0, fan_rpm=3000, gpu_util=50)
    spin(50)
    cpu = _find(gui, "cpuTile")
    fan = cpu.findChild(QObject, "cpuFanSpin")
    assert cpu.property("stale") is False
    assert cpu.property("inkOpacity") == pytest.approx(1.0)
    assert fan.property("running") is True
    assert _find(gui, "cpuTempRoll").property("color") == theme.property("fg")

    d.set_state(connected=False)
    spin(50)
    for name in ("cpuTile", "gpuTile"):
        tile = _find(gui, name)
        assert tile.property("visible") is True                      # not hidden
        assert tile.property("stale") is True
        assert tile.property("inkOpacity") == pytest.approx(0.45)
        assert tile.property("arcColor") == theme.property("muted")
    assert fan.property("running") is False
    roll = _find(gui, "cpuTempRoll")
    assert roll.property("text") == "60"                             # the last reading
    assert roll.property("color") == theme.property("muted")
    assert _find(gui, "cpuRpmRoll").property("color") == theme.property("muted")
    assert _find(gui, "gpuLoadRow").property("opacity") == pytest.approx(0.45)
    assert _find(gui, "vramPanel").property("inkOpacity") == pytest.approx(0.45)
    # controls are not telemetry: they stay as they are
    assert _find(gui, "secFans").property("opacity") == pytest.approx(1.0)
    assert _find(gui, "mode-cool").property("opacity") == pytest.approx(1.0)

    d.set_state(connected=True, cpu_temp=61.0)
    spin(50)
    assert cpu.property("stale") is False
    assert cpu.property("arcColor") != theme.property("muted")
    assert fan.property("running") is True
    assert gui.messages == []


def test_mark_draws_without_effects_on_the_software_renderer(gui):
    # Offscreen tests run on the software renderer, which draws no
    # MultiEffect: the mark (and the gauge arcs) must show as plain items.
    spin(50)
    mark = _find(gui, "livingMark")
    if mark.property("effectsDrawn"):
        pytest.skip("not on the software renderer")
    assert _find(gui, "markPlain").isVisible()


def test_mark_orbits_awake_and_sleeps_dormant(gui, live):
    d = gui.daemon
    d.set_state(cpu_temp=50.0, gpu_temp=45.0, fan_rpm=0)
    spin(100)
    mark = _find(gui, "livingMark")
    orbit = mark.findChild(QObject, "markOrbit")
    assert mark.property("awake") == pytest.approx(1.0)
    assert orbit.property("running") is True
    assert mark.property("targetSpeed") == pytest.approx(0.12)
    d.set_state(fan_rpm=5600)
    spin(50)
    assert mark.property("targetSpeed") == pytest.approx(1.0)
    p0 = mark.property("phase")
    spin(300)
    assert mark.property("phase") != p0
    assert mark.property("speed") < 1.0                  # eases, never jumps

    d.set_state(connected=False)
    spin(1000)
    assert mark.property("asleep") is True
    assert mark.property("awake") == pytest.approx(0.0)
    assert orbit.property("running") is False            # no frames for a sleeping mark
    motes = [i for i in _items(mark) if i.property("depth") is not None]
    assert len(motes) == 5 and all(not m.isVisible() for m in motes)
    assert gui.messages == []


def test_mark_motes_still_under_reduce_motion(gui, live):
    gui.singleton("Prefs").setProperty("reduceMotion", True)
    gui.daemon.set_state(cpu_temp=50.0, gpu_temp=45.0, fan_rpm=4000)
    spin(100)
    mark = _find(gui, "livingMark")
    assert mark.findChild(QObject, "markOrbit").property("running") is False
    assert mark.property("phase") == 0
    motes = [i for i in _items(mark) if i.property("depth") is not None]
    assert motes and all(m.isVisible() for m in motes)


def test_conn_dot_breathes_only_connected_with_motion(gui, live):
    breath = gui.window.findChild(QObject, "connBreath")
    assert breath is not None and breath.property("running") is True
    gui.daemon.set_state(connected=False)
    spin(20)
    assert breath.property("running") is False
    gui.daemon.set_state(connected=True)
    gui.singleton("Prefs").setProperty("reduceMotion", True)
    spin(20)
    assert breath.property("running") is False


# -- frost bloom ----------------------------------------------------------------

def _bloom(gui):
    button = _find(gui, "mode-cool")
    return next(i for i in _items(button) if i.property("reach") is not None)


def test_bloom_plays_with_motion_only(gui, live):
    bloom = _bloom(gui)
    assert bloom.property("active") is False and bloom.isVisible() is False
    gui.call(bloom, "burst", 20, 20)
    spin(100)
    assert bloom.property("active") is True
    spin(500)
    assert bloom.property("active") is False             # once, about 450 ms
    gui.singleton("Prefs").setProperty("reduceMotion", True)
    spin(20)
    gui.call(bloom, "burst", 20, 20)
    spin(50)
    assert bloom.property("active") is False
    assert gui.messages == []


# -- reveal -----------------------------------------------------------------------

def test_reveal_shows_every_section_and_happens_once(gui, live):
    spin(200)
    amb = live
    assert amb.property("revealed") is True
    sections = [gui.window.findChild(QObject, n) for n in SECTIONS]
    # the software renderer (these tests) gets the instant reveal
    assert all(s.property("opacity") == 1 for s in sections)
    gui.call(amb, "replayReveal")
    spin(20)
    assert all(s.property("opacity") == 1 for s in sections)
    # the panel shadows settle in over the reveal, and land at once if the
    # window stops being live meanwhile
    assert amb.property("revealShadow") < 1
    amb.setProperty("forceLive", False)
    amb.setProperty("live", False)
    spin(5)
    assert amb.property("revealShadow") == 1
    assert gui.messages == []


def test_reveal_is_skipped_for_a_window_started_hidden(gui):
    """Started hidden (in the tray): the window never goes live, the reveal
    deadline passes and the sections simply show, so they are never stuck
    invisible."""
    gui.window.hide()
    amb = gui.singleton("Ambient")
    spin(1700)
    assert amb.property("live") is False
    assert amb.property("revealed") is True
    for n in SECTIONS:
        assert gui.window.findChild(QObject, n).property("opacity") == 1


def _running_loops(gui):
    """Every FrameAnimation and infinite animation that is running now."""
    def walk(obj):
        yield obj
        for child in obj.children():
            yield from walk(child)
    out = []
    for obj in walk(gui.window):
        mo = obj.metaObject()
        if mo.indexOfProperty("running") < 0 or not obj.property("running"):
            continue
        if mo.className() == "QQuickFrameAnimation" or obj.property("loops") == -1:
            out.append(obj.objectName() or mo.className())
    return out


def test_no_loops_or_frames_while_not_live(gui):
    """Unfocused (live false) with every loop's trigger present (fans at
    speed, the mark awake, cryod connected, guard and gaming pulses): no
    loop runs and the window renders no frames."""
    amb = gui.singleton("Ambient")
    gui.daemon.set_state(cpu_temp=88.0, gpu_temp=80.0, fan_rpm=4200, guard=True, gaming=True)
    gui.daemon.setLighting("rainbow", "#00D1FF")
    amb.setProperty("forceLive", True)
    spin(300)
    assert {"markOrbit", "connBreath", "cpuFanSpin"} <= set(_running_loops(gui))
    # As if the window lost focus: Main.qml's Binding writes `live` only
    # when the window state changes, so this sticks for the test.
    amb.setProperty("forceLive", False)
    amb.setProperty("live", False)
    spin(600)                                  # let one-shot easings land
    assert amb.property("motion") is False
    assert _running_loops(gui) == []
    frames = []
    gui.window.afterRendering.connect(lambda: frames.append(1))
    spin(1000)
    assert frames == [], f"{len(frames)} frames in 1 s with the window not live"
    amb.setProperty("live", True)              # control: live again, it renders
    spin(500)
    assert len(frames) > 5
    assert gui.messages == []


def _grab(gui):
    gui.window.update()
    spin(30)
    return gui.window.grabWindow()


def test_reduce_motion_freezes_the_living_header(gui, live):
    """Reduce motion with the mark awake and visible, fans spinning (motes
    would orbit at full speed), the conn dot connected: frames 700 ms apart
    are pixel-identical."""
    gui.singleton("Prefs").setProperty("reduceMotion", True)
    gui.daemon.set_state(cpu_temp=60, gpu_temp=55, fan_rpm=5200)
    spin(300)
    mark = _find(gui, "livingMark")
    assert mark.isVisible() and mark.property("awake") == pytest.approx(1.0)
    assert mark.property("fastestRpm") >= 5000
    gui.window.findChild(QObject, "scroller").setProperty("contentY", 0)
    first = _grab(gui)
    spin(700)
    second = _grab(gui)
    assert not first.isNull() and first == second
    assert gui.messages == []
