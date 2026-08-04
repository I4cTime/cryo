#!/usr/bin/env bash
# Cryo installer — personal machine, personal assumptions.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo $0" >&2
    exit 1
fi

REAL_USER="${SUDO_USER:-i4cdeath}"

echo ">> Syncing venv (as $REAL_USER)"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
sudo -u "$REAL_USER" env PATH="$REAL_HOME/.local/bin:$PATH" \
    bash -c "cd '$REPO_DIR' && uv sync"

echo ">> Writing default config with socket_group=$REAL_USER"
mkdir -p /etc/cryo /var/lib/cryo
if [[ ! -f /etc/cryo/config.json ]]; then
    echo "{\"socket_group\": \"$REAL_USER\"}" > /etc/cryo/config.json
fi

echo ">> Installing systemd unit"
cp "$REPO_DIR/packaging/cryod.service" /etc/systemd/system/cryod.service
systemctl daemon-reload
systemctl enable --now cryod.service

echo ">> Installing desktop entry"
sudo -u "$REAL_USER" mkdir -p "/home/$REAL_USER/.local/share/applications"
cat > "/home/$REAL_USER/.local/share/applications/cryo.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Cryo
Comment=Alienware m18 R2 command center
Exec=$REPO_DIR/.venv/bin/cryo-gui
Icon=preferences-system
Terminal=false
Categories=Utility;System;Settings;
EOF
chown "$REAL_USER:" "/home/$REAL_USER/.local/share/applications/cryo.desktop"

echo ">> Done. Daemon: systemctl status cryod | GUI: cryo-gui | CLI: cryoctl status"
