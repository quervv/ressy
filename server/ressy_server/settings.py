from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def load_dotenv(path: str | os.PathLike[str] = ".env") -> None:
    file = Path(path)
    if not file.is_file():
        return
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _get_int(env: Mapping[str, str], key: str, default: int, minimum: int = 0) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{key} must be >= {minimum}, got {value}")
    return value


def _get_float(env: Mapping[str, str], key: str, default: float, minimum: float = 0.0) -> float:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a number, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{key} must be >= {minimum}, got {value}")
    return value


def _get_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "si", "sì"}


@dataclass(frozen=True)
class Settings:
    telegram_token: str = ""
    discord_token: str = ""
    discord_invite_url: str = ""
    host: str = "0.0.0.0"
    port: int = 8765
    db_path: str = "data/ressy.db"
    public_url: str = "https://ressy.top"
    timezone: str = "Europe/Rome"
    offline_grace_s: float = 45.0
    startup_sweep_delay_s: float = 90.0
    command_timeout_s: float = 150.0
    pair_code_ttl_s: int = 600
    max_commands_per_minute: int = 20
    max_link_failures: int = 5
    max_registrations_per_hour: int = 30
    stale_message_s: float = 120.0
    trust_proxy: bool = False
    log_level: str = "INFO"
    announce_first_connect: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        settings = cls(
            telegram_token=env.get("TELEGRAM_BOT_TOKEN", "").strip(),
            discord_token=env.get("DISCORD_BOT_TOKEN", "").strip(),
            discord_invite_url=env.get("DISCORD_INVITE_URL", "").strip(),
            host=env.get("RESSY_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=_get_int(env, "RESSY_PORT", 8765, minimum=1),
            db_path=env.get("RESSY_DB_PATH", "data/ressy.db").strip() or "data/ressy.db",
            public_url=(env.get("RESSY_PUBLIC_URL", "https://ressy.top").strip() or "https://ressy.top").rstrip("/"),
            timezone=env.get("RESSY_TIMEZONE", "Europe/Rome").strip() or "Europe/Rome",
            offline_grace_s=_get_float(env, "RESSY_OFFLINE_GRACE_SECONDS", 45.0),
            startup_sweep_delay_s=_get_float(env, "RESSY_STARTUP_SWEEP_SECONDS", 90.0),
            command_timeout_s=_get_float(env, "RESSY_COMMAND_TIMEOUT_SECONDS", 150.0, minimum=5.0),
            pair_code_ttl_s=_get_int(env, "RESSY_PAIR_CODE_TTL_SECONDS", 600, minimum=60),
            max_commands_per_minute=_get_int(env, "RESSY_MAX_COMMANDS_PER_MINUTE", 20, minimum=1),
            max_link_failures=_get_int(env, "RESSY_MAX_LINK_FAILURES", 5, minimum=1),
            max_registrations_per_hour=_get_int(env, "RESSY_MAX_REGISTRATIONS_PER_HOUR", 30, minimum=1),
            stale_message_s=_get_float(env, "RESSY_STALE_MESSAGE_SECONDS", 120.0, minimum=10.0),
            trust_proxy=_get_bool(env, "RESSY_TRUST_PROXY", False),
            log_level=(env.get("LOG_LEVEL", "INFO").strip() or "INFO").upper(),
            announce_first_connect=_get_bool(env, "RESSY_ANNOUNCE_FIRST_CONNECT", False),
        )
        return settings

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.telegram_token and not self.discord_token:
            problems.append(
                "Nessun bot configurato: imposta TELEGRAM_BOT_TOKEN e/o DISCORD_BOT_TOKEN."
            )
        return problems
