from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import CLAUDE_MODELS, DEFAULT_LOCAL_LLM_MODEL, DEFAULT_MODEL_SERVER_PORT, LOCAL_LLM_MODELS, LOCAL_STT_MODELS, PROVIDER_NAMES, normalize_custom_url
from ..paths import resource_path
from . import theme
from ..i18n import tr

PROVIDERS: dict[str, dict[str, Any]] = {
    "groq": {
        "tagline": tr("Velocissimo, con piano gratuito."),
        "badge": tr("Gratis"),
        "placeholder": tr("gsk_…"),
        "url": "https://console.groq.com/keys",
        "site": "console.groq.com",
        "models": [
            ("openai/gpt-oss-120b", tr("GPT-OSS 120B (consigliato)")),
            ("openai/gpt-oss-20b", tr("GPT-OSS 20B (più veloce)")),
            ("qwen/qwen3.8-27b", tr("Qwen 3.8 27B")),
        ],
    },
    "gemini": {
        "tagline": tr("Di Google, piano gratuito generoso."),
        "badge": tr("Gratis"),
        "placeholder": tr("AIza…"),
        "url": "https://aistudio.google.com/apikey",
        "site": "aistudio.google.com",
        "models": [
            ("gemini-flash-latest", tr("Gemini Flash, sempre l'ultimo (consigliato)")),
            ("gemini-flash-lite-latest", tr("Gemini Flash-Lite (più veloce)")),
            ("gemini-pro-latest", tr("Gemini Pro (più capace, più lento)")),
        ],
    },
    "openrouter": {
        "tagline": tr("Tanti modelli gratis: ottima riserva."),
        "badge": tr("Gratis"),
        "placeholder": tr("sk-or-v1-…"),
        "url": "https://openrouter.ai/settings/keys",
        "site": "openrouter.ai",
        "models": [("auto", tr("Il miglior modello gratis del giorno (automatico)"))],
    },
    "claude": {
        "tagline": tr("Il più capace. A consumo, a pagamento."),
        "badge": tr("Il più capace"),
        "placeholder": tr("sk-ant-…"),
        "url": "https://console.anthropic.com/settings/keys",
        "site": "console.anthropic.com",
        "models": list(CLAUDE_MODELS.items()),
    },
    "local": {
        "tagline": tr("Gratis e offline, scaricata sul PC."),
        "badge": tr("Senza chiave"),
        "placeholder": "",
        "url": "",
        "site": "",
        "models": [],
    },
    "custom": {
        "tagline": tr("Usa il tuo server (Ollama, llama.cpp, VPS…)."),
        "badge": tr("Self-host"),
        "placeholder": "",
        "url": "",
        "site": "",
        "models": [],
    },
}
LOCAL_AI_DETAILS = {
    "": (tr("Nessuna"), tr("Solo le chiavi online")),
    "qwen2.5-0.5b": (tr("Leggera"), tr("Meno di 500 MB: apre app, siti, musica, meteo")),
    "qwen2.5-1.5b": (tr("Consigliata"), tr("Equilibrio ideale su PC, capisce più comandi")),
    "qwen2.5-3b": (tr("Massima"), tr("Fino a 2 GB: massima intelligenza offline per fare tutto")),
}

