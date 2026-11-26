from __future__ import annotations

import json
import logging
import os
import secrets
import socket
import threading
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import dpapi
from .paths import config_path, ensure_dirs
from .i18n import tr

log = logging.getLogger("ressy.config")

LEGACY_SERVER_URL = "wss://ressy.top/ws/agent"
DEFAULT_SERVER_PORT = 8765
REMOTE_MODES = ("local", "server")
DEFAULT_LLM_MODEL = "openai/gpt-oss-120b"
LLM_FALLBACK_MODELS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b")
DEFAULT_STT_MODEL = "whisper-large-v3"
OLD_STT_DEFAULT = "whisper-large-v3-turbo"

EDGE_VOICES = {
    "it-IT-IsabellaNeural": tr("Isabella (italiano, femminile)"),
    "it-IT-ElsaNeural": tr("Elsa (italiano, femminile)"),
    "it-IT-DiegoNeural": tr("Diego (italiano, maschile)"),
    "it-IT-GiuseppeMultilingualNeural": tr("Giuseppe (italiano, maschile)"),
    "en-US-AvaMultilingualNeural": tr("Ava (inglese, femminile)"),
    "en-US-AndrewMultilingualNeural": tr("Andrew (inglese, maschile)"),
}

WAKE_DEFAULTS = {
    "it": ["ressy sveglia", "sveglia ressy", "ressy svegliati"],
    "en": ["ressy wake up", "wake up ressy", "hey ressy"],
}
VOICE_DEFAULTS = {"it": "it-IT-IsabellaNeural", "en": "en-US-AvaMultilingualNeural"}
_VOICE_TWINS = {
    "it-IT-IsabellaNeural": "en-US-AvaMultilingualNeural",
    "it-IT-ElsaNeural": "en-US-AvaMultilingualNeural",
    "it-IT-DiegoNeural": "en-US-AndrewMultilingualNeural",
    "it-IT-GiuseppeMultilingualNeural": "en-US-AndrewMultilingualNeural",
    "en-US-AvaMultilingualNeural": "it-IT-IsabellaNeural",
    "en-US-AndrewMultilingualNeural": "it-IT-DiegoNeural",
}


def voice_for(language: str, voice: str) -> str:
    code = "en" if language == "en" else "it"
    if (voice or "").lower().startswith(code + "-"):
        return voice
    return _VOICE_TWINS.get(voice, VOICE_DEFAULTS[code])


def wake_phrases_for(language: str, phrases: list[str]) -> list[str]:
    code = "en" if language == "en" else "it"
    other = WAKE_DEFAULTS["it" if code == "en" else "en"]
    own = [p for p in phrases if p not in other and p not in WAKE_DEFAULTS[code]]
    return list(WAKE_DEFAULTS[code]) + own

LLM_PROVIDERS = ("groq", "gemini", "openrouter", "claude", "local")
PROVIDER_NAMES = {"groq": "Groq", "claude": "Claude", "gemini": "Gemini", "openrouter": "OpenRouter", "local": tr("Sul PC")}
CLAUDE_MODELS = {
    "claude-opus-5-5": tr("Claude Opus 5.5 (il più capace)"),
    "claude-sonnet-5-5": "Claude Sonnet 5.5 (veloce e capace)",
    "claude-haiku-5-5": tr("Claude Haiku 5.5 (il più veloce ed economico)"),
}
DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"

STT_ENGINES = ("local", "groq", "gemini")
LOCAL_STT_MODELS = {
    "tiny-q5_1": (tr("Leggero"), 32),
    "base-q5_1": (tr("Bilanciato"), 60),
    "small-q5_1": (tr("Preciso"), 190),
}
DEFAULT_LOCAL_STT_MODEL = "base-q5_1"

LOCAL_LLM_MODELS = {
    "qwen2.5-0.5b": (tr("Leggera"), 491, "qwen2.5-0.5b-instruct-q4_k_m.gguf",
                     "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"),
    "qwen2.5-1.5b": (tr("Consigliata"), 1117, "qwen2.5-1.5b-instruct-q4_k_m.gguf",
                     "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"),
    "qwen2.5-3b": (tr("Massima"), 1998, "qwen2.5-3b-instruct-q4_0.gguf",
                   "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_0.gguf"),
}
DEFAULT_LOCAL_LLM_MODEL = "qwen2.5-1.5b"

_SECRET_FIELDS = ("groq_api_key", "anthropic_api_key", "gemini_api_key", "openrouter_api_key", "agent_secret", "telegram_token", "discord_token")


