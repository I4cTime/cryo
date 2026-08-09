# Contributing to Cryo

Thanks for helping! The most valuable contribution right now is
**model reports**: run `cryoctl doctor` on your Alienware / Dell
G-Series machine and open a
[model report](https://github.com/I4cTime/cryo/issues/new?template=model-report.yml)
— working or broken, both grow [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).

## Dev environment

- Python **3.12+** and [`uv`](https://docs.astral.sh/uv/).
- An alienware-wmi machine to test on (the daemon refuses to start
  without the driver's hwmon).

```bash
git clone https://github.com/I4cTime/cryo.git && cd cryo
uv sync                      # editable install into .venv
sudo packaging/install.sh    # config + systemd unit + icons + .desktop
```

The venv install is editable — after changing daemon code, just
`sudo systemctl restart cryod`. GUI changes need only a `cryo-gui`
relaunch.

## Layout

- `src/cryo/daemon/` — `cryod`: engine tick, gamesense, config, socket server
- `src/cryo/hw/` — sysfs thermal control, AlienFX ELC USB protocol
- `src/cryo/gui/` — PySide6 bridge + QML (`qml/Main.qml`)
- `src/cryo/cli.py` — `cryoctl`
- `src/cryo/paths.py` — ALL sysfs discovery lives here; never hardcode
  a model-specific path anywhere else

## Conventions

- Capability honesty: anything model-dependent must be probed at daemon
  start, surfaced in the `capabilities` block, and degrade **visibly**
  in clients. No silent failures.
- All hardware I/O goes through the mainline kernel driver or the ELC
  USB device — `acpi_call` and out-of-tree modules are off the table.
- Conventional commits (`feat:`, `fix:`, `docs:`…).
- License is GPL-3.0-or-later (the lighting protocol derives from
  tr1xem/AWCC, GPL-3.0) — contributions are accepted under the same.
