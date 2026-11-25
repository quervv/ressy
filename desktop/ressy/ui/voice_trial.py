from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from . import theme

log = logging.getLogger("ressy.trial")

RATE = 16000


@dataclass
class Trial:
    key: str
    say: str
    help: str


TRIALS = [
    Trial("wake", "Ressy, sveglia!", "Così la svegli: tieni premuto K e dillo."),
    Trial("weather", "Che meteo c'è?", "Ressy capisce la domanda e legge il meteo."),
    Trial("site", "Apri time.is sul browser", "Ressy apre davvero il sito nel browser."),
]


class _Relay(QObject):
    level = Signal(float)
    result = Signal(str, bool, str, str)
    ready = Signal(str)
    switched = Signal(str)


class _Check(QWidget):

    def __init__(self, number: int) -> None:
        super().__init__()
        self.number = number
        self.state = "todo"
        self.setFixedSize(QSize(30, 30))

    def set_state(self, state: str) -> None:
        self.state = state
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, 28, 28)
        ok, current = self.state == "ok", self.state in ("current", "busy", "fail")
        p.setPen(QPen(QColor(theme.ACCENT if (ok or current) else theme.FIELD_EDGE), 1.4))
        p.setBrush(QColor(theme.ACCENT if ok else ("#2F2548" if current else theme.FIELD)))
        p.drawRoundedRect(r, 8, 8)
        if ok:
            path = QPainterPath()
            path.moveTo(r.left() + 8.5, r.center().y() + 0.5)
            path.lineTo(r.left() + 12.5, r.bottom() - 9)
            path.lineTo(r.right() - 8, r.top() + 9.5)
            p.setPen(QPen(QColor(theme.INK), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        else:
            p.setFont(theme.font(13, 800))
            p.setPen(QColor(theme.LILAC if current else theme.LEGEND_DIM))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "…" if self.state == "busy" else str(self.number))
        p.end()


class TalkButton(QPushButton):

    held = Signal(bool)

    def __init__(self) -> None:
        super().__init__("Tieni premuto e parla")
        self.setObjectName("primary")
        self.setMinimumHeight(52)
        self.setMinimumWidth(260)
        self.setFont(theme.font(15, 700, 106))
        self.pressed.connect(lambda: self.held.emit(True))
        self.released.connect(lambda: self.held.emit(False))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.setDown(True)
            self.held.emit(True)
            return
        if event.key() == Qt.Key.Key_Space:
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.setDown(False)
            self.held.emit(False)
            return
        if event.key() == Qt.Key.Key_Space:
            return
        super().keyReleaseEvent(event)


class VoiceTrial(QWidget):

    completed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings: Any = None
        self.passed: set[str] = set()
        self.no_microphone = False
        self._index = 0
        self._busy = False
        self._recording = False
        self._frames: list[Any] = []
        self._mic: Any = None
        self._stt: Any = None
        self._lock = threading.Lock()
        self.relay = _Relay()
        self.relay.level.connect(self._on_level)
        self.relay.result.connect(self._on_result)
        self.relay.ready.connect(self._on_ready)
        self.relay.switched.connect(self._on_switched)

        self.rows: dict[str, tuple[_Check, QLabel, QLabel]] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for number, trial in enumerate(TRIALS, start=1):
            row = QWidget()
            row.setObjectName("trialRow")
            row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            row.setStyleSheet(
                f"QWidget#trialRow {{ background: {theme.MODS}; border: 1px solid #383A42;"
                f" border-bottom: 3px solid {theme.MODS_SKIRT}; border-radius: 10px; }}"
            )
            h = QHBoxLayout(row)
            h.setContentsMargins(14, 12, 14, 12)
            h.setSpacing(14)
            check = _Check(number)
            h.addWidget(check, 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(3)
            say = QLabel(f"Di' «<b>{trial.say}</b>»")
            say.setFont(theme.font(15, 500))
            say.setStyleSheet("background: transparent; border: none;")
            detail = QLabel(trial.help)
            detail.setObjectName("hint")
            detail.setWordWrap(True)
            detail.setTextFormat(Qt.TextFormat.RichText)
            detail.setStyleSheet("background: transparent; border: none;")
            col.addWidget(say)
            col.addWidget(detail)
            h.addLayout(col, 1)
            layout.addWidget(row)
            self.rows[trial.key] = (check, say, detail)

        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        self.talk = TalkButton()
        self.talk.held.connect(self._hold)
        self.talk.setEnabled(False)
        right = QVBoxLayout()
        right.setSpacing(8)
        mic_row = QHBoxLayout()
        mic_row.setSpacing(10)
        mic_label = QLabel("Microfono")
        mic_label.setObjectName("hint")
        self.mic_choice = QComboBox()
        self.mic_choice.setMinimumWidth(260)
        self.mic_choice.currentIndexChanged.connect(self._on_mic_chosen)
        mic_row.addWidget(mic_label)
        mic_row.addWidget(self.mic_choice, 1)
        right.addLayout(mic_row)
        self.status = QLabel("Preparo il microfono e il modello…")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        self.meter = QProgressBar()
        self.meter.setRange(0, 1000)
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(8)
        right.addWidget(self.status)
        right.addWidget(self.meter)
        bottom.addWidget(self.talk)
        bottom.addLayout(right, 1)
        layout.addSpacing(6)
        layout.addLayout(bottom)

    def start(self, settings: Any) -> None:
        self.settings = settings
        self.passed.clear()
        self.no_microphone = False
        self._index = 0
        for key, (check, _, detail) in self.rows.items():
            check.set_state("todo")
            detail.setText(next(t.help for t in TRIALS if t.key == key))
        self._mark_current()
        self.talk.setEnabled(False)
        self.status.setText("Preparo il microfono e il modello…")
        self._fill_mics(getattr(settings, "mic_device", ""))
        threading.Thread(target=self._prepare, name="ressy-trial-prepare", daemon=True).start()

    @property
    def mic_device(self) -> str:
        return str(self.mic_choice.currentData() or "")

    def _fill_mics(self, selected: str) -> None:
        from ..audio import devices

        self.mic_choice.blockSignals(True)
        self.mic_choice.clear()
        self.mic_choice.addItem("Predefinito di Windows", "")
        for name in devices.input_devices():
            if "mapper" not in name.lower():
                self.mic_choice.addItem(name, name)
        index = self.mic_choice.findData(selected)
        self.mic_choice.setCurrentIndex(max(0, index))
        self.mic_choice.blockSignals(False)

    def _on_mic_chosen(self, _index: int) -> None:
        if self.settings is None:
            return
        self.settings.mic_device = self.mic_device
        if self._mic is None:
            return
        self.stop()
        self.status.setText("Cambio microfono…")
        threading.Thread(target=self._reopen_mic, name="ressy-trial-mic", daemon=True).start()

    def _reopen_mic(self) -> None:
        from ..audio.mic import MicError

        try:
            self._open_mic()
        except MicError as exc:
            self.relay.ready.emit(f"mic:{exc}")
            return
        self.relay.ready.emit("")

    def _open_mic(self) -> None:
        from ..audio.mic import Microphone

        mic = Microphone(lambda: getattr(self.settings, "mic_device", ""))
        mic.on_switch = self.relay.switched.emit
        mic.start(self._on_frame)
        self._mic = mic

    def _on_switched(self, name: str) -> None:
        self.mic_choice.blockSignals(True)
        index = self.mic_choice.findData(name)
        if index < 0:
            self.mic_choice.addItem(name, name)
            index = self.mic_choice.count() - 1
        self.mic_choice.setCurrentIndex(index)
        self.mic_choice.blockSignals(False)
        if self.settings is not None:
            self.settings.mic_device = name
        self.status.setText(
            f"Il microfono predefinito di Windows non manda suono: uso «{name}». "
            "Puoi sceglierne un altro qui sopra."
        )

    def stop(self) -> None:
        mic, self._mic = self._mic, None
        if mic is not None:
            try:
                mic.stop()
            except Exception:
                log.debug("mic stop failed", exc_info=True)

    def _prepare(self) -> None:
        try:
            from ..audio.mic import MicError
            from ..speech.stt import SpeechToText

            self._stt = SpeechToText(self.settings, None, vocabulary=lambda: ["Ressy", "time.is"])
            self._stt.preload()
            try:
                self._open_mic()
            except MicError as exc:
                self.relay.ready.emit(f"mic:{exc}")
                return
            self.relay.ready.emit("")
        except Exception as exc:
            log.warning("trial setup failed", exc_info=True)
            self.relay.ready.emit(str(exc) or type(exc).__name__)

    def _on_ready(self, error: str) -> None:
        if error.startswith("mic:"):
            self.no_microphone = True
            self.status.setText(
                f"<span style='color:#FF8C73'>Non trovo un microfono</span> ({error[4:]}). "
                "Collegane uno e riapri l'installazione, oppure vai avanti e prova dopo."
            )
            self.completed.emit(False)
            return
        if error:
            self.status.setText(f"<span style='color:#FF8C73'>Non riesco a preparare la prova</span>: {error}")
            return
        self.talk.setEnabled(True)
        self.talk.setFocus()
        self.status.setText("Tieni premuto il pulsante (o la barra spaziatrice), parla, poi lascia.")

    def _on_frame(self, frame: Any, db: float) -> None:
        if self._recording:
            with self._lock:
                self._frames.append(frame.copy())
        self.relay.level.emit(max(0.0, min(1.0, (db + 60) / 50)))

    def _on_level(self, value: float) -> None:
        self.meter.setValue(int(value * 1000))

    def _hold(self, down: bool) -> None:
        if self._busy or self._index >= len(TRIALS):
            return
        if down:
            with self._lock:
                self._frames = []
            self._recording = True
            self._started = time.monotonic()
            self.status.setText("Ti ascolto… lascia quando hai finito.")
            return
        if not self._recording:
            return
        self._recording = False
        with self._lock:
            frames, self._frames = self._frames, []
        if self._mic is None:
            return
        if time.monotonic() - self._started < 0.4 or not frames:
            self.status.setText("Tieni premuto mentre parli, poi lascia.")
            return
        self._busy = True
        self.talk.setEnabled(False)
        trial = TRIALS[self._index]
        self.rows[trial.key][0].set_state("busy")
        self.status.setText("Ci penso…")
        threading.Thread(target=self._run, args=(trial, frames), name="ressy-trial", daemon=True).start()

    def _run(self, trial: Trial, frames: list[Any]) -> None:
        import numpy as np

        pcm = np.concatenate(frames).astype(np.int16)
        try:
            ok, heard, detail = asyncio.run(self._evaluate(trial, pcm))
        except Exception as exc:
            log.warning("trial failed", exc_info=True)
            ok, heard, detail = False, "", _error_text(exc)
        self.relay.result.emit(trial.key, ok, heard, detail)

    async def _evaluate(self, trial: Trial, pcm: Any) -> tuple[bool, str, str]:
        from ..brain.providers import LLMRouter

        llm = LLMRouter(self.settings)
        self._stt.llm = llm
        try:
            transcript = await self._stt.transcribe_pcm(pcm, RATE, lenient=trial.key == "wake")
            heard = transcript.text
            if not heard:
                return False, "", "Non ho sentito parole: avvicinati al microfono e riprova."
            if trial.key == "wake":
                from ..speech.wake import loose_wake, match_wake

                ok = match_wake(heard, self.settings.wake_phrases).matched or loose_wake(heard).matched
                return ok, heard, "" if ok else "Non era la frase di risveglio: riprova."
            brain = _trial_brain(self.settings, llm)
            from ..tools.registry import Channel

            result = await asyncio.wait_for(brain.respond(heard, Channel("voice")), timeout=45)
            wanted = "weather" if trial.key == "weather" else "open_url"
            ok = any(p.startswith(f"{wanted}:") for p in result.performed)
            return ok, heard, result.text if ok else (result.text or "Non ho capito cosa fare: riprova.")
        finally:
            await llm.aclose()

    def _on_result(self, key: str, ok: bool, heard: str, detail: str) -> None:
        self._busy = False
        check, _, label = self.rows[key]
        heard_html = f"Ho sentito «{heard}». " if heard else ""
        if ok:
            self.passed.add(key)
            check.set_state("ok")
            label.setText(f"<span style='color:{theme.BACKLIGHT}'>{heard_html}</span>{detail}")
            self._index += 1
            self._mark_current()
        else:
            check.set_state("fail")
            label.setText(f"{heard_html}<span style='color:#FF8C73'>{detail}</span>")
        if self._index >= len(TRIALS):
            self.talk.setEnabled(False)
            self.status.setText(f"<span style='color:{theme.BACKLIGHT}'>Tutto a posto</span>: Ressy ti sente e ti capisce.")
            self.stop()
            self.completed.emit(True)
            return
        self.talk.setEnabled(True)
        self.talk.setFocus()
        self.status.setText("Tieni premuto il pulsante (o la barra spaziatrice), parla, poi lascia.")

    def _mark_current(self) -> None:
        for number, trial in enumerate(TRIALS):
            check = self.rows[trial.key][0]
            if trial.key in self.passed:
                check.set_state("ok")
            elif number == self._index:
                check.set_state("current")
            else:
                check.set_state("todo")


def _trial_brain(settings: Any, llm: Any) -> Any:
    from ..brain.agent import Brain
    from ..core.services import Services
    from ..tools import more, web
    from ..tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.extend([t for t in [*more.TOOLS, *web.TOOLS] if t.name in ("weather", "open_url")])
    return Brain(settings, llm, registry, Services(settings, llm, None, None))


def settings_for_trial(base: Any, changes: dict[str, Any]) -> Any:
    import copy

    trial = copy.copy(base)
    for key, value in changes.items():
        setattr(trial, key, value)
    trial.save = lambda: None
    return trial


def _error_text(exc: BaseException) -> str:
    from ..brain.groq import GroqAuthError, GroqError, GroqRateLimited, GroqUnavailable

    name = getattr(exc, "provider", "") or "il provider"
    if isinstance(exc, GroqError) and name == "PC":
        return str(exc)
    if isinstance(exc, GroqAuthError):
        return f"La chiave di {name} non è valida: torna indietro e controllala."
    if isinstance(exc, GroqRateLimited):
        return str(exc)
    if isinstance(exc, GroqUnavailable):
        return f"Non riesco a raggiungere {name}: controlla la connessione."
    if isinstance(exc, asyncio.TimeoutError):
        return "Ci ho messo troppo: riprova."
    return f"Qualcosa non è andato ({type(exc).__name__}): riprova."
