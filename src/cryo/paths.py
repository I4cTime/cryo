"""Sysfs paths and discovery for the Alienware m18 R2.

Everything the daemon touches lives in sysfs, provided by the in-kernel
alienware-wmi driver — no acpi_call, no custom kernel modules.
"""

from __future__ import annotations

from pathlib import Path

PLATFORM_PROFILE = Path("/sys/firmware/acpi/platform_profile")
PLATFORM_PROFILE_CHOICES = Path("/sys/firmware/acpi/platform_profile_choices")
AC_ONLINE = Path("/sys/class/power_supply/AC/online")
NO_TURBO = Path("/sys/devices/system/cpu/intel_pstate/no_turbo")

RUN_SOCKET = Path("/run/cryo.sock")
CONFIG_FILE = Path("/etc/cryo/config.json")
STATE_FILE = Path("/var/lib/cryo/state.json")

HWMON_ROOT = Path("/sys/class/hwmon")


def find_hwmon(name: str = "alienware_wmi") -> Path | None:
    """Locate the hwmon directory for the given driver name."""
    for hwmon in sorted(HWMON_ROOT.glob("hwmon*")):
        try:
            if (hwmon / "name").read_text().strip() == name:
                return hwmon
        except OSError:
            continue
    return None
