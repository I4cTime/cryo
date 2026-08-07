"""The Cryo engine: one tick per poll interval.

Each tick:  read telemetry -> update game state -> apply auto-profile
transitions -> drive fan curves (custom profile only) -> emit telemetry
to subscribers.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from cryo.daemon.gamesense import GameDetector, GpuSense
from cryo.hw.effects import Effects
from cryo.hw.thermal import ThermalController

log = logging.getLogger(__name__)


def interpolate(curve: list[list[float]], temp: float) -> int:
    """Linear interpolation over [temp, boost] points."""
    if not curve:
        return 0
    if temp <= curve[0][0]:
        return int(curve[0][1])
    if temp >= curve[-1][0]:
        return int(curve[-1][1])
    for (t1, b1), (t2, b2) in zip(curve, curve[1:]):
        if t1 <= temp <= t2:
            if t2 == t1:
                return int(b2)
            return int(b1 + (b2 - b1) * (temp - t1) / (t2 - t1))
    return int(curve[-1][1])


class Engine:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.thermal = ThermalController()
        self.effects = Effects()
        self.gpu = GpuSense()
        self.detector = GameDetector(config["auto"], config["poll_interval"])
        self.listeners: list[Callable[[dict], None]] = []

        self._last_ac = self.thermal.ac_online()
        self._profile_before_game: str | None = None
        # Per-group state for curve hysteresis
        self._curve_anchor: dict[str, float] = {}
        self._curve_boost: dict[str, int] = {}
        # Thermal guard state
        self._guard_active = False
        self._guard_engaged_at = 0.0
        self._guard_saved_boosts: dict[str, int] = {}
        self._peaks: dict[str, float] = {"cpu": 0.0, "gpu": 0.0}

        if config["lighting"]["restore"]:
            self.restore_lighting()

    # -- lighting ----------------------------------------------------------

    def restore_lighting(self) -> None:
        last = self.config["lighting"]["last"]
        try:
            if not self.effects.available():
                log.warning("ELC not available; skipping lighting restore")
                return
            self.effects.apply(last["effect"], int(last.get("color", "00D1FF"), 16))
            self.effects.brightness(int(last.get("brightness", 60)))
            log.info("Restored lighting: %s", last)
        except Exception as exc:
            log.warning("Lighting restore failed: %s", exc)

    def set_lighting(self, effect: str, color: int, brightness: int | None = None) -> None:
        self.effects.apply(effect, color)
        if brightness is not None:
            self.effects.brightness(brightness)
        self.config["lighting"]["last"] = {
            "effect": effect,
            "color": f"{color:06X}",
            **(
                {"brightness": brightness}
                if brightness is not None
                else {"brightness": self.config["lighting"]["last"].get("brightness", 60)}
            ),
        }

    # -- profile helpers ---------------------------------------------------

    def set_profile(self, name: str) -> None:
        self.thermal.set_profile(name)
        if name == "custom":
            # Reset curve state so boosts get re-applied fresh.
            self._curve_anchor.clear()
            self._curve_boost.clear()
        log.info("Profile -> %s", name)

    def toggle_gmode(self) -> str:
        current = self.thermal.profile()
        target = self.config["auto"]["after_game"] if current == "gmode" else "gmode"
        self.set_profile(target)
        return target

    # -- tick --------------------------------------------------------------

    def tick(self) -> dict:
        telemetry = self.thermal.telemetry()
        util = self.gpu.utilization()
        telemetry["gpu_util"] = util

        auto = self.config["auto"]

        # Game transitions
        candidates = self.gpu.game_candidates(
            self.detector.ignore, self.detector.min_vram_mb
        )
        telemetry["game_procs"] = candidates or []
        change = self.detector.sample(util, candidates)
        if auto["enabled"] and change is True:
            self._profile_before_game = telemetry["profile"]
            log.info("Game detected (gpu util %s%%)", util)
            self.set_profile(auto["on_game"])
            telemetry["profile"] = auto["on_game"]
        elif auto["enabled"] and change is False:
            target = self._profile_before_game or auto["after_game"]
            self._profile_before_game = None
            log.info("Game ended, restoring %s", target)
            self.set_profile(target)
            telemetry["profile"] = target
        telemetry["gaming"] = self.detector.gaming

        # AC/battery transitions
        ac = telemetry["ac"]
        if auto["enabled"] and ac != self._last_ac:
            target = auto["on_ac"] if ac else auto["on_battery"]
            log.info("Power source changed (ac=%s) -> %s", ac, target)
            self.set_profile(target)
            telemetry["profile"] = target
        self._last_ac = ac

        # Peak tracking
        for group, key in (("cpu", "cpu_temp"), ("gpu", "gpu_temp")):
            if telemetry[key] is not None:
                self._peaks[group] = max(self._peaks[group], telemetry[key])
        telemetry["cpu_peak"] = self._peaks["cpu"]
        telemetry["gpu_peak"] = self._peaks["gpu"]

        # Thermal guard runs in ANY profile and outranks curves.
        self._apply_guard(telemetry)
        telemetry["guard"] = self._guard_active

        # Fan curves (only meaningful in custom profile)
        curves = self.config["fan_curves"]
        if (
            not self._guard_active
            and curves["enabled"]
            and telemetry["profile"] == "custom"
        ):
            self._apply_curves(telemetry, curves)

        # Config state the GUI mirrors (switches, lighting controls) — one
        # data path for everything the UI shows.
        telemetry["curves_enabled"] = curves["enabled"]
        telemetry["auto_enabled"] = auto["enabled"]
        telemetry["lighting"] = self.config["lighting"]["last"]

        return telemetry

    def _apply_guard(self, telemetry: dict) -> None:
        guard = self.config["thermal_guard"]
        if not guard["enabled"]:
            return
        cpu = telemetry["cpu_temp"]
        gpu = telemetry["gpu_temp"]
        tripped = (cpu is not None and cpu >= guard["cpu_trip"]) or (
            gpu is not None and gpu >= guard["gpu_trip"]
        )
        if tripped and not self._guard_active:
            self._guard_saved_boosts = {
                group: max(
                    (self.thermal.boost(f) for f in self.thermal.fans if f.group == group),
                    default=0,
                )
                for group in ("cpu", "gpu")
            }
            try:
                self.thermal.set_boost("cpu", guard["boost"])
                self.thermal.set_boost("gpu", guard["boost"])
                self._guard_active = True
                self._guard_engaged_at = time.monotonic()
                log.warning(
                    "THERMAL GUARD engaged (cpu=%s gpu=%s) — fans to %s%%",
                    cpu, gpu, guard["boost"],
                )
            except OSError as exc:
                log.error("thermal guard boost write failed: %s", exc)
        elif self._guard_active:
            cpu_clear = cpu is None or cpu <= guard["cpu_trip"] - guard["release_c"]
            gpu_clear = gpu is None or gpu <= guard["gpu_trip"] - guard["release_c"]
            # Boost-clock temp spikes clear within a second or two of full
            # fans; without a minimum hold the guard saw-tooths (100% -> 0%
            # -> 100%) every few seconds under sustained load.
            held_long_enough = (
                time.monotonic() - self._guard_engaged_at >= guard["min_hold_s"]
            )
            if cpu_clear and gpu_clear and held_long_enough:
                try:
                    for group, saved in self._guard_saved_boosts.items():
                        self.thermal.set_boost(group, saved)
                    log.info(
                        "Thermal guard released (cpu=%s gpu=%s), boosts restored %s",
                        cpu, gpu, self._guard_saved_boosts,
                    )
                except OSError as exc:
                    log.error("thermal guard restore failed: %s", exc)
                self._guard_active = False
                # Let curves retake control cleanly if they're active.
                self._curve_anchor.clear()
                self._curve_boost.clear()

    def _apply_curves(self, telemetry: dict, curves: dict) -> None:
        for group, temp_key in (("cpu", "cpu_temp"), ("gpu", "gpu_temp")):
            temp = telemetry[temp_key]
            if temp is None or group not in curves:
                continue
            anchor = self._curve_anchor.get(group)
            if anchor is not None and abs(temp - anchor) < curves["hysteresis_c"]:
                continue  # within the dead zone, hold current boost
            target = interpolate(curves[group], temp)
            current = self._curve_boost.get(group)
            if current is None or abs(target - current) >= curves["min_step"] or (
                target in (0, 100) and target != current
            ):
                try:
                    self.thermal.set_boost(group, target)
                    self._curve_boost[group] = target
                    self._curve_anchor[group] = temp
                except OSError as exc:
                    log.warning("boost write failed for %s: %s", group, exc)
