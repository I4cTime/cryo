# Contributing to Cryo

Thanks for helping! The most valuable contribution right now is
**model reports**: run `cryoctl doctor` on your Alienware / Dell
G-Series machine and open a
[model report](https://github.com/I4cTime/cryo/issues/new?template=model-report.yml).
Working or broken, both grow [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).

## Dev environment

- Python **3.12+** and [`uv`](https://docs.astral.sh/uv/).
- An alienware-wmi machine to test on (without the driver's hwmon or
  platform profiles the daemon runs in limited mode, so fan and mode
  code can't be exercised there). GUI work needs none: see
  [demo mode](#gui).

```bash
git clone https://github.com/I4cTime/cryo.git && cd cryo
uv sync                      # editable install into .venv
sudo packaging/install.sh    # config + systemd unit + icons + .desktop
```

The venv install is editable - after changing daemon code, just
`sudo systemctl restart cryod`. GUI changes need only a `cryo-gui`
relaunch.

## Release bundle

Releases ship `cryo-<version>-linux-x86_64.tar.gz`, built by
`uv run --no-project tools/build_bundle.py` (wheel, hash-pinned
requirements from `uv.lock`, a pinned static `uv`, and
`packaging/bundle/{install,uninstall}.sh`; see
[docs/INSTALL.md](docs/INSTALL.md)). Don't run the bundle installer on your
own machine: it replaces a from-source install. CI's `bundle` job installs,
upgrades and uninstalls it on the runner, and
`tools/bundle_container_test.sh` does the same in Arch, Ubuntu and Fedora
systemd containers with rootless podman.

## Layout

- `src/cryo/daemon/` - `cryod`: engine tick, gamesense, config, socket server
- `src/cryo/hw/` - sysfs thermal control, AlienFX ELC USB protocol
- `src/cryo/gui/` - `cryo-gui`: entry point and tray (`main.py`), the
  daemon bridge (`bridge.py`), demo daemon (`demo.py`), Frost's status
  line (`voice.py`, pure Python, no network), SVG icon provider
  (`icons.py`)
- `src/cryo/gui/qml/` - `Main.qml` is the window; every piece of UI is
  a file in the `Cryo` module (`qml/Cryo/`, registered in `qmldir`).
  Singletons: `Theme` (look tokens per style, accent, fonts), `Ambient`
  (runtime state: `live`, `motion`, `heat`, frost amount, guard phase),
  `Prefs` (persisted settings), `Sfx` (sound cues)
- `src/cryo/gui/qml/Cryo/fx/` - the frost shader (`frost.frag`, its
  compiled `.qsb` and hash sidecar) and the generated `frost_growth.png`
  and `frost_static.png` (software renderer fallback)
- `src/cryo/gui/assets/` - fonts, `icons/` (white-on-transparent SVGs,
  tinted at runtime), `sounds/<set>/` (generated WAVs)
- `src/cryo/cli.py` - `cryoctl`
- `src/cryo/paths.py` - ALL sysfs discovery lives here; never hardcode
  a model-specific path anywhere else
- `tools/` - asset generators and look tools for the GUI (below)

## GUI

- **Demo mode**: `uv run cryo-gui --demo [--scenario idle|load|guard|gaming|cycle]`
  runs the real GUI against `DemoDaemon`, a scripted stand-in for
  `cryod`. No daemon, no hardware; its settings live under `Cryo-demo`,
  apart from the real app's.
- **Tour**: `uv run tools/tour.py OUTDIR` writes deterministic
  screenshots of every scene (`--list`) against a paused demo daemon,
  with `--style`, `--accent`, `--reduce-motion` and `--perf SECONDS`.
  The default path runs inside a headless gamescope so shaders render;
  without gamescope use `--software` (Qt's software renderer, no shader
  or MultiEffect output).
- **Tokens**: no colour literals in QML outside `Theme.qml` (the
  lighting swatch data in `Lighting.qml` and `FrostOverlay.qml`'s
  property defaults are the only exemptions) and no emoji;
  `tests/test_gui_tokens.py` enforces both. Styles, accents and the
  token contract: [docs/THEME.md](docs/THEME.md).
- **Generated files are committed.** Rerun the generator when you
  change its input:
  - shaders (`*.frag`): `uv run python tools/build_shaders.py`;
    `tests/test_shaders.py` fails when a `.qsb` is stale
  - sounds (`tools/gen_sounds.py` itself): `uv run python tools/gen_sounds.py`;
    `tests/test_sounds.py` fails when the committed WAVs differ
  - frost art (`tools/gen_frost.py`): `uv run --with numpy --with pillow --with scipy python tools/gen_frost.py`;
    no test checks these PNGs, so commit them with the generator change
- **Look tools**: `tools/icon_sheet.py OUT.png` renders a contact sheet
  of the icon set (`tests/test_icons.py` keeps every SVG Qt SVG Tiny
  safe and tintable); `tools/frost_preview.py OUTDIR` renders the frost
  at several amounts (GPU path, run it under gamescope as its docstring
  shows).
- The GUI tests run offscreen with the rest: `uv run pytest`.

## Conventions

- Capability honesty: anything model-dependent must be probed at daemon
  start, surfaced in the `capabilities` block, and degrade **visibly**
  in clients. No silent failures.
- All hardware I/O goes through the mainline kernel driver or the ELC
  USB device - `acpi_call` and out-of-tree modules are off the table.
- GUI: every looping animation (`FrameAnimation`, `loops:
  Animation.Infinite`) needs a `running:` binding gated on
  `Ambient.motion`, which is false while the window is hidden,
  minimized or unfocused and under reduce motion;
  `tests/test_gui_alive.py` enforces it. Nothing may repaint
  continuously at rest: a thermal tool must not warm the machine.
- Conventional commits (`feat:`, `fix:`, `docs:`…).
- License is GPL-3.0-or-later (the lighting protocol derives from
  tr1xem/AWCC, GPL-3.0) - contributions are accepted under the same.
