"""Demo mode: DemoDaemon speaks exactly the daemon's telemetry dialect and
applies every GUI command locally. No sockets, no hardware."""

import pytest

pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
pytest.importorskip("PySide6.QtNetwork", exc_type=ImportError)

from types import SimpleNamespace  # noqa: E402

from cryo.daemon import config as config_mod  # noqa: E402
from cryo.daemon import engine as engine_mod  # noqa: E402
from cryo.hw.thermal import ThermalController  # noqa: E402


@pytest.fixture
def demo(qapp):
    from cryo.gui.demo import DemoDaemon

    d = DemoDaemon(scenario="idle", autostart=False)
    yield d
    d.deleteLater()


# -- the frame matches what a real cryod tick broadcasts --------------------

class StubThermal:
    """Just enough ThermalController for Engine.__init__ and tick(); the
    telemetry/capabilities dicts come from the real methods."""

    telemetry = ThermalController.telemetry
    capabilities = ThermalController.capabilities

    has_thermals = True
    has_profiles = True
    has_gmode = True
    boost_ok = True
    missing: list = []
    turbo_control = ("x", False)
    ac_path = "x"
    cap_path = "x"
    cpu_max_mhz = 5800
    profile_to_kernel = {"balanced": "balanced", "gmode": "performance", "custom": "custom"}

    def __init__(self):
        self.fans = [SimpleNamespace(index=1, label="CPU Fan", group="cpu"),
                     SimpleNamespace(index=2, label="GPU Fan", group="gpu")]

    def profile_choices(self):
        return list(self.profile_to_kernel)

    def profile(self):
        return "balanced"

    def turbo(self):
        return True

    def cpu_cap(self):
        return 100

    def set_cpu_cap(self, pct):
        pass

    def ac_online(self):
        return True

    def temp(self, which):
        return 50.0

    def rpm(self, fan):
        return 2000

    def boost(self, fan):
        return 0

    def set_boost(self, group, value):
        pass


class StubGpu:
    def available(self):
        return True

    def maybe_reinit(self):
        return False

    def utilization(self):
        return 12

    def memory(self):
        return (1200, 12282)

    def power_w(self):
        return 11.0

    def clock_mhz(self):
        return 300

    def snapshot(self):
        return ([("firefox", 300)], None)

    def game_candidates(self, ignore, min_vram_mb, procs=None):
        return []


class StubLights:
    def available(self):
        return True


@pytest.fixture
def engine_frame(monkeypatch):
    monkeypatch.setattr(engine_mod, "ThermalController", StubThermal)
    monkeypatch.setattr(engine_mod, "GpuSense", StubGpu)
    monkeypatch.setattr(engine_mod, "Effects", StubLights)
    monkeypatch.setattr(engine_mod, "Keyboard", StubLights)
    config = config_mod.merged({"lighting": {"restore": False}})
    engine = engine_mod.Engine(config, state={})
    # server.broadcast() prefixes every frame with the event name
    return {"event": "telemetry", **engine.tick()}


def test_frame_keys_match_the_engine(demo, engine_frame):
    frame = demo.build_frame()
    assert set(frame) == set(engine_frame)
    assert set(frame["capabilities"]) == set(engine_frame["capabilities"])
    assert set(frame["lighting"]) == set(engine_frame["lighting"])
    assert set(frame["fans"][0]) == set(engine_frame["fans"][0])
    assert set(frame["vram_procs"][0]) == set(engine_frame["vram_procs"][0])


def test_frame_value_types_match_the_engine(demo, engine_frame):
    frame = demo.build_frame()
    for key, value in engine_frame.items():
        if value is not None and frame[key] is not None:
            assert isinstance(frame[key], type(value)) or (
                isinstance(value, float) and isinstance(frame[key], (int, float))
            ), key


# -- no daemon involved ------------------------------------------------------

def test_demo_never_opens_a_socket(demo):
    assert demo.demo is True
    assert demo.connected is True
    assert not hasattr(demo, "_stream") and not hasattr(demo, "_cmd")


def test_the_real_bridge_is_not_a_demo(qapp):
    from cryo.gui.bridge import Daemon

    assert Daemon.DEMO is False


# -- commands mutate the demo's state ----------------------------------------

def test_profile_commands(demo):
    demo.setProfile("cool")
    assert demo.profile == "cool"
    demo.toggleGmode()
    assert demo.profile == "gmode"
    demo.toggleGmode()
    assert demo.profile == "balanced"           # auto.after_game


def test_unknown_profile_is_reported(demo):
    errors = []
    demo.errorOccurred.connect(errors.append)
    demo.setProfile("warp")
    assert errors and "warp" in errors[0]
    assert demo.profile == "balanced"


def test_manual_boost_latches_curves_off(demo):
    assert demo.curvesEnabled is True
    demo.setBoost("cpu", 40)
    assert demo.curvesEnabled is False
    assert [f["boost"] for f in demo.fans if f["group"] == "cpu"] == [40]
    demo.setCurvesEnabled(True)
    assert demo.curvesEnabled is True


