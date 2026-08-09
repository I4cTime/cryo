"""Sysfs paths and discovery for alienware-wmi machines.

Everything the daemon touches lives in sysfs, provided by the in-kernel
alienware-wmi driver — no acpi_call, no custom kernel modules. Nothing
here assumes a specific model: supplies, turbo controls, and the
platform-profile node are discovered, not hardcoded.
"""

from __future__ import annotations

from pathlib import Path

PLATFORM_PROFILE = Path("/sys/firmware/acpi/platform_profile")
PLATFORM_PROFILE_CHOICES = Path("/sys/firmware/acpi/platform_profile_choices")
PLATFORM_PROFILE_CLASS = Path("/sys/class/platform-profile")
POWER_SUPPLY_ROOT = Path("/sys/class/power_supply")
NO_TURBO = Path("/sys/devices/system/cpu/intel_pstate/no_turbo")
CPUFREQ_BOOST = Path("/sys/devices/system/cpu/cpufreq/boost")
DMI_ROOT = Path("/sys/devices/virtual/dmi/id")
USB_DEVICES = Path("/sys/bus/usb/devices")

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


def find_ac_supply() -> Path | None:
    """`online` file of the first Mains power supply.

    The supply's name varies by model/firmware (AC, ACAD, AC0, ADP1…), so
    match on type instead of name.
    """
    for supply in sorted(POWER_SUPPLY_ROOT.glob("*")):
        try:
            if (supply / "type").read_text().strip() == "Mains":
                return supply / "online"
        except OSError:
            continue
    return None


def find_turbo_control() -> tuple[list[Path], bool] | None:
    """(paths, inverted) for the CPU turbo/boost toggle, or None.

    Intel: intel_pstate/no_turbo (one file, 1 = turbo OFF — inverted).
    acpi-cpufreq: the global cpufreq/boost (one file, direct).
    amd_pstate: no global knob — per-policy cpuX/cpufreq/boost files
    (direct); reads use the first, writes fan out to all of them.
    """
    if NO_TURBO.exists():
        return [NO_TURBO], True
    if CPUFREQ_BOOST.exists():
        return [CPUFREQ_BOOST], False
    per_policy = sorted(
        Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/boost"),
        key=lambda p: int(p.parent.parent.name[3:]),
    )
    if per_policy:
        return per_policy, False
    return None


def dmi_model() -> str:
    """Human-readable vendor + product from DMI, best effort."""
    parts = []
    for field in ("sys_vendor", "product_name"):
        try:
            value = (DMI_ROOT / field).read_text().strip()
        except OSError:
            continue
        if value:
            parts.append(value)
    return " ".join(parts)
