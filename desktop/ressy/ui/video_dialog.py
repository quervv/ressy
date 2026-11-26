from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from . import theme
from .winframe import style_title_bar

log = logging.getLogger("ressy.video_ui")

_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


class _DropList(QListWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(130)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        if not event.mimeData().hasUrls():
            return
        added = 0
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() in (_VIDEO_EXTS | _AUDIO_EXTS):
                self._add_path(str(path))
                added += 1
        if added:
            event.acceptProposedAction()

    def _add_path(self, path: str) -> None:
        existing = {self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())}
        if path in existing:
            return
        from PySide6.QtWidgets import QListWidgetItem

        item = QListWidgetItem(Path(path).name)
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        self.addItem(item)


class VideoUploadDialog(QDialog):

    def __init__(self, defaults: dict[str, Any] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._defaults = defaults or {}
        self.result_payload: dict[str, Any] | None = None

        self.setWindowTitle(tr("Ressy · Carica i video da editare"))
        self.setMinimumWidth(540)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        title = QLabel(tr("Carica i video da editare"))
        title.setObjectName("title")
        title.setFont(theme.font(19, 700, 110))

        intro = QLabel(
            tr("Trascina i video qui sotto oppure scegli i file. Ressy aggiungerà sfondo, effetti e frasi ad impatto su CapCut o DaVinci Resolve.")
        )
        intro.setObjectName("hint")
        intro.setWordWrap(True)

        self.file_list = _DropList(self)
        for existing in self._defaults.get("files") or []:
            self.file_list._add_path(str(existing))

        browse_btn = QPushButton(tr("Scegli video…"))
        browse_btn.clicked.connect(self._browse_videos)
        clear_btn = QPushButton(tr("Rimuovi selezionato"))
        clear_btn.clicked.connect(self._remove_selected)

        file_btns = QHBoxLayout()
        file_btns.addWidget(browse_btn)
        file_btns.addWidget(clear_btn)
        file_btns.addStretch(1)

        self.editor = QComboBox()
        self.editor.addItem(tr("Automatico (usa quello installato)"), "auto")
        self.editor.addItem("CapCut", "capcut")
        self.editor.addItem("DaVinci Resolve", "davinci")
        wanted_ed = str(self._defaults.get("editor") or "auto")
        idx = self.editor.findData(wanted_ed)
        if idx >= 0:
            self.editor.setCurrentIndex(idx)

        self.style = QComboBox()
        self.style.addItem(tr("Viral / TikTok / Reels (dinamico + testi grandi)"), "viral")
        self.style.addItem(tr("Cinematic (transizioni morbide + titoli eleganti)"), "cinematic")
        self.style.addItem(tr("Gaming / Highlight (zoom veloci + neon)"), "gaming")
        self.style.addItem(tr("Vlog (pulito + sottotitoli)"), "vlog")
        wanted_st = str(self._defaults.get("style") or "viral")
        s_idx = self.style.findData(wanted_st)
        if s_idx >= 0:
            self.style.setCurrentIndex(s_idx)

        self.ratio = QComboBox()
        self.ratio.addItem(tr("Verticale 9:16 (TikTok / Reels / Shorts)"), "9:16")
        self.ratio.addItem(tr("Orizzontale 16:9 (YouTube)"), "16:9")
        self.ratio.addItem(tr("Quadrato 1:1"), "1:1")
        wanted_ratio = str(self._defaults.get("aspect_ratio") or "9:16")
        r_idx = self.ratio.findData(wanted_ratio)
        if r_idx >= 0:
            self.ratio.setCurrentIndex(r_idx)

        self.hook_title = QLineEdit(str(self._defaults.get("title") or ""))
        self.hook_title.setPlaceholderText(tr("Es. NON CI CREDERAI MAI (opzionale)"))

        self.phrases = QLineEdit(", ".join(self._defaults.get("phrases") or []))
        self.phrases.setPlaceholderText(tr("Frasi ad impatto separate da virgola (opzionale)"))

        self.transition = QComboBox()
        self.transition.addItem(tr("Smooth Fade / Dissolve"), "smooth")
        self.transition.addItem(tr("Zoom Whip dinamico"), "zoom_whip")
        self.transition.addItem(tr("Flash cinematografico"), "flash")
        self.transition.addItem(tr("Nessuna transizione (cut netti)"), "cut")
        t_idx = self.transition.findData(str(self._defaults.get("transition") or "smooth"))
        if t_idx >= 0:
            self.transition.setCurrentIndex(t_idx)

        self.color_grade = QComboBox()
        self.color_grade.addItem(tr("Vivido / Social Pop"), "vivid")
        self.color_grade.addItem(tr("Teal & Orange Cinematic"), "teal_orange")
        self.color_grade.addItem(tr("Pellicola contrastata"), "cinematic_film")
        self.color_grade.addItem(tr("Naturale (nessuna alterazione)"), "neutral")
        c_idx = self.color_grade.findData(str(self._defaults.get("color_grade") or "vivid"))
        if c_idx >= 0:
            self.color_grade.setCurrentIndex(c_idx)

        self.auto_captions = QCheckBox(tr("Sottotitoli automatici sincronizzati dall'audio"))
        self.auto_captions.setChecked(bool(self._defaults.get("auto_captions", True)))

        self.progress_bar = QCheckBox(tr("Barra di avanzamento moderna nella parte bassa"))
        self.progress_bar.setChecked(bool(self._defaults.get("progress_bar", True)))

        self.render_preview = QCheckBox(tr("Esporta anche un MP4 finito pronto subito (oltre al progetto)"))
        self.render_preview.setChecked(bool(self._defaults.get("render_preview", True)))

        form = QFormLayout()
        form.addRow(tr("Editor video"), self.editor)
        form.addRow(tr("Stile montaggio"), self.style)
        form.addRow(tr("Formato"), self.ratio)
        form.addRow(tr("Transizioni"), self.transition)
        form.addRow(tr("Color grading"), self.color_grade)
        form.addRow(tr("Titolo iniziale"), self.hook_title)
        form.addRow(tr("Frasi ad impatto"), self.phrases)
        form.addRow("", self.auto_captions)
        form.addRow("", self.progress_bar)
        form.addRow("", self.render_preview)

        self.error_lbl = QLabel()
        self.error_lbl.setStyleSheet("color: #FF6B81;")
        self.error_lbl.hide()

        cancel_btn = QPushButton(tr("Annulla"))
        cancel_btn.clicked.connect(self.reject)
        start_btn = QPushButton(tr("Inizia editing"))
        start_btn.setObjectName("primary")
        start_btn.setDefault(True)
        start_btn.clicked.connect(self._accept)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(cancel_btn)
        actions.addWidget(start_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(self.file_list)
        layout.addLayout(file_btns)
        layout.addLayout(form)
        layout.addWidget(self.error_lbl)
        layout.addLayout(actions)
        style_title_bar(self)

    def _browse_videos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            tr("Seleziona i video o l'audio"),
            "",
            tr("Video e audio (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.mp3 *.wav);;Tutti i file (*)"),
        )
        for p in paths:
            self.file_list._add_path(p)
        if paths:
            self.error_lbl.hide()

    def _remove_selected(self) -> None:
        for item in self.file_list.selectedItems():
            row = self.file_list.row(item)
            self.file_list.takeItem(row)

    def _accept(self) -> None:
        files: list[str] = []
        music = ""
        for i in range(self.file_list.count()):
            p = str(self.file_list.item(i).data(Qt.ItemDataRole.UserRole) or "")
            if not p:
                continue
            if Path(p).suffix.lower() in _AUDIO_EXTS and not music:
                music = p
            else:
                files.append(p)
        if not files:
            self.error_lbl.setText(tr("Carica almeno un video prima di iniziare."))
            self.error_lbl.show()
            return
        phrases = [p.strip() for p in self.phrases.text().split(",") if p.strip()]
        self.result_payload = {
            "files": files,
            "music": music,
            "editor": str(self.editor.currentData() or "auto"),
            "style": str(self.style.currentData() or "viral"),
            "aspect_ratio": str(self.ratio.currentData() or "9:16"),
            "transition": str(self.transition.currentData() or "smooth"),
            "color_grade": str(self.color_grade.currentData() or "vivid"),
            "title": self.hook_title.text().strip(),
            "phrases": phrases,
            "auto_captions": self.auto_captions.isChecked(),
            "progress_bar": self.progress_bar.isChecked(),
            "render_preview": self.render_preview.isChecked(),
        }
        self.accept()
