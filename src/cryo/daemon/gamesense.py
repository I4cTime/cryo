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


# Ticks between NVML init attempts while the driver is unavailable — cryod
# often starts before the NVIDIA module on boot, and the driver can go away
# and come back across suspend.
NVML_RETRY_TICKS = 30


class GpuSense:
    def __init__(self) -> None:
        self._nvml = None
        self._handle = None
        self._ticks_since_attempt = 0
        self._announced_missing = False
        self.reinit()

    def reinit(self) -> bool:
        """(Re)initialize NVML. Returns availability."""
        self._ticks_since_attempt = 0
        try:
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
        except Exception as exc:  # NVML missing/driver asleep — degrade gracefully
            self._nvml = None
            self._handle = None
            if not self._announced_missing:
                log.warning("NVML unavailable, game detection disabled: %s", exc)
                self._announced_missing = True
            return False
        self._nvml = pynvml
        self._handle = handle
        self._announced_missing = False
        log.info("NVML initialized: %s", name)
        return True

    def maybe_reinit(self) -> bool:
        """Retry NVML init every NVML_RETRY_TICKS while unavailable.

        Returns True on the tick NVML *becomes* available so the caller can
        refresh what it tells clients.
        """
        if self._nvml is not None:
            return False
        self._ticks_since_attempt += 1
        if self._ticks_since_attempt < NVML_RETRY_TICKS:
            return False
        return self.reinit()

    def available(self) -> bool:
        return self._nvml is not None

    def utilization(self) -> int | None:
        """dGPU utilization percent, or None if NVML is unavailable."""
        if self._nvml is None:
            return None
        try:
            return int(self._nvml.nvmlDeviceGetUtilizationRates(self._handle).gpu)
        except Exception:
            return None

    def memory(self) -> tuple[int, int] | None:
        """dGPU VRAM as (used_mb, total_mb), or None if NVML is unavailable."""
        if self._nvml is None:
            return None
        try:
            info = self._nvml.nvmlDeviceGetMemoryInfo(self._handle)
            return int(info.used) // (1024 * 1024), int(info.total) // (1024 * 1024)
        except Exception:
            return None

    def power_w(self) -> float | None:
        """dGPU board power draw in watts, or None if NVML is unavailable."""
        if self._nvml is None:
            return None
        try:
            return round(self._nvml.nvmlDeviceGetPowerUsage(self._handle) / 1000, 1)
        except Exception:
            return None

    def clock_mhz(self) -> int | None:
        """dGPU graphics clock in MHz, or None if NVML is unavailable."""
        if self._nvml is None:
            return None
        try:
            return int(
                self._nvml.nvmlDeviceGetClockInfo(
                    self._handle, self._nvml.NVML_CLOCK_GRAPHICS
                )
            )
        except Exception:
            return None

    _PROC_GETTERS = {
        "graphics": "nvmlDeviceGetGraphicsRunningProcesses",
        "compute": "nvmlDeviceGetComputeRunningProcesses",
    }

    def _raw_processes(
        self, kinds: tuple[str, ...]
    ) -> dict[int, tuple[int, set[str]]] | None:
        """pid -> (vram_mb, kinds it appeared under). None = no signal."""
        if self._nvml is None:
            return None
        by_pid: dict[int, tuple[int, set[str]]] = {}
        any_ok = False
        for kind in kinds:
            try:
                procs = getattr(self._nvml, self._PROC_GETTERS[kind])(self._handle)
            except Exception:
                continue
            any_ok = True
            for proc in procs:
                mb = int((proc.usedGpuMemory or 0) // (1024 * 1024))
                prev_mb, prev_kinds = by_pid.get(proc.pid, (0, set()))
                by_pid[proc.pid] = (max(prev_mb, mb), prev_kinds | {kind})
        return by_pid if any_ok else None

    @staticmethod
    def _basename(name: str) -> str:
        # Chromium/Electron rewrite their proc title to one spaced string
        # ("brave --type=gpu-process ..."), so cut at the first flag; " -"
        # (not any space) keeps paths with spaces intact. Then basename over
        # "/" AND "\": Wine/Proton argv[0] is a Windows path
        # (Z:\games\...\Game.exe).
        name = name.split(" -", 1)[0].strip()
        return name.replace("\\", "/").split("/")[-1].lower()

    def _named(
        self, raw: dict[int, tuple[int, set[str]]]
    ) -> list[tuple[str, int, set[str]]]:
        out = []
        for pid, (mb, kinds) in raw.items():
            name = self._proc_name(pid)
            if name is None:
                continue
            out.append((self._basename(name), mb, kinds))
        out.sort(key=lambda item: item[1], reverse=True)
        return out

    def processes(
        self, kinds: tuple[str, ...] = ("graphics", "compute")
    ) -> list[tuple[str, int]] | None:
        """dGPU processes as (basename, vram_mb), largest VRAM first.

        None if NVML is unavailable or every requested query failed —
        callers treat that as "no signal", not "no processes".
        """
        raw = self._raw_processes(kinds)
        if raw is None:
            return None
        return [(name, mb) for name, mb, _ in self._named(raw)]

    def snapshot(self) -> tuple[list[tuple[str, int]], list[tuple[str, int]]] | None:
        """One NVML pass per tick: (all processes, graphics-only processes).

        The engine needs both — the VRAM breakdown wants everything, game
        detection wants graphics contexts only — and querying twice doubled
        the per-tick NVML and /proc work.
        """
        raw = self._raw_processes(("graphics", "compute"))
        if raw is None:
            return None
        named = self._named(raw)
        every = [(name, mb) for name, mb, _ in named]
        graphics = [(name, mb) for name, mb, kinds in named if "graphics" in kinds]
        return every, graphics

    def _proc_name(self, pid: int) -> str | None:
        """argv[0] of a pid, NVML name as fallback.

        NVML's process name is the full command line on recent drivers
        (580+), which breaks exact-basename matching and floods displays;
        /proc cmdline is NUL-delimited so argv[0] survives paths with
        spaces intact.
        """
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                argv0 = f.read().split(b"\0", 1)[0]
            if argv0:
                return argv0.decode(errors="replace")
        except OSError:
            pass
        try:
            name = self._nvml.nvmlSystemGetProcessName(pid)
            return name.decode() if isinstance(name, bytes) else name
        except Exception:
            return None

    def game_candidates(
        self,
        ignore: list[str],
        min_vram_mb: int,
        procs: list[tuple[str, int]] | None = None,
    ) -> list[str] | None:
        """Names of dGPU graphics processes that look like games.

        `procs` lets the engine pass the graphics half of snapshot() so the
        tick does one NVML pass; without it this queries on its own.
        """
        if procs is None:
            procs = self.processes(kinds=("graphics",))
        if procs is None:
            return None
        # Exact match only: substring matching once ate
        # "StarRuptureGameSteam-Win64-Shipping.exe" via the "steam" entry.
        return [
            name for name, vram_mb in procs
            if vram_mb >= min_vram_mb and name not in ignore
        ]


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
