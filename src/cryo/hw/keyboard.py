"""Per-key RGB keyboard backlight on Darfon "DELL Technologies Keyboard" USB
keyboards (0d62:aab1 on the Alienware m18 R2; bab0/bab1 on the R1 and
Cherry MX variants).

On these machines the keyboard is NOT on the AW-ELC lighting controller
(187c:0551 drives the lid logo, exhaust lights and power button only, see
effects.py). The keyboard speaks what alienfx-tools calls "API V5": one
HID feature report (ID 0xCC, 64 bytes on the m18 R2) per command, sent
over hidraw. Protocol per T-Troll/alienfx-tools AlienFX_SDK.cpp and the
packet captures in tr1xem/alienfx-linux#2.

Packet layout (all REPORT_LEN bytes, zero padded, byte 0 = 0xCC):
  reset       cc 94
  status      cc 93              then GET_FEATURE; byte 2 is the status
  colour set  cc 8c 02 00  then 4-byte blocks [wire id, r, g, b] from
                           byte 4; at most 15 blocks per packet
  loop        cc 8c 13            commit the colour blocks
  update      cc 8b 01 ff         show them
  brightness  cc 83 38 9c BB      BB = 0..255, global
  effect      cc 80 TT SS 00 00 01 01 01 NN r g b r g b
                                  the keyboard's own effect engine: TT =
                                  type (2 breathe, 3 wave, 4 two-colour
                                  wave, 8 pulse, 9 two-colour pulse, 0xa
                                  night rider, 0xb laser; 1 = back to
                                  plain colours), SS = tempo, NN = colour
                                  count - 1 (alienfx-tools' comments;
                                  tempo scale not documented)

wire id = light index + 1. Sending exactly REPORT_LEN bytes matters: a
65-byte packet lets a 16th block spill past the end and every 16th key
keeps its old colour (that was the "five keys stay blue" bug upstream).
"""

from __future__ import annotations

import fcntl
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

VENDOR_ID = 0x0D62
REPORT_ID = 0xCC
DEFAULT_REPORT_LEN = 64
BLOCK_BYTES = 4
BLOCKS_START = 4
# Light indices 0..135 (wire ids 0x01..0x88): the whole 20x8 grid of the
# m18 R2 map, including the unnamed LEDs, as the upstream captures do.
KEY_COUNT = 136

CMD_RESET = bytes([0x94])
CMD_STATUS = bytes([0x93])
CMD_COLOR_SET = bytes([0x8C, 0x02, 0x00])
CMD_LOOP = bytes([0x8C, 0x13])
CMD_UPDATE = bytes([0x8B, 0x01, 0xFF])
CMD_BRIGHTNESS = bytes([0x83, 0x38, 0x9C])
CMD_EFFECT = bytes([0x80])
EFFECT_TAIL = bytes([0x00, 0x00, 0x01, 0x01, 0x01])
EFFECT_OFF = 0x01
EFFECT_BREATHE = 0x02
EFFECT_WAVE = 0x03
EFFECT_WAVE2 = 0x04
EFFECT_PULSE = 0x08
EFFECT_PULSE2 = 0x09
EFFECT_RIDER = 0x0A
DEFAULT_TEMPO = 0x07

HIDRAW_CLASS = Path("/sys/class/hidraw")


class KeyboardNotFound(RuntimeError):
    pass


# -- packet builders (pure; unit tested) ------------------------------------


def packet(cmd: bytes, payload: bytes = b"", length: int = DEFAULT_REPORT_LEN) -> bytes:
    buf = bytes([REPORT_ID]) + cmd + payload
    if len(buf) > length:
        raise ValueError(f"packet of {len(buf)} bytes exceeds report length {length}")
    return buf.ljust(length, b"\x00")


def blocks_per_packet(length: int = DEFAULT_REPORT_LEN) -> int:
    return (length - BLOCKS_START) // BLOCK_BYTES


