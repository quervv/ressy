from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtCore import QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPainter, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..audio import devices
from ..config import EDGE_VOICES, voice_for, wake_phrases_for
from ..paths import log_dir
from ..system_integration import autostart_enabled, set_autostart
from . import logo, theme
from .bot_setup import BotSetup
from .brain_setup import BrainSetup, SpeechSetup
from .keys import KeyCapture, PresenceLight
from .tray import PRESENCE_TEXT
from .winframe import style_title_bar
from ..i18n import LANGUAGES, tr

if TYPE_CHECKING:
    from ..core.controller import Controller
    from .bridge import UiBridge

PAGES = [tr("Generale"), tr("Intelligenza"), tr("Voce"), tr("Tasto e ascolto"), tr("Da remoto"), "Info"]
VOICE_TEST = tr("Ciao! Sono Ressy. Questa è la mia voce.")


def _section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("section")
    f = theme.font(12, 700, 110)
    f.setLetterSpacing(f.SpacingType.PercentageSpacing, 106)
    label.setFont(f)
    return label


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    return label


def _link(text: str, url: str) -> str:
    return f'<a href="{url}" style="color:{theme.LEGEND};">{text}</a>'


def _form() -> QFormLayout:
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setHorizontalSpacing(18)
    form.setVerticalSpacing(12)
    return form


def _combo(items: list[tuple[str, str]], current: str) -> QComboBox:
    combo = QComboBox()
    for value, label in items:
        combo.addItem(label, value)
    index = combo.findData(current)
    if index < 0 and current:
        combo.addItem(current, current)
        index = combo.count() - 1
    combo.setCurrentIndex(max(index, 0))
    return combo


class _Mark(QWidget):
    def __init__(self, size: int) -> None:
        super().__init__()
        self.setFixedSize(QSize(size, size))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        logo.paint_mark(p, QRectF(0, 0, self.width(), self.height()))
        p.end()


