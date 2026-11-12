"""Frost's voice: classification, timing, rotation, copy rules."""

import random
import re
from dataclasses import replace

import pytest

from cryo.gui import voice
from cryo.gui.voice import PROFILE_LABELS, FrostVoice, Snapshot, situation

BASE = Snapshot(
    connected=True, cpu=40.0, gpu=38.0, guard=False, gaming=False,
    ac=True, profile="balanced", rpm=2200,
)


def snap(**kw):
    return replace(BASE, **kw)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(dwell=45.0, seed=1):
    clock = Clock()
    return FrostVoice(random.Random(seed), clock, dwell), clock


# --- classification -------------------------------------------------------

@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({"connected": False}, "disconnected"),
        ({"guard": True}, "guard"),
        ({"gaming": True}, "gaming"),
        ({"cpu": 85.0}, "hot"),
        ({"gpu": 80.0}, "hot"),
        ({"cpu": 70.0}, "warm"),
        ({"ac": False}, "battery"),
        ({"cpu": 45.0, "gpu": 30.0}, "cool"),
        ({"cpu": 55.0}, "mild"),
        ({"cpu": None, "gpu": None}, "blind"),
        ({"cpu": None, "gpu": 90.0}, "hot"),
    ],
)
def test_classification(kw, expected):
    assert situation(snap(**kw)) == expected


def test_priority_order():
    everything = snap(connected=True, guard=True, gaming=True, cpu=95.0, ac=False)
    assert situation(replace(everything, connected=False)) == "disconnected"
    assert situation(everything) == "guard"
    assert situation(replace(everything, guard=False)) == "gaming"
    assert situation(replace(everything, guard=False, gaming=False)) == "hot"
    assert situation(snap(cpu=70.0, ac=False)) == "warm"
    assert situation(snap(cpu=55.0, ac=False)) == "battery"
    assert situation(snap(cpu=None, gpu=None, ac=False)) == "battery"


@pytest.mark.parametrize(
    ("temp", "previous", "expected"),
    [
        (50.0, None, "mild"), (49.9, None, "cool"),
        (49.0, "mild", "mild"), (48.0, "mild", "mild"), (47.9, "mild", "cool"),
        (51.0, "cool", "mild"),
        (65.0, None, "warm"), (64.9, None, "mild"),
        (63.0, "warm", "warm"), (62.9, "warm", "mild"),
        (80.0, None, "hot"), (79.9, None, "warm"),
        (78.0, "hot", "hot"), (77.9, "hot", "warm"),
        (66.0, "mild", "warm"),
    ],
)
def test_hysteresis(temp, previous, expected):
    assert situation(snap(cpu=temp, gpu=None), previous) == expected


def test_hovering_does_not_flap():
    prev = None
    seen = set()
    for t in (49.5, 50.5, 49.5, 50.5, 49.5, 50.5):
        prev = situation(snap(cpu=t), prev)
        seen.add(prev)
    assert seen <= {"cool", "mild"}
    assert prev == "mild"


# --- timed situations ------------------------------------------------------

def test_greeting_window():
    v, clock = make()
    assert v.update(BASE).key.startswith("greeting:")
    clock.t += 5.9
    assert v.update(BASE).key.startswith("greeting:")
    clock.t += 0.2
    assert v.update(BASE).key.startswith("cool:")


def test_greeting_waits_for_connection():
    v, clock = make()
    assert v.update(snap(connected=False)).key.startswith("disconnected:")
    clock.t += 100
    assert v.update(BASE).key.startswith("greeting:")


def test_recovered_window():
    v, clock = make()
    v.update(BASE)
    clock.t += 10
    assert v.update(snap(guard=True)).key.startswith("guard:")
    clock.t += 1
    assert v.update(snap(guard=False)).key.startswith("recovered:")
    clock.t += 19
    assert v.update(snap(guard=False)).key.startswith("recovered:")
    clock.t += 1.5
    assert v.update(snap(guard=False)).key.startswith("cool:")


def test_guard_outranks_recovered_and_profile():
    v, clock = make()
    v.update(BASE)
    clock.t += 10
    v.update(snap(guard=True))
    assert v.update(snap(guard=True, profile="gmode")).key.startswith("guard:")


