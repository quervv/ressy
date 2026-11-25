from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import CLAUDE_MODELS, LOCAL_STT_MODELS, PROVIDER_NAMES
from ..paths import resource_path
from . import theme

PROVIDERS: dict[str, dict[str, Any]] = {
    "groq": {
        "tagline": "Velocissimo. Piano gratuito, con limiti al minuto.",
        "badge": "Gratis",
        "placeholder": "gsk_…",
        "url": "https://console.groq.com/keys",
        "site": "console.groq.com",
        "models": [
            ("openai/gpt-oss-120b", "GPT-OSS 120B (consigliato)"),
            ("openai/gpt-oss-20b", "GPT-OSS 20B (più veloce)"),
            ("qwen/qwen3.8-27b", "Qwen 3.8 27B"),
        ],
    },
    "gemini": {
        "tagline": "Di Google. Piano gratuito generoso, capisce anche la voce.",
        "badge": "Gratis",
        "placeholder": "AIza…",
        "url": "https://aistudio.google.com/apikey",
        "site": "aistudio.google.com",
        "models": [
            ("gemini-2.5-flash", "Gemini 2.5 Flash (consigliato)"),
            ("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite (più veloce)"),
            ("gemini-2.5-pro", "Gemini 2.5 Pro (più capace, più lento)"),
        ],
    },
    "openrouter": {
        "tagline": "Una chiave, tanti modelli gratuiti. Ottima come riserva.",
        "badge": "Gratis",
        "placeholder": "sk-or-v1-…",
        "url": "https://openrouter.ai/settings/keys",
        "site": "openrouter.ai",
        "models": [("auto", "Il miglior modello gratis del giorno (automatico)")],
    },
    "claude": {
        "tagline": "Il più bravo a usare il PC. A consumo, con la tua carta.",
        "badge": "Il più capace",
        "placeholder": "sk-ant-…",
        "url": "https://console.anthropic.com/settings/keys",
        "site": "console.anthropic.com",
        "models": list(CLAUDE_MODELS.items()),
    },
}

SPEECH_OPTIONS = {
    "local": ("Sul PC", "Gratis e senza limiti. Funziona anche offline.", "Consigliato", "pc"),
    "groq": ("Groq", "Whisper online, il più preciso. Usa la chiave Groq.", "", "groq"),
    "gemini": ("Gemini", "Online, con la chiave Gemini.", "", "gemini"),
}
LOCAL_DETAILS = {
    "tiny-q5_1": "Il più rapido, sbaglia di più",
    "base-q5_1": "Buon equilibrio, consigliato",
    "small-q5_1": "Capisce meglio, più lento",
}

_renderers: dict[str, QSvgRenderer] = {}


def logo_renderer(name: str) -> QSvgRenderer | None:
    if name not in _renderers:
        path = resource_path(f"assets/providers/{name}.svg")
        renderer = QSvgRenderer(str(path)) if path.exists() else None
        if renderer is None or not renderer.isValid():
            return None
        _renderers[name] = renderer
    return _renderers[name]


def _link(text: str, url: str) -> str:
    return f'<a href="{url}" style="color:{theme.LILAC};">{text}</a>'


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    return label