class SettingsDialog(QDialog):
    _usage_ready = Signal(str)

    def __init__(
        self,
        controller: "Controller",
        bridge: "UiBridge",
        *,
        open_pairing: Callable[[], None],
        restart: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.settings = controller.settings
        self._open_pairing = open_pairing
        self._restart = restart
        self._shown_language = self.settings.language
        self._voice_backup: dict[str, Any] | None = None
        self.setWindowTitle(tr("Ressy · Impostazioni"))
        self.setMinimumSize(QSize(860, 660))
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(178)
        self.nav.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for name in PAGES:
            self.nav.addItem(QListWidgetItem(name))
        self.stack = QStackedWidget()

        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            "background: {MODS}; border: 1px solid {ACCENT}; border-radius: 8px;padding: 10px 14px; color: {LEGEND};".format(MODS=theme.MODS, ACCENT=theme.ACCENT, LEGEND=theme.LEGEND)
        )
        self.banner.hide()

        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()

        self._build_general()
        self._build_brain()
        self._build_voice()
        self._build_keys()
        self._build_remote()
        self._build_info()
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        cancel = QPushButton(tr("Annulla"))
        cancel.clicked.connect(self.reject)
        save = QPushButton(tr("Salva"))
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons = QHBoxLayout()
        buttons.addWidget(self.error, 1)
        buttons.addStretch()
        buttons.addSpacing(12)
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        right = QVBoxLayout()
        right.setSpacing(14)
        right.addWidget(self.banner)
        right.addWidget(self.stack, 1)
        right.addLayout(buttons)

        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 22, 20)
        root.setSpacing(22)
        left = QVBoxLayout()
        left.setSpacing(18)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(_Mark(30))
        brand = QLabel(f"Ressy <span style='color:{theme.LEGEND_DIM}; font-weight:500'>{__version__}</span>")
        brand.setFont(theme.font(17, 800, 112))
        head.addWidget(brand)
        head.addStretch(1)
        left.addLayout(head)
        left.addWidget(self.nav, 1)
        root.addLayout(left)
        root.addLayout(right, 1)

        bridge.remoteStateChanged.connect(self._on_remote_state)
        bridge.linksChanged.connect(self._fill_links)

    def _page(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 0, 12, 12)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("title")
        heading.setFont(theme.font(22, 700, 112))
        layout.addWidget(heading)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(page)
        self.stack.addWidget(scroll)
        return page, layout

    def _build_general(self) -> None:
        _, layout = self._page(tr("Generale"))
        form = _form()
        self.user_name = QLineEdit()
        self.user_name.setPlaceholderText(tr("Come vuoi che Ressy ti chiami"))
        self.user_name.setMaxLength(40)
        form.addRow(tr("Il tuo nome"), self.user_name)
        self.language = _combo(list(LANGUAGES.items()), "it")
        self.language.currentIndexChanged.connect(self._language_changed)
        form.addRow(tr("Lingua"), self.language)
        self.home_city = QLineEdit()
        self.home_city.setPlaceholderText(tr("Automatica (posizione approssimativa del PC)"))
        self.home_city.setMaxLength(80)
        form.addRow(tr("Città per il meteo"), self.home_city)
        layout.addLayout(form)
        layout.addWidget(_hint(
            tr("La lingua vale per le finestre, la voce, le risposte e le frasi di risveglio. "
               "Quando la cambi e salvi, Ressy si riavvia.")
        ))
        self.autostart = QCheckBox(tr("Avvia Ressy all'accensione del PC"))
        layout.addWidget(self.autostart)
        layout.addWidget(_hint(
            tr("Ressy resta nell'area di notifica, accanto all'orologio. Se non parte con Windows, "
            "da Telegram e Discord risulterà offline finché non la apri.")
        ))
        layout.addStretch(1)

    def _build_brain(self) -> None:
        _, layout = self._page(tr("Intelligenza"))
        layout.addWidget(_hint(
            tr("Scegli chi fa ragionare Ressy. Ognuno usa la <b>propria</b> chiave: niente piani condivisi, "
            "niente limiti di altri. Puoi cambiare quando vuoi.")
        ))
        self.brain = BrainSetup()
        layout.addWidget(self.brain)
        self.fallback = QCheckBox(tr("Se la chiave scelta è al limite, continua con le altre chiavi inserite"))
        layout.addWidget(self.fallback)
        self.quick = QCheckBox(tr("Esegui i comandi semplici sul PC senza usare l'AI (apri app e siti, meteo, volume…)"))
        layout.addWidget(self.quick)
        self.auto_update = QCheckBox(tr("Avvisami quando c'è una nuova versione di Ressy e installala con un clic"))
        layout.addWidget(self.auto_update)

        layout.addWidget(_section(tr("Consumi delle chiavi")))
        self.usage_text = QLabel("")
        self.usage_text.setWordWrap(True)
        self.usage_text.setTextFormat(Qt.TextFormat.RichText)
        self.usage_text.setObjectName("usage")
        layout.addWidget(self.usage_text)
        usage_row = QHBoxLayout()
        self.usage_refresh = QPushButton(tr("Aggiorna"))
        self.usage_refresh.clicked.connect(self._refresh_usage)
        usage_row.addWidget(self.usage_refresh)
        self._usage_ready.connect(self._show_usage)
        usage_row.addWidget(_hint(tr("Puoi anche chiederlo a voce o in chat: «quanto mi resta delle API?»")), 1)
        layout.addLayout(usage_row)
        layout.addStretch(1)

    def _refresh_usage(self) -> None:
        llm = getattr(self.controller, "llm", None)
        if llm is None:
            return
        self.usage_refresh.setEnabled(False)

        def done(future) -> None:
            try:
                text = future.result()
            except Exception:
                text = llm.usage.report(self.settings.providers_with_keys())
            self._usage_ready.emit(text)

        try:
            self.controller.runner.submit(llm.usage_report()).add_done_callback(done)
        except Exception:
            self._show_usage(llm.usage.report(self.settings.providers_with_keys()))

    def _show_usage(self, text: str) -> None:
        self.usage_refresh.setEnabled(True)
        lines = []
        for line in text.splitlines():
            name, _, rest = line.partition(": ")
            lines.append(f"<b>{name}</b> — {rest}" if rest else line)
        self.usage_text.setText("<br>".join(lines))

    def _build_voice(self) -> None:
        _, layout = self._page(tr("Voce"))
        layout.addWidget(_section(tr("Capire la voce")))
        self.speech = SpeechSetup()
        layout.addWidget(self.speech)
        layout.addWidget(_section(tr("La voce di Ressy")))
        form = _form()
        self.tts_engine = _combo(
            [("edge", tr("Voce neurale Microsoft (online)")), ("sapi", tr("Voce di Windows (offline)"))], "edge"
        )
        self.tts_engine.currentIndexChanged.connect(self._engine_changed)
        form.addRow(tr("Motore"), self.tts_engine)
        self.tts_voice = _combo(list(EDGE_VOICES.items()), "")
        form.addRow(tr("Voce"), self.tts_voice)
        rate_row = QHBoxLayout()
        self.tts_rate = QSlider(Qt.Orientation.Horizontal)
        self.tts_rate.setRange(-50, 50)
        self.tts_rate.setSingleStep(5)
        self.tts_rate.setPageStep(10)
        self.rate_label = QLabel()
        self.rate_label.setFixedWidth(52)
        self.tts_rate.valueChanged.connect(lambda v: self.rate_label.setText(f"{v:+d}%"))
        rate_row.addWidget(self.tts_rate, 1)
        rate_row.addWidget(self.rate_label)
        form.addRow(tr("Velocità"), rate_row)
        layout.addLayout(form)
        self.sounds = QCheckBox(tr("Suoni dell'interfaccia (tasto, risveglio, fine)"))
        layout.addWidget(self.sounds)
        test_row = QHBoxLayout()
        test = QPushButton(tr("Prova la voce"))
        test.clicked.connect(self._test_voice)
        test_row.addWidget(test)
        test_row.addStretch(1)
        layout.addLayout(test_row)
        layout.addWidget(_hint(
            tr("La voce neurale richiede internet; la voce di Windows funziona anche offline. "
            "Se la prima non risponde, Ressy usa automaticamente la seconda.")
        ))
        layout.addStretch(1)

    def _build_keys(self) -> None:
        _, layout = self._page(tr("Tasto e ascolto"))
        form = _form()
        self.hotkey = KeyCapture(self.settings.hotkey_vk, self.settings.hotkey_name)
        self.hotkey.capturing.connect(self._capturing)
        key_row = QHBoxLayout()
        key_row.addWidget(self.hotkey)
        key_row.addStretch(1)
        form.addRow(tr("Tasto per parlare"), key_row)
        self.hold_ms = QSpinBox()
        self.hold_ms.setRange(150, 2000)
        self.hold_ms.setSingleStep(50)
        self.hold_ms.setSuffix(" ms")
        form.addRow(tr("Tienilo premuto per"), self.hold_ms)
        self.wake_phrases = QLineEdit()
        self.wake_phrases.setPlaceholderText(tr("ressy sveglia, sveglia ressy"))
        form.addRow(tr("Frasi di risveglio"), self.wake_phrases)
        self.listen_mode = _combo(
            [("continuous", tr("Ascolta sempre: basta parlare")), ("push_to_talk", tr("Solo mentre tengo premuto il tasto"))],
            "continuous",
        )
        form.addRow(tr("Quando è sveglia"), self.listen_mode)
        self.auto_sleep = QSpinBox()
        self.auto_sleep.setRange(15, 3600)
        self.auto_sleep.setSingleStep(15)
        self.auto_sleep.setSuffix(tr(" s di silenzio"))
        form.addRow(tr("Si addormenta dopo"), self.auto_sleep)
        self.mic_device = QComboBox()
        form.addRow(tr("Microfono"), self.mic_device)
        self.output_device = QComboBox()
        form.addRow(tr("Altoparlanti"), self.output_device)
        layout.addLayout(form)
        layout.addWidget(_hint(
            tr("Un tocco veloce scrive la lettera come sempre; tenendo premuto parli con Ressy. "
            "Mentre Ressy dorme il microfono resta chiuso: si apre solo mentre tieni premuto il tasto.")
        ))
        layout.addStretch(1)

    def _build_remote(self) -> None:
        _, layout = self._page(tr("Da remoto"))
        layout.addWidget(_hint(
            tr("Ressy non usa un bot condiviso: il bot è tuo, e gira su questo PC o su un tuo server.")
        ))
        self.bot_setup = BotSetup()
        layout.addWidget(self.bot_setup)
        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.presence = PresenceLight()
        self.remote_status = QLabel()
        status_row.addWidget(self.presence)
        status_row.addWidget(self.remote_status, 1)
        layout.addLayout(status_row)
        form = _form()
        self.device_name = QLineEdit()
        self.device_name.setMaxLength(64)
        form.addRow(tr("Nome di questo PC"), self.device_name)
        layout.addLayout(form)
        pair_row = QHBoxLayout()
        pair = QPushButton(tr("Collega Telegram o Discord…"))
        pair.setObjectName("primary")
        pair.clicked.connect(self._open_pairing)
        pair_row.addWidget(pair)
        pair_row.addStretch(1)
        layout.addLayout(pair_row)
        layout.addWidget(_section(tr("Account collegati")))
        self.links_list = QListWidget()
        self.links_list.setObjectName("links")
        self.links_list.setMinimumHeight(96)
        self.links_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self.links_list)
        self.speak_remote = QCheckBox(tr("Leggi ad alta voce sul PC le risposte ai comandi remoti"))
        self.notify_remote = QCheckBox(tr("Mostra una notifica sul PC per ogni comando remoto"))
        layout.addWidget(self.speak_remote)
        layout.addWidget(self.notify_remote)
        layout.addWidget(_section(tr("Avanzate")))
        reset_row = QHBoxLayout()
        reset = QPushButton(tr("Nuova identità per questo PC…"))
        reset.clicked.connect(self._reset_identity)
        reset_row.addWidget(reset)
        reset_row.addStretch(1)
        layout.addLayout(reset_row)
        layout.addWidget(_hint(
            tr("Solo gli account che colleghi con un codice possono comandare questo PC. "
            "Una nuova identità scollega tutti gli account.")
        ))
        layout.addStretch(1)

    def _build_info(self) -> None:
        _, layout = self._page("Info")
        layout.addWidget(QLabel(f"Ressy {__version__}"))
        layout.addWidget(_hint(
            tr("Software libero con licenza MIT. ") + _link("ressy.top", "https://ressy.top")
        ))
        layout.addWidget(_hint(
            tr("Le chiavi API e l'identità del PC sono cifrate con Windows (DPAPI) e valgono solo per il tuo "
            "utente su questo PC. I registri non contengono il testo dei messaggi.")
        ))
        row = QHBoxLayout()
        logs = QPushButton(tr("Apri la cartella dei registri"))
        logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir()))))
        apps = QPushButton(tr("Aggiorna l'elenco dei programmi"))
        apps.clicked.connect(self.controller.refresh_apps)
        row.addWidget(logs)
        row.addWidget(apps)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)

    def open_with(self, reason: str = "") -> None:
        self._load()
        if reason:
            self.banner.setText(reason)
            self.banner.show()
        else:
            self.banner.hide()
        if any(word in reason for word in ("modello vocale", "voce con", tr("modello vocale"), tr("voce con"))):
            self.nav.setCurrentRow(PAGES.index(tr("Voce")))
        elif not self.settings.provider_key(self.settings.llm_provider) or "chiave" in reason or tr("chiave") in reason:
            self.nav.setCurrentRow(PAGES.index(tr("Intelligenza")))
            self.brain.focus_key()
        self.show()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        style_title_bar(self)

    def _load(self) -> None:
        s = self.settings
        self.error.hide()
        self.user_name.setText(s.user_name)
        self.home_city.setText(s.home_city)
        self._shown_language = s.language
        self.language.setCurrentIndex(max(0, self.language.findData(s.language)))
        self.autostart.setChecked(autostart_enabled())

        self.brain.load(
            s.llm_provider,
            {"groq": s.groq_api_key, "claude": s.anthropic_api_key, "gemini": s.gemini_api_key,
             "openrouter": s.openrouter_api_key},
            {"groq": s.llm_model, "claude": s.claude_model, "gemini": s.gemini_model,
             "openrouter": s.openrouter_model or "auto"},
            s.local_llm_model,
        )
        self.fallback.setChecked(s.llm_fallback)
        self.quick.setChecked(s.quick_commands)
        self.auto_update.setChecked(s.auto_update)
        llm = getattr(self.controller, "llm", None)
        if llm is not None and hasattr(llm, "usage"):
            self._show_usage(llm.usage.report(s.providers_with_keys()))
        self.speech.load(s.speech_engine, s.local_stt_model)

        self.tts_engine.setCurrentIndex(max(0, self.tts_engine.findData(s.tts_engine)))
        index = self.tts_voice.findData(s.tts_voice)
        if index < 0:
            self.tts_voice.addItem(s.tts_voice, s.tts_voice)
            index = self.tts_voice.count() - 1
        self.tts_voice.setCurrentIndex(index)
        self.tts_rate.setValue(s.tts_rate)
        self.rate_label.setText(f"{s.tts_rate:+d}%")
        self.sounds.setChecked(s.sounds_enabled)
        self._engine_changed()

        self.hotkey.set_key(s.hotkey_vk, s.hotkey_name)
        self.hold_ms.setValue(s.hotkey_hold_ms)
        self.wake_phrases.setText(", ".join(s.wake_phrases))
        self.listen_mode.setCurrentIndex(max(0, self.listen_mode.findData(s.listen_mode)))
        self.auto_sleep.setValue(s.auto_sleep_seconds)
        self._fill_devices(self.mic_device, devices.input_devices(), s.mic_device)
        self._fill_devices(self.output_device, devices.output_devices(), s.output_device)

        self.bot_setup.load(
            enabled=s.remote_enabled, mode=s.remote_mode, server_url=s.server_url,
            telegram=s.telegram_token, discord=s.discord_token,
        )
        self.device_name.setText(s.device_name)
        self.speak_remote.setChecked(s.speak_remote_replies)
        self.notify_remote.setChecked(s.notify_remote_commands)
        self._on_remote_state(self.controller.remote.state, self.controller.remote.detail)
        self._fill_links(self.controller.remote.links)

    @staticmethod
    def _fill_devices(combo: QComboBox, names: list[str], current: str) -> None:
        combo.clear()
        combo.addItem(tr("Predefinito di Windows"), "")
        for name in names:
            combo.addItem(name, name)
        if current and combo.findData(current) < 0:
            combo.addItem(tr("{current} (non collegato)").format(current=current), current)
        combo.setCurrentIndex(max(0, combo.findData(current)))

    def _language_changed(self) -> None:
        code = self.language.currentData() or "it"
        if code == self._shown_language:
            return
        self._shown_language = code
        index = self.tts_voice.findData(voice_for(code, self.tts_voice.currentData() or ""))
        if index >= 0:
            self.tts_voice.setCurrentIndex(index)
        self.wake_phrases.setText(", ".join(wake_phrases_for(code, self._phrases())))

    def _engine_changed(self) -> None:
        self.tts_voice.setEnabled(self.tts_engine.currentData() == "edge")

    def _capturing(self, active: bool) -> None:
        self.controller.hotkey.enabled = not active

    def _test_voice(self) -> None:
        if self._voice_backup is None:
            s = self.settings
            self._voice_backup = {"tts_engine": s.tts_engine, "tts_voice": s.tts_voice, "tts_rate": s.tts_rate}
        self.controller.apply_settings(**self._voice_changes())
        self.controller.say(VOICE_TEST)

    def _voice_changes(self) -> dict[str, Any]:
        return {
            "tts_engine": self.tts_engine.currentData(),
            "tts_voice": self.tts_voice.currentData(),
            "tts_rate": int(self.tts_rate.value()),
        }

    def _on_remote_state(self, state: str, detail: str) -> None:
        self.presence.set_online(state == "online")
        text = PRESENCE_TEXT.get(state, tr("Offline"))
        explain = {
            "online": tr("Puoi comandare questo PC da Telegram e Discord."),
            "connecting": tr("Mi sto collegando al bot."),
            "bot_error": detail,
            "offline": tr("Non riesco a raggiungere il server: riprovo da sola."),
            "disabled": tr("I comandi da remoto sono disattivati, o manca il token del bot."),
            "auth_failed": tr("Il server ha rifiutato questo PC. Prova con una nuova identità."),
            "outdated": tr("Questa versione di Ressy è troppo vecchia per il server: aggiornala."),
            "replaced": tr("Questa identità è in uso su un altro PC."),
        }.get(state, "")
        self.remote_status.setText(f"<b>{text}</b> · {explain}" if explain else f"<b>{text}</b>")

    def _fill_links(self, links: list) -> None:
        self.links_list.clear()
        if not links:
            item = QListWidgetItem(tr("Nessun account collegato."))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.links_list.addItem(item)
            return
        for link in links:
            platform = {"telegram": "Telegram", "discord": "Discord"}.get(str(link.get("platform")), "Chat")
            display = str(link.get("display") or link.get("user_id") or "")
            since = ""
            if link.get("linked_at"):
                when = dt.datetime.fromtimestamp(float(link["linked_at"]))
                since = tr(" · dal {date}").format(date=when.strftime(tr("%d/%m/%Y")))
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(10, 6, 6, 6)
            label = QLabel(f"<b>{platform}</b> · {display}{since}")
            unlink = QPushButton(tr("Scollega"))
            unlink.clicked.connect(lambda _=False, l=dict(link), d=display, p=platform: self._unlink(l, d, p))
            h.addWidget(label, 1)
            h.addWidget(unlink)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self.links_list.addItem(item)
            self.links_list.setItemWidget(item, row)

    def _unlink(self, link: dict, display: str, platform: str) -> None:
        answer = QMessageBox.question(
            self, tr("Scollega account"),
            tr("Scollegare {display} ({platform})? Non potrà più comandare questo PC finché non lo ricolleghi.").format(display=display, platform=platform),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.unlink(str(link.get("platform")), str(link.get("user_id")))

    def _reset_identity(self) -> None:
        answer = QMessageBox.question(
            self, tr("Nuova identità"),
            tr("Creare una nuova identità per questo PC? Tutti gli account collegati verranno scollegati "
            "e dovrai ricollegarli con un nuovo codice."),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.reset_identity()

    def _phrases(self) -> list[str]:
        return [p.strip().lower() for p in self.wake_phrases.text().replace(";", ",").split(",") if p.strip()]

    def _changes(self) -> dict[str, Any] | str:
        phrases = self._phrases()
        if not phrases:
            return tr("Scrivi almeno una frase di risveglio, per esempio «ressy sveglia».")
        brain = self.brain.values()
        keys = {"groq": brain["groq_api_key"], "claude": brain["anthropic_api_key"], "gemini": brain["gemini_api_key"]}
        problem = (self.brain.problem() or self.speech.problem(keys) or self.bot_setup.problem())
        if problem:
            return problem
        values: dict[str, Any] = {
            "user_name": self.user_name.text().strip(),
            "home_city": self.home_city.text().strip(),
            "language": self.language.currentData(),
            **brain,
            "llm_fallback": self.fallback.isChecked(),
            "quick_commands": self.quick.isChecked(),
            "auto_update": self.auto_update.isChecked(),
            **self.speech.values(),
            **self._voice_changes(),
            "sounds_enabled": self.sounds.isChecked(),
            "hotkey_vk": self.hotkey.vk,
            "hotkey_name": self.hotkey.name,
            "hotkey_hold_ms": int(self.hold_ms.value()),
            "wake_phrases": phrases,
            "listen_mode": self.listen_mode.currentData(),
            "auto_sleep_seconds": int(self.auto_sleep.value()),
            "mic_device": self.mic_device.currentData() or "",
            "output_device": self.output_device.currentData() or "",
            **self.bot_setup.values(),
            "device_name": self.device_name.text().strip() or self.settings.device_name,
            "speak_remote_replies": self.speak_remote.isChecked(),
            "notify_remote_commands": self.notify_remote.isChecked(),
            "first_run_done": True,
        }
        if values["stt_engine"] == self.settings.speech_engine:
            values.pop("stt_engine")
        return {k: v for k, v in values.items() if getattr(self.settings, k) != v}

    def _save(self) -> None:
        changes = self._changes()
        if isinstance(changes, str):
            self.error.setText(changes)
            self.error.show()
            return
        try:
            if self.autostart.isChecked() != autostart_enabled():
                set_autostart(self.autostart.isChecked())
        except OSError:
            self.error.setText(tr("Non riesco a modificare l'avvio automatico di Windows."))
            self.error.show()
            return
        if changes:
            self.controller.apply_settings(**changes)
        self._voice_backup = None
        self.accept()
        if "language" in changes and self._restart is not None:
            new = changes["language"]
            title = "Ressy"
            text = (
                "Ressy will restart now to speak English." if new == "en"
                else "Ressy si riavvia adesso per parlare in italiano."
            )
            QMessageBox.information(self, title, text)
            self._restart()

    def reject(self) -> None:
        if self._voice_backup is not None:
            self.controller.apply_settings(**self._voice_backup)
            self._voice_backup = None
        self.hotkey.stop()
        super().reject()

    def done(self, result: int) -> None:
        self.hotkey.stop()
        self.speech.cancel_download()
        self.controller.hotkey.enabled = True
        super().done(result)
