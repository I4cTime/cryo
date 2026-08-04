# Cryo

Personal command center for **one specific machine**: an Alienware m18 R2
running Pop!_OS. Replaces [tr1xem/AWCC](https://github.com/tr1xem/AWCC) with a
daemon + QML GUI that adds the things stock AWCC (and the Windows original)
don't do:

- **Custom fan curves** — temp→boost curves per fan group with hysteresis,
  driven through the kernel's `custom` platform profile. No acpi_call.
- **Game detection** — sustained RTX 4080 utilization (NVML) flips the machine
  into G-Mode automatically, and back out when you quit.
- **Auto profiles** — battery → quiet, AC → balanced, all configurable.
- **Live telemetry** — CPU/GPU temps, 4-fan RPM, dGPU load, sparkline history,
  in-window and in the tray tooltip.
- **AlienFX lighting** — 4-zone keyboard effects (protocol ported from AWCC),
  including a `quantum` cyan↔violet preset, restored on boot.

## Architecture

```
┌──────────────┐   unix socket (JSON lines)   ┌─────────────────────┐
│ cryo-gui     │◄────────────────────────────►│ cryod (root,        │
│ (QML + tray) │      /run/cryo.sock          │  systemd service)   │
└──────────────┘                              │  · platform_profile │
┌──────────────┐                              │  · hwmon fan boost  │
│ cryoctl (CLI)│◄────────────────────────────►│  · NVML game sense  │
└──────────────┘                              │  · AlienFX ELC USB  │
                                              └─────────────────────┘
```

Everything thermal goes through sysfs (`alienware-wmi` kernel driver):
`/sys/firmware/acpi/platform_profile` and the `alienware_wmi` hwmon
(`fan*_boost`, `fan*_input`, `temp*_input`). Lighting talks to the ELC USB
controller (`187c:0551`) directly. Profile names map as:

| Cryo/AWCC name | kernel platform_profile |
| -------------- | ----------------------- |
| performance    | balanced-performance    |
| gmode          | performance             |
| custom         | custom (manual fans)    |

## Install

```sh
uv sync
sudo packaging/install.sh   # venv sync + /etc/cryo + systemd unit + .desktop
```

## Use

```sh
cryoctl status | watch
cryoctl profile gmode / cryoctl gmode
cryoctl boost cpu 60
cryoctl light quantum / cryoctl light static 00D1FF
cryo-gui
```

Config lives at `/etc/cryo/config.json` (deep-merged over defaults in
`cryo/daemon/config.py`) — fan curve points, auto-rule targets, game
detection thresholds, socket group.

## Notes

- Lighting protocol ported from tr1xem/AWCC (GPL-3.0); this repo is
  GPL-3.0-or-later accordingly.
- G-Mode assumption: on the m18 R2 the kernel maps G-Mode to the
  `performance` platform profile (`balanced-performance` is AWCC's
  "Performance"). If Fn+G disagrees, fix `PROFILE_TO_KERNEL` in
  `src/cryo/hw/thermal.py`.
- Game detection needs the NVIDIA driver's NVML (present with the
  proprietary driver). Without it, Cryo degrades to manual + AC/battery
  rules only.
