"""Engine logic tests — pure state machines, no hardware.

Engine.__init__ touches sysfs/USB/NVML, so guard tests build a bare
instance via __new__ with a stub thermal controller.
"""

from types import SimpleNamespace

from cryo.daemon.engine import Engine, interpolate


# -- interpolate -----------------------------------------------------------

CURVE = [[40, 0], [60, 30], [80, 70], [90, 100]]


def test_interpolate_empty_curve_is_zero():
    assert interpolate([], 70) == 0


def test_interpolate_clamps_below_first_point():
    assert interpolate(CURVE, 20) == 0


def test_interpolate_clamps_above_last_point():
    assert interpolate(CURVE, 105) == 100


def test_interpolate_hits_points_exactly():
    assert interpolate(CURVE, 60) == 30
    assert interpolate(CURVE, 90) == 100


def test_interpolate_midpoint_is_linear():
    assert interpolate(CURVE, 70) == 50  # halfway 60->80 = halfway 30->70


def test_interpolate_duplicate_temp_points():
    assert interpolate([[70, 20], [70, 80]], 70) in (20, 80)  # no ZeroDivisionError


# -- thermal guard ---------------------------------------------------------

class StubThermal:
    boost_ok = True

    def __init__(self):
        self.fans = [SimpleNamespace(group="cpu"), SimpleNamespace(group="gpu")]
        self.boosts = {"cpu": 20, "gpu": 30}
        self.writes: list[tuple[str, int]] = []

    def boost(self, fan):
        return self.boosts[fan.group]

    def set_boost(self, group, value):
        self.writes.append((group, value))
        self.boosts[group] = value


def make_engine(guard_cfg=None):
    engine = Engine.__new__(Engine)
    engine.thermal = StubThermal()
    engine.config = {
        "thermal_guard": {
            "enabled": True,
            "cpu_trip": 95,
            "gpu_trip": 87,
            "boost": 100,
            "release_c": 8,
            "min_hold_s": 0,
            **(guard_cfg or {}),
        }
    }
    engine._guard_active = False
    engine._guard_engaged_at = 0.0
    engine._guard_saved_boosts = {}
    engine._curve_anchor = {}
    engine._curve_boost = {}
    return engine


def test_guard_engages_on_cpu_trip_and_saves_boosts():
    engine = make_engine()
    engine._apply_guard({"cpu_temp": 96, "gpu_temp": 60})
    assert engine._guard_active
    assert engine._guard_saved_boosts == {"cpu": 20, "gpu": 30}
    assert engine.thermal.boosts == {"cpu": 100, "gpu": 100}


def test_guard_stays_put_below_trip():
    engine = make_engine()
    engine._apply_guard({"cpu_temp": 94, "gpu_temp": 86})
    assert not engine._guard_active
    assert engine.thermal.writes == []


def test_guard_releases_below_release_band_and_restores():
    engine = make_engine()
    engine._apply_guard({"cpu_temp": 96, "gpu_temp": 60})
    # Cooled, but still inside the release band -> hold
    engine._apply_guard({"cpu_temp": 90, "gpu_temp": 60})
    assert engine._guard_active
    # Both clear of trip - release_c -> restore saved boosts
    engine._apply_guard({"cpu_temp": 86, "gpu_temp": 60})
    assert not engine._guard_active
    assert engine.thermal.boosts == {"cpu": 20, "gpu": 30}


def test_guard_honors_min_hold():
    engine = make_engine({"min_hold_s": 3600})
    engine._apply_guard({"cpu_temp": 96, "gpu_temp": 60})
    engine._apply_guard({"cpu_temp": 50, "gpu_temp": 40})
    assert engine._guard_active  # cooled instantly, but the hold pins it


def test_guard_disabled_never_actuates():
    engine = make_engine({"enabled": False})
    engine._apply_guard({"cpu_temp": 120, "gpu_temp": 120})
    assert not engine._guard_active
    assert engine.thermal.writes == []
