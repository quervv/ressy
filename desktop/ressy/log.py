from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

from .paths import ensure_dirs, is_frozen, log_dir

_SECRET_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9]{8,}"),
    re.compile(r"(\"secret\"\s*:\s*\")[^\"]+"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"\d{6,12}:[A-Za-z0-9_\-]{30,}"),
    re.compile(r"[A-Za-z0-9_\-]{24,}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,}"),
]


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "***", redacted)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


def setup_logging(level: int = logging.INFO) -> None:
    ensure_dirs()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s")
    redact = RedactFilter()
    handlers: list[logging.Handler] = []
    file_handler = RotatingFileHandler(log_dir() / "ressy.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.addFilter(redact)
    handlers.append(file_handler)
    if not is_frozen() and sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        console.addFilter(redact)
        handlers.append(console)
    root = logging.getLogger()
    root.handlers[:] = handlers
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "asyncio", "PIL", "websockets", "edge_tts", "aiohttp",
                  "telegram", "discord", "aiosqlite"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
