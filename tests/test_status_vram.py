"""VRAM in the status frame: daemon-side session peak + `cryoctl status` line."""

from cryo.cli import fmt_status
from cryo.daemon.engine import Engine


def make_engine():
    engine = Engine.__new__(Engine)
    engine._peaks = {"cpu": 0.0, "gpu": 0.0, "vram": 0}
    return engine


def frame(**vals):
    return {"cpu_temp": 50.0, "gpu_temp": 45.0, "vram_used_mb": None, **vals}


def test_vram_peak_tracks_session_high_water_mark():
    engine = make_engine()
    for used in (1400, 6200, 3100):
        t = frame(vram_used_mb=used)
        engine._track_peaks(t)
    assert t["vram_peak_mb"] == 6200
    assert t["cpu_peak"] == 50.0


def test_vram_peak_is_none_without_nvml():
    engine = make_engine()
    t = frame()
    engine._track_peaks(t)
    assert t["vram_peak_mb"] is None


def test_vram_peak_survives_nvml_dropping_out():
    engine = make_engine()
    engine._track_peaks(frame(vram_used_mb=4096))
    t = frame()
    engine._track_peaks(t)
    assert t["vram_peak_mb"] == 4096


def vram_line(st):
    return next(line for line in fmt_status(st).splitlines() if line.startswith("vram"))


def test_status_vram_line_shows_share_and_peak():
    st = {"vram_used_mb": 1434, "vram_total_mb": 12288, "vram_peak_mb": 6246}
    assert vram_line(st) == "vram      1.4 / 12.0 GB (12%)  ·  peak 6.1 GB"


def test_status_vram_line_without_peak_from_older_daemon():
    st = {"vram_used_mb": 6144, "vram_total_mb": 12288}
    assert vram_line(st) == "vram      6.0 / 12.0 GB (50%)"


def test_status_omits_vram_without_nvml():
    st = {"vram_used_mb": None, "vram_total_mb": None, "vram_peak_mb": None}
    assert not any(line.startswith("vram") for line in fmt_status(st).splitlines())


def test_status_lists_vram_procs_under_the_vram_line():
    st = {
        "vram_used_mb": 2048, "vram_total_mb": 12288,
        "vram_procs": [{"name": "icarus", "vram_mb": 1536}],
    }
    lines = fmt_status(st).splitlines()
    i = next(i for i, line in enumerate(lines) if line.startswith("vram"))
    assert lines[i + 1].strip() == "1.5 GB  icarus"
