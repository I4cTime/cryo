"""High-level lighting effects for the AW-ELC chassis lights.

On the m16/m18 R1/R2 family the ELC (187c:0551) drives the chassis
lights, not the keyboard: ids 0 and 1 are the rear exhaust rings, 2 the
lid logo and 4 the power button (probed on the m18 R2, 2026-10-22). Id 3
is a phantom and id 5 is poison: a zone list containing 5 makes the
firmware drop the whole animation. The per-key keyboard is a separate USB
device, see keyboard.py. Multi-zone effects (wave, bounce) step across
rings, lid, button in that order.

Effects are written into the controller's power-state animation slots
(opcode 0x22; AC charged/charging and battery on/low get the effect, the
two sleep slots go dark) rather than the post-boot user animation 0x61.
The controller layers both families and blends them per zone, and the
power-state layer keeps re-asserting on the power button, which left the
button flickering and then dark when only the user animation drove it.
One family for everything means no blending, the button animates like
the rings, lights go off in sleep, and the effect survives a reboot
because the slots are persistent (AWCC on Windows reprograms them).

Effect recipes ported from tr1xem/AWCC's EffectController (GPL-3.0), plus
Cryo-specific "quantum" presets using the I4C palette.
"""

from __future__ import annotations

import logging
from typing import Callable, TypeVar

import usb.core

from cryo.hw import elc as _elc

log = logging.getLogger(__name__)

T = TypeVar("T")

# Chassis light ids on 0551 laptops: exhaust rings, lid logo, power button.
CHASSIS_ZONES = [0x00, 0x01, 0x02, 0x04]

# Power-state slots that show the effect; the rest (AC sleep 0x5b, battery
# sleep 0x5e) are written dark.
ACTIVE_SLOTS = (0x5C, 0x5D, 0x5F, 0x60)
# The post-boot user animation; retired so it never blends with the slots.
ANIM_USER = 0x0061

# I4C quantum palette (lib/palette.ts equivalents)
QUANTUM_CYAN = 0x00D1FF
QUANTUM_VIOLET = 0x7B2DFF

RAINBOW = [0xFF0000, 0xFFA500, 0xFFFF00, 0x008000, 0x00BFFF, 0x0000FF, 0x800080]

# (action, duration, tempo, rgb)
Action = tuple[int, int, int, int]
# zone -> its action list, in zone order
Program = list[tuple[int, list[Action]]]


class Effects:
    def __init__(self, zones: list[int] | None = None, elc_factory=None) -> None:
        self.zones = zones or CHASSIS_ZONES
        self._elc: _elc.Elc | None = None
        self._factory = elc_factory or _elc.Elc

    def available(self) -> bool:
        try:
            self._device()
            return True
        except _elc.ElcNotFound:
            return False

    def _device(self) -> _elc.Elc:
        if self._elc is None:
            self._elc = self._factory()
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

    # -- programming --------------------------------------------------------

    def _write(self, program: Program) -> None:
        """Write a program into every power-state slot (dark in the sleep
        slots) and retire the user animation."""
        dark: Program = [(zone, [(_elc.ACTION_COLOR, 0xFFFF, 1, 0x000000)]) for zone in self.zones]
        dev = self._device()
        dev.acquire()
        try:
            dev.animation(_elc.ANIM_REMOVE, ANIM_USER)
            for slot in _elc.POWER_SLOTS:
                op = _elc.OP_POWER_ANIMATION
                dev.animation(_elc.ANIM_REMOVE, slot, op)
                dev.animation(_elc.ANIM_CONFIG_START, slot, op)
                for zone, actions in program if slot in ACTIVE_SLOTS else dark:
                    dev.zone_select(1, [zone])
                    for action, duration, tempo, rgb in actions:
                        dev.add_action(action, duration, tempo, rgb)
                dev.animation(_elc.ANIM_CONFIG_SAVE, slot, op)
                dev.animation(_elc.ANIM_SET_DEFAULT, slot, op)
        finally:
            dev.release()

    def _per_zone(self, actions: Callable[[int], list[Action]]) -> Program:
        return [(zone, actions(i)) for i, zone in enumerate(self.zones)]

    # -- effects -----------------------------------------------------------

    def brightness(self, value: int) -> None:
        value = max(0, min(100, value))

        def op() -> None:
            dev = self._device()
            dev.acquire()
            try:
                dev.set_dim(100 - value, self.zones)
            finally:
                dev.release()

        self._retrying(op)

    def static(self, rgb: int) -> None:
        self._write(self._per_zone(lambda i: [(_elc.ACTION_COLOR, 0xFFFF, 1, rgb)]))

    def breathe(self, rgb: int) -> None:
        self._write(self._per_zone(lambda i: [
            (_elc.ACTION_MORPH, 500, 64, rgb),
            (_elc.ACTION_MORPH, 2000, 64, rgb),
            (_elc.ACTION_MORPH, 500, 64, 0),
            (_elc.ACTION_MORPH, 2000, 64, 0),
        ]))

    def spectrum(self, duration: int = 2000) -> None:
        self._write(self._per_zone(lambda i: [
            (_elc.ACTION_MORPH, duration, 64, color) for color in RAINBOW
        ]))

    def rainbow_wave(self, duration: int = 500) -> None:
        n = len(RAINBOW)
        self._write(self._per_zone(lambda i: [
            (_elc.ACTION_MORPH, duration, 64, RAINBOW[(i + j) % n]) for j in range(n)
        ]))

    def wave(self, rgb: int) -> None:
        n = len(self.zones)
        self._write(self._per_zone(lambda i: [
            (_elc.ACTION_MORPH, 500, 64, rgb if i == j else 0) for j in range(n)
        ]))

    def back_and_forth(self, rgb: int) -> None:
        n = len(self.zones)
        if n <= 1:
            return self.static(rgb)
        sequence = list(range(n)) + list(range(n - 2, 0, -1))
        self._write(self._per_zone(lambda i: [
            (_elc.ACTION_MORPH, 500, 64, rgb if i == step else 0) for step in sequence
        ]))

    def quantum(self, duration: int = 3000) -> None:
        """Cryo signature: slow cyan <-> violet morph across the chassis."""
        self._write(self._per_zone(lambda i: [
            (_elc.ACTION_MORPH, duration, 64, QUANTUM_CYAN),
            (_elc.ACTION_MORPH, duration, 64, QUANTUM_VIOLET),
        ]))

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
