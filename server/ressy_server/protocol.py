from __future__ import annotations

import base64
import binascii
import re

PROTOCOL_VERSION = 1

MAX_WS_MESSAGE = 32 * 1024 * 1024
MAX_COMMAND_TEXT = 4000
MAX_AUDIO_BYTES = 15 * 1024 * 1024
MAX_AUDIO_SECONDS = 300
MAX_REPLY_TEXT = 8000
MAX_VOICE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 9 * 1024 * 1024
MAX_IMAGES = 4
MAX_NAME_LEN = 64

AGENT_ID_RE = re.compile(r"^[a-f0-9]{32}$")
SECRET_RE = re.compile(r"^[A-Za-z0-9_\-]{32,128}$")

PAIR_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PAIR_CODE_LEN = 6
PAIR_CODE_RE = re.compile(rf"^[{PAIR_ALPHABET}]{{{PAIR_CODE_LEN}}}$")

AUDIO_EXTENSIONS = {
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/webm": "webm",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
}


def normalize_pair_code(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if PAIR_CODE_RE.match(cleaned):
        return cleaned
    return None


def clean_name(raw: object, fallback: str = "PC") -> str:
    if not isinstance(raw, str):
        return fallback
    name = " ".join(raw.split())[:MAX_NAME_LEN]
    return name or fallback


def b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64decode(data: object, max_bytes: int) -> bytes:
    if not isinstance(data, str):
        raise ValueError("binary payload must be a base64 string")
    if len(data) > (max_bytes * 4) // 3 + 8:
        raise ValueError("binary payload too large")
    try:
        decoded = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64 payload") from exc
    if len(decoded) > max_bytes:
        raise ValueError("binary payload too large")
    return decoded


def audio_extension(mime: str | None) -> str:
    if not mime:
        return "ogg"
    return AUDIO_EXTENSIONS.get(mime.split(";")[0].strip().lower(), "ogg")
