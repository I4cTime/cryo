"""Resume re-apply and cryoctl status rendering — stubs only, no hardware."""

from types import SimpleNamespace

import pytest

from cryo import __version__, cli
from cryo.daemon import config as config_mod
from cryo.daemon.engine import Engine


class StubThermal:
    def __init__(self, profile):
        self._profile = profile
        self.profile_writes: list[str] = []

    def profile(self):
        return self._profile

    def set_profile(self, name):
        if self._profile is None:
            raise RuntimeError("this machine exposes no platform profiles (power modes)")
        self.profile_writes.append(name)

    def cpu_cap(self):
        return 100

    def set_cpu_cap(self, pct):
        pass


def make_engine(profile):
    engine = Engine.__new__(Engine)
    engine.config = config_mod.merged({"lighting": {"restore": False}})
    engine.thermal = StubThermal(profile)
    engine.effects = SimpleNamespace(reset=lambda: None, available=lambda: False)
    reinits: list[bool] = []
    engine.gpu = SimpleNamespace(
        reinit=lambda: reinits.append(True) or True, available=lambda: True
    )
    engine.reinits = reinits
    engine.capabilities = {"cpu_cap": False, "game_detection": False}
    engine._curve_anchor = {"cpu": 70.0}
    engine._curve_boost = {"cpu": 35}
    return engine


def test_reapply_reasserts_the_profile():
    engine = make_engine("balanced")
    result = engine.reapply()
    assert result["profile"] == "balanced"
    assert engine.thermal.profile_writes == ["balanced"]
    assert engine._curve_anchor == {} and engine._curve_boost == {}


def test_reapply_without_platform_profiles_still_reinits_nvml():
    # Limited-mode machines (no platform profiles) used to raise out of
    # reapply, skipping the NVML re-init and CPU cap after every resume.
    engine = make_engine(None)
    result = engine.reapply()
    assert result["profile"] is None
    assert result["nvml"] is True
    assert engine.reinits == [True]
    assert engine.capabilities["game_detection"] is True


def frame(**extra):
    return {
        "profile": "balanced", "ac": True, "turbo": True,
        "cpu_temp": 50.0, "gpu_temp": 45.0, "fans": [], **extra,
    }


def test_status_hides_turbo_when_the_machine_has_no_control():
    assert "turbo" not in cli.fmt_status(frame(turbo=None))
    assert "turbo on" in cli.fmt_status(frame(turbo=True))
    assert "turbo off" in cli.fmt_status(frame(turbo=False))


def test_status_shows_the_daemon_version_and_flags_a_stale_daemon():
    current = cli.fmt_status(frame(capabilities={"version": __version__}))
    assert f"cryod     {__version__}" in current
    assert "restart cryod" not in current
    stale = cli.fmt_status(frame(capabilities={"version": "0.0.1"}))
    assert "restart cryod" in stale


def test_version_flag(capsys, monkeypatch):
    monkeypatch.setattr(cli.sys, "argv", ["cryoctl", "--version"])
    cli.main()
    assert capsys.readouterr().out.strip() == f"cryoctl {__version__}"


def test_daemon_error_exits_nonzero(monkeypatch, capsys):
    class FakeSocket:
        def __init__(self, *a):
            pass

        def connect(self, path):
            pass

        def sendall(self, data):
            pass

        def makefile(self):
            import io

            return io.StringIO('{"ok": false, "error": "boom"}\n')

    monkeypatch.setattr(cli.socket, "socket", FakeSocket)
    with pytest.raises(SystemExit) as exc:
        cli.request({"op": "reapply"})
    assert exc.value.code == 1
    assert "boom" in capsys.readouterr().out
