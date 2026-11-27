from __future__ import annotations

import asyncio
import base64
import binascii
import concurrent.futures
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import numpy as np

from ..audio import sounds
from ..audio.mic import RATE, Microphone, MicError
from ..audio.player import AudioPlayer
from ..audio.vad import PushToTalkBuffer, UtteranceDetector
from ..brain import prompts
from ..brain.agent import Brain, TurnResult
from ..brain.groq import GroqAuthError, GroqError, GroqRateLimited, GroqUnavailable
from ..brain.providers import LLMRouter
from ..config import Settings
from ..paths import app_dir
from ..remote.client import RemoteClient
from ..remote.local_bot import BotError, LocalBot
from ..speech.stt import SpeechToText
from ..speech.tts import Speaker
from ..speech.wake import is_sleep_command, loose_wake, match_wake
from ..speech.textnorm import normalize
from ..tools import build_registry
from ..tools.apps import AppIndex
from ..tools.registry import Channel
from ..tools.reminders import Reminder, ReminderService
from .hotkey import HoldHotkey
from .runner import AsyncRunner
from .services import Services
from ..i18n import tr

log = logging.getLogger("ressy.controller")

ASLEEP = "asleep"
LISTENING = "listening"
HEARING = "hearing"
THINKING = "thinking"
SPEAKING = "speaking"

VOICE = Channel("voice")
PTT_MAX_S = 60.0
MIN_PTT_SECONDS = 0.35
PREROLL_FRAMES = 50
PREROLL_LEAD_S = 0.28
WARM_MIC_S = 2.5
REMOTE_TIMEOUT_S = 140.0
VOICE_TIMEOUT_S = 300.0
MAX_REPLY_TEXT = 8000
MAX_IMAGE_BYTES = 9 * 1024 * 1024
MAX_VOICE_BYTES = 20 * 1024 * 1024

POPULAR_APPS = (
    "spotify", "discord", "google chrome", "steam", "telegram", "whatsapp", "word", "excel", "powerpoint",
    "visual studio code", "obs studio", "epic games launcher", "minecraft launcher", "fortnite", "roblox player",
    "microsoft edge", "firefox", "teams", "zoom", "notion", "blocco note", "notepad", "calcolatrice", "calculator",
    "battle net", "riot client", "valorant", "league of legends", "netflix", "prime video", "capcut", "photoshop",
)

TOOL_STATUS = {
    "open_app": tr("Apro il programma…"),
    "close_app": tr("Chiudo il programma…"),
    "list_windows": tr("Guardo le finestre aperte…"),
    "focus_app": tr("Cambio finestra…"),
    "window_action": tr("Sistemo la finestra…"),
    "send_discord_message": tr("Scrivo su Discord…"),
    "read_discord_chat": tr("Leggo Discord…"),
    "send_telegram_message": tr("Scrivo su Telegram…"),
    "call_phone": tr("Avvio la chiamata…"),
    "open_url": tr("Apro il browser…"),
    "web_search": tr("Cerco sul web…"),
    "read_webpage": tr("Leggo la pagina web…"),
    "compose_email": tr("Preparo l’email…"),
    "play_youtube": tr("Cerco su YouTube…"),
    "web_answer": tr("Cerco sul web…"),
    "media_control": tr("Controllo la musica…"),
    "set_volume": tr("Regolo il volume…"),
    "take_screenshot": tr("Faccio uno screenshot…"),
    "pc_power": tr("Gestisco l’alimentazione…"),
    "system_status": tr("Controllo il PC…"),
    "system_control": tr("Regolo le impostazioni del PC…"),
    "open_folder": tr("Apro la cartella…"),
    "type_text": tr("Scrivo…"),
    "press_keys": tr("Premo i tasti…"),
    "mouse_action": tr("Muovo il mouse…"),
    "set_clipboard": tr("Copio negli appunti…"),
    "clipboard": tr("Gestisco gli appunti…"),
    "reminder": tr("Gestisco i promemoria…"),
    "timer": tr("Gestisco timer e cronometro…"),
    "create_file": tr("Creo il file…"),
    "create_folder": tr("Creo la cartella…"),
    "file_action": tr("Sistemo i file…"),
    "find_files": tr("Cerco i file…"),
    "notes": tr("Aggiorno le note…"),
    "wait": tr("Aspetto…"),
    "read_file": tr("Leggo il file…"),
    "list_folder": tr("Guardo nella cartella…"),
    "write_in_app": tr("Scrivo nell’app…"),
    "read_screen": tr("Guardo lo schermo…"),
    "click_text": tr("Clicco…"),
    "weather": tr("Guardo il meteo…"),
    "record_video": tr("Registro il video…"),
    "edit_video": tr("Edito il video…"),
    "run_python": tr("Eseguo uno script Python…"),
    "download_file": tr("Scarico il file…"),
    "run_powershell": tr("Eseguo un comando…"),
}


