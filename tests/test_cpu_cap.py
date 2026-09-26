"""Per-profile CPU performance cap (0.4.0) — engine logic with a stub
thermal controller, no sysfs."""

from types import SimpleNamespace

from cryo.daemon import config as config_mod
from cryo.daemon.engine import Engine


class StubThermal:
    boost_ok = True

    def __init__(self, has_cap=True, profile="performance"):
        self.fans = []
        self._cap = 100 if has_cap else None
        self._profile = profile
        self.cap_writes: list[int] = []
        self.profile_writes: list[str] = []
        self.profile_to_kernel = {"performance": "balanced-performance", "gmode": "performance"}

    def cpu_cap(self):
        return self._cap

    def set_cpu_cap(self, pct):
        self.cap_writes.append(pct)
        self._cap = pct

    def profile(self):
        return self._profile

    def set_profile(self, name):
        self.profile_writes.append(name)
        self._profile = name


def make_engine(overrides=None, has_cap=True, profile="performance"):
    engine = Engine.__new__(Engine)
    engine.config = config_mod.merged(overrides or {})
    engine.thermal = StubThermal(has_cap=has_cap, profile=profile)
    engine.capabilities = {"cpu_cap": has_cap}
    engine._curve_anchor = {}
    engine._curve_boost = {}
    return engine


def test_no_cap_control_means_no_writes():
    engine = make_engine({"cpu_cap": {"profiles": {"performance": 90}}}, has_cap=False)
    assert engine.apply_cpu_cap() is None
    assert engine.thermal.cap_writes == []


def test_profile_without_entry_runs_uncapped():
    engine = make_engine({"cpu_cap": {"profiles": {"gmode": 95}}})
    assert engine.cpu_cap_target("performance") == 100
    engine.apply_cpu_cap()          # already 100 → nothing written
    assert engine.thermal.cap_writes == []


def test_set_profile_applies_that_profiles_cap():
    engine = make_engine({"cpu_cap": {"profiles": {"performance": 90, "gmode": 100}}})
    engine.set_profile("performance")
    assert engine.thermal.cap_writes == [90]
    engine.set_profile("gmode")
    assert engine.thermal.cap_writes == [90, 100]
    engine.set_profile("gmode")      # unchanged → no extra write
    assert engine.thermal.cap_writes == [90, 100]


def test_disabled_feature_leaves_the_knob_alone():
    engine = make_engine({"cpu_cap": {"enabled": False, "profiles": {"performance": 90}}})
    assert engine.cpu_cap_target("performance") is None
    engine.set_profile("performance")
    assert engine.thermal.cap_writes == []


def test_cap_write_failure_is_logged_not_raised():
    engine = make_engine({"cpu_cap": {"profiles": {"performance": 80}}})

    def boom(pct):
        raise OSError("read-only")

    engine.thermal.set_cpu_cap = boom
    assert engine.apply_cpu_cap("performance") == 80