def test_turbo_and_lighting(demo):
    demo.setTurbo(False)
    assert demo.turbo is False
    demo.setLighting("static", "#ff2d55")
    assert demo.lightEffect == "static"
    assert demo.lightColor == "#FF2D55"
    demo.setBrightness(30)
    assert demo.lightBrightness == 30


def test_config_patches_merge_and_publish(demo):
    seen = []
    demo.configChanged.connect(lambda: seen.append(True))
    demo.setFanCurve("gpu", [[40, 0], [70, 50], [90, 100]])
    demo.setCurveTuning(4.0, 6)
    demo.setGuard(90, 86, 12)
    demo.setAutoEnabled(False)
    assert demo.gpuCurve == [[40, 0], [70, 50], [90, 100]]
    assert demo.cpuCurve == config_mod.DEFAULTS["fan_curves"]["cpu"]   # untouched
    assert (demo.curveHysteresis, demo.curveMinStep) == (4.0, 6)
    assert (demo.guardCpuTrip, demo.guardGpuTrip, demo.guardRelease) == (90, 86, 12)
    assert demo.autoEnabled is False
    assert len(seen) == 4


def test_invalid_patch_is_rejected_like_the_daemon(demo):
    errors = []
    demo.errorOccurred.connect(errors.append)
    demo.setFanCurve("cpu", [[40, 0]])
    assert errors and "2-8 points" in errors[0]
    assert demo.cpuCurve == config_mod.DEFAULTS["fan_curves"]["cpu"]


def test_cpu_cap_is_per_profile(demo):
    demo.setProfile("cool")
    demo.setCpuCap(80)
    assert demo.cpuCapProfiles == {"cool": 80}
    assert demo.cpuCap == 80
    demo.setProfile("balanced")
    assert demo.cpuCap == 100
    demo.setProfile("cool")
    demo.setCpuCapEnabled(False)
    assert demo.cpuCapEnabled is False
    assert demo.cpuCap == 100


def test_get_config_publishes(demo):
    seen = []
    demo.configChanged.connect(lambda: seen.append(True))
    demo.refreshConfig()
    assert seen and demo.guardCpuTrip == config_mod.DEFAULTS["thermal_guard"]["cpu_trip"]


# -- scripting API -----------------------------------------------------------

def test_set_state_pins_values(demo):
    connected = []
    demo.connectedChanged.connect(lambda: connected.append(demo.connected))
    demo.set_state(cpu_temp=82, gpu_temp=71, guard=True, gaming=True, ac=False,
                   profile="cool", fan_rpm=3200)
    assert (demo.cpuTemp, demo.gpuTemp) == (82, 71)
    assert demo.guard and demo.gaming and not demo.ac
    assert demo.profile == "cool"
    assert {f["rpm"] for f in demo.fans} == {3200}
    demo.step()                                  # pinned: the timeline leaves it
    assert demo.cpuTemp == 82 and demo.guard
    demo.set_state(connected=False)
    assert connected == [False]
    demo.set_state(connected=True)
    assert connected == [False, True]


def test_set_state_rejects_unknown_keys(demo):
    with pytest.raises(KeyError):
        demo.set_state(cpu_tmp=80)


def test_feed_pushes_an_exact_frame(demo):
    frame = {**demo.build_frame(), "cpu_temp": 77.5, "profile": "quiet"}
    demo.feed(frame)
    assert demo.cpuTemp == 77.5 and demo.profile == "quiet"
    assert demo.cpuHistory[-1] == 77.5


def test_pause_and_resume(demo):
    assert not demo.running
    demo.resume()
    assert demo.running
    demo.pause()
    assert not demo.running


def test_guard_scenario_trips_and_releases(demo):
    demo.set_scenario("guard")
    seen = []
    for _ in range(80):
        demo.step()
        seen.append(demo.guard)
    assert True in seen
    first = seen.index(True)
    assert False in seen[first:], "guard never released"
    assert demo.cpuPeak >= config_mod.DEFAULTS["thermal_guard"]["cpu_trip"]


def test_gaming_scenario_runs_the_auto_profile(demo):
    demo.set_scenario("gaming")
    demo.step()
    assert demo.gaming and demo.profile == "gmode"
    for _ in range(55):
        demo.step()
    assert not demo.gaming and demo.profile == "balanced"


def test_unknown_scenario(qapp):
    from cryo.gui.demo import DemoDaemon

    with pytest.raises(ValueError):
        DemoDaemon(scenario="lava", autostart=False)


def test_reset_clears_history_and_pins(demo):
    demo.set_state(cpu_temp=90)
    demo.reset()
    assert demo.cpuTemp < 50
    assert len(demo.cpuHistory) == 1
    assert demo.cpuPeak < 50
