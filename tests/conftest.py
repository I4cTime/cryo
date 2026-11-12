"""Shared fixtures.

The Qt fixture forces Qt's offscreen platform before any application object
exists: a test must never open a window on the developer's desktop.
"""

import os

import pytest


@pytest.fixture(scope="session")
def qapp():
    """One Qt application for the whole session: a QGuiApplication when
    QtGui can load on this runner, else a QCoreApplication (enough for the
    demo daemon). Tests that need QtGui/QtQuick check the type and skip."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    QtCore = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
    app = QtCore.QCoreApplication.instance()
    if app is None:
        try:
            from PySide6.QtGui import QGuiApplication
        except ImportError:
            app = QtCore.QCoreApplication([])
        else:
            app = QGuiApplication([])
    return app

