"""Unix-socket JSON-lines API.

One request per line: {"op": "...", ...} -> one response line.
{"op": "subscribe"} upgrades the connection: the daemon then pushes
{"event": "telemetry", ...} every tick until the client disconnects.
"""

from __future__ import annotations

import asyncio
import grp
import json
import logging
import os

from cryo import paths
from cryo.daemon import config as config_mod
from cryo.daemon.engine import Engine

log = logging.getLogger(__name__)


# A subscriber that stops reading (hung GUI, suspended terminal) would
# otherwise make the daemon buffer telemetry forever.
MAX_SUBSCRIBER_BACKLOG = 256 * 1024


class Server:
    def __init__(self, engine: Engine, overrides: dict | None = None) -> None:
        self.engine = engine
        # The user's partial config (what /etc/cryo/config.json holds). Only
        # this is ever written back — never the merged config.
        self.overrides: dict = overrides if overrides is not None else {}
        self.subscribers: set[asyncio.StreamWriter] = set()
        self._last_telemetry: dict = {}

    # -- request handling --------------------------------------------------

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while line := await reader.readline():
                try:
                    request = json.loads(line)
                    response = self.dispatch(request, writer)
                except Exception as exc:
                    response = {"ok": False, "error": str(exc)}
                if response is not None:
                    writer.write(json.dumps(response).encode() + b"\n")
                    await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self.subscribers.discard(writer)
            writer.close()

    def dispatch(self, req: dict, writer: asyncio.StreamWriter) -> dict | None:
        engine = self.engine
        match req.get("op"):
            case "status":
                return {"ok": True, "status": self._last_telemetry or engine.thermal.telemetry()}
            case "subscribe":
                self.subscribers.add(writer)
                return {"ok": True, "subscribed": True}
            case "set_profile":
                engine.set_profile(req["profile"])
                return {"ok": True, "profile": req["profile"]}
            case "toggle_gmode":
                return {"ok": True, "profile": engine.toggle_gmode()}
            case "set_boost":
                # Manual boost implies the user wants control: latch curves
                # off in daemon state (persisted — otherwise a daemon restart
                # silently re-enables them and fights the manual setting).
                # The user's config file is left alone; re-enabling curves
                # through set_config clears the latch.
                if engine.curves_enabled():
                    engine.latch_curves(False)
                engine.thermal.set_boost(req["group"], int(req["value"]))
                return {"ok": True}
            case "set_turbo":
                engine.thermal.set_turbo(bool(req["enabled"]))
                return {"ok": True, "turbo": bool(req["enabled"])}
            case "set_lighting":
                engine.set_lighting(
                    req["effect"],
                    int(req.get("color", "00D1FF"), 16),
                    req.get("brightness"),
                )
                return {"ok": True}
            case "set_brightness":
                engine.set_brightness(int(req["value"]))
                return {"ok": True}
            case "get_config":
                return {"ok": True, "config": engine.config, "overrides": self.overrides}
            case "set_config":
                patch = req["patch"]
                if not isinstance(patch, dict):
                    raise ValueError("patch must be an object")
                self.overrides = config_mod._merge(self.overrides, patch)
                engine.config = config_mod.merged(self.overrides)
                engine.detector.configure(engine.config["auto"])
                if "enabled" in patch.get("fan_curves", {}):
                    # An explicit curves switch overrides the manual-boost latch.
                    engine.latch_curves(None)
                config_mod.save_overrides(self.overrides)
                return {"ok": True, "config": engine.config}
            case "reapply":
                return {"ok": True, **engine.reapply()}
            case unknown:
                return {"ok": False, "error": f"unknown op {unknown!r}"}

    # -- telemetry fanout --------------------------------------------------

    def broadcast(self, telemetry: dict) -> None:
        self._last_telemetry = telemetry
        if not self.subscribers:
            return
        payload = json.dumps({"event": "telemetry", **telemetry}).encode() + b"\n"
        for writer in list(self.subscribers):
            transport = writer.transport
            if transport.is_closing() or (
                transport.get_write_buffer_size() > MAX_SUBSCRIBER_BACKLOG
            ):
                # Gone, or not reading: drop it rather than buffer forever.
                self.subscribers.discard(writer)
                if not transport.is_closing():
                    log.warning("dropping stalled telemetry subscriber")
                    writer.close()
                continue
            try:
                writer.write(payload)
            except Exception:
                self.subscribers.discard(writer)

    # -- lifecycle ---------------------------------------------------------

    async def run(self) -> None:
        socket_path = paths.RUN_SOCKET
        socket_path.unlink(missing_ok=True)
        server = await asyncio.start_unix_server(self.handle, path=str(socket_path))

        group = self.engine.config.get("socket_group")
        try:
            os.chown(socket_path, 0, grp.getgrnam(group).gr_gid)
        except (KeyError, PermissionError) as exc:
            log.warning("could not set socket group %r: %s", group, exc)
        os.chmod(socket_path, 0o660)
        log.info("Listening on %s (group %s)", socket_path, group)

        interval = self.engine.config["poll_interval"]
        async with server:
            while True:
                # A transient sysfs/NVML hiccup must not take the daemon
                # down (a crash-restart cycle would drop guard/curve state
                # mid-incident) — log it and keep ticking.
                try:
                    telemetry = await asyncio.to_thread(self.engine.tick)
                except Exception:
                    log.exception("tick failed; continuing")
                else:
                    self.broadcast(telemetry)
                await asyncio.sleep(interval)