SPEECH_OPTIONS = {
    "local": (tr("Sul PC"), tr("Gratis e senza limiti. Funziona anche offline."), tr("Consigliato"), "pc"),
    "groq": ("Groq", tr("Whisper online, il più preciso. Usa la chiave Groq."), "", "groq"),
    "gemini": ("Gemini", tr("Online, con la chiave Gemini."), "", "gemini"),
}
LOCAL_DETAILS = {
    "tiny-q5_1": tr("Il più rapido, sbaglia di più"),
    "base-q5_1": tr("Buon equilibrio, consigliato"),
    "small-q5_1": tr("Capisce meglio, più lento"),
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
            p.setBrush(QColor(theme.BACKLIGHT if self.badge == tr("Gratis") else theme.LILAC).darker(100))
            p.setOpacity(0.16)
            p.drawRoundedRect(pill, 9, 9)
            p.setOpacity(1.0)
            p.setPen(QColor(theme.BACKLIGHT if self.badge == tr("Gratis") else theme.LILAC))
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
    hostResult = Signal(object, str)


class BrainSetup(QWidget):

    validity = Signal(bool)

    def __init__(self, parent: QWidget | None = None, *, auto_verify: bool = False) -> None:
        super().__init__(parent)
        self.auto_verify = auto_verify
        self.keys = {name: "" for name in PROVIDERS}
        self.models = {name: "" for name in PROVIDERS}
        self.custom_base_url = ""
        self._available: dict[str, list[str] | None] = {name: None for name in PROVIDERS}
        self._current = "groq"
        self._checking: tuple[str, str] | None = None
        self._loading = False
        self._verified: dict[str, str] = {}
        self.relay = _Relay()
        self.relay.verified.connect(self._on_verified)
        self.relay.hostResult.connect(self._on_host_result)

        cards = [
            ChoiceCard(
                name,
                PROVIDER_NAMES[name],
                info["tagline"],
                logo="pc" if name == "local" else ("server" if name == "custom" else name),
                badge=info["badge"],
            )
            for name, info in PROVIDERS.items()
        ]
        self.cards = CardRow(cards, columns=3)
        self.cards.changed.connect(self._switch)

        self.key_hint = _hint("")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.textEdited.connect(self._key_edited)
        show = QPushButton(tr("Mostra"))
        show.setCheckable(True)
        show.toggled.connect(lambda on: (
            self.key.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password),
            show.setText(tr("Nascondi") if on else tr("Mostra")),
        ))
        self.verify_button = QPushButton(tr("Verifica"))
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

        self.key_box = QWidget()
        form = QGridLayout(self.key_box)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.key_label = QLabel(tr("Chiave API"))
        form.addWidget(self.key_label, 0, 0)
        form.addLayout(key_row, 0, 1)
        form.addWidget(self.status, 1, 1)
        form.addWidget(QLabel(tr("Modello")), 2, 0)
        form.addWidget(self.model, 2, 1)
        form.setColumnStretch(1, 1)

        self._build_custom_box()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self.cards)
        layout.addWidget(self.key_hint)
        layout.addWidget(self.key_box)
        layout.addWidget(self.custom_box)
        self.keys_hint = _hint(
            tr("Puoi inserire <b>più chiavi</b>: scegli una scheda, incolla la chiave, poi torna su quella che vuoi "
            "usare. Se la prima arriva al limite, Ressy continua con le altre.")
        )
        layout.addWidget(self.keys_hint)
        self.local_ai = LocalAISetup()
        self.local_ai.readiness.connect(self._local_changed)
        layout.addWidget(self.local_ai)

    def _build_custom_box(self) -> None:
        self.custom_box = QWidget()
        root = QVBoxLayout(self.custom_box)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        presets = QHBoxLayout()
        presets.setSpacing(8)
        for label, url in (
            (tr("Questo PC (8088)"), "http://127.0.0.1:8088/v1"),
            ("Ollama (11434)", "http://127.0.0.1:11434/v1"),
            ("LM Studio (1234)", "http://127.0.0.1:1234/v1"),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, u=url: self._apply_custom_preset(u))
            presets.addWidget(btn)
        presets.addStretch(1)
        root.addLayout(presets)

        self.custom_url = QLineEdit()
        self.custom_url.setPlaceholderText("http://127.0.0.1:8088/v1")
        self.custom_url.textEdited.connect(self._custom_edited)

        self.custom_key = QLineEdit()
        self.custom_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.custom_key.setPlaceholderText(tr("Opzionale (lascia vuoto se non serve)"))
        self.custom_key.textEdited.connect(self._custom_edited)
        show_c = QPushButton(tr("Mostra"))
        show_c.setCheckable(True)
        show_c.toggled.connect(lambda on: (
            self.custom_key.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password),
            show_c.setText(tr("Nascondi") if on else tr("Mostra")),
        ))
        self.custom_verify = QPushButton(tr("Connetti"))
        self.custom_verify.clicked.connect(self.verify)
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        url_row.addWidget(self.custom_url, 1)
        url_row.addWidget(self.custom_verify)

        ckey_row = QHBoxLayout()
        ckey_row.setSpacing(8)
        ckey_row.addWidget(self.custom_key, 1)
        ckey_row.addWidget(show_c)

        self.custom_model = QComboBox()
        self.custom_model.setEditable(True)
        self.custom_model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        if self.custom_model.lineEdit() is not None:
            self.custom_model.lineEdit().setPlaceholderText(tr("Automatico dal server (o scrivi il nome esatto)"))
            self.custom_model.lineEdit().textEdited.connect(self._custom_edited)

        self.custom_status = QLabel()
        self.custom_status.setWordWrap(True)

        form = QGridLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.addWidget(QLabel(tr("URL server AI")), 0, 0)
        form.addLayout(url_row, 0, 1)
        form.addWidget(self.custom_status, 1, 1)
        form.addWidget(QLabel(tr("Token (opzionale)")), 2, 0)
        form.addLayout(ckey_row, 2, 1)
        form.addWidget(QLabel(tr("Modello")), 3, 0)
        form.addWidget(self.custom_model, 3, 1)
        form.setColumnStretch(1, 1)
        root.addLayout(form)

        host_card = QFrame()
        host_card.setStyleSheet(
            f"QFrame {{ background: {theme.FIELD}; border: 1px solid {theme.PLATE_EDGE}; border-radius: 10px; }}"
        )
        hb = QVBoxLayout(host_card)
        hb.setContentsMargins(14, 12, 14, 12)
        hb.setSpacing(8)

        htitle = QLabel(tr("CREA IL TUO SERVER PER IL MODELLO (HOST SU QUESTO PC)"))
        htitle.setStyleSheet(f"color: {theme.LILAC}; font-size: 11px; font-weight: 700; border: none;")
        hb.addWidget(htitle)

        self.host_model = QComboBox()
        browse_gguf = QPushButton(tr("Scegli .gguf…"))
        browse_gguf.clicked.connect(self._browse_gguf)
        refresh_gguf = QPushButton(tr("Aggiorna"))
        refresh_gguf.clicked.connect(self._refresh_gguf_list)
        mrow = QHBoxLayout()
        mrow.setSpacing(8)
        mrow.addWidget(self.host_model, 1)
        mrow.addWidget(browse_gguf)
        mrow.addWidget(refresh_gguf)
        hb.addLayout(mrow)

        opt_row = QHBoxLayout()
        opt_row.setSpacing(10)
        opt_row.addWidget(QLabel(tr("Porta")))
        self.host_port = QSpinBox()
        self.host_port.setRange(1024, 65535)
        self.host_port.setValue(DEFAULT_MODEL_SERVER_PORT)
        self.host_lan = QCheckBox(tr("Accessibile anche in rete / altri PC (0.0.0.0)"))
        gen_tok = QPushButton(tr("Genera token"))
        gen_tok.clicked.connect(self._generate_custom_token)
        self.host_toggle = QPushButton(tr("Crea e avvia server AI"))
        self.host_toggle.setObjectName("primary")
        self.host_toggle.clicked.connect(self._toggle_host_server)
        opt_row.addWidget(self.host_port)
        opt_row.addWidget(self.host_lan, 1)
        opt_row.addWidget(gen_tok)
        opt_row.addWidget(self.host_toggle)
        hb.addLayout(opt_row)

        self.host_info = QLabel(tr("Puoi servire un modello Qwen già scaricato o un qualsiasi file .gguf, poi collegarci Ressy o un altro PC."))
        self.host_info.setWordWrap(True)
        self.host_info.setObjectName("hint")
        self.host_info.setStyleSheet("border: none;")
        hb.addWidget(self.host_info)

        root.addWidget(host_card)
        self._refresh_gguf_list()
        self._sync_host_status()

    def load(self, provider: str, keys: dict[str, str], models: dict[str, str], local_model: str = "",
             custom_url: str = "") -> None:
        self.local_ai.load(local_model)
        self.keys.update({k: v or "" for k, v in keys.items()})
        self.models.update({k: v or "" for k, v in models.items()})
        self.custom_base_url = normalize_custom_url(custom_url) or (custom_url or "").strip()
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
            "custom_base_url": normalize_custom_url(self.custom_base_url),
            "custom_model": self.models["custom"].strip(),
            "custom_api_key": self.keys["custom"].strip(),
            "local_llm_model": self.local_ai.value(),
        }

    def problem(self) -> str:
        self._remember()
        provider = self.provider()
        if provider == "local":
            return self.local_ai.problem(required=True)
        if provider == "custom":
            if not normalize_custom_url(self.custom_base_url):
                return tr("Inserisci l'URL del tuo server AI o avvia un server su questo PC.")
            return self.local_ai.problem(required=False)
        if not self.keys[provider].strip():
            return tr("Incolla la chiave API di {value} (è gratis crearla).").format(value=PROVIDER_NAMES[provider])
        return self.local_ai.problem(required=False)

    def focus_key(self) -> None:
        if self.provider() == "custom":
            self.custom_url.setFocus()
        else:
            self.key.setFocus()

    def is_verified(self) -> bool:
        provider = self.provider()
        if provider == "local":
            return self.local_ai.is_ready()
        if provider == "custom":
            url = normalize_custom_url(self.custom_base_url)
            return bool(url) and self._verified.get("custom") == url
        key = (self.keys.get(provider) or "").strip()
        return bool(key) and self._verified.get(provider) == key

    def verify_if_needed(self) -> None:
        self._remember()
        if self.provider() == "local":
            return
        if self.provider() == "custom":
            if normalize_custom_url(self.custom_base_url) and not self.is_verified() and self._checking is None:
                self.verify()
            return
        if self.keys[self.provider()].strip() and not self.is_verified() and self._checking is None:
            self.verify()

    def _remember(self) -> None:
        if self._current == "local":
            self._mark_keys()
            return
        if self._current == "custom":
            self.custom_base_url = self.custom_url.text().strip()
            self.keys["custom"] = self.custom_key.text().strip()
            self.models["custom"] = (self.custom_model.currentData() or self.custom_model.currentText() or "").strip()
            self._mark_keys()
            return
        self.keys[self._current] = self.key.text().strip()
        if self.model.currentData():
            self.models[self._current] = self.model.currentData()
        self._mark_keys()

    def _mark_keys(self) -> None:
        for name, card in self.cards.cards.items():
            if name == "local":
                has = self.local_ai.is_ready()
                status = tr("Scaricata") if has else ""
            elif name == "custom":
                has = bool(normalize_custom_url(self.custom_base_url))
                status = tr("Configurato") if has else ""
            else:
                has = bool((self.keys.get(name) or "").strip())
                status = tr("Chiave inserita") if has else ""
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

    def _local_changed(self, _ready: bool) -> None:
        self._mark_keys()
        self.validity.emit(self.is_verified())

    def _show(self, provider: str) -> None:
        local = provider == "local"
        custom = provider == "custom"
        self.key_box.setVisible(not local and not custom)
        self.custom_box.setVisible(custom)
        self.keys_hint.setVisible(not local)
        self.local_ai.set_required(local)
        if local:
            self.key.setText("")
            self.key_hint.setText(
                tr("Ressy pensa con un'AI scaricata su questo PC: gratis, senza chiave e anche senza internet. "
                "È meno brava dei servizi online, ma per aprire app, siti, musica e meteo basta.")
            )
            self._set_status("", "")
            return
        if custom:
            self.key_hint.setText(
                tr("Collega Ressy a un <b>tuo</b> server AI OpenAI-compatibile (Ollama, LM Studio, llama.cpp o VPS), "
                "oppure creane e avviamone uno direttamente da qui sotto.")
            )
            self.custom_url.setText(self.custom_base_url)
            self.custom_key.setText(self.keys["custom"])
            self._fill_custom_models()
            self._refresh_gguf_list()
            self._sync_host_status()
            return
        info = PROVIDERS[provider]
        name = PROVIDER_NAMES[provider]
        self.key_label.setText(tr("Chiave {name}").format(name=name))
        self.key.setPlaceholderText(info["placeholder"])
        self.key.setText(self.keys[provider])
        self.key_hint.setText(
            tr("Ressy pensa con {name} usando la <b>tua</b> chiave: resta su questo PC, cifrata da Windows. ").format(name=name)
            + _link(tr("Crea una chiave su {value}").format(value=info['site']), info["url"])
        )
        self._set_status("", "")
        self._fill_models(provider)

    def _apply_custom_preset(self, url: str) -> None:
        self.custom_url.setText(url)
        self._custom_edited()

    def _custom_edited(self) -> None:
        self.custom_base_url = self.custom_url.text().strip()
        self.keys["custom"] = self.custom_key.text().strip()
        self.models["custom"] = (self.custom_model.currentData() or self.custom_model.currentText() or "").strip()
        self._mark_keys()
        self._set_custom_status("", "")
        self.validity.emit(self.is_verified())

    def _fill_custom_models(self) -> None:
        current = (self.models.get("custom") or "").strip()
        available = self._available.get("custom") or []
        self.custom_model.blockSignals(True)
        self.custom_model.clear()
        for mid in available:
            self.custom_model.addItem(mid, mid)
        if current and self.custom_model.findText(current) < 0:
            self.custom_model.insertItem(0, current, current)
        if current:
            self.custom_model.setEditText(current)
        elif available:
            self.custom_model.setCurrentIndex(0)
        else:
            self.custom_model.setEditText("")
        self.custom_model.blockSignals(False)

    def _set_custom_status(self, kind: str, text: str) -> None:
        self.custom_status.setObjectName(kind or "hint")
        self.custom_status.setText(text)
        self.custom_status.setVisible(bool(text))
        self.custom_status.style().unpolish(self.custom_status)
        self.custom_status.style().polish(self.custom_status)

    def _refresh_gguf_list(self) -> None:
        from ..brain.model_server import scan_gguf_models

        prev = str(self.host_model.currentData() or "")
        self.host_model.clear()
        for label, path in scan_gguf_models():
            self.host_model.addItem(label, str(path))
        if self.host_model.count() == 0:
            self.host_model.addItem(tr("Nessun file .gguf trovato (scegli o scarica sotto)"), "")
        elif prev:
            idx = self.host_model.findData(prev)
            if idx >= 0:
                self.host_model.setCurrentIndex(idx)

    def _browse_gguf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Scegli modello GGUF"), "", "GGUF (*.gguf);;All files (*)")
        if path:
            from pathlib import Path

            p = Path(path)
            if self.host_model.count() == 1 and not self.host_model.itemData(0):
                self.host_model.clear()
            idx = self.host_model.findData(str(p))
            if idx < 0:
                self.host_model.insertItem(0, p.name, str(p))
                idx = 0
            self.host_model.setCurrentIndex(idx)

    def _generate_custom_token(self) -> None:
        from ..brain.model_server import generate_api_key

        tok = generate_api_key()
        self.custom_key.setText(tok)
        self._custom_edited()

    def _sync_host_status(self) -> None:
        from ..brain.model_server import server_urls, shared_runner

        runner = shared_runner()
        if runner.running and runner.config is not None:
            self.host_toggle.setText(tr("Ferma server AI"))
            expose = runner.config.host in ("0.0.0.0", "::")
            urls = server_urls(runner.config.port, expose_lan=expose)
            self.host_info.setText(
                tr("<span style='color:{BACKLIGHT}'>Server attivo</span> · Connettiti a: <b>{urls}</b>").format(
                    BACKLIGHT=theme.BACKLIGHT,
                    urls=", ".join(urls),
                )
            )
        else:
            self.host_toggle.setText(tr("Crea e avvia server AI"))

    def _toggle_host_server(self) -> None:
        from ..brain.model_server import ModelServerConfig, server_urls, shared_runner

        runner = shared_runner()
        if runner.running:
            runner.stop()
            self.host_info.setText(tr("Server AI fermato."))
            self._sync_host_status()
            return

        model_path = str(self.host_model.currentData() or "").strip()
        if not model_path:
            self._set_custom_status("error", tr("Scegli prima un file .gguf (oppure scarica un modello locale qui sotto)."))
            return
        port = int(self.host_port.value())
        expose = self.host_lan.isChecked()
        cfg = ModelServerConfig(
            model_path=model_path,
            host="0.0.0.0" if expose else "127.0.0.1",
            port=port,
            api_key=self.custom_key.text().strip(),
        )
        self.host_toggle.setEnabled(False)
        self.host_info.setText(tr("Avvio il server del modello AI…"))
        urls = server_urls(port, expose_lan=expose)
        self.custom_url.setText(urls[0])
        self._custom_edited()

        def work() -> None:
            try:
                models = runner.start(cfg, wait_s=60.0)
                self.relay.hostResult.emit(models, "")
            except Exception as exc:
                self.relay.hostResult.emit([], str(exc) or type(exc).__name__)

        threading.Thread(target=work, name="ressy-model-server", daemon=True).start()

    def _on_host_result(self, models: object, error: str) -> None:
        self.host_toggle.setEnabled(True)
        self._sync_host_status()
        if error:
            self._set_custom_status("error", error)
            self.host_info.setText(tr("Avvio non riuscito: {err}").format(err=error))
            return
        model_list = list(models or [])
        if model_list:
            self._available["custom"] = model_list
            self.models["custom"] = model_list[0]
            self._fill_custom_models()
        norm = normalize_custom_url(self.custom_url.text())
        self._verified["custom"] = norm
        self._set_custom_status("ok", tr("Server AI creato e connesso!"))
        self.validity.emit(self.is_verified())

    def _fill_models(self, provider: str) -> None:
        if provider == "custom":
            self._fill_custom_models()
            return
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
        if provider == "custom":
            url = normalize_custom_url(self.custom_url.text())
            key = self.custom_key.text().strip()
            if not url:
                self._set_custom_status("error", tr("Inserisci prima un URL valido (es. http://127.0.0.1:8088/v1)."))
                return
            self.custom_verify.setEnabled(False)
            self._set_custom_status("hint", tr("Connessione a {url}…").format(url=url))
            self._checking = ("custom", url)

            def work_custom() -> None:
                from ..brain.providers import verify_key_blocking

                try:
                    self.relay.verified.emit("custom", url, verify_key_blocking("custom", key, base_url=url), None)
                except Exception as exc:
                    self.relay.verified.emit("custom", url, None, exc)

            threading.Thread(target=work_custom, name="ressy-verify", daemon=True).start()
            return

        key = self.key.text().strip()
        if not key:
            self._set_status("error", tr("Incolla prima la chiave."))
            return
        self.verify_button.setEnabled(False)
        self._set_status("hint", tr("Verifico la chiave con {value}…").format(value=PROVIDER_NAMES[provider]))
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
        if provider == "custom":
            self.custom_verify.setEnabled(True)
            if self.provider() != "custom":
                return
            if error is not None:
                self._set_custom_status("error", str(error))
                return
            model_list = list(models or [])
            self._available["custom"] = model_list
            self._verified["custom"] = key
            self._fill_custom_models()
            self._set_custom_status(
                "ok",
                tr("Server connesso! Trovati {n} modelli.").format(n=len(model_list)) if model_list else tr("Server connesso!"),
            )
            self.validity.emit(self.is_verified())
            return

        self.verify_button.setEnabled(True)
        if provider != self.provider():
            return
        name = PROVIDER_NAMES[provider]
        if error is not None:
            from ..brain.groq import GroqAuthError

            if isinstance(error, GroqAuthError):
                self._set_status("error", tr("{name} ha rifiutato questa chiave: controlla di averla copiata tutta.").format(name=name))
            else:
                self._set_status("error", tr("Non riesco a raggiungere {name} ora: controlla la connessione e riprova.").format(name=name))
            return
        self._available[provider] = list(models or [])
        self._verified[provider] = key
        self._set_status("ok", tr("Chiave valida."))
        self._fill_models(provider)
        self.validity.emit(self.is_verified())


