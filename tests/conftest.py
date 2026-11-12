"""Shared fixtures.

The Qt fixture forces Qt's offscreen platform before any application object
exists: a test must never open a window on the developer's desktop.
"""

import importlib
import os

import pytest


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
    return app

