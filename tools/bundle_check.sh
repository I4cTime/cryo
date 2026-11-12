#!/usr/bin/env bash
# Assertions after a bundle install, uninstall or purge. Used by the CI
# bundle job and tools/bundle_container_test.sh; run as root on a disposable
# machine (never on a machine with a real Cryo install you care about).
#
#   sudo tools/bundle_check.sh installed USER VERSION
#   sudo tools/bundle_check.sh uninstalled
#   sudo tools/bundle_check.sh purged
set -euo pipefail

PREFIX=/opt/cryo
UNITS=(cryod.service cryod-resume.service)
ICON_SIZES=(32 48 64 128 256 512)
FAILED=0

ok() { printf '  ok   %s\n' "$*"; }
bad() { printf '  FAIL %s\n' "$*"; FAILED=1; }
check() { local what=$1; shift; if "$@" >/dev/null 2>&1; then ok "$what"; else bad "$what"; fi; }

prop() { systemctl show cryod.service -p "$1" --value; }

leftovers() {
    # Anything the installer adds, outside /etc/cryo and /var/lib/cryo.
    local f
    for f in "$PREFIX" /usr/local/bin/cryoctl /usr/local/bin/cryo-gui \
        /usr/local/share/applications/cryo.desktop \
        /usr/local/share/icons/hicolor/scalable/apps/cryo.svg \
        /etc/systemd/system/cryod.service /etc/systemd/system/cryod-resume.service; do
        [[ -e $f || -L $f ]] && echo "$f"
    done
    for f in "${ICON_SIZES[@]}"; do
        f=/usr/local/share/icons/hicolor/${f}x${f}/apps/cryo.png
        [[ -e $f ]] && echo "$f"
    done
    find /etc/systemd/system -name 'cryod*' 2>/dev/null
    return 0
}

installed() {
    local user=$1 version=$2 unit status
    echo "== installed ($version, user $user)"
    check "$PREFIX/env/bin/python exists" test -x "$PREFIX/env/bin/python"
    check "the environment runs on a managed Python in $PREFIX/python" \
        grep -q "^home = $PREFIX/python/cpython-" "$PREFIX/env/pyvenv.cfg"
    check "$PREFIX/VERSION is $version" grep -qx "$version" "$PREFIX/VERSION"
    check "$PREFIX/uninstall.sh is executable" test -x "$PREFIX/uninstall.sh"
    check "no env.new or env.old left" bash -c "! compgen -G '$PREFIX/env.*'"
    check "no installer work dir left" bash -c "! compgen -G '$PREFIX/.install.*'"
    for unit in "${UNITS[@]}"; do
        check "$unit is enabled" systemctl is-enabled --quiet "$unit"
        check "$unit runs $PREFIX/env/bin/python" grep -q "^ExecStart=$PREFIX/env/bin/python " "/etc/systemd/system/$unit"
    done
    check "cryoctl --help from /usr/local/bin as $user" \
        runuser -u "$user" -- env -i PATH=/usr/local/bin:/usr/bin:/bin cryoctl --help
    check "cryoctl --version is $version" \
        bash -c "runuser -u '$user' -- env -i PATH=/usr/local/bin:/usr/bin:/bin cryoctl --version | grep -qx 'cryoctl $version'"
    check "cryo-gui link points into $PREFIX" bash -c "[[ \$(readlink /usr/local/bin/cryo-gui) == $PREFIX/env/bin/cryo-gui ]]"
    check "desktop entry runs /usr/local/bin/cryo-gui" grep -qx 'Exec=/usr/local/bin/cryo-gui' /usr/local/share/applications/cryo.desktop
    check "256 px and scalable icons installed" test -f /usr/local/share/icons/hicolor/256x256/apps/cryo.png -a -f /usr/local/share/icons/hicolor/scalable/apps/cryo.svg
    check "config.json grants group $(id -gn "$user")" grep -q "\"socket_group\": \"$(id -gn "$user")\"" /etc/cryo/config.json
    check "/var/lib/cryo exists" test -d /var/lib/cryo
    # Unsupported hardware: one start, exit 78, no restarts.
    sleep 3
    status=$(prop ExecMainStatus)
    if [[ $status == 78 ]]; then ok "cryod ExecMainStatus=78"; else bad "cryod ExecMainStatus=$status (want 78)"; fi
    local active restarts
    active=$(prop ActiveState) restarts=$(prop NRestarts)
    if [[ $active == failed && $restarts == 0 ]]; then
        ok "cryod is not restarting (ActiveState=$active, NRestarts=$restarts)"
    else
        bad "cryod ActiveState=$active NRestarts=$restarts (want failed, 0)"
    fi
}

uninstalled() {
    echo "== uninstalled (settings kept)"
    local left
    left=$(leftovers)
    if [[ -z $left ]]; then ok "nothing left outside /etc/cryo and /var/lib/cryo"; else bad "left behind: $left"; fi
    check "systemd no longer knows cryod" bash -c "[[ \$(systemctl show cryod.service -p LoadState --value) == not-found ]]"
    check "/etc/cryo/config.json kept" test -f /etc/cryo/config.json
    check "/var/lib/cryo kept" test -d /var/lib/cryo
}

purged() {
    echo "== purged"
    local left
    left=$(leftovers)
    if [[ -z $left ]]; then ok "nothing left"; else bad "left behind: $left"; fi
    check "/etc/cryo removed" test ! -e /etc/cryo
    check "/var/lib/cryo removed" test ! -e /var/lib/cryo
}

[[ $EUID -eq 0 ]] || { echo "bundle_check: run as root" >&2; exit 2; }
case ${1:-} in
    installed) installed "${2:?user}" "${3:?version}" ;;
    uninstalled) uninstalled ;;
    purged) purged ;;
    *) echo "usage: $0 installed USER VERSION | uninstalled | purged" >&2; exit 2 ;;
esac
exit "$FAILED"
