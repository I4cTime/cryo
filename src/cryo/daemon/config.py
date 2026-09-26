"""Daemon configuration: JSON file at /etc/cryo/config.json, deep-merged
over defaults so a partial file is always valid.

The file holds *overrides only*. The daemon reads it at startup and, when
the GUI, `cryoctl curve/guard/cap` or a raw `set_config` changes something,
writes the updated overrides back — never the merged result, so defaults
added in later releases keep applying to keys the user never touched.
Every patch is validated (`validate_patch`) before it is merged or saved.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path

from cryo import paths

log = logging.getLogger(__name__)

DEFAULTS: dict = {
    # unix group allowed to talk to the daemon socket. install.sh writes
    # the installing user into /etc/cryo/config.json; this fallback is the
    # Debian-family admin group so a fresh daemon is usable without config.
    "socket_group": "sudo",
    "poll_interval": 1.0,
    "fan_curves": {
        # Applied only while profile == "custom".
        "enabled": True,
        # [temp_c, boost_pct] points; linear interpolation between them.
        "cpu": [[45, 0], [60, 15], [70, 35], [80, 60], [88, 85], [95, 100]],
        "gpu": [[45, 0], [60, 15], [70, 40], [80, 70], [87, 100]],
        # Ignore temp wobble smaller than this when deciding to move fans.
        "hysteresis_c": 3.0,
        # Don't write a new boost unless it differs by at least this much.
        "min_step": 5,
    },
    "thermal_guard": {
        # Emergency fan boost in ANY profile: trip -> boost to `boost`%,
        # release once both temps drop `release_c` below their trip points
        # AND the guard has been engaged at least `min_hold_s` (boost-clock
        # spikes cool within seconds; without the hold the fans saw-tooth),
        # restoring the boosts that were set before the guard engaged.
        "enabled": True,
        "cpu_trip": 88,
        "gpu_trip": 85,
        "release_c": 10,
        "min_hold_s": 30,
        "boost": 100,
    },
    "auto": {
        # Rules fire on *transitions* (AC plug/unplug, game start/stop),
        # so a manual profile choice sticks until the next event.
        "enabled": True,
        "on_battery": "quiet",
        "on_ac": "balanced",
        "on_game": "gmode",
        "after_game": "balanced",
        # Game detection: non-infrastructure dGPU graphics process with
        # >= game_min_vram_mb VRAM AND sustained utilization (NVML).
        "game_enter_util": 50,
        "game_enter_secs": 10,
        "game_exit_util": 20,
        "game_exit_secs": 45,
        "game_min_vram_mb": 400,
        # exact (lowercased) process basenames, never substrings — a game
        # binary like StarRuptureGameSteam-Win64-Shipping.exe must not be
        # eaten by a "steam" pattern.
        "game_ignore": [
            "cosmic-comp", "steamwebhelper", "steam", "xwayland", "xorg",
            "gnome-shell", "kwin_wayland", "kwin_x11", "mutter",
            "firefox", "firefox-bin", "chrome", "chromium", "brave", "code",
        ],
    },
    "lighting": {
        # Re-apply last lighting state when the daemon starts.
        "restore": True,
        "last": {"effect": "quantum", "color": "00D1FF", "brightness": 60},
    },
    "cpu_cap": {
        # Per-profile ceiling for the CPU's performance state, written to
        # intel_pstate/max_perf_pct on every profile change (and re-asserted
        # after resume). A profile missing from `profiles` means 100 = no
        # cap. On an m18 R2, 90 ≈ 5.2 GHz single-core: about 12 W and 9 °C
        # off the in-game peak for a couple of percent of CPU headroom.
        # `enabled: false` makes Cryo leave the knob alone entirely.
        "enabled": True,
        "profiles": {},
    },
}

# Bounds for the editable keys (GUI editor, cryoctl curve/guard/cap).
CURVE_POINTS_MIN = 2
CURVE_POINTS_MAX = 8
CURVE_TEMP_RANGE = (0, 110)
HYSTERESIS_RANGE = (0.0, 15.0)
MIN_STEP_RANGE = (1, 25)
GUARD_TRIP_RANGE = (60, 105)
GUARD_RELEASE_RANGE = (1, 30)
GUARD_HOLD_RANGE = (0, 600)
CPU_CAP_RANGE = (10, 100)


class PatchError(ValueError):
    """A `set_config` patch failed validation (message is user-facing)."""


def _number(value, label: str, lo, hi, integer: bool = False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PatchError(f"{label} must be a number")
    if integer and int(value) != value:
        raise PatchError(f"{label} must be a whole number")
    if not lo <= value <= hi:
        raise PatchError(f"{label} must be between {lo} and {hi}")
    return int(value) if integer else float(value)


def validate_curve(points, label: str) -> list[list[int]]:
    """A curve is 2-8 [temp_c, boost_pct] points with strictly rising temps
    and non-decreasing boosts."""
    if not isinstance(points, list):
        raise PatchError(f"{label} must be a list of [temp, boost] points")
    if not CURVE_POINTS_MIN <= len(points) <= CURVE_POINTS_MAX:
        raise PatchError(
            f"{label} needs {CURVE_POINTS_MIN}-{CURVE_POINTS_MAX} points, got {len(points)}"
        )
    out: list[list[int]] = []
    for i, point in enumerate(points):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise PatchError(f"{label} point {i + 1} must be [temp, boost]")
        temp = _number(point[0], f"{label} point {i + 1} temp", *CURVE_TEMP_RANGE, integer=True)
        boost = _number(point[1], f"{label} point {i + 1} boost", 0, 100, integer=True)
        if out and temp <= out[-1][0]:
            raise PatchError(f"{label} temperatures must rise from point to point")
        if out and boost < out[-1][1]:
            raise PatchError(f"{label} boosts must not decrease as temperature rises")
        out.append([temp, boost])
    return out


def validate_patch(patch: dict) -> dict:
    """Check the keys Cryo's editors write; return a normalized copy.

    Keys this doesn't know about pass through untouched (the config file
    is the user's), but anything the daemon actuates from must be sane —
    a curve with falling temperatures or a 5% CPU cap would otherwise be
    written to sysfs verbatim.
    """
    if not isinstance(patch, dict):
        raise PatchError("patch must be an object")
    out = copy.deepcopy(patch)

    curves = out.get("fan_curves")
    if curves is not None:
        if not isinstance(curves, dict):
            raise PatchError("fan_curves must be an object")
        for group in ("cpu", "gpu"):
            if group in curves:
                curves[group] = validate_curve(curves[group], f"fan_curves.{group}")
        if "hysteresis_c" in curves:
            curves["hysteresis_c"] = _number(
                curves["hysteresis_c"], "fan_curves.hysteresis_c", *HYSTERESIS_RANGE
            )
        if "min_step" in curves:
            curves["min_step"] = _number(
                curves["min_step"], "fan_curves.min_step", *MIN_STEP_RANGE, integer=True
            )
        if "enabled" in curves and not isinstance(curves["enabled"], bool):
            raise PatchError("fan_curves.enabled must be true or false")

    guard = out.get("thermal_guard")
    if guard is not None:
        if not isinstance(guard, dict):
            raise PatchError("thermal_guard must be an object")
        for key in ("cpu_trip", "gpu_trip"):
            if key in guard:
                guard[key] = _number(guard[key], f"thermal_guard.{key}", *GUARD_TRIP_RANGE, integer=True)
        if "release_c" in guard:
            guard["release_c"] = _number(
                guard["release_c"], "thermal_guard.release_c", *GUARD_RELEASE_RANGE, integer=True
            )
        if "min_hold_s" in guard:
            guard["min_hold_s"] = _number(
                guard["min_hold_s"], "thermal_guard.min_hold_s", *GUARD_HOLD_RANGE, integer=True
            )
        if "boost" in guard:
            guard["boost"] = _number(guard["boost"], "thermal_guard.boost", 0, 100, integer=True)
        if "enabled" in guard and not isinstance(guard["enabled"], bool):
            raise PatchError("thermal_guard.enabled must be true or false")

    cap = out.get("cpu_cap")
    if cap is not None:
        if not isinstance(cap, dict):
            raise PatchError("cpu_cap must be an object")
        if "enabled" in cap and not isinstance(cap["enabled"], bool):
            raise PatchError("cpu_cap.enabled must be true or false")
        profiles = cap.get("profiles")
        if profiles is not None:
            if not isinstance(profiles, dict):
                raise PatchError("cpu_cap.profiles must map profile names to percentages")
            cap["profiles"] = {
                str(name).lower(): _number(pct, f"cpu_cap.profiles.{name}", *CPU_CAP_RANGE, integer=True)
                for name, pct in profiles.items()
            }

    auto = out.get("auto")
    if auto is not None and not isinstance(auto, dict):
        raise PatchError("auto must be an object")
    return out


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_overrides(path: Path = paths.CONFIG_FILE) -> dict:
    """The user's partial config, or {} when missing or unreadable.

    A broken file must not keep the daemon (and with it the thermal guard)
    from starting: log loudly and run on defaults.
    """
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.error("config %s unreadable (%s); running on defaults", path, exc)
        return {}
    if not isinstance(raw, dict):
        log.error("config %s is not a JSON object; running on defaults", path)
        return {}
    return raw


def merged(overrides: dict) -> dict:
    return _merge(DEFAULTS, overrides)


def load(path: Path = paths.CONFIG_FILE) -> dict:
    """Effective config: defaults deep-merged with the user's overrides."""
    return merged(load_overrides(path))


def save_overrides(overrides: dict, path: Path = paths.CONFIG_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(overrides, indent=2) + "\n")
    os.replace(tmp, path)
