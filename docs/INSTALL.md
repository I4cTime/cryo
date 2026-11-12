# Installing Cryo

Every [GitHub release](https://github.com/I4cTime/cryo/releases/latest)
carries `cryo-<version>-linux-x86_64.tar.gz`, an installer bundle, and
`SHA256SUMS`. That is the normal way to install Cryo. Contributors who
want to run their own checkout use the [from-source install](#from-source)
instead.

## Requirements

- An x86_64 Linux distro with glibc 2.34 or newer and systemd (Arch,
  Fedora, Ubuntu 22.04 and newer, Debian 12 and newer, openSUSE, ...).
  musl-based distros are not supported.
- The `alienware-wmi` kernel driver (mainline; fan control needs its
  hwmon, which landed in Linux 6.16). For game detection, the NVIDIA
  proprietary driver.
- For lighting, the system's `libusb-1.0` (Debian/Ubuntu `libusb-1.0-0`,
  Fedora `libusb1`, Arch `libusb`; desktop installs have it). The
  installer's summary says when it is missing.
- For `cryo-gui`, a desktop session: Qt uses the system's OpenGL/EGL,
  xkbcommon and fontconfig libraries, which any desktop install has.
- Network access during the install: the bundle is a net installer. It
  downloads about 300 MB: Python 3.13 (about 35 MB) and Cryo's
  dependencies (about 265 MB, mostly Qt). An upgrade that keeps the same
  Python and dependency versions downloads little or nothing.

No git, uv or pip is needed; the bundle carries its own `uv`.

## Download and verify

```sh
gh release download --repo I4cTime/cryo --pattern 'cryo-*-linux-x86_64.tar.gz' --pattern SHA256SUMS
sha256sum -c SHA256SUMS
gh attestation verify cryo-*-linux-x86_64.tar.gz --repo I4cTime/cryo
```

Without `gh`, download both files from the release page and run the
`sha256sum -c` line. The attestation proves the tarball was built by this
repository's release workflow from the tagged commit.

## Install

```sh
tar xf cryo-*-linux-x86_64.tar.gz
cd cryo-*/
sudo ./install.sh
```

Run it with sudo from your own account (not from a root shell): the
installer gives that account's primary group access to the daemon (see
[Socket access](#socket-access)). It refuses,
before changing anything, when it is not root, when it runs as root
directly, without systemd, on a non-x86_64 machine or on musl.

What it installs:

| Path | What |
| --- | --- |
| `/opt/cryo/env` | Cryo's Python environment |
| `/opt/cryo/python` | the Python Cryo runs on (uv-managed, never the system's) |
| `/opt/cryo/cache` | uv's download cache (makes upgrades faster) |
| `/opt/cryo/uninstall.sh`, `VERSION`, `LICENSE` | |
| `/usr/local/bin/cryoctl`, `/usr/local/bin/cryo-gui` | links into the environment, on every user's PATH |
| `/etc/systemd/system/cryod.service`, `cryod-resume.service` | enabled; `cryod` is restarted |
| `/usr/local/share/applications/cryo.desktop` | the menu entry |
| `/usr/local/share/icons/hicolor/*/apps/cryo.png`, `scalable/apps/cryo.svg` | icons |
| `/etc/cryo/config.json` | written only if missing: `{"socket_group": "<your group>"}` |
| `/var/lib/cryo` | daemon state |

How it builds the environment: the bundled `uv` downloads Python 3.13 into
`/opt/cryo/python` (reused on later runs while the bundle pins the same
version), creates `/opt/cryo/env.new` on it, installs the dependencies
from `requirements.txt` with `--require-hashes` (every file must match the
hash recorded in Cryo's lock file, and nothing is built from source),
installs the Cryo wheel, and checks that the new environment imports. Only
then is it swapped in as `/opt/cryo/env`. If any of that fails, the
installed Cryo and its units are left as they were. Cryo never uses the
system Python, so a distro upgrade to a new Python cannot break it. All
of uv's state stays under `/opt/cryo`; nothing is written to root's or
your home directory.

The installer ends with a summary that includes the daemon's state. On a
machine Cryo cannot drive, `cryod` exits with status 78 and stays stopped;
`cryoctl doctor` says why.

### Replacing a from-source install

Run over a from-source install (`packaging/install.sh`), the installer
says what it is replacing, points the units at `/opt/cryo`, and removes
your `~/.local/bin/cryoctl` and `~/.local/bin/cryo-gui` links and your
`~/.local/share/applications/cryo.desktop` entry, which would otherwise
shadow the system-wide ones. It leaves the checkout itself alone; delete it
when you no longer need it. `/etc/cryo` and `/var/lib/cryo` carry over.

## Upgrade

Download the newer bundle and run its `install.sh` the same way. The new
environment is built beside the running one, swapped in, and `cryod` is
restarted on it; `/etc/cryo` and `/var/lib/cryo` are kept.

If a newer bundle pins a different Python, the installer downloads it and
removes the old one once the new environment is running.

## Socket access

`cryod` listens on `/run/cryo.sock`, and members of the group named by
`socket_group` in `/etc/cryo/config.json` may use it (change the fans,
modes and lighting). The installer writes that file only when it does not
exist, with the primary group of the account that ran `sudo ./install.sh`.
On most distros that is a private group holding only that account; where
the primary group is a shared one such as `users`, every member of it gets
access. To change it, edit `socket_group` in `/etc/cryo/config.json`
(for example to a group only you are in) and run
`sudo systemctl restart cryod`.

## Uninstall

```sh
sudo /opt/cryo/uninstall.sh            # keeps /etc/cryo and /var/lib/cryo
sudo /opt/cryo/uninstall.sh --purge    # removes them too
```

`cryod` leaves the firmware where it last put it, so when the daemon is
running the uninstaller first hands the machine back to stock with the
same commands as the README (`cryoctl profile balanced`, `boost cpu 0`,
`boost gpu 0`, `cap 100`, skipping what the machine does not support).
When the daemon is not running it says how to do that by hand. It then
disables and removes both units and removes everything listed above. It
is safe to run twice, and the copy in the extracted bundle works too.

## From source

For working on Cryo itself:

```sh
git clone https://github.com/I4cTime/cryo.git && cd cryo
uv sync
sudo packaging/install.sh
```

This needs [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
on your user's PATH. It installs into the checkout's `.venv` (editable),
links `cryoctl` and `cryo-gui` into `~/.local/bin`, puts the icons and the
menu entry under `~/.local/share`, and points the systemd units at the
checkout, so the checkout must stay where it is. Update with `git pull`
and a rerun of `sudo packaging/install.sh`. The README's
[Uninstall](../README.md#uninstall) section removes it.

## Building the bundle

```sh
uv run --no-project tools/build_bundle.py            # dist/cryo-<version>-linux-x86_64.tar.gz + SHA256SUMS
tools/bundle_container_test.sh                        # install/upgrade/uninstall in Arch, Ubuntu, Fedora (podman)
```

The release workflow (`.github/workflows/release.yml`) runs the builder on
every `v*` tag, attests the tarball and attaches it to the release.
