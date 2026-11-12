"""Thermal chrome state in the Ambient singleton: heat from telemetry,
dormant, idle frost, the guard's flash freeze, held frost and thaw."""

from __future__ import annotations

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # before any Qt application exists

from conftest import require_qt  # noqa: E402

require_qt("PySide6.QtQuick")

from conftest import largest_step, sample_until, spin, wait_until  # noqa: E402


@pytest.fixture
def amb(gui):
    ambient = gui.singleton("Ambient")
    ambient.setProperty("forceLive", True)
    spin(20)
    return ambient


def _p(obj, name):
    return obj.property(name)


def _running(gui, amb, animation: str) -> bool:
    """Whether one of Ambient's animations runs (they are not readable as
    QObjects from Python, so ask QML)."""
    from PySide6.QtQml import QQmlExpression

    value, undefined = QQmlExpression(gui.engine.rootContext(), amb, f"{animation}.running").evaluate()
    assert not undefined, animation
    return bool(value)


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
    # Synchronously after the frame the ease has started from where heat was.
    assert _running(gui, amb, "heatEase") is True
    assert _p(amb, "heat") == pytest.approx(2 / 40)
    heats = sample_until(lambda: _p(amb, "heat"),
                         lambda: _p(amb, "heat") == pytest.approx(35 / 40))
    assert all(b >= a for a, b in zip(heats, heats[1:])), heats       # rises, never back


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
    # Every value the overlay was given (each animation tick notifies).
    seen: list[float] = []
    amb.frostAmountChanged.connect(lambda: seen.append(_p(amb, "frostAmount")))
    d.set_state(guard=True)
    assert _p(amb, "guardPhase") == "sweep"
    assert wait_until(lambda: not _running(gui, amb, "sweepAnim"))
    peak = seen.index(max(seen))
    assert max(seen) == pytest.approx(_p(amb, "peakAmount"))        # flashed to the peak
    assert all(b >= a for a, b in zip(seen[:peak], seen[1:peak + 1]))  # up, then settles
    assert _p(amb, "guardPhase") == "held"
    assert _p(amb, "frostAmount") == pytest.approx(_p(amb, "heldAmount"))
    d.set_state(cpu_temp=60.0, gpu_temp=55.0, guard=False)
    assert _p(amb, "guardPhase") == "thaw"
    thaw = sample_until(lambda: _p(amb, "frostAmount"), lambda: _p(amb, "guardPhase") == "none")
    idle = _p(amb, "idleFrost")
    assert any(idle + 0.02 < v < _p(amb, "heldAmount") - 0.02 for v in thaw)   # it eased
    assert all(b <= a + 0.005 for a, b in zip(thaw, thaw[1:])), thaw           # downhill
    assert _p(amb, "frostAmount") == pytest.approx(idle)
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


# -- the thaw follows a moving target (no pop at its end) --------------------

# Largest change allowed between two consecutive samples of a thaw. The
# thaw's own slope is about 0.3/s, so even a 100 ms stall on a slow runner
# stays well under this; the old pop to the dormant frost was 0.34.
STEP = 0.06


def _frost(amb) -> float:
    return _p(amb, "frostAmount")


def _hold(gui, amb, **temps) -> None:
    gui.daemon.set_state(cpu_temp=90.0, gpu_temp=80.0, **temps)
    gui.daemon.set_state(guard=True)
    assert wait_until(lambda: _p(amb, "guardPhase") == "held"
                      and not _running(gui, amb, "sweepAnim"))
    assert _frost(amb) == pytest.approx(_p(amb, "heldAmount"))


def _thaw_to_the_end(amb) -> list[float]:
    """Samples from now until the phase is "none", plus a few after it."""
    samples = sample_until(lambda: _frost(amb), lambda: _p(amb, "guardPhase") == "none")
    for _ in range(5):
        spin(10)
        samples.append(_frost(amb))
    return samples


