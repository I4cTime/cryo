"""GameDetector hysteresis and GpuSense process filtering — no NVML."""

from types import SimpleNamespace

from cryo.daemon.gamesense import GameDetector, GpuSense

CFG = {
    "game_enter_util": 60,
    "game_enter_secs": 10,
    "game_exit_util": 20,
    "game_exit_secs": 10,
    "game_ignore": ["steam", "cosmic-comp"],
    "game_min_vram_mb": 400,
}

GAME = ["eldenring.exe"]


def make_detector(poll=5.0):
    return GameDetector(CFG, poll)


# -- GameDetector ----------------------------------------------------------

def test_enters_after_sustained_util_with_candidate():
    det = make_detector()
    assert det.sample(80, GAME) is None  # 5s accumulated
    assert det.sample(80, GAME) is True  # 10s -> enter
    assert det.gaming


def test_never_enters_without_candidate_process():
    det = make_detector()
    for _ in range(10):
        assert det.sample(95, []) is None
    assert not det.gaming


def test_util_dip_resets_enter_clock():
    det = make_detector()
    det.sample(80, GAME)
    det.sample(10, GAME)  # dip resets the clock
    assert det.sample(80, GAME) is None
    assert det.sample(80, GAME) is True


def test_exits_after_sustained_low_util():
    det = make_detector()
    det.sample(80, GAME)
    det.sample(80, GAME)
    assert det.gaming
    assert det.sample(10, GAME) is None
    assert det.sample(10, GAME) is False
    assert not det.gaming


def test_losing_candidate_exits_even_at_high_util():
    det = make_detector()
    det.sample(80, GAME)
    det.sample(80, GAME)
    det.sample(80, [])  # compositor still busy, game gone
    assert det.sample(80, []) is False


def test_none_util_is_no_signal():
    det = make_detector()
    assert det.sample(None, GAME) is None
    assert not det.gaming


# -- GpuSense process filtering (faked NVML) -------------------------------

class FakeNvml:
    NVML_CLOCK_GRAPHICS = 0

    def __init__(self, graphics=(), compute=(), names=None):
        self._graphics = list(graphics)
        self._compute = list(compute)
        self._names = names or {}

    def nvmlDeviceGetGraphicsRunningProcesses(self, handle):
        return self._graphics

    def nvmlDeviceGetComputeRunningProcesses(self, handle):
        return self._compute

    def nvmlSystemGetProcessName(self, pid):
        return self._names[pid - BASE_PID]


# Way past any live pid so /proc/<pid>/cmdline misses and the tests
# exercise the NVML-name fallback deterministically.
BASE_PID = 4_000_000


def proc(pid, mb):
    return SimpleNamespace(pid=BASE_PID + pid, usedGpuMemory=mb * 1024 * 1024)


def make_sense(nvml):
    sense = GpuSense.__new__(GpuSense)
    sense._nvml = nvml
    sense._handle = object()
    return sense


def test_processes_merges_kinds_and_sorts_by_vram():
    nvml = FakeNvml(
        graphics=[proc(1, 500), proc(2, 8000)],
        compute=[proc(3, 1200)],
        names={1: b"/usr/bin/Xwayland", 2: "/games/EldenRing.exe", 3: b"ollama"},
    )
    assert make_sense(nvml).processes() == [
        ("eldenring.exe", 8000), ("ollama", 1200), ("xwayland", 500),
    ]


def test_game_candidates_filters_vram_and_exact_ignore():
    nvml = FakeNvml(
        graphics=[proc(1, 300), proc(2, 8000), proc(3, 900), proc(4, 700)],
        names={
            1: b"tinytool",                                # under min_vram
            2: b"StarRuptureGameSteam-Win64-Shipping.exe", # must NOT match "steam"
            3: b"steam",                                   # exact ignore
            4: b"cosmic-comp",                             # exact ignore
        },
    )
    sense = make_sense(nvml)
    assert sense.game_candidates(["steam", "cosmic-comp"], 400) == [
        "starrupturegamesteam-win64-shipping.exe"
    ]


def test_chromium_proc_titles_reduce_to_binary():
    nvml = FakeNvml(
        graphics=[proc(1, 200), proc(2, 300)],
        names={
            1: "brave --type=gpu-process --ozone-platform=x11",
            2: "/games/Elden Ring/eldenring.exe",  # space in path survives
        },
    )
    assert make_sense(nvml).processes() == [
        ("eldenring.exe", 300), ("brave", 200),
    ]


def test_wine_backslash_paths_get_basenamed():
    nvml = FakeNvml(
        graphics=[proc(1, 9000)],
        names={1: "Z:\\games\\Elden Ring\\eldenring.exe"},
    )
    assert make_sense(nvml).processes() == [("eldenring.exe", 9000)]


def test_proc_name_prefers_cmdline_argv0():
    import os

    # A real pid whose cmdline we control: our own. NVML name is the
    # driver-580-style full command line and must NOT win.
    import sys
    nvml = FakeNvml(names={})
    sense = make_sense(nvml)
    name = sense._proc_name(os.getpid())
    assert name == sys.argv[0] or name.endswith("pytest") or "python" in name.lower()


def test_processes_none_when_nvml_missing():
    sense = GpuSense.__new__(GpuSense)
    sense._nvml = None
    sense._handle = None
    assert sense.processes() is None
    assert sense.game_candidates([], 400) is None
    assert sense.memory() is None
    assert sense.power_w() is None
    assert sense.clock_mhz() is None


def test_snapshot_returns_all_and_graphics_only():
    nvml = FakeNvml(
        graphics=[proc(1, 2000)],
        compute=[proc(2, 500)],
        names={1: "/games/Game.exe", 2: "/usr/bin/ollama"},
    )
    every, graphics = make_sense(nvml).snapshot()
    assert every == [("game.exe", 2000), ("ollama", 500)]
    assert graphics == [("game.exe", 2000)]


def test_game_candidates_accepts_precomputed_procs():
    sense = GpuSense.__new__(GpuSense)
    sense._nvml = None
    assert sense.game_candidates([], 400, procs=[("game.exe", 2000), ("tiny", 10)]) == [
        "game.exe"
    ]


def test_maybe_reinit_retries_after_backoff(monkeypatch):
    from cryo.daemon import gamesense

    sense = GpuSense.__new__(GpuSense)
    sense._nvml = None
    sense._handle = None
    sense._ticks_since_attempt = 0
    sense._announced_missing = True
    attempts = []
    monkeypatch.setattr(sense, "reinit", lambda: attempts.append(1) or False)
    for _ in range(gamesense.NVML_RETRY_TICKS - 1):
        assert sense.maybe_reinit() is False
    assert attempts == []
    sense.maybe_reinit()
    assert attempts == [1]
