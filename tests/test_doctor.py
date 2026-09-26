"""cryoctl doctor's verdict + the curve-point parser (0.4.0)."""

import pytest

from cryo.cli import parse_curve_points, verdict

FULL = {
    "hwmon": True, "profiles": True, "fan_boost": True, "elc": True,
    "nvml": True, "mains": True, "turbo": True, "cpu_cap": True,
}


def test_everything_present_is_supported():
    assert verdict(FULL) == ("supported", [])


def test_missing_hwmon_is_unsupported_regardless_of_the_rest():
    level, reasons = verdict({**FULL, "hwmon": False})
    assert level == "unsupported"
    assert any("hwmon" in r for r in reasons)


def test_unreadable_profiles_is_unsupported():
    level, reasons = verdict({**FULL, "profiles": False})
    assert level == "unsupported"
    assert any("platform profiles" in r for r in reasons)


def test_missing_optional_features_are_partial_with_reasons():
    level, reasons = verdict({**FULL, "elc": False, "nvml": False, "cpu_cap": False})
    assert level == "partial"
    assert len(reasons) == 3
    assert any("lighting" in r for r in reasons)
    assert any("game detection" in r for r in reasons)
    assert any("performance cap" in r for r in reasons)


def test_parse_curve_points():
    assert parse_curve_points(["45:0", "60:15", "95:100"]) == [[45, 0], [60, 15], [95, 100]]
    with pytest.raises(SystemExit):
        parse_curve_points(["45-0"])
