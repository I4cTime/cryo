"""Frost's voice: a rule-based, local one-line status for the GUI footer.

Frost is a calm, dry cryo technician who is never alarmed. No network, no
model: a classification of the machine state picks a template, and the template
is rendered with live numbers. Pure Python, no Qt.
"""

from __future__ import annotations

import random
import string
import time
from collections.abc import Callable
from dataclasses import dataclass

PROFILE_LABELS: dict[str, str] = {
    "cool": "Cool",
    "quiet": "Quiet",
    "balanced": "Balanced",
    "performance": "Performance",
    "gmode": "G-Mode",
    "custom": "Custom",
    "low-power": "Low Power",
}

RECOVERED_SECONDS = 20.0
PROFILE_SECONDS = 8.0
GREETING_SECONDS = 6.0
HYSTERESIS = 2.0
# Boundaries between cool | mild | warm | hot.
BOUNDS = (50.0, 65.0, 80.0)
BANDS = ("cool", "mild", "warm", "hot")


@dataclass(frozen=True)
class Snapshot:
    connected: bool
    cpu: float | None  # deg C, None when the machine has no thermal readout
    gpu: float | None
    guard: bool  # Thermal Guard engaged
    gaming: bool  # a game was detected
    ac: bool | None  # on AC power; None = unknown
    profile: str  # cool, quiet, balanced, performance, gmode, custom, low-power
    rpm: int | None  # highest fan rpm


@dataclass(frozen=True)
class Line:
    key: str  # "<situation>:<variant index>"; changes only when the template changes
    text: str  # rendered with live numbers; may change every update


def profile_label(profile_id: str) -> str:
    """Display label for a daemon profile id, with a tidy fallback."""
    if profile_id in PROFILE_LABELS:
        return PROFILE_LABELS[profile_id]
    cleaned = profile_id.replace("-", " ").replace("_", " ").strip()
    return cleaned.capitalize() if cleaned else "Unknown"


def hottest(snap: Snapshot) -> float | None:
    temps = [t for t in (snap.cpu, snap.gpu) if t is not None]
    return max(temps) if temps else None


def situation(snap: Snapshot, previous: str | None = None) -> str:
    """Base classification (no timed situations) with 2 degree hysteresis.

    `previous` is the base situation returned last time; a reading that
    hovers at a boundary keeps the band it was already in.
    """
    if not snap.connected:
        return "disconnected"
    if snap.guard:
        return "guard"
    if snap.gaming:
        return "gaming"
    temp = hottest(snap)
    if temp is None:
        return "battery" if snap.ac is False else "blind"

    # Battery stands in for the cool and mild bands; treat it as mild.
    prev_band = {"battery": 1}.get(previous or "")
    if prev_band is None and previous in BANDS:
        prev_band = BANDS.index(previous)
    band = 0
    for i, bound in enumerate(BOUNDS, start=1):
        edge = bound - HYSTERESIS if prev_band is not None and prev_band >= i else bound
        if temp >= edge:
            band = i
    if band <= 1 and snap.ac is False:
        return "battery"
    return BANDS[band]


