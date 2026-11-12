"""Frost's voice through the bridge: Daemon builds a Snapshot from telemetry,
exposes frostLine / frostLineKey and notifies only on a real change. Driven
by DemoDaemon.set_state with a seeded rng and a hand-moved clock."""

from __future__ import annotations

import os
import random

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # before any Qt application exists

from conftest import require_qt  # noqa: E402

require_qt("PySide6.QtCore")

from cryo.gui import voice as voice_mod  # noqa: E402
from cryo.gui.bridge import FROST_REEVALUATE_MS  # noqa: E402
from cryo.gui.voice import FrostVoice  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def frost(qapp):
    from cryo.gui.demo import DemoDaemon

    daemon = DemoDaemon(autostart=False)
    clock = Clock()
    daemon.set_voice(FrostVoice(rng=random.Random(3), clock=clock))
    emitted: list[tuple[str, str]] = []
    daemon.frostLineChanged.connect(lambda: emitted.append((daemon.frostLineKey, daemon.frostLine)))
    clock.now += 60          # past the greeting
    daemon.set_state(cpu_temp=41.0, gpu_temp=38.0, profile="balanced", ac=True)
    try:
        yield daemon, clock, emitted
    finally:
        daemon.deleteLater()


def situation(daemon) -> str:
    return daemon.frostLineKey.split(":")[0]


def template(daemon) -> str:
    name, index = daemon.frostLineKey.split(":")
    return voice_mod.LINES[name][int(index)]


def test_snapshot_reads_the_telemetry(frost):
    daemon, _, _ = frost
    daemon.set_state(cpu_temp=55.5, gpu_temp=61.2, ac=False, gaming=True, fan_rpm=2400)
    snap = daemon.frost_snapshot()
    assert snap.connected is True
    assert snap.cpu == pytest.approx(55.5) and snap.gpu == pytest.approx(61.2)
    assert snap.ac is False and snap.gaming is True and snap.guard is False
    assert snap.profile == "balanced"
    assert snap.rpm == 2400


def test_no_thermals_means_no_numbers(frost):
    daemon, _, _ = frost
    frame = daemon.build_frame()
    frame["capabilities"] = {**frame["capabilities"], "thermals": False, "ac_supply": False}
    daemon.feed(frame)
    snap = daemon.frost_snapshot()
    assert snap.cpu is None and snap.gpu is None and snap.rpm is None and snap.ac is None
    assert situation(daemon) == "blind"


def test_line_follows_set_state(frost):
    daemon, clock, _ = frost
    assert situation(daemon) == "cool"
    assert daemon.frostLine == voice_mod.render(template(daemon), daemon.frost_snapshot())

    daemon.set_state(cpu_temp=88.0, gpu_temp=79.0)
    assert situation(daemon) == "hot"

    daemon.set_state(guard=True)
    assert situation(daemon) == "guard"

    daemon.set_state(guard=False, cpu_temp=60.0, gpu_temp=55.0)
    assert situation(daemon) == "recovered"
    clock.now += voice_mod.RECOVERED_SECONDS + 1
    daemon.set_state(cpu_temp=60.0)
    assert situation(daemon) == "mild"

    daemon.set_state(gaming=True, cpu_temp=74.0)
    assert situation(daemon) == "gaming"

    daemon.set_state(gaming=False, cpu_temp=44.0, gpu_temp=40.0, ac=False)
    assert situation(daemon) == "battery"

    daemon.set_state(connected=False)          # no frame: the connection change drives it
    assert situation(daemon) == "disconnected"
    assert daemon.frostLine in voice_mod.LINES["disconnected"]


def test_profile_change_is_acknowledged(frost):
    daemon, clock, _ = frost
    daemon.set_state(profile="quiet")
    assert situation(daemon) == "profile"
    assert "Quiet" in daemon.frostLine
    clock.now += voice_mod.PROFILE_SECONDS + 1
    daemon.set_state(cpu_temp=41.0)
    assert situation(daemon) == "cool"


def test_key_is_stable_while_only_numbers_change(frost):
    daemon, _, emitted = frost
    # pick a seed whose cool template carries a number, so the text moves
    for seed in range(50):
        clock = Clock()
        daemon.set_voice(FrostVoice(rng=random.Random(seed), clock=clock))
        clock.now += 60                                # past the greeting
        daemon._update_frost()
        if situation(daemon) == "cool" and ("{hot}" in template(daemon) or "{cpu}" in template(daemon)):
            break
    else:
        pytest.fail("no numeric cool template came up")
    key, text = daemon.frostLineKey, daemon.frostLine
    emitted.clear()
    daemon.set_state(cpu_temp=43.0, gpu_temp=42.0)
    assert daemon.frostLineKey == key
    assert daemon.frostLine != text
    assert emitted == [(key, daemon.frostLine)]


def test_signal_only_fires_on_a_change(frost):
    daemon, _, emitted = frost
    emitted.clear()
    daemon.set_state(cpu_temp=41.0, gpu_temp=38.0)     # same frame again
    daemon.set_state(cpu_temp=41.0, gpu_temp=38.0)
    daemon._update_frost()                             # the slow timer's work
    assert emitted == []


def test_timer_lets_time_pass_without_telemetry(frost):
    daemon, clock, emitted = frost
    timer = daemon._frost_timer
    assert timer.isActive() and timer.interval() == FROST_REEVALUATE_MS
    daemon.set_state(guard=True)
    daemon.set_state(guard=False)
    assert situation(daemon) == "recovered"
    daemon.pause()
    clock.now += voice_mod.RECOVERED_SECONDS + 1
    emitted.clear()
    timer.timeout.emit()                               # no frame, only time
    assert situation(daemon) != "recovered"
    assert len(emitted) == 1


def test_greeting_on_first_connect_then_settles(qapp):
    from cryo.gui.demo import DemoDaemon

    clock = Clock()
    daemon = DemoDaemon(autostart=False)
    try:
        daemon.set_state(connected=False)
        daemon.set_voice(FrostVoice(rng=random.Random(5), clock=clock))
        assert situation(daemon) == "disconnected"
        daemon.set_state(connected=True, cpu_temp=41.0, gpu_temp=38.0)
        assert situation(daemon) == "greeting"
        clock.now += voice_mod.GREETING_SECONDS + 1
        daemon._update_frost()
        assert situation(daemon) == "cool"
    finally:
        daemon.deleteLater()


def test_real_daemon_starts_standing_by(qapp, monkeypatch, tmp_path):
    """The socket bridge (no cryod here) has a line before any frame."""
    from cryo import paths
    from cryo.gui.bridge import Daemon

    monkeypatch.setattr(paths, "RUN_SOCKET", tmp_path / "missing.sock")
    daemon = Daemon()
    try:
        assert daemon.frostLine == "Standing by."
        assert daemon.connected is False
        daemon._update_frost()
        assert situation(daemon) == "disconnected"
    finally:
        daemon._reconnect.stop()
        daemon.deleteLater()
