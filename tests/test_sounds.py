"""Generated UI sound sets: format, levels, click safety, freshness."""

import array
import importlib.util
import math
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOUNDS = ROOT / "src" / "cryo" / "gui" / "assets" / "sounds"

SETS = ("ice", "glass", "deep")
LIMITS = {
    "tap": 0.12, "toggle_on": 0.18, "toggle_off": 0.18, "mode": 0.35,
    "freeze": 1.4, "thaw": 1.2, "connect": 0.5, "disconnect": 0.5, "error": 0.4,
}
CASES = [(s, e) for s in SETS for e in LIMITS]


def load(set_name, event):
    with wave.open(str(SOUNDS / set_name / f"{event}.wav"), "rb") as w:
        params = w.getparams()
        samples = array.array("h", w.readframes(w.getnframes()))
    return params, samples


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("gen_sounds", ROOT / "tools" / "gen_sounds.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_all_files_exist():
    assert len(CASES) == 27
    for s, e in CASES:
        assert (SOUNDS / s / f"{e}.wav").is_file(), f"{s}/{e}"


@pytest.mark.parametrize(("s", "e"), CASES)
def test_format_and_duration(s, e):
    params, samples = load(s, e)
    assert (params.nchannels, params.sampwidth, params.framerate) == (1, 2, 44100)
    seconds = len(samples) / 44100
    assert 0.03 <= seconds <= LIMITS[e]


@pytest.mark.parametrize(("s", "e"), CASES)
def test_levels_and_no_dc(s, e):
    _, x = load(s, e)
    rms = math.sqrt(sum(v * v for v in x) / len(x))
    assert rms > 500, "silent"
    assert max(abs(v) for v in x) < 32767, "clipping"
    assert abs(sum(x) / len(x)) < 0.01 * 32767, "DC offset"


@pytest.mark.parametrize(("s", "e"), CASES)
def test_edges_are_quiet(s, e):
    _, x = load(s, e)
    edge = int(0.002 * 44100)
    limit = 0.1 * 32767
    assert max(abs(v) for v in x[:edge]) < limit
    assert max(abs(v) for v in x[-edge:]) < limit
    assert abs(x[0]) <= 1


def test_total_size():
    total = sum(p.stat().st_size for p in SOUNDS.rglob("*.wav"))
    assert total < 1_500_000


def test_fresh_and_deterministic(gen, tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    gen.generate(first)
    gen.generate(second)
    for s, e in CASES:
        rel = Path(s) / f"{e}.wav"
        a = (first / rel).read_bytes()
        assert a == (second / rel).read_bytes(), f"{rel} not deterministic"
        assert a == (SOUNDS / rel).read_bytes(), f"{rel} is stale; run tools/gen_sounds.py"


def test_check_flag(gen, tmp_path):
    assert gen.main(["--check"]) == 0
    assert gen.main(["--check", "--out", str(tmp_path)]) == 1