def test_profile_window_and_label():
    v, clock = make()
    v.update(BASE)
    clock.t += 10
    v.update(BASE)
    line = v.update(snap(profile="gmode"))
    assert line.key.startswith("profile:")
    assert "G-Mode" in line.text
    clock.t += 7.9
    assert v.update(snap(profile="gmode")).key.startswith("profile:")
    clock.t += 0.2
    assert v.update(snap(profile="gmode")).key.startswith("cool:")


def test_no_profile_line_on_first_update():
    v, clock = make()
    clock.t += 1000
    v.update(snap(profile="gmode"))
    v2, _ = make()
    assert not v2.update(snap(profile="quiet")).key.startswith("profile:")


def test_profile_outranks_gaming():
    v, clock = make()
    v.update(snap(gaming=True))
    clock.t += 10
    v.update(snap(gaming=True))
    assert v.update(snap(gaming=True, profile="gmode")).key.startswith("profile:")


# --- dwell and rotation ---------------------------------------------------

def settled(v, clock, **kw):
    v.update(snap(**kw))
    clock.t += 10
    return v.update(snap(**kw))


def test_key_stable_before_dwell_text_follows_numbers():
    v, clock = make(dwell=45.0)
    first = settled(v, clock, cpu=55.0, gpu=None)
    clock.t += 30
    second = v.update(snap(cpu=57.0, gpu=None))
    assert second.key == first.key
    if "{hot}" in voice.LINES["mild"][int(first.key.split(":")[1])]:
        assert second.text != first.text


def test_rotates_after_dwell_without_repeat():
    v, clock = make(dwell=45.0)
    line = settled(v, clock)
    for _ in range(30):
        clock.t += 46
        nxt = v.update(BASE)
        assert nxt.key != line.key
        assert nxt.key.startswith("cool:")
        line = nxt


def test_situation_change_is_immediate():
    v, clock = make()
    settled(v, clock)
    clock.t += 1
    assert v.update(snap(ac=False)).key.startswith("battery:")


def test_deterministic_with_seed():
    def run():
        v, clock = make(seed=42)
        keys = []
        for i in range(40):
            clock.t += 20
            keys.append(v.update(snap(cpu=30.0 + i)).key)
        return keys

    assert run() == run()


def test_line_property_tracks_update():
    v, _ = make()
    out = v.update(BASE)
    assert v.line == out


# --- None handling ---------------------------------------------------------

NONE_CASES = [
    {"cpu": None}, {"gpu": None}, {"rpm": None},
    {"cpu": None, "gpu": None}, {"cpu": None, "gpu": None, "rpm": None},
]
STATES = [
    {}, {"connected": False}, {"guard": True}, {"gaming": True}, {"cpu": 90.0},
    {"cpu": 70.0}, {"cpu": 55.0}, {"ac": False}, {"ac": None},
]


@pytest.mark.parametrize("nones", NONE_CASES)
@pytest.mark.parametrize("state", STATES)
def test_none_values_never_leak(nones, state):
    for seed in range(15):
        v, clock = make(dwell=1.0, seed=seed)
        for _ in range(12):
            line = v.update(snap(**{**state, **nones}))
            assert "None" not in line.text
            assert "  " not in line.text
            assert not re.search(r"(^|[^\d])°C", line.text), line.text
            assert "rpm" not in line.text or re.search(r"\d rpm", line.text), line.text
            clock.t += 2


def test_every_situation_has_always_eligible_variants():
    for name, templates in voice.LINES.items():
        plain = [t for t in templates if voice._needs(t) <= {"profile"} and t not in voice.CONDITIONS]
        assert len(plain) >= 2, name
    empty = snap(cpu=None, gpu=None, rpm=None)
    for name in voice.LINES:
        assert len(voice.eligible(name, empty)) >= 2, name


def test_conditions_reference_real_templates():
    every = {t for ts in voice.LINES.values() for t in ts}
    assert set(voice.CONDITIONS) <= every


