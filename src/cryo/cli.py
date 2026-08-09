"""cryoctl — talk to the Cryo daemon from the shell."""

from __future__ import annotations

import json
import platform
import socket
import sys

from cryo import __version__, paths

USAGE = """\
cryoctl — Cryo control CLI

  cryoctl status                     Show telemetry snapshot
  cryoctl watch                      Stream live telemetry
  cryoctl profile <name>             cool|quiet|balanced|performance|gmode|custom
                                     (availability varies by model — see doctor)
  cryoctl gmode                      Toggle G-Mode
  cryoctl boost <cpu|gpu> <0-100>    Manual fan boost (disables curves)
  cryoctl turbo <on|off>             CPU turbo boost
  cryoctl light <effect> [RRGGBB]    static|breathe|spectrum|rainbow|wave|backforth|quantum|off
  cryoctl brightness <0-100>         Keyboard brightness
  cryoctl config                     Dump daemon config
  cryoctl doctor                     Hardware/driver compatibility report
                                     (paste into GitHub model reports)
"""


def doctor() -> None:
    """Daemon-optional hardware report — everything read is world-readable."""
    lines: list[str] = []

    def add(label: str, value: object) -> None:
        lines.append(f"{label:<22} {value}")

    add("cryo", __version__)
    add("kernel", platform.release())
    add("model", paths.dmi_model() or "unknown")

    import pathlib

    add("alienware_wmi module", pathlib.Path("/sys/module/alienware_wmi").exists())
    hwmon = paths.find_hwmon()
    add("hwmon", hwmon or "NOT FOUND")
    if hwmon:
        fans = sorted(hwmon.glob("fan*_label"))
        temps = sorted(hwmon.glob("temp*_label"))
        add("fans", ", ".join(f.read_text().strip() for f in fans) or "none")
        add("temps", ", ".join(t.read_text().strip() for t in temps) or "none")
        boosts = sorted(hwmon.glob("fan*_boost"))
        add("fan boost files", len(boosts))

    profile_path, choices_path = paths.find_platform_profile()
    add("profile node", profile_path)
    try:
        add("profile choices", choices_path.read_text().strip())
        add("current profile", profile_path.read_text().strip())
    except OSError as exc:
        add("profile choices", f"unreadable ({exc})")

    ac = paths.find_ac_supply()
    add("mains supply", ac.parent.name if ac else "NOT FOUND")
    turbo = paths.find_turbo_control()
    if turbo:
        turbo_paths, _ = turbo
        suffix = f" (+{len(turbo_paths) - 1} per-cpu)" if len(turbo_paths) > 1 else ""
        add("turbo control", f"{turbo_paths[0]}{suffix}")
    else:
        add("turbo control", "NOT FOUND")

    elc_pids = []
    for dev in sorted(paths.USB_DEVICES.glob("*")):
        try:
            vid = (dev / "idVendor").read_text().strip()
            pid = (dev / "idProduct").read_text().strip()
        except OSError:
            continue
        if vid == "187c":
            elc_pids.append(pid)
    add("alienware usb (187c)", ", ".join(elc_pids) or "none")
    add("known AW-ELC", any(pid in ("0550", "0551") for pid in elc_pids))

    try:
        import pynvml

        pynvml.nvmlInit()
        add("nvml", pynvml.nvmlDeviceGetName(pynvml.nvmlDeviceGetHandleByIndex(0)))
    except Exception as exc:
        add("nvml", f"unavailable ({type(exc).__name__})")

    daemon_caps = "daemon unreachable"
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(str(paths.RUN_SOCKET))
        sock.sendall(b'{"op": "status"}\n')
        response = json.loads(sock.makefile().readline())
        daemon_caps = json.dumps(
            response.get("status", {}).get("capabilities", "pre-0.2 daemon (no capabilities)")
        )
        sock.close()
    except OSError:
        pass
    add("daemon capabilities", daemon_caps)

    print("```")
    print("\n".join(lines))
    print("```")


def request(payload: dict, stream: bool = False) -> None:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(paths.RUN_SOCKET))
    except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
        sys.exit(f"cryoctl: cannot reach cryod at {paths.RUN_SOCKET} ({exc})")
    sock.sendall(json.dumps(payload).encode() + b"\n")
    buf = sock.makefile()
    first = json.loads(buf.readline())
    print(json.dumps(first, indent=2))
    if stream:
        try:
            for line in buf:
                event = json.loads(line)
                cpu = event.get("cpu_temp")
                gpu = event.get("gpu_temp")
                fans = " ".join(f"{f['rpm']}rpm" for f in event.get("fans", []))
                print(
                    f"[{event.get('profile')}] cpu {cpu}°C gpu {gpu}°C "
                    f"util {event.get('gpu_util')}% gaming={event.get('gaming')} | {fans}"
                )
        except KeyboardInterrupt:
            pass


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(USAGE)
        return
    match args:
        case ["status"]:
            request({"op": "status"})
        case ["watch"]:
            request({"op": "subscribe"}, stream=True)
        case ["profile", name]:
            request({"op": "set_profile", "profile": name})
        case ["gmode"]:
            request({"op": "toggle_gmode"})
        case ["boost", group, value]:
            request({"op": "set_boost", "group": group, "value": int(value)})
        case ["turbo", state]:
            request({"op": "set_turbo", "enabled": state == "on"})
        case ["light", effect, *rest]:
            payload = {"op": "set_lighting", "effect": effect}
            if rest:
                payload["color"] = rest[0]
            request(payload)
        case ["brightness", value]:
            request({"op": "set_brightness", "value": int(value)})
        case ["config"]:
            request({"op": "get_config"})
        case ["doctor"]:
            doctor()
        case _:
            sys.exit(USAGE)


if __name__ == "__main__":
    main()
