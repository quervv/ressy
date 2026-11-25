from __future__ import annotations

import logging
import threading
from typing import Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from .. import __version__, updater
from . import theme
from .winframe import style_title_bar

log = logging.getLogger("ressy.update")


def short_notes(text: str, limit: int = 6) -> str:
    lines = []
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("-*• ").replace("**", "").replace("`", "")
        if line:
            lines.append(line)
        if len(lines) >= limit:
            break
    return "\n".join(f"• {line}" for line in lines)


class UpdateChecker(QObject):

    found = Signal(object)

    def __init__(self, enabled: Callable[[], bool], first_ms: int = 20_000, every_ms: int = 6 * 3600_000) -> None:
        super().__init__()
        self._enabled = enabled
        self.release: updater.Release | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_now)
        QTimer.singleShot(first_ms, self.check_now)
        self._timer.start(every_ms)

    def check_now(self) -> None:
        if not updater.can_update() or not self._enabled():
            return
        threading.Thread(target=self._check, name="update-check", daemon=True).start()

    def _check(self) -> None:
        release = updater.check()
        if release is not None:
            self.found.emit(release)


class UpdateDialog(QDialog):
    progress = Signal(int, int)
    failed = Signal(str)
    ready = Signal(str)

    def __init__(self, quit_app: Callable[[], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._quit_app = quit_app
        self.release: updater.Release | None = None
        self._cancel = threading.Event()
        self.setWindowTitle("Ressy · Aggiornamento")
        self.setMinimumWidth(520)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self.title = QLabel()
        self.title.setObjectName("title")
        self.title.setFont(theme.font(20, 700, 112))
        self.title.setWordWrap(True)
        self.intro = QLabel()
        self.intro.setObjectName("hint")
        self.intro.setWordWrap(True)
        self.notes = QLabel()
        self.notes.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.bar.hide()
        self.status = QLabel()
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        self.later = QPushButton("Più tardi")
        self.update_button = QPushButton("Aggiorna")
        self.update_button.setObjectName("primary")
        self.update_button.setMinimumWidth(130)
        self.later.clicked.connect(self._later)
        self.update_button.clicked.connect(self._start)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.later)
        buttons.addWidget(self.update_button)
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 20)
        v.setSpacing(12)
        for widget in (self.title, self.intro, self.notes, self.bar, self.status):
            v.addWidget(widget)
        v.addSpacing(6)
        v.addLayout(buttons)

        self.progress.connect(self._on_progress)
        self.failed.connect(self._on_failed)
        self.ready.connect(self._on_ready)

    def offer(self, release: updater.Release) -> None:
        busy = self.bar.isVisible() and not self.update_button.isEnabled()
        if busy:
            return
        self.release = release
        self.title.setText(f"È disponibile Ressy {release.version}")
        self.intro.setText(f"Hai la versione {__version__}. L'aggiornamento richiede un minuto: Ressy si chiude, "
                           "si aggiorna e riparte da sola. Le tue impostazioni restano.")
        notes = short_notes(release.notes)
        self.notes.setText(notes)
        self.notes.setVisible(bool(notes))
        self.status.setText("")
        self.bar.hide()
        self.update_button.setEnabled(True)
        self.update_button.setText("Aggiorna")
        self.later.setEnabled(True)
        self.show()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        style_title_bar(self)

    def _later(self) -> None:
        self._cancel.set()
        self.hide()

    def _start(self) -> None:
        if self.release is None:
            return
        self._cancel = threading.Event()
        self.update_button.setEnabled(False)
        self.update_button.setText("Scarico…")
        self.bar.setValue(0)
        self.bar.show()
        self.status.setText("Scarico l'aggiornamento…")
        release, cancel = self.release, self._cancel
        threading.Thread(target=self._download, args=(release, cancel), name="update-download", daemon=True).start()

    def _download(self, release: updater.Release, cancel: threading.Event) -> None:
        try:
            setup = updater.download(release, lambda done, total: self.progress.emit(done, total), cancel)
        except InterruptedError:
            return
        except Exception as exc:
            log.warning("update download failed: %s", exc)
            self.failed.emit(str(exc) or type(exc).__name__)
            return
        self.ready.emit(str(setup))

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.bar.setValue(int(100 * done / total))
            self.status.setText(f"Scarico l'aggiornamento… {done / 1e6:.0f} di {total / 1e6:.0f} MB")

    def _on_failed(self, error: str) -> None:
        self.bar.hide()
        self.status.setText(f"Aggiornamento non riuscito: {error}")
        self.update_button.setEnabled(True)
        self.update_button.setText("Riprova")

    def _on_ready(self, setup: str) -> None:
        from pathlib import Path

        self.status.setText("Installo: Ressy si chiude e riparte tra poco…")
        self.later.setEnabled(False)
        try:
            updater.install(Path(setup))
        except OSError as exc:
            self._on_failed(f"non riesco ad avviare l'installazione ({exc})")
            return
        log.info("update to %s started", self.release.version if self.release else "?")
        QTimer.singleShot(1500, self._quit_app)
