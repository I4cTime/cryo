"""Demo mode: the real GUI against a scripted stand-in for cryod.

`DemoDaemon` is the GUI bridge (`cryo.gui.bridge.Daemon`) with the socket
layer swapped out. It never opens a socket: it reports itself connected,
simulates thermals, fans and VRAM on a scenario timeline at 1 Hz, and
applies every command locally so each control in the window responds.

Its telemetry frames carry exactly the keys a real cryod tick broadcasts
(tests/test_demo.py pins them against the engine), so the GUI cannot tell
the difference.

Scripting API (tests, tools/tour.py):

- `feed(frame)`        push one exact telemetry frame
- `set_state(**kw)`    pin simulated values (cpu_temp=82, guard=True,
                       gaming=True, connected=False, ac=False,
                       profile="cool", fan_rpm=3200, ...) and push a frame
- `clear_state()`      unpin everything (the timeline drives it again)
- `pause()` / `resume()` / `step()`   control the timeline
- `set_scenario(name)` switch scenario ("idle", "load", "guard", "gaming",
                       "cycle")
- `reset()`            back to the cold idle start, histories and peaks cleared
"""

from __future__ import annotations

import copy
import math

from PySide6.QtCore import QObject, QTimer

from cryo import __version__
from cryo.daemon import config as config_mod
from cryo.gui.bridge import Daemon

TICK_MS = 1000

DEMO_CAPABILITIES: dict = {
    "model": "Alienware m18 R2",
    "thermals": True,
    "profiles": ["cool", "quiet", "balanced", "performance", "gmode", "custom"],
    "gmode": True,
    "fan_boost": True,
    "fan_groups": ["cpu", "gpu"],
    "turbo": True,
    "ac_supply": True,
    "cpu_cap": True,
    "cpu_max_mhz": 5800,
    "lighting": True,
    "lighting_elc": True,
    "lighting_keyboard": True,
    "game_detection": True,
    "version": __version__,
}

DEMO_FANS = [
    {"index": 1, "label": "CPU Fan", "group": "cpu"},
    {"index": 2, "label": "GPU Fan", "group": "gpu"},
]

VRAM_TOTAL_MB = 12282
MAX_RPM = 5600

# Firmware fan response per mode (custom hands the fans to Cryo's curves).
PROFILE_FAN_FACTOR = {
    "cool": 1.25, "quiet": 0.7, "balanced": 1.0, "performance": 1.15,
    "low-power": 0.6, "custom": 0.0,
}

# Keys set_state() may pin. Everything else in a frame is derived.
STATE_KEYS = frozenset({
    "profile", "turbo", "ac", "cpu_temp", "gpu_temp", "gpu_util",
    "vram_used_mb", "gaming", "guard", "fan_rpm", "cpu_rpm", "gpu_rpm",
    "connected",
})


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, f))


def _interpolate(curve: list, temp: float) -> int:
    """Same linear [temp, boost] interpolation the engine runs."""
    if not curve:
        return 0
    if temp <= curve[0][0]:
        return int(curve[0][1])
    for (t1, b1), (t2, b2) in zip(curve, curve[1:]):
        if t1 <= temp <= t2:
            return int(b2) if t2 == t1 else int(b1 + (b2 - b1) * (temp - t1) / (t2 - t1))
    return int(curve[-1][1])


# -- scenarios: seconds into the scenario -> targets the temps glide to --

def _idle(t: float) -> dict:
    return {
        "cpu_temp": 41 + 0.6 * math.sin(t / 7), "gpu_temp": 38 + 0.4 * math.sin(t / 11),
        "gpu_util": 3, "vram_used_mb": 1100, "gaming": False,
    }


def _load(t: float) -> dict:
    f = t / 25
    return {
        "cpu_temp": _lerp(46, 86, f), "gpu_temp": _lerp(41, 78, f),
        "gpu_util": 88, "vram_used_mb": int(_lerp(1400, 6200, f)), "gaming": False,
    }


def _guard(t: float) -> dict:
    # ramp past the trip, hold hot, then cool well under the release point
    if t < 15:
        f = t / 15
        return {"cpu_temp": _lerp(55, 93, f), "gpu_temp": _lerp(50, 86, f),
                "gpu_util": 95, "vram_used_mb": 7000, "gaming": False}
    if t < 45:
        return {"cpu_temp": 93, "gpu_temp": 86, "gpu_util": 95,
                "vram_used_mb": 7000, "gaming": False}
    f = (t - 45) / 30
    return {"cpu_temp": _lerp(93, 58, f), "gpu_temp": _lerp(86, 52, f),
            "gpu_util": int(_lerp(95, 10, f)), "vram_used_mb": int(_lerp(7000, 1600, f)),
            "gaming": False}