class LocalAISetup(QWidget):

    readiness = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from ..brain import local_llm

        self._llm = local_llm
        self._required = False
        self._cancel: threading.Event | None = None
        self._downloading = ""
        self.relay = _Relay()
        self.relay.progress.connect(self._on_progress)
        self.relay.downloaded.connect(self._on_downloaded)

        self.title = QLabel()
        self.title.setObjectName("section")
        cards = []
        for name, (label, detail) in LOCAL_AI_DETAILS.items():
            size = f" · {self._size_text(LOCAL_LLM_MODELS[name][1])}" if name else ""
            cards.append(ChoiceCard(name or "none", f"{label}{size}", detail, compact=True))
        self.sizes = CardRow(cards, columns=2)
        self.sizes.changed.connect(lambda _: self._refresh())

        row = QHBoxLayout()
        row.setSpacing(12)
        self.download_button = QPushButton(tr("Scarica"))
        self.download_button.setObjectName("primary")
        self.download_button.clicked.connect(self._download_clicked)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.status = QLabel()
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        col = QVBoxLayout()
        col.setSpacing(6)
        col.addWidget(self.status)
        col.addWidget(self.bar)
        row.addWidget(self.download_button)
        row.addLayout(col, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(self.sizes)
        layout.addLayout(row)
        self.set_required(False)

    @staticmethod
    def _size_text(mb: int) -> str:
        return f"{mb / 1000:.1f} GB".replace(".", ",") if mb >= 1000 else f"{mb} MB"

    def load(self, model: str) -> None:
        self.sizes.set_value(model or "none")
        self._refresh()

    def value(self) -> str:
        key = self.sizes.value()
        return "" if key == "none" else key

    def set_required(self, required: bool) -> None:
        self._required = required
        self.title.setText(tr("SCEGLI L'AI SUL PC") if required else tr("RISERVA GRATUITA SUL PC (FACOLTATIVA)"))
        self.sizes.cards["none"].setVisible(not required)
        if required and self.sizes.value() == "none":
            self.sizes.set_value(DEFAULT_LOCAL_LLM_MODEL)
        self._refresh()

    def is_ready(self) -> bool:
        name = self.value()
        return bool(name) and not self._downloading and self._llm.is_downloaded(name)

    def problem(self, *, required: bool) -> str:
        if self._downloading:
            return tr("Aspetta che finisca il download dell'AI sul PC.")
        name = self.value()
        if not name:
            return tr("Scegli quale AI scaricare sul PC.") if required else ""
        if not self._llm.is_downloaded(name):
            return (tr("Scarica l'AI sul PC (pulsante «Scarica»).") if required
                    else tr("Scarica l'AI sul PC (pulsante «Scarica»), oppure scegli «Nessuna»."))
        return ""

    def _refresh(self) -> None:
        for name, card in self.sizes.cards.items():
            if name == "none":
                continue
            if self._downloading == name:
                card.set_status(tr("Download in corso…"))
            elif self._llm.is_downloaded(name):
                card.set_status(tr("Scaricata"), ok=True)
            else:
                card.set_status(tr("Da scaricare"))
        name = self.value()
        if self._downloading:
            self.download_button.setText(tr("Annulla"))
            self.download_button.setObjectName("")
            self.download_button.show()
            self.bar.show()
        elif not name:
            self.download_button.hide()
            self.bar.hide()
            self.status.setText(tr("Se tutte le chiavi sono al limite Ressy aspetta che si ricarichino."))
        elif self._llm.is_downloaded(name):
            self.download_button.hide()
            self.bar.hide()
            self.status.setText(tr("<span style='color:{BACKLIGHT}'>AI sul PC pronta</span>: si accende solo quando serve e si spegne da sola dopo 10 minuti.").format(BACKLIGHT=theme.BACKLIGHT))
        else:
            mb = self._llm.download_size_mb(name)
            self.download_button.show()
            self.download_button.setText(tr("Scarica ({size_text})").format(size_text=self._size_text(mb)))
            self.download_button.setObjectName("primary")
            self.bar.hide()
            self.status.setText(tr("Si scarica una volta: il modello Qwen 2.5 (Apache 2.0) e il motore llama.cpp "
                                "ufficiale. Servono circa 2 GB di RAM libera quando è accesa."))
        self.download_button.style().unpolish(self.download_button)
        self.download_button.style().polish(self.download_button)
        self.readiness.emit(self.is_ready())

    def _download_clicked(self) -> None:
        if self._downloading and self._cancel is not None:
            self._cancel.set()
            return
        if self.value():
            self.start_download(self.value())

    def start_download(self, name: str) -> None:
        self._downloading = name
        self._cancel = threading.Event()
        cancel = self._cancel
        self.bar.setValue(0)
        self.status.setText(tr("Scarico l'AI sul PC…"))
        self._refresh()

        def work() -> None:
            from ..speech.local_stt import DownloadCancelled

            try:
                self._llm.download(name, lambda d, t: self.relay.progress.emit(name, d, t), cancel)
                self.relay.downloaded.emit(name, "")
            except DownloadCancelled:
                self.relay.downloaded.emit(name, "cancelled")
            except Exception as exc:
                self.relay.downloaded.emit(name, str(exc) or type(exc).__name__)

        threading.Thread(target=work, name="ressy-ai-download", daemon=True).start()

    def cancel_download(self) -> None:
        if self._cancel is not None:
            self._cancel.set()

    def _on_progress(self, name: str, done: int, total: int) -> None:
        if name != self._downloading:
            return
        self.bar.setValue(int(1000 * done / max(1, total)))
        self.status.setText(tr("Scarico l'AI sul PC… {value:.0f} di {value2:.0f} MB").format(value=done / 1e6, value2=total / 1e6))

    def _on_downloaded(self, name: str, error: str) -> None:
        self._downloading = ""
        self._refresh()
        if error == "cancelled":
            self.status.setText(tr("Download annullato."))
        elif error:
            self.status.setText(tr("<span style='color:#FF8C73'>Download non riuscito</span>: "
                                "controlla la connessione e riprova."))


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

        sizes = [ChoiceCard(name, tr("{label} · {mb} MB").format(label=label, mb=mb), LOCAL_DETAILS.get(name, ""), compact=True,
                            badge="")
                 for name, (label, mb) in LOCAL_STT_MODELS.items()]
        self.sizes = CardRow(sizes)
        self.sizes.changed.connect(lambda _: self._refresh())

        self.local_box = QWidget()
        lv = QVBoxLayout(self.local_box)
        lv.setContentsMargins(0, 4, 0, 0)
        lv.setSpacing(10)
        lv.addWidget(_hint(
            tr("Il modello si scarica una volta sola dentro la cartella di Ressy; poi la voce non esce dal PC.")
        ))
        lv.addWidget(self.sizes)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.download_button = QPushButton(tr("Scarica"))
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
                return tr("Aspetta che finisca il download del modello vocale.")
            if self.download_now and self.needs_download():
                return tr("Scarica il modello vocale (pulsante «Scarica»), oppure scegli di capire la voce online.")
            return ""
        if keys is not None and not (keys.get(engine) or "").strip():
            return tr("Per capire la voce con {value} serve anche la sua chiave (pagina Intelligenza).").format(value=PROVIDER_NAMES[engine])
        return ""

    def _engine_changed(self, engine: str) -> None:
        self.local_box.setVisible(engine == "local")
        texts = {
            "groq": tr("La voce viene inviata a Groq (Whisper large v3) con la tua chiave Groq: è il più preciso, "
                    "ma conta nei limiti del tuo piano gratuito."),
            "gemini": tr("La voce viene inviata a Gemini con la tua chiave Gemini."),
        }
        self.online_hint.setText(texts.get(engine, ""))
        self.online_hint.setVisible(engine in texts)
        self._refresh()

    def _refresh(self) -> None:
        for name, card in self.sizes.cards.items():
            if self._downloading == name:
                card.set_status(tr("Download in corso…"))
            elif self._local.is_downloaded(name):
                card.set_status(tr("Scaricato"), ok=True)
            else:
                card.set_status(tr("Da scaricare"))
        name = self.sizes.value()
        mb = LOCAL_STT_MODELS[name][1]
        if self._downloading:
            self.download_button.setText(tr("Annulla"))
            self.download_button.setObjectName("")
            self.bar.show()
        elif self._local.is_downloaded(name):
            self.download_button.hide()
            self.bar.hide()
            self.download_status.setText(tr("<span style='color:{BACKLIGHT}'>Modello pronto</span> ({mb} MB).").format(BACKLIGHT=theme.BACKLIGHT, mb=mb))
        else:
            self.download_button.show()
            self.download_button.setText(tr("Scarica ({mb} MB)").format(mb=mb))
            self.download_button.setObjectName("primary")
            self.bar.hide()
            self.download_status.setText(
                tr("Si scaricherà durante l'installazione.") if not self.download_now
                else tr("Da scaricare: circa {mb} MB.").format(mb=mb)
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
        self.download_status.setText(tr("Scarico il modello…"))
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
        self.download_status.setText(tr("Scarico il modello… {value:.0f} di {value2:.0f} MB").format(value=done / 1e6, value2=total / 1e6))

    def _on_downloaded(self, name: str, error: str) -> None:
        self._downloading = ""
        self._refresh()
        if error == "cancelled":
            self.download_status.setText(tr("Download annullato."))
        elif error:
            self.download_status.setText(
                tr("<span style='color:#FF8C73'>Download non riuscito</span>: controlla la connessione e riprova.").format()
            )

    def cancel_download(self) -> None:
        if self._cancel is not None:
            self._cancel.set()

