from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QEasingCurve, QElapsedTimer, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QImage, QMouseEvent, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import logo, theme
from ..i18n import tr

if TYPE_CHECKING:
    from ..core.controller import Controller
    from .bridge import UiBridge

WIDTH = 452
SHADOW_SIDE, SHADOW_TOP, SHADOW_BOTTOM = 18, 10, 26
PAD = 18
LEGEND_COLUMN = 68
FRAME_MS = 16


def clip_text(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:")
    return cut + "…"


class VoiceLines(QWidget):

    ATTACK = 0.55
    RELEASE = 0.16

    def __init__(self, color: str, height: int, bar: float = 5.0, gap: float = 4.0, parent=None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._rest = QColor(theme.REST)
        self._bar = bar
        self._gap = gap
        self._values = np.zeros(24, dtype=np.float32)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def feed(self, bands: np.ndarray) -> bool:
        if bands.size >= 24:
            groups = np.maximum(bands[0:24:2], bands[1:24:2])
        else:
            groups = np.zeros(12, dtype=np.float32)
        target = np.concatenate([groups[::-1], groups]).astype(np.float32) ** 0.85
        rising = target > self._values
        coef = np.where(rising, self.ATTACK, self.RELEASE).astype(np.float32)
        new = self._values + (target - self._values) * coef
        new[new < 0.004] = 0.0
        moved = bool(np.max(np.abs(new - self._values)) > 0.002)
        self._values = new
        if moved:
            self.update()
        return moved

    def reset(self) -> None:
        self._values[:] = 0.0
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        n = self._values.size
        bar, gap = self._bar, self._gap
        total = n * bar + (n - 1) * gap
        scale = min(1.0, self.width() / total) if total else 1.0
        bar, gap = bar * scale, gap * scale
        x = 0.0
        mid = self.height() / 2
        span = self.height() - bar
        for value in self._values:
            h = bar + float(value) * span
            p.setBrush(self._color if value > 0.02 else self._rest)
            p.drawRoundedRect(QRectF(x, mid - h / 2, bar, h), bar / 2, bar / 2)
            x += bar + gap
        p.end()


class MarkWidget(QWidget):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.pressed = False
        self.backlight = False
        self.awake = False
        self.mood = "asleep"
        self.level = 0.0
        self.voice = [1.0] * 5
        self._voice_target = [1.0] * 5
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last = 0.0
        self.setFixedSize(QSize(54, 58))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._anim = QTimer(self)
        self._anim.setInterval(16)
        self._anim.timeout.connect(self._step)

    def set_state(
        self,
        *,
        pressed: bool | None = None,
        backlight: bool | None = None,
        mood: str | None = None,
    ) -> None:
        changed = False
        if pressed is not None and pressed != self.pressed:
            self.pressed, changed = pressed, True
        if backlight is not None and backlight != self.backlight:
            self.backlight, changed = backlight, True
        if mood is not None:
            self.mood = mood
            self.awake = mood != "asleep"
            if mood != "speaking":
                self._voice_target = [1.0] * 5
            self._anim.start()
        if changed:
            self.update()

    def set_voice(self, bands) -> None:
        if self.mood != "speaking" or bands is None or len(bands) == 0:
            return
        n = len(bands)
        picks = [bands[min(n - 1, int(n * f))] for f in (0.1, 0.3, 0.5, 0.7, 0.9)]
        self._voice_target = [max(0.0, min(1.0, float(v))) for v in picks]
        if not self._anim.isActive():
            self._anim.start()

    def _now(self) -> float:
        return self._clock.elapsed() / 1000.0

    def _step(self) -> None:
        now = self._now()
        dt = min(0.05, max(0.0, now - self._last)) if self._last else 0.016
        self._last = now
        target_level = 1.0 if self.awake else 0.0
        rate = 14.0 if target_level > self.level else 10.0
        self.level += (target_level - self.level) * (1.0 - math.exp(-rate * dt))
        target = list(self._voice_target)
        if self.mood == "thinking":
            target = [0.55 + 0.45 * (0.5 + 0.5 * math.sin(now * 5.0 - i * 0.9)) for i in range(5)]
        for i in range(5):
            self.voice[i] += (target[i] - self.voice[i]) * (1.0 - math.exp(-18.0 * dt))
        self.update()
        moving = self.mood == "thinking" or any(abs(target[i] - self.voice[i]) > 0.003 for i in range(5))
        if not moving and abs(target_level - self.level) < 0.003:
            self.level = target_level
            self._anim.stop()
            self._last = 0.0

    def hideEvent(self, event) -> None:
        self._anim.stop()
        self._last = 0.0

    def showEvent(self, event) -> None:
        self._anim.start()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        logo.paint_mark(
            p,
            QRectF(0, 0, 54, 54),
            pressed=self.pressed,
            backlight=False,
            level=self.level,
            voice=self.voice,
        )
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.BACKLIGHT if self.backlight else theme.REST))
        p.drawRoundedRect(QRectF(12, 54.5, 30, 3), 1.5, 1.5)
        p.end()


