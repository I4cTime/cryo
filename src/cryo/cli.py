"""cryoctl — talk to the Cryo daemon from the shell."""

from __future__ import annotations

import json
import platform
import socket
import sys

from cryo import __version__, paths
from cryo.hw.thermal import COMPATIBILITY_URL

EXIT_UNSUPPORTED = 2

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
  cryoctl cap [<10-100>|off|on]      CPU performance cap for the current profile
  cryoctl cap <profile> <10-100>     …for a specific profile (intel_pstate max_perf_pct;
                                     90 ≈ 5.2 GHz on m18 R2, re-applied on every switch)
  cryoctl curve show                 Fan curve points, hysteresis, min step
  cryoctl curve <cpu|gpu> T:B [T:B…] Set a curve, e.g. cpu 45:0 60:15 70:35 80:60 95:100
  cryoctl curve hysteresis <°C>      Dead zone before fans move (0-15)
  cryoctl curve step <pct>           Minimum boost change to write (1-25)
  cryoctl guard show                 Thermal Guard thresholds
  cryoctl guard <cpu|gpu> <°C>       Trip temperature (60-105)
  cryoctl guard release <°C>         Degrees below trip to release (1-30)
  cryoctl guard hold <s>             Minimum seconds engaged (0-600)
  cryoctl light <effect> [RRGGBB]    static|breathe|spectrum|rainbow|wave|backforth|quantum|off
  cryoctl brightness <0-100>         Keyboard brightness
  cryoctl config                     Dump effective config (+ your overrides)
  cryoctl reapply                    Re-assert lighting/profile/NVML (run by
                                     cryod-resume.service after suspend)
  cryoctl doctor                     Hardware/driver compatibility report with a
                                     supported / partial / unsupported verdict
                                     (paste into GitHub model reports; exit 2 when
                                     unsupported)
