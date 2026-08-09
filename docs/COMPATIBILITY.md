# Hardware compatibility

Cryo is built on the mainline **alienware-wmi** kernel driver — no
`acpi_call`, no out-of-tree modules. That driver covers many Alienware
and Dell G-Series machines, so most of Cryo works far beyond the machine
it was written on. Since v0.2 the daemon probes what your machine
actually supports at startup and every client (GUI, tray, CLI) renders
only what exists.

## Feature availability

| Feature | Requires | Behavior when missing |
|---|---|---|
| Power modes | `alienware-wmi` platform profiles | Cryo won't start without the driver |
| G-Mode | G-Mode-capable model (kernel advertises `balanced-performance` **and** `performance`) | "Performance" becomes the boost profile; auto-rules fall back |
| Fan curves + manual boost | `fan*_boost` support (probed — "not implemented in every model" per kernel docs) | Curves/sliders disabled with a visible notice |
| Thermal Guard | fan boost (above) | Disabled (nothing to actuate) |
| Auto profiles (AC/battery) | a `Mains`-type power supply in sysfs (name is discovered, not assumed) | Battery rules never fire; everything else works |
| CPU Turbo toggle | `intel_pstate/no_turbo` or `cpufreq/boost` | Toggle hidden |
| Game detection | NVIDIA proprietary driver (NVML) | Auto-G-Mode off; manual modes unaffected |
| AlienFX lighting | AW-ELC USB controller `187c:0550/0551` (≈2020+ m/x-series keyboards) | Lighting section hidden |

Profile naming is translated per machine: on G-Mode models the kernel's
`balanced-performance` is AWCC "Performance" and `performance` is
G-Mode; on models without G-Mode, `performance` *is* Performance. Cryo
builds this mapping from the kernel's advertised choices at startup.

## Tested models

| Model | Thermals | Curves/Guard | G-Mode | Lighting | Game sense | Reported by |
|---|---|---|---|---|---|---|
| Alienware m18 R2 (Intel + RTX 4080) | ✅ | ✅ | ✅ | ✅ | ✅ | maintainer |

**Have a different Alienware or Dell G-Series machine?** Run:

```
cryoctl doctor
```

and open a [model report](../../issues/new?template=model-report.yml)
with the output — working or not, both results grow this table.

## Known out of scope (for now)

- AMD dGPU game detection (needs DRM fdinfo instead of NVML)
- Pre-ELC lighting controllers (older AlienFX protocols, per-key RGB)
- Aurora/Area-51 desktops (thermals may work; entirely untested)