# Templates. Fields: {cpu} {gpu} {hot} {rpm} {profile}. Temperatures carry
# their unit in the template. Every situation has several variants that need
# no numbers and no condition. Fan-state claims are gated by CONDITIONS below,
# so Frost never says more about the machine than the data supports.
LINES: dict[str, tuple[str, ...]] = {
    "disconnected": (
        "No word from cryod. I am watching the door.",
        "The daemon is silent. I will keep the light on.",
        "Cannot reach cryod. Standing by.",
        "Nothing on the line from cryod. Waiting.",
        "The daemon is away. I will be here when it returns.",
        "Link is down, so no opinions about the machine.",
    ),
    "greeting": (
        "Frost here. Sensors are coming online.",
        "Good to see you. Checking the machine over.",
        "Connected. {profile} profile is set.",
        "Systems up. Let us see what the machine is doing.",
    ),
    "blind": (
        "Connected, but this machine reports no temperatures.",
        "No thermal readout here. I am working by feel.",
        "Sensors are quiet. Nothing to read, nothing to report.",
        "No temperatures to read. Everything else looks steady.",
        "No thermal data on this model. Carrying on.",
    ),
    "guard": (
        "Guard is up. Fans at full until we are under the line.",
        "Thermal Guard engaged. Fans at full while we cool.",
        "Guard is holding at {hot}\u00b0C. Fans at full.",
        "Guard has the helm. Fans at full, nothing more to do.",
        "Guard engaged. Holding the line while the fans work.",
        "Fans at full and the guard is on duty. Steady.",
        "Guard is on at {hot}\u00b0C. Fans at {rpm} rpm.",
    ),
    "recovered": (
        "Guard released. Back under the line.",
        "Guard released. Temperatures are back in range.",
        "Down to {hot}\u00b0C. The guard has stood down.",
        "All clear. The guard has stood down.",
        "Back to normal at {hot}\u00b0C. Fans are easing off.",
        "Guard is off. Tidy work from the fans.",
        "Recovered. Nothing more to do here.",
    ),
    "profile": (
        "Switched to {profile}. Noted.",
        "{profile} mode is set. The firmware takes it from here.",
        "Now running {profile}. Carry on.",
        "{profile} it is. Understood.",
        "Mode change acknowledged: {profile}.",
        "Profile is now {profile}.",
        "{profile} is live.",
    ),
    "gaming": (
        "Game detected. I will stay out of its way.",
        "Play on. I am keeping an eye on the heat.",
        "Game detected. Standing watch.",
        "Game on. I will keep the readings handy.",
        "Game detected. Watching the heat, currently {hot}\u00b0C.",
        "Gaming load. Sitting at {hot}\u00b0C.",
        "Game running. Fans at {rpm} rpm, nothing to report.",
    ),
    "hot": (
        "Heat is up. I am not worried.",
        "Running hot. I am keeping count.",
        "Temperatures are high. I am watching them.",
        "At {hot}\u00b0C. Fans at {rpm} rpm, and I am watching.",
        "Hot spell at {hot}\u00b0C. I am watching it.",
        "CPU {cpu}\u00b0C, GPU {gpu}\u00b0C. Within my tolerance.",
        "Running warm at {hot}\u00b0C. The fans are doing the work.",
        "It is warm in here. The fans are pushing hard.",
        "Running hot. The fans are earning their keep.",
    ),
    "warm": (
        "A little warm. Nothing to worry about.",
        "Working up a sweat, as far as silicon can.",
        "Holding at {hot}\u00b0C. Nothing to be done yet.",
        "Comfortably warm. Fans at {rpm} rpm.",
        "CPU {cpu}\u00b0C, GPU {gpu}\u00b0C. Steady enough.",
        "Warming up at {hot}\u00b0C. Fans are keeping pace.",
        "Load is showing at {hot}\u00b0C. The fans are on it.",
    ),
    "mild": (
        "All quiet, with a little warmth.",
        "Nothing to see here, which is how I like it.",
        "Mild at {hot}\u00b0C. Nothing to report.",
        "A calm {hot}\u00b0C. Fans at {rpm} rpm.",
        "CPU {cpu}\u00b0C, GPU {gpu}\u00b0C. Pleasant enough.",
        "Steady at {hot}\u00b0C. Nothing to add.",
        "Holding at {hot}\u00b0C. Fans are barely awake.",
    ),
    "cool": (
        "Cold and calm, just the way I like it.",
        "Still waters. Nothing to do but wait.",
        "Very calm. {cpu}\u00b0C on the CPU.",
        "Not a degree out of place at {hot}\u00b0C.",
        "A calm {hot}\u00b0C. I could do this all day.",
        "Cool at {hot}\u00b0C. The fans are resting.",
        "Everything is cool. The fans are at ease.",
    ),
    "battery": (
        "On battery. Keeping things lean.",
        "Running on battery. Nothing else to report.",
        "No wall power. Efficiency first.",
        "Unplugged. Carrying on.",
        "Battery power at {hot}\u00b0C. Noted.",
        "On battery with {profile} set. Every watt counts.",
    ),
}


def _resting(snap: Snapshot) -> bool:
    return snap.rpm is not None and snap.rpm < 1500


def _keeping_pace(snap: Snapshot) -> bool:
    return snap.rpm is not None and 1500 <= snap.rpm < 3000


