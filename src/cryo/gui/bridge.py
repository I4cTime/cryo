"""Qt bridge between the QML UI and the cryod unix socket."""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtNetwork import QLocalSocket

from cryo import paths

log = logging.getLogger(__name__)

HISTORY_LEN = 120  # samples kept for the sparklines (~2 min at 1 Hz)

# Shown until the daemon's real capability block arrives (or against a
# pre-0.2 daemon that doesn't send one): the classic m18 layout.
DEFAULT_CAPABILITIES: dict = {
    "model": "",
    "profiles": ["cool", "quiet", "balanced", "performance", "gmode", "custom"],
    "gmode": True,
    "fan_boost": True,
    "fan_groups": ["cpu", "gpu"],
    "turbo": True,
    "ac_supply": True,
    "lighting": True,
    "game_detection": True,
}


class Daemon(QObject):
    telemetryChanged = Signal()
    connectedChanged = Signal()
    capabilitiesChanged = Signal()
    errorOccurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._connected = False
        self._telemetry: dict = {}
        self._capabilities: dict = DEFAULT_CAPABILITIES
        self._cpu_history: list[float] = []
        self._gpu_history: list[float] = []
        self._buffer = b""

        # Telemetry stream socket
        self._stream = QLocalSocket(self)
        self._stream.connected.connect(self._on_stream_connected)
        self._stream.disconnected.connect(self._on_stream_disconnected)
        self._stream.readyRead.connect(self._on_ready_read)

        # Command socket (serialized request/response). Responses are read
        # so daemon-side failures surface in the UI instead of vanishing —
        # a kernel EINVAL on a profile write used to look like "the button
        # does nothing".
        self._cmd = QLocalSocket(self)
        self._cmd_buffer = b""
        self._cmd.readyRead.connect(self._on_cmd_ready_read)

        self._reconnect = QTimer(self)
        self._reconnect.setInterval(2000)
        self._reconnect.timeout.connect(self._connect)
        self._connect()

    # -- connection --------------------------------------------------------

    def _connect(self) -> None:
        if self._stream.state() == QLocalSocket.LocalSocketState.UnconnectedState:
            self._stream.connectToServer(str(paths.RUN_SOCKET))

    def _on_stream_connected(self) -> None:
        self._connected = True
        self._reconnect.stop()
        self.connectedChanged.emit()
        self._stream.write(json.dumps({"op": "subscribe"}).encode() + b"\n")

    def _on_stream_disconnected(self) -> None:
        self._connected = False
        self.connectedChanged.emit()
        self._reconnect.start()

    def _on_ready_read(self) -> None:
        self._buffer += bytes(self._stream.readAll().data())
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("event") == "telemetry":
                self._apply_telemetry(message)

    def _apply_telemetry(self, t: dict) -> None:
        self._telemetry = t
        if t.get("cpu_temp") is not None:
            self._cpu_history = (self._cpu_history + [t["cpu_temp"]])[-HISTORY_LEN:]
        if t.get("gpu_temp") is not None:
            self._gpu_history = (self._gpu_history + [t["gpu_temp"]])[-HISTORY_LEN:]
        # Capabilities are static per daemon run — emit separately and only
        # on change, so the mode grid isn't rebuilt every tick.
        caps = t.get("capabilities") or DEFAULT_CAPABILITIES
        if caps != self._capabilities:
            self._capabilities = caps
            self.capabilitiesChanged.emit()
        self.telemetryChanged.emit()

    def _on_cmd_ready_read(self) -> None:
        self._cmd_buffer += bytes(self._cmd.readAll().data())
        while b"\n" in self._cmd_buffer:
            line, self._cmd_buffer = self._cmd_buffer.split(b"\n", 1)
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not response.get("ok", True):
                message = str(response.get("error", "unknown error"))
                log.warning("daemon rejected command: %s", message)
                self.errorOccurred.emit(message)

    def _command(self, payload: dict) -> None:
        if self._cmd.state() != QLocalSocket.LocalSocketState.ConnectedState:
            self._cmd.connectToServer(str(paths.RUN_SOCKET))
            if not self._cmd.waitForConnected(300):
                self.errorOccurred.emit("cryod unreachable — command dropped")
                return
        self._cmd.write(json.dumps(payload).encode() + b"\n")
        self._cmd.flush()

    # -- properties for QML ------------------------------------------------

    @Property(bool, notify=connectedChanged)
    def connected(self) -> bool:
        return self._connected

    @Property(str, notify=telemetryChanged)
    def profile(self) -> str:
        return self._telemetry.get("profile", "—")

    @Property(float, notify=telemetryChanged)
    def cpuTemp(self) -> float:
        return self._telemetry.get("cpu_temp") or 0.0

    @Property(float, notify=telemetryChanged)
    def gpuTemp(self) -> float:
        return self._telemetry.get("gpu_temp") or 0.0

    @Property(int, notify=telemetryChanged)
    def gpuUtil(self) -> int:
        return self._telemetry.get("gpu_util") or 0

    @Property(bool, notify=telemetryChanged)
    def gaming(self) -> bool:
        return bool(self._telemetry.get("gaming"))

    @Property(bool, notify=telemetryChanged)
    def guard(self) -> bool:
        return bool(self._telemetry.get("guard"))

    @Property(float, notify=telemetryChanged)
    def cpuPeak(self) -> float:
        return self._telemetry.get("cpu_peak") or 0.0

    @Property(float, notify=telemetryChanged)
    def gpuPeak(self) -> float:
        return self._telemetry.get("gpu_peak") or 0.0

    @Property(bool, notify=telemetryChanged)
    def ac(self) -> bool:
        return bool(self._telemetry.get("ac", True))

    @Property(bool, notify=telemetryChanged)
    def turbo(self) -> bool:
        return bool(self._telemetry.get("turbo", True))

    @Property("QVariantList", notify=capabilitiesChanged)
    def profiles(self) -> list:
        return list(self._capabilities.get("profiles", []))

    @Property(bool, notify=capabilitiesChanged)
    def hasGmode(self) -> bool:
        return bool(self._capabilities.get("gmode", True))

    @Property(bool, notify=capabilitiesChanged)
    def hasBoost(self) -> bool:
        return bool(self._capabilities.get("fan_boost", True))

    @Property(bool, notify=capabilitiesChanged)
    def hasTurbo(self) -> bool:
        return bool(self._capabilities.get("turbo", True))

    @Property(bool, notify=capabilitiesChanged)
    def hasLighting(self) -> bool:
        return bool(self._capabilities.get("lighting", True))

    @Property(bool, notify=capabilitiesChanged)
    def hasGameSense(self) -> bool:
        return bool(self._capabilities.get("game_detection", True))

    @Property(str, notify=capabilitiesChanged)
    def modelName(self) -> str:
        return str(self._capabilities.get("model", ""))

    @Property(bool, notify=telemetryChanged)
    def curvesEnabled(self) -> bool:
        return bool(self._telemetry.get("curves_enabled", True))

    @Property(bool, notify=telemetryChanged)
    def autoEnabled(self) -> bool:
        return bool(self._telemetry.get("auto_enabled", True))

    @Property(str, notify=telemetryChanged)
    def lightEffect(self) -> str:
        return (self._telemetry.get("lighting") or {}).get("effect", "quantum")

    @Property(str, notify=telemetryChanged)
    def lightColor(self) -> str:
        color = (self._telemetry.get("lighting") or {}).get("color", "00D1FF")
        return "#" + str(color).upper()

    @Property(int, notify=telemetryChanged)
    def lightBrightness(self) -> int:
        return int((self._telemetry.get("lighting") or {}).get("brightness", 60))

    @Property("QVariantList", notify=telemetryChanged)
    def fans(self) -> list:
        return self._telemetry.get("fans", [])

    @Property("QVariantList", notify=telemetryChanged)
    def cpuHistory(self) -> list:
        return self._cpu_history

    @Property("QVariantList", notify=telemetryChanged)
    def gpuHistory(self) -> list:
        return self._gpu_history

    # -- slots (commands) --------------------------------------------------

    @Slot(str)
    def setProfile(self, name: str) -> None:
        self._command({"op": "set_profile", "profile": name})

    @Slot()
    def toggleGmode(self) -> None:
        self._command({"op": "toggle_gmode"})

    @Slot(str, int)
    def setBoost(self, group: str, value: int) -> None:
        self._command({"op": "set_boost", "group": group, "value": value})

    @Slot(bool)
    def setTurbo(self, enabled: bool) -> None:
        self._command({"op": "set_turbo", "enabled": enabled})

    @Slot(str, str)
    def setLighting(self, effect: str, color: str) -> None:
        self._command({"op": "set_lighting", "effect": effect, "color": color.lstrip("#")})

    @Slot(int)
    def setBrightness(self, value: int) -> None:
        self._command({"op": "set_brightness", "value": value})

    @Slot(bool)
    def setCurvesEnabled(self, enabled: bool) -> None:
        self._command({"op": "set_config", "patch": {"fan_curves": {"enabled": enabled}}})

    @Slot(bool)
    def setAutoEnabled(self, enabled: bool) -> None:
        self._command({"op": "set_config", "patch": {"auto": {"enabled": enabled}}})
