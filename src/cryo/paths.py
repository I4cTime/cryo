"""Sysfs paths and discovery for the Alienware m18 R2.

Everything the daemon touches lives in sysfs, provided by the in-kernel
alienware-wmi driver — no acpi_call, no custom kernel modules.
"""

from __future__ import annotations

from pathlib import Path

PLATFORM_PROFILE = Path("/sys/firmware/acpi/platform_profile")
PLATFORM_PROFILE_CHOICES = Path("/sys/firmware/acpi/platform_profile_choices")
PLATFORM_PROFILE_CLASS = Path("/sys/class/platform-profile")
AC_ONLINE = Path("/sys/class/power_supply/AC/online")
NO_TURBO = Path("/sys/devices/system/cpu/intel_pstate/no_turbo")

RUN_SOCKET = Path("/run/cryo.sock")
CONFIG_FILE = Path("/etc/cryo/config.json")
STATE_FILE = Path("/var/lib/cryo/state.json")

HWMON_ROOT = Path("/sys/class/hwmon")


def find_platform_profile(driver: str = "alienware-wmi") -> tuple[Path, Path]:
    """(profile, choices) sysfs paths for the driver's platform profile.

    Prefers the per-handler node under /sys/class/platform-profile (kernel
    6.14+). The legacy aggregate /sys/firmware/acpi/platform_profile
    rejects writing "custom" with EINVAL — on the aggregate, "custom" is a
    read-only marker meaning "handlers disagree" — and once a second
    handler registers (e.g. Intel's processor_thermal_soc_slider) the
    aggregate no longer speaks for alienware-wmi alone anyway. The
    per-handler node accepts everything alienware-wmi itself declares,
    including the "custom" profile manual fan control depends on. Falls
    back to the legacy aggregate on pre-6.14 kernels, where it maps
    straight to the single driver.
    """
    for dev in sorted(PLATFORM_PROFILE_CLASS.glob("platform-profile-*")):
        try:
            if (dev / "name").read_text().strip() == driver:
                return dev / "profile", dev / "choices"
        except OSError:
            continue
    return PLATFORM_PROFILE, PLATFORM_PROFILE_CHOICES


def find_hwmon(name: str = "alienware_wmi") -> Path | None:
    """Locate the hwmon directory for the given driver name."""
    for hwmon in sorted(HWMON_ROOT.glob("hwmon*")):
        try:
            if (hwmon / "name").read_text().strip() == name:
                return hwmon
        except OSError:
            continue
    return None
