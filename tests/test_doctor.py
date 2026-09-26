"""cryoctl doctor's verdict + the curve-point parser (0.4.0)."""

import pytest

from cryo.cli import parse_curve_points, verdict

FULL = {
    "hwmon": True, "profiles": True, "fan_boost": True, "elc": True,
    "nvml": True, "mains": True, "turbo": True, "cpu_cap": True,
}


def test_everything_present_is_supported():
    assert verdict(FULL) == ("supported", [])


def test_missing_hwmon_is_limited_when_extras_remain():
    level, reasons = verdict({**FULL, "hwmon": False})
    assert level == "limited"
    assert any("hwmon" in r for r in reasons)


def test_unreadable_profiles_is_limited():
    level, reasons = verdict({**FULL, "profiles": False})
    assert level == "limited"
    assert any("platform profiles" in r for r in reasons)


def test_nothing_to_drive_is_unsupported():
    nothing = {k: False for k in FULL}
    level, reasons = verdict(nothing)
    assert level == "unsupported"
    assert any("nothing" in r or "fall back" in r for r in reasons)
    # The 2011 Aurora from issue #9: no hwmon/profiles/ELC, but NVML + turbo → limited.
    aurora = {**nothing, "nvml": True, "turbo": True, "cpu_cap": True}
    assert verdict(aurora)[0] == "limited"


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
