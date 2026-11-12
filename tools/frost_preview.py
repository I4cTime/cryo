#!/usr/bin/env python3
"""Render FrostOverlay over a background at several amounts, for judging the art.

Needs a real GPU platform for the shader path; never run it bare on a desktop
session (it opens a window). Headless recipe:

    gamescope --backend headless -W 800 -H 1100 -- env -u WAYLAND_DISPLAY \\
        QT_QPA_PLATFORM=xcb .venv/bin/python tools/frost_preview.py OUT_DIR \\
        --background shot.png

With QT_QPA_PLATFORM=offscreen Qt uses the software renderer and this shows
the static fallback instead (the report says which path was used).

Writes into OUT_DIR:
  dark-<amount>.png, dark-sheet.png       frost over --background (or a dark fill)
  pale-<amount>.png, pale-sheet.png       frost over a pale fill, shade enabled
  sweep-sheet.png, sweep-zoom-sheet.png   0 to 0.9 sweep, plus 2x crops of the front
  size-<w>x<h>-<amount>.png, sizes-sheet.png   other window sizes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow  # noqa: F401  (QQuickWindow: grabWindow)

ROOT = Path(__file__).resolve().parents[1]
FX_DIR = ROOT / "src" / "cryo" / "gui" / "fx"

AMOUNTS = [0.0, 0.15, 0.30, 0.45, 0.60, 0.85, 1.0]
SWEEP = [0.0, 0.15, 0.30, 0.45, 0.60, 0.75, 0.90]

QML = """
import QtQuick
import QtQuick.Window
Window {
    id: win
    width: 480; height: 860
    visible: true
    color: "black"
    property alias bgSource: bg.source
    property alias bgColor: fill.color
    Rectangle { id: fill; anchors.fill: parent }
    Image { id: bg; anchors.fill: parent; fillMode: Image.Stretch; smooth: true }
    FrostOverlay { id: frost; objectName: "frost"; anchors.fill: parent }
}
"""


def sheet(
    images: list[QImage], labels: list[str], path: Path, scale: float = 1.0
) -> None:
    w = int(max(i.width() for i in images) * scale)
    h = int(max(i.height() for i in images) * scale)
    pad, head = 8, 26
    out = QImage(
        len(images) * (w + pad) + pad, h + head + pad, QImage.Format.Format_RGB32
    )
    out.fill(QColor(24, 24, 28))
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    font = QFont()
    font.setPixelSize(16)
    p.setFont(font)
    p.setPen(QColor(230, 230, 235))
    for k, (img, label) in enumerate(zip(images, labels)):
        x = pad + k * (w + pad)
        p.drawText(QRect(x, 0, w, head), Qt.AlignmentFlag.AlignCenter, label)
        p.drawImage(
            QRect(x, head, int(img.width() * scale), int(img.height() * scale)), img
        )
    p.end()
    out.save(str(path))


def main() -> int:
    ap = argparse.ArgumentParser(description="Render FrostOverlay previews")
    ap.add_argument("out", type=Path)
    ap.add_argument(
        "--background", type=Path, help="screenshot to use as the dark background"
    )
    ap.add_argument("--pale", default="#EAF3F9")
    ap.add_argument("--shade-strength", type=float, default=0.6)
    ap.add_argument(
        "--zoom-rect", default="300,120,180,260", help="x,y,w,h of the sweep crop"
    )
    ap.add_argument("--sizes", default="440x700,720x1000")
    ap.add_argument("--size-amount", type=float, default=0.45)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.loadData(QML.encode(), QUrl.fromLocalFile(str(FX_DIR / "_preview.qml")))
    if not engine.rootObjects():
        return 1
    win = engine.rootObjects()[0]
    frost = win.findChild(QQuickItem, "frost")

    jobs: list = []
    results: dict[str, list] = {}

    def grab(group: str, label: str, name: str):
        img = win.grabWindow()
        img.save(str(args.out / f"{name}.png"))
        results.setdefault(group, []).append((img, label))

    def setup(bg_src: str, bg_color: str, shade: float, w: int = 480, h: int = 860):
        def run():
            win.setProperty("width", w)
            win.setProperty("height", h)
            win.setProperty("bgColor", bg_color)
            win.setProperty("bgSource", bg_src)
            frost.setProperty("shadeStrength", shade)

        return run

    def amount(a: float):
        return lambda: frost.setProperty("amount", a)

    bg_url = (
        QUrl.fromLocalFile(str(args.background.resolve())).toString()
        if args.background
        else ""
    )
    jobs.append(setup(bg_url, "#05060A", 0.0))
    for a in AMOUNTS:
        jobs += [amount(a), lambda a=a: grab("dark", f"{a:.2f}", f"dark-{a:.2f}")]
    for a in SWEEP:
        jobs += [amount(a), lambda a=a: grab("sweep", f"{a:.2f}", f"sweep-{a:.2f}")]
    for size in args.sizes.split(","):
        w, h = (int(v) for v in size.split("x"))
        jobs.append(setup(bg_url, "#05060A", 0.0, w, h))
        for a in (args.size_amount, 0.85):
            jobs += [
                amount(a),
                lambda w=w, h=h, a=a: grab(
                    "sizes", f"{w}x{h} @ {a:.2f}", f"size-{w}x{h}-{a:.2f}"
                ),
            ]
    jobs.append(setup("", args.pale, args.shade_strength))
    for a in AMOUNTS:
        jobs += [amount(a), lambda a=a: grab("pale", f"{a:.2f}", f"pale-{a:.2f}")]

    def finish():
        print(f"renderer available={frost.property('available')}")
        sheet(*zip(*results["dark"]), args.out / "dark-sheet.png")
        sheet(*zip(*results["pale"]), args.out / "pale-sheet.png")
        sheet(*zip(*results["sweep"]), args.out / "sweep-sheet.png")
        x, y, w, h = (int(v) for v in args.zoom_rect.split(","))
        crops = [img.copy(x, y, w, h) for img, _ in results["sweep"]]
        sheet(
            crops,
            [lbl for _, lbl in results["sweep"]],
            args.out / "sweep-zoom-sheet.png",
            2.0,
        )
        sheet(*zip(*results["sizes"]), args.out / "sizes-sheet.png")
        app.quit()

    jobs.append(finish)

    def step():
        if jobs:
            jobs.pop(0)()
            QTimer.singleShot(60, step)

    QTimer.singleShot(400, step)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
