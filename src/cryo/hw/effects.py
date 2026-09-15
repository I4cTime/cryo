"""High-level lighting effects for the AW-ELC 4-zone keyboard.

Effect recipes ported from tr1xem/AWCC's EffectController (GPL-3.0), plus
Cryo-specific "quantum" presets using the I4C palette.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Callable, TypeVar

import usb.core

from cryo.hw import elc as _elc

log = logging.getLogger(__name__)

T = TypeVar("T")

# m18 R2 keyboard: four zones, left to right.
KEYBOARD_ZONES = [0x00, 0x01, 0x02, 0x03]

# Animation slot used for user effects (same slot upstream uses, so Cryo
# and stock awcc overwrite each other cleanly instead of stacking).
ANIM_USER = 0x0061

# I4C quantum palette (lib/palette.ts equivalents)
QUANTUM_CYAN = 0x00D1FF
QUANTUM_VIOLET = 0x7B2DFF

RAINBOW = [0xFF0000, 0xFFA500, 0xFFFF00, 0x008000, 0x00BFFF, 0x0000FF, 0x800080]


class Effects:
    def __init__(self, zones: list[int] | None = None) -> None:
        self.zones = zones or KEYBOARD_ZONES
        self._elc: _elc.Elc | None = None

    def available(self) -> bool:
        try:
            self._device()
            return True
        except _elc.ElcNotFound:
            return False

    def _device(self) -> _elc.Elc:
        if self._elc is None:
            self._elc = _elc.Elc()
        return self._elc

    def reset(self) -> None:
        """Forget the open handle; the next call re-enumerates the device.

        Suspend/resume re-enumerates USB, which leaves a claimed handle
        pointing at a device that no longer exists.
        """
        if self._elc is not None:
            try:
                self._elc.release()
            except Exception:
                pass
        self._elc = None

    def _retrying(self, fn: Callable[[], T]) -> T:
        """Run a lighting operation; on a USB error reopen the ELC once."""
        try:
            return fn()
        except usb.core.USBError as exc:
            log.warning("ELC write failed (%s); reopening the controller", exc)
            self.reset()
            return fn()

    @contextmanager
    def _session(self):
        dev = self._device()
        dev.acquire()
        try:
            yield dev
        finally:
            dev.release()

    @contextmanager
    def _user_animation(self):
        """Remove/start/save/set-default wrapper around a user effect."""
        with self._session() as dev:
            dev.animation(_elc.ANIM_REMOVE, ANIM_USER)
            dev.animation(_elc.ANIM_CONFIG_START, ANIM_USER)
            yield dev
            dev.animation(_elc.ANIM_CONFIG_SAVE, ANIM_USER)
            dev.animation(_elc.ANIM_SET_DEFAULT, ANIM_USER)

    # -- effects -----------------------------------------------------------

    def brightness(self, value: int) -> None:
        value = max(0, min(100, value))

        def op() -> None:
            with self._session() as dev:
                dev.set_dim(100 - value, self.zones)

        self._retrying(op)

    def static(self, rgb: int) -> None:
        with self._user_animation() as dev:
            for zone in self.zones:
                dev.zone_select(1, [zone])
                dev.add_action(_elc.ACTION_COLOR, 1, 2, rgb)

    def breathe(self, rgb: int) -> None:
        with self._user_animation() as dev:
            for zone in self.zones:
                dev.zone_select(1, [zone])
                dev.add_action(_elc.ACTION_MORPH, 500, 64, rgb)
                dev.add_action(_elc.ACTION_MORPH, 2000, 64, rgb)
                dev.add_action(_elc.ACTION_MORPH, 500, 64, 0)
                dev.add_action(_elc.ACTION_MORPH, 2000, 64, 0)

    def spectrum(self, duration: int = 2000) -> None:
        with self._user_animation() as dev:
            for zone in self.zones:
                dev.zone_select(1, [zone])
                for color in RAINBOW:
                    dev.add_action(_elc.ACTION_MORPH, duration, 64, color)

    def rainbow_wave(self, duration: int = 500) -> None:
        with self._user_animation() as dev:
            for i, zone in enumerate(self.zones):
                dev.zone_select(1, [zone])
                for j in range(len(RAINBOW)):
                    dev.add_action(_elc.ACTION_MORPH, duration, 64, RAINBOW[(i + j) % len(RAINBOW)])

    def wave(self, rgb: int) -> None:
        n = len(self.zones)
        with self._user_animation() as dev:
            for i, zone in enumerate(self.zones):
                dev.zone_select(1, [zone])
                for j in range(n):
                    dev.add_action(_elc.ACTION_MORPH, 500, 64, rgb if i == j else 0)

    def back_and_forth(self, rgb: int) -> None:
        n = len(self.zones)
        if n <= 1:
            return self.static(rgb)
        sequence = list(range(n)) + list(range(n - 2, 0, -1))
        with self._user_animation() as dev:
            for i, zone in enumerate(self.zones):
                dev.zone_select(1, [zone])
                for step in sequence:
                    dev.add_action(_elc.ACTION_MORPH, 500, 64, rgb if i == step else 0)

    def quantum(self, duration: int = 3000) -> None:
        """Cryo signature: slow cyan <-> violet morph across the board."""
        with self._user_animation() as dev:
            for zone in self.zones:
                dev.zone_select(1, [zone])
                dev.add_action(_elc.ACTION_MORPH, duration, 64, QUANTUM_CYAN)
                dev.add_action(_elc.ACTION_MORPH, duration, 64, QUANTUM_VIOLET)

    def off(self) -> None:
        self.static(0x000000)

    # -- dispatch used by daemon API --------------------------------------

    def apply(self, effect: str, color: int = QUANTUM_CYAN, duration: int | None = None) -> None:
        self._retrying(lambda: self._apply(effect, color, duration))

    def _apply(self, effect: str, color: int, duration: int | None) -> None:
        match effect:
            case "static":
                self.static(color)
            case "breathe":
                self.breathe(color)
            case "spectrum":
                self.spectrum(duration or 2000)
            case "rainbow":
                self.rainbow_wave(duration or 500)
            case "wave":
                self.wave(color)
            case "backforth":
                self.back_and_forth(color)
            case "quantum":
                self.quantum(duration or 3000)
            case "off":
                self.off()
            case _:
                raise ValueError(f"unknown effect {effect!r}")