def _gaming(t: float) -> dict:
    if t < 50:
        return {"cpu_temp": 74 + math.sin(t / 3), "gpu_temp": 72 + 0.8 * math.sin(t / 5),
                "gpu_util": 96, "vram_used_mb": 9200, "gaming": True}
    return {"cpu_temp": 55, "gpu_temp": 50, "gpu_util": 6, "vram_used_mb": 1500,
            "gaming": False}


# name -> (length in seconds, targets(t)); every scenario loops
SCENARIOS: dict = {
    "idle": (60, _idle),
    "load": (60, _load),
    "guard": (80, _guard),
    "gaming": (60, _gaming),
}
CYCLE = [("idle", 30), ("load", 45), ("guard", 80), ("gaming", 60)]
SCENARIO_NAMES = (*SCENARIOS, "cycle")


def scenario_targets(name: str, t: float) -> dict:
    """Targets for second `t` of a scenario (loops)."""
    if name == "cycle":
        t %= sum(length for _, length in CYCLE)
        for part, length in CYCLE:
            if t < length:
                return SCENARIOS[part][1](t)
            t -= length
    length, fn = SCENARIOS[name]
    return fn(t % length)


class DemoDaemon(Daemon):
    """Daemon bridge with no sockets: a scripted, self-contained cryod."""

    DEMO = True

    def __init__(
        self,
        scenario: str = "cycle",
        parent: QObject | None = None,
        autostart: bool = True,
    ) -> None:
        if scenario not in SCENARIO_NAMES:
            raise ValueError(f"unknown scenario {scenario!r}; pick one of {SCENARIO_NAMES}")
        self._scenario = scenario
        super().__init__(parent)
        if autostart:
            self.resume()

    # -- transport replacement ---------------------------------------------

    def _setup_transport(self) -> None:
        self._overrides: dict = {}            # the "user config file"
        self._config = config_mod.merged(self._overrides)
        self._curves_latch: bool | None = None
        self._pinned: set[str] = set()
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self.step)
        self._init_sim()
        self._connected = True
        self._last_frame: dict = {}
        self._push()

    def _connect(self) -> None:  # pragma: no cover - nothing to connect to
        pass

    def _init_sim(self) -> None:
        start = scenario_targets(self._scenario, 0)
        self._sim: dict = {
            "profile": "balanced", "turbo": True, "ac": True,
            "cpu_temp": float(start["cpu_temp"]), "gpu_temp": float(start["gpu_temp"]),
            "gpu_util": int(start["gpu_util"]), "vram_used_mb": int(start["vram_used_mb"]),
            "gaming": False, "guard": False,
            "fan_rpm": None, "cpu_rpm": None, "gpu_rpm": None,
            "boost": {"cpu": 0, "gpu": 0},
            "lighting": dict(self._config["lighting"]["last"]),
        }
        self._peaks = {"cpu": 0.0, "gpu": 0.0, "vram": 0}
        self._guard_since: float | None = None
        self._guard_saved: dict = {}
        self._profile_before_game: str | None = None

    # -- public scripting API ----------------------------------------------

    @property
    def scenario(self) -> str:
        return self._scenario

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def pause(self) -> None:
        self._timer.stop()

    def resume(self) -> None:
        self._timer.start()

    def set_scenario(self, name: str) -> None:
        if name not in SCENARIO_NAMES:
            raise ValueError(f"unknown scenario {name!r}; pick one of {SCENARIO_NAMES}")
        self._scenario = name
        self._t = 0.0

    def reset(self) -> None:
        """Cold idle start: sim, pins, histories and peaks cleared; config kept."""
        self._pinned.clear()
        self._t = 0.0
        self._init_sim()
        self._cpu_history, self._gpu_history, self._vram_history = [], [], []
        self._vram_peak = 0
        self._set_connected(True)
        self._push()

    def feed(self, frame: dict) -> None:
        """Push one exact telemetry frame, as if cryod had broadcast it."""
        self._last_frame = frame
        self._apply_telemetry(frame)

    def set_state(self, **values) -> None:
        """Pin simulated values (the timeline leaves pinned keys alone) and
        push a frame built from them right away."""
        unknown = set(values) - STATE_KEYS
        if unknown:
            raise KeyError(f"unknown demo state {sorted(unknown)}; known: {sorted(STATE_KEYS)}")
        if "connected" in values:
            self._set_connected(bool(values.pop("connected")))
        for key, value in values.items():
            self._sim[key] = value
            self._pinned.add(key)
        if values or self._connected:
            self._push()

    def clear_state(self) -> None:
        self._pinned.clear()
        for key in ("fan_rpm", "cpu_rpm", "gpu_rpm"):
            self._sim[key] = None

    def build_frame(self) -> dict:
        """The telemetry frame the current simulated state broadcasts."""
        sim = self._sim
        cfg = self._config
        caps = DEMO_CAPABILITIES
        guard = bool(sim["guard"])
        boost = dict(sim["boost"])
        if guard:
            boost = {g: int(cfg["thermal_guard"]["boost"]) for g in boost}
        elif self._curves_on() and sim["profile"] == "custom":
            curves = cfg["fan_curves"]
            boost = {g: _interpolate(curves[g], sim[f"{g}_temp"]) for g in ("cpu", "gpu")}

        fans = []
        for i, fan in enumerate(DEMO_FANS):
            group = fan["group"]
            rpm = sim.get(f"{group}_rpm")
            if rpm is None:
                rpm = sim.get("fan_rpm")
            if rpm is None:
                rpm = self._firmware_rpm(sim["profile"], sim[f"{group}_temp"], boost[group], i)
            fans.append({**fan, "rpm": int(rpm), "boost": int(boost[group])})

        util = int(sim["gpu_util"])
        vram = int(sim["vram_used_mb"])
        for key, value in (("cpu", sim["cpu_temp"]), ("gpu", sim["gpu_temp"]), ("vram", vram)):
            self._peaks[key] = max(self._peaks[key], value)
        procs = [{"name": "Xwayland", "vram_mb": 412}, {"name": "firefox", "vram_mb": 338}]
        if sim["gaming"]:
            procs.insert(0, {"name": "Cyberpunk2077.exe", "vram_mb": max(0, vram - 900)})
        cap_cfg = cfg.get("cpu_cap", {})
        cpu_cap = (
            int(cap_cfg.get("profiles", {}).get(sim["profile"], 100))
            if cap_cfg.get("enabled", True) else 100
        )
        return {
            "event": "telemetry",
            # ThermalController.telemetry()
            "profile": sim["profile"],
            "turbo": bool(sim["turbo"]),
            "cpu_cap": cpu_cap,
            "ac": bool(sim["ac"]),
            "cpu_temp": round(float(sim["cpu_temp"]), 1),
            "gpu_temp": round(float(sim["gpu_temp"]), 1),
            "fans": fans,
            # Engine.tick()
            "gpu_util": util,
            "vram_used_mb": vram,
            "vram_total_mb": VRAM_TOTAL_MB,
            "gpu_power_w": round(8.5 + util * 1.55, 1),
            "gpu_clock_mhz": int(210 + util * 19),
            "vram_procs": procs[:5],
            "game_procs": ["Cyberpunk2077.exe"] if sim["gaming"] else [],
            "gaming": bool(sim["gaming"]),
            "cpu_peak": round(float(self._peaks["cpu"]), 1),
            "gpu_peak": round(float(self._peaks["gpu"]), 1),
            "vram_peak_mb": self._peaks["vram"] or None,
            "guard": guard,
            "curves_enabled": self._curves_on(),
            "auto_enabled": bool(cfg["auto"]["enabled"]),
            "cpu_cap_enabled": bool(cap_cfg.get("enabled", True)),
            "lighting": dict(sim["lighting"]),
            "capabilities": caps,
        }

    # -- timeline ----------------------------------------------------------

    def step(self) -> None:
        """Advance the simulation one tick (1 s) and broadcast."""
        self._t += TICK_MS / 1000
        targets = scenario_targets(self._scenario, self._t)
        sim = self._sim
        for key in ("cpu_temp", "gpu_temp"):
            if key not in self._pinned:
                sim[key] += (targets[key] - sim[key]) * 0.35
        for key in ("gpu_util", "vram_used_mb"):
            if key not in self._pinned:
                sim[key] = int(targets[key])
        if "gaming" not in self._pinned and targets["gaming"] != sim["gaming"]:
            self._game_transition(bool(targets["gaming"]))
        if "guard" not in self._pinned:
            self._run_guard()
        if self._connected:
            self._push()

    def _game_transition(self, gaming: bool) -> None:
        sim = self._sim
        auto = self._config["auto"]
        sim["gaming"] = gaming
        if "profile" in self._pinned or not auto["enabled"]:
            return
        if gaming:
            self._profile_before_game = sim["profile"]
            sim["profile"] = auto["on_game"]
        else:
            sim["profile"] = self._profile_before_game or auto["after_game"]
            self._profile_before_game = None

    def _run_guard(self) -> None:
        sim = self._sim
        guard = self._config["thermal_guard"]
        if not guard["enabled"]:
            sim["guard"] = False
            return
        tripped = sim["cpu_temp"] >= guard["cpu_trip"] or sim["gpu_temp"] >= guard["gpu_trip"]
        if tripped and not sim["guard"]:
            sim["guard"] = True
            self._guard_since = self._t
        elif sim["guard"]:
            clear = (
                sim["cpu_temp"] <= guard["cpu_trip"] - guard["release_c"]
                and sim["gpu_temp"] <= guard["gpu_trip"] - guard["release_c"]
            )
            held = self._t - (self._guard_since or 0) >= guard["min_hold_s"]
            if clear and held:
                sim["guard"] = False
                self._guard_since = None

    # -- commands, applied locally -----------------------------------------

    def _command(self, payload: dict) -> None:
        try:
            self._dispatch(payload)
        except (config_mod.PatchError, KeyError, ValueError, TypeError, RuntimeError) as exc:
            self.errorOccurred.emit(str(exc))
            return
        if self._connected:
            self._push()

    def _dispatch(self, req: dict) -> None:
        sim = self._sim
        profiles = DEMO_CAPABILITIES["profiles"]
        match req.get("op"):
            case "set_profile":
                name = req["profile"]
                if name not in profiles:
                    raise ValueError(f"unknown profile {name!r}")
                sim["profile"] = name
            case "toggle_gmode":
                after = self._config["auto"]["after_game"]
                sim["profile"] = after if sim["profile"] == "gmode" else "gmode"
            case "set_boost":
                if self._curves_on():
                    self._curves_latch = False
                sim["boost"][req["group"]] = max(0, min(100, int(req["value"])))
            case "set_turbo":
                sim["turbo"] = bool(req["enabled"])
            case "set_lighting":
                light = dict(sim["lighting"])
                light["effect"] = req["effect"]
                light["color"] = str(req.get("color", "00D1FF")).upper()
                if req.get("brightness") is not None:
                    light["brightness"] = int(req["brightness"])
                sim["lighting"] = light
            case "set_brightness":
                sim["lighting"] = {**sim["lighting"], "brightness": int(req["value"])}
            case "get_config":
                self._publish_config()
            case "set_config":
                self._apply_patch(req["patch"])
            case "set_cpu_cap":
                profile = req.get("profile") or sim["profile"] or "default"
                self._apply_patch({"cpu_cap": {"profiles": {profile: int(req["pct"])}}})
            case unknown:
                raise ValueError(f"unknown op {unknown!r}")

    def _apply_patch(self, patch: dict) -> None:
        patch = config_mod.validate_patch(patch)
        self._overrides = config_mod._merge(self._overrides, patch)
        self._config = config_mod.merged(self._overrides)
        if "enabled" in patch.get("fan_curves", {}):
            self._curves_latch = None
        self._publish_config()

    def _publish_config(self) -> None:
        self._config = copy.deepcopy(self._config)
        self.configChanged.emit()

    # -- helpers -------------------------------------------------------------

    def _curves_on(self) -> bool:
        if self._curves_latch is None:
            return bool(self._config["fan_curves"]["enabled"])
        return self._curves_latch

    @staticmethod
    def _firmware_rpm(profile: str, temp: float, boost: int, i: int) -> int:
        if profile == "gmode":
            firmware = MAX_RPM - 200 * i
        elif temp < 38:
            firmware = 0
        else:
            factor = PROFILE_FAN_FACTOR.get(profile, 1.0)
            firmware = factor * (1100 + (temp - 38) * 78) + 90 * i if factor else 0
        return int(min(MAX_RPM, max(firmware, boost / 100 * MAX_RPM)))

    def _push(self) -> None:
        self.feed(self.build_frame())
