"""Render a contact sheet of the Cryo SVG icon set.

Usage:
    QT_QPA_PLATFORM=offscreen .venv/bin/python tools/icon_sheet.py OUT.png

Every icon in src/cryo/gui/assets/icons is drawn at 16, 20, 24 and 48 px,
tinted cyan on the dark panel and dark navy on the light panel, one row per
icon with its file name underneath.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ICON_DIR = Path(__file__).resolve().parent.parent / "src" / "cryo" / "gui" / "assets" / "icons"
SIZES = (16, 20, 24, 48)
THEMES = (
    ("#090D14", "#00D1FF", "#8FA3B8"),  # dark panel, cyan icon, label
    ("#EEF5FA", "#0B2A3A", "#4A5D6E"),  # light panel, navy icon, label
)
COLS = 3
PAD = 12
GAP = 14
LABEL_H = 16


def tinted(renderer: QSvgRenderer, size: int, color: str) -> QImage:
    """Rasterize the SVG at size x size and replace its colour, keeping alpha."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(img.rect(), QColor(color))
    p.end()
    return img


def cell_width() -> int:
    return sum(SIZES) + GAP * (len(SIZES) - 1)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    out = Path(argv[1])
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841
    icons = sorted(ICON_DIR.glob("*.svg"))
    if not icons:
        print(f"no icons in {ICON_DIR}")
        return 1

    # One cell = both themes side by side for one icon.
    half_w = cell_width() + 2 * PAD
    cell_w = half_w * len(THEMES)
    cell_h = max(SIZES) + LABEL_H + 2 * PAD
    rows = (len(icons) + COLS - 1) // COLS
    sheet = QImage(cell_w * COLS, cell_h * rows, QImage.Format.Format_ARGB32_Premultiplied)
    sheet.fill(QColor("#000000"))

    p = QPainter(sheet)
    font = QFont("JetBrains Mono")
    font.setPixelSize(11)
    p.setFont(font)
    for i, path in enumerate(icons):
        renderer = QSvgRenderer(str(path))
        cx = (i % COLS) * cell_w
        cy = (i // COLS) * cell_h
        for t, (bg, fg, label) in enumerate(THEMES):
            x0 = cx + t * half_w
            p.fillRect(x0, cy, half_w, cell_h, QColor(bg))
            x = x0 + PAD
            base = cy + PAD + max(SIZES)
            for s in SIZES:
                p.drawImage(x, base - s, tinted(renderer, s, fg))
                x += s + GAP
            p.setPen(QColor(label))
            p.drawText(
                QRectF(x0 + PAD, base + 2, half_w - 2 * PAD, LABEL_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                path.stem,
            )
    p.end()

    out.parent.mkdir(parents=True, exist_ok=True)
    if not sheet.save(str(out)):
        print(f"could not write {out}")
        return 1
    print(f"wrote {out} ({len(icons)} icons)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
