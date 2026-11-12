"""Tinted SVG icons for QML: ``image://cryoicon/<name>?color=RRGGBB``.

The icon set (src/cryo/gui/assets/icons) is white on transparent. This
provider renders an icon with QSvgRenderer at exactly the requested
sourceSize (Icon.qml asks for device pixels, so icons stay crisp at
fractional scale factors) and tints it with a SourceIn fill. Plain QPainter
work, no shaders, so it draws the same on the software renderer.

An unknown name yields a transparent image and one Qt warning per name
(the GUI smoke test fails on Qt warnings, so a typo cannot slip through).
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, qWarning
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQml import QQmlImageProviderBase
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).parent / "assets" / "icons"
PROVIDER_ID = "cryoicon"
DEFAULT_SIZE = 24
MAX_SIZE = 1024
_HEX = re.compile(r"^[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")


def icon_names() -> list[str]:
    return sorted(p.stem for p in ICON_DIR.glob("*.svg"))


def parse_request(request_id: str) -> tuple[str, QColor]:
    """``mode-cool?color=00D1FF`` -> ("mode-cool", QColor). Colour is
    RRGGBB or AARRGGBB (QML's colour.toString() order); default white."""
    name, _, query = request_id.partition("?")
    color = QColor(255, 255, 255)
    for part in query.split("&"):
        key, _, value = part.partition("=")
        if key == "color" and _HEX.match(value):
            color = QColor("#" + value)
    return name.strip("/"), color


class IconProvider(QQuickImageProvider):
    def __init__(self, icon_dir: Path = ICON_DIR) -> None:
        super().__init__(QQmlImageProviderBase.ImageType.Image)
        self._dir = icon_dir
        self._renderers: dict[str, QSvgRenderer] = {}
        self._warned: set[str] = set()
        self._lock = threading.Lock()   # Image.asynchronous loads off the GUI thread

    def _renderer(self, name: str) -> QSvgRenderer | None:
        with self._lock:
            if name in self._renderers:
                return self._renderers[name]
            path = self._dir / f"{name}.svg"
            renderer = QSvgRenderer(str(path)) if path.is_file() else None
            if renderer is not None and not renderer.isValid():
                renderer = None
            if renderer is None:
                if name not in self._warned:
                    self._warned.add(name)
                    qWarning(f"cryoicon: unknown icon {name!r}")
                return None
            self._renderers[name] = renderer
            return renderer

    def requestImage(self, request_id: str, size: QSize, requested: QSize) -> QImage:  # noqa: N802
        name, color = parse_request(request_id)
        w = requested.width() if requested.width() > 0 else DEFAULT_SIZE
        h = requested.height() if requested.height() > 0 else DEFAULT_SIZE
        w, h = min(w, MAX_SIZE), min(h, MAX_SIZE)
        image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        if size is not None:
            size.setWidth(w)
            size.setHeight(h)
        renderer = self._renderer(name)
        if renderer is None:
            return image
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        with self._lock:
            renderer.render(painter, QRectF(0, 0, w, h))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(image.rect(), color)
        painter.end()
        return image
