"""AlienFX ELC (Embedded Lighting Controller) USB protocol.

Protocol ported from tr1xem/AWCC (GPL-3.0) and the AlienFX SDK notes.
Device: 187c:0551 (AW-ELC) on the m18 R2. All packets are 33 bytes,
sent via HID SET_REPORT control transfers.
"""

from __future__ import annotations

import usb.core
import usb.util

VENDOR_ID = 0x187C
PRODUCT_IDS = (0x0550, 0x0551)

PACKET_SIZE = 33
PREAMBLE = 0x03

# opcodes
OP_REQUEST = 0x20
OP_ANIMATION = 0x21
OP_ZONE_SELECT = 0x23
OP_ADD_ACTION = 0x24
OP_SET_DIM = 0x26

# animation subcodes (u16)
ANIM_CONFIG_START = 0x0001
ANIM_CONFIG_SAVE = 0x0002
ANIM_CONFIG_PLAY = 0x0003
ANIM_REMOVE = 0x0004
ANIM_PLAY = 0x0005
ANIM_SET_DEFAULT = 0x0006
ANIM_SET_STARTUP = 0x0007

# actions
ACTION_COLOR = 0x00
ACTION_PULSE = 0x01
ACTION_MORPH = 0x02


class ElcNotFound(RuntimeError):
    pass


class Elc:
    """Low-level packet interface to the lighting controller."""

    def __init__(self) -> None:
        self.dev = None
        for pid in PRODUCT_IDS:
            self.dev = usb.core.find(idVendor=VENDOR_ID, idProduct=pid)
            if self.dev is not None:
                break
        if self.dev is None:
            raise ElcNotFound("AlienFX ELC (187c:0550/0551) not found on USB")
        self._claimed = False

    def acquire(self) -> None:
        if self._claimed:
            return
        if self.dev.is_kernel_driver_active(0):
            self.dev.detach_kernel_driver(0)
        usb.util.claim_interface(self.dev, 0)
        self._claimed = True

    def release(self) -> None:
        if not self._claimed:
            return
        usb.util.release_interface(self.dev, 0)
        try:
            self.dev.attach_kernel_driver(0)
        except usb.core.USBError:
            pass
        self._claimed = False

    def _send(self, payload: bytes) -> None:
        buf = payload.ljust(PACKET_SIZE, b"\x00")
        written = self.dev.ctrl_transfer(0x21, 9, 0x0202, 0, buf, timeout=1000)
        if written != PACKET_SIZE:
            raise IOError(f"short ELC write: {written}/{PACKET_SIZE}")

    def _recv(self) -> bytes:
        return bytes(self.dev.ctrl_transfer(0xA1, 1, 0x0101, 0, PACKET_SIZE, timeout=1000))

    # -- protocol ops ------------------------------------------------------

    def animation(self, subcode: int, animation_id: int) -> None:
        self._send(
            bytes(
                [
                    PREAMBLE,
                    OP_ANIMATION,
                    (subcode >> 8) & 0xFF,
                    subcode & 0xFF,
                    (animation_id >> 8) & 0xFF,
                    animation_id & 0xFF,
                ]
            )
        )

    def zone_select(self, loop: int, zones: list[int]) -> None:
        self._send(
            bytes([PREAMBLE, OP_ZONE_SELECT, loop, (len(zones) >> 8) & 0xFF, len(zones) & 0xFF])
            + bytes(zones)
        )

    def add_action(self, action: int, duration: int, tempo: int, rgb: int) -> None:
        self._send(
            bytes(
                [
                    PREAMBLE,
                    OP_ADD_ACTION,
                    action & 0xFF,
                    (duration >> 8) & 0xFF,
                    duration & 0xFF,
                    (tempo >> 8) & 0xFF,
                    tempo & 0xFF,
                    (rgb >> 16) & 0xFF,
                    (rgb >> 8) & 0xFF,
                    rgb & 0xFF,
                ]
            )
        )

    def set_dim(self, dim: int, zones: list[int]) -> None:
        """dim is 0-100 where 100 = fully dimmed (off)."""
        self._send(
            bytes([PREAMBLE, OP_SET_DIM, dim & 0xFF, (len(zones) >> 8) & 0xFF, len(zones) & 0xFF])
            + bytes(zones)
        )
