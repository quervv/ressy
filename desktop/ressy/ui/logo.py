from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from . import theme

BAR_W = 8.0
CENTERS = (8.0, 20.0, 32.0, 44.0, 56.0)
HEIGHTS = (18.0, 36.0, 54.0, 36.0, 18.0)
MID_Y = 30.0
BAR = QRectF(14, 61, 36, 2.4)
PRESS = 0.9


def bar_rects(level: float = 1.0, voice: Sequence[float] | None = None, pressed: bool = False) -> list[QRectF]:
    level = max(0.0, min(1.0, level))
    rects = []
    for i, (cx, full) in enumerate(zip(CENTERS, HEIGHTS)):
        h = BAR_W + (full - BAR_W) * level
        if voice is not None:
            v = max(0.0, min(1.0, float(voice[i])))
            h = BAR_W + (h - BAR_W) * (0.55 + 0.45 * v)
        if pressed:
            h *= PRESS
        h = max(BAR_W, h)
        rects.append(QRectF(cx - BAR_W / 2, MID_Y - h / 2, BAR_W, h))
    return rects


def paint_mark(
    painter: QPainter,
    rect: QRectF,
    *,
    pressed: bool = False,
    backlight: bool = False,
    min_bar_px: float = 0.0,
    level: float = 1.0,
    voice: Sequence[float] | None = None,
    two_tone: bool = True,
) -> None:
    side = min(rect.width(), rect.height())
    scale = side / 64.0
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(rect.x() + (rect.width() - side) / 2, rect.y() + (rect.height() - side) / 2)
    painter.scale(scale, scale)
    painter.setPen(Qt.PenStyle.NoPen)

    if backlight:
        bar = QRectF(BAR)
        if min_bar_px and bar.height() * scale < min_bar_px:
            height = min_bar_px / scale
            bar = QRectF(bar.x(), 64.0 - height, bar.width(), height)
        painter.setBrush(QColor(theme.BACKLIGHT))
        painter.drawRoundedRect(bar, bar.height() / 2, bar.height() / 2)

    for i, r in enumerate(bar_rects(level, voice, pressed)):
        painter.setBrush(QColor(theme.LILAC if i == 2 and two_tone else theme.ACCENT))
        painter.drawRoundedRect(r, BAR_W / 2, BAR_W / 2)
    painter.restore()


def mark_image(
    size: int, *, pressed: bool = False, backlight: bool = False, dpr: float = 1.0, level: float = 1.0
) -> QImage:
    px = max(1, round(size * dpr))
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    paint_mark(painter, QRectF(0, 0, px, px), pressed=pressed, backlight=backlight, min_bar_px=2.0, level=level,
               two_tone=False)
    painter.end()
    image.setDevicePixelRatio(dpr)
    return image


def mark_pixmap(
    size: int, *, pressed: bool = False, backlight: bool = False, dpr: float = 1.0, level: float = 1.0
) -> QPixmap:
    return QPixmap.fromImage(mark_image(size, pressed=pressed, backlight=backlight, dpr=dpr, level=level))


_ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
_icons: dict[tuple[bool, bool, bool], QIcon] = {}


def icon(*, pressed: bool = False, backlight: bool = False, awake: bool = True) -> QIcon:
    key = (pressed, backlight, awake)
    cached = _icons.get(key)
    if cached is None:
        cached = QIcon()
        for size in _ICON_SIZES:
            cached.addPixmap(mark_pixmap(size, pressed=pressed, backlight=backlight, level=1.0 if awake else 0.0))
        _icons[key] = cached
    return cached


def app_icon() -> QIcon:
    return icon()


def svg(*, backlight: bool = False, awake: bool = True, two_tone: bool = False) -> str:
    bar = (
        f'<rect x="{BAR.x():g}" y="{BAR.y():g}" width="{BAR.width():g}" height="{BAR.height():g}" '
        f'rx="{BAR.height() / 2:g}" fill="{theme.BACKLIGHT}"/>'
        if backlight
        else ""
    )
    bars = "".join(
        f'<rect x="{r.x():g}" y="{r.y():g}" width="{r.width():g}" height="{r.height():g}" rx="{BAR_W / 2:g}" '
        f'fill="{theme.LILAC if i == 2 and two_tone else theme.ACCENT}"/>'
        for i, r in enumerate(bar_rects(1.0 if awake else 0.0))
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="Ressy">'
        f"{bar}{bars}</svg>"
    )


def save_ico(path: str) -> None:
    from io import BytesIO

    from PIL import Image
    from PySide6.QtCore import QBuffer, QIODevice

    images = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        mark_image(size).save(buffer, "PNG")
        images.append(Image.open(BytesIO(bytes(buffer.data()))).convert("RGBA"))
    largest = images[-1]
    largest.save(path, format="ICO", sizes=[im.size for im in images], append_images=images[:-1])
