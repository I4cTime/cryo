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


class Server:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
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
                # Manual boost implies the user wants control: disable curves.
                engine.config["fan_curves"]["enabled"] = False
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
                config_mod.save(engine.config)
                return {"ok": True}
            case "set_brightness":
                engine.effects.brightness(int(req["value"]))
                engine.config["lighting"]["last"]["brightness"] = int(req["value"])
                config_mod.save(engine.config)
                return {"ok": True}
            case "get_config":
                return {"ok": True, "config": engine.config}
            case "set_config":
                engine.config = config_mod._merge(engine.config, req["patch"])
                engine.detector.configure(engine.config["auto"])
                config_mod.save(engine.config)
                return {"ok": True, "config": engine.config}
            case unknown:
                return {"ok": False, "error": f"unknown op {unknown!r}"}

    # -- telemetry fanout --------------------------------------------------

    def broadcast(self, telemetry: dict) -> None:
        self._last_telemetry = telemetry
        if not self.subscribers:
            return
        payload = json.dumps({"event": "telemetry", **telemetry}).encode() + b"\n"
        for writer in list(self.subscribers):
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
                telemetry = await asyncio.to_thread(self.engine.tick)
                self.broadcast(telemetry)
                await asyncio.sleep(interval)
