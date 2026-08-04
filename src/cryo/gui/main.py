"""cryo-gui — QML window + system tray."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from cryo.gui.bridge import Daemon

QML_DIR = Path(__file__).parent / "qml"

PROFILES = ["cool", "quiet", "balanced", "performance", "gmode", "custom"]


def _tray_pixmap(color: str = "#00D1FF") -> QPixmap:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(color))
    painter.setBrush(QColor(color))
    painter.drawEllipse(8, 8, 48, 48)
    painter.end()
    return pixmap


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Cryo")
    app.setQuitOnLastWindowClosed(False)

    daemon = Daemon()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("daemon", daemon)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    if not engine.rootObjects():
        sys.exit("Failed to load QML")
    window = engine.rootObjects()[0]

    # -- tray --------------------------------------------------------------

    tray = QSystemTrayIcon(QIcon(_tray_pixmap()), app)
    menu = QMenu()

    show_action = QAction("Show Cryo")
    show_action.triggered.connect(lambda: (window.show(), window.raise_()))
    menu.addAction(show_action)

    gmode_action = QAction("Toggle G-Mode")
    gmode_action.triggered.connect(daemon.toggleGmode)
    menu.addAction(gmode_action)

    profile_menu = menu.addMenu("Profile")
    for profile in PROFILES:
        action = QAction(profile.capitalize(), profile_menu)
        action.triggered.connect(lambda checked=False, p=profile: daemon.setProfile(p))
        profile_menu.addAction(action)

    menu.addSeparator()
    quit_action = QAction("Quit")
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: (window.show(), window.raise_())
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )

    def update_tooltip() -> None:
        tray.setToolTip(
            f"Cryo — {daemon.profile}\n"
            f"CPU {daemon.cpuTemp:.0f}°C · GPU {daemon.gpuTemp:.0f}°C"
            + (" · GAMING" if daemon.gaming else "")
        )

    daemon.telemetryChanged.connect(update_tooltip)
    tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
