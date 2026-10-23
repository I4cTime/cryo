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


def program(dev):
    """Group packets per animation slot: {slot: [packets]}."""
    slots, current = {}, None
    for p in dev.sent:
        if p[1] in (elc.OP_ANIMATION, elc.OP_POWER_ANIMATION) and p[2:4] == b"\x00\x01":
            current = p[5]
            slots[current] = []
        elif current is not None and p[1] in (elc.OP_ZONE_SELECT, elc.OP_ADD_ACTION):
            slots[current].append(p)
    return slots


def test_chassis_zones_are_rings_lid_button_without_poison_ids():
    assert fx.CHASSIS_ZONES == [0, 1, 2, 4]
    assert 3 not in fx.CHASSIS_ZONES and 5 not in fx.CHASSIS_ZONES


def test_static_retires_user_animation_and_fills_every_power_slot():
    dev = FakeElc()
    fx.Effects(elc_factory=lambda: dev).static(0x00D1FF)
    first = dev.sent[0]
    assert first[1] == elc.OP_ANIMATION and first[2:6] == b"\x00\x04\x00\x61"  # remove user anim
    assert all(p[1] != elc.OP_ANIMATION for p in dev.sent[1:])  # nothing else in that family
    slots = program(dev)
    assert sorted(slots) == list(elc.POWER_SLOTS)
    for slot, pkts in slots.items():
        zones = [p[5] for p in pkts if p[1] == elc.OP_ZONE_SELECT]
        colours = {p[7:10] for p in pkts if p[1] == elc.OP_ADD_ACTION}
        assert zones == [0, 1, 2, 4]
        assert colours == ({b"\x00\xd1\xff"} if slot in fx.ACTIVE_SLOTS else {b"\x00\x00\x00"})
    # each slot: remove, start, (select + action) x4, save, default
    per_slot = [p for p in dev.sent if p[1] == elc.OP_POWER_ANIMATION]
    assert len(per_slot) == 6 * 4
    assert per_slot[-1][2:6] == b"\x00\x06\x00\x60"  # last: set default on 0x60
    assert not dev.claimed


def test_quantum_morphs_every_zone_in_active_slots():
    dev = FakeElc()
    fx.Effects(elc_factory=lambda: dev).quantum()
    pkts = program(dev)[0x5C]
    actions = [p for p in pkts if p[1] == elc.OP_ADD_ACTION]
    assert len(actions) == 8  # 2 morph steps x 4 zones
    assert actions[0][2] == elc.ACTION_MORPH and actions[0][7:10] == b"\x00\xd1\xff"
    assert actions[1][7:10] == b"\x7b\x2d\xff"


def test_wave_steps_rings_lid_button_in_order():
    dev = FakeElc()
    fx.Effects(elc_factory=lambda: dev).wave(0xFF0000)
    pkts = program(dev)[0x5F]
    lit = []
    zone = None
    for p in pkts:
        if p[1] == elc.OP_ZONE_SELECT:
            zone = p[5]
        elif p[7:10] == b"\xff\x00\x00":
            lit.append(zone)
    assert lit == [0, 1, 2, 4]


def test_brightness_dims_every_chassis_zone():
    dev = FakeElc()
    fx.Effects(elc_factory=lambda: dev).brightness(40)
    (dim,) = dev.sent
    assert dim[1] == elc.OP_SET_DIM and dim[2] == 60
    assert dim[3:5] == b"\x00\x04" and list(dim[5:9]) == [0, 1, 2, 4]
