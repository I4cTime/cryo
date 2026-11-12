#!/usr/bin/env bash
# Cryo bundle installer: puts Cryo in /opt/cryo with its own Python
# environment, links cryoctl and cryo-gui into /usr/local/bin, installs the
# systemd units, icons and the menu entry, and starts cryod.
#
#   sudo ./install.sh          (from the extracted cryo-<version> directory)
#
# Rerun it from a newer bundle to upgrade in place; /etc/cryo and
# /var/lib/cryo are kept. Uninstall with: sudo /opt/cryo/uninstall.sh
# The from-source developer install is packaging/install.sh in the repo.
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

# Cryo always runs on this uv-managed Python in /opt/cryo/python, never on
# the system one: a distro's Python upgrade must not break the environment.
# tools/build_bundle.py checks that the lock has wheels for this version.
MANAGED_PYTHON=3.13
# Oldest glibc the pinned PySide6 wheels (manylinux_2_34) run on.
GLIBC_MIN=2.34
# cryod's exit status on hardware it cannot drive (RestartPreventExitStatus).
UNSUPPORTED_STATUS=78

say() { printf '>> %s\n' "$*"; }
note() { printf '   %s\n' "$*"; }
die() { printf 'cryo install: %s\n' "$*" >&2; exit 1; }

# version_ge A B: true when dotted version A >= B (major.minor).
version_ge() {
    local -a a b
    IFS=. read -r -a a <<<"$1"
    IFS=. read -r -a b <<<"$2"
    (( a[0] > b[0] || (a[0] == b[0] && ${a[1]:-0} >= ${b[1]:-0}) ))
}

# Prints "glibc X.Y", "musl" or "unknown".
detect_libc() {
    local v
    if v=$(getconf GNU_LIBC_VERSION 2>/dev/null) && [[ $v == "glibc "* ]]; then
        echo "$v"
    elif compgen -G '/lib/ld-musl-*.so.1' >/dev/null \
        || { ldd --version 2>&1 || true; } | grep -qi musl; then
        echo musl
    else
        echo unknown
    fi
}

# refusal_reason EUID SUDO_USER ARCH LIBC SYSTEMD(yes|no)
# Prints the refusal for the first precondition that fails, nothing if all hold.
refusal_reason() {
    local euid=$1 sudo_user=$2 arch=$3 libc=$4 systemd=$5
    if [[ $euid -ne 0 ]]; then
        echo "must run as root: sudo ./install.sh"
    elif [[ -z $sudo_user || $sudo_user == root ]]; then
        echo "run it with sudo from your own account, not as root directly: the installer grants that account access to cryod"
    elif [[ $arch != x86_64 ]]; then
        echo "this bundle is for x86_64 and this machine is $arch"
    elif [[ $libc == musl ]]; then
        echo "this bundle needs glibc; musl-based systems are not supported"
    elif [[ $libc != "glibc "* ]]; then
        echo "could not find glibc (glibc $GLIBC_MIN or newer is required)"
    elif ! version_ge "${libc#glibc }" "$GLIBC_MIN"; then
        echo "glibc ${libc#glibc } is too old; Cryo's Qt needs glibc $GLIBC_MIN or newer"
    elif [[ $systemd != yes ]]; then
        echo "systemd is not running (no /run/systemd/system); cryod runs as a systemd service"
    fi
}

# bundle_problem DIR: prints what is missing from an extracted bundle, nothing if complete.
bundle_problem() {
    local dir=$1 f version
    for f in VERSION requirements.txt bin/uv uninstall.sh LICENSE \
        share/cryod.service share/cryod-resume.service share/mark.svg; do
        [[ -f $dir/$f ]] || { echo "$f"; return; }
    done
    for f in "${ICON_SIZES[@]}"; do
        [[ -f $dir/share/icons/cryo-$f.png ]] || { echo "share/icons/cryo-$f.png"; return; }
    done
    version=$(<"$dir/VERSION")
    [[ -f $dir/wheels/cryo-$version-py3-none-any.whl ]] \
        || echo "wheels/cryo-$version-py3-none-any.whl"
}

