"""GUI smoke: the real Main.qml loads offscreen against the demo daemon with
zero QML warnings, through the same build_engine() the app uses (the `gui`
fixture lives in conftest.py)."""

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # before any Qt application exists

from conftest import require_qt  # noqa: E402

require_qt("PySide6.QtGui")
require_qt("PySide6.QtQml")
require_qt("PySide6.QtQuick")
require_qt("PySide6.QtWidgets")      # cryo.gui.main (tray)

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtQuick import QQuickItem, QQuickWindow  # noqa: E402,F401

from conftest import spin  # noqa: E402

SECTIONS = ["secModes", "secTelemetry", "secFans", "secCpu", "secAutomation", "secLighting"]


def test_main_qml_loads_without_warnings(gui):
    assert gui.window is not None, gui.messages
    assert isinstance(gui.window, QQuickWindow)
    assert gui.window.title().endswith(" (demo)")
    for name in SECTIONS + ["scroller", "curveBody"]:
        assert gui.window.findChild(QObject, name) is not None, name
    spin(200)

    # Drive every state the UI branches on.
    d = gui.daemon
    for _ in range(3):
        d.step()
    d.set_state(cpu_temp=91, gpu_temp=80, guard=True, gaming=True, profile="gmode")
    d.setProfile("custom")
    d.setLighting("rainbow", "#3DDC97")
    d.setFanCurve("cpu", [[40, 0]])                 # rejected: error banner
    gui.window.findChild(QObject, "curveBody").setProperty("visible", True)
    d.set_state(connected=False)
    spin(300)
    assert gui.messages == []


def test_theme_and_ambient_contract(gui):
    theme = gui.singleton("Theme")
    ambient = gui.singleton("Ambient")
    assert theme is not None and ambient is not None
    for token in ("bg", "panel", "panelBorder", "track", "deck", "keycap", "fg", "muted",
                  "accent", "accent2", "accent2Text", "frost", "hot", "warn", "ok", "shadow"):
        assert theme.property(token) is not None, token
    assert theme.property("accent").name().upper() == "#00D1FF"
    assert theme.property("accent2").name().upper() == "#7B2DFF"
    assert theme.property("uiFont") and theme.property("monoFont")
    for prop in ("live", "forceLive", "motion", "connected"):
        assert ambient.property(prop) is not None, prop

    # Offscreen windows may or may not count as active; forceLive must win.
    ambient.setProperty("forceLive", True)
    spin(50)
    assert ambient.property("live") is True and ambient.property("motion") is True
    assert ambient.property("connected") is True
    gui.daemon.set_state(connected=False)
    spin(50)
    assert ambient.property("connected") is False
    assert gui.messages == []


def test_cli_flags_leave_qt_arguments_alone():
    from cryo.gui.main import parse_args

    args, qt_args = parse_args(["--demo", "--scenario", "guard", "-platform", "offscreen"])
    assert args.demo and args.scenario == "guard"
    assert qt_args == ["-platform", "offscreen"]
    args, qt_args = parse_args([])
    assert not args.demo and args.scenario == "cycle" and qt_args == []


def test_settings_page_toggles_and_returns(gui):
    window = gui.window
    assert window.property("page") == "home"
    gear = window.findChild(QObject, "settingsButton")
    assert gear is not None
    gear.clicked.emit()
    spin(50)
    assert window.property("page") == "settings"
    assert window.findChild(QObject, "scroller").property("visible") is False
    close = window.findChild(QObject, "settingsClose")
    assert close is not None
    assert window.findChild(QObject, "settingsBack") is None
    close.clicked.emit()
    spin(50)
    assert window.property("page") == "home"
    assert gui.messages == []


def test_prefs_identity_and_defaults(gui):
    from PySide6.QtCore import QCoreApplication

    from conftest import PREFS_DEFAULTS

    assert QCoreApplication.organizationName() == "i4c"
    assert QCoreApplication.organizationDomain() == "i4c.studio"
    # never the real app's settings file
    assert QCoreApplication.applicationName() not in ("Cryo", "Cryo-demo")
    assert os.environ["XDG_CONFIG_HOME"] != os.path.expanduser("~/.config")
    prefs = gui.singleton("Prefs")
    for key, value in PREFS_DEFAULTS.items():
        got = prefs.property(key)
        assert (round(got, 3) if isinstance(got, float) else got) == value, key
    sfx = gui.singleton("Sfx")
    assert sfx is not None
    gui.call(sfx, "play", "mode")           # the seam exists and does nothing
    assert gui.messages == []


def _grab(gui):
    gui.window.update()
    spin(30)
    return gui.window.grabWindow()


def test_reduce_motion_freezes_the_window(gui):
    """Reduce motion with the window live and every looping animation's
    trigger present (fans spinning, guard and gaming pulses, an animated
    lighting effect, frost held): frames 700 ms apart are identical."""
    prefs, ambient = gui.singleton("Prefs"), gui.singleton("Ambient")
    prefs.setProperty("reduceMotion", True)
    ambient.setProperty("forceLive", True)
    spin(50)
    assert ambient.property("live") is True and ambient.property("motion") is False
    gui.daemon.set_state(cpu_temp=88, gpu_temp=80, guard=True, gaming=True, fan_rpm=4200)
    gui.daemon.setLighting("rainbow", "#00D1FF")
    spin(600)                                 # past the frost crossfade
    scroller = gui.window.findChild(QObject, "scroller")
    for y in (0.0, max(0.0, scroller.property("contentHeight") - scroller.height())):
        scroller.setProperty("contentY", y)
        spin(100)
        first = _grab(gui)
        spin(700)
        second = _grab(gui)
        assert not first.isNull() and first == second, f"frames differ at contentY {y}"
    assert gui.messages == []


def test_motion_on_does_animate(gui):
    """Control for the test above: with motion allowed the same scene moves,
    so identical frames there mean something."""
    ambient = gui.singleton("Ambient")
    ambient.setProperty("forceLive", True)
    gui.daemon.set_state(cpu_temp=60, gpu_temp=55, fan_rpm=4200)
    spin(200)
    assert ambient.property("motion") is True
    first = _grab(gui)
    spin(700)
    second = _grab(gui)
    assert first != second
