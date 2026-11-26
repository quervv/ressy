from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import logo, theme
from ..i18n import tr

if TYPE_CHECKING:
    from ..core.controller import Controller
    from .bridge import UiBridge

PRESENCE_TEXT = {
    "online": tr("Online"),
    "connecting": tr("Mi collego…"),
    "offline": tr("Offline"),
    "disabled": tr("Disattivato"),
    "auth_failed": tr("Rifiutato dal server"),
    "outdated": tr("Da aggiornare"),
    "replaced": tr("Attiva su un altro PC"),
    "bot_error": tr("Bot fermo"),
}


class Tray(QObject):
    def __init__(
        self,
        controller: "Controller",
        bridge: "UiBridge",
        *,
        open_settings: Callable[[str], None],
        open_pairing: Callable[[], None],
        quit_app: Callable[[], None],
    ) -> None:
        super().__init__()
        self.controller = controller
        self._open_settings = open_settings
        self._state = controller.state
        self._remote = getattr(controller.remote, "state", "disabled")

        self.icon = QSystemTrayIcon(self)
        menu = QMenu()
        self.header = menu.addAction("Ressy")
        self.header.setEnabled(False)
        menu.addSeparator()
        self.wake_action = menu.addAction(tr("Sveglia Ressy"))
        self.wake_action.triggered.connect(self._toggle_wake)
        self.stop_action = menu.addAction(tr("Interrompi la voce"))
        self.stop_action.triggered.connect(controller.stop_speaking)
        menu.addSeparator()
        menu.addAction(tr("Collega Telegram o Discord…")).triggered.connect(open_pairing)
        menu.addAction(tr("Impostazioni…")).triggered.connect(lambda: open_settings(""))
        menu.addSeparator()
        self._quit_separator = menu.actions()[-1]
        menu.addAction(tr("Esci da Ressy")).triggered.connect(quit_app)
        self.menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._activated)

        bridge.stateChanged.connect(self._on_state)
        bridge.remoteStateChanged.connect(self._on_remote)
        bridge.toastRequested.connect(self.toast)
        self._refresh()
        self.icon.show()

    def add_update_action(self, callback: Callable[[], None]):
        from PySide6.QtGui import QAction

        action = QAction(tr("Aggiorna Ressy…"), self.menu)
        action.triggered.connect(callback)
        action.setVisible(False)
        self.menu.insertAction(self._quit_separator, action)
        return action

    def _toggle_wake(self) -> None:
        if self.controller.awake:
            self.controller.sleep()
        else:
            self.controller.wake()

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.menu.popup(QCursor.pos())
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._open_settings("")

    def toast(self, title: str, text: str) -> None:
        if QSystemTrayIcon.supportsMessages():
            self.icon.showMessage(title, text, logo.app_icon(), 6000)

    def _on_state(self, state: str) -> None:
        self._state = state
        self._refresh()

    def _on_remote(self, state: str, detail: str) -> None:
        self._remote = state
        self._refresh()

    def _refresh(self) -> None:
        awake = self._state != "asleep"
        online = self._remote == "online"
        self.icon.setIcon(logo.icon(pressed=awake, backlight=online, awake=awake))
        label = theme.STATE_LABELS.get(self._state, tr("Dorme"))
        presence = PRESENCE_TEXT.get(self._remote, tr("Offline"))
        key = self.controller.settings.hotkey_name or "K"
        self.header.setText(tr("Ressy · {label} · Telegram/Discord: {presence}").format(label=label, presence=presence))
        self.wake_action.setText(tr("Metti Ressy a dormire") if awake else tr("Sveglia Ressy"))
        self.stop_action.setVisible(self._state == "speaking")
        tip = tr("Ressy · {label} · Telegram/Discord: {presence}\nTieni premuto {key} e di' «Ressy, sveglia!»").format(label=label, presence=presence, key=key)
        self.icon.setToolTip(tip[:127])
