from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from . import theme
from .winframe import style_title_bar

log = logging.getLogger("ressy.video_studio")

_STAGES: list[tuple[str, str]] = [
    ("analyze", tr("Analisi clip & audio")),
    ("assets", tr("Sfondo studio & grafiche")),
    ("captions", tr("Trascrizione & sottotitoli")),
    ("effects", tr("Color grading, FX & transizioni")),
    ("timeline", tr("Timeline, keyframe & progetto")),
    ("render", tr("Render MP4 & apertura editor")),
]

_TRACK_COLORS: dict[str, str] = {
    "V3": "#9D6BFF",
    "V2": "#F6AD55",
    "FX": "#EC4899",
    "V1": "#38BDF8",
    "BG": "#475569",
    "A1": "#4DF0B5",
}


def _open_local_path(path: str) -> None:
    target = str(path or "").strip()
    if not target:
        return
    try:
        if sys.platform == "win32":
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
    except Exception as exc:
        log.warning("open path failed (%s): %s", target, exc)


class _TimelineCanvas(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(188)
        self._duration: float = 12.0
        self._playhead: float = 0.0
        self._tracks: list[dict[str, Any]] = []
        self._transitions: list[float] = []

    def set_data(
        self,
        *,
        duration: float | None = None,
        playhead: float | None = None,
        tracks: list[dict[str, Any]] | None = None,
        transitions: list[float] | None = None,
    ) -> None:
        if duration is not None and duration > 0.1:
            self._duration = float(duration)
        if playhead is not None:
            self._playhead = max(0.0, float(playhead))
        if tracks is not None:
            self._tracks = list(tracks)
        if transitions is not None:
            self._transitions = [float(t) for t in transitions]
        self.update()

    def set_playhead(self, seconds: float) -> None:
        self._playhead = max(0.0, float(seconds))
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        h = self.height()

        p.fillRect(0, 0, w, h, QColor("#121318"))
        p.setPen(QPen(QColor(theme.PLATE_EDGE), 1))
        p.drawRoundedRect(0.5, 0.5, w - 1, h - 1, 8, 8)

        label_w = 88
        ruler_h = 22
        plot_x = label_w
        plot_w = max(40, w - label_w - 10)
        dur = max(1.0, self._duration)

        p.fillRect(0, 1, w - 1, ruler_h, QColor("#1A1C23"))
        p.setPen(QColor(theme.LEGEND_DIM))
        p.setFont(theme.font(10, 600))
        p.drawText(10, 15, "TIMELINE")

        step = 1.0 if dur <= 10 else (2.0 if dur <= 24 else 5.0)
        t = 0.0
        p.setPen(QColor("#5C6070"))
        while t <= dur + 0.01:
            x = plot_x + (t / dur) * plot_w
            p.drawLine(int(x), ruler_h - 6, int(x), ruler_h)
            if t < dur - step * 0.25:
                p.drawText(int(x) + 3, 14, f"{t:.0f}s")
            t += step

        tracks = self._tracks or [
            {"id": "V3", "label": "V3 TITOLI", "items": []},
            {"id": "V2", "label": "V2 SUBS", "items": []},
            {"id": "V1", "label": "V1 VIDEO", "items": []},
            {"id": "BG", "label": "BG STUDIO", "items": []},
            {"id": "A1", "label": "A1 AUDIO", "items": []},
        ]
        row_count = max(1, len(tracks))
        body_h = max(40, h - ruler_h - 8)
        row_h = body_h / row_count

        for idx, track in enumerate(tracks):
            y = ruler_h + 4 + idx * row_h
            tid = str(track.get("id") or f"T{idx}")
            label = str(track.get("label") or tid)
            base_hex = _TRACK_COLORS.get(tid, theme.ACCENT)

            if idx % 2 == 0:
                p.fillRect(QRectF(2, y, w - 4, row_h - 2), QColor("#16181F"))

            p.setPen(QColor(theme.LEGEND_DIM))
            p.setFont(theme.font(10, 700))
            p.drawText(QRectF(10, y, label_w - 14, row_h - 2), Qt.AlignmentFlag.AlignVCenter, label)

            p.setPen(QPen(QColor("#262934"), 1))
            p.drawLine(label_w - 2, int(y), label_w - 2, int(y + row_h - 2))

            for item in track.get("items") or []:
                s = max(0.0, float(item.get("start", 0.0)))
                e = max(s + 0.15, float(item.get("end", s + 1.0)))
                rx = plot_x + (min(s, dur) / dur) * plot_w
                rw = max(8.0, ((min(e, dur) - min(s, dur)) / dur) * plot_w - 2)
                rect = QRectF(rx, y + 3, rw, max(12.0, row_h - 8))

                fill = QColor(str(item.get("color") or base_hex))
                fill.setAlpha(185 if tid != "BG" else 115)
                border = QColor(str(item.get("color") or base_hex))

                path = QPainterPath()
                path.addRoundedRect(rect, 4, 4)
                p.fillPath(path, fill)
                p.setPen(QPen(border, 1))
                p.drawPath(path)

                if item.get("keyframes") and rw >= 24:
                    p.setBrush(QColor("#FFFFFF"))
                    for frac in (0.12, 0.5, 0.88):
                        kx = rect.left() + rect.width() * frac
                        ky = rect.bottom() - 4
                        diamond = QPainterPath()
                        diamond.moveTo(kx, ky - 3)
                        diamond.lineTo(kx + 3, ky)
                        diamond.lineTo(kx, ky + 3)
                        diamond.lineTo(kx - 3, ky)
                        diamond.closeSubpath()
                        p.drawPath(diamond)
                    p.setBrush(Qt.BrushStyle.NoBrush)

                if tid == "A1" and rw >= 16:
                    p.setPen(QPen(QColor("#0D3B2E"), 1.2))
                    bx = rect.left() + 4
                    mid_y = rect.center().y()
                    step_b = 4.0
                    k = 0
                    while bx < rect.right() - 4:
                        amp = 3 + ((k * 7) % 5)
                        p.drawLine(int(bx), int(mid_y - amp), int(bx), int(mid_y + amp))
                        bx += step_b
                        k += 1

                text = str(item.get("text") or "").strip()
                if text and rw >= 28:
                    p.setPen(QColor("#0F1117" if tid in ("V1", "A1", "V2") else "#FFFFFF"))
                    p.setFont(theme.font(10, 700))
                    p.drawText(
                        rect.adjusted(5, 0, -5, 0),
                        Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextSingleLine,
                        text[:32],
                    )

        v1_idx = next((i for i, t_row in enumerate(tracks) if t_row.get("id") == "V1"), 2)
        ty = ruler_h + 4 + v1_idx * row_h + row_h * 0.5
        for cut_t in self._transitions:
            tx = plot_x + (min(max(cut_t, 0.0), dur) / dur) * plot_w
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(QPen(QColor(theme.ACCENT), 1.5))
            p.drawEllipse(QRectF(tx - 5, ty - 5, 10, 10))
            p.setBrush(Qt.BrushStyle.NoBrush)

        px = plot_x + (min(self._playhead, dur) / dur) * plot_w
        p.setPen(QPen(QColor("#FFFFFF"), 2))
        p.drawLine(int(px), 4, int(px), h - 4)
        head = QPainterPath()
        head.moveTo(px - 5, 2)
        head.lineTo(px + 5, 2)
        head.lineTo(px, 11)
        head.closeSubpath()
        p.fillPath(head, QColor(theme.ACCENT))


class VideoStudioWindow(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self.setWindowTitle(tr("Ressy Studio · Live Editing"))
        self.setMinimumSize(880, 600)
        self.resize(980, 650)
        self.setStyleSheet(theme.stylesheet())
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self._output_mp4 = ""
        self._project_dir = ""
        self._editor_name = ""
        self._stage_labels: dict[str, QLabel] = {}
        self._stage_icons: dict[str, QLabel] = {}
        self._pulse_target = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(90)
        self._pulse_timer.timeout.connect(self._tick_playhead)

        badge = QLabel("LIVE STUDIO")
        badge.setStyleSheet(
            f"background: {theme.ACCENT}; color: {theme.INK}; font-weight: 800; "
            "font-size: 11px; padding: 3px 8px; border-radius: 5px;"
        )
        self.project_lbl = QLabel(tr("Nuovo progetto video"))
        self.project_lbl.setObjectName("title")
        self.project_lbl.setFont(theme.font(18, 700, 108))

        self.meta_lbl = QLabel("")
        self.meta_lbl.setObjectName("hint")

        self.status_pill = QLabel(tr("In preparazione"))
        self.status_pill.setStyleSheet(
            f"background: {theme.FIELD}; color: {theme.BACKLIGHT}; border: 1px solid {theme.FIELD_EDGE}; "
            "font-weight: 700; font-size: 12px; padding: 4px 10px; border-radius: 12px;"
        )

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(badge)
        header.addWidget(self.project_lbl)
        header.addWidget(self.meta_lbl)
        header.addStretch(1)
        header.addWidget(self.status_pill)

        monitor_frame = QFrame()
        monitor_frame.setStyleSheet(
            f"QFrame {{ background: #0D0E12; border: 1px solid {theme.PLATE_EDGE}; border-radius: 10px; }}"
        )
        monitor_box = QVBoxLayout(monitor_frame)
        monitor_box.setContentsMargins(12, 12, 12, 12)
        monitor_box.setSpacing(8)

        mon_top = QHBoxLayout()
        mon_title = QLabel(tr("ANTEPRIMA COMPOSITO LIVE"))
        mon_title.setStyleSheet(f"color: {theme.LEGEND_DIM}; font-size: 11px; font-weight: 700; border: none;")
        self.frame_tag = QLabel(tr("In attesa dei fotogrammi…"))
        self.frame_tag.setStyleSheet(f"color: {theme.LILAC}; font-size: 11px; font-weight: 600; border: none;")
        mon_top.addWidget(mon_title)
        mon_top.addStretch(1)
        mon_top.addWidget(self.frame_tag)

        self.preview_lbl = QLabel(tr("L'anteprima visiva comparirà qui durante il montaggio…"))
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setMinimumSize(320, 320)
        self.preview_lbl.setWordWrap(True)
        self.preview_lbl.setStyleSheet(
            f"background: #07080B; color: {theme.LEGEND_DIM}; border: 1px dashed {theme.PLATE_EDGE}; border-radius: 8px;"
        )

        self.ticker_lbl = QLabel(tr("Preparazione pipeline di montaggio…"))
        self.ticker_lbl.setWordWrap(True)
        self.ticker_lbl.setStyleSheet(f"color: {theme.LEGEND}; font-size: 13px; font-weight: 600; border: none;")

        monitor_box.addLayout(mon_top)
        monitor_box.addWidget(self.preview_lbl, 1)
        monitor_box.addWidget(self.ticker_lbl)

        pipe_frame = QFrame()
        pipe_frame.setStyleSheet(
            f"QFrame {{ background: {theme.FIELD}; border: 1px solid {theme.PLATE_EDGE}; border-radius: 10px; }}"
        )
        pipe_box = QVBoxLayout(pipe_frame)
        pipe_box.setContentsMargins(14, 12, 14, 12)
        pipe_box.setSpacing(7)

        pipe_title = QLabel(tr("OPERAZIONI DI EDITING"))
        pipe_title.setStyleSheet(f"color: {theme.LEGEND_DIM}; font-size: 11px; font-weight: 700; border: none;")
        pipe_box.addWidget(pipe_title)

        for key, label_text in _STAGES:
            row = QHBoxLayout()
            row.setSpacing(8)
            icon = QLabel("○")
            icon.setFixedWidth(18)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setStyleSheet(f"color: {theme.LEGEND_DIM}; font-weight: 700; border: none;")
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {theme.LEGEND_DIM}; font-size: 13px; border: none;")
            row.addWidget(icon)
            row.addWidget(lbl, 1)
            pipe_box.addLayout(row)
            self._stage_icons[key] = icon
            self._stage_labels[key] = lbl

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: #14151B; border: 1px solid {theme.PLATE_EDGE}; border-radius: 6px; "
            f"height: 18px; text-align: center; color: {theme.LEGEND}; font-size: 11px; font-weight: 700; }}"
            f"QProgressBar::chunk {{ background: {theme.ACCENT}; border-radius: 5px; }}"
        )
        pipe_box.addWidget(self.progress)

        log_title = QLabel(tr("REGISTRO STUDIO"))
        log_title.setStyleSheet(f"color: {theme.LEGEND_DIM}; font-size: 11px; font-weight: 700; border: none; padding-top: 4px;")
        pipe_box.addWidget(log_title)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(120)
        self.log_box.setStyleSheet(
            f"background: #121318; color: {theme.LEGEND}; border: 1px solid {theme.PLATE_EDGE}; "
            "border-radius: 6px; font-size: 12px; padding: 6px;"
        )
        pipe_box.addWidget(self.log_box, 1)

        mid = QHBoxLayout()
        mid.setSpacing(12)
        mid.addWidget(monitor_frame, 5)
        mid.addWidget(pipe_frame, 6)

        self.timeline = _TimelineCanvas(self)

        self.open_mp4_btn = QPushButton(tr("Apri video finale"))
        self.open_mp4_btn.setObjectName("primary")
        self.open_mp4_btn.setEnabled(False)
        self.open_mp4_btn.clicked.connect(lambda: _open_local_path(self._output_mp4))

        self.open_dir_btn = QPushButton(tr("Apri cartella progetto"))
        self.open_dir_btn.setEnabled(False)
        self.open_dir_btn.clicked.connect(lambda: _open_local_path(self._project_dir))

        self.close_btn = QPushButton(tr("Chiudi"))
        self.close_btn.clicked.connect(self.hide)

        actions = QHBoxLayout()
        actions.addWidget(self.open_mp4_btn)
        actions.addWidget(self.open_dir_btn)
        actions.addStretch(1)
        actions.addWidget(self.close_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        root.addLayout(header)
        root.addLayout(mid, 1)
        root.addWidget(self.timeline)
        root.addLayout(actions)
        style_title_bar(self)

    def _tick_playhead(self) -> None:
        cur = self.timeline._playhead
        if cur < self._pulse_target:
            self.timeline.set_playhead(min(self._pulse_target, cur + max(0.15, (self._pulse_target - cur) * 0.28)))
        else:
            self._pulse_timer.stop()

    def _set_stage_state(self, key: str, state: str) -> None:
        icon = self._stage_icons.get(key)
        lbl = self._stage_labels.get(key)
        if icon is None or lbl is None:
            return
        if state == "done":
            icon.setText("✓")
            icon.setStyleSheet(f"color: {theme.BACKLIGHT}; font-weight: 800; border: none;")
            lbl.setStyleSheet(f"color: {theme.LEGEND}; font-size: 13px; border: none;")
        elif state == "active":
            icon.setText("◉")
            icon.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 800; border: none;")
            lbl.setStyleSheet(f"color: #FFFFFF; font-size: 13px; font-weight: 700; border: none;")
        elif state == "error":
            icon.setText("✕")
            icon.setStyleSheet("color: #FF6B81; font-weight: 800; border: none;")
            lbl.setStyleSheet("color: #FF8C73; font-size: 13px; font-weight: 700; border: none;")
        else:
            icon.setText("○")
            icon.setStyleSheet(f"color: {theme.LEGEND_DIM}; font-weight: 700; border: none;")
            lbl.setStyleSheet(f"color: {theme.LEGEND_DIM}; font-size: 13px; border: none;")

    def _show_preview_image(self, image_path: str, caption: str = "") -> None:
        path = Path(image_path)
        if not path.is_file():
            return
        pix = QPixmap(str(path))
        if pix.isNull():
            return
        target = self.preview_lbl.size()
        w = max(280, target.width() - 8)
        h = max(240, target.height() - 8)
        scaled = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.preview_lbl.setPixmap(scaled)
        if caption:
            self.frame_tag.setText(caption)

    def _append_log(self, line: str) -> None:
        text = str(line or "").strip()
        if not text:
            return
        self.log_box.appendPlainText(f"• {text}")
        sb = self.log_box.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

    def apply_event(self, payload: dict[str, Any]) -> None:
        kind = str(payload.get("type") or "stage")
        if kind == "init":
            self._output_mp4 = ""
            self._project_dir = str(payload.get("project_dir") or "")
            self._editor_name = str(payload.get("editor") or "")
            self.open_mp4_btn.setEnabled(False)
            self.open_dir_btn.setEnabled(bool(self._project_dir))
            self.project_lbl.setText(str(payload.get("project_name") or tr("Nuovo progetto video")))
            meta_parts = [p for p in (self._editor_name, payload.get("style"), payload.get("aspect_ratio")) if p]
            self.meta_lbl.setText(" · ".join(str(p) for p in meta_parts))
            self.status_pill.setText(tr("Editing live"))
            self.status_pill.setStyleSheet(
                f"background: {theme.FIELD}; color: {theme.ACCENT}; border: 1px solid {theme.ACCENT}; "
                "font-weight: 700; font-size: 12px; padding: 4px 10px; border-radius: 12px;"
            )
            self.progress.setValue(4)
            self.log_box.clear()
            self.preview_lbl.clear()
            self.preview_lbl.setText(tr("Caricamento fotogrammi in corso…"))
            self.frame_tag.setText(tr("Analisi"))
            for key, _ in _STAGES:
                self._set_stage_state(key, "pending")
            self.timeline.set_data(
                duration=float(payload.get("duration") or 10.0),
                playhead=0.0,
                tracks=[],
                transitions=[],
            )
            self._append_log(str(payload.get("message") or tr("Avvio studio di montaggio…")))
            if payload.get("show", True):
                self.show()
                self.raise_()
                self.activateWindow()
            return

        if "progress" in payload and payload["progress"] is not None:
            self.progress.setValue(max(0, min(100, int(payload["progress"]))))
        if payload.get("message"):
            msg = str(payload["message"])
            self.ticker_lbl.setText(msg)
            self._append_log(msg)
        if payload.get("project_dir"):
            self._project_dir = str(payload["project_dir"])
            self.open_dir_btn.setEnabled(True)
        if payload.get("stage"):
            stage_key = str(payload["stage"])
            done_stages = set(payload.get("done_stages") or [])
            for k, _ in _STAGES:
                if k in done_stages:
                    self._set_stage_state(k, "done")
                elif k == stage_key:
                    self._set_stage_state(k, "error" if kind == "error" else "active")
        if payload.get("preview_path"):
            self._show_preview_image(str(payload["preview_path"]), str(payload.get("preview_label") or ""))
        if any(k in payload for k in ("tracks", "duration", "transitions")):
            self.timeline.set_data(
                duration=payload.get("duration"),
                tracks=payload.get("tracks"),
                transitions=payload.get("transitions"),
            )
        if payload.get("playhead") is not None:
            self._pulse_target = float(payload["playhead"])
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()

        if kind == "done":
            for k, _ in _STAGES:
                self._set_stage_state(k, "done")
            self.progress.setValue(100)
            self.status_pill.setText(tr("Completato"))
            self.status_pill.setStyleSheet(
                f"background: {theme.FIELD}; color: {theme.BACKLIGHT}; border: 1px solid {theme.BACKLIGHT}; "
                "font-weight: 700; font-size: 12px; padding: 4px 10px; border-radius: 12px;"
            )
            if payload.get("output_mp4"):
                self._output_mp4 = str(payload["output_mp4"])
                self.open_mp4_btn.setEnabled(True)
            if payload.get("project_dir"):
                self._project_dir = str(payload["project_dir"])
                self.open_dir_btn.setEnabled(True)
        elif kind == "error":
            self.status_pill.setText(tr("Errore"))
            self.status_pill.setStyleSheet(
                "background: #2C161B; color: #FF8C73; border: 1px solid #FF6B81; "
                "font-weight: 700; font-size: 12px; padding: 4px 10px; border-radius: 12px;"
            )