RESTING = ("resting", "at ease", "barely awake")
PUSHING = ("pushing hard", "earning their keep", "doing the work", "on it.")


def draws(**kw):
    """Many seeded draws across fan-relevant situations."""
    for seed in range(40):
        for state in ({"cpu": 40.0}, {"cpu": 55.0}, {"cpu": 70.0}, {"cpu": 90.0}):
            v, clock = make(dwell=1.0, seed=seed)
            for _ in range(10):
                yield v.update(snap(**{**state, **kw})).text
                clock.t += 2


def test_high_rpm_never_resting():
    for text in draws(rpm=4200):
        assert not any(p in text for p in RESTING), text


def test_low_rpm_never_pushing():
    for text in draws(rpm=900):
        assert not any(p in text for p in PUSHING), text
        assert "keeping pace" not in text, text


def test_mid_rpm_only_keeping_pace():
    for text in draws(rpm=2200):
        assert not any(p in text for p in RESTING + PUSHING), text


def test_unknown_rpm_makes_no_fan_claim():
    # Guard and recovered state what the guard does, so they are exempt.
    for kw in ({}, {"gaming": True}, {"ac": False}, {"connected": False}):
        for seed in range(30):
            v, clock = make(dwell=1.0, seed=seed)
            for _ in range(10):
                text = v.update(snap(rpm=None, **kw)).text
                assert "fan" not in text.lower(), text
                clock.t += 2
    for text in draws(rpm=None):
        assert "fan" not in text.lower(), text


# --- copy rules -----------------------------------------------------------

def all_rendered():
    full = snap(cpu=71.0, gpu=64.0, rpm=3100)
    for name, templates in voice.LINES.items():
        for i, tpl in enumerate(templates):
            for label_id in PROFILE_LABELS:
                yield name, i, voice.render(tpl, replace(full, profile=label_id))


def test_variant_counts():
    for name, templates in voice.LINES.items():
        minimum = 3 if name in ("greeting", "blind") else 5
        assert len(templates) >= minimum, name
    assert set(voice.LINES) == {
        "disconnected", "guard", "recovered", "profile", "gaming", "hot",
        "warm", "battery", "cool", "mild", "greeting", "blind",
    }


def test_every_template_renders():
    assert sum(1 for _ in all_rendered()) > 60


@pytest.mark.parametrize("temp", [20, 35, 49.6, 64.4, 80, 99.5, 105])
@pytest.mark.parametrize("rpm", [0, 1500, 6000])
def test_max_length_over_grid(temp, rpm):
    for label_id in PROFILE_LABELS:
        s = snap(cpu=temp, gpu=temp, rpm=rpm, profile=label_id)
        for name, templates in voice.LINES.items():
            for tpl in templates:
                text = voice.render(tpl, s)
                assert len(text) <= 64, text


def test_tone_rules():
    for name, i, text in all_rendered():
        where = f"{name}:{i} {text!r}"
        assert "!" not in text, where
        assert chr(0x2014) not in text and chr(0x2013) not in text, where
        assert chr(0x2026) not in text and "..." not in text, where
        assert all(ord(c) < 0x2000 for c in text), f"non-text char: {where}"
        assert text[0].isupper(), where
        assert text.endswith("."), where
        assert "i'm sorry" not in text.lower() and "sorry" not in text.lower(), where
        for sentence in re.split(r"(?<=\.)\s+", text):
            assert sentence[0].isupper() or sentence[0].isdigit(), where


def test_guard_is_not_alarming():
    alarming = ("danger", "critical", "emergency", "warning", "alert", "panic", "overheat")
    for text in (voice.render(t, BASE) for t in voice.LINES["guard"]):
        assert not any(w in text.lower() for w in alarming), text


def test_unknown_profile_falls_back_to_capitalized():
    assert voice.profile_label("turbo") == "Turbo"
    assert voice.profile_label("ultra-low") == "Ultra low"
    assert voice.profile_label("") == "Unknown"
    v, _ = make()
    v.update(snap(profile="balanced"))
    assert PROFILE_LABELS["low-power"] == "Low Power"
    assert PROFILE_LABELS["gmode"] == "G-Mode"
