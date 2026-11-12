#!/usr/bin/env bash
# Cryo bundle uninstaller: removes what install.sh added. Keeps /etc/cryo and
# /var/lib/cryo unless --purge is given. Safe to run more than once.
#
#   sudo /opt/cryo/uninstall.sh [--purge]
set -euo pipefail

PREFIX=/opt/cryo
BIN_DIR=/usr/local/bin
UNIT_DIR=/etc/systemd/system
APP_DIR=/usr/local/share/applications
ICON_ROOT=/usr/local/share/icons/hicolor
CONF_DIR=/etc/cryo
STATE_DIR=/var/lib/cryo
UNITS=(cryod.service cryod-resume.service)
COMMANDS=(cryoctl cryo-gui)
ICON_SIZES=(32 48 64 128 256 512)
UNSUPPORTED_STATUS=78
# The README's hand-back-to-stock commands.
STOCK=("profile balanced" "boost cpu 0" "boost gpu 0" "cap 100")

USAGE="usage: sudo $PREFIX/uninstall.sh [--purge]
  --purge   also remove $CONF_DIR (settings) and $STATE_DIR (daemon state)"

say() { printf '>> %s\n' "$*"; }
note() { printf '   %s\n' "$*"; }
die() { printf 'cryo uninstall: %s\n' "$*" >&2; exit 1; }

# unit_exec FILE: the program of the unit's first ExecStart.
unit_exec() {
    sed -n 's/^ExecStart=[-@+!:]*\([^ ]*\).*/\1/p' "$1" | head -n 1
}

# is_ours FILE: a unit this bundle installed (it runs a program in PREFIX).
is_ours() {
    [[ $(unit_exec "$1") == "$PREFIX"/* ]]
}

hand_back_to_stock() {
    local cryoctl=$PREFIX/env/bin/cryoctl status cmd
    status=$(systemctl show cryod.service -p ExecMainStatus --value 2>/dev/null || true)
    if [[ -x $cryoctl ]] && systemctl is-active --quiet cryod.service \
        && timeout 10 "$cryoctl" status --json >/dev/null 2>&1; then
        say "Handing the firmware back to stock"
        for cmd in "${STOCK[@]}"; do
            # shellcheck disable=SC2086  # each entry is a word list on purpose
            if timeout 10 "$cryoctl" $cmd >/dev/null 2>&1; then
                note "cryoctl $cmd"
            else
                note "cryoctl $cmd (not supported here, skipped)"
            fi
        done
    elif [[ $status == "$UNSUPPORTED_STATUS" ]]; then
        say "cryod never ran on this machine (unsupported), so there is nothing to hand back"
    else
        say "cryod is not running, so the firmware stays where Cryo last put it"
        note "To hand it back to stock first, start cryod (sudo systemctl start cryod), run"
        note "  cryoctl profile balanced && cryoctl boost cpu 0 && cryoctl boost gpu 0 && cryoctl cap 100"
        note "(skip what cryoctl doctor says is unsupported), then run this uninstaller again."
    fi
}

main() {
    local purge=no arg unit c link removed_units=no
    for arg in "$@"; do
        case $arg in
            --purge) purge=yes ;;
            -h | --help) echo "$USAGE"; return 0 ;;
            *) printf '%s\n' "$USAGE" >&2; exit 2 ;;
        esac
    done
    [[ $EUID -eq 0 ]] || die "must run as root: sudo $PREFIX/uninstall.sh"

    local -a ours=()
    for unit in "${UNITS[@]}"; do
        if [[ -f $UNIT_DIR/$unit ]]; then
            if is_ours "$UNIT_DIR/$unit"; then
                ours+=("$unit")
            else
                say "Leaving $UNIT_DIR/$unit: it runs $(unit_exec "$UNIT_DIR/$unit"), not this install"
            fi
        fi
    done

    if [[ -d /run/systemd/system ]] && (( ${#ours[@]} )); then
        hand_back_to_stock
        say "Stopping and removing ${ours[*]}"
        systemctl disable --now --quiet "${ours[@]}" 2>/dev/null || true
        for unit in "${ours[@]}"; do
            rm -f -- "$UNIT_DIR/$unit"
        done
        removed_units=yes
    elif (( ${#ours[@]} )); then
        for unit in "${ours[@]}"; do
            rm -f -- "$UNIT_DIR/$unit"
        done
    fi
    if [[ -d /run/systemd/system && $removed_units == yes ]]; then
        systemctl daemon-reload
        systemctl reset-failed "${UNITS[@]}" 2>/dev/null || true
    fi

    say "Removing the commands, menu entry and icons"
    for c in "${COMMANDS[@]}"; do
        link=$BIN_DIR/$c
        if [[ -L $link && $(readlink "$link") == "$PREFIX"/* ]]; then
            rm -f -- "$link"
        fi
    done
    if [[ -f $APP_DIR/cryo.desktop ]] && grep -qx "Exec=$BIN_DIR/cryo-gui" "$APP_DIR/cryo.desktop"; then
        rm -f -- "$APP_DIR/cryo.desktop"
    fi
    for c in "${ICON_SIZES[@]}"; do
        rm -f -- "$ICON_ROOT/${c}x${c}/apps/cryo.png"
    done
    rm -f -- "$ICON_ROOT/scalable/apps/cryo.svg"
    if command -v gtk-update-icon-cache >/dev/null && [[ -d $ICON_ROOT ]]; then
        gtk-update-icon-cache -q -t -f "$ICON_ROOT" >/dev/null 2>&1 || true
    fi
    if command -v update-desktop-database >/dev/null && [[ -d $APP_DIR ]]; then
        update-desktop-database -q "$APP_DIR" >/dev/null 2>&1 || true
    fi

    if [[ -d $PREFIX ]]; then
        say "Removing $PREFIX"
        rm -rf -- "$PREFIX"
    fi

    if [[ $purge == yes ]]; then
        say "Purging $CONF_DIR and $STATE_DIR"
        rm -rf -- "$CONF_DIR" "$STATE_DIR"
    fi

    echo
    echo "Cryo is uninstalled."
    if [[ $purge == yes ]]; then
        note "Settings and daemon state were removed too."
    else
        note "Kept your settings in $CONF_DIR and daemon state in $STATE_DIR;"
        note "remove them with: sudo rm -r $CONF_DIR $STATE_DIR"
    fi
}

# Everything runs from main, which bash has fully read before it starts, so
# deleting this file along with $PREFIX is safe.
main "$@"
