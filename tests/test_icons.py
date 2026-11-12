"""The GUI icon set: tintable white-on-transparent SVGs that Qt's Tiny 1.2 renderer can draw."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ICON_DIR = Path(__file__).resolve().parent.parent / "src" / "cryo" / "gui" / "assets" / "icons"
SVG_NS = "{http://www.w3.org/2000/svg}"

EXPECTED = {
    "mode-cool", "mode-quiet", "mode-balanced", "mode-performance", "mode-gmode",
    "mode-custom", "mode-low-power",
    "settings", "back", "close", "check", "info", "external-link", "play",
    "sound-on", "sound-off", "guard", "gaming", "plug", "battery", "snowflake",
    "flame", "palette", "motion", "voice",
}
ALLOWED_TAGS = {"svg", "g", "path", "line", "polyline", "polygon", "circle", "rect"}
ALLOWED_PAINT = {"#FFFFFF", "#ffffff", "white", "none"}

ICONS = sorted(ICON_DIR.glob("*.svg"))


def _local(tag: str) -> str:
    return tag[len(SVG_NS):] if tag.startswith(SVG_NS) else tag


def test_expected_set_present():
    names = {p.stem for p in ICONS}
    missing = EXPECTED - names
    assert not missing, f"missing icons: {sorted(missing)}"


@pytest.mark.parametrize("path", ICONS, ids=lambda p: p.stem)
def test_svg_is_tiny_and_tintable(path: Path):
    root = ET.parse(path).getroot()
    assert _local(root.tag) == "svg"
    assert root.get("viewBox") == "0 0 24 24"
    for el in root.iter():
        name = _local(el.tag)
        assert name in ALLOWED_TAGS, f"{path.name}: <{name}> not allowed"
        assert "style" not in el.attrib, f"{path.name}: style attribute on <{name}>"
        assert "class" not in el.attrib, f"{path.name}: class attribute on <{name}>"
        for attr in ("fill", "stroke"):
            value = el.get(attr)
            if value is not None:
                assert value in ALLOWED_PAINT, f"{path.name}: {attr}={value!r} on <{name}>"


@pytest.mark.parametrize("path", ICONS, ids=lambda p: p.stem)
def test_qt_renderer_accepts(path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qtsvg = pytest.importorskip("PySide6.QtSvg")
    assert qtsvg.QSvgRenderer(str(path)).isValid(), path.name