"""


def verdict(facts: dict) -> tuple[str, list[str]]:
    """Classify a machine from doctor's findings.

    supported   — everything Cryo knows how to do is available.
    partial     — the daemon runs with full thermals; listed extras missing.
    limited     — no hwmon and/or no platform profiles: fans, curves, the
                  guard and power modes are out, but the daemon still runs
                  what exists (GPU telemetry, game detection, turbo, CPU
                  cap, lighting).
    unsupported — nothing at all to drive: cryod refuses to start.
    """
    core: list[str] = []
    if not facts.get("hwmon"):
        core.append("fans, temperatures, curves and Thermal Guard (no alienware-wmi hwmon)")
    if not facts.get("profiles"):
        core.append("power modes (no readable platform profiles)")
    extras_present = any(
        facts.get(k) for k in ("turbo", "cpu_cap", "elc", "nvml")
    )
    if core and not extras_present:
        return "unsupported", core + ["and no turbo, CPU cap, lighting or NVML to fall back on"]
    missing: list[str] = list(core)
    if not facts.get("fan_boost"):
        missing.append("fan boost (curves, manual boost, Thermal Guard)")
    if not facts.get("elc"):
        missing.append("AlienFX lighting (no AW-ELC controller)")
    if not facts.get("nvml"):
        missing.append("game detection (no NVML)")
    if not facts.get("mains"):
        missing.append("battery/AC auto rules (no Mains supply)")
    if not facts.get("turbo"):
        missing.append("CPU turbo toggle")
    if not facts.get("cpu_cap"):
        missing.append("CPU performance cap (no intel_pstate max_perf_pct)")
    if core:
        return "limited", missing
    return ("partial", missing) if missing else ("supported", [])


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
    facts: dict = {}
    hwmon = paths.find_hwmon()
    facts["hwmon"] = hwmon is not None
    add("hwmon", hwmon or "NOT FOUND")
    boosts: list = []
    if hwmon:
        fans = sorted(hwmon.glob("fan*_label"))
        temps = sorted(hwmon.glob("temp*_label"))
        add("fans", ", ".join(f.read_text().strip() for f in fans) or "none")
        add("temps", ", ".join(t.read_text().strip() for t in temps) or "none")
        boosts = sorted(hwmon.glob("fan*_boost"))
        add("fan boost files", len(boosts))
    facts["fan_boost"] = bool(boosts)

    profile_path, choices_path = paths.find_platform_profile()
    add("profile node", profile_path)
    try:
        add("profile choices", choices_path.read_text().strip())
        add("current profile", profile_path.read_text().strip())
        facts["profiles"] = True
    except OSError as exc:
        add("profile choices", f"unreadable ({exc})")
        facts["profiles"] = False

    ac = paths.find_ac_supply()
    facts["mains"] = ac is not None
    add("mains supply", ac.parent.name if ac else "NOT FOUND")
    turbo = paths.find_turbo_control()
    facts["turbo"] = turbo is not None
    if turbo:
        turbo_paths, _ = turbo
        suffix = f" (+{len(turbo_paths) - 1} per-cpu)" if len(turbo_paths) > 1 else ""
        add("turbo control", f"{turbo_paths[0]}{suffix}")
    else:
        add("turbo control", "NOT FOUND")
    cap = paths.find_cpu_cap()
    facts["cpu_cap"] = cap is not None
    add("cpu cap control", cap or "NOT FOUND")

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
    facts["elc"] = any(pid in ("0550", "0551") for pid in elc_pids)
    add("known AW-ELC", facts["elc"])

    try:
        import pynvml

        pynvml.nvmlInit()
        add("nvml", pynvml.nvmlDeviceGetName(pynvml.nvmlDeviceGetHandleByIndex(0)))
        facts["nvml"] = True
    except Exception as exc:
        add("nvml", f"unavailable ({type(exc).__name__})")
        facts["nvml"] = False

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

    level, reasons = verdict(facts)
    lines.append("")
    if level == "supported":
        add("verdict", "SUPPORTED — everything Cryo does is available here")
    elif level == "partial":
        add("verdict", "PARTIAL — cryod runs; unavailable: " + "; ".join(reasons))
    elif level == "limited":
        add("verdict", "LIMITED — cryod runs what exists; unavailable: " + "; ".join(reasons))
    else:
        add("verdict", "UNSUPPORTED — " + "; ".join(reasons))
        add("", "cryod will not start on this machine.")
    add("compatibility", COMPATIBILITY_URL)

    print("```")
    print("\n".join(lines))
    print("```")
    if level == "unsupported":
        sys.exit(EXIT_UNSUPPORTED)


def fmt_status(st: dict) -> str:
    """Human-readable status; the raw frame stays behind --json."""
    lines: list[str] = []

    def add(label: str, value: str) -> None:
        lines.append(f"{label:<9} {value}")

    flags = " ".join(
        name for name, on in (("GAMING", st.get("gaming")), ("GUARD", st.get("guard"))) if on
    )
    add("profile", str(st.get("profile") or "n/a") + (f"   [{flags}]" if flags else ""))

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

    power = ("AC" if st.get("ac") else "battery") + (
        "  ·  turbo on" if st.get("turbo") else "  ·  turbo off"
    )
    cap = st.get("cpu_cap")
    if cap is not None:
        max_mhz = (st.get("capabilities") or {}).get("cpu_max_mhz")
        ghz = f" ≈ {cap / 100 * max_mhz / 1000:.1f} GHz" if max_mhz else ""
        power += f"  ·  cap {cap}%{ghz}" + ("" if st.get("cpu_cap_enabled", True) else " (off)")
    add("power", power)
    return "\n".join(lines)


def parse_curve_points(tokens: list[str]) -> list[list[int]]:
    """`45:0 60:15 …` → [[45, 0], [60, 15], …] (validation happens daemon-side)."""
    points: list[list[int]] = []
    for token in tokens:
        try:
            temp, boost = token.split(":")
            points.append([int(temp), int(boost)])
        except ValueError:
            sys.exit(f"cryoctl: bad curve point {token!r} — expected TEMP:BOOST, e.g. 70:35")
    return points


def fmt_curves(config: dict) -> str:
    curves = config.get("fan_curves", {})
    lines = []
    for group in ("cpu", "gpu"):
        pts = "  ".join(f"{t}:{b}" for t, b in curves.get(group, []))
        lines.append(f"{group:<11} {pts}")
    lines.append(f"{'hysteresis':<11} {curves.get('hysteresis_c')} °C")
    lines.append(f"{'min step':<11} {curves.get('min_step')} %")
    lines.append(f"{'curves':<11} {'on' if curves.get('enabled') else 'off'}")
    return "\n".join(lines)


def fmt_guard(config: dict) -> str:
    guard = config.get("thermal_guard", {})
    return "\n".join([
        f"{'cpu trip':<11} {guard.get('cpu_trip')} °C",
        f"{'gpu trip':<11} {guard.get('gpu_trip')} °C",
        f"{'release':<11} {guard.get('release_c')} °C below trip",
        f"{'min hold':<11} {guard.get('min_hold_s')} s",
        f"{'boost':<11} {guard.get('boost')} %",
        f"{'guard':<11} {'on' if guard.get('enabled') else 'off'}",
    ])


def set_config(patch: dict, show: str | None = None) -> None:
    """Send a validated config patch; print the relevant section afterwards."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(paths.RUN_SOCKET))
    except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
        sys.exit(f"cryoctl: cannot reach cryod at {paths.RUN_SOCKET} ({exc})")
    sock.sendall(json.dumps({"op": "set_config", "patch": patch}).encode() + b"\n")
    response = json.loads(sock.makefile().readline())
    sock.close()
    if not response.get("ok"):
        sys.exit(f"cryoctl: {response.get('error', 'rejected')}")
    config = response.get("config", {})
    if show == "curve":
        print(fmt_curves(config))
    elif show == "guard":
        print(fmt_guard(config))
    else:
        print(json.dumps(response, indent=2))


