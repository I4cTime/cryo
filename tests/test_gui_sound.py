"""Sound cues: Sfx accepts cues only while sound is on, never stacks the same
cue within its gap, builds nothing in dry run, and SoundWiring.qml plays the
state cues (mode, guard, connection, error). Every test runs in dry run:
nothing here makes a sound or touches the audio backend."""

from __future__ import annotations

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # before any Qt application exists

from conftest import require_qt  # noqa: E402

require_qt("PySide6.QtQuick")

from conftest import spin  # noqa: E402

GAP = 70          # ms; a little over Sfx.minGapMs


@pytest.fixture
def cues(gui):
    sfx = gui.singleton("Sfx")
    sfx.setProperty("dryRun", True)
    played: list[str] = []
    sfx.played.connect(played.append)
    gui.singleton("Prefs").setProperty("soundEnabled", True)
    spin(10)
    gui.sfx, gui.played = sfx, played
    return gui


def test_off_by_default_and_silent(gui):
    sfx, prefs = gui.singleton("Sfx"), gui.singleton("Prefs")
    sfx.setProperty("dryRun", True)
    played: list[str] = []
    sfx.played.connect(played.append)
    assert prefs.property("soundEnabled") is False
    assert sfx.property("state") == "off" and sfx.property("available") is True
    gui.daemon.set_state(guard=True, profile="quiet")
    gui.call(sfx, "play", "tap")
    spin(20)
    assert played == []
    assert gui.messages == []


def test_dry_run_builds_nothing(cues):
    assert cues.sfx.property("state") == "off"
    assert cues.sfx.property("_bank") is None
    cues.call(cues.sfx, "play", "mode")
    assert cues.played == ["mode"]


def test_names_and_gap(cues):
    names = cues.sfx.property("names")
    names = names.toVariant() if hasattr(names, "toVariant") else names
    assert names == ["tap", "toggle_on", "toggle_off", "mode", "freeze", "thaw",
                     "connect", "disconnect", "error"]
    cues.call(cues.sfx, "play", "tap")
    cues.call(cues.sfx, "play", "tap")          # stacked: dropped
    cues.call(cues.sfx, "play", "toggle_on")    # another cue is fine
    cues.call(cues.sfx, "play", "no-such-cue")
    spin(GAP)
    cues.call(cues.sfx, "play", "tap")
    assert cues.played == ["tap", "toggle_on", "tap"]


def test_startup_is_silent(cues):
    # the fixture's window saw the demo daemon's first frame and connection
    cues.daemon.set_state(cpu_temp=41.0)
    spin(10)
    assert cues.played == []


def test_profile_change_plays_mode(cues):
    cues.daemon.set_state(profile="quiet")
    spin(GAP)
    cues.daemon.set_state(profile="quiet", cpu_temp=45.0)      # same profile: nothing
    cues.daemon.setProfile("performance")                      # a mode button's path
    assert cues.played == ["mode", "mode"]


def test_guard_engage_and_release(cues):
    cues.daemon.set_state(guard=True)
    cues.daemon.set_state(guard=True, cpu_temp=92.0)
    cues.daemon.set_state(guard=False)
    assert cues.played == ["freeze", "thaw"]


def test_connection_lost_and_regained(cues):
    d = cues.daemon
    d.set_state(connected=False)
    spin(GAP)
    d.set_state(profile="cool")                 # changed while away: no "mode" on return
    d.set_state(connected=True)
    spin(GAP)
    d.set_state(guard=True)                     # cues resume after the first frame
    assert cues.played == ["disconnect", "connect", "freeze"]


def test_error_plays_error(cues):
    cues.daemon.setFanCurve("cpu", [[40, 0]])   # rejected by the config validator
    assert cues.played == ["error"]


def test_set_is_validated(cues):
    prefs = cues.singleton("Prefs")
    prefs.setProperty("soundSet", "glass")
    assert cues.sfx.property("_set") == "glass"
    prefs.setProperty("soundSet", "nonsense")
    assert cues.sfx.property("_set") == "ice"
    prefs.setProperty("soundVolume", 0.5)
    assert cues.sfx.property("_volume") == pytest.approx(0.25)
    assert cues.messages == []


def test_missing_qtmultimedia_degrades_visibly(qapp, tmp_path, monkeypatch):
    """A copy of the QML tree whose sound bank imports a module that is not
    installed: turning sound on must leave Sfx unavailable (Settings says so)
    with no QML warning or error. Nothing loads the real audio backend."""
    import shutil

    from PySide6.QtCore import QCoreApplication, QEvent, QtMsgType, qInstallMessageHandler

    import cryo.gui.main as gui_main
    from cryo.gui.demo import DemoDaemon
    from conftest import GuiHarness

    src = gui_main.QML_DIR
    qml = tmp_path / "gui" / "qml"
    shutil.copytree(src, qml)
    (tmp_path / "gui" / "assets").symlink_to(gui_main.ASSETS_DIR)
    bank = qml / "Cryo" / "SfxBank.qml"
    bank.write_text(bank.read_text().replace("import QtMultimedia\n", "import QtMultimediaNotInstalled\n"))
    monkeypatch.setattr(gui_main, "QML_DIR", qml)

    messages: list[str] = []

    def handler(mode, context, message):
        if mode not in (QtMsgType.QtDebugMsg, QtMsgType.QtInfoMsg):
            messages.append(f"{mode.name}: {message}")

    previous = qInstallMessageHandler(handler)
    daemon = DemoDaemon(autostart=False)
    engine = gui_main.build_engine(daemon)
    harness = GuiHarness(engine, daemon, messages)
    try:
        sfx, prefs = harness.singleton("Sfx"), harness.singleton("Prefs")
        prefs.setProperty("soundVolume", 0.0)
        prefs.setProperty("soundEnabled", True)
        spin(50)
        assert sfx.property("state") == "unavailable"
        assert sfx.property("available") is False
        assert "QtMultimediaNotInstalled" in sfx.property("reason")
        harness.window.setProperty("page", "settings")
        spin(50)
        line = None
        stack = [harness.window.contentItem()]
        while stack:
            item = stack.pop()
            if item.objectName() == "soundUnavailable":
                line = item
            stack.extend(item.childItems())
        assert line is not None and line.property("visible") is True
        seen = []
        sfx.played.connect(seen.append)
        daemon.set_state(guard=True)              # cues still resolve, nothing breaks
        assert seen == ["freeze"]
    finally:
        prefs = harness.singleton("Prefs")
        for key, value in {"soundEnabled": False, "soundVolume": 0.6}.items():
            prefs.setProperty(key, value)
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        daemon.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qInstallMessageHandler(previous)
    assert messages == []