@dataclass
class Settings:
    user_name: str = ""
    language: str = "it"

    llm_provider: str = "groq"
    groq_api_key: str = ""
    llm_model: str = DEFAULT_LLM_MODEL
    anthropic_api_key: str = ""
    claude_model: str = DEFAULT_CLAUDE_MODEL
    gemini_api_key: str = ""
    gemini_model: str = DEFAULT_GEMINI_MODEL
    openrouter_api_key: str = ""
    openrouter_model: str = ""
    llm_fallback: bool = True
    local_llm_model: str = ""
    quick_commands: bool = True
    auto_update: bool = True
    last_version: str = ""

    stt_engine: str = ""
    stt_model: str = DEFAULT_STT_MODEL
    local_stt_model: str = DEFAULT_LOCAL_STT_MODEL

    tts_engine: str = "edge"
    tts_voice: str = "it-IT-IsabellaNeural"
    tts_rate: int = 0
    sounds_enabled: bool = True

    hotkey_vk: int = 0x4B
    hotkey_name: str = "K"
    hotkey_hold_ms: int = 350
    wake_phrases: list[str] = field(default_factory=lambda: ["ressy sveglia", "sveglia ressy", "ressy svegliati"])

    listen_mode: str = "continuous"
    auto_sleep_seconds: int = 90
    mic_device: str = ""
    output_device: str = ""

    hud_x: int | None = None
    hud_y: int | None = None

    remote_enabled: bool = False
    remote_mode: str = "local"
    server_url: str = ""
    telegram_token: str = ""
    discord_token: str = ""
    discord_invite_url: str = ""
    device_name: str = field(default_factory=lambda: socket.gethostname()[:64] or "PC")
    agent_id: str = ""
    agent_secret: str = ""
    speak_remote_replies: bool = False
    notify_remote_commands: bool = True

    home_city: str = ""

    first_run_done: bool = False
    stt_upgraded: bool = False

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self._path: Path | None = None

    def ensure_identity(self) -> bool:
        changed = False
        if not self.agent_id or len(self.agent_id) != 32:
            self.agent_id = uuid.uuid4().hex
            changed = True
        if not self.agent_secret or len(self.agent_secret) < 32:
            self.agent_secret = secrets.token_urlsafe(32)
            changed = True
        return changed

    def use_language(self, code: str) -> None:
        code = "en" if code == "en" else "it"
        if code != self.language:
            self.wake_phrases = wake_phrases_for(code, self.wake_phrases)
        self.tts_voice = voice_for(code, self.tts_voice)
        self.language = code

    def reset_identity(self) -> None:
        self.agent_id = ""
        self.agent_secret = ""
        self.ensure_identity()

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or config_path()
        settings = cls()
        settings._path = path
        if not path.exists():
            return settings
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            log.exception("config file unreadable, using defaults")
            return settings
        known = {f.name: f for f in fields(cls)}
        for key, value in raw.items():
            if key.endswith("_enc"):
                name = key[: -len("_enc")]
                if name in _SECRET_FIELDS:
                    try:
                        setattr(settings, name, dpapi.unprotect(value))
                    except Exception:
                        log.warning("could not decrypt %s (config copied from another user/PC?)", name)
                continue
            if key in known and key not in _SECRET_FIELDS:
                default = getattr(settings, key)
                if default is None or value is None or isinstance(value, type(default)):
                    setattr(settings, key, value)
                elif isinstance(default, float) and isinstance(value, int):
                    setattr(settings, key, float(value))
        settings._sanitize()
        return settings

    def _sanitize(self) -> None:
        self.hotkey_hold_ms = max(150, min(int(self.hotkey_hold_ms), 2000))
        self.auto_sleep_seconds = max(15, min(int(self.auto_sleep_seconds), 3600))
        self.tts_rate = max(-50, min(int(self.tts_rate), 50))
        if self.listen_mode not in ("continuous", "push_to_talk"):
            self.listen_mode = "continuous"
        if self.tts_engine not in ("edge", "sapi"):
            self.tts_engine = "edge"
        if self.language not in ("it", "en"):
            self.language = "it"
        self.wake_phrases = [p.strip() for p in self.wake_phrases if isinstance(p, str) and p.strip()] or [
            "ressy sveglia"
        ]
        self.device_name = (self.device_name or "PC").strip()[:64] or "PC"
        if self.remote_mode not in REMOTE_MODES:
            self.remote_mode = "local"
        self.server_url = (self.server_url or "").strip()
        if self.server_url == LEGACY_SERVER_URL:
            self.server_url = ""
            self.remote_enabled = False
        self.telegram_token = (self.telegram_token or "").strip()
        self.discord_token = (self.discord_token or "").strip()
        self.home_city = (self.home_city or "").strip()[:80]
        if self.llm_provider not in LLM_PROVIDERS:
            self.llm_provider = "groq"
        if self.stt_engine not in STT_ENGINES:
            self.stt_engine = "groq" if self.groq_api_key.strip() else "local"
        if self.local_stt_model not in LOCAL_STT_MODELS:
            self.local_stt_model = DEFAULT_LOCAL_STT_MODEL
        if self.claude_model not in CLAUDE_MODELS:
            self.claude_model = DEFAULT_CLAUDE_MODEL
        self.gemini_model = (self.gemini_model or DEFAULT_GEMINI_MODEL).strip()
        if self.gemini_model.startswith("gemini-2."):
            self.gemini_model = {"gemini-2.5-flash-lite": "gemini-flash-lite-latest",
                                 "gemini-2.5-pro": "gemini-pro-latest"}.get(self.gemini_model, DEFAULT_GEMINI_MODEL)
        self.openrouter_api_key = (self.openrouter_api_key or "").strip()
        self.openrouter_model = (self.openrouter_model or "").strip()
        if self.local_llm_model not in LOCAL_LLM_MODELS:
            self.local_llm_model = ""
        if self.llm_provider == "local" and not self.local_llm_model:
            self.local_llm_model = DEFAULT_LOCAL_LLM_MODEL
        if not self.stt_upgraded:
            if self.stt_model == OLD_STT_DEFAULT:
                self.stt_model = DEFAULT_STT_MODEL
            self.stt_upgraded = True

    @property
    def has_bot_token(self) -> bool:
        return bool(self.telegram_token or self.discord_token)

    @property
    def remote_ready(self) -> bool:
        if not self.remote_enabled:
            return False
        if self.remote_mode == "local":
            return self.has_bot_token
        return bool(self.server_url)

    def save(self) -> None:
        with self._lock:
            path = self._path or config_path()
            ensure_dirs()
            data = {k: v for k, v in asdict(self).items() if k not in _SECRET_FIELDS}
            for name in _SECRET_FIELDS:
                value = getattr(self, name)
                data[f"{name}_enc"] = dpapi.protect(value) if value else ""
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)

    def update(self, **changes: object) -> None:
        with self._lock:
            for key, value in changes.items():
                if not hasattr(self, key):
                    raise AttributeError(key)
                setattr(self, key, value)
            self._sanitize()
        self.save()

    @property
    def has_groq_key(self) -> bool:
        return bool(self.groq_api_key.strip())

    def provider_key(self, provider: str) -> str:
        return {
            "groq": self.groq_api_key,
            "claude": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
            "openrouter": self.openrouter_api_key,
        }.get(provider, "").strip()

    def local_llm_ready(self) -> bool:
        if not self.local_llm_model:
            return False
        from .brain.local_llm import is_downloaded

        return is_downloaded(self.local_llm_model)

    def providers_with_keys(self) -> list[str]:
        order = [self.llm_provider, *(p for p in LLM_PROVIDERS if p != self.llm_provider)]
        return [p for p in order if (self.local_llm_ready() if p == "local" else self.provider_key(p))]

    @property
    def speech_engine(self) -> str:
        if self.stt_engine in STT_ENGINES:
            return self.stt_engine
        return "groq" if self.groq_api_key.strip() else "local"

    @property
    def brain_ready(self) -> bool:
        return not self.brain_problem

    @property
    def brain_problem(self) -> str:
        if self.llm_provider == "local":
            if not self.local_llm_ready():
                return tr("Scarica il modello AI sul PC (Impostazioni › Intelligenza) o inserisci una chiave API.")
        elif not self.provider_key(self.llm_provider):
            return tr("Per usare Ressy inserisci la chiave API di {value} (Impostazioni › Intelligenza).").format(value=PROVIDER_NAMES[self.llm_provider])
        engine = self.speech_engine
        if engine == "local":
            from .speech.local_stt import is_downloaded

            if not is_downloaded(self.local_stt_model):
                return tr("Scarica il modello vocale sul PC (Impostazioni › Voce) o scegli di capire la voce online.")
        elif not self.provider_key(engine):
            return tr("Per capire la voce con {value} serve la sua chiave API, oppure scegli il modello sul PC.").format(value=PROVIDER_NAMES[engine])
        return ""

    def llm_models(self) -> list[str]:
        ordered = [self.llm_model, *LLM_FALLBACK_MODELS]
        seen: set[str] = set()
        return [m for m in ordered if m and not (m in seen or seen.add(m))]
