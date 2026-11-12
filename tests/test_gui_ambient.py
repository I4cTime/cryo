"""Thermal chrome state in the Ambient singleton: heat from telemetry,
dormant, idle frost, the guard's flash freeze, held frost and thaw."""

from __future__ import annotations

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # before any Qt application exists

from conftest import require_qt  # noqa: E402

require_qt("PySide6.QtQuick")

from conftest import spin  # noqa: E402


@pytest.fixture
def amb(gui):
    ambient = gui.singleton("Ambient")
    ambient.setProperty("forceLive", True)
    spin(20)
    return ambient


def _p(obj, name):
    return obj.property(name)


def test_heat_maps_quantises_and_snaps(gui, amb):
    d = gui.daemon
    d.set_state(cpu_temp=45.0, gpu_temp=30.0)
    spin(20)
    assert _p(amb, "dormant") is False
    assert _p(amb, "heat") == pytest.approx(0.0)
    d.set_state(cpu_temp=50.0, gpu_temp=55.4)          # gpu wins, rounds to 55
    spin(600)                                           # a 0.25 jump eases first
    assert _p(amb, "heat") == pytest.approx(10 / 40)
    d.set_state(gpu_temp=55.3)                          # same whole degree: no change
    spin(20)
    assert _p(amb, "heatTarget") == pytest.approx(10 / 40)
    d.set_state(cpu_temp=99.0, gpu_temp=40.0)           # clamped to 1
    spin(600)                                           # big jump: eased, then lands
    assert _p(amb, "heat") == pytest.approx(1.0)


def test_large_jump_eases_small_steps_snap(gui, amb):
    d = gui.daemon
    d.set_state(cpu_temp=45.0, gpu_temp=40.0)
    spin(20)
    d.set_state(cpu_temp=47.0)                          # 0.05: snaps
    spin(5)
    assert _p(amb, "heat") == pytest.approx(2 / 40)
    d.set_state(cpu_temp=80.0)                          # 0.82 jump: eases over ~400 ms
    spin(60)
    mid = _p(amb, "heat")
    assert 2 / 40 < mid < 35 / 40
    spin(500)
    assert _p(amb, "heat") == pytest.approx(35 / 40)


def test_no_easing_under_reduce_motion(gui, amb):
    gui.singleton("Prefs").setProperty("reduceMotion", True)
    d = gui.daemon
    d.set_state(cpu_temp=45.0, gpu_temp=40.0)
    spin(20)
    d.set_state(cpu_temp=85.0)
    spin(5)
    assert _p(amb, "heat") == pytest.approx(1.0)


def test_dormant_when_disconnected(gui, amb):
    gui.daemon.set_state(cpu_temp=80.0, gpu_temp=70.0)
    spin(600)
    gui.daemon.set_state(connected=False)
    spin(600)
    assert _p(amb, "dormant") is True
    assert _p(amb, "heat") == pytest.approx(_p(amb, "neutralHeat"))


def test_idle_frost_follows_heat_and_effects(gui, amb):
    prefs = gui.singleton("Prefs")
    idle_max = _p(amb, "idleMax")
    d = gui.daemon
    d.set_state(cpu_temp=40.0, gpu_temp=38.0)
    spin(600)
    assert _p(amb, "frostAmount") == pytest.approx(idle_max)
    d.set_state(cpu_temp=57.0)                          # heat 0.3: half the idle frost
    spin(600)
    assert _p(amb, "frostAmount") == pytest.approx(idle_max * 0.5)
    d.set_state(cpu_temp=69.0)                          # heat 0.6: gone
    spin(600)
    assert _p(amb, "frostAmount") == pytest.approx(0.0)
    d.set_state(cpu_temp=40.0)
    spin(600)
    prefs.setProperty("effects", False)
    spin(20)
    assert _p(amb, "frostAmount") == 0


def test_flash_freeze_hold_and_thaw(gui, amb):
    d = gui.daemon
    d.set_state(cpu_temp=90.0, gpu_temp=80.0)
    spin(600)
    assert _p(amb, "frostAmount") == pytest.approx(0.0)
    d.set_state(guard=True)
    spin(30)
    assert _p(amb, "guardPhase") == "sweep"
    spin(450)
    assert _p(amb, "frostAmount") > 0.8                 # most of the way to the peak
    spin(1100)
    assert _p(amb, "guardPhase") == "held"
    assert _p(amb, "frostAmount") == pytest.approx(_p(amb, "heldAmount"))
    d.set_state(cpu_temp=60.0, gpu_temp=55.0, guard=False)
    spin(30)
    assert _p(amb, "guardPhase") == "thaw"
    spin(1000)
    mid = _p(amb, "frostAmount")
    assert _p(amb, "idleFrost") < mid < _p(amb, "heldAmount")
    spin(1800)
    assert _p(amb, "guardPhase") == "none"
    assert _p(amb, "frostAmount") == pytest.approx(_p(amb, "idleFrost"))
    assert gui.messages == []


def test_reduce_motion_jumps_and_signals_a_crossfade(gui, amb):
    gui.singleton("Prefs").setProperty("reduceMotion", True)
    jumps: list[float] = []
    amb.frostJumped.connect(lambda frm: jumps.append(frm))
    d = gui.daemon
    d.set_state(cpu_temp=40.0, gpu_temp=38.0)
    spin(20)
    d.set_state(guard=True)
    spin(5)
    assert _p(amb, "guardPhase") == "held"
    assert _p(amb, "frostAmount") == pytest.approx(_p(amb, "heldAmount"))
    d.set_state(guard=False)
    spin(5)
    assert _p(amb, "guardPhase") == "none"
    assert jumps == [pytest.approx(_p(amb, "idleMax")), pytest.approx(_p(amb, "heldAmount"))]
    assert gui.messages == []