def get_config() -> dict:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(paths.RUN_SOCKET))
    except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
        sys.exit(f"cryoctl: cannot reach cryod at {paths.RUN_SOCKET} ({exc})")
    sock.sendall(b'{"op": "get_config"}\n')
    response = json.loads(sock.makefile().readline())
    sock.close()
    return response.get("config", {})


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
        case ["cap"]:
            request({"op": "status"})
        case ["cap", "off"] | ["cap", "on"] as words:
            set_config({"cpu_cap": {"enabled": words[1] == "on"}})
        case ["cap", pct] if pct.isdigit():
            request({"op": "set_cpu_cap", "pct": int(pct)})
        case ["cap", profile, pct]:
            request({"op": "set_cpu_cap", "profile": profile, "pct": int(pct)})
        case ["curve", "show"]:
            print(fmt_curves(get_config()))
        case ["curve", "hysteresis", value]:
            set_config({"fan_curves": {"hysteresis_c": float(value)}}, show="curve")
        case ["curve", "step", value]:
            set_config({"fan_curves": {"min_step": int(value)}}, show="curve")
        case ["curve", ("cpu" | "gpu") as group, *points] if points:
            set_config({"fan_curves": {group: parse_curve_points(points)}}, show="curve")
        case ["guard", "show"]:
            print(fmt_guard(get_config()))
        case ["guard", ("cpu" | "gpu") as group, value]:
            set_config({"thermal_guard": {f"{group}_trip": int(value)}}, show="guard")
        case ["guard", "release", value]:
            set_config({"thermal_guard": {"release_c": int(value)}}, show="guard")
        case ["guard", "hold", value]:
            set_config({"thermal_guard": {"min_hold_s": int(value)}}, show="guard")
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