class UiSink(Protocol):
    def state(self, state: str) -> None: ...
    def show_hud(self) -> None: ...
    def hide_hud(self) -> None: ...
    def ressy_line(self, text: str) -> None: ...
    def user_line(self, text: str, final: bool) -> None: ...
    def status(self, text: str) -> None: ...
    def remote_state(self, state: str, detail: str) -> None: ...
    def links(self, links: list) -> None: ...
    def linked(self, link: dict) -> None: ...
    def pair_code(self, data: dict) -> None: ...
    def pair_error(self, text: str) -> None: ...
    def toast(self, title: str, text: str) -> None: ...
    def open_settings(self, reason: str) -> None: ...


class NullUi:

    def __getattr__(self, name: str) -> Callable[..., None]:
        return lambda *args, **kwargs: None


@dataclass
class VoiceJob:
    pcm: np.ndarray
    gen: int
    was_asleep: bool
    push_to_talk: bool


@dataclass
class RemoteJob:
    message: dict[str, Any]
    future: asyncio.Future


@dataclass
class AnnounceJob:
    text: str


@dataclass
class WakeJob:
    pass


@dataclass
class ScheduledJob:
    reminder: Reminder
    late: bool


def error_text(exc: BaseException) -> str:
    name = getattr(exc, "provider", "") or "Groq"
    if isinstance(exc, GroqError) and name == "PC":
        return str(exc)
    if isinstance(exc, GroqAuthError):
        return tr("La chiave API di {name} manca o non è valida: controllala nelle impostazioni di Ressy.").format(name=name)
    if isinstance(exc, GroqRateLimited):
        return str(exc)
    if isinstance(exc, GroqUnavailable):
        return tr("Non riesco a raggiungere {name}: controlla la connessione a internet.").format(name=name)
    if isinstance(exc, asyncio.TimeoutError):
        return tr("Ci sto mettendo troppo: riprova tra poco.")
    if isinstance(exc, GroqError):
        return tr("{name} ha restituito un errore, riprova tra poco.").format(name=name)
    return tr("Si è verificato un errore imprevisto.")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class Controller:
    def __init__(self, settings: Settings, ui: UiSink | None = None, runner: AsyncRunner | None = None) -> None:
        self.settings = settings
        self.ui: UiSink = ui or NullUi()
        self.runner = runner or AsyncRunner()

        self.mic = Microphone(lambda: self.settings.mic_device)
        self.mic.on_switch = lambda name: self.ui.toast(
            tr("Microfono"), tr("Il microfono predefinito di Windows non manda suono: uso «{name}».").format(name=name))
        self.player = AudioPlayer(lambda: self.settings.output_device)
        self.cue_player = AudioPlayer(lambda: self.settings.output_device)
        self.llm = LLMRouter(settings)
        self.stt = SpeechToText(settings, self.llm, vocabulary=self._vocabulary)
        self.speaker = Speaker(settings, self.player)
        self.apps = AppIndex(app_dir() / "apps.json")
        self.reminders = ReminderService(app_dir() / "reminders.json", self._announce_reminder)
        self.services = Services(settings, self.llm, self.apps, self.reminders, ui=self.ui, stt=self.stt)
        self.brain = Brain(settings, self.llm, build_registry(), self.services)
        self.remote = RemoteClient(settings, self._on_remote_command, self._on_remote_event)
        self.bot = LocalBot(settings, on_error=self.remote.block)
        self.remote.url_provider = self._remote_url
        self.hotkey = HoldHotkey(
            lambda: self.settings.hotkey_vk,
            lambda: self.settings.hotkey_hold_ms,
            on_hold=lambda: self.runner.call(self._on_hold),
            on_release=lambda: self.runner.call(self._on_release),
            on_press=lambda: self.runner.call(self._on_press, time.monotonic()),
        )
        self.vad = UtteranceDetector(
            on_start=lambda: self.runner.call(self._on_vad_start),
            on_utterance=lambda pcm: self.runner.call(self._on_vad_utterance, pcm),
            on_discard=lambda: self.runner.call(self._on_vad_discard),
            end_silence_ms=1150,
            max_utterance_ms=30000,
        )
        self.ptt = PushToTalkBuffer(max_seconds=int(PTT_MAX_S))
        self._preroll: deque[tuple[float, np.ndarray]] = deque(maxlen=PREROLL_FRAMES)
        self._press_at = 0.0
        self._press_seq = 0

        self.state = ASLEEP
        self.awake = False
        self._gen = 0
        self._mode = "off"
        self._vad_epoch = 0
        self._vad_seen = 0
        self._queue: asyncio.Queue | None = None
        self._tasks: list[asyncio.Task] = []
        self._last_activity = time.monotonic()
        self._ptt_deadline: asyncio.TimerHandle | None = None
        self._started = False

    def _vocabulary(self) -> list[str]:
        from ..tools.discord import known_contacts

        names = known_contacts()[:15]
        try:
            installed = {normalize(app.name): app.name for app in self.apps.apps()}
        except Exception:
            installed = {}
        names += [installed[key] for key in POPULAR_APPS if key in installed]
        return names

    def start(self) -> None:
        self.runner.start()
        self.mic.set_consumer(self._on_frame)
        self.runner.submit(self._start_async()).result(timeout=15)
        try:
            self.hotkey.start()
        except Exception:
            log.exception("keyboard hook unavailable")
            self.ui.toast("Ressy", tr("Non riesco a intercettare la tastiera: il tasto per parlare non funzionerà."))
        self._started = True

    async def _start_async(self) -> None:
        self._queue = asyncio.Queue()
        self.reminders.start()
        self.remote.start()
        asyncio.ensure_future(self._sync_bot())
        self._tasks = [
            asyncio.create_task(self._worker(), name="ressy-worker"),
            asyncio.create_task(self._watchdog(), name="ressy-watchdog"),
        ]
        refresh = asyncio.ensure_future(asyncio.to_thread(self.apps.ensure_fresh))
        refresh.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
        from ..paths import trim_memory

        asyncio.get_running_loop().call_later(4.0, trim_memory)
        if self.settings.llm_provider == "local" and self.settings.local_llm_ready():
            asyncio.ensure_future(asyncio.to_thread(self._preload_local_ai))

    def _preload_local_ai(self) -> None:
        try:
            self.llm.local.preload()
        except Exception:
            log.warning("could not start the AI on the PC", exc_info=True)

    def shutdown(self) -> None:
        if not self._started:
            return
        self._started = False
        self.hotkey.stop()
        try:
            self.runner.submit(self._shutdown_async()).result(timeout=20)
        except Exception:
            log.warning("shutdown did not complete cleanly", exc_info=True)
        self.runner.stop()

    async def _shutdown_async(self) -> None:
        self.awake = False
        self._mode = "off"
        self.speaker.interrupt()
        self.cue_player.stop()
        for task in self._tasks:
            task.cancel()
        self.reminders.stop()
        await self.remote.stop("quit")
        await self.bot.stop()
        await asyncio.to_thread(self.mic.stop)
        await self.llm.aclose()

    def wake(self) -> None:
        self.runner.call(self._enqueue, WakeJob())

    def sleep(self) -> None:
        self.runner.call(self._sleep_now)

    def stop_speaking(self) -> None:
        self.speaker.interrupt()

    def say(self, text: str) -> None:
        self.runner.call(self._enqueue, AnnounceJob(text))

    @property
    def listening(self) -> bool:
        return self._mode in ("vad", "ptt")

    def apply_settings(self, **changes: Any) -> None:
        self.runner.call(self._apply_settings, changes)

    def reset_identity(self) -> None:
        def reset() -> None:
            self.settings.reset_identity()
            self.settings.save()
            self.remote.reconnect()

        self.runner.call(reset)

    def request_pair_code(self) -> None:
        async def go() -> None:
            try:
                self.ui.pair_code(await self.remote.request_pair_code())
            except Exception as exc:
                self.ui.pair_error(str(exc) or tr("Il server non ha risposto."))

        self.runner.submit(go())

    def unlink(self, platform: str, user_id: str) -> None:
        async def go() -> None:
            try:
                await self.remote.unlink(platform, user_id)
            except Exception as exc:
                self.ui.toast("Ressy", tr("Non riesco a scollegare: {exc}").format(exc=exc))

        self.runner.submit(go())

    def verify_key(self, provider: str, key: str) -> concurrent.futures.Future:
        return self.runner.submit(self.llm.list_models(key, provider))

    def verify_groq_key(self, key: str) -> concurrent.futures.Future:
        return self.verify_key("groq", key)

    def preload_speech_model(self) -> None:
        self.runner.call(lambda: asyncio.ensure_future(asyncio.to_thread(self._preload_stt)))

    def _preload_stt(self) -> None:
        try:
            self.stt.preload()
        except Exception:
            log.warning("speech model preload failed", exc_info=True)

    def refresh_apps(self) -> None:
        self.runner.call(lambda: asyncio.ensure_future(asyncio.to_thread(self.apps.refresh)))

    def _enqueue(self, job: object) -> None:
        if self._queue is not None:
            self._queue.put_nowait(job)

    def _touch(self) -> None:
        self._last_activity = time.monotonic()

    def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.ui.state(state)

    def _idle_mode(self) -> str:
        return "vad" if self.awake and self.settings.listen_mode == "continuous" else "off"

    def _set_mode(self, mode: str) -> None:
        if mode == "vad" and self._mode != "vad":
            self._vad_epoch += 1
        self._mode = mode

    def _play_cue(self, name: str) -> None:
        if not self.settings.sounds_enabled:
            return
        future = asyncio.ensure_future(
            asyncio.to_thread(self.cue_player.play, sounds.cue(name), sounds.RATE, meter=False)
        )
        future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)

    def _ensure_mic(self) -> None:
        if not self.mic.running:
            self.mic.start()

    def _stop_mic_later(self) -> None:
        future = asyncio.ensure_future(asyncio.to_thread(self.mic.stop))
        future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)

    def _remote_url(self) -> str:
        if self.settings.remote_mode == "local":
            return self.bot.url
        return self.settings.server_url.strip()

    def _bot_key(self) -> tuple:
        s = self.settings
        return (s.remote_enabled, s.remote_mode, s.telegram_token, s.discord_token, s.discord_invite_url)

    async def _sync_bot(self) -> None:
        s = self.settings
        self.remote.unblock()
        if s.remote_enabled and s.remote_mode == "local" and s.has_bot_token:
            try:
                await self.bot.start()
            except BotError as exc:
                self.remote.block(str(exc))
                return
            except Exception as exc:
                log.exception("bot failed to start")
                self.remote.block(tr("Il bot non è partito ({name}).").format(name=type(exc).__name__))
                return
        else:
            await self.bot.stop()
        self.remote.reconnect()

    def _apply_settings(self, changes: dict[str, Any]) -> None:
        old = (self.settings.remote_enabled, self.settings.server_url, self.settings.agent_id)
        old_bot = self._bot_key()
        old_name = self.settings.device_name
        old_mic = self.settings.mic_device
        old_stt = (self.settings.stt_engine, self.settings.local_stt_model)
        self.settings.update(**changes)
        if (self.settings.stt_engine, self.settings.local_stt_model) != old_stt:
            asyncio.ensure_future(asyncio.to_thread(self._preload_stt))
        if self._bot_key() != old_bot:
            asyncio.ensure_future(self._sync_bot())
        elif (self.settings.remote_enabled, self.settings.server_url, self.settings.agent_id) != old:
            self.remote.reconnect()
        elif self.settings.device_name != old_name:
            asyncio.ensure_future(self.remote.rename(self.settings.device_name))
        if self.settings.mic_device != old_mic and self.mic.running:
            self.mic.stop()
            try:
                self._ensure_mic()
            except MicError as exc:
                self.ui.toast(tr("Microfono"), str(exc))
        if self.awake and self._mode != "ptt" and self.state == LISTENING:
            self._set_mode(self._idle_mode())

    def _on_frame(self, frame: np.ndarray, db: float) -> None:
        mode = self._mode
        if mode == "ptt":
            self.ptt.add(frame)
            return
        self._preroll.append((time.monotonic(), frame))
        if mode == "vad":
            if self._vad_seen != self._vad_epoch:
                self.vad.reset()
                self._vad_seen = self._vad_epoch
            self.vad.process(frame, db)

    def _on_vad_start(self) -> None:
        if self.awake and self._mode == "vad":
            self._touch()
            self._set_state(HEARING)
            self.ui.user_line("…", False)

    def _on_vad_discard(self) -> None:
        if self.awake and self._mode == "vad" and self.state == HEARING:
            self._set_state(LISTENING)
            self.ui.user_line("", False)

    def _on_vad_utterance(self, pcm: np.ndarray) -> None:
        if not self.awake or self._mode != "vad":
            return
        self._set_mode("off")
        self._set_state(THINKING)
        self._enqueue(VoiceJob(pcm, self._gen, was_asleep=False, push_to_talk=False))

    def _on_press(self, pressed_at: float) -> None:
        self._press_at = pressed_at
        if not self.settings.brain_ready or self._mode == "ptt":
            return
        self._press_seq += 1
        seq = self._press_seq
        if not self.mic.running:
            self._preroll.clear()
            future = asyncio.ensure_future(asyncio.to_thread(self._ensure_mic))
            future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)

        def cool_down() -> None:
            if seq == self._press_seq and not self.awake and self._mode == "off" and self.state == ASLEEP:
                self._stop_mic_later()

        asyncio.get_running_loop().call_later(WARM_MIC_S, cool_down)

    def _take_preroll(self) -> list[np.ndarray]:
        start = self._press_at - PREROLL_LEAD_S
        if time.monotonic() - self._press_at > 3:
            return []
        return [frame for at, frame in list(self._preroll) if at >= start]

    def _on_hold(self) -> None:
        self._touch()
        if not self.settings.brain_ready:
            self.ui.open_settings(self.settings.brain_problem)
            return
        if self.player.playing or self.state in (SPEAKING, THINKING):
            self.speaker.interrupt()
            self._gen += 1
        try:
            self._ensure_mic()
        except MicError as exc:
            self._play_cue("error")
            self.ui.toast(tr("Microfono non disponibile"), str(exc))
            return
        self.ptt.begin(self._take_preroll())
        self._set_mode("ptt")
        self._play_cue("thock")
        self._set_state(HEARING)
        if self.awake:
            self.ui.user_line("…", False)
        if self._ptt_deadline is not None:
            self._ptt_deadline.cancel()
        self._ptt_deadline = asyncio.get_running_loop().call_later(PTT_MAX_S, self._on_release)

    def _on_release(self) -> None:
        if self._mode != "ptt":
            return
        if self._ptt_deadline is not None:
            self._ptt_deadline.cancel()
            self._ptt_deadline = None
        pcm = self.ptt.end()
        was_asleep = not self.awake
        if was_asleep:
            self._stop_mic_later()
        if pcm.size < RATE * MIN_PTT_SECONDS:
            self._set_mode(self._idle_mode())
            self._set_state(LISTENING if self.awake else ASLEEP)
            if self.awake:
                self.ui.user_line("", False)
            return
        self._set_mode("off")
        self._set_state(THINKING)
        self._enqueue(VoiceJob(pcm, self._gen, was_asleep=was_asleep, push_to_talk=True))

    async def _worker(self) -> None:
        assert self._queue is not None
        while True:
            job = await self._queue.get()
            try:
                if isinstance(job, VoiceJob):
                    await self._handle_voice(job)
                elif isinstance(job, RemoteJob):
                    await self._handle_remote(job)
                elif isinstance(job, AnnounceJob):
                    await self._handle_announce(job)
                elif isinstance(job, ScheduledJob):
                    await self._handle_scheduled(job)
                elif isinstance(job, WakeJob):
                    if not self.awake:
                        await self._wake_up()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("job failed")
            finally:
                self._queue.task_done()
            self._resume_idle()

    def _resume_idle(self) -> None:
        if self._mode == "ptt" or (self._queue is not None and not self._queue.empty()):
            return
        if self.state == HEARING and self._mode == "vad":
            return
        if self.awake:
            self._set_mode(self._idle_mode())
            self._set_state(LISTENING)
            self.ui.status("")
        else:
            self._set_state(ASLEEP)
        self._touch()

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(5)
            if not self.awake or self.state != LISTENING or self._mode == "ptt":
                continue
            if self._queue is not None and not self._queue.empty():
                continue
            if time.monotonic() - self._last_activity > self.settings.auto_sleep_seconds:
                log.info("auto sleep after %ss of silence", self.settings.auto_sleep_seconds)
                self._sleep_now()

    async def _handle_voice(self, job: VoiceJob) -> None:
        if not job.was_asleep and job.gen != self._gen:
            return
        if self.awake:
            self._set_state(THINKING)
        try:
            transcript = await self.stt.transcribe_pcm(job.pcm, RATE, lenient=job.was_asleep and not self.awake)
        except GroqAuthError as exc:
            self._play_cue("error")
            self.ui.open_settings(error_text(exc))
            return
        except GroqError as exc:
            self._play_cue("error")
            if self.awake:
                self.ui.ressy_line(error_text(exc))
            else:
                self.ui.toast("Ressy", error_text(exc))
            return
        text = transcript.text

        if job.was_asleep and not self.awake:
            match = match_wake(text, self.settings.wake_phrases)
            if not match.matched:
                match = loose_wake(text)
            if match.matched:
                log.info("woken up (%s match, %d words after it)", "loose" if match.phrase == "loose" else "phrase",
                         len(match.remainder.split()))
                await self._wake_up(first_command=match.remainder)
            elif not text:
                self.ui.toast("Ressy", tr("Non ho capito bene: tieni premuto K e riprova «Ressy, sveglia!»."))
                log.info("wake attempt: nothing understood (%s)", transcript.rejected)
            else:
                self.ui.toast("Ressy", tr("Per svegliarmi di' «{capitalize}!»").format(capitalize=self.settings.wake_phrases[0].capitalize()))
                log.info("hotkey speech without the wake phrase: ignored")
            return
        if not self.awake:
            return
        if not text:
            if job.push_to_talk:
                self.ui.user_line(tr("Non ho sentito niente."), True)
            else:
                self.ui.user_line("", False)
            return
        self.ui.user_line(text, True)
        if is_sleep_command(text):
            await self._sleep_with_goodbye()
            return
        await self._converse(text, self._gen)

    async def _converse(self, text: str, gen: int) -> None:
        self._set_state(THINKING)
        self.ui.status(tr("Ci penso…"))
        progress = {"step": ""}

        def on_step(index: int, total: int, _text: str) -> None:
            progress["step"] = f"{index}/{total} · "
            self.ui.status(progress["step"] + "…")

        def on_tool(name: str) -> None:
            self.ui.status(progress["step"] + TOOL_STATUS.get(name, "…"))

        try:
            result = await asyncio.wait_for(
                self.brain.respond(text, VOICE, on_tool=on_tool, on_step=on_step),
                timeout=VOICE_TIMEOUT_S,
            )
        except Exception as exc:
            log.warning("voice turn failed: %s", exc, exc_info=not isinstance(exc, GroqError))
            if isinstance(exc, GroqAuthError):
                self.ui.open_settings(error_text(exc))
            result = TurnResult(text=error_text(exc))
        self.ui.status("")
        if gen != self._gen or not self.awake:
            self._run_deferred(result.deferred)
            return
        await self._say(result.text)
        self._run_deferred(result.deferred)
        if result.sleep and gen == self._gen:
            self._sleep_now(cue=True)

    async def _say(self, text: str) -> bool:
        self.ui.ressy_line(text)
        self._set_state(SPEAKING)
        if self._mode != "ptt":
            self._set_mode("off")
        completed = await self.speaker.speak(text)
        await asyncio.sleep(0.25)
        self._touch()
        return completed

    async def _wake_up(self, first_command: str = "") -> None:
        self.awake = True
        self._gen += 1
        gen = self._gen
        self._touch()
        self.ui.show_hud()
        self._play_cue("wake")
        try:
            self._ensure_mic()
        except MicError as exc:
            self.ui.toast(tr("Microfono non disponibile"), str(exc))
        if not self.settings.brain_ready:
            await self._say(tr("Ciao! Per iniziare mi serve una chiave API: inseriscila nelle impostazioni."))
            self.ui.open_settings(self.settings.brain_problem)
            return
        if first_command:
            self.ui.user_line(first_command, True)
            await self._converse(first_command, gen)
        else:
            self.ui.user_line("", False)
            await self._say(prompts.greeting(self.settings.user_name, language=self.settings.language))

    async def _sleep_with_goodbye(self) -> None:
        await self._say(prompts.farewell(self.settings.language))
        mem = getattr(self.brain, "memory", None)
        if mem is not None:
            mem.clear(VOICE.key)
        self._sleep_now(cue=False)

    def _sleep_now(self, cue: bool = True) -> None:
        if not self.awake:
            return
        self.awake = False
        self._gen += 1
        if self._mode != "ptt":
            self._set_mode("off")
            self._stop_mic_later()
        self.speaker.interrupt()
        self.ui.status("")
        self.ui.hide_hud()
        from ..paths import trim_memory

        trim_memory()
        self._set_state(ASLEEP if self._mode != "ptt" else HEARING)
        if cue:
            self._play_cue("sleep")

    def _run_deferred(self, actions: list[Callable[[], object]]) -> None:
        loop = asyncio.get_running_loop()
        for action in actions:
            loop.call_later(3.0, lambda a=action: asyncio.ensure_future(asyncio.to_thread(a)))

    async def _on_remote_command(self, message: dict[str, Any]) -> dict[str, Any]:
        future = asyncio.get_running_loop().create_future()
        self._enqueue(RemoteJob(message, future))
        return await future

    async def _handle_remote(self, job: RemoteJob) -> None:
        source = job.message.get("source") or {}
        channel = Channel(
            kind=str(source.get("platform") or "telegram"),
            user_id=str(source.get("user_id") or ""),
            display=str(source.get("display") or ""),
        )
        try:
            reply = await asyncio.wait_for(self._remote_turn(job.message, channel), timeout=REMOTE_TIMEOUT_S)
        except Exception as exc:
            log.warning("remote turn failed: %s", exc, exc_info=not isinstance(exc, (GroqError, asyncio.TimeoutError)))
            reply = {"ok": False, "text": error_text(exc)}
        if not job.future.done():
            job.future.set_result(reply)

    async def _remote_turn(self, message: dict[str, Any], channel: Channel) -> dict[str, Any]:
        if not self.settings.brain_ready:
            return {"ok": False, "text": tr("Sul PC manca una chiave API: ") + self.settings.brain_problem}
        text = str(message.get("text") or "").strip()
        transcript: str | None = None
        audio = message.get("audio")
        if not text and isinstance(audio, dict):
            try:
                data = base64.b64decode(str(audio.get("data") or ""), validate=True)
            except (binascii.Error, ValueError):
                return {"ok": False, "text": tr("Il messaggio vocale è arrivato danneggiato.")}
            heard = await self.stt.transcribe_file(data, str(audio.get("mime") or "audio/ogg"))
            if not heard.ok:
                return {"ok": False, "text": tr("Non sono riuscita a capire il messaggio vocale.")}
            text = transcript = heard.text
        if not text:
            return {"ok": False, "text": tr("Il messaggio è vuoto.")}

        if self.settings.notify_remote_commands:
            who = f" ({channel.display})" if channel.display else ""
            self.ui.toast(tr("Comando da {label}{who}").format(label=channel.label, who=who), text[:160])
            self._play_cue("remote")
        if self.awake:
            self.ui.status(tr("Comando da {label}…").format(label=channel.label))

        result = await self.brain.respond(text, channel)
        reply: dict[str, Any] = {"ok": True, "text": result.text[:MAX_REPLY_TEXT]}
        if transcript:
            reply["transcript"] = transcript
        images = [img for img in result.images if len(img.data) <= MAX_IMAGE_BYTES][:4]
        if images:
            reply["images"] = [{"mime": img.mime, "name": img.name, "data": _b64(img.data)} for img in images]
        if message.get("want_voice"):
            note = await self.speaker.voice_note(result.text)
            if note is not None and len(note[0]) <= MAX_VOICE_BYTES:
                reply["voice"] = {"mime": note[1], "data": _b64(note[0])}
        if self.settings.speak_remote_replies:
            self._enqueue(AnnounceJob(result.text))
        self._run_deferred(result.deferred)
        return reply

    def _on_remote_event(self, kind: str, data: dict[str, Any]) -> None:
        if kind == "state":
            self.ui.remote_state(str(data.get("state")), str(data.get("detail") or ""))
        elif kind == "links":
            self.ui.links(list(data.get("links") or []))
        elif kind == "linked":
            self.ui.linked(data)
            platform = {"telegram": "Telegram", "discord": "Discord"}.get(str(data.get("platform")), "chat")
            self.ui.toast(tr("Ressy collegata"), tr("Ora puoi comandare questo PC da {platform} ({get}).").format(platform=platform, get=data.get('display', '')))
        elif kind == "pair_code":
            self.ui.pair_code(data)

    async def _announce_reminder(self, reminder: Reminder, late: bool) -> None:
        if getattr(reminder, "command", ""):
            self._enqueue(ScheduledJob(reminder, late))
            return
        if getattr(reminder, "kind", "reminder") == "timer":
            text = tr("Timer scaduto: {text}.").format(text=reminder.text)
            title = tr("Timer")
        else:
            text = tr("Promemoria: {text}").format(text=reminder.text)
            title = tr("Promemoria")
        if late:
            text += tr(" (in ritardo: il PC era spento o in sospensione)")
        self.ui.toast(title, reminder.text)
        if getattr(reminder, "call", False):
            from ..tools import calls
            from ..tools.registry import ToolContext

            plat = getattr(reminder, "call_platform", "") or reminder.platform or "auto"
            ctx = ToolContext(channel=VOICE, services=self.services)
            try:
                await calls.call_phone(
                    ctx,
                    {
                        "platform": plat,
                        "recipient": getattr(reminder, "call_target", ""),
                        "reason": text,
                    },
                )
            except Exception:
                log.warning("reminder call escalation failed", exc_info=True)
        async def _voice_payload(msg: str) -> dict[str, str] | None:
            import base64

            if not getattr(self.speaker, "voice_note", None):
                return None
            try:
                note = await self.speaker.voice_note(msg)
                if note is not None and len(note) == 2 and note[0]:
                    return {"mime": str(note[1]), "data": base64.b64encode(note[0]).decode("ascii")}
            except Exception:
                pass
            return None

        if reminder.platform:
            voice = await _voice_payload(text)
            delivered = await self.remote.notify(
                "⏰ " + text, voice=voice, target={"platform": reminder.platform, "user_id": reminder.user_id}
            )
            if delivered:
                return
        elif getattr(self.remote, "links", None):
            voice = await _voice_payload(text)
            await self.remote.notify("⏰ " + text, voice=voice)
        self._enqueue(AnnounceJob(text))

    async def _handle_scheduled(self, job: ScheduledJob) -> None:
        reminder = job.reminder
        if job.late:
            msg = tr("Azione programmata saltata (il PC era spento): {command}").format(command=reminder.command)
            if reminder.platform:
                await self.remote.notify("⏰ " + msg, target={"platform": reminder.platform, "user_id": reminder.user_id})
            else:
                await self._handle_announce(AnnounceJob(msg))
            return
        channel = (
            Channel(kind=reminder.platform, user_id=reminder.user_id)
            if reminder.platform else VOICE
        )
        self.ui.toast(tr("Azione programmata"), reminder.command)
        try:
            result = await asyncio.wait_for(self.brain.respond(reminder.command, channel), timeout=VOICE_TIMEOUT_S)
            reply_text = result.text
        except Exception as exc:
            reply_text = error_text(exc)
        if reminder.platform:
            delivered = await self.remote.notify(
                "⏰ " + reply_text, target={"platform": reminder.platform, "user_id": reminder.user_id}
            )
            if delivered:
                self._run_deferred(result.deferred if "result" in locals() else [])
                return
        await self._handle_announce(AnnounceJob(reply_text))
        if "result" in locals():
            self._run_deferred(result.deferred)

    async def _handle_announce(self, job: AnnounceJob) -> None:
        temporary = not self.awake
        if temporary:
            self.ui.show_hud()
        self._play_cue("done")
        await self._say(job.text)
        if temporary and not self.awake:
            await asyncio.sleep(1.2)
            if not self.awake:
                self.ui.hide_hud()
                if self._mode != "ptt":
                    self._set_state(ASLEEP)