class ChoiceCard(QAbstractButton):

    def __init__(self, key: str, title: str, text: str, *, logo: str = "", badge: str = "",
                 compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.title = title
        self.text_ = text
        self.logo = logo
        self.badge = badge
        self.compact = compact
        self.status = ""
        self.status_ok = False
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"{title}. {text}")
        self.setMinimumSize(QSize(150, 92 if compact else 128))
        self._hover = False

    def sizeHint(self) -> QSize:
        return QSize(190, 96 if self.compact else 136)

    def set_status(self, text: str, ok: bool = False) -> None:
        self.status, self.status_ok = text, ok
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -4.5)
        radius = 12.0
        skirt = QRectF(rect).translated(0, 1.5 if on else 3.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.ACCENT_SKIRT if on else theme.MODS_SKIRT))
        p.drawRoundedRect(skirt, radius, radius)
        top = QRectF(rect).translated(0, 1.5 if on else 0)
        grad = QLinearGradient(top.topLeft(), top.bottomLeft())
        if on:
            grad.setColorAt(0, QColor("#2F2548"))
            grad.setColorAt(1, QColor("#221D31"))
        else:
            base = QColor("#2C2E36" if self._hover else theme.MODS)
            grad.setColorAt(0, base.lighter(108))
            grad.setColorAt(1, base)
        p.setBrush(grad)
        p.setPen(QPen(QColor(theme.ACCENT if on else ("#474A55" if self._hover else "#383A42")), 1.6 if on else 1.0))
        p.drawRoundedRect(top, radius, radius)
        if self.hasFocus():
            p.setPen(QPen(QColor(theme.LEGEND), 1.4, Qt.PenStyle.DotLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(top.adjusted(3, 3, -3, -3), radius - 3, radius - 3)

        pad = 12.0 if self.compact else 14.0
        x, y = top.left() + pad, top.top() + pad
        if self.logo:
            tile = QRectF(x, y, 34, 34)
            p.setPen(QPen(QColor("#3A3D46"), 1))
            p.setBrush(QColor(theme.PLATE))
            p.drawRoundedRect(tile, 9, 9)
            renderer = logo_renderer(self.logo)
            if renderer is not None:
                renderer.render(p, tile.adjusted(7, 7, -7, -7))
            text_x = tile.right() + 11
        else:
            text_x = x
        dot = QRectF(top.right() - pad - 18, y + (8 if self.logo else 0), 18, 18)
        p.setPen(QPen(QColor(theme.ACCENT if on else "#4A4D58"), 1.4))
        p.setBrush(QColor(theme.ACCENT if on else theme.PLATE))
        p.drawEllipse(dot)
        if on:
            path = QPainterPath()
            path.moveTo(dot.left() + 5, dot.center().y() + 0.5)
            path.lineTo(dot.left() + 8, dot.bottom() - 5)
            path.lineTo(dot.right() - 4.5, dot.top() + 5.5)
            p.setPen(QPen(QColor(theme.INK), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        p.setPen(QColor(theme.LEGEND))
        title_font = theme.font(15 if self.compact else 16, 700, 108)
        p.setFont(title_font)
        title_h = 20
        title_y = y + (7 if self.logo else 0)
        title_w = p.fontMetrics().horizontalAdvance(self.title)
        p.drawText(QRectF(text_x, title_y, dot.left() - text_x - 6, title_h),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)
        inline_badge = self.compact and self.badge
        if self.badge:
            p.setFont(theme.font(10.5, 700, 104))
            fm = p.fontMetrics()
            bw = fm.horizontalAdvance(self.badge) + 14
            if inline_badge:
                pill = QRectF(text_x + title_w + 8, title_y + 1, bw, 18)
                if pill.right() > dot.left() - 4:
                    pill.moveLeft(dot.left() - 4 - bw)
            else:
                pill = QRectF(x, (y + 34 + 10) if self.logo else (title_y + title_h + 6), bw, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.BACKLIGHT if self.badge == "Gratis" else theme.LILAC).darker(100))
            p.setOpacity(0.16)
            p.drawRoundedRect(pill, 9, 9)
            p.setOpacity(1.0)
            p.setPen(QColor(theme.BACKLIGHT if self.badge == "Gratis" else theme.LILAC))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, self.badge)
            body_y = (title_y + title_h + 4) if inline_badge else pill.bottom() + 7
        else:
            body_y = (y + 34 + 10) if self.logo else (title_y + title_h + 4)
        p.setPen(QColor(theme.LEGEND_DIM))
        body_font = theme.font(12.5, 400)
        p.setFont(body_font)
        bottom = top.bottom() - pad - (16 if self.status else 0)
        p.drawText(QRectF(x, body_y, top.width() - 2 * pad, max(14.0, bottom - body_y)),
                   Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self.text_)
        if self.status:
            f = theme.font(11.5, 600)
            p.setFont(f)
            p.setPen(QColor(theme.BACKLIGHT if self.status_ok else theme.LEGEND_DIM))
            p.drawText(QRectF(x, top.bottom() - pad - 14, top.width() - 2 * pad, 16),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.status)
        p.end()


class CardRow(QWidget):

    changed = Signal(str)

    def __init__(self, cards: list[ChoiceCard], columns: int | None = None) -> None:
        super().__init__()
        self.cards = {card.key: card for card in cards}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        columns = columns or len(cards)
        for index, card in enumerate(cards):
            self.group.addButton(card)
            grid.addWidget(card, index // columns, index % columns)
            card.toggled.connect(lambda on, k=card.key: on and self.changed.emit(k))

    def value(self) -> str:
        for key, card in self.cards.items():
            if card.isChecked():
                return key
        return next(iter(self.cards))

    def set_value(self, key: str) -> None:
        card = self.cards.get(key) or next(iter(self.cards.values()))
        card.setChecked(True)


class _Relay(QObject):

    verified = Signal(str, str, object, object)
    progress = Signal(str, int, int)
    downloaded = Signal(str, str)


class BrainSetup(QWidget):

    validity = Signal(bool)

    def __init__(self, parent: QWidget | None = None, *, auto_verify: bool = False) -> None:
        super().__init__(parent)
        self.auto_verify = auto_verify
        self.keys = {name: "" for name in PROVIDERS}
        self.models = {name: "" for name in PROVIDERS}
        self._available: dict[str, list[str] | None] = {name: None for name in PROVIDERS}
        self._current = "groq"
        self._checking: tuple[str, str] | None = None
        self._loading = False
        self._verified: dict[str, str] = {}
        self.relay = _Relay()
        self.relay.verified.connect(self._on_verified)

        cards = [
            ChoiceCard(name, PROVIDER_NAMES[name], info["tagline"], logo=name, badge=info["badge"])
            for name, info in PROVIDERS.items()
        ]
        self.cards = CardRow(cards, columns=2)
        self.cards.changed.connect(self._switch)

        self.key_hint = _hint("")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.textEdited.connect(self._key_edited)
        show = QPushButton("Mostra")
        show.setCheckable(True)
        show.toggled.connect(lambda on: (
            self.key.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password),
            show.setText("Nascondi" if on else "Mostra"),
        ))
        self.verify_button = QPushButton("Verifica")
        self.verify_button.clicked.connect(self.verify)
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_row.addWidget(self.key, 1)
        key_row.addWidget(show)
        key_row.addWidget(self.verify_button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.model = QComboBox()
        self.model.currentIndexChanged.connect(self._model_changed)

        form = QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.key_label = QLabel("Chiave API")
        form.addWidget(self.key_label, 0, 0)
        form.addLayout(key_row, 0, 1)
        form.addWidget(self.status, 1, 1)
        form.addWidget(QLabel("Modello"), 2, 0)
        form.addWidget(self.model, 2, 1)
        form.setColumnStretch(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self.cards)
        layout.addWidget(self.key_hint)
        layout.addLayout(form)
        layout.addWidget(_hint(
            "Puoi inserire <b>più chiavi</b>: scegli una scheda, incolla la chiave, poi torna su quella che vuoi "
            "usare. Se la prima arriva al limite, Ressy continua con le altre, così resta sempre gratis."
        ))

    def load(self, provider: str, keys: dict[str, str], models: dict[str, str]) -> None:
        self.keys.update({k: v or "" for k, v in keys.items()})
        self.models.update({k: v or "" for k, v in models.items()})
        self._current = provider
        self._loading = True
        try:
            self.cards.set_value(provider)
        finally:
            self._loading = False
        self._show(provider)
        self._mark_keys()
        self.validity.emit(self.is_verified())
        if self.auto_verify:
            self.verify_if_needed()

    def provider(self) -> str:
        return self.cards.value()

    def values(self) -> dict[str, Any]:
        self._remember()
        return {
            "llm_provider": self.provider(),
            "groq_api_key": self.keys["groq"].strip(),
            "anthropic_api_key": self.keys["claude"].strip(),
            "gemini_api_key": self.keys["gemini"].strip(),
            "llm_model": self.models["groq"] or PROVIDERS["groq"]["models"][0][0],
            "claude_model": self.models["claude"] or PROVIDERS["claude"]["models"][0][0],
            "gemini_model": self.models["gemini"] or PROVIDERS["gemini"]["models"][0][0],
            "openrouter_api_key": self.keys["openrouter"].strip(),
            "openrouter_model": "" if self.models["openrouter"] in ("", "auto") else self.models["openrouter"],
        }

    def problem(self) -> str:
        self._remember()
        provider = self.provider()
        if not self.keys[provider].strip():
            return f"Incolla la chiave API di {PROVIDER_NAMES[provider]} (è gratis crearla)."
        return ""

    def focus_key(self) -> None:
        self.key.setFocus()

    def is_verified(self) -> bool:
        provider = self.provider()
        key = (self.keys.get(provider) or "").strip()
        return bool(key) and self._verified.get(provider) == key

    def verify_if_needed(self) -> None:
        self._remember()
        if self.keys[self.provider()].strip() and not self.is_verified() and self._checking is None:
            self.verify()

    def _remember(self) -> None:
        self.keys[self._current] = self.key.text().strip()
        if self.model.currentData():
            self.models[self._current] = self.model.currentData()
        self._mark_keys()

    def _mark_keys(self) -> None:
        for name, card in self.cards.cards.items():
            has = bool((self.keys.get(name) or "").strip())
            status = "Chiave inserita" if has else ""
            if card.status != status:
                card.status, card.status_ok = status, has
                card.update()

    def _switch(self, provider: str) -> None:
        if self._loading:
            return
        self._remember()
        self._current = provider
        self._show(provider)
        self.validity.emit(self.is_verified())
        if self.auto_verify:
            self.verify_if_needed()

    def _show(self, provider: str) -> None:
        info = PROVIDERS[provider]
        name = PROVIDER_NAMES[provider]
        self.key_label.setText(f"Chiave {name}")
        self.key.setPlaceholderText(info["placeholder"])
        self.key.setText(self.keys[provider])
        self.key_hint.setText(
            f"Ressy pensa con {name} usando la <b>tua</b> chiave: resta su questo PC, cifrata da Windows. "
            + _link(f"Crea una chiave su {info['site']}", info["url"])
        )
        self._set_status("", "")
        self._fill_models(provider)

    def _fill_models(self, provider: str) -> None:
        current = self.models.get(provider) or ""
        available = self._available.get(provider)
        items = list(PROVIDERS[provider]["models"])
        if available is not None:
            known = {v for v, _ in items}
            items = [(v, label) for v, label in items if v in available] or items
            if provider == "gemini":
                items += [(m, m) for m in available if m not in known and ("flash" in m or "pro" in m)
                          and "preview" not in m and "exp" not in m][:6]
            if provider == "openrouter":
                items = [items[0]] + [(m, m.removesuffix(":free")) for m in available][:12]
        self.model.blockSignals(True)
        self.model.clear()
        for value, label in items:
            self.model.addItem(label, value)
        index = self.model.findData(current)
        if index < 0 and current:
            self.model.addItem(current, current)
            index = self.model.count() - 1
        self.model.setCurrentIndex(max(0, index))
        self.model.blockSignals(False)
        self.models[provider] = self.model.currentData() or ""

    def _model_changed(self) -> None:
        if self.model.currentData():
            self.models[self._current] = self.model.currentData()

    def _key_edited(self) -> None:
        self.keys[self._current] = self.key.text().strip()
        self._mark_keys()
        self._set_status("", "")
        self.validity.emit(self.is_verified())

    def _set_status(self, kind: str, text: str) -> None:
        self.status.setObjectName(kind or "hint")
        self.status.setText(text)
        self.status.setVisible(bool(text))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def verify(self) -> None:
        provider = self.provider()
        key = self.key.text().strip()
        if not key:
            self._set_status("error", "Incolla prima la chiave.")
            return
        self.verify_button.setEnabled(False)
        self._set_status("hint", f"Verifico la chiave con {PROVIDER_NAMES[provider]}…")
        self._checking = (provider, key)

        def work() -> None:
            from ..brain.providers import verify_key_blocking

            try:
                self.relay.verified.emit(provider, key, verify_key_blocking(provider, key), None)
            except Exception as exc:
                self.relay.verified.emit(provider, key, None, exc)

        threading.Thread(target=work, name="ressy-verify", daemon=True).start()

    def _on_verified(self, provider: str, key: str, models: object, error: object) -> None:
        if self._checking != (provider, key):
            return
        self._checking = None
        self.verify_button.setEnabled(True)
        if provider != self.provider():
            return
        name = PROVIDER_NAMES[provider]
        if error is not None:
            from ..brain.groq import GroqAuthError

            if isinstance(error, GroqAuthError):
                self._set_status("error", f"{name} ha rifiutato questa chiave: controlla di averla copiata tutta.")
            else:
                self._set_status("error", f"Non riesco a raggiungere {name} ora: controlla la connessione e riprova.")
            return
        self._available[provider] = list(models or [])
        self._verified[provider] = key
        self._set_status("ok", "Chiave valida.")
        self._fill_models(provider)
        self.validity.emit(self.is_verified())


class SpeechSetup(QWidget):

    readiness = Signal(bool)

    def __init__(self, *, download_now: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from ..speech import local_stt

        self._local = local_stt
        self.download_now = download_now
        self._cancel: threading.Event | None = None
        self._downloading = ""
        self.keys: dict[str, str] = {}
        self.relay = _Relay()
        self.relay.progress.connect(self._on_progress)
        self.relay.downloaded.connect(self._on_downloaded)

        engines = [ChoiceCard(key, title, text, logo=logo, badge=badge)
                   for key, (title, text, badge, logo) in SPEECH_OPTIONS.items()]
        self.engines = CardRow(engines)
        self.engines.changed.connect(self._engine_changed)

        sizes = [ChoiceCard(name, f"{label} · {mb} MB", LOCAL_DETAILS.get(name, ""), compact=True,
                            badge="")
                 for name, (label, mb) in LOCAL_STT_MODELS.items()]
        self.sizes = CardRow(sizes)
        self.sizes.changed.connect(lambda _: self._refresh())

        self.local_box = QWidget()
        lv = QVBoxLayout(self.local_box)
        lv.setContentsMargins(0, 4, 0, 0)
        lv.setSpacing(10)
        lv.addWidget(_hint(
            "Il modello si scarica una volta sola dentro la cartella di Ressy; poi la voce non esce dal PC."
        ))
        lv.addWidget(self.sizes)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.download_button = QPushButton("Scarica")
        self.download_button.setObjectName("primary")
        self.download_button.clicked.connect(self._download_clicked)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.download_status = QLabel()
        self.download_status.setObjectName("hint")
        row.addWidget(self.download_button)
        col = QVBoxLayout()
        col.setSpacing(6)
        col.addWidget(self.download_status)
        col.addWidget(self.bar)
        row.addLayout(col, 1)
        lv.addLayout(row)

        self.online_hint = _hint("")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.engines)
        layout.addWidget(self.local_box)
        layout.addWidget(self.online_hint)

    def load(self, engine: str, local_model: str) -> None:
        self.engines.set_value(engine)
        self.sizes.set_value(local_model)
        self._engine_changed(self.engines.value())

    def values(self) -> dict[str, Any]:
        return {"stt_engine": self.engines.value(), "local_stt_model": self.sizes.value()}

    def is_ready(self) -> bool:
        engine = self.engines.value()
        if engine == "local":
            return not self._downloading and not self.needs_download()
        return bool((self.keys.get(engine) or "").strip())

    def needs_download(self) -> bool:
        return self.engines.value() == "local" and not self._local.is_downloaded(self.sizes.value())

    def problem(self, keys: dict[str, str] | None = None) -> str:
        engine = self.engines.value()
        if engine == "local":
            if self._downloading:
                return "Aspetta che finisca il download del modello vocale."
            if self.download_now and self.needs_download():
                return "Scarica il modello vocale (pulsante «Scarica»), oppure scegli di capire la voce online."
            return ""
        if keys is not None and not (keys.get(engine) or "").strip():
            return f"Per capire la voce con {PROVIDER_NAMES[engine]} serve anche la sua chiave (pagina Intelligenza)."
        return ""

    def _engine_changed(self, engine: str) -> None:
        self.local_box.setVisible(engine == "local")
        texts = {
            "groq": "La voce viene inviata a Groq (Whisper large v3) con la tua chiave Groq: è il più preciso, "
                    "ma conta nei limiti del tuo piano gratuito.",
            "gemini": "La voce viene inviata a Gemini con la tua chiave Gemini.",
        }
        self.online_hint.setText(texts.get(engine, ""))
        self.online_hint.setVisible(engine in texts)
        self._refresh()

    def _refresh(self) -> None:
        for name, card in self.sizes.cards.items():
            if self._downloading == name:
                card.set_status("Download in corso…")
            elif self._local.is_downloaded(name):
                card.set_status("Scaricato", ok=True)
            else:
                card.set_status("Da scaricare")
        name = self.sizes.value()
        mb = LOCAL_STT_MODELS[name][1]
        if self._downloading:
            self.download_button.setText("Annulla")
            self.download_button.setObjectName("")
            self.bar.show()
        elif self._local.is_downloaded(name):
            self.download_button.hide()
            self.bar.hide()
            self.download_status.setText(f"<span style='color:{theme.BACKLIGHT}'>Modello pronto</span> ({mb} MB).")
        else:
            self.download_button.show()
            self.download_button.setText(f"Scarica ({mb} MB)")
            self.download_button.setObjectName("primary")
            self.bar.hide()
            self.download_status.setText(
                "Si scaricherà durante l'installazione." if not self.download_now
                else f"Da scaricare: circa {mb} MB."
            )
            if not self.download_now:
                self.download_button.hide()
        self.download_button.style().unpolish(self.download_button)
        self.download_button.style().polish(self.download_button)
        self.readiness.emit(self.is_ready())

    def _download_clicked(self) -> None:
        if self._downloading and self._cancel is not None:
            self._cancel.set()
            return
        self.start_download(self.sizes.value())

    def start_download(self, name: str) -> None:
        self._downloading = name
        self._cancel = threading.Event()
        cancel = self._cancel
        self.bar.setValue(0)
        self.download_status.setText("Scarico il modello…")
        self.download_button.show()
        self._refresh()

        def work() -> None:
            try:
                self._local.download_model(name, lambda d, t: self.relay.progress.emit(name, d, t), cancel)
                self.relay.downloaded.emit(name, "")
            except self._local.DownloadCancelled:
                self.relay.downloaded.emit(name, "cancelled")
            except Exception as exc:
                self.relay.downloaded.emit(name, str(exc) or type(exc).__name__)

        threading.Thread(target=work, name="ressy-model-download", daemon=True).start()

    def _on_progress(self, name: str, done: int, total: int) -> None:
        if name != self._downloading:
            return
        self.bar.setValue(int(1000 * done / max(1, total)))
        self.download_status.setText(f"Scarico il modello… {done / 1e6:.0f} di {total / 1e6:.0f} MB")

    def _on_downloaded(self, name: str, error: str) -> None:
        self._downloading = ""
        self._refresh()
        if error == "cancelled":
            self.download_status.setText("Download annullato.")
        elif error:
            self.download_status.setText(
                f"<span style='color:#FF8C73'>Download non riuscito</span>: controlla la connessione e riprova."
            )

    def cancel_download(self) -> None:
        if self._cancel is not None:
            self._cancel.set()

