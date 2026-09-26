"""Limited mode (0.4.0): a machine without the driver's hwmon and/or
platform profiles still gets a ThermalController — missing parts are
reported, not fatal. sysfs is faked by pointing paths at tmp_path."""

from pathlib import Path

from cryo import paths
from cryo.hw.thermal import ThermalController


def _fake_sysfs(monkeypatch, tmp_path: Path, hwmon: bool, profiles: bool):
    if hwmon:
        hw = tmp_path / "hwmon0"
        hw.mkdir()
        (hw / "name").write_text("alienware_wmi\n")
        (hw / "fan1_label").write_text("CPU Fan\n")
        (hw / "fan1_input").write_text("1200\n")
        (hw / "fan1_boost").write_text("0\n")
        (hw / "temp1_label").write_text("CPU\n")
        (hw / "temp1_input").write_text("55000\n")
        monkeypatch.setattr(paths, "find_hwmon", lambda name="alienware_wmi": hw)
    else:
        monkeypatch.setattr(paths, "find_hwmon", lambda name="alienware_wmi": None)
    prof = tmp_path / "profile"
    choices = tmp_path / "choices"
    if profiles:
        prof.write_text("balanced\n")
        choices.write_text("quiet balanced balanced-performance performance custom\n")
    monkeypatch.setattr(paths, "find_platform_profile", lambda driver="alienware-wmi": (prof, choices))
    monkeypatch.setattr(paths, "find_ac_supply", lambda: None)
    monkeypatch.setattr(paths, "find_turbo_control", lambda: None)
    monkeypatch.setattr(paths, "find_cpu_cap", lambda: None)
    monkeypatch.setattr(paths, "cpu_max_khz", lambda: 5800000)
    monkeypatch.setattr(paths, "dmi_model", lambda: "Test Box")


def test_full_machine_reports_nothing_missing(monkeypatch, tmp_path):
    _fake_sysfs(monkeypatch, tmp_path, hwmon=True, profiles=True)
    tc = ThermalController()
    assert tc.missing == []
    assert tc.has_thermals and tc.has_profiles and tc.has_gmode
    assert tc.profile() == "balanced"
    assert tc.temp("cpu") == 55.0
    caps = tc.capabilities()
    assert caps["thermals"] is True and "gmode" in caps["profiles"]
    assert caps["cpu_max_mhz"] == 5800


def test_no_hwmon_degrades_thermals_only(monkeypatch, tmp_path):
    _fake_sysfs(monkeypatch, tmp_path, hwmon=False, profiles=True)
    tc = ThermalController()
    assert len(tc.missing) == 1 and "hwmon" in tc.missing[0]
    assert not tc.has_thermals and tc.has_profiles
    assert tc.fans == [] and tc.boost_ok is False
    assert tc.temp("cpu") is None
    assert tc.profile() == "balanced"
    t = tc.telemetry()
    assert t["fans"] == [] and t["cpu_temp"] is None and t["profile"] == "balanced"


def test_no_profiles_degrades_power_modes_only(monkeypatch, tmp_path):
    _fake_sysfs(monkeypatch, tmp_path, hwmon=True, profiles=False)
    tc = ThermalController()
    assert len(tc.missing) == 1 and "profiles" in tc.missing[0]
    assert tc.has_thermals and not tc.has_profiles
    assert tc.profile() is None
    assert tc.capabilities()["profiles"] == []
    try:
        tc.set_profile("balanced")
    except RuntimeError as exc:
        assert "no platform profiles" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("set_profile should refuse without profiles")


def test_neither_still_constructs(monkeypatch, tmp_path):
    _fake_sysfs(monkeypatch, tmp_path, hwmon=False, profiles=False)
    tc = ThermalController()
    assert len(tc.missing) == 2
    assert tc.telemetry()["profile"] is None
