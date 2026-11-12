"""The cryoicon image provider: every icon renders tinted at the requested
size; an unknown name gives a transparent image and exactly one warning."""

from __future__ import annotations

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # before any Qt application exists

from conftest import require_qt  # noqa: E402

QtGui = require_qt("PySide6.QtGui")
require_qt("PySide6.QtSvg")
require_qt("PySide6.QtQuick")

from PySide6.QtCore import QSize, QtMsgType, qInstallMessageHandler  # noqa: E402

from cryo.gui.icons import ICON_DIR, IconProvider, icon_names, parse_request  # noqa: E402

NAMES = icon_names()


@pytest.fixture
def provider(qapp):
    if not isinstance(qapp, QtGui.QGuiApplication):
        pytest.skip("QtGui is not usable on this runner")
    return IconProvider()


def _opaque_pixels(image):
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            if c.alpha() > 0:
                yield c


def test_the_set_is_there():
    assert len(NAMES) >= 25
    assert {"settings", "back", "guard", "gaming", "plug", "battery"} <= set(NAMES)
    assert all(n.startswith("mode-") for n in NAMES if "mode" in n)
    assert all((ICON_DIR / f"{n}.svg").is_file() for n in NAMES)


def test_parse_request():
    name, color = parse_request("mode-cool?color=00D1FF")
    assert name == "mode-cool" and color.name().upper() == "#00D1FF"
    name, color = parse_request("guard?color=80FF5470")       # QML's #AARRGGBB order
    assert name == "guard" and color.alpha() == 0x80 and color.name().upper() == "#FF5470"
    name, color = parse_request("check")
    assert name == "check" and color.name().upper() == "#FFFFFF"
    name, color = parse_request("check?color=nonsense")
    assert color.name().upper() == "#FFFFFF"


@pytest.mark.parametrize("name", NAMES)
def test_every_icon_renders_tinted(provider, name):
    size = QSize()
    image = provider.requestImage(f"{name}?color=FF5470", size, QSize(30, 30))
    assert (image.width(), image.height()) == (30, 30)
    assert (size.width(), size.height()) == (30, 30)
    inked = list(_opaque_pixels(image))
    assert len(inked) > 20, f"{name}: almost nothing drawn"
    # every drawn pixel carries the tint (anti-aliased edges vary only in alpha)
    solid = [c for c in inked if c.alpha() == 255]
    assert solid, name
    assert all((c.red(), c.green(), c.blue()) == (0xFF, 0x54, 0x70) for c in solid)


def test_requested_size_is_honoured(provider):
    small = provider.requestImage("settings?color=FFFFFF", None, QSize(16, 16))
    big = provider.requestImage("settings?color=FFFFFF", None, QSize(48, 48))
    default = provider.requestImage("settings", None, QSize(-1, -1))
    assert small.width() == 16 and big.width() == 48 and default.width() == 24


def test_unknown_icon_is_transparent_with_one_warning(provider):
    warnings: list[str] = []

    def handler(mode, context, message):
        if mode == QtMsgType.QtWarningMsg:
            warnings.append(message)

    previous = qInstallMessageHandler(handler)
    try:
        first = provider.requestImage("no-such-icon?color=FFFFFF", None, QSize(20, 20))
        second = provider.requestImage("no-such-icon?color=00D1FF", None, QSize(20, 20))
    finally:
        qInstallMessageHandler(previous)
    for image in (first, second):
        assert (image.width(), image.height()) == (20, 20)
        assert not any(True for _ in _opaque_pixels(image))
    assert len(warnings) == 1 and "no-such-icon" in warnings[0]