class EscKey(QAbstractButton):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(QSize(44, 34))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("Metti Ressy a dormire"))
        self.setAccessibleName(tr("Metti Ressy a dormire"))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover = False

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        travel = 2.0 if self.isDown() else 0.0
        skirt = QRectF(1, 1 + travel, self.width() - 2, self.height() - 2 - travel)
        p.setBrush(QColor(theme.MODS_SKIRT))
        p.drawRoundedRect(skirt, 7, 7)
        top = QRectF(4, 2 + travel, self.width() - 8, self.height() - 10)
        p.setBrush(QColor("#363942" if self._hover else theme.MODS))
        p.drawRoundedRect(top, 5, 5)
        p.setPen(QColor(theme.LEGEND))
        p.setFont(theme.font(11, 600, 112))
        p.drawText(top, Qt.AlignmentFlag.AlignCenter, "Esc")
        p.end()


def _legend(text: str, color: str) -> QLabel:
    label = QLabel(text.upper())
    f = theme.font(11, 700, 108)
    f.setLetterSpacing(f.SpacingType.PercentageSpacing, 104)
    label.setFont(f)
    label.setStyleSheet("color: {color}; background: transparent;".format(color=color))
    label.setFixedWidth(LEGEND_COLUMN)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    return label


class Hud(QWidget):
    def __init__(self, controller: "Controller", bridge: "UiBridge") -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        super().__init__(None, flags)
        self.controller = controller
        self.setWindowTitle("Ressy")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedWidth(WIDTH)

        self._state = "asleep"
        self._remote_state = getattr(controller.remote, "state", "disabled")
        self._ressy_text = ""
        self._status_text = ""
        self._drag: QPoint | None = None
        self._shadow: QPixmap | None = None
        self._hiding = False

        self.mark = MarkWidget()
        self.ressy_lines = VoiceLines(theme.LEGEND, 52)
        self.esc = EscKey()
        self.esc.clicked.connect(self.controller.sleep)

        self.state_legend = _legend(tr("Dorme"), theme.LEGEND)
        self.presence_legend = _legend(theme.OFFLINE_LABEL, theme.LEGEND_DIM)
        self.ressy_label = QLabel()
        self.ressy_label.setWordWrap(True)
        self.ressy_label.setFont(theme.font(15, 450, 100))
        self.ressy_label.setTextFormat(Qt.TextFormat.PlainText)
        self.ressy_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.ressy_label.setMaximumHeight(QFontMetrics(self.ressy_label.font()).lineSpacing() * 3 + 2)

        self.user_legend = _legend(tr("Tu"), theme.ACCENT)
        self.user_lines = VoiceLines(theme.ACCENT, 30)
        self.user_label = QLabel()
        self.user_label.setWordWrap(True)
        self.user_label.setFont(theme.font(14, 400, 100))
        self.user_label.setTextFormat(Qt.TextFormat.PlainText)
        self.user_label.setStyleSheet("color: {LEGEND}; background: transparent;".format(LEGEND=theme.LEGEND))
        self.user_label.setMaximumHeight(QFontMetrics(self.user_label.font()).lineSpacing() * 2 + 2)

        for w in (self.ressy_label, self.user_label, self.state_legend, self.presence_legend, self.user_legend):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignTop)
        top.addWidget(self.ressy_lines, 1, Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.esc, 0, Qt.AlignmentFlag.AlignTop)

        legends = QVBoxLayout()
        legends.setSpacing(4)
        legends.addWidget(self.state_legend)
        legends.addWidget(self.presence_legend)
        legends.addStretch(1)
        speech = QHBoxLayout()
        speech.setSpacing(0)
        speech.addLayout(legends)
        speech.addWidget(self.ressy_label, 1)

        self.separator = QWidget()
        self.separator.setFixedHeight(1)
        self.separator.setStyleSheet("background: {PLATE_EDGE};".format(PLATE_EDGE=theme.PLATE_EDGE))

        you = QHBoxLayout()
        you.setSpacing(0)
        you.addWidget(self.user_legend, 0, Qt.AlignmentFlag.AlignVCenter)
        you.addWidget(self.user_lines, 1)
        heard = QHBoxLayout()
        heard.setSpacing(0)
        heard.addSpacing(LEGEND_COLUMN)
        heard.addWidget(self.user_label, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(SHADOW_SIDE + PAD, SHADOW_TOP + PAD - 2, SHADOW_SIDE + PAD - 8, SHADOW_BOTTOM + PAD)
        root.setSpacing(0)
        root.addLayout(top)
        root.addSpacing(12)
        root.addLayout(speech)
        root.addSpacing(14)
        root.addWidget(self.separator)
        root.addSpacing(12)
        root.addLayout(you)
        root.addSpacing(4)
        root.addLayout(heard)

        self._apply_state()
        self._apply_presence()
        self._render_texts()

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(170)
        self._fade.setEasingCurve(QEasingCurve.Type.OutExpo)
        self._fade.finished.connect(self._fade_done)
        self._slide = QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(220)
        self._slide.setEasingCurve(QEasingCurve.Type.OutExpo)
        self._linger = QTimer(self)
        self._linger.setSingleShot(True)
        self._linger.setInterval(620)
        self._linger.timeout.connect(self._fade_out)
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

        bridge.stateChanged.connect(self.on_state)
        bridge.hudShown.connect(self.reveal)
        bridge.hudHidden.connect(self.conceal)
        bridge.ressyLine.connect(self.on_ressy_line)
        bridge.userLine.connect(self.on_user_line)
        bridge.statusChanged.connect(self.on_status)
        bridge.remoteStateChanged.connect(self.on_remote_state)

    def on_state(self, state: str) -> None:
        self._state = state
        self._apply_state()
        self._render_texts()

    def on_ressy_line(self, text: str) -> None:
        self._ressy_text = text
        self._status_text = ""
        self._render_texts()

    def on_status(self, text: str) -> None:
        self._status_text = text
        self._render_texts()

    def on_user_line(self, text: str, final: bool) -> None:
        if final and text and text != tr("Non ho sentito niente."):
            shown = f"«{clip_text(text, 160)}»"
        else:
            shown = clip_text(text, 160)
        self.user_label.setText(shown)

    def on_remote_state(self, state: str, detail: str) -> None:
        self._remote_state = state
        self._apply_presence()

    def _apply_state(self) -> None:
        label = theme.STATE_LABELS.get(self._state, tr("Ascolta"))
        self.state_legend.setText(label.upper())
        self.mark.set_state(pressed=self._state == "hearing", mood=self._state)

    def _apply_presence(self) -> None:
        enabled = bool(self.controller.settings.remote_ready)
        online = self._remote_state == "online"
        self.mark.set_state(backlight=online)
        self.presence_legend.setVisible(enabled and not online)
        tip = {
            "online": tr("Telegram/Discord: online, puoi comandare il PC dal telefono"),
            "connecting": tr("Telegram/Discord: mi sto collegando al server…"),
            "disabled": tr("Comandi da Telegram/Discord disattivati"),
            "auth_failed": tr("Telegram/Discord: il server ha rifiutato questo PC"),
            "outdated": tr("Telegram/Discord: aggiorna Ressy per collegarti"),
            "replaced": tr("Telegram/Discord: Ressy è attiva su un altro PC con la stessa identità"),
            "bot_error": tr("Telegram/Discord: il tuo bot non è partito, controlla il token"),
        }.get(self._remote_state, tr("Telegram/Discord: offline"))
        self.mark.setToolTip(tip)

    def _render_texts(self) -> None:
        thinking = self._state == "thinking"
        if thinking and self._status_text:
            text, color = self._status_text, theme.LEGEND_DIM
        elif self._ressy_text:
            speaking = self._state == "speaking"
            text, color = self._ressy_text, theme.LEGEND if speaking or thinking else theme.LEGEND_DIM
        else:
            text, color = self._status_text, theme.LEGEND_DIM
        self.ressy_label.setText(clip_text(text, 230))
        self.ressy_label.setStyleSheet("color: {color}; background: transparent;".format(color=color))

    def _tick(self) -> None:
        _, ressy = self.controller.player.meter.read()
        self.ressy_lines.feed(ressy)
        self.mark.set_voice(self.ressy_lines._values)
        if self.controller.mic.running and self.controller.listening:
            _, user = self.controller.mic.meter.read()
        else:
            user = np.zeros(24, dtype=np.float32)
        self.user_lines.feed(user)

    def _plate_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(SHADOW_SIDE, SHADOW_TOP, -SHADOW_SIDE, -SHADOW_BOTTOM)

    def _shadow_pixmap(self) -> QPixmap:
        if self._shadow is not None and self._shadow.size() == self.size() * self.devicePixelRatioF():
            return self._shadow
        dpr = self.devicePixelRatioF()
        image = QImage((self.size() * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.GlobalColor.transparent)
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        plate = self._plate_rect()
        steps = 16
        for i in range(steps, 0, -1):
            p.setBrush(QColor(0, 0, 0, 9))
            p.drawRoundedRect(plate.adjusted(-i * 0.9, -i * 0.5 + 6, i * 0.9, i * 1.1 + 6), 14 + i, 14 + i)
        p.end()
        self._shadow = QPixmap.fromImage(image)
        return self._shadow

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(0, 0, self._shadow_pixmap())
        plate = self._plate_rect()
        p.setPen(QColor(theme.PLATE_EDGE))
        p.setBrush(QColor(theme.PLATE))
        p.drawRoundedRect(plate.adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)
        p.end()

    def resizeEvent(self, event) -> None:
        self._shadow = None
        super().resizeEvent(event)

    def _default_pos(self) -> QPoint:
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)
        return QPoint(area.center().x() - self.width() // 2, area.top() + 24)

    def _saved_pos(self) -> QPoint | None:
        x, y = self.controller.settings.hud_x, self.controller.settings.hud_y
        if x is None or y is None:
            return None
        frame = QRect(int(x), int(y), self.width(), max(self.height(), 120))
        for screen in QGuiApplication.screens():
            visible = screen.availableGeometry().intersected(frame)
            if visible.width() * visible.height() >= 0.6 * frame.width() * frame.height():
                return QPoint(int(x), int(y))
        return None

    def reveal(self) -> None:
        self._hiding = False
        self._linger.stop()
        self.adjustSize()
        target = self._saved_pos() or self._default_pos()
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.move(target + QPoint(0, 8))
            self.show()
            self.raise_()
            self._slide.stop()
            self._slide.setStartValue(target + QPoint(0, 8))
            self._slide.setEndValue(target)
            self._slide.start()
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start()

    def conceal(self) -> None:
        if not self.isVisible():
            return
        self._hiding = True
        if self._state != "hearing" and not self._linger.isActive():
            self._linger.start()
            return
        self._fade_out()

    def _fade_out(self) -> None:
        if not self._hiding:
            return
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _fade_done(self) -> None:
        if self._hiding and self.windowOpacity() <= 0.01:
            self.hide()
            self._timer.stop()
            self.ressy_lines.reset()
            self.user_lines.reset()
            self._ressy_text = ""
            self._status_text = ""
            self.user_label.setText("")
            self._render_texts()
            self._hiding = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._slide.stop()
            self.move(event.globalPosition().toPoint() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag = None
            pos = self.pos()
            self.controller.apply_settings(hud_x=int(pos.x()), hud_y=int(pos.y()))
            event.accept()
