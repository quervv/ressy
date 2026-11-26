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


_SPOKEN_APP_CONTEXT = (
    r"(?:apri\w*|chiudi\w*|avvia\w*|lancia\w*|termina\w*|passa\s+a|vai\s+su|torna\s+su|porta\s+avanti|"
    r"minimizza\w*|massimizza\w*|ingrandisci\w*|in|nel|nella|su|sul|sulla|su'|con|open|close|launch|start|on)"
)
_SPOKEN_SUBS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(rf"(\b{_SPOKEN_APP_CONTEXT}\s+(?:il\s+)?)(?:discorso|discordia|discordo|di\s+scord|di\s+scort)\b", re.I),
     r"\1Discord"),
    (re.compile(rf"(\b{_SPOKEN_APP_CONTEXT}\s+)(?:spotifai|spot\s+if\s+i|spoti\s+fai|spotifi)\b", re.I), r"\1Spotify"),
    (re.compile(rf"(\b{_SPOKEN_APP_CONTEXT}\s+)(?:uozzap|wazzap|watsap|what'?s\s*up|what\s+app)\b", re.I),
     r"\1WhatsApp"),
    (re.compile(rf"(\b{_SPOKEN_APP_CONTEXT}\s+(?:google\s+)?)(?:cromo|crome)\b", re.I), r"\1Chrome"),
    (re.compile(rf"(\b{_SPOKEN_APP_CONTEXT}\s+)(?:fortreta|fortnait|fortinite|fort\s+nite|fort\s+night)\b", re.I),
     r"\1Fortnite"),
    (re.compile(rf"(\b{_SPOKEN_APP_CONTEXT}\s+)(?:maicraft|maincraft|mine\s+craft)\b", re.I), r"\1Minecraft"),
    (re.compile(rf"(\b{_SPOKEN_APP_CONTEXT}\s+)(?:roblocs|roblocks|rob\s+lox)\b", re.I), r"\1Roblox"),
    (re.compile(rf"(\b{_SPOKEN_APP_CONTEXT}\s+)(?:valorent)\b", re.I), r"\1Valorant"),
    (re.compile(rf"(\b{_SPOKEN_APP_CONTEXT}\s+)(?:iutub|yu\s*tube|yutub)\b", re.I), r"\1YouTube"),
    (re.compile(rf"(\b{_SPOKEN_APP_CONTEXT}\s+)(?:telegramma)\b", re.I), r"\1Telegram"),
    (re.compile(r"\bblocconote\b", re.I), "Blocco note"),
    (re.compile(rf"(\b{_SPOKEN_APP_CONTEXT}\s+)(?:time\s+is|taim\s+is)\b", re.I), r"\1time.is"),
    (re.compile(r"\b(?:cap\s*cut+|capcat|cup\s*cut|cepcat)\b", re.I), "CapCut"),
    (re.compile(r"\b(?:da\s*vinci(?:\s+resolve)?|davinci(?:\s+risolv\w*)?)\b", re.I), "DaVinci Resolve"),
    (re.compile(
        r"\s+è\s+(?=(?:apri|chiudi|avvia|scrivi|manda|invia|crea|cerca|metti|imposta|alza|abbassa|"
        r"fai|leggi|sposta|copia|cestina|elimina|rimuovi|ricorda|mostra|clicca|minimizza|massimizza|"
        r"muta|silenzia|ferma|riprendi|salta)\b)",
        re.I,
    ), " e "),
)


def fix_spoken_text(text: str) -> str:
    out = (text or "").strip()
    if not out:
        return ""
    for pattern, repl in _SPOKEN_SUBS:
        out = pattern.sub(repl, out)
    return out
