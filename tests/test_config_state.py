"""Config is an overrides overlay; state lives in its own file."""

import json

from cryo.daemon import config as config_mod
from cryo.daemon import state as state_mod


# -- config ------------------------------------------------------------------

def test_missing_config_runs_on_defaults(tmp_path):
    assert config_mod.load_overrides(tmp_path / "config.json") == {}
    assert config_mod.load(tmp_path / "config.json") == config_mod.DEFAULTS


def test_broken_config_runs_on_defaults(tmp_path, caplog):
    path = tmp_path / "config.json"
    path.write_text("{ not json")
    assert config_mod.load_overrides(path) == {}
    assert "unreadable" in caplog.text


def test_non_object_config_runs_on_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[1, 2, 3]")
    assert config_mod.load_overrides(path) == {}


def test_partial_config_keeps_tracking_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"auto": {"on_battery": "cool"}}))
    cfg = config_mod.load(path)
    assert cfg["auto"]["on_battery"] == "cool"
    assert cfg["auto"]["on_ac"] == config_mod.DEFAULTS["auto"]["on_ac"]
    assert cfg["thermal_guard"] == config_mod.DEFAULTS["thermal_guard"]


def test_save_overrides_writes_only_overrides(tmp_path):
    path = tmp_path / "config.json"
    overrides = {"fan_curves": {"enabled": False}}
    config_mod.save_overrides(overrides, path)
    assert json.loads(path.read_text()) == overrides
    assert not (tmp_path / "config.json.tmp").exists()


# -- state -------------------------------------------------------------------

def test_missing_state_is_defaults(tmp_path):
    assert state_mod.load(tmp_path / "state.json") == state_mod.DEFAULT_STATE


def test_state_roundtrip_and_unknown_keys_dropped(tmp_path):
    path = tmp_path / "state.json"
    state_mod.save(
        {"lighting": {"effect": "static", "color": "FF0000", "brightness": 40}}, path
    )
    loaded = state_mod.load(path)
    assert loaded["lighting"]["effect"] == "static"
    assert loaded["fan_curves_enabled"] is None
    path.write_text(json.dumps({"fan_curves_enabled": False, "bogus": 1}))
    loaded = state_mod.load(path)
    assert loaded["fan_curves_enabled"] is False
    assert "bogus" not in loaded


def test_broken_state_starts_fresh(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("nope")
    assert state_mod.load(path) == state_mod.DEFAULT_STATE
