"""Game detection via NVML.

The m18 R2 runs hybrid graphics, but on COSMIC the compositor itself sits
on the RTX 4080 (~25-50% idle utilization), so raw utilization is not a
reliable game signal on its own. A "game" here is:

    a dGPU graphics process that is NOT on the ignore list (compositor,
    Steam chrome, browsers), is using real VRAM, AND utilization is
    sustained above the enter threshold.

Both conditions must hold to enter gaming state; losing either one
(sustained) exits it.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Exact (lowercased) process basenames — never substring patterns.
DEFAULT_IGNORE = [
    "cosmic-comp",
    "steamwebhelper",
    "steam",
    "xwayland",
    "xorg",
    "gnome-shell",
    "kwin_wayland",
    "kwin_x11",
    "mutter",
    "firefox",
    "firefox-bin",
    "chrome",
    "chromium",
    "brave",
    "code",
]


class GpuSense:
    def __init__(self) -> None:
        self._nvml = None
        self._handle = None
        try:
            import pynvml

            pynvml.nvmlInit()
            self._nvml = pynvml
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            log.info("NVML initialized: %s", pynvml.nvmlDeviceGetName(self._handle))
        except Exception as exc:  # NVML missing/driver asleep — degrade gracefully
            log.warning("NVML unavailable, game detection disabled: %s", exc)

    def utilization(self) -> int | None:
        """dGPU utilization percent, or None if NVML is unavailable."""
        if self._nvml is None:
            return None
        try:
            return int(self._nvml.nvmlDeviceGetUtilizationRates(self._handle).gpu)
        except Exception:
            return None

    def game_candidates(self, ignore: list[str], min_vram_mb: int) -> list[str] | None:
        """Names of dGPU graphics processes that look like games."""
        if self._nvml is None:
            return None
        try:
            procs = self._nvml.nvmlDeviceGetGraphicsRunningProcesses(self._handle)
        except Exception:
            return None
        candidates = []
        for proc in procs:
            vram_mb = (proc.usedGpuMemory or 0) / (1024 * 1024)
            if vram_mb < min_vram_mb:
                continue
            try:
                name = self._nvml.nvmlSystemGetProcessName(proc.pid)
                if isinstance(name, bytes):
                    name = name.decode()
            except Exception:
                continue
            basename = name.split("/")[-1].lower()
            # Exact match only: substring matching once ate
            # "StarRuptureGameSteam-Win64-Shipping.exe" via the "steam" entry.
            if basename in ignore:
                continue
            candidates.append(basename)
        return candidates


class GameDetector:
    """Hysteresis state machine over (utilization, candidate-process) pairs."""

    def __init__(self, cfg: dict, poll_interval: float) -> None:
        self.gaming = False
        self._enter_clock = 0.0
        self._exit_clock = 0.0
        self._interval = poll_interval
        self.configure(cfg)

    def configure(self, cfg: dict) -> None:
        self.enter_util = cfg["game_enter_util"]
        self.enter_secs = cfg["game_enter_secs"]
        self.exit_util = cfg["game_exit_util"]
        self.exit_secs = cfg["game_exit_secs"]
        self.ignore = [p.lower() for p in cfg.get("game_ignore", DEFAULT_IGNORE)]
        self.min_vram_mb = cfg.get("game_min_vram_mb", 400)

    def sample(self, util: int | None, candidates: list[str] | None) -> bool | None:
        """Feed one sample. Returns True on game start, False on game end,
        None when state is unchanged."""
        if util is None:
            return None
        has_game_proc = bool(candidates)
        if not self.gaming:
            if has_game_proc and util >= self.enter_util:
                self._enter_clock += self._interval
                if self._enter_clock >= self.enter_secs:
                    self.gaming = True
                    self._exit_clock = 0.0
                    return True
            else:
                self._enter_clock = 0.0
        else:
            if not has_game_proc or util <= self.exit_util:
                self._exit_clock += self._interval
                if self._exit_clock >= self.exit_secs:
                    self.gaming = False
                    self._enter_clock = 0.0
                    return False
            else:
                self._exit_clock = 0.0
        return None
