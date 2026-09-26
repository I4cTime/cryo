"""set_config patch validation (0.4.0): the editors' inputs are bounded
before anything reaches sysfs."""

import pytest

from cryo.daemon import config as config_mod
from cryo.daemon.config import PatchError, validate_curve, validate_patch


def test_defaults_include_cpu_cap_block():
    cfg = config_mod.merged({})
    assert cfg["cpu_cap"] == {"enabled": True, "profiles": {}}


def test_valid_curve_is_normalized_to_ints():
    assert validate_curve([[45.0, 0], [60, 15.0], [95, 100]], "c") == [[45, 0], [60, 15], [95, 100]]


@pytest.mark.parametrize(
    "points",
    [
        [[45, 0]],                                   # too few
        [[t, 0] for t in range(0, 90, 10)],          # 9 points
        [[60, 10], [50, 20]],                        # temps must rise
        [[50, 40], [60, 20]],                        # boosts must not fall
        [[50, 0], [200, 100]],                       # temp out of range
        [[50, 0], [60, 150]],                        # boost out of range
        [[50, 0], [60]],                             # malformed point
        "45:0 60:15",                                # not a list
    ],
)
def test_bad_curves_are_rejected(points):
    with pytest.raises(PatchError):
        validate_curve(points, "fan_curves.cpu")


def test_patch_bounds_guard_and_tuning():
    ok = validate_patch({
        "fan_curves": {"hysteresis_c": 2, "min_step": 5},
        "thermal_guard": {"cpu_trip": 90, "gpu_trip": 85, "release_c": 8, "min_hold_s": 20, "boost": 100},
    })
    assert ok["fan_curves"]["hysteresis_c"] == 2.0
    assert ok["thermal_guard"]["cpu_trip"] == 90
    for bad in (
        {"fan_curves": {"hysteresis_c": 40}},
        {"fan_curves": {"min_step": 0}},
        {"thermal_guard": {"cpu_trip": 30}},
        {"thermal_guard": {"release_c": 0}},
        {"thermal_guard": {"enabled": "yes"}},
        {"fan_curves": "nope"},
    ):
        with pytest.raises(PatchError):
            validate_patch(bad)


def test_patch_cpu_cap_profiles_are_lowercased_and_bounded():
    ok = validate_patch({"cpu_cap": {"enabled": False, "profiles": {"GMode": 90, "quiet": 70.0}}})
    assert ok["cpu_cap"] == {"enabled": False, "profiles": {"gmode": 90, "quiet": 70}}
    with pytest.raises(PatchError):
        validate_patch({"cpu_cap": {"profiles": {"gmode": 5}}})
    with pytest.raises(PatchError):
        validate_patch({"cpu_cap": {"profiles": ["gmode", 90]}})


def test_unknown_keys_pass_through():
    assert validate_patch({"socket_group": "wheel", "poll_interval": 2})["socket_group"] == "wheel"
