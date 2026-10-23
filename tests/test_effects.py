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


def test_static_rings_lid_in_user_animation_button_in_active_slots():
    dev = FakeElc()
    fx.Effects(elc_factory=lambda: dev).static(0x00D1FF)
    slots = program(dev)
    assert sorted(slots) == sorted([fx.ANIM_USER, *elc.POWER_SLOTS])
    zones = lambda pkts: [p[5] for p in pkts if p[1] == elc.OP_ZONE_SELECT]
    colours = lambda pkts: {p[7:10] for p in pkts if p[1] == elc.OP_ADD_ACTION}
    assert zones(slots[fx.ANIM_USER]) == [0, 1, 2]  # never the button
    assert colours(slots[fx.ANIM_USER]) == {b"\x00\xd1\xff"}
    for slot in elc.POWER_SLOTS:
        assert zones(slots[slot]) == [4]  # never the rings or lid
        assert colours(slots[slot]) == ({b"\x00\xd1\xff"} if slot in fx.ACTIVE_SLOTS else {b"\x00\x00\x00"})
    user_pkts = [p for p in dev.sent if p[1] == elc.OP_ANIMATION]
    assert [p[2:6] for p in user_pkts] == [b"\x00\x04\x00\x61", b"\x00\x01\x00\x61", b"\x00\x02\x00\x61", b"\x00\x06\x00\x61"]
    assert dev.sent[-1][1:6] == b"\x22\x00\x06\x00\x60"  # last: set default on 0x60
    assert not dev.claimed


def test_quantum_morphs_every_zone():
    dev = FakeElc()
    fx.Effects(elc_factory=lambda: dev).quantum()
    slots = program(dev)
    user = [p for p in slots[fx.ANIM_USER] if p[1] == elc.OP_ADD_ACTION]
    assert len(user) == 6  # 2 morph steps x 3 zones
    assert user[0][2] == elc.ACTION_MORPH and user[0][7:10] == b"\x00\xd1\xff"
    assert user[1][7:10] == b"\x7b\x2d\xff"
    button = [p for p in slots[0x5F] if p[1] == elc.OP_ADD_ACTION]
    assert [p[7:10] for p in button] == [b"\x00\xd1\xff", b"\x7b\x2d\xff"]


def test_wave_steps_rings_lid_button_in_order():
    dev = FakeElc()
    fx.Effects(elc_factory=lambda: dev).wave(0xFF0000)
    lit = []
    for key in (fx.ANIM_USER, 0x5C):
        zone = None
        for p in program(dev)[key]:
            if p[1] == elc.OP_ZONE_SELECT:
                zone = p[5]
            elif p[1] == elc.OP_ADD_ACTION:
                lit.append((zone, p[7:10] == b"\xff\x00\x00"))
    # zone i lit exactly at step i: rings, lid, then the button on step 4
    assert [z for z, on in lit if on] == [0, 1, 2, 4]
    assert [z for z, _ in lit].count(4) == 4  # the button has all four steps


def test_brightness_dims_every_chassis_zone():
    dev = FakeElc()
    fx.Effects(elc_factory=lambda: dev).brightness(40)
    (dim,) = dev.sent
    assert dim[1] == elc.OP_SET_DIM and dim[2] == 60
    assert dim[3:5] == b"\x00\x04" and list(dim[5:9]) == [0, 1, 2, 4]