def test_disconnect_while_held_thaws_into_the_dormant_frost(gui, amb):
    _hold(gui, amb)
    before = _frost(amb)
    gui.daemon.set_state(connected=False)      # guard and dormant flip together
    assert _p(amb, "guardPhase") == "thaw"
    assert _frost(amb) == pytest.approx(before)
    samples = _thaw_to_the_end(amb)
    assert largest_step(samples) < STEP, samples
    assert _frost(amb) == pytest.approx(_p(amb, "dormantFrost"), abs=1e-3)
    assert gui.messages == []


def test_target_change_mid_thaw_ends_on_the_new_target(gui, amb):
    _hold(gui, amb)
    gui.daemon.set_state(cpu_temp=60.0, gpu_temp=55.0, guard=False)
    assert wait_until(lambda: _p(amb, "thawProgress") > 0.3)
    gui.daemon.set_state(cpu_temp=40.0, gpu_temp=38.0)      # colder: more idle frost
    samples = _thaw_to_the_end(amb)
    assert largest_step(samples) < STEP, samples
    assert _frost(amb) == pytest.approx(_p(amb, "idleMax"), abs=1e-3)
    assert gui.messages == []


def test_reengage_mid_thaw_returns_to_held(gui, amb):
    _hold(gui, amb)
    gui.daemon.set_state(cpu_temp=60.0, gpu_temp=55.0, guard=False)
    assert wait_until(lambda: _p(amb, "thawProgress") > 0.3)
    before = _frost(amb)
    gui.daemon.set_state(cpu_temp=90.0, gpu_temp=80.0, guard=True)
    assert _p(amb, "guardPhase") == "sweep"
    assert _frost(amb) == pytest.approx(before, abs=1e-3)     # no jump at the turn
    assert wait_until(lambda: _p(amb, "guardPhase") == "held"
                      and not _running(gui, amb, "sweepAnim"))
    assert _frost(amb) == pytest.approx(_p(amb, "heldAmount"))
    assert _running(gui, amb, "thawAnim") is False
    assert gui.messages == []


def test_release_mid_sweep_completes_the_thaw(gui, amb):
    d = gui.daemon
    d.set_state(cpu_temp=90.0, gpu_temp=80.0)
    assert wait_until(lambda: _p(amb, "heat") == pytest.approx(_p(amb, "heatTarget")))
    d.set_state(guard=True)
    assert wait_until(lambda: _frost(amb) > 0.2)
    assert _p(amb, "guardPhase") == "sweep"
    before = _frost(amb)
    d.set_state(guard=False)
    assert _p(amb, "guardPhase") == "thaw"
    assert _frost(amb) == pytest.approx(before, abs=1e-3)
    samples = _thaw_to_the_end(amb)
    assert largest_step(samples) < STEP, samples
    assert _running(gui, amb, "sweepAnim") is False
    assert _frost(amb) == pytest.approx(_p(amb, "idleFrost"), abs=1e-3)
    assert gui.messages == []


def test_reconnect_with_a_stale_guard_does_not_freeze(gui, amb):
    """cryod restarts while the guard was on: the reconnect alone must not
    start a flash freeze; the first fresh frame decides."""
    d = gui.daemon
    _hold(gui, amb)
    d.set_state(connected=False)
    assert d.guard is False and _p(amb, "guard") is False
    assert d.cpuTemp == pytest.approx(90.0)                 # the stale reading stays
    assert wait_until(lambda: _p(amb, "guardPhase") == "none")
    d._set_connected(True)                                  # connected, no frame yet
    assert d.connected is True and d.guard is False
    spin(50)
    assert _p(amb, "guard") is False and _p(amb, "guardPhase") == "none"
    d.feed({**d.build_frame(), "guard": False, "cpu_temp": 60.0})
    assert _p(amb, "guard") is False and _p(amb, "guardPhase") == "none"
    assert gui.messages == []