# render_unit TEMPLATE PYTHON: the unit with @PYTHON@ replaced.
render_unit() {
    sed "s|@PYTHON@|$2|g" "$1"
}

# desktop_entry EXEC
desktop_entry() {
    cat <<EOF
[Desktop Entry]
Type=Application
Name=Cryo
Comment=Command center for Alienware and Dell G-Series laptops
Exec=$1
Icon=cryo
Terminal=false
Categories=Utility;System;Settings;
StartupWMClass=cryo
EOF
}

# unit_exec FILE: the program of the unit's first ExecStart.
unit_exec() {
    sed -n 's/^ExecStart=[-@+!:]*\([^ ]*\).*/\1/p' "$1" | head -n 1
}

# is_foreign_unit FILE: an installed unit that runs something outside PREFIX.
is_foreign_unit() {
    local prog
    prog=$(unit_exec "$1")
    [[ -n $prog && $prog != "$PREFIX"/* ]]
}

# is_stale_user_desktop FILE: a per-user entry whose Exec is an absolute path
# outside /usr/local and /opt (a from-source checkout), which would shadow ours.
is_stale_user_desktop() {
    local prog
    prog=$(sed -n 's/^Exec=\([^ ]*\).*/\1/p' "$1" | head -n 1)
    [[ $prog == /* && $prog != /usr/local/* && $prog != /opt/* ]]
}

# Every uv call: the bundled binary, a scrubbed environment, and all uv state
# (cache, managed Pythons, config, homes) under PREFIX, so nothing lands in
# root's or the user's home and no uv.toml on this machine changes the result.
run_uv() {
    local -a pass=()
    local v
    for v in http_proxy https_proxy no_proxy HTTP_PROXY HTTPS_PROXY NO_PROXY ALL_PROXY \
        SSL_CERT_FILE SSL_CERT_DIR; do
        [[ -n ${!v:-} ]] && pass+=("$v=${!v}")
    done
    (cd "$WORK_DIR" && env -i "${pass[@]}" \
        PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin \
        LANG=C.UTF-8 \
        HOME="$WORK_DIR/home" \
        XDG_CACHE_HOME="$WORK_DIR/home/.cache" \
        XDG_CONFIG_HOME="$WORK_DIR/home/.config" \
        XDG_DATA_HOME="$WORK_DIR/home/.local/share" \
        XDG_STATE_HOME="$WORK_DIR/home/.local/state" \
        XDG_BIN_HOME="$WORK_DIR/home/.local/bin" \
        UV_CACHE_DIR="$PREFIX/cache" \
        UV_PYTHON_INSTALL_DIR="$PREFIX/python" \
        UV_PYTHON_BIN_DIR="$PREFIX/python/bin" \
        UV_TOOL_DIR="$WORK_DIR/tools" \
        UV_TOOL_BIN_DIR="$WORK_DIR/tools/bin" \
        UV_NO_CONFIG=1 \
        UV_NO_PROGRESS=1 \
        "$WORK_DIR/uv" "$@")
}

# Sets PYTHON (the interpreter env.new is built on) and PYTHON_DESC. An
# interpreter already in /opt/cryo/python is reused; uv downloads it otherwise.
choose_python() {
    if ! PYTHON=$(run_uv python find --no-project --managed-python "$MANAGED_PYTHON" 2>/dev/null); then
        say "Downloading Python $MANAGED_PYTHON into $PREFIX/python"
        run_uv python install --quiet --no-bin "$MANAGED_PYTHON"
        PYTHON=$(run_uv python find --no-project --managed-python "$MANAGED_PYTHON")
    fi
    PYTHON_DESC="Python $("$PYTHON" -c 'import platform; print(platform.python_version())') in $PREFIX/python"
}

# prune_pythons: remove managed interpreters the environment does not use
# (left behind when MANAGED_PYTHON changes between bundles).
prune_pythons() {
    local home keep entry
    home=$(sed -n 's/^home = //p' "$PREFIX/env/pyvenv.cfg")
    keep=$(realpath -e -- "$home/..") || return 0
    for entry in "$PREFIX"/python/cpython-*; do
        [[ -e $entry || -L $entry ]] || continue
        if [[ $(realpath -e -- "$entry" 2>/dev/null) != "$keep" ]]; then
            say "Removing the unused $entry"
            rm -rf -- "$entry"
        fi
    done
}

# daemon_state: "running", "unsupported", or a short description, after
# giving a freshly restarted cryod a few seconds to settle. "running" means
# the same process stayed up for 3 s with no automatic restart in between.
daemon_state() {
    local i key value active sub status restarts pid first_pid=''
    for i in $(seq 1 20); do
        sleep 0.5
        active='' sub='' status='' restarts='' pid=''
        while IFS='=' read -r key value; do
            case $key in
                ActiveState) active=$value ;;
                SubState) sub=$value ;;
                ExecMainStatus) status=$value ;;
                NRestarts) restarts=$value ;;
                MainPID) pid=$value ;;
            esac
        done < <(systemctl show cryod.service -p ActiveState -p SubState -p ExecMainStatus -p NRestarts -p MainPID)
        if [[ $active == failed || $active == inactive ]]; then
            if [[ $status == "$UNSUPPORTED_STATUS" ]]; then
                echo unsupported
            else
                echo "stopped (exit status $status)"
            fi
            return
        fi
        if [[ $active == active && $sub == running && $pid != 0 ]]; then
            [[ -n $first_pid ]] || first_pid=$pid
            if [[ $pid != "$first_pid" || ${restarts:-0} != 0 ]]; then
                echo "crashing and restarting"
                return
            fi
            (( i >= 6 )) && { echo running; return; }
        fi
    done
    if [[ ${restarts:-0} != 0 || $sub == auto-restart ]]; then
        echo "crashing and restarting"
    else
        echo "$active/$sub after 10 s"
    fi
}

PHASE=preflight
FRESH=no
WORK_DIR=
on_exit() {
    local rc=$?
    [[ -n $WORK_DIR ]] && rm -rf -- "$WORK_DIR"
    (( rc == 0 )) && return
    case $PHASE in
        build)
            rm -rf -- "$PREFIX/env.new"
            if [[ $FRESH == yes ]]; then
                rm -rf -- "$PREFIX"
                printf 'cryo install: FAILED while building the environment; nothing was installed.\n' >&2
            else
                printf 'cryo install: FAILED while building the new environment; the installed Cryo (%s/env) and its units were left untouched.\n' "$PREFIX" >&2
            fi
            ;;
        swap | system)
            if [[ -d $PREFIX/env.old ]]; then
                rm -rf -- "$PREFIX/env" "$PREFIX/env.new"
                mv -- "$PREFIX/env.old" "$PREFIX/env"
                printf 'cryo install: FAILED while installing the system files; rolled back to the previous environment.\n' >&2
            else
                printf 'cryo install: FAILED while installing the system files; rerun the installer, or remove what it added with sudo %s/uninstall.sh\n' "$PREFIX" >&2
            fi
            ;;
    esac
}

main() {
    umask 022
    local bundle reason missing version previous unit prog home c path desktop state
    bundle=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

    local systemd=no
    [[ -d /run/systemd/system ]] && systemd=yes
    reason=$(refusal_reason "$EUID" "${SUDO_USER:-}" "$(uname -m)" "$(detect_libc)" "$systemd")
    [[ -z $reason ]] || die "$reason"
    missing=$(bundle_problem "$bundle")
    [[ -z $missing ]] || die "run install.sh from the extracted cryo-<version> bundle ($missing is missing next to it)"

    local user=$SUDO_USER group
    group=$(id -gn "$user")
    version=$(<"$bundle/VERSION")
    local wheel="$bundle/wheels/cryo-$version-py3-none-any.whl"

    trap on_exit EXIT

    if [[ -f $PREFIX/VERSION && -d $PREFIX/env ]]; then
        previous=$(<"$PREFIX/VERSION")
        say "Upgrading Cryo $previous to $version in $PREFIX"
    else
        say "Installing Cryo $version into $PREFIX"
    fi
    local -a foreign=()
    for unit in "${UNITS[@]}"; do
        if [[ -f $UNIT_DIR/$unit ]] && is_foreign_unit "$UNIT_DIR/$unit"; then
            foreign+=("$unit")
            prog=$(unit_exec "$UNIT_DIR/$unit")
            say "Replacing an existing install: $UNIT_DIR/$unit runs $prog"
        fi
    done
    if (( ${#foreign[@]} )); then
        prog=$(unit_exec "$UNIT_DIR/${foreign[0]}")
        if [[ $prog == */.venv/bin/* ]]; then
            note "The from-source checkout at ${prog%%/.venv/bin/*} is left in place; delete it when you no longer need it."
        fi
    fi

    # 1. Build the new environment beside the current one. Nothing outside
    #    PREFIX changes until it imports cleanly.
    PHASE=build
    [[ -d $PREFIX/env ]] || FRESH=yes
    mkdir -p "$PREFIX"
    WORK_DIR=$(mktemp -d "$PREFIX/.install.XXXXXX")
    mkdir -p "$WORK_DIR/home"
    # Copied so a bundle extracted on a noexec mount still works.
    install -m 755 "$bundle/bin/uv" "$WORK_DIR/uv"
    rm -rf -- "$PREFIX/env.new"

    choose_python
    say "Creating the environment with $PYTHON_DESC"
    run_uv venv --quiet --relocatable --no-project --python "$PYTHON" "$PREFIX/env.new"
    say "Installing dependencies (hash-checked against the lock; PySide6 is a large download)"
    run_uv pip install --python "$PREFIX/env.new/bin/python" \
        --require-hashes --no-build -r "$bundle/requirements.txt"
    run_uv pip install --python "$PREFIX/env.new/bin/python" --no-deps --no-build "$wheel"
    local got
    got=$("$PREFIX/env.new/bin/python" -B -c 'import cryo, cryo.cli; print(cryo.__version__)') \
        || die "the new environment cannot import cryo"
    [[ $got == "$version" ]] || die "the new environment has cryo $got, expected $version"
    # pyusb drives the lighting controller through the system libusb-1.0.
    local libusb=yes
    "$PREFIX/env.new/bin/python" -B -c \
        'import sys, usb.backend.libusb1 as b; sys.exit(0 if b.get_backend() else 1)' 2>/dev/null \
        || libusb=no

    # 2. Swap it into place; the previous one stays as env.old until the
    #    daemon has restarted on the new one.
    PHASE=swap
    rm -rf -- "$PREFIX/env.old"
    [[ -d $PREFIX/env ]] && mv -- "$PREFIX/env" "$PREFIX/env.old"
    mv -- "$PREFIX/env.new" "$PREFIX/env"
    PHASE=system
    # Byte-compile at the final path so the GUI (run as a user who cannot
    # write here) starts fast and tracebacks name /opt/cryo/env.
    "$PREFIX/env/bin/python" -m compileall -q -j 0 "$PREFIX/env/lib" >/dev/null 2>&1 || true
    install -m 755 "$bundle/uninstall.sh" "$PREFIX/uninstall.sh"
    install -m 644 "$bundle/VERSION" "$PREFIX/VERSION"
    install -m 644 "$bundle/LICENSE" "$PREFIX/LICENSE"

    say "Linking ${COMMANDS[*]} into $BIN_DIR"
    mkdir -p "$BIN_DIR"
    for c in "${COMMANDS[@]}"; do
        if [[ -e $BIN_DIR/$c && ! -L $BIN_DIR/$c ]]; then
            note "replacing the existing $BIN_DIR/$c"
        fi
        ln -sfn "$PREFIX/env/bin/$c" "$BIN_DIR/$c"
    done

    say "Installing icons and the menu entry"
    for c in "${ICON_SIZES[@]}"; do
        install -D -m 644 "$bundle/share/icons/cryo-$c.png" "$ICON_ROOT/${c}x${c}/apps/cryo.png"
    done
    install -D -m 644 "$bundle/share/mark.svg" "$ICON_ROOT/scalable/apps/cryo.svg"
    mkdir -p "$APP_DIR"
    desktop_entry "$BIN_DIR/cryo-gui" >"$APP_DIR/cryo.desktop"
    chmod 644 "$APP_DIR/cryo.desktop"
    if command -v gtk-update-icon-cache >/dev/null; then
        gtk-update-icon-cache -q -t -f "$ICON_ROOT" >/dev/null 2>&1 || true
    fi
    if command -v update-desktop-database >/dev/null; then
        update-desktop-database -q "$APP_DIR" >/dev/null 2>&1 || true
    fi

    mkdir -p "$CONF_DIR" "$STATE_DIR"
    if [[ -f $CONF_DIR/config.json ]]; then
        say "Keeping $CONF_DIR/config.json"
    else
        say "Writing $CONF_DIR/config.json (socket access for group $group)"
        printf '{"socket_group": "%s"}\n' "$group" >"$CONF_DIR/config.json"
    fi

    say "Installing the systemd units"
    for unit in "${UNITS[@]}"; do
        render_unit "$bundle/share/$unit" "$PREFIX/env/bin/python" >"$UNIT_DIR/$unit.new"
        chmod 644 "$UNIT_DIR/$unit.new"
        mv -- "$UNIT_DIR/$unit.new" "$UNIT_DIR/$unit"
    done
    systemctl daemon-reload
    systemctl enable --quiet "${UNITS[@]}"

    # A from-source install left links and a menu entry in the user's home
    # that would shadow the system-wide ones.
    home=$(getent passwd "$user" | cut -d: -f6)
    if [[ -n $home && -d $home ]]; then
        for c in "${COMMANDS[@]}"; do
            path="$home/.local/bin/$c"
            if [[ -L $path ]]; then
                say "Removing $path (an old per-user link that would shadow $BIN_DIR/$c)"
                sudo -u "$user" rm -f -- "$path"
            fi
        done
        desktop="$home/.local/share/applications/cryo.desktop"
        if [[ -f $desktop && ! -L $desktop ]] && is_stale_user_desktop "$desktop"; then
            say "Removing $desktop (an old per-user menu entry that would shadow $APP_DIR/cryo.desktop)"
            sudo -u "$user" rm -f -- "$desktop"
        fi
    fi

    say "Restarting cryod"
    systemctl restart cryod.service
    state=$(daemon_state)
    PHASE=finished
    rm -rf -- "$PREFIX/env.old"
    prune_pythons
    run_uv cache prune --quiet >/dev/null 2>&1 || true

    echo
    echo "Cryo $version is installed."
    note "Program:   $PREFIX ($PYTHON_DESC)"
    note "Commands:  $BIN_DIR/cryoctl, $BIN_DIR/cryo-gui"
    note "Menu:      $APP_DIR/cryo.desktop"
    note "Services:  ${UNITS[*]} (enabled)"
    note "Config:    $CONF_DIR/config.json, state in $STATE_DIR"
    case $state in
        running) note "Daemon:    running (cryoctl status)" ;;
        unsupported) note "Daemon:    this machine is not supported: cryod exited with status $UNSUPPORTED_STATUS; run cryoctl doctor" ;;
        *) note "Daemon:    $state; see journalctl -u cryod" ;;
    esac
    if [[ $libusb == no ]]; then
        note "Note:      lighting needs libusb-1.0, which is not installed. Install it"
        note "           (Debian/Ubuntu: libusb-1.0-0, Fedora: libusb1, Arch: libusb), then run"
        note "           sudo systemctl restart cryod"
    fi
    note "Uninstall: sudo $PREFIX/uninstall.sh (add --purge to also remove $CONF_DIR and $STATE_DIR)"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
