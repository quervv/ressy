from __future__ import annotations

from dataclasses import dataclass

from .textnorm import normalize, similarity, token_spans, tokens

_PHONETIC_RULES = (
    ("ch", "k"), ("gh", "g"), ("ph", "f"), ("gli", "li"), ("gl", "l"), ("sc", "s"), ("cc", "c"), ("ci", "si"),
    ("ce", "se"), ("gi", "i"), ("ge", "e"), ("x", "s"), ("z", "s"), ("y", "i"), ("j", "i"), ("w", "v"),
    ("b", "v"), ("k", "c"), ("h", ""),
)


def phonetic(word: str) -> str:
    out = word.lower()
    for a, b in _PHONETIC_RULES:
        out = out.replace(a, b)
    collapsed = []
    for ch in out:
        if not collapsed or collapsed[-1] != ch:
            collapsed.append(ch)
    out = "".join(collapsed)
    for end in ("ie", "ei", "ee", "e"):
        if len(out) > 3 and out.endswith(end):
            out = out[: -len(end)] + "i"
            break
    return out


def _sounds_like(heard: str, expected: str, threshold: float) -> bool:
    a, b = phonetic(heard), phonetic(expected)
    return a == b or similarity(a, b) >= threshold


def _fuzzy_contains(text: str, target: str, threshold: float) -> bool:
    size = len(target)
    if len(text) < size - 1:
        return False
    for length in (size - 1, size, size + 1):
        for start in range(0, max(1, len(text) - length + 1)):
            if similarity(text[start:start + length], target) >= threshold:
                return True
    return False

NAME = "ressy"
NAME_VARIANTS = frozenset(
    {
        "ressy", "ressi", "ressie", "ressey", "resy", "resi", "rexy", "ressee", "rassi", "rassy", "rezzy", "rezi",
        "rexi", "lessy", "jessy", "tessy", "ressa", "resse", "rescy", "wrecy", "recy",
    }
)
WAKE_WORDS = ("sveglia", "svegliati", "sveglio", "svegliarti", "svegliamo", "wake", "wakeup")

NAME_THRESHOLD = 0.6
WORD_THRESHOLD = 0.72
_REMAINDER_TRIM = " \t\r\n,.;:!?-–—"

SLEEP_PHRASES = frozenset(
    {
        "dormi",
        "vai a dormire",
        "torna a dormire",
        "puoi andare",
        "puoi andare a dormire",
        "basta cosi",
        "basta cosi grazie",
        "grazie e tutto",
        "e tutto grazie",
        "grazie basta cosi",
        "a dopo",
        "buonanotte",
        "go to sleep",
        "go back to sleep",
        "thats all",
        "that s all",
        "thats it",
        "that s it",
        "thank you thats all",
        "thank you that s all",
        "thanks thats all",
        "thanks that s all",
        "you can go",
        "see you later",
        "good night",
        "goodnight",
    }
)


@dataclass(frozen=True)
class WakeMatch:
    matched: bool
    remainder: str = ""
    phrase: str = ""


def _word_ok(heard: str, expected: str) -> bool:
    if expected == NAME:
        return (
            heard in NAME_VARIANTS
            or similarity(heard, expected) >= NAME_THRESHOLD
            or (len(heard) >= 3 and _sounds_like(heard, expected, 0.72))
        )
    return similarity(heard, expected) >= WORD_THRESHOLD or _sounds_like(heard, expected, 0.8)


def match_wake(transcript: str, phrases: list[str]) -> WakeMatch:
    spans = token_spans(transcript)
    words = [w for w, _, _ in spans]
    best = WakeMatch(False)
    best_key: tuple[int, int] | None = None
    for phrase in phrases:
        expected = tokens(phrase)
        size = len(expected)
        if not size or size > len(words):
            continue
        for start in range(0, len(words) - size + 1):
            if all(_word_ok(words[start + i], expected[i]) for i in range(size)):
                key = (start, -size)
                if best_key is None or key < best_key:
                    end_offset = spans[start + size - 1][2]
                    remainder = transcript[end_offset:].strip(_REMAINDER_TRIM)
                    best = WakeMatch(True, remainder, phrase)
                    best_key = key
                break
    return best


def _wake_word(word: str) -> bool:
    return len(word) >= 4 and any(similarity(word, w) >= 0.75 or _sounds_like(word, w, 0.8) for w in WAKE_WORDS)


_NAME_SOUND = phonetic(NAME)
_WAKE_SOUND = phonetic("sveglia")


def _call_in(words: list[str]) -> bool:
    joined = "".join(phonetic(w) for w in words)
    return _fuzzy_contains(joined, _NAME_SOUND, 0.88) or _fuzzy_contains(joined, _WAKE_SOUND, 0.85)


def loose_wake(transcript: str) -> WakeMatch:
    spans = token_spans(transcript)
    last = -1
    for index, (word, _, _) in enumerate(spans):
        if _word_ok(word, NAME) or _wake_word(word):
            last = index
        elif last >= 0 and last == index - 1 and word == "up" and _wake_word(spans[last][0]):
            last = index
        elif last >= 0:
            break
        elif index >= 3:
            return WakeMatch(False)
    if last < 0:
        words = [w for w, _, _ in spans]
        for count in range(1, min(4, len(words)) + 1):
            if _call_in(words[:count]):
                last = count - 1
                while last + 1 < len(words) and _call_in(words[last + 1:last + 2]):
                    last += 1
                break
        if last < 0:
            return WakeMatch(False)
    remainder = transcript[spans[last][2]:].strip(_REMAINDER_TRIM)
    return WakeMatch(True, remainder, "loose")


def strip_name(text: str) -> str:
    words = normalize(text).split()
    if words and _word_ok(words[0], NAME):
        words = words[1:]
    if words and _word_ok(words[-1], NAME):
        words = words[:-1]
    return " ".join(words)


def is_sleep_command(text: str) -> bool:
    return strip_name(text) in SLEEP_PHRASES
