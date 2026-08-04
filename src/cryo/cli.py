"""cryoctl — talk to the Cryo daemon from the shell."""

from __future__ import annotations

import json
import socket
import sys

from cryo import paths

USAGE = """\
cryoctl — Cryo control CLI

  cryoctl status                     Show telemetry snapshot
  cryoctl watch                      Stream live telemetry
  cryoctl profile <name>             cool|quiet|balanced|performance|gmode|custom
  cryoctl gmode                      Toggle G-Mode
  cryoctl boost <cpu|gpu> <0-100>    Manual fan boost (disables curves)
  cryoctl turbo <on|off>             CPU turbo boost
  cryoctl light <effect> [RRGGBB]    static|breathe|spectrum|rainbow|wave|backforth|quantum|off
  cryoctl brightness <0-100>         Keyboard brightness
  cryoctl config                     Dump daemon config
"""


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
        case _:
            sys.exit(USAGE)


if __name__ == "__main__":
    main()
