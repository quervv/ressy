from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class UiBridge(QObject):
    stateChanged = Signal(str)
    hudShown = Signal()
    hudHidden = Signal()
    ressyLine = Signal(str)
    userLine = Signal(str, bool)
    statusChanged = Signal(str)
    remoteStateChanged = Signal(str, str)
    linksChanged = Signal(object)
    linkedAccount = Signal(object)
    pairCodeReady = Signal(object)
    pairFailed = Signal(str)
    toastRequested = Signal(str, str)
    settingsRequested = Signal(str)
    videoUploadRequested = Signal(object)

    def state(self, state: str) -> None:
        self.stateChanged.emit(state)

    def show_hud(self) -> None:
        self.hudShown.emit()

    def hide_hud(self) -> None:
        self.hudHidden.emit()

    def ressy_line(self, text: str) -> None:
        self.ressyLine.emit(text)

    def user_line(self, text: str, final: bool) -> None:
        self.userLine.emit(text, final)

    def status(self, text: str) -> None:
        self.statusChanged.emit(text)

    def remote_state(self, state: str, detail: str) -> None:
        self.remoteStateChanged.emit(state, detail)

    def links(self, links: list) -> None:
        self.linksChanged.emit(list(links))

    def linked(self, link: dict) -> None:
        self.linkedAccount.emit(dict(link))

    def pair_code(self, data: dict) -> None:
        self.pairCodeReady.emit(dict(data))

    def pair_error(self, text: str) -> None:
        self.pairFailed.emit(text)

    def toast(self, title: str, text: str) -> None:
        self.toastRequested.emit(title, text)

    def open_settings(self, reason: str) -> None:
        self.settingsRequested.emit(reason)

    def request_video_upload(self, payload: dict) -> None:
        self.videoUploadRequested.emit(payload)
