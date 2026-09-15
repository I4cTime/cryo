#!/usr/bin/env bash
# Cryo installer — sets up the venv, /etc/cryo, the systemd unit, CLI symlinks, icons and a .desktop entry.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo $0" >&2
    exit 1
fi

if [[ -z "${SUDO_USER:-}" || "$SUDO_USER" == "root" ]]; then
    echo "Run via sudo from your own account (not as root directly): sudo $0" >&2
    echo "The installer links cryoctl/cryo-gui into that user's ~/.local/bin and grants it socket access." >&2
    exit 1
fi
REAL_USER="$SUDO_USER"

echo ">> Syncing venv (as $REAL_USER)"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
sudo -u "$REAL_USER" env PATH="$REAL_HOME/.local/bin:$PATH" \
    bash -c "cd '$REPO_DIR' && uv sync"

echo ">> Linking CLIs into $REAL_HOME/.local/bin"
sudo -u "$REAL_USER" mkdir -p "$REAL_HOME/.local/bin"
sudo -u "$REAL_USER" ln -sf "$REPO_DIR/.venv/bin/cryoctl" "$REAL_HOME/.local/bin/cryoctl"
sudo -u "$REAL_USER" ln -sf "$REPO_DIR/.venv/bin/cryo-gui" "$REAL_HOME/.local/bin/cryo-gui"

echo ">> Writing default config with socket_group=$REAL_USER"
mkdir -p /etc/cryo /var/lib/cryo
if [[ ! -f /etc/cryo/config.json ]]; then
    echo "{\"socket_group\": \"$REAL_USER\"}" > /etc/cryo/config.json
fi

echo ">> Installing systemd units"
for unit in cryod.service cryod-resume.service; do
    sed "s|@PYTHON@|$REPO_DIR/.venv/bin/python|" \
        "$REPO_DIR/packaging/$unit" > "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable cryod.service cryod-resume.service
# restart (not enable --now): a re-run is the documented update path and
# must put the freshly synced code into the running daemon.
systemctl restart cryod.service

echo ">> Installing icons"
for size in 32 48 64 128 256 512; do
    icon_dir="$REAL_HOME/.local/share/icons/hicolor/${size}x${size}/apps"
    sudo -u "$REAL_USER" mkdir -p "$icon_dir"
    sudo -u "$REAL_USER" cp "$REPO_DIR/assets/icons/cryo-$size.png" "$icon_dir/cryo.png"
done
scalable_dir="$REAL_HOME/.local/share/icons/hicolor/scalable/apps"
sudo -u "$REAL_USER" mkdir -p "$scalable_dir"
sudo -u "$REAL_USER" cp "$REPO_DIR/assets/brand/mark.svg" "$scalable_dir/cryo.svg"

echo ">> Installing desktop entry"
sudo -u "$REAL_USER" mkdir -p "$REAL_HOME/.local/share/applications"
cat > "$REAL_HOME/.local/share/applications/cryo.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Cryo
Comment=Command center for Alienware and Dell G-Series laptops
Exec=$REPO_DIR/.venv/bin/cryo-gui
Icon=cryo
Terminal=false
Categories=Utility;System;Settings;
StartupWMClass=cryo
EOF
chown "$REAL_USER:" "$REAL_HOME/.local/share/applications/cryo.desktop"

echo ">> Done. Daemon: systemctl status cryod | GUI: cryo-gui | CLI: cryoctl status"
