"""Server request/broadcast behaviour with a stub engine — no sockets."""

from types import SimpleNamespace

from cryo.daemon import config as config_mod
from cryo.daemon.server import MAX_SUBSCRIBER_BACKLOG, Server


class FakeTransport:
    def __init__(self, closing=False, backlog=0):
        self._closing = closing
        self._backlog = backlog

    def is_closing(self):
        return self._closing

    def get_write_buffer_size(self):
        return self._backlog


class FakeWriter:
    def __init__(self, closing=False, backlog=0):
        self.transport = FakeTransport(closing, backlog)
        self.written = []
        self.closed = False

    def write(self, data):
        self.written.append(data)

    def close(self):
        self.closed = True


def make_server(overrides=None):
    latch: dict = {"value": "unset"}
    engine = SimpleNamespace(
        config=config_mod.merged(overrides or {}),
        detector=SimpleNamespace(configure=lambda cfg: None),
        latch_curves=lambda v: latch.__setitem__("value", v),
        curves_enabled=lambda: True,
        thermal=SimpleNamespace(set_boost=lambda g, v: None),
    )
    server = Server(engine, dict(overrides or {}))
    return server, engine, latch


def test_broadcast_drops_closing_and_stalled_subscribers():
    server, _, _ = make_server()
    healthy = FakeWriter()
    gone = FakeWriter(closing=True)
    stalled = FakeWriter(backlog=MAX_SUBSCRIBER_BACKLOG + 1)
    server.subscribers.update({healthy, gone, stalled})
    server.broadcast({"cpu_temp": 50})
    assert server.subscribers == {healthy}
    assert len(healthy.written) == 1
    assert stalled.closed and not gone.closed  # closing one is already on its way out


def test_set_config_persists_only_overrides(tmp_path, monkeypatch):
    saved = {}
    monkeypatch.setattr(config_mod, "save_overrides", lambda o, path=None: saved.update(o))
    server, engine, latch = make_server({"auto": {"on_battery": "cool"}})
    resp = server.dispatch(
        {"op": "set_config", "patch": {"fan_curves": {"enabled": True}}}, writer=None
    )
    assert resp["ok"]
    assert saved == {"auto": {"on_battery": "cool"}, "fan_curves": {"enabled": True}}
    assert engine.config["fan_curves"]["enabled"] is True
    assert engine.config["auto"]["on_battery"] == "cool"
    assert latch["value"] is None  # explicit switch clears the manual-boost latch


def test_manual_boost_latches_curves_off_without_touching_config(monkeypatch):
    monkeypatch.setattr(
        config_mod, "save_overrides", lambda *a, **k: (_ for _ in ()).throw(AssertionError("config written"))
    )
    server, engine, latch = make_server()
    resp = server.dispatch({"op": "set_boost", "group": "cpu", "value": 40}, writer=None)
    assert resp["ok"]
    assert latch["value"] is False
    assert engine.config["fan_curves"]["enabled"] is True  # config untouched
