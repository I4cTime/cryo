"""GUI smoke: the real Main.qml loads offscreen against the demo daemon with
zero QML warnings, through the same build_engine() the app uses."""

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # before any Qt application exists

QtGui = pytest.importorskip("PySide6.QtGui", exc_type=ImportError)
pytest.importorskip("PySide6.QtQml", exc_type=ImportError)
pytest.importorskip("PySide6.QtQuick", exc_type=ImportError)
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)      # cryo.gui.main (tray)

from PySide6.QtCore import (  # noqa: E402
    QCoreApplication, QEvent, QObject, QtMsgType, qInstallMessageHandler,
)
from PySide6.QtQml import QJSValue  # noqa: E402
from PySide6.QtQuick import QQuickItem, QQuickWindow  # noqa: E402,F401


def spin(ms: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()

SECTIONS = ["secModes", "secTelemetry", "secFans", "secCpu", "secAutomation", "secLighting"]


def _singleton(engine, name):
    value = engine.singletonInstance("Cryo", name)
    if isinstance(value, QJSValue):
        value = value.toQObject() if value.isQObject() else None
    return value


@pytest.fixture
def gui(qapp):
    if not isinstance(qapp, QtGui.QGuiApplication):
        pytest.skip("QtGui is not usable on this runner")
    from cryo.gui.demo import DemoDaemon
    from cryo.gui.main import build_engine

    messages: list[str] = []

    def handler(mode, context, message):
        if mode not in (QtMsgType.QtDebugMsg, QtMsgType.QtInfoMsg):
            messages.append(f"{mode.name}: {message}")

    previous = qInstallMessageHandler(handler)
    daemon = DemoDaemon(autostart=False)
    engine = build_engine(daemon)
    try:
        yield SimpleGui(engine, daemon, messages)
    finally:
        # The engine goes before the bridge it references, or every
        # daemon.* binding fails on teardown.
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        daemon.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qInstallMessageHandler(previous)


class SimpleGui:
    def __init__(self, engine, daemon, messages):
        self.engine, self.daemon, self.messages = engine, daemon, messages
        roots = engine.rootObjects()
        self.window = roots[0] if roots else None


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
    theme = _singleton(gui.engine, "Theme")
    ambient = _singleton(gui.engine, "Ambient")
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
