from __future__ import annotations

import locale
import logging

log = logging.getLogger("ressy.i18n")

LANGUAGES = {"it": "Italiano", "en": "English"}

_language = "it"
_english: dict[str, str] | None = None


def set_language(code: str) -> None:
    global _language
    _language = "en" if (code or "").lower().startswith("en") else "it"


def language() -> str:
    return _language


def saved_language() -> str:
    try:
        import json

        from .paths import config_path

        data = json.loads(config_path().read_text(encoding="utf-8"))
        code = str(data.get("language") or "")
        return code if code in LANGUAGES else ""
    except Exception:
        return ""


def apply_saved_language() -> str:
    set_language(saved_language() or system_language())
    return _language


def system_language() -> str:
    try:
        import ctypes

        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "it" if (lang_id & 0x3FF) == 0x10 else "en"
    except Exception:
        code = (locale.getlocale()[0] or "").lower()
        return "it" if code.startswith(("it", "italian")) else "en"


def _table() -> dict[str, str]:
    global _english
    if _english is None:
        try:
            from .i18n_en import EN

            _english = EN
        except Exception:
            log.exception("English texts unavailable")
            _english = {}
    return _english


def tr(text: str) -> str:
    if _language == "it" or not text:
        return text
    return _table().get(text, text)


def N_(text: str) -> str:
    return text
