from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
import zipfile
from pathlib import Path

for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QObject, QRectF, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ressy import __version__, install
from ressy.config import Settings
from ressy.ui import logo, theme
from ressy.ui.bot_setup import TOKEN_HELP, BotSetup, TokenFields, check_token, hint
from ressy.ui.brain_setup import BrainSetup, SpeechSetup
from ressy.ui.voice_trial import VoiceTrial, settings_for_trial


UPDATE = "--update" in sys.argv[1:]


def payload_path() -> Path:
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    if files:
        return Path(files[0])
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "payload" / "Ressy-win64.zip"


class Mark(QWidget):
    def __init__(self, size: int = 56) -> None:
        super().__init__()
        self.setFixedSize(QSize(size, size))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        logo.paint_mark(p, QRectF(0, 0, self.width(), self.height()))
        p.end()


def title(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(theme.font(28, 800, 112))
    label.setStyleSheet("font-size: 28px; font-weight: 800;")
    label.setWordWrap(True)
    return label


def section(text: str) -> QLabel:
    label = QLabel(text.upper())
    f = theme.font(11, 700, 108)
    label.setFont(f)
    label.setStyleSheet(f"color: {theme.LEGEND_DIM}; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
    return label


class StepRail(QWidget):

    def __init__(self) -> None:
        super().__init__()
        self.steps: list[str] = []
        self.current = 0
        self.setFixedWidth(200)

    def set_steps(self, steps: list[str], current: int) -> None:
        self.steps, self.current = steps, current
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = 8.0
        for index, name in enumerate(self.steps):
            done, now = index < self.current, index == self.current
            dot = QRectF(4, y, 28, 28)
            if index < len(self.steps) - 1:
                p.setPen(QPen(QColor(theme.ACCENT if done else theme.FIELD_EDGE), 2))
                p.drawLine(dot.center().x(), dot.bottom() + 4, dot.center().x(), dot.bottom() + 26)
            p.setPen(QPen(QColor(theme.ACCENT if (done or now) else theme.FIELD_EDGE), 1.4))
            p.setBrush(QColor(theme.ACCENT if done else ("#2F2548" if now else theme.FIELD)))
            p.drawRoundedRect(dot, 8, 8)
            p.setFont(theme.font(13, 800))
            p.setPen(QColor(theme.INK if done else (theme.LILAC if now else theme.LEGEND_DIM)))
            if done:
                path = QPainterPath()
                path.moveTo(dot.left() + 8.5, dot.center().y() + 0.5)
                path.lineTo(dot.left() + 12.5, dot.bottom() - 9)
                path.lineTo(dot.right() - 8, dot.top() + 9.5)
                p.setPen(QPen(QColor(theme.INK), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                              Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
            else:
                p.drawText(dot, Qt.AlignmentFlag.AlignCenter, str(index + 1))
            p.setFont(theme.font(14, 700 if now else 500, 106 if now else 100))
            p.setPen(QColor(theme.LEGEND if (now or done) else theme.LEGEND_DIM))
            p.drawText(QRectF(dot.right() + 12, y, self.width() - dot.right() - 12, 28),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
            y += 58
        p.end()


class Backdrop(QWidget):

    divider = True

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.PLATE))
        glow = QRadialGradient(120, 40, 420)
        glow.setColorAt(0, theme.color(theme.ACCENT, 0.20))
        glow.setColorAt(0.5, theme.color(theme.ACCENT, 0.05))
        glow.setColorAt(1, theme.color(theme.ACCENT, 0.0))
        p.fillRect(self.rect(), glow)
        if self.divider:
            p.setPen(QPen(QColor(theme.PLATE_EDGE), 1))
            p.drawLine(236, 96, 236, self.height() - 24)
        p.end()


def copy_payload(folder: Path, progress) -> None:
    if (folder / install.APP_EXE).exists():
        shutil.rmtree(folder / "_internal", ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(payload_path()) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        for i, member in enumerate(members):
            parts = Path(member.filename).parts
            rel = Path(*parts[1:]) if parts and parts[0] == "Ressy" else Path(*parts)
            target = (folder / rel).resolve()
            if folder.resolve() not in target.parents:
                raise RuntimeError(f"percorso non valido nel pacchetto: {member.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            if i % 40 == 0:
                progress(i / max(1, len(members)))


class Updater(QObject):

    step = Signal(str, int)
    finished = Signal(str)

    def __init__(self, folder: Path) -> None:
        super().__init__()
        self.folder = folder
        self.server_was_running = False

    def run(self) -> None:
        try:
            self._run()
            self.finished.emit("")
        except Exception as exc:
            traceback.print_exc()
            self.finished.emit(f"{type(exc).__name__}: {exc}")

    def _run(self) -> None:
        folder = self.folder
        self.step.emit("Chiudo Ressy…", 5)
        install.ask_app_to_quit()
        self.server_was_running = install.stop_server()
        if not install.wait_unlocked(folder, 20):
            raise RuntimeError("Ressy.exe è ancora in uso: chiudi Ressy e riprova.")
        self.step.emit("Copio i file…", 15)
        copy_payload(folder, lambda pct: self.step.emit("Copio i file…", 15 + int(75 * pct)))
        size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) // 1024
        install.register_uninstall(folder, size)
        self.step.emit("Fatto: riavvio Ressy…", 100)


class UpdateWindow(Backdrop):

    divider = False

    def __init__(self, folder: Path) -> None:
        super().__init__()
        self.folder = folder
        self.setWindowTitle("Aggiorno Ressy")
        self.setWindowIcon(logo.app_icon())
        self.setFixedSize(QSize(520, 230))
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(14)
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(Mark(40))
        head.addWidget(title("Aggiorno Ressy"), 1)
        version = QLabel(f"versione {__version__}")
        version.setObjectName("hint")
        head.addWidget(version, 0, Qt.AlignmentFlag.AlignBottom)
        v.addLayout(head)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        v.addWidget(self.bar)
        self.status = QLabel("Un momento…")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        v.addStretch(1)
        self.close_button = QPushButton("Chiudi")
        self.close_button.clicked.connect(QApplication.quit)
        self.close_button.hide()
        v.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignRight)

        self.thread = QThread(self)
        self.worker = Updater(folder)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.step.connect(lambda text, pct: (self.status.setText(text), self.bar.setValue(pct)))
        self.worker.finished.connect(self._done)
        self.worker.finished.connect(self.thread.quit)
        self.thread.start()

    def _done(self, error: str) -> None:
        exe = self.folder / install.APP_EXE
        if exe.exists():
            flags = install.DETACHED_PROCESS
            if self.worker.server_was_running:
                subprocess.Popen([str(exe), "--server"], creationflags=flags, close_fds=True)
            subprocess.Popen([str(exe), "--background"], creationflags=flags, close_fds=True)
        if error:
            self.status.setText(f"Aggiornamento non riuscito: {error}\nPuoi scaricare Ressy da ressy.top.")
            self.close_button.show()
            return
        from PySide6.QtCore import QTimer

        QTimer.singleShot(800, QApplication.quit)


class Installer(QObject):
    step = Signal(str, int)
    finished = Signal(str)

    def __init__(self, plan: dict) -> None:
        super().__init__()
        self.plan = plan
        self.warning = ""

    def run(self) -> None:
        try:
            self._run()
            self.finished.emit("")
        except Exception as exc:
            traceback.print_exc()
            self.finished.emit(f"{type(exc).__name__}: {exc}")

    def _run(self) -> None:
        plan = self.plan
        folder: Path = plan["folder"]
        exe = folder / install.APP_EXE

        self.step.emit("Chiudo Ressy, se è aperta…", 5)
        install.ask_app_to_quit()
        install.stop_server()
        if not install.wait_unlocked(folder, 15):
            raise RuntimeError("Ressy.exe è ancora in uso: chiudi Ressy e riprova.")

        copy_payload(folder, lambda pct: self.step.emit("Copio i file…", 15 + int(60 * pct)))

        self.step.emit("Salvo le impostazioni…", 78)
        if plan["server"]:
            cfg = install.ServerConfig.load()
            cfg.telegram_token = plan["server_tokens"]["telegram_token"]
            cfg.discord_token = plan["server_tokens"]["discord_token"]
            cfg.port = plan["port"]
            cfg.save()
        if plan["app"]:
            settings = Settings.load()
            settings.ensure_identity()
            for key, value in {**plan["remote"], **plan["brain"], **plan["speech"]}.items():
                setattr(settings, key, value)
            settings._sanitize()
            settings.save()

        self.step.emit("Creo i collegamenti…", 85)
        menu = install.start_menu_dir()
        if plan["app"]:
            install.create_shortcut(menu / "Ressy.lnk", exe, "", "Ressy, l'assistente vocale")
            if plan["desktop"]:
                install.create_shortcut(install.desktop_dir() / "Ressy.lnk", exe, "", "Ressy, l'assistente vocale")
        if plan["server"]:
            install.create_shortcut(menu / "Ressy Server.lnk", exe, "--server", "Il server del tuo bot")
            install.create_shortcut(menu / "Ferma Ressy Server.lnk", exe, "--server-stop", "Ferma il server del bot")
        install.create_shortcut(menu / "Disinstalla Ressy.lnk", exe, "--uninstall", "Disinstalla Ressy")

        self.step.emit("Avvio con Windows…", 92)
        quoted = subprocess.list2cmdline([str(exe)])
        install.set_run(install.RUN_APP, f"{quoted} --background" if plan["app"] and plan["autostart"] else None)
        install.set_run(install.RUN_SERVER, f"{quoted} --server" if plan["server"] else None)

        size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) // 1024
        install.register_uninstall(folder, size)

        model = plan.get("download")
        if model:
            from ressy.speech import local_stt

            mb = local_stt.size_mb(model)
            self.step.emit(f"Scarico il modello vocale ({mb} MB)…", 86)
            try:
                local_stt.download_model(model, lambda done, total: self.step.emit(
                    f"Scarico il modello vocale… {done / 1e6:.0f} di {total / 1e6:.0f} MB",
                    86 + int(13 * done / max(1, total))))
            except Exception as exc:
                traceback.print_exc()
                self.warning = f"Il modello vocale non si è scaricato ({exc}): Ressy te lo riproporrà nelle impostazioni."
        self.step.emit("Fatto.", 100)


class Setup(Backdrop):
    PAGE_NAMES = {
        "welcome": "Installa",
        "brain": "Intelligenza",
        "voice": "Voce",
        "trial": "Prova",
        "remote": "Telegram e Discord",
        "progress": "Installazione",
        "done": "Fatto",
    }

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Installa Ressy")
        self.setWindowIcon(logo.app_icon())
        self.setMinimumSize(QSize(940, 700))
        self.settings = Settings.load()
        root = QHBoxLayout(self)
        root.setContentsMargins(28, 26, 32, 24)
        root.setSpacing(36)

        left = QVBoxLayout()
        left.setSpacing(30)
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(Mark(40))
        name = QLabel(f"Ressy <span style='color:{theme.LEGEND_DIM}; font-weight:500'>{__version__}</span>")
        name.setFont(theme.font(21, 800, 112))
        head.addWidget(name)
        head.addStretch(1)
        left.addLayout(head)
        self.rail = StepRail()
        left.addWidget(self.rail, 1)
        left.addWidget(hint("Software libero, licenza MIT.<br>Si installa solo per il tuo utente."))
        root.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(16)
        self.pages = QStackedWidget()
        right.addWidget(self.pages, 1)
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()
        right.addWidget(self.error)
        nav = QHBoxLayout()
        self.back = QPushButton("Indietro")
        self.next = QPushButton("Avanti")
        self.next.setObjectName("primary")
        self.next.setMinimumWidth(130)
        self.back.clicked.connect(self._back)
        self.next.clicked.connect(self._next)
        nav.addWidget(self.back)
        nav.addStretch(1)
        nav.addWidget(self.next)
        right.addLayout(nav)
        root.addLayout(right, 1)

        self.page_index: dict[str, int] = {}
        self.current = "welcome"
        self._trial_signature = ""
        self._build_welcome()
        self._build_brain()
        self._build_voice()
        self._build_trial()
        self._build_remote()
        self._build_progress()
        self._build_done()
        self.current = "welcome"
        self._show("welcome")

    @staticmethod
    def _scrolling(page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        page.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        scroll.setWidget(page)
        scroll.viewport().setAutoFillBackground(False)
        return scroll

    def _add(self, key: str, page: QWidget) -> None:
        self.page_index[key] = self.pages.addWidget(page)

    @staticmethod
    def _page(heading: str, intro: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addWidget(title(heading))
        if intro:
            v.addWidget(hint(intro))
        v.addSpacing(4)
        return page, v

    def _build_welcome(self) -> None:
        page, v = self._page(
            "Installa Ressy",
            "L'assistente vocale per Windows: tieni premuto K e di' «Ressy, sveglia!». "
            "Si installa solo per il tuo utente, senza permessi da amministratore.",
        )
        v.addWidget(section("Cosa installare"))
        self.want_app = QCheckBox("Ressy, l'assistente vocale")
        self.want_app.setChecked(True)
        v.addWidget(self.want_app)
        self.want_server = QCheckBox("Ressy Server (self-host), per un PC sempre acceso")
        v.addWidget(self.want_server)
        server_hint = hint(
            "Fa girare il tuo bot Telegram/Discord giorno e notte per i tuoi PC e ti avvisa quando uno va "
            "offline. Non serve se vuoi che il bot giri dentro Ressy su questo PC."
        )
        server_hint.setContentsMargins(28, 0, 0, 0)
        v.addWidget(server_hint)
        v.addSpacing(6)
        v.addWidget(section("Dove"))
        row = QHBoxLayout()
        self.folder = QLineEdit(str(install.installed_dir() or install.default_install_dir()))
        browse = QPushButton("Sfoglia…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        v.addLayout(row)
        self.desktop = QCheckBox("Collegamento sul desktop")
        self.desktop.setChecked(True)
        self.autostart = QCheckBox("Avvia Ressy con Windows")
        self.autostart.setChecked(True)
        v.addWidget(self.desktop)
        v.addWidget(self.autostart)
        self.want_app.toggled.connect(lambda on: (self.desktop.setEnabled(on), self.autostart.setEnabled(on)))
        self.want_app.toggled.connect(lambda _: self._update_rail())
        self.want_server.toggled.connect(lambda _: self._update_rail())
        v.addStretch(1)
        self._add("welcome", page)

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Cartella di Ressy", self.folder.text())
        if chosen:
            path = Path(chosen)
            self.folder.setText(str(path if path.name.lower() == "ressy" else path / "Ressy"))

    def _build_brain(self) -> None:
        page, v = self._page(
            "L'intelligenza di Ressy",
            "Chi capisce cosa chiedi e decide cosa fare sul PC. Ognuno usa la propria chiave API: "
            "crearla è gratis e richiede un minuto.",
        )
        self.brain = BrainSetup(auto_verify=True)
        self.brain.validity.connect(lambda _: self._refresh_next())
        s = self.settings
        self.brain.load(
            s.llm_provider,
            {"groq": s.groq_api_key, "claude": s.anthropic_api_key, "gemini": s.gemini_api_key,
             "openrouter": s.openrouter_api_key},
            {"groq": s.llm_model, "claude": s.claude_model, "gemini": s.gemini_model,
             "openrouter": s.openrouter_model or "auto"},
            s.local_llm_model,
        )
        v.addWidget(self.brain)
        v.addStretch(1)
        self._add("brain", self._scrolling(page))

    def _build_voice(self) -> None:
        page, v = self._page(
            "Come ti ascolta",
            "Per capire la tua voce Ressy può usare un piccolo modello sul PC, gratis e senza limiti, "
            "oppure un servizio online con la tua chiave.",
        )
        self.speech = SpeechSetup(download_now=True)
        self.speech.readiness.connect(lambda _: self._refresh_next())
        self.speech.load(self.settings.speech_engine if self.settings.first_run_done else "local",
                         self.settings.local_stt_model)
        v.addWidget(self.speech)
        v.addStretch(1)
        self._add("voice", page)

    def _build_trial(self) -> None:
        page, v = self._page(
            "Proviamo",
            "Tre prove vere con il tuo microfono, prima di finire: Ressy deve sentirti e capirti. "
            "Avanti si sblocca quando sono riuscite tutte e tre.",
        )
        self.trial = VoiceTrial()
        self.trial.completed.connect(lambda _: self._refresh_next())
        v.addWidget(self.trial)
        v.addStretch(1)
        self._add("trial", page)

    def _trial_settings(self):
        return settings_for_trial(self.settings, {**self.brain.values(), **self.speech.values()})

    def _build_remote(self) -> None:
        page, v = self._page(
            "Telegram e Discord",
            "Nessun bot condiviso: ognuno usa il proprio, così nessuno si pesta i piedi. "
            "Puoi cambiare idea quando vuoi nelle impostazioni di Ressy.",
        )
        self.bot_setup = BotSetup()
        v.addWidget(self.bot_setup)

        self.server_box = QWidget()
        s = QVBoxLayout(self.server_box)
        s.setContentsMargins(0, 0, 0, 0)
        s.setSpacing(10)
        s.addWidget(section("Ressy Server"))
        s.addWidget(hint("Il bot del server: i tuoi PC si collegano a lui."))
        self.server_tokens = TokenFields()
        s.addWidget(self.server_tokens)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(install.ServerConfig.load().port)
        self.port.setMaximumWidth(140)
        form.addRow("Porta", self.port)
        s.addLayout(form)
        s.addWidget(hint(TOKEN_HELP))
        self.app_note = hint("Ressy su questo PC si collegherà da sola a questo server.")
        s.addWidget(self.app_note)
        v.addWidget(self.server_box)
        v.addStretch(1)
        self._add("remote", page)

    def _prepare_remote(self) -> None:
        app, server = self.want_app.isChecked(), self.want_server.isChecked()
        settings = self.settings
        if app and not server:
            self.bot_setup.load(
                enabled=settings.remote_enabled or not settings.first_run_done,
                mode=settings.remote_mode, server_url=settings.server_url,
                telegram=settings.telegram_token, discord=settings.discord_token,
            )
        if server:
            cfg = install.ServerConfig.load()
            self.server_tokens.set_values(cfg.telegram_token or settings.telegram_token,
                                          cfg.discord_token or settings.discord_token)
        self.bot_setup.setVisible(app and not server)
        self.server_box.setVisible(server)
        self.app_note.setVisible(app)

    def _build_progress(self) -> None:
        page, v = self._page("Installo…", "")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        v.addWidget(self.bar)
        v.addWidget(self.status)
        v.addStretch(1)
        self._add("progress", page)

    def _build_done(self) -> None:
        page, v = self._page("Ressy è installata", "")
        self.done_text = hint("")
        v.addWidget(self.done_text)
        self.launch = QCheckBox("Avvia Ressy ora")
        self.launch.setChecked(True)
        v.addWidget(self.launch)
        v.addStretch(1)
        self._add("done", page)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        try:
            from ressy.ui.winframe import style_title_bar

            style_title_bar(self)
        except Exception:
            pass

    def _sequence(self) -> list[str]:
        steps = ["welcome"]
        if self.want_app.isChecked():
            steps += ["brain", "voice", "trial"]
        return steps + ["remote", "progress", "done"]

    def _update_rail(self) -> None:
        rail = [k for k in self._sequence() if k != "progress"]
        current = rail.index("done") if self.current == "progress" else rail.index(self.current)
        self.rail.set_steps([self.PAGE_NAMES[k] for k in rail], current)

    def _step_done(self, key: str) -> bool:
        if key == "brain":
            return self.brain.is_verified()
        if key == "voice":
            return self.speech.is_ready()
        if key == "trial":
            return self.trial.no_microphone or len(self.trial.passed) == 3
        return key != "progress"

    def _refresh_next(self) -> None:
        self.next.setEnabled(self._step_done(self.current))

    def _show(self, key: str) -> None:
        if self.current == "trial" and key != "trial":
            self.trial.stop()
        self.current = key
        self.pages.setCurrentIndex(self.page_index[key])
        self.error.hide()
        steps = self._sequence()
        self.back.setVisible(key not in ("welcome", "progress", "done"))
        if key == "voice":
            self.speech.keys = self._keys()
            self.speech._refresh()
        if key == "trial":
            choices = {**self.brain.values(), **self.speech.values()}
            signature = repr(sorted(choices.items()))
            done = self.trial.no_microphone or len(self.trial.passed) == 3
            if signature != self._trial_signature or not done:
                self._trial_signature = signature
                self.trial.start(self._trial_settings())
        self._refresh_next()
        following = steps[steps.index(key) + 1] if key != "done" else ""
        self.next.setText("Fine" if key == "done" else ("Installa" if following == "progress" else "Avanti"))
        self._update_rail()

    def _fail(self, text: str) -> None:
        self.error.setText(text)
        self.error.show()

    def _back(self) -> None:
        steps = self._sequence()
        self._show(steps[max(0, steps.index(self.current) - 1)])

    def _next(self) -> None:
        key = self.current
        if key == "welcome":
            if not (self.want_app.isChecked() or self.want_server.isChecked()):
                return self._fail("Scegli almeno una cosa da installare.")
            if not self.folder.text().strip():
                return self._fail("Scegli una cartella.")
            self._prepare_remote()
        elif key == "brain":
            problem = self.brain.problem()
            if problem:
                return self._fail(problem)
        elif key == "voice":
            problem = self.speech.problem(self._keys())
            if problem:
                return self._fail(problem)
        if not self._step_done(key):
            return
        elif key == "remote":
            plan = self._plan()
            if isinstance(plan, str):
                return self._fail(plan)
            return self._install(plan)
        elif key == "done":
            return self._finish()
        steps = self._sequence()
        self._show(steps[steps.index(key) + 1])

    def _keys(self) -> dict[str, str]:
        values = self.brain.values()
        return {"groq": values["groq_api_key"], "claude": values["anthropic_api_key"],
                "gemini": values["gemini_api_key"]}

    def _plan(self) -> dict | str:
        app, server = self.want_app.isChecked(), self.want_server.isChecked()
        plan: dict = {
            "app": app, "server": server,
            "folder": Path(self.folder.text().strip()),
            "desktop": self.desktop.isChecked(), "autostart": self.autostart.isChecked(),
            "port": int(self.port.value()), "remote": {}, "server_tokens": {},
            "brain": {}, "speech": {}, "download": "",
        }
        if app:
            plan["brain"] = self.brain.values()
            plan["speech"] = self.speech.values()
            if self.speech.needs_download():
                plan["download"] = plan["speech"]["local_stt_model"]
        if server:
            tokens = self.server_tokens.values()
            if not tokens["telegram_token"] and not tokens["discord_token"]:
                return "Incolla il token del bot per il server."
            problem = check_token("telegram", tokens["telegram_token"]) or check_token("discord", tokens["discord_token"])
            if problem:
                return problem
            plan["server_tokens"] = tokens
            if app:
                plan["remote"] = {"remote_enabled": True, "remote_mode": "server",
                                  "server_url": f"ws://127.0.0.1:{plan['port']}/ws/agent"}
        elif app:
            problem = self.bot_setup.problem()
            if problem:
                return problem
            plan["remote"] = self.bot_setup.values()
        return plan

    def _install(self, plan: dict) -> None:
        self.plan = plan
        self._show("progress")
        self.thread = QThread(self)
        self.worker = Installer(plan)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.step.connect(lambda text, pct: (self.status.setText(text), self.bar.setValue(pct)))
        self.worker.finished.connect(self._installed)
        self.worker.finished.connect(self.thread.quit)
        self.thread.start()

    def _installed(self, error: str) -> None:
        if error:
            self._show("remote")
            self._fail(f"Installazione non riuscita: {error}")
            return
        plan = self.plan
        lines = [f"Ressy è in <b>{plan['folder']}</b>. La trovi nel menu Start; si disinstalla da "
                 "Impostazioni › App, come ogni altro programma."]
        if plan["app"]:
            from ressy.config import PROVIDER_NAMES

            brain = PROVIDER_NAMES.get(plan["brain"].get("llm_provider", ""), "")
            engine = plan["speech"].get("stt_engine", "")
            ear = "il modello sul PC" if engine == "local" else PROVIDER_NAMES.get(engine, "")
            lines.append(f"Ressy pensa con <b>{brain}</b> e ti ascolta con <b>{ear}</b>. "
                         "Tieni premuto K e di' «Ressy, sveglia!».")
            if plan["remote"].get("remote_mode") == "local" and plan["remote"].get("remote_enabled"):
                lines.append("Per comandarla dal telefono: icona di Ressy › «Collega Telegram o Discord…» e "
                             "scrivi il codice al tuo bot.")
        if self.worker.warning:
            lines.append(f"<span style='color:#FF8C73'>{self.worker.warning}</span>")
        if plan["server"]:
            ips = install.lan_addresses()
            where = ", ".join(f"<code>ws://{ip}:{plan['port']}/ws/agent</code>" for ip in ips) or \
                f"<code>ws://IP-di-questo-PC:{plan['port']}/ws/agent</code>"
            lines.append(
                "Ressy Server parte con Windows. Sugli altri PC, in Ressy › Impostazioni › Da remoto, scegli "
                f"«Il tuo server» e scrivi {where}. Se Windows chiede di consentire l'accesso alla rete, "
                "consenti le reti private."
            )
        self.done_text.setText("<br><br>".join(lines))
        self.launch.setVisible(plan["app"] or plan["server"])
        self.launch.setText("Avvia Ressy ora" if plan["app"] else "Avvia Ressy Server ora")
        self._show("done")

    def _finish(self) -> None:
        if self.launch.isChecked():
            exe = self.plan["folder"] / install.APP_EXE
            flags = install.DETACHED_PROCESS
            if self.plan["server"]:
                subprocess.Popen([str(exe), "--server"], creationflags=flags, close_fds=True)
            if self.plan["app"]:
                subprocess.Popen([str(exe)], creationflags=flags, close_fds=True)
        QApplication.quit()


def main() -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv[:1])
    app.setFont(theme.font(14))
    app.setStyleSheet(theme.stylesheet())
    if not payload_path().exists():
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(None, "Ressy", "Il pacchetto di installazione è danneggiato: scaricalo di nuovo.")
        return 1
    folder = install.installed_dir() if UPDATE else None
    if UPDATE and folder is not None and (folder / install.APP_EXE).exists():
        window = UpdateWindow(folder)
    else:
        window = Setup()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
