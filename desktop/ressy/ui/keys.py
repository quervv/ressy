from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QKeySequence, QPainter, QPaintEvent
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from . import theme
from ..i18n import tr

UNIT = 44


def paint_keycap(
    p: QPainter,
    rect: QRectF,
    legend: str,
    *,
    accent: bool = False,
    pressed: bool = False,
    hover: bool = False,
    font_px: float = 15,
    width_axis: float = 100,
    focus: bool = False,
) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    travel = 2.0 if pressed else 0.0
    skirt = rect.adjusted(0.5, 0.5 + travel, -0.5, -0.5)
    p.setBrush(QColor(theme.ACCENT_SKIRT if accent else theme.MODS_SKIRT))
    p.drawRoundedRect(skirt, 8, 8)
    top = QRectF(rect.x() + 4, rect.y() + 2 + travel, rect.width() - 8, rect.height() - 11)
    if accent:
        fill = "#AE85FF" if hover else theme.ACCENT
    else:
        fill = "#33363E" if hover else theme.MODS
    p.setBrush(QColor(fill))
    p.drawRoundedRect(top, 6, 6)
    if focus:
        pen_color = QColor(theme.LEGEND if accent else theme.ACCENT)
        p.setPen(pen_color)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect.adjusted(-2.5, -2.5, 2.5, 2.5), 10, 10)
        p.setPen(Qt.PenStyle.NoPen)
    p.setPen(QColor(theme.INK if accent else theme.LEGEND))
    p.setFont(theme.font(font_px, 650, width_axis))
    p.drawText(top, Qt.AlignmentFlag.AlignCenter, legend)
    p.restore()


_ALLOWED_VK = (
    set(range(0x30, 0x3A))
    | set(range(0x41, 0x5B))
    | set(range(0x60, 0x70))
    | set(range(0x70, 0x88))
    | {0x13, 0x91, 0x2D}
    | set(range(0xBA, 0xC1))
    | set(range(0xDB, 0xE0))
    | {0xE2}
)


named_qt = {
    Qt.Key.Key_Pause: 0x13,
    Qt.Key.Key_ScrollLock: 0x91,
    Qt.Key.Key_Insert: 0x2D,
    Qt.Key.Key_Semicolon: 0xBA,
    Qt.Key.Key_Equal: 0xBB,
    Qt.Key.Key_Comma: 0xBC,
    Qt.Key.Key_Minus: 0xBD,
    Qt.Key.Key_Period: 0xBE,
    Qt.Key.Key_Slash: 0xBF,
    Qt.Key.Key_QuoteLeft: 0xC0,
    Qt.Key.Key_BracketLeft: 0xDB,
    Qt.Key.Key_Backslash: 0xDC,
    Qt.Key.Key_BracketRight: 0xDD,
    Qt.Key.Key_Apostrophe: 0xDE,
}


def _resolve_vk(event: QKeyEvent) -> int:
    import sys

    if sys.platform == "win32":
        return int(event.nativeVirtualKey())
    qt = int(event.key())
    if 0x30 <= qt <= 0x39 or 0x41 <= qt <= 0x5A:
        return qt
    if Qt.Key.Key_F1 <= qt <= Qt.Key.Key_F24:
        return 0x70 + (qt - int(Qt.Key.Key_F1))
    if event.key() in named_qt:
        return named_qt[event.key()]
    return int(event.nativeVirtualKey())


def key_name(vk: int, text: str = "", qt_key: int = 0) -> str:
    if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    if 0x60 <= vk <= 0x69:
        return tr("Num {value}").format(value=vk - 0x60)
    named = {0x13: tr("Pausa"), 0x91: tr("Bloc Scorr"), 0x2D: tr("Ins"), 0x6A: tr("Num *"), 0x6B: tr("Num +"), 0x6D: tr("Num -"),
             0x6E: tr("Num ,"), 0x6F: tr("Num /")}
    if vk in named:
        return named[vk]
    if text and text.isprintable() and not text.isspace():
        return text.upper()
    if qt_key:
        native = QKeySequence(qt_key).toString(QKeySequence.SequenceFormat.NativeText)
        if native:
            return native
    return tr("Tasto {vk:#04x}").format(vk=vk)


class KeyCapture(QAbstractButton):

    captured = Signal(int, str)
    capturing = Signal(bool)

    def __init__(self, vk: int, name: str, parent=None) -> None:
        super().__init__(parent)
        self.vk = vk
        self.name = name
        self._listening = False
        self._hover = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(UNIT + 6)
        self.setMinimumWidth(int(UNIT * 1.25))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.clicked.connect(self._toggle)
        self._update_accessible()

    def sizeHint(self) -> QSize:
        if self._listening:
            return QSize(int(UNIT * 4.25), UNIT + 6)
        width = 1.25 if len(self.name) <= 2 else 2.25
        return QSize(int(UNIT * width), UNIT + 6)

    def set_key(self, vk: int, name: str) -> None:
        self.vk, self.name = vk, name
        self._update_accessible()
        self.updateGeometry()
        self.update()

    def _update_accessible(self) -> None:
        self.setAccessibleName(tr("Tasto per parlare: {name}. Premi per cambiarlo.").format(name=self.name))

    def _toggle(self) -> None:
        if self._listening:
            self.stop()
        else:
            self._listening = True
            self.capturing.emit(True)
            self.grabKeyboard()
            self.updateGeometry()
            self.update()

    def stop(self) -> None:
        if self._listening:
            self._listening = False
            self.releaseKeyboard()
            self.capturing.emit(False)
            self.updateGeometry()
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._listening:
            super().keyPressEvent(event)
            return
        if event.isAutoRepeat():
            return
        vk = _resolve_vk(event)
        if event.key() == Qt.Key.Key_Escape:
            self.stop()
            return
        if vk in _ALLOWED_VK:
            name = key_name(vk, event.text(), int(event.key()))
            self.set_key(vk, name)
            self.stop()
            self.captured.emit(vk, name)

    def focusOutEvent(self, event) -> None:
        self.stop()
        super().focusOutEvent(event)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        rect = QRectF(3, 3, self.width() - 6, self.height() - 6)
        if self._listening:
            paint_keycap(p, rect, tr("Premi il nuovo tasto (Esc annulla)"), pressed=True, font_px=13, focus=True)
        else:
            paint_keycap(p, rect, self.name, accent=True, pressed=self.isDown(), hover=self._hover,
                         font_px=18 if len(self.name) <= 2 else 14, width_axis=112, focus=self.hasFocus())
        p.end()


class CodeKeys(QWidget):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.code = ""
        self.setFixedHeight(UNIT + 4)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set_code(self, code: str) -> None:
        self.code = code
        self.setAccessibleName(tr("Codice di collegamento: {code}").format(code=" ".join(code)))
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(max(1, len(self.code)) * (UNIT + 6), UNIT + 4)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        x = 0.0
        for char in self.code:
            paint_keycap(p, QRectF(x, 2, UNIT, UNIT), char, font_px=20, width_axis=112)
            x += UNIT + 6
        p.end()


class PresenceLight(QWidget):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.online = False
        self.setFixedSize(QSize(28, 6))

    def set_online(self, online: bool) -> None:
        if online != self.online:
            self.online = online
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.BACKLIGHT if self.online else theme.REST))
        p.drawRoundedRect(QRectF(0, 1.5, 28, 3), 1.5, 1.5)
        p.end()
