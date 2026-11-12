"""Shared fixtures.

The Qt fixture forces Qt's offscreen platform before any application object
exists: a test must never open a window on the developer's desktop.

Settings isolation: XDG_CONFIG_HOME points at a throwaway directory before
any Qt object exists, and the application is named "Cryo-test", so the GUI's
Prefs (QtCore Settings) can never read or write the user's real
~/.config/i4c/Cryo.conf.
"""

import atexit
import importlib
import os
import shutil
import tempfile

import pytest

_CONFIG_HOME = tempfile.mkdtemp(prefix="cryo-test-config-")
os.environ["XDG_CONFIG_HOME"] = _CONFIG_HOME
atexit.register(shutil.rmtree, _CONFIG_HOME, ignore_errors=True)


def require_qt(name: str):
    """Import a Qt module, skipping the test when it cannot load on this
    machine. On CI a missing Qt library is a failure instead: the workflow
    installs them, and a silent skip would turn the GUI tests off."""
    if os.environ.get("CI"):
        return importlib.import_module(name)
    return pytest.importorskip(name, exc_type=ImportError)


@pytest.fixture(scope="session")
def qapp():
    """One Qt application for the whole session: a QGuiApplication when
    QtGui can load on this runner, else a QCoreApplication (enough for the
    demo daemon). Tests that need QtGui/QtQuick check the type and skip."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    QtCore = require_qt("PySide6.QtCore")
    app = QtCore.QCoreApplication.instance()
    if app is None:
        try:
            from PySide6.QtGui import QGuiApplication
        except ImportError:
            if os.environ.get("CI"):
                raise
            app = QtCore.QCoreApplication([])
        else:
            app = QGuiApplication([])
    app.setApplicationName("Cryo-test")
    return app



# Prefs keys and their defaults (Prefs.qml). GUI tests restore these on
# teardown so one test's style or motion choice never leaks into the next
# through the (temp) settings file.
PREFS_DEFAULTS = {
    "style": "cryo", "accent": "", "effects": True, "reduceMotion": False,
    "soundEnabled": False, "soundSet": "ice", "soundVolume": 0.6, "frostLine": True,
}


def spin(ms: int) -> None:
    """Run the Qt event loop for `ms` milliseconds."""
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class GuiHarness:
    """The real Main.qml loaded offscreen against a paused DemoDaemon.
    `messages` collects every Qt warning or error emitted meanwhile."""

    def __init__(self, engine, daemon, messages):
        self.engine, self.daemon, self.messages = engine, daemon, messages
        roots = engine.rootObjects()
        self.window = roots[0] if roots else None

    def singleton(self, name: str):
        from PySide6.QtQml import QJSValue

        value = self.engine.singletonInstance("Cryo", name)
        if isinstance(value, QJSValue):
            value = value.toQObject() if value.isQObject() else None
        return value

    def call(self, obj, method: str, *args):
        """Call a QML function (its arguments arrive as QVariant)."""
        from PySide6.QtCore import Q_ARG, QMetaObject

        QMetaObject.invokeMethod(obj, method, *(Q_ARG("QVariant", a) for a in args))


@pytest.fixture
def gui(qapp):
    QtGui = require_qt("PySide6.QtGui")
    require_qt("PySide6.QtQml")
    require_qt("PySide6.QtQuick")
    require_qt("PySide6.QtWidgets")   # cryo.gui.main (tray)
    if not isinstance(qapp, QtGui.QGuiApplication):
        pytest.skip("QtGui is not usable on this runner")   # unreachable on CI: qapp raises there
    from PySide6.QtCore import QCoreApplication, QEvent, QtMsgType, qInstallMessageHandler

    from cryo.gui.demo import DemoDaemon
    from cryo.gui.main import build_engine

    messages: list[str] = []

    def handler(mode, context, message):
        if mode not in (QtMsgType.QtDebugMsg, QtMsgType.QtInfoMsg):
            messages.append(f"{mode.name}: {message}")

    previous = qInstallMessageHandler(handler)
    daemon = DemoDaemon(autostart=False)
    engine = build_engine(daemon)
    harness = GuiHarness(engine, daemon, messages)
    try:
        yield harness
    finally:
        prefs = harness.singleton("Prefs") if harness.window is not None else None
        if prefs is not None:
            for key, value in PREFS_DEFAULTS.items():
                prefs.setProperty(key, value)
        # The engine goes before the bridge it references, or every
        # daemon.* binding fails on teardown.
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        daemon.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qInstallMessageHandler(previous)
    # Teardown is part of the contract: deleting in the wrong order makes
    # every daemon.* binding warn, and that must not pass unnoticed.
    assert not messages, messages
