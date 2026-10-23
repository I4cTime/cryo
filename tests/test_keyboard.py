"""Darfon per-key keyboard (API V5) packets and sequencing — no hardware."""

import pytest

from cryo.hw import keyboard as kb


class FakeTransport:
    def __init__(self, length=64, fail_first=False):
        self.length = length
        self.sent: list[bytes] = []
        self.closed = False
        self.fail_first = fail_first

    def send(self, buf):
        if self.fail_first:
            self.fail_first = False
            raise OSError("EPIPE")
        assert len(buf) == self.length
        self.sent.append(bytes(buf))

    def recv(self):
        return bytes([kb.REPORT_ID, 0, 0x21]) + bytes(self.length - 3)

    def close(self):
        self.closed = True


def test_packet_is_report_length_and_starts_with_cc():
    p = kb.packet(kb.CMD_RESET)
    assert len(p) == 64 and p[:2] == b"\xcc\x94" and not any(p[2:])


def test_packet_rejects_overflow():
    with pytest.raises(ValueError):
        kb.packet(kb.CMD_COLOR_SET, bytes(70))


def test_color_block_uses_wire_id_index_plus_one():
    (p,) = kb.color_packets({0: 0xFF0000, 1: 0x00FF00})
    assert p[:4] == b"\xcc\x8c\x02\x00"
    assert p[4:12] == bytes([0x01, 0xFF, 0, 0, 0x02, 0, 0xFF, 0])
    assert not any(p[12:])


def test_full_keyboard_is_ten_packets_of_fifteen_blocks():
    pkts = kb.color_packets({i: 0x123456 for i in range(kb.KEY_COUNT)})
    assert len(pkts) == 10  # 136 blocks / 15 per packet
    assert pkts[0][60:64] == bytes([15, 0x12, 0x34, 0x56])  # 15th block fills the packet
    assert pkts[-1][4] == 136 and not any(pkts[-1][8:])  # last packet: one block, padded
    # the upstream 65-byte bug: no block ever straddles the packet end
    for p in pkts:
        assert len(p) == 64


def test_shorter_report_holds_fewer_blocks():
    pkts = kb.color_packets({i: 0 for i in range(20)}, length=32)
    assert kb.blocks_per_packet(32) == 7
    assert len(pkts) == 3


def test_brightness_scales_percent_to_byte():
    assert kb.brightness_packet(100)[:5] == b"\xcc\x83\x38\x9c\xff"
    assert kb.brightness_packet(0)[4] == 0
    assert kb.brightness_packet(60)[4] == 153
    assert kb.brightness_packet(250)[4] == 255  # clamped


def test_keyboard_color_for_effects():
    assert kb.keyboard_color("off", 0xFF0000) == 0
    assert kb.keyboard_color("quantum", 0xFF0000) == 0x00D1FF
    assert kb.keyboard_color("static", 0xFF0000) == 0xFF0000
    assert kb.keyboard_color("breathe", 0x7B2DFF) == 0x7B2DFF


def test_set_color_sequence_reset_status_blocks_loop_update():
    t = FakeTransport()
    k = kb.Keyboard(transport_factory=lambda: t)
    k.set_color(0x00D1FF)
    ops = [p[1:4] for p in t.sent]
    assert ops[0] == b"\x94\x00\x00" and ops[1] == b"\x93\x00\x00"
    assert ops[2:12] == [b"\x8c\x02\x00"] * 10
    assert ops[12] == b"\x8c\x13\x00" and ops[13] == b"\x8b\x01\xff"
    assert len(t.sent) == 14


def test_brightness_sequence():
    t = FakeTransport()
    k = kb.Keyboard(transport_factory=lambda: t)
    k.brightness(50)
    assert [p[1] for p in t.sent] == [0x94, 0x93, 0x83]
    assert t.sent[-1][4] == 128


def test_apply_sets_brightness_then_colour():
    t = FakeTransport()
    k = kb.Keyboard(transport_factory=lambda: t)
    k.apply("quantum", 0xFF0000, 40)
    assert t.sent[2][1] == 0x83  # brightness first
    assert t.sent[-1][1:4] == b"\x8b\x01\xff"  # colour update last
    assert t.sent[5][5:8] == b"\x00\xd1\xff"  # quantum cyan on the keys


def test_write_error_reopens_once():
    first = FakeTransport(fail_first=True)
    second = FakeTransport()
    handles = iter([first, second])
    k = kb.Keyboard(transport_factory=lambda: next(handles))
    k.off()
    assert first.closed and len(second.sent) == 14
    assert all(b == 0 for b in second.sent[2][5:8])


def test_feature_report_size_from_descriptor():
    # Report ID 0xCC, Report Size 8, Report Count 63, Feature; then an
    # unrelated input report that must not be counted.
    desc = bytes([0x85, 0xCC, 0x75, 0x08, 0x95, 0x3F, 0xB1, 0x02,
                  0x85, 0x01, 0x75, 0x08, 0x95, 0x10, 0x81, 0x02])
    assert kb._feature_report_bytes(desc, 0xCC) == 63
    assert kb._feature_report_bytes(desc, 0x5A) is None


def test_find_keyboard_matches_darfon_with_cc_report(tmp_path):
    def node(name, hid_id, desc):
        d = tmp_path / name / "device"
        d.mkdir(parents=True)
        (d / "uevent").write_text(f"DRIVER=hid-generic\nHID_ID={hid_id}\nHID_NAME=x\n")
        (d / "report_descriptor").write_bytes(desc)

    cc = bytes([0x85, 0xCC, 0x75, 0x08, 0x95, 0x3F, 0xB1, 0x02])
    node("hidraw0", "0003:0000187C:00000551", cc)       # ELC, wrong vendor
    node("hidraw1", "0003:00000D62:0000AAB1", b"\x85\x01\x75\x08\x95\x08\x81\x02")  # darfon, no 0xCC
    node("hidraw2", "0003:00000D62:0000AAB1", cc)
    assert kb.find_keyboard(tmp_path) == (kb.Path("/dev/hidraw2"), 64)


def test_find_keyboard_none_when_absent(tmp_path):
    assert kb.find_keyboard(tmp_path) is None
