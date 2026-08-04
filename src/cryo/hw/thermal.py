"""Thermal control via the alienware-wmi hwmon + ACPI platform_profile.

Profile naming: the kernel exposes six platform profiles. On G-Mode-capable
machines like the m18 R2 the kernel maps AWCC's modes as:

    kernel "balanced-performance"  == AWCC "Performance"
    kernel "performance"           == AWCC "G-Mode"
    kernel "custom"                == manual fan control (fan*_boost honored)

Cryo uses AWCC-style names in its public API and translates here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cryo import paths

# Cryo/AWCC name -> kernel platform_profile value
PROFILE_TO_KERNEL = {
    "cool": "cool",
    "quiet": "quiet",
    "balanced": "balanced",
    "performance": "balanced-performance",
    "gmode": "performance",
    "custom": "custom",
}
KERNEL_TO_PROFILE = {v: k for k, v in PROFILE_TO_KERNEL.items()}


@dataclass
class Fan:
    index: int  # hwmon fan index (1-based)
    label: str  # e.g. "CPU Fan"
    group: str  # "cpu" | "gpu"


class ThermalController:
    """Reads temps/RPM and writes profiles/boosts. Writes require root."""

    def __init__(self) -> None:
        self.hwmon = paths.find_hwmon()
        if self.hwmon is None:
            raise RuntimeError(
                "alienware_wmi hwmon not found — is the alienware-wmi driver loaded?"
            )
        self.fans = self._discover_fans()
        self.temps = self._discover_temps()  # {"cpu": index, "gpu": index}

    # -- discovery ---------------------------------------------------------

    def _discover_fans(self) -> list[Fan]:
        fans = []
        for label_file in sorted(self.hwmon.glob("fan*_label")):
            idx = int(label_file.name[3:].split("_")[0])
            label = label_file.read_text().strip()
            group = "gpu" if "gpu" in label.lower() else "cpu"
            fans.append(Fan(index=idx, label=label, group=group))
        return fans

    def _discover_temps(self) -> dict[str, int]:
        temps: dict[str, int] = {}
        for label_file in sorted(self.hwmon.glob("temp*_label")):
            idx = int(label_file.name[4:].split("_")[0])
            temps[label_file.read_text().strip().lower()] = idx
        return temps

    # -- reads -------------------------------------------------------------

    def _read_int(self, path: Path) -> int:
        return int(path.read_text().strip())

    def temp(self, which: str) -> float | None:
        idx = self.temps.get(which)
        if idx is None:
            return None
        try:
            return self._read_int(self.hwmon / f"temp{idx}_input") / 1000.0
        except OSError:
            return None

    def rpm(self, fan: Fan) -> int:
        try:
            return self._read_int(self.hwmon / f"fan{fan.index}_input")
        except OSError:
            return 0

    def boost(self, fan: Fan) -> int:
        try:
            return self._read_int(self.hwmon / f"fan{fan.index}_boost")
        except OSError:
            return 0

    def profile(self) -> str:
        raw = paths.PLATFORM_PROFILE.read_text().strip()
        return KERNEL_TO_PROFILE.get(raw, raw)

    def profile_choices(self) -> list[str]:
        raw = paths.PLATFORM_PROFILE_CHOICES.read_text().split()
        return [KERNEL_TO_PROFILE.get(c, c) for c in raw]

    def turbo(self) -> bool:
        try:
            return self._read_int(paths.NO_TURBO) == 0
        except OSError:
            return True

    def ac_online(self) -> bool:
        try:
            return self._read_int(paths.AC_ONLINE) == 1
        except OSError:
            return True

    # -- writes (root) -----------------------------------------------------

    def set_profile(self, name: str) -> None:
        kernel = PROFILE_TO_KERNEL.get(name)
        if kernel is None:
            raise ValueError(f"unknown profile {name!r}")
        paths.PLATFORM_PROFILE.write_text(kernel)

    def set_boost(self, group: str, value: int) -> None:
        """Set boost (0-100) on all fans in a group ("cpu"/"gpu")."""
        value = max(0, min(100, int(value)))
        for fan in self.fans:
            if fan.group == group:
                (self.hwmon / f"fan{fan.index}_boost").write_text(str(value))

    def set_turbo(self, enabled: bool) -> None:
        paths.NO_TURBO.write_text("0" if enabled else "1")

    # -- snapshots ---------------------------------------------------------

    def telemetry(self) -> dict:
        return {
            "profile": self.profile(),
            "turbo": self.turbo(),
            "ac": self.ac_online(),
            "cpu_temp": self.temp("cpu"),
            "gpu_temp": self.temp("gpu"),
            "fans": [
                {
                    "index": f.index,
                    "label": f.label,
                    "group": f.group,
                    "rpm": self.rpm(f),
                    "boost": self.boost(f),
                }
                for f in self.fans
            ],
        }
