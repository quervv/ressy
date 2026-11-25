from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPainter, QPaintEvent, QShowEvent
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme
from .keys import CodeKeys
from .winframe import style_title_bar

if TYPE_CHECKING:
    from ..core.controller import Controller
    from .bridge import UiBridge


class QrCode(QWidget):

    def __init__(self, size: int = 168, parent=None) -> None:
        super().__init__(parent)
        self.matrix: list[list[bool]] = []
        self.setFixedSize(QSize(size, size))

    def set_data(self, data: str) -> None:
        import qrcode

        qr = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(data)
        qr.make(fit=True)
        self.matrix = [[bool(cell) for cell in row] for row in qr.get_matrix()]
        self.setAccessibleName("Codice QR del link di Telegram")
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.LEGEND))
        p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        if not self.matrix:
            p.end()
            return
        n = len(self.matrix)
        quiet = 3
        cell = self.width() / (n + 2 * quiet)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setBrush(QColor(theme.PLATE))
        for y, row in enumerate(self.matrix):
            for x, dark in enumerate(row):
                if dark:
                    p.drawRect(QRectF((x + quiet) * cell, (y + quiet) * cell, cell + 0.4, cell + 0.4))
        p.end()


class PairDialog(QDialog):
    def __init__(self, controller: "Controller", bridge: "UiBridge", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._expires_at = 0.0
        self._code = ""
        self._discord_command = ""
        self._telegram_url = ""
        self._discord_invite = ""
        self.setWindowTitle("Ressy · Collega Telegram o Discord")
        self.setMinimumWidth(620)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        title = QLabel("Collega il telefono")
        title.setObjectName("title")
        title.setFont(theme.font(22, 700, 112))
        intro = QLabel(
            "Dal bot di Telegram o Discord potrai dare comandi a questo PC, anche con un messaggio vocale. "
            "Il codice vale una volta sola."
        )
        intro.setObjectName("hint")
        intro.setWordWrap(True)

        self.status = QLabel("Chiedo un codice al bot…")
        self.status.setWordWrap(True)
        self.code_keys = CodeKeys()
        self.copy_code = QPushButton("Copia il codice")
        self.copy_code.clicked.connect(lambda: self._copy(self._code, self.copy_code, "Copia il codice"))
        self.expiry = QLabel()
        self.expiry.setObjectName("hint")
        code_row = QHBoxLayout()
        code_row.addWidget(self.code_keys)
        code_row.addSpacing(10)
        code_row.addWidget(self.copy_code)
        code_row.addStretch(1)

        self.qr = QrCode()
        self.telegram_title = QLabel("<b>Telegram</b>")
        self.telegram_text = QLabel()
        self.telegram_text.setWordWrap(True)
        self.telegram_open = QPushButton("Apri Telegram")
        self.telegram_open.setObjectName("primary")
        self.telegram_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._telegram_url)))
        tg_text = QVBoxLayout()
        tg_text.addWidget(self.telegram_title)
        tg_text.addWidget(self.telegram_text)
        tg_text.addWidget(self.telegram_open, 0, Qt.AlignmentFlag.AlignLeft)
        tg_text.addStretch(1)
        self.telegram_box = QWidget()
        tg = QHBoxLayout(self.telegram_box)
        tg.setContentsMargins(0, 0, 0, 0)
        tg.setSpacing(18)
        tg.addWidget(self.qr, 0, Qt.AlignmentFlag.AlignTop)
        tg.addLayout(tg_text, 1)

        self.discord_title = QLabel("<b>Discord</b>")
        self.discord_text = QLabel()
        self.discord_text.setWordWrap(True)
        self.discord_copy = QPushButton("Copia il comando")
        self.discord_copy.clicked.connect(
            lambda: self._copy(self._discord_command, self.discord_copy, "Copia il comando")
        )
        self.discord_invite_button = QPushButton("Aggiungi il bot")
        self.discord_invite_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._discord_invite)))
        dc_buttons = QHBoxLayout()
        dc_buttons.addWidget(self.discord_copy)
        dc_buttons.addWidget(self.discord_invite_button)
        dc_buttons.addStretch(1)
        self.discord_box = QWidget()
        dc = QVBoxLayout(self.discord_box)
        dc.setContentsMargins(0, 0, 0, 0)
        dc.addWidget(self.discord_title)
        dc.addWidget(self.discord_text)
        dc.addLayout(dc_buttons)

        self.retry = QPushButton("Nuovo codice")
        self.retry.clicked.connect(self.request)
        close = QPushButton("Chiudi")
        close.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(self.retry)
        bottom.addStretch(1)
        bottom.addWidget(close)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)
        root.addWidget(title)
        root.addWidget(intro)
        root.addWidget(self.status)
        root.addLayout(code_row)
        root.addWidget(self.expiry)
        root.addSpacing(6)
        root.addWidget(self.telegram_box)
        root.addSpacing(6)
        root.addWidget(self.discord_box)
        root.addStretch(1)
        root.addLayout(bottom)

        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._countdown)
        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self.accept)

        bridge.pairCodeReady.connect(self._on_code)
        bridge.pairFailed.connect(self._on_error)
        bridge.linkedAccount.connect(self._on_linked)
        self._show_code(False)

    def open_and_request(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.request()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        style_title_bar(self)

    def request(self) -> None:
        self._close_timer.stop()
        self._show_code(False)
        self.status.setObjectName("")
        self._restyle(self.status)
        if not self.controller.settings.remote_ready:
            self._on_error("Il controllo da remoto non è configurato: in Impostazioni › Da remoto scegli il tuo bot e incolla il token.")
            return
        self.status.setText("Chiedo un codice al bot…")
        self.retry.setEnabled(False)
        self.controller.request_pair_code()

    def _on_code(self, data: dict) -> None:
        if not self.isVisible():
            return
        self._code = str(data.get("code") or "")
        self._expires_at = time.monotonic() + float(data.get("expires_in") or 600)
        platforms = data.get("platforms") or {}
        self.status.setText("Usa questo codice dal telefono:")
        self.code_keys.set_code(self._code)

        telegram = platforms.get("telegram")
        self.telegram_box.setVisible(bool(telegram))
        if telegram:
            self._telegram_url = str(telegram.get("url") or "")
            self.telegram_text.setText(
                "Inquadra il QR con il telefono, oppure apri il link: il bot ti collega da solo.<br>"
                f"<span style='color:{theme.LEGEND_DIM}'>{telegram.get('instruction', '')}</span>"
            )
            self.telegram_open.setVisible(bool(self._telegram_url))
            if self._telegram_url:
                self.qr.set_data(self._telegram_url)
            self.qr.setVisible(bool(self._telegram_url))

        discord = platforms.get("discord")
        self.discord_box.setVisible(bool(discord))
        if discord:
            self._discord_command = f"!collega {self._code}"
            self._discord_invite = str(discord.get("url") or "")
            self.discord_text.setText(str(discord.get("instruction") or ""))
            self.discord_invite_button.setVisible(bool(self._discord_invite))
        if not telegram and not discord:
            self.status.setText("Il server non ha bot attivi: chiedi a chi lo gestisce di configurarli.")
        self._show_code(True)
        self.retry.setEnabled(True)
        self._countdown()
        self._tick.start()

    def _on_error(self, text: str) -> None:
        if not self.isVisible():
            return
        self._tick.stop()
        self._show_code(False)
        self.status.setText(text or "Il server non ha risposto.")
        self.status.setObjectName("error")
        self._restyle(self.status)
        self.retry.setEnabled(True)

    def _on_linked(self, link: dict) -> None:
        if not self.isVisible():
            return
        platform = {"telegram": "Telegram", "discord": "Discord"}.get(str(link.get("platform")), "chat")
        self._tick.stop()
        self._show_code(False)
        self.status.setObjectName("ok")
        self._restyle(self.status)
        self.status.setText(f"Collegato: {link.get('display', '')} su {platform}. Ora puoi scrivere al bot.")
        self._close_timer.start(2600)

    def _countdown(self) -> None:
        left = int(self._expires_at - time.monotonic())
        if left <= 0:
            self._tick.stop()
            self._show_code(False)
            self.status.setText("Il codice è scaduto: chiedine uno nuovo.")
            return
        self.expiry.setText(f"Scade tra {left // 60}:{left % 60:02d}")

    def _show_code(self, visible: bool) -> None:
        for widget in (self.code_keys, self.copy_code, self.expiry):
            widget.setVisible(visible)
        if not visible:
            self.telegram_box.hide()
            self.discord_box.hide()

    @staticmethod
    def _restyle(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _copy(self, text: str, button: QPushButton, label: str) -> None:
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        button.setText("Copiato")
        QTimer.singleShot(1500, lambda: button.setText(label))

    def done(self, result: int) -> None:
        self._tick.stop()
        self._close_timer.stop()
        super().done(result)
