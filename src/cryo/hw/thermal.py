"""Thermal control via the alienware-wmi hwmon + platform profiles.

Profile naming: Cryo uses AWCC-style names in its public API and
translates to kernel platform-profile values here. The translation is
built at startup from what the kernel actually advertises, because the
mapping depends on the machine:

  * G-Mode-capable machines (m18 R2 and friends) expose BOTH
    "balanced-performance" and "performance" — there, AWCC "Performance"
    is kernel "balanced-performance" and G-Mode is kernel "performance".
  * Machines without G-Mode expose plain "performance", which IS AWCC
    Performance — translating it to G-Mode there would mislabel the mode.
  * Legacy-profile machines advertise a smaller set (quiet/balanced/
    performance); anything the kernel doesn't list simply isn't offered.

Fan boost is probed rather than assumed — the kernel docs note boost "is
not implemented in every model". Without it, curves and the thermal
guard have nothing to actuate and must disable themselves visibly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from cryo import paths

log = logging.getLogger(__name__)


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
        # Per-handler node when available — the legacy aggregate rejects
        # writing "custom" on kernel 6.14+ (see paths.find_platform_profile).
        self.profile_path, self.profile_choices_path = paths.find_platform_profile()
        self._build_profile_maps()
        self.boost_ok = self._probe_boost()
        self.ac_path = paths.find_ac_supply()
        self.turbo_control = paths.find_turbo_control()

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

    def _build_profile_maps(self) -> None:
        kernel_choices = self.profile_choices_path.read_text().split()
        # Heuristic per the kernel driver docs: only G-Mode machines carry
        # balanced-performance AND performance side by side.
        self.has_gmode = (
            "balanced-performance" in kernel_choices and "performance" in kernel_choices
        )
        to_kernel: dict[str, str] = {}
        for choice in kernel_choices:
            if choice == "balanced-performance":
                to_kernel["performance"] = choice
            elif choice == "performance":
                to_kernel["gmode" if self.has_gmode else "performance"] = choice
            else:
                # cool / quiet / balanced / custom / low-power — 1:1 names.
                to_kernel[choice] = choice
        self.profile_to_kernel = to_kernel
        self.kernel_to_profile = {v: k for k, v in to_kernel.items()}

    def _probe_boost(self) -> bool:
        """Whether fan*_boost exists and accepts writes on this model."""
        for fan in self.fans:
            boost_path = self.hwmon / f"fan{fan.index}_boost"
            if not boost_path.exists():
                continue
            try:
                current = boost_path.read_text().strip()
                boost_path.write_text(current)  # rewrite current value: a no-op
                return True
            except OSError as exc:
                log.warning("fan boost probe failed on %s: %s", boost_path, exc)
        return False

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
        raw = self.profile_path.read_text().strip()
        return self.kernel_to_profile.get(raw, raw)

    def profile_choices(self) -> list[str]:
        return list(self.profile_to_kernel)

    def turbo(self) -> bool | None:
        """Turbo state, or None when this machine has no known control."""
        if self.turbo_control is None:
            return None
        path, inverted = self.turbo_control
        try:
            raw = self._read_int(path)
        except OSError:
            return None
        return raw == 0 if inverted else raw == 1

    def ac_online(self) -> bool:
        if self.ac_path is None:
            return True
        try:
            return self._read_int(self.ac_path) == 1
        except OSError:
            return True

    # -- writes (root) -----------------------------------------------------

    def set_profile(self, name: str) -> None:
        kernel = self.profile_to_kernel.get(name)
        if kernel is None:
            raise ValueError(
                f"profile {name!r} not supported on this machine "
                f"(available: {', '.join(self.profile_to_kernel)})"
            )
        self.profile_path.write_text(kernel)

    def set_boost(self, group: str, value: int) -> None:
        """Set boost (0-100) on all fans in a group ("cpu"/"gpu")."""
        if not self.boost_ok:
            raise RuntimeError("fan boost is not supported by this model's firmware")
        value = max(0, min(100, int(value)))
        for fan in self.fans:
            if fan.group == group:
                (self.hwmon / f"fan{fan.index}_boost").write_text(str(value))

    def set_turbo(self, enabled: bool) -> None:
        if self.turbo_control is None:
            raise RuntimeError("no CPU turbo control found on this machine")
        path, inverted = self.turbo_control
        raw = (0 if enabled else 1) if inverted else (1 if enabled else 0)
        path.write_text(str(raw))

    # -- snapshots ---------------------------------------------------------

    def capabilities(self) -> dict:
        """Static hardware capabilities, resolved once at daemon start."""
        return {
            "model": paths.dmi_model(),
            "profiles": self.profile_choices(),
            "gmode": self.has_gmode,
            "fan_boost": self.boost_ok,
            "fan_groups": sorted({f.group for f in self.fans}),
            "turbo": self.turbo_control is not None,
            "ac_supply": self.ac_path is not None,
        }

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
