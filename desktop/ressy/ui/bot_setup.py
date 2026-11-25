from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFormLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from . import theme

MODES = (
    ("off", "Nessuno", "Ressy risponde solo alla tua voce, su questo PC."),
    ("local", "Il tuo bot, su questo PC",
     "Crei un bot tuo su Telegram (o Discord) e Ressy lo fa girare qui. Niente da ospitare. "
     "Quando il PC è spento il bot tace; quando si riaccende ti scrive che è di nuovo online "
     "e non esegue i messaggi arrivati nel frattempo."),
    ("server", "Il tuo server (self-host)",
     "Il bot gira su una macchina tua sempre accesa (un altro PC, un Raspberry, un VPS) e ti avvisa "
     "subito quando questo PC va offline. Puoi installare il server con questo stesso installer."),
)


def link(text: str, url: str) -> str:
    return f'<a href="{url}" style="color:{theme.LEGEND};">{text}</a>'


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    return label


def secret_field(placeholder: str) -> QLineEdit:
    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.Password)
    field.setPlaceholderText(placeholder)
    field.setClearButtonEnabled(True)
    return field


TOKEN_HELP = (
    "Telegram: scrivi " + link("@BotFather", "https://t.me/BotFather")
    + " <code>/newbot</code>, scegli un nome e copia il token. "
    "Discord (facoltativo): " + link("Developer Portal", "https://discord.com/developers/applications")
    + " → New Application → Bot → Reset Token. "
    "I token restano su questo PC, cifrati da Windows."
)


class TokenFields(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.telegram = secret_field("123456789:AA…")
        self.discord = secret_field("facoltativo")
        form.addRow("Token Telegram", self.telegram)
        form.addRow("Token Discord", self.discord)

    def values(self) -> dict[str, str]:
        return {"telegram_token": self.telegram.text().strip(), "discord_token": self.discord.text().strip()}

    def set_values(self, telegram: str, discord: str) -> None:
        self.telegram.setText(telegram)
        self.discord.setText(discord)


def check_token(platform: str, token: str) -> str:
    token = token.strip()
    if not token:
        return ""
    if any(ch.isspace() for ch in token):
        return "Il token non deve contenere spazi."
    if platform == "telegram":
        head, _, tail = token.partition(":")
        if not head.isdigit() or len(tail) < 30:
            return "Il token Telegram ha la forma 123456789:AA… (lo trovi nel messaggio di BotFather)."
    elif len(token) < 50 or token.count(".") < 2:
        return "Il token Discord è lungo e ha due punti: copialo da Bot → Reset Token."
    return ""


def check_server_url(url: str) -> str:
    url = url.strip()
    if not url:
        return "Scrivi l'indirizzo del tuo server, per esempio ws://192.168.1.10:8765/ws/agent."
    if not url.startswith(("ws://", "wss://")):
        return "L'indirizzo del server inizia con ws:// (rete di casa) o wss:// (Internet, con HTTPS)."
    return ""


class BotSetup(QWidget):

    changed = Signal()

    def __init__(self, parent: QWidget | None = None, *, show_help: bool = True) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.group = QButtonGroup(self)
        self.radios: dict[str, QRadioButton] = {}

        self.local_box = QWidget()
        local = QVBoxLayout(self.local_box)
        local.setContentsMargins(26, 0, 0, 10)
        local.setSpacing(8)
        self.tokens = TokenFields()
        local.addWidget(self.tokens)
        if show_help:
            local.addWidget(hint(TOKEN_HELP))

        self.server_box = QWidget()
        server = QFormLayout(self.server_box)
        server.setContentsMargins(26, 0, 0, 10)
        server.setHorizontalSpacing(18)
        self.server_url = QLineEdit()
        self.server_url.setPlaceholderText("ws://192.168.1.10:8765/ws/agent")
        server.addRow("Indirizzo del server", self.server_url)
        boxes = {"local": self.local_box, "server": self.server_box}
        for key, title, text in MODES:
            radio = QRadioButton(title)
            radio.setObjectName("mode")
            self.group.addButton(radio)
            self.radios[key] = radio
            layout.addWidget(radio)
            desc = hint(text)
            desc.setContentsMargins(26, 0, 0, 6)
            layout.addWidget(desc)
            if key in boxes:
                layout.addWidget(boxes[key])
            radio.toggled.connect(self._sync)
        self.radios["local"].setChecked(True)
        self._sync()

    def _sync(self) -> None:
        mode = self.mode()
        self.local_box.setVisible(mode == "local")
        self.server_box.setVisible(mode == "server")
        self.changed.emit()

    def mode(self) -> str:
        for key, radio in self.radios.items():
            if radio.isChecked():
                return key
        return "off"

    def load(self, *, enabled: bool, mode: str, server_url: str, telegram: str, discord: str) -> None:
        self.radios["off" if not enabled else (mode if mode in self.radios else "local")].setChecked(True)
        self.server_url.setText(server_url)
        self.tokens.set_values(telegram, discord)
        self._sync()

    def problem(self) -> str:
        mode = self.mode()
        if mode == "local":
            values = self.tokens.values()
            if not values["telegram_token"] and not values["discord_token"]:
                return "Incolla il token del tuo bot Telegram (o Discord)."
            return check_token("telegram", values["telegram_token"]) or check_token("discord", values["discord_token"])
        if mode == "server":
            return check_server_url(self.server_url.text())
        return ""

    def values(self) -> dict[str, Any]:
        mode = self.mode()
        out: dict[str, Any] = {"remote_enabled": mode != "off"}
        if mode != "off":
            out["remote_mode"] = mode
        if mode == "local":
            out.update(self.tokens.values())
        if mode == "server":
            out["server_url"] = self.server_url.text().strip()
        return out
