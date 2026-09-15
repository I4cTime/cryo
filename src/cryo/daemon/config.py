"""Daemon configuration: JSON file at /etc/cryo/config.json, deep-merged
over defaults so a partial file is always valid.

The file holds *overrides only*. The daemon reads it at startup and, when
the GUI or `set_config` changes something, writes the updated overrides
back — never the merged result, so defaults added in later releases keep
applying to keys the user never touched.
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
}


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
