"""cryo-gui - QML window + system tray."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QUrl
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from cryo.gui.bridge import Daemon
from cryo.gui.icons import PROVIDER_ID, IconProvider

QML_DIR = Path(__file__).parent / "qml"
ASSETS_DIR = Path(__file__).parent / "assets"

# QSettings identity (the Prefs singleton): ~/.config/i4c/Cryo.conf, or
# Cryo-demo.conf in demo mode. The application name is the caller's.
ORGANIZATION = "i4c"
ORGANIZATION_DOMAIN = "i4c.studio"

PROFILE_LABELS = {
    "cool": "Cool",
    "quiet": "Quiet",
    "balanced": "Balanced",
    "performance": "Performance",
    "gmode": "G-Mode",
    "custom": "Custom",
    "low-power": "Low Power",
}


def _tray_pixmap(color: str = "#00D1FF") -> QPixmap:
    """Fallback tray art (plain quantum dot) if the brand assets are missing."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(color))
    painter.setBrush(QColor(color))
    painter.drawEllipse(8, 8, 48, 48)
    painter.end()
    return pixmap


def _brand_icon(name: str) -> QIcon | None:
    path = ASSETS_DIR / name
    if path.exists():
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return None


def build_engine(daemon: Daemon, qml_file: Path | None = None) -> QQmlApplicationEngine:
    """The QML engine every entry point uses (app, tour, tests): the `Cryo`
    module on the import path, the bridge as the `daemon` context property,
    Main.qml loaded. Check `engine.rootObjects()` for success, and delete
    the engine before the daemon it references.

    Sets the organization name and domain the Prefs singleton (QtCore
    Settings) needs; the application name ("Cryo", "Cryo-demo") is left to
    the caller, which must set it before this runs."""
    QCoreApplication.setOrganizationName(ORGANIZATION)
    QCoreApplication.setOrganizationDomain(ORGANIZATION_DOMAIN)
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIR))
    engine.addImageProvider(PROVIDER_ID, IconProvider())
    engine.rootContext().setContextProperty("daemon", daemon)
    engine.load(QUrl.fromLocalFile(str(qml_file or QML_DIR / "Main.qml")))
    return engine


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    """Cryo's own flags; everything else (-platform, -style ...) goes to Qt."""
    from cryo.gui.demo import SCENARIO_NAMES

    parser = argparse.ArgumentParser(prog="cryo-gui", allow_abbrev=False)
    parser.add_argument(
        "--demo", action="store_true",
        help="run against a scripted daemon (no cryod needed, real settings untouched)",
    )
    parser.add_argument(
        "--scenario", choices=SCENARIO_NAMES, default="cycle",
        help="demo timeline (default: cycle)",
    )
    return parser.parse_known_args(argv)


def main() -> None:
    args, qt_args = parse_args(sys.argv[1:])
    app = QApplication([sys.argv[0], *qt_args])
    # Demo mode runs under its own application name, so nothing it
    # persists (QSettings) can ever land in the real app's settings.
    app.setApplicationName("Cryo-demo" if args.demo else "Cryo")
    # Wayland app_id must match the desktop entry basename, or the
    # compositor can't associate the window with cryo.desktop (dock and
    # alt-tab would show a generic icon and the python binary name).
    app.setDesktopFileName("cryo")
    window_icon = _brand_icon("cryo-256.png")
    if window_icon:
        app.setWindowIcon(window_icon)
    app.setQuitOnLastWindowClosed(False)

    if args.demo:
        from cryo.gui.demo import DemoDaemon

        daemon: Daemon = DemoDaemon(scenario=args.scenario)
    else:
        daemon = Daemon()

    engine = build_engine(daemon)
    if not engine.rootObjects():
        sys.exit("Failed to load QML")
    window = engine.rootObjects()[0]

    def show_window() -> None:
        # Wayland: an existing surface can't raise itself - no activation
        # token flows through a tray click, so show()/raise_() on a buried
        # or minimized window silently does nothing (cosmic-comp declines).
        # Remap instead: hide+show maps a fresh toplevel, which the
        # compositor stacks on the current workspace, focused. Costs a
        # brief flicker when the window was already frontmost.
        window.hide()
        window.setWindowStates(Qt.WindowState.WindowNoState)
        window.show()
        window.requestActivate()

    # -- tray --------------------------------------------------------------

    # The 64px small-cut crystal (hexagon + spokes + core dot) - designed
    # to stay legible at tray size; falls back to the plain quantum dot.
    tray = QSystemTrayIcon(_brand_icon("cryo-64.png") or QIcon(_tray_pixmap()), app)
    menu = QMenu()

    show_action = QAction("Show Cryo")
    show_action.triggered.connect(show_window)
    menu.addAction(show_action)

    gmode_action = QAction("Toggle G-Mode")
    gmode_action.triggered.connect(daemon.toggleGmode)
    menu.addAction(gmode_action)

    profile_menu = menu.addMenu("Profile")

    def rebuild_profile_menu() -> None:
        # Capability-driven: only the profiles this machine's kernel driver
        # advertises. capabilitiesChanged fires once per daemon connection.
        gmode_action.setText(
            "Toggle G-Mode" if daemon.hasGmode else "Toggle Performance"
        )
        profile_menu.clear()
        for profile in daemon.profiles:
            action = QAction(
                PROFILE_LABELS.get(profile, profile.capitalize()), profile_menu
            )
            action.triggered.connect(
                lambda checked=False, p=profile: daemon.setProfile(p)
            )
            profile_menu.addAction(action)

    rebuild_profile_menu()
    daemon.capabilitiesChanged.connect(rebuild_profile_menu)

    menu.addSeparator()
    quit_action = QAction("Quit")
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    # Any non-context activation (left click, double click, middle click)
    # shows the window - whether these ever arrive is up to the tray host;
    # COSMIC's applet may only offer the context menu.
    tray.activated.connect(
        lambda reason: show_window()
        if reason != QSystemTrayIcon.ActivationReason.Context
        else None
    )

    def update_tooltip() -> None:
        tray.setToolTip(
            f"Cryo{' (demo)' if daemon.demo else ''} - {daemon.profile}\n"
            f"CPU {daemon.cpuTemp:.0f}°C · GPU {daemon.gpuTemp:.0f}°C"
            + (f" · VRAM {daemon.vramUsed / 1024:.1f}G" if daemon.vramTotal else "")
            + (" · GAMING" if daemon.gaming else "")
        )

    daemon.telemetryChanged.connect(update_tooltip)
    tray.show()

    # Tear the QML engine down before the bridge object it references;
    # otherwise every `daemon.*` binding spams TypeError on quit.
    app.aboutToQuit.connect(engine.deleteLater)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