def color_packets(colors: dict[int, int], length: int = DEFAULT_REPORT_LEN) -> list[bytes]:
    """Colour-set packets for {light index: 0xRRGGBB}, in index order."""
    per = blocks_per_packet(length)
    items = sorted(colors.items())
    out = []
    for start in range(0, len(items), per):
        payload = bytearray()
        for index, rgb in items[start : start + per]:
            if not 0 <= index < 0xFF:
                raise ValueError(f"light index {index} out of range")
            payload += bytes([index + 1, (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF])
        out.append(packet(CMD_COLOR_SET, bytes(payload), length))
    return out


def brightness_packet(percent: int, length: int = DEFAULT_REPORT_LEN) -> bytes:
    percent = max(0, min(100, int(percent)))
    return packet(CMD_BRIGHTNESS, bytes([round(percent * 255 / 100)]), length)


def effect_packet(kind: int, colors: list[int], tempo: int = DEFAULT_TEMPO,
                  length: int = DEFAULT_REPORT_LEN) -> bytes:
    """Engage one of the keyboard's built-in effects with one or two colours."""
    if not 1 <= len(colors) <= 2:
        raise ValueError("effects take one or two colours")
    rgb = b"".join(bytes([(c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF]) for c in colors)
    return packet(CMD_EFFECT, bytes([kind & 0xFF, tempo & 0xFF]) + EFFECT_TAIL
                  + bytes([len(colors) - 1]) + rgb, length)


def keyboard_plan(effect: str, color: int) -> tuple[int | None, list[int]]:
    """(built-in effect type or None for a solid colour, colours) that
    mirrors a chassis effect on the keyboard."""
    from cryo.hw.effects import QUANTUM_CYAN, QUANTUM_VIOLET

    color &= 0xFFFFFF
    match effect:
        case "off":
            return None, [0x000000]
        case "static":
            return None, [color]
        case "quantum":
            return EFFECT_PULSE2, [QUANTUM_CYAN, QUANTUM_VIOLET]
        case "breathe":
            return EFFECT_BREATHE, [color]
        case "spectrum":
            return EFFECT_WAVE2, [0xFF0000, 0x0000FF]
        case "rainbow":
            return EFFECT_WAVE2, [color, 0xFFFFFF ^ color]
        case "wave":
            return EFFECT_WAVE, [color]
        case "backforth":
            return EFFECT_RIDER, [color]
        case _:
            return None, [color]


def keyboard_color(effect: str, color: int) -> int:
    """The solid colour the keyboard shows for a chassis effect."""
    return keyboard_plan(effect, color)[1][0]


# -- device discovery -------------------------------------------------------


def _feature_report_bytes(descriptor: bytes, report_id: int) -> int | None:
    """Size in bytes (excluding the ID) of a feature report, from a HID
    report descriptor. Minimal item walk: enough for these keyboards."""
    i = 0
    rid = None
    rsize = rcount = 0
    total = 0
    seen = False
    while i < len(descriptor):
        prefix = descriptor[i]
        i += 1
        if prefix == 0xFE:  # long item
            n = descriptor[i]
            i += 2 + n
            continue
        size = (0, 1, 2, 4)[prefix & 3]
        kind, tag = (prefix >> 2) & 3, prefix >> 4
        value = int.from_bytes(descriptor[i : i + size], "little")
        i += size
        if kind == 1 and tag == 7:
            rsize = value
        elif kind == 1 and tag == 9:
            rcount = value
        elif kind == 1 and tag == 8:
            rid = value
        elif kind == 0 and tag == 11 and rid == report_id:  # Feature
            total += rsize * rcount
            seen = True
    return total // 8 if seen else None


def find_keyboard(hidraw_class: Path = HIDRAW_CLASS) -> tuple[Path, int] | None:
    """(/dev/hidrawN, report length) of the first Darfon keyboard exposing
    the 0xCC feature report, or None."""
    for node in sorted(hidraw_class.glob("hidraw*")):
        try:
            uevent = (node / "device" / "uevent").read_text()
        except OSError:
            continue
        hid_id = next((l.split("=", 1)[1] for l in uevent.splitlines() if l.startswith("HID_ID=")), "")
        parts = hid_id.split(":")
        if len(parts) != 3 or int(parts[1], 16) != VENDOR_ID:
            continue
        try:
            descriptor = (node / "device" / "report_descriptor").read_bytes()
        except OSError:
            continue
        size = _feature_report_bytes(descriptor, REPORT_ID)
        if size is None:
            continue
        return Path("/dev") / node.name, size + 1
    return None


# -- transport --------------------------------------------------------------


def _ioc(direction: int, type_char: str, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(type_char) << 8) | nr


def hidiocsfeature(length: int) -> int:
    return _ioc(3, "H", 0x06, length)  # _IOC_READ | _IOC_WRITE


def hidiocgfeature(length: int) -> int:
    return _ioc(3, "H", 0x07, length)


class HidrawTransport:
    def __init__(self, path: Path, length: int) -> None:
        self.path = path
        self.length = length
        self.fd = os.open(path, os.O_RDWR)

    def send(self, buf: bytes) -> None:
        if len(buf) != self.length:
            raise ValueError(f"expected {self.length}-byte report, got {len(buf)}")
        fcntl.ioctl(self.fd, hidiocsfeature(self.length), buf)

    def recv(self) -> bytes:
        buf = bytearray(self.length)
        buf[0] = REPORT_ID
        fcntl.ioctl(self.fd, hidiocgfeature(self.length), buf)
        return bytes(buf)

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


# -- high level -------------------------------------------------------------


class Keyboard:
    """Solid-colour and brightness control of the per-key keyboard."""

    def __init__(self, transport_factory=None) -> None:
        self._factory = transport_factory or self._open
        self._transport: HidrawTransport | None = None
        self.length = DEFAULT_REPORT_LEN

    @staticmethod
    def _open() -> HidrawTransport:
        found = find_keyboard()
        if found is None:
            raise KeyboardNotFound("Darfon per-key keyboard (0d62, report 0xCC) not found")
        path, length = found
        return HidrawTransport(path, length)

    def available(self) -> bool:
        return find_keyboard() is not None

    def reset(self) -> None:
        """Drop the handle; the next call reopens (after resume the hidraw
        node can be a new one)."""
        if self._transport is not None:
            self._transport.close()
        self._transport = None

    def _device(self) -> HidrawTransport:
        if self._transport is None:
            self._transport = self._factory()
            self.length = self._transport.length
        return self._transport

    def _retrying(self, fn):
        try:
            return fn()
        except OSError as exc:
            log.warning("keyboard write failed (%s); reopening", exc)
            self.reset()
            return fn()

    def _begin(self, dev: HidrawTransport) -> None:
        dev.send(packet(CMD_RESET, length=dev.length))
        dev.send(packet(CMD_STATUS, length=dev.length))
        try:
            dev.recv()
        except OSError:
            pass  # status is informational; upstream never waits on it

    def set_colors(self, colors: dict[int, int]) -> None:
        def op() -> None:
            dev = self._device()
            self._begin(dev)
            # leave any built-in effect first, else the colours never show
            dev.send(packet(CMD_EFFECT, bytes([EFFECT_OFF, 0xFE]), dev.length))
            dev.send(packet(CMD_UPDATE, length=dev.length))
            self._begin(dev)
            for pkt in color_packets(colors, dev.length):
                dev.send(pkt)
            dev.send(packet(CMD_LOOP, length=dev.length))
            dev.send(packet(CMD_UPDATE, length=dev.length))

        self._retrying(op)

    def set_color(self, rgb: int) -> None:
        self.set_colors({i: rgb for i in range(KEY_COUNT)})

    def brightness(self, percent: int) -> None:
        def op() -> None:
            dev = self._device()
            self._begin(dev)
            dev.send(brightness_packet(percent, dev.length))

        self._retrying(op)

    def effect(self, kind: int, colors: list[int], tempo: int = DEFAULT_TEMPO) -> None:
        def op() -> None:
            dev = self._device()
            self._begin(dev)
            dev.send(effect_packet(kind, colors, tempo, dev.length))
            dev.send(packet(CMD_UPDATE, length=dev.length))

        self._retrying(op)

    def off(self) -> None:
        self.set_color(0x000000)

    def apply(self, effect: str, color: int, brightness: int | None = None) -> None:
        """Mirror a chassis lighting effect on the keyboard."""
        if brightness is not None:
            self.brightness(brightness)
        kind, colors = keyboard_plan(effect, color)
        if kind is None:
            self.set_color(colors[0])
        else:
            self.effect(kind, colors)
