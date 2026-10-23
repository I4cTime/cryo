"""ELC chassis effects: zone list and packet sequence, no hardware."""

from cryo.hw import effects as fx
from cryo.hw import elc


class FakeElc:
    def __init__(self):
        self.sent: list[bytes] = []
        self.claimed = False

    def acquire(self):
        self.claimed = True

    def release(self):
        self.claimed = False

    def _send(self, payload):
        self.sent.append(bytes(payload).ljust(elc.PACKET_SIZE, b"\x00"))

    animation = elc.Elc.animation
    zone_select = elc.Elc.zone_select
    add_action = elc.Elc.add_action
    set_dim = elc.Elc.set_dim


def test_chassis_zones_are_rings_lid_button_without_poison_ids():
    assert fx.CHASSIS_ZONES == [0, 1, 2, 4]
    assert 3 not in fx.CHASSIS_ZONES and 5 not in fx.CHASSIS_ZONES


def test_static_blanks_power_slots_then_programs_user_animation():
    dev = FakeElc()
    fx.Effects(elc_factory=lambda: dev).static(0x00D1FF)
    ops = [(p[1], p[2:4], p[4:6]) for p in dev.sent]
    # six power slots, each: remove, start, zone select, action, save, default
    power = [p for p in dev.sent if p[1] == elc.OP_POWER_ANIMATION]
    assert len(power) == 6 * 4
    assert power[0][2:6] == b"\x00\x04\x00\x5b"  # remove slot 0x5b
    slot_zone = dev.sent[2]
    assert slot_zone[1] == elc.OP_ZONE_SELECT and slot_zone[5] == 0x04  # only the button
    assert dev.sent[3][7:10] == b"\x00\x00\x00"  # black
    # then the user animation on every chassis zone, one select per zone
    user = [p for p in dev.sent if p[1] == elc.OP_ANIMATION]
    assert [p[2:6] for p in user] == [b"\x00\x04\x00\x61", b"\x00\x01\x00\x61", b"\x00\x02\x00\x61", b"\x00\x06\x00\x61"]
    selects = [p[5] for p in dev.sent if p[1] == elc.OP_ZONE_SELECT]
    assert selects == [4] * 6 + [0, 1, 2, 4]
    colours = [p[7:10] for p in dev.sent if p[1] == elc.OP_ADD_ACTION]
    assert colours[6:] == [b"\x00\xd1\xff"] * 4
    assert not dev.claimed


def test_brightness_dims_every_chassis_zone():
    dev = FakeElc()
    fx.Effects(elc_factory=lambda: dev).brightness(40)
    (dim,) = dev.sent
    assert dim[1] == elc.OP_SET_DIM and dim[2] == 60
    assert dim[3:5] == b"\x00\x04" and list(dim[5:9]) == [0, 1, 2, 4]
