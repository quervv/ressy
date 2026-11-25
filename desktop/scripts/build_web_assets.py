from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QGuiApplication, QImage, QPainter

from ressy.ui import logo, theme

ALPHA, ALPHA_SKIRT = "#E9E6DF", "#C9C4B9"
PLATE_DEEP = "#111216"


def _canvas(width: int, height: int) -> tuple[QImage, QPainter]:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(theme.PLATE))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    return image, painter


def apple_touch_icon(path: Path) -> None:
    image, p = _canvas(180, 180)
    logo.paint_mark(p, QRectF(26, 24, 128, 128))
    p.end()
    image.save(str(path), "PNG")


def _key(p: QPainter, rect: QRectF, u: float, top: str, skirt: str, legend: str, text: str, size: float, weight: int, width: float) -> None:
    pad = u * 0.028
    cap = rect.adjusted(pad, pad, -pad, -pad)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 110))
    p.drawRoundedRect(cap.translated(0, u * 0.035), u * 0.12, u * 0.12)
    p.setBrush(QColor(skirt))
    p.drawRoundedRect(cap, u * 0.12, u * 0.12)
    face = cap.adjusted(u * 0.085, u * 0.035, -u * 0.085, -u * 0.15)
    p.setBrush(QColor(top))
    p.drawRoundedRect(face, u * 0.085, u * 0.085)
    if text:
        p.setPen(QColor(legend))
        p.setFont(theme.font(size, weight, width))
        ascent = QFontMetricsF(p.font()).ascent()
        p.drawText(QPointF(face.x() + u * 0.1, face.y() + u * 0.075 + ascent * 0.8), text)


def og_image(path: Path) -> None:
    w, h = 1200, 630
    image, p = _canvas(w, h)
    margin = 72.0

    logo.paint_mark(p, QRectF(margin - 4, 52, 56, 56))
    p.setPen(QColor(theme.LEGEND))
    p.setFont(theme.font(40, 800, 112))
    p.drawText(QPointF(margin + 64, 94), "ressy")

    size = 80.0
    line1 = theme.font(size, 800, 108)
    p.setFont(line1)
    fm = QFontMetricsF(line1)
    base1 = 236.0
    p.drawText(QPointF(margin, base1), "Tieni premuto")
    x = margin + fm.horizontalAdvance("Tieni premuto ")
    cap = QRectF(x, base1 - size * 0.86, size * 1.1, size * 1.06)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.ACCENT_SKIRT))
    p.drawRoundedRect(cap, size * 0.16, size * 0.16)
    face = cap.adjusted(size * 0.07, size * 0.03, -size * 0.07, -size * 0.12)
    p.setBrush(QColor(theme.ACCENT))
    p.drawRoundedRect(face, size * 0.12, size * 0.12)
    p.setPen(QColor(theme.INK))
    small = theme.font(size * 0.6, 700, 100)
    p.setFont(small)
    p.drawText(QPointF(face.x() + size * 0.16, face.y() + size * 0.1 + QFontMetricsF(small).ascent() * 0.82), "K")
    p.setPen(QColor(theme.LEGEND))
    p.setFont(theme.font(size, 400, 100))
    p.drawText(QPointF(margin, base1 + size * 1.08), "e di’ «Ressy, sveglia!»")

    u = 104.0
    top_y = 398.0
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(PLATE_DEEP))
    p.drawRect(QRectF(0, top_y - 10, w, h - top_y + 10))
    p.setBrush(QColor(theme.PLATE_EDGE))
    p.drawRect(QRectF(0, top_y - 10, w, 1))
    x0 = -150.0
    rows = [
        [("Tab", 1.5, "mod")] + [(c, 1, "a") for c in "QWERTYUIOP"] + [("é", 1, "a"), ("*", 1, "a"), ("", 1.5, "a")],
        [("Bloc Maiusc", 1.75, "mod")] + [(c, 1, "a") for c in "ASDFGHJ"] + [("K", 1, "k")] + [(c, 1, "a") for c in "Lòàù"],
        [("Maiusc", 1.25, "mod")] + [(c, 1, "a") for c in "<ZXCVBNM,.-"] + [("", 2.75, "mod")],
    ]
    for r, row in enumerate(rows):
        x = x0
        y = top_y + r * u
        for text, width_u, kind in row:
            rect = QRectF(x, y, width_u * u, u)
            if kind == "mod":
                _key(p, rect, u, theme.MODS, theme.MODS_SKIRT, theme.LEGEND, text, u * 0.13, 600, 112)
            elif kind == "k":
                _key(p, rect, u, theme.ACCENT, theme.ACCENT_SKIRT, theme.INK, text, u * 0.24, 600, 100)
            else:
                _key(p, rect, u, ALPHA, ALPHA_SKIRT, theme.MODS, text, u * 0.24, 600, 100)
            x += width_u * u
    p.end()
    image.save(str(path), "PNG")


def main() -> None:
    web = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "web"
    assets = web / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    theme.family()
    (assets / "ressy-mark.svg").write_text(logo.svg(), encoding="utf-8")
    logo.save_ico(str(web / "favicon.ico"))
    apple_touch_icon(assets / "apple-touch-icon.png")
    og_image(assets / "og.png")
    del app
    for name in ("favicon.ico", "assets/ressy-mark.svg", "assets/apple-touch-icon.png", "assets/og.png"):
        print("wrote", web / name)


if __name__ == "__main__":
    main()
