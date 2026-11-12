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


def test_a_cue_waits_for_the_bank_to_load(cues):
    """The switch that turns sound on cues "toggle_on" while the bank is
    still loading: the cue is held and plays once the bank is ready."""
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    component = QQmlComponent(cues.engine)
    component.setData(b"import QtQuick\nQtObject { property bool ready: false; "
                      b"property string failed: \"\"; property var plays: []; signal updated(); "
                      b"function play(name) { plays = plays.concat([name]) } }", QUrl())
    bank = component.create()
    assert bank is not None, component.errorString()
    sfx = cues.sfx
    try:
        sfx.setProperty("_bank", bank)
        sfx.setProperty("_state", "loading")
        cues.call(sfx, "play", "toggle_on")
        assert cues.played == ["toggle_on"]
        assert bank.property("plays").toVariant() == []
        bank.setProperty("ready", True)
        cues.call(sfx, "_bankState")
        assert sfx.property("state") == "ready"
        assert bank.property("plays").toVariant() == ["toggle_on"]
        cues.call(sfx, "_bankState")                 # played once, not again
        assert bank.property("plays").toVariant() == ["toggle_on"]
    finally:
        sfx.setProperty("_bank", None)
        sfx.setProperty("_state", "off")
        bank.deleteLater()
    assert cues.messages == []


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


# -- recovering from "unavailable" -------------------------------------------

FAKE_BANK = (
    "import QtQuick\n"
    "QtObject {{\n"
    "    property string soundSet\n"
    "    property real volume\n"
    "    property bool ready: {ready}\n"
    "    property string failed: \"{failed}\"\n"
    "    property var plays: []\n"
    "    signal updated()\n"
    "    function play(name) {{ plays = plays.concat([name]) }}\n"
    "}}\n"
)


@pytest.fixture
def banks(gui, tmp_path):
    """Sound on (not a dry run) against fake banks: nothing touches the
    audio backend. `use(kind)` points Sfx at one: "broken" (no output),
    "loading" (output, effects still loading) or "working"."""
    from PySide6.QtCore import QUrl

    sources = {}
    for kind, ready, failed in (("broken", "false", "no audio output device"),
                                ("loading", "false", ""), ("working", "true", "")):
        path = tmp_path / f"{kind}.qml"
        path.write_text(FAKE_BANK.format(ready=ready, failed=failed))
        sources[kind] = QUrl.fromLocalFile(str(path)).toString()
    sfx, prefs = gui.singleton("Sfx"), gui.singleton("Prefs")
    played: list[str] = []
    sfx.played.connect(played.append)

    def use(kind: str) -> None:
        sfx.setProperty("_bankSource", sources[kind])

    def cooldown_over() -> None:
        sfx.setProperty("_failedAt", sfx.property("_failedAt") - sfx.property("retryMs") - 1)

    use("broken")
    prefs.setProperty("soundEnabled", True)
    gui.sfx, gui.played, gui.use, gui.cooldown_over = sfx, played, use, cooldown_over
    try:
        yield gui
    finally:
        prefs.setProperty("soundEnabled", False)
        spin(sfx.property("closeDelayMs") + 50)
        assert sfx.property("_bank") is None


def _bank_plays(sfx) -> list:
    return sfx.property("_bank").property("plays").toVariant()


def test_a_failing_bank_marks_sound_unavailable(banks):
    sfx = banks.sfx
    assert sfx.property("state") == "unavailable" and sfx.property("available") is False
    assert sfx.property("reason") == "no audio output device"
    assert sfx.property("_bank") is None
    assert sfx.property("_failedAt") > 0
    assert banks.messages == []


def test_plays_inside_the_cooldown_do_not_retry(banks):
    sfx = banks.sfx
    failed_at = sfx.property("_failedAt")
    banks.use("working")                      # an output exists now, but it is too soon
    for cue in ("tap", "mode", "freeze"):
        banks.call(sfx, "play", cue)
    assert banks.played == ["tap", "mode", "freeze"]
    assert sfx.property("_bank") is None
    assert sfx.property("state") == "unavailable"
    assert sfx.property("_failedAt") == failed_at
    assert banks.messages == []


def test_a_play_after_the_cooldown_retries_and_recovers(banks):
    sfx = banks.sfx
    # still no output: the retry fails and starts a new cooldown
    banks.cooldown_over()
    stale = sfx.property("_failedAt")
    banks.call(sfx, "play", "tap")
    assert sfx.property("state") == "unavailable" and sfx.property("_bank") is None
    assert sfx.property("_failedAt") > stale
    # an output, effects still loading: Settings keeps the unavailable line
    banks.use("loading")
    banks.cooldown_over()
    banks.call(sfx, "play", "mode")
    assert sfx.property("_bank") is not None
    assert sfx.property("state") == "unavailable" and sfx.property("available") is False
    assert _bank_plays(sfx) == []
    sfx.property("_bank").setProperty("ready", True)
    banks.call(sfx, "_bankState")              # the bank's updated() signal
    assert sfx.property("state") == "ready" and sfx.property("available") is True
    assert sfx.property("reason") == ""
    assert _bank_plays(sfx) == ["mode"]        # the cue that triggered the retry
    spin(GAP)
    banks.call(sfx, "play", "tap")
    assert _bank_plays(sfx) == ["mode", "tap"]
    assert banks.played == ["tap", "mode", "tap"]
    assert banks.messages == []


def test_a_retry_straight_to_ready_plays_the_cue(banks):
    sfx = banks.sfx
    banks.use("working")
    banks.cooldown_over()
    banks.call(sfx, "play", "connect")
    assert sfx.property("state") == "ready"
    assert _bank_plays(sfx) == ["connect"]
    assert banks.messages == []


def test_dry_run_never_retries(banks):
    sfx = banks.sfx
    sfx.setProperty("dryRun", True)
    banks.use("working")
    banks.cooldown_over()
    banks.call(sfx, "play", "tap")
    assert banks.played == ["tap"]
    assert sfx.property("_bank") is None
    assert banks.messages == []