def _working(snap: Snapshot) -> bool:
    return snap.rpm is not None and snap.rpm >= 3000


# Optional per-template predicates, keyed by template text. A template with
# an entry is eligible only while its predicate holds for the snapshot.
CONDITIONS: dict[str, Callable[[Snapshot], bool]] = {
    "Holding at {hot}\u00b0C. Fans are barely awake.": _resting,
    "Cool at {hot}\u00b0C. The fans are resting.": _resting,
    "Everything is cool. The fans are at ease.": _resting,
    "Warming up at {hot}\u00b0C. Fans are keeping pace.": _keeping_pace,
    "Running warm at {hot}\u00b0C. The fans are doing the work.": _working,
    "It is warm in here. The fans are pushing hard.": _working,
    "Running hot. The fans are earning their keep.": _working,
    "Load is showing at {hot}\u00b0C. The fans are on it.": _working,
}


def _needs(template: str) -> frozenset[str]:
    return frozenset(
        name for _, name, _, _ in string.Formatter().parse(template) if name
    )


def render(template: str, snap: Snapshot) -> str:
    """Render a template with live numbers; whole degrees, label for profile."""
    hot = hottest(snap)
    return template.format(
        cpu="" if snap.cpu is None else f"{round(snap.cpu)}",
        gpu="" if snap.gpu is None else f"{round(snap.gpu)}",
        hot="" if hot is None else f"{round(hot)}",
        rpm="" if snap.rpm is None else f"{int(snap.rpm)}",
        profile=profile_label(snap.profile),
    )


def _available(name: str, snap: Snapshot) -> bool:
    have = {
        "cpu": snap.cpu is not None,
        "gpu": snap.gpu is not None,
        "hot": hottest(snap) is not None,
        "rpm": snap.rpm is not None,
        "profile": True,
    }
    return have.get(name, False)


def eligible(situation_name: str, snap: Snapshot) -> list[int]:
    """Indices of variants whose numbers are all present in the snapshot."""
    return [
        i
        for i, tpl in enumerate(LINES[situation_name])
        if all(_available(n, snap) for n in _needs(tpl))
        and CONDITIONS.get(tpl, lambda _s: True)(snap)
    ]


class FrostVoice:
    """Picks and rotates Frost's line as the machine state changes."""

    def __init__(
        self,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
        dwell: float = 45.0,
    ) -> None:
        self._rng = rng or random.Random()
        self._clock = clock
        self._dwell = dwell
        self._base: str | None = None
        self._last_profile: str | None = None
        self._last_guard = False
        self._greet_until: float | None = None
        self._recovered_until = 0.0
        self._profile_until = 0.0
        self._situation: str | None = None
        self._variant = 0
        self._chosen_at = 0.0
        self._line = Line("idle:0", "Standing by.")

    @property
    def line(self) -> Line:
        return self._line

    def _effective(self, snap: Snapshot, now: float) -> str:
        """Base situation, overlaid with the timed ones."""
        first = self._last_profile is None
        if not first and snap.profile != self._last_profile:
            self._profile_until = now + PROFILE_SECONDS
        self._last_profile = snap.profile
        if self._last_guard and not snap.guard:
            self._recovered_until = now + RECOVERED_SECONDS
        self._last_guard = snap.guard
        if snap.connected and self._greet_until is None:
            self._greet_until = now + GREETING_SECONDS

        self._base = situation(snap, self._base)
        if self._base in ("disconnected", "guard"):
            return self._base
        if now < self._recovered_until:
            return "recovered"
        if now < self._profile_until:
            return "profile"
        if self._greet_until is not None and now < self._greet_until:
            return "greeting"
        return self._base

    def update(self, snap: Snapshot) -> Line:
        now = self._clock()
        name = self._effective(snap, now)
        options = eligible(name, snap)
        same = name == self._situation
        if same and self._variant in options and now - self._chosen_at < self._dwell:
            variant = self._variant
        else:
            pool = options
            if same and len(options) > 1:
                pool = [i for i in options if i != self._variant]
            variant = self._rng.choice(pool)
            self._chosen_at = now
            self._situation = name
            self._variant = variant
        text = render(LINES[name][variant], snap)
        self._line = Line(f"{name}:{variant}", text)
        return self._line
