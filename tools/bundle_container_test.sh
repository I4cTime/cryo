#!/usr/bin/env bash
# Install, upgrade and uninstall the release bundle inside rootless podman
# containers running systemd (Arch, Ubuntu LTS, Fedora), as an unprivileged
# user with sudo. Nothing runs on the host but podman.
#
#   uv run --no-project tools/build_bundle.py --out dist
#   tools/bundle_container_test.sh [--keep] [arch] [ubuntu] [fedora]
#
# BUNDLE=path/to/cryo-<version>-linux-x86_64.tar.gz overrides the newest one
# in dist/. Logs go to $LOG_DIR (default: a new temp dir). Extra scenarios:
# arch takes over a fake from-source install first (Acceptance 4); ubuntu
# runs a tampered requirements.txt on a fresh machine and over an install
# (Acceptance 6). Containers and images are removed at the end unless --keep.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
KEEP=no
DISTROS=()
for arg in "$@"; do
    case $arg in
        --keep) KEEP=yes ;;
        arch | ubuntu | fedora) DISTROS+=("$arg") ;;
        *) echo "usage: $0 [--keep] [arch] [ubuntu] [fedora]" >&2; exit 2 ;;
    esac
done
(( ${#DISTROS[@]} )) || DISTROS=(arch ubuntu fedora)

if [[ -z ${BUNDLE:-} ]]; then
    BUNDLE=$(find "$REPO/dist" -maxdepth 1 -name 'cryo-*-linux-x86_64.tar.gz' -printf '%T@ %p\n' 2>/dev/null \
        | sort -n | tail -n 1 | cut -d' ' -f2-)
fi
[[ -f ${BUNDLE:-} ]] || { echo "no bundle: build one with tools/build_bundle.py or set BUNDLE" >&2; exit 2; }
BUNDLE=$(realpath "$BUNDLE")
TARBALL=$(basename "$BUNDLE")
VERSION=${TARBALL#cryo-}
VERSION=${VERSION%-linux-x86_64.tar.gz}
DIR=cryo-$VERSION
LOG_DIR=${LOG_DIR:-$(mktemp -d -t cryo-bundle-test.XXXXXX)}
mkdir -p "$LOG_DIR"
echo "bundle $BUNDLE, logs in $LOG_DIR"

containerfile() {
    case $1 in
        arch) cat <<'EOF'
FROM docker.io/library/archlinux:latest
RUN pacman -Syu --noconfirm --needed sudo python && pacman -Scc --noconfirm
EOF
            ;;
        ubuntu) cat <<'EOF'
FROM docker.io/library/ubuntu:24.04
RUN apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
        systemd systemd-sysv sudo ca-certificates
EOF
            ;;
        fedora) cat <<'EOF'
FROM registry.fedoraproject.org/fedora:latest
RUN dnf -y install systemd sudo python3 util-linux && dnf clean all
EOF
            ;;
    esac
    # Ubuntu's image ships an "ubuntu" user with uid 1000; the tester gets its own.
    cat <<'EOF'
RUN useradd -m tester && echo 'tester ALL=(ALL) NOPASSWD: ALL' >/etc/sudoers.d/tester \
    && chmod 440 /etc/sudoers.d/tester
STOPSIGNAL SIGRTMIN+3
CMD ["/usr/lib/systemd/systemd"]
EOF
}

HW_MASK=/sys/class/hwmon:/sys/firmware/acpi:/sys/class/platform-profile:/sys/devices/system/cpu/intel_pstate:/sys/devices/system/cpu/cpufreq:/sys/bus/usb:/sys/class/hidraw
declare -A RESULT
COLUMNS=(install status78 upgrade takeover tamper uninstall purge)
record() { RESULT[$1,$2]=$3; }

run_distro() {
    local distro=$1 name=cryo-bundle-test-$1 image=localhost/cryo-bundle-test-$1
    local log=$LOG_DIR/$distro.log
    local ctx
    ctx=$(mktemp -d)
    containerfile "$distro" >"$ctx/Containerfile"
    echo "== $distro: building image"
    if ! podman build -q -t "$image" "$ctx" >>"$log" 2>&1; then
        rm -rf "$ctx"
        echo "   image build failed (see $log)"
        record "$distro" install "image build failed"
        return
    fi
    rm -rf "$ctx"
    podman rm -f "$name" >/dev/null 2>&1 || true
    # A rootless container sees the host's /sys (read-only). On an Alienware
    # host cryod would find the real hardware and keep running, so hide what
    # it probes: the container must look like unsupported hardware (exit 78).
    podman run -d --name "$name" --systemd=always \
        --security-opt mask="$HW_MASK" \
        -v "$BUNDLE:/bundle/$TARBALL:ro" -v "$REPO/tools:/tools:ro" "$image" >>"$log"

    root() { podman exec "$name" bash -c "$1" >>"$log" 2>&1; }
    user() { podman exec -u tester -w /home/tester "$name" bash -c "$1" >>"$log" 2>&1; }
    step() { printf '\n######## %s: %s\n' "$distro" "$1" >>"$log"; echo "   $1"; }
    pass_if() { if "$@"; then echo PASS; else echo FAIL; fi; }

    step "waiting for systemd"
    # "degraded" is fine (some units fail in a container); no systemd is not.
    if ! root 'for _ in {1..60}; do [[ -S /run/systemd/private ]] && break; sleep 1; done
               timeout 90 systemctl is-system-running --wait; [[ -d /run/systemd/system ]]'; then
        record "$distro" install "systemd did not start"
        return
    fi
    user "tar xzf /bundle/$TARBALL"

    if [[ $distro == ubuntu ]]; then
        step "tampered requirements.txt on a clean machine"
        user "cp -r $DIR tampered && sed -i '/^nvidia-ml-py==/,/^pyside6==/ s/sha256:[0-9a-f]\{64\}/sha256:$(printf '0%.0s' {1..64})/' tampered/requirements.txt"
        local t1=FAIL mark
        mark=$(wc -l <"$log")
        if ! user "cd tampered && sudo ./install.sh"; then
            root '[[ ! -e /opt/cryo && ! -e /etc/systemd/system/cryod.service && ! -e /usr/local/bin/cryoctl ]]' \
                && tail -n +"$mark" "$log" | grep -qi 'hash' && t1=PASS
        fi
        echo "      fresh: $t1"
        record "$distro" tamper "$t1"
    fi

    if [[ $distro == arch ]]; then
        step "faking a from-source install"
        root "mkdir -p /home/tester/src/cryo/.venv/bin && ln -sf /usr/bin/python3 /home/tester/src/cryo/.venv/bin/python \
            && for u in cryod.service cryod-resume.service; do \
                 sed 's|@PYTHON@|/home/tester/src/cryo/.venv/bin/python|' /home/tester/$DIR/share/\$u >/etc/systemd/system/\$u; done \
            && systemctl daemon-reload && systemctl enable cryod.service cryod-resume.service \
            && chown -R tester: /home/tester/src"
        user "mkdir -p .local/bin .local/share/applications \
            && ln -sf /home/tester/src/cryo/.venv/bin/cryoctl .local/bin/cryoctl \
            && ln -sf /home/tester/src/cryo/.venv/bin/cryo-gui .local/bin/cryo-gui \
            && printf '[Desktop Entry]\nType=Application\nName=Cryo\nExec=/home/tester/src/cryo/.venv/bin/cryo-gui\n' \
               >.local/share/applications/cryo.desktop"
    fi

    step "install"
    local before rx0 rx1
    before=$(wc -l <"$log")
    rx0=$(podman exec "$name" awk '/:/ && !/lo:/ {n += $2} END {print n}' /proc/net/dev)
    if user "cd $DIR && sudo ./install.sh"; then
        record "$distro" install PASS
    else
        record "$distro" install FAIL
    fi
    rx1=$(podman exec "$name" awk '/:/ && !/lo:/ {n += $2} END {print n}' /proc/net/dev)
    echo "      downloaded during the install: $(( (rx1 - rx0) / 1000000 )) MB" | tee -a "$log"
    tail -n +"$before" "$log" | sed -n '/^Cryo .* is installed\./,$p' >"$LOG_DIR/$distro.summary.txt"
    if [[ $distro == ubuntu ]]; then
        # The minimal image has no libusb-1.0 (any desktop install does):
        # the installer must say so; then add it and restart cryod.
        step "libusb-1.0 missing: warning expected, then installing it"
        if ! grep -q 'lighting needs libusb-1.0, which is not installed' "$LOG_DIR/$distro.summary.txt"; then
            record "$distro" install "FAIL (no libusb note)"
        fi
        root "DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends libusb-1.0-0 && systemctl stop cryod && systemctl reset-failed cryod && systemctl start cryod"
    fi
    root "/tools/bundle_check.sh installed tester $VERSION" || record "$distro" install FAIL
    grep -q 'libusb-1.0, which is not installed' "$LOG_DIR/$distro.summary.txt" && [[ $distro != ubuntu ]] \
        && record "$distro" install "FAIL (false libusb note)"
    # shellcheck disable=SC2016  # expanded inside the container
    record "$distro" status78 "$(pass_if root '[[ $(systemctl show cryod -p ExecMainStatus --value) == 78 && $(systemctl show cryod -p NRestarts --value) == 0 ]]')"

    if [[ $distro == arch ]]; then
        local tk=FAIL
        if tail -n +"$before" "$log" | grep -q 'Replacing an existing install' \
            && user '[[ ! -e .local/bin/cryoctl && ! -L .local/bin/cryoctl && ! -L .local/bin/cryo-gui && ! -e .local/share/applications/cryo.desktop && -d src/cryo ]]' \
            && root 'grep -q "^ExecStart=/opt/cryo/env/bin/python" /etc/systemd/system/cryod.service'; then
            tk=PASS
        fi
        record "$distro" takeover "$tk"
    fi

    if [[ $distro == ubuntu ]]; then
        step "tampered requirements.txt over an install"
        local t2=FAIL
        if ! user "cd tampered && sudo ./install.sh"; then
            root "[[ ! -e /opt/cryo/env.new && ! -e /opt/cryo/env.old ]] && grep -qx $VERSION /opt/cryo/VERSION \
                && runuser -u tester -- cryoctl --version | grep -qx 'cryoctl $VERSION'" && t2=PASS
        fi
        echo "      over an install: $t2"
        [[ $t2 == PASS && ${RESULT[$distro,tamper]} == PASS ]] || record "$distro" tamper FAIL
    fi

    step "upgrade (rerun the installer; reuses the Python, prunes an old one)"
    # A stand-in for the interpreter of an older bundle with another MANAGED_PYTHON.
    root "mkdir -p /opt/cryo/python/cpython-3.12.0-linux-x86_64-gnu/bin"
    local up
    up=$(wc -l <"$log")
    if user "cd $DIR && sudo ./install.sh" && root "/tools/bundle_check.sh installed tester $VERSION" \
        && root "[[ ! -e /opt/cryo/python/cpython-3.12.0-linux-x86_64-gnu ]] && ls -d /opt/cryo/python/cpython-3.13*" \
        && ! tail -n +"$up" "$log" | grep -q 'Downloading Python'; then
        record "$distro" upgrade PASS
    else
        record "$distro" upgrade FAIL
    fi

    step "uninstall"
    if user "sudo /opt/cryo/uninstall.sh" && root "/tools/bundle_check.sh uninstalled" \
        && user "sudo ./$DIR/uninstall.sh" && root "/tools/bundle_check.sh uninstalled"; then
        record "$distro" uninstall PASS
    else
        record "$distro" uninstall FAIL
    fi

    step "uninstall --purge"
    if user "sudo ./$DIR/uninstall.sh --purge" && root "/tools/bundle_check.sh purged"; then
        record "$distro" purge PASS
    else
        record "$distro" purge FAIL
    fi
}

# shellcheck disable=SC2329  # run by the EXIT trap
cleanup() {
    [[ $KEEP == yes ]] && return
    local d
    for d in "${DISTROS[@]}"; do
        podman rm -f "cryo-bundle-test-$d" >/dev/null 2>&1 || true
        podman rmi -f "localhost/cryo-bundle-test-$d" >/dev/null 2>&1 || true
    done
}
trap cleanup EXIT

for d in "${DISTROS[@]}"; do
    run_distro "$d"
done

echo
printf '%-8s' distro
printf ' %-10s' "${COLUMNS[@]}"
echo
status=0
for d in "${DISTROS[@]}"; do
    printf '%-8s' "$d"
    for c in "${COLUMNS[@]}"; do
        v=${RESULT[$d,$c]:--}
        printf ' %-10s' "$v"
        [[ $v == - || $v == PASS ]] || status=1
    done
    echo
done
echo "logs: $LOG_DIR"
exit "$status"
