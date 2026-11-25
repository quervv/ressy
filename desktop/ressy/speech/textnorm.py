from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _norm_word(word: str) -> str:
    return _NON_ALNUM.sub("", strip_accents(word.casefold()))


def normalize(text: str) -> str:
    return " ".join(tokens(text))


def tokens(text: str) -> list[str]:
    return [w for w in (_norm_word(m.group()) for m in _WORD.finditer(text or "")) if w]


def token_spans(text: str) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    for match in _WORD.finditer(text or ""):
        word = _norm_word(match.group())
        if word:
            spans.append((word, match.start(), match.end()))
    return spans


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()
