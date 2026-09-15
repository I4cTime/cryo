"""cryoctl — talk to the Cryo daemon from the shell."""

from __future__ import annotations

import json
import platform
import socket
import sys

from cryo import __version__, paths

USAGE = """\
cryoctl — Cryo control CLI

  cryoctl status [--json]            Show telemetry snapshot (--json: raw frame)
  cryoctl watch [--log FILE.csv]     Stream live telemetry (--log: append CSV,
                                     made for long leak-hunt sessions)
  cryoctl profile <name>             cool|quiet|balanced|performance|gmode|custom
                                     (availability varies by model — see doctor)
  cryoctl gmode                      Toggle G-Mode
  cryoctl boost <cpu|gpu> <0-100>    Manual fan boost (disables curves)
  cryoctl turbo <on|off>             CPU turbo boost
  cryoctl light <effect> [RRGGBB]    static|breathe|spectrum|rainbow|wave|backforth|quantum|off
  cryoctl brightness <0-100>         Keyboard brightness
  cryoctl config                     Dump effective config (+ your overrides)
  cryoctl reapply                    Re-assert lighting/profile/NVML (run by
                                     cryod-resume.service after suspend)
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


def fmt_status(st: dict) -> str:
    """Human-readable status; the raw frame stays behind --json."""
    lines: list[str] = []

    def add(label: str, value: str) -> None:
        lines.append(f"{label:<9} {value}")

    flags = " ".join(
        name for name, on in (("GAMING", st.get("gaming")), ("GUARD", st.get("guard"))) if on
    )
    add("profile", str(st.get("profile", "?")) + (f"   [{flags}]" if flags else ""))

    for group in ("cpu", "gpu"):
        temp = st.get(f"{group}_temp")
        peak = st.get(f"{group}_peak")
        fans = "  ".join(
            f"{f['rpm']} rpm ({f['boost']}%)"
            for f in st.get("fans", [])
            if f.get("group") == group
        )
        parts = [f"{temp:.0f}°C" if temp is not None else "—"]
        if peak:
            parts.append(f"peak {peak:.0f}°C")
        if fans:
            parts.append(fans)
        add(group, "  ·  ".join(parts))

    util = st.get("gpu_util")
    if util is not None:
        parts = [f"{util}% load"]
        if st.get("gpu_power_w") is not None:
            parts.append(f"{st['gpu_power_w']:.0f} W")
        if st.get("gpu_clock_mhz") is not None:
            parts.append(f"{st['gpu_clock_mhz']} MHz")
        add("dgpu", "  ·  ".join(parts))

    used, total = st.get("vram_used_mb"), st.get("vram_total_mb")
    if used is not None and total:
        add("vram", f"{used / 1024:.1f} / {total / 1024:.1f} GB")
        for proc in st.get("vram_procs", []):
            add("", f"{proc['vram_mb'] / 1024:5.1f} GB  {proc['name']}")

    add(
        "power",
        ("AC" if st.get("ac") else "battery")
        + ("  ·  turbo on" if st.get("turbo") else "  ·  turbo off"),
    )
    return "\n".join(lines)


CSV_HEADER = [
    "time", "profile", "cpu_temp", "gpu_temp", "gpu_util", "gpu_power_w",
    "gpu_clock_mhz", "vram_used_mb", "vram_total_mb", "gaming", "guard",
    "fan_rpms", "top_proc", "top_proc_mb",
]


def request(
    payload: dict,
    stream: bool = False,
    log_path: str | None = None,
    raw: bool = False,
) -> None:
    import contextlib
    import csv
    import datetime

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(paths.RUN_SOCKET))
    except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
        sys.exit(f"cryoctl: cannot reach cryod at {paths.RUN_SOCKET} ({exc})")
    sock.sendall(json.dumps(payload).encode() + b"\n")
    buf = sock.makefile()
    first = json.loads(buf.readline())
    if payload.get("op") == "status" and not raw and "status" in first:
        print(fmt_status(first["status"]))
    else:
        print(json.dumps(first, indent=2))
    if stream:
        with contextlib.ExitStack() as stack:
            writer = None
            log_file = None
            if log_path:
                log_file = stack.enter_context(open(log_path, "a", newline=""))
                writer = csv.writer(log_file)
                if log_file.tell() == 0:
                    writer.writerow(CSV_HEADER)
            try:
                for line in buf:
                    event = json.loads(line)
                    cpu = event.get("cpu_temp")
                    gpu = event.get("gpu_temp")
                    power = event.get("gpu_power_w")
                    power_s = (
                        f" {power:.0f}W {event.get('gpu_clock_mhz')}MHz"
                        if power is not None
                        else ""
                    )
                    vram = event.get("vram_used_mb")
                    vram_s = f" vram {vram / 1024:.1f}G" if vram is not None else ""
                    fans = " ".join(f"{f['rpm']}rpm" for f in event.get("fans", []))
                    print(
                        f"[{event.get('profile')}] cpu {cpu}°C gpu {gpu}°C "
                        f"util {event.get('gpu_util')}%{power_s}{vram_s} "
                        f"gaming={event.get('gaming')} | {fans}"
                    )
                    if writer and log_file:
                        top = (event.get("vram_procs") or [{}])[0]
                        writer.writerow([
                            datetime.datetime.now().isoformat(timespec="seconds"),
                            event.get("profile"), cpu, gpu, event.get("gpu_util"),
                            power, event.get("gpu_clock_mhz"),
                            vram, event.get("vram_total_mb"),
                            int(bool(event.get("gaming"))), int(bool(event.get("guard"))),
                            ";".join(str(f["rpm"]) for f in event.get("fans", [])),
                            top.get("name", ""), top.get("vram_mb", ""),
                        ])
                        log_file.flush()
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
        case ["status", "--json"]:
            request({"op": "status"}, raw=True)
        case ["watch"]:
            request({"op": "subscribe"}, stream=True)
        case ["watch", "--log", path]:
            request({"op": "subscribe"}, stream=True, log_path=path)
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
        case ["reapply"]:
            request({"op": "reapply"})
        case ["doctor"]:
            doctor()
        case _:
            sys.exit(USAGE)


if __name__ == "__main__":
    main()
