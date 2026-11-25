from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

from ..speech.textnorm import strip_accents
from ..speech.wake import strip_name

_DAYS = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
_MONTHS = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
           "novembre", "dicembre")


@dataclass
class Quick:
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    answer: str = ""
    special: str = ""


def _clean(text: str) -> str:
    low = strip_accents((text or "").casefold()).strip()
    low = re.sub(r"[!?¿¡;,:\"«»]+", " ", low)
    low = re.sub(r"\.(\s|$)", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    words = low.split()
    if words and strip_name(words[0]) == "":
        low = " ".join(words[1:])
    for lead in ("per favore ", "per piacere ", "puoi ", "potresti ", "mi ", "ehi ", "hey "):
        if low.startswith(lead):
            low = low[len(lead):]
    return re.sub(r"\s+(per favore|grazie)$", "", low).strip()


_SITE = re.compile(
    r"^(?:apri|aprimi|vai su|vai a|portami su|mostrami|apri il sito(?: di)?)\s+(?:il sito\s+)?"
    r"((?:https?://)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:/\S*)?)"
    r"(?:\s+(?:sul|nel|in|con)\s+(?:il\s+)?(?:browser|chrome|edge|brave|firefox|opera))?$"
)
_OPEN = re.compile(r"^(?:apri|aprimi|avvia|lancia|fai partire|esegui)\s+(?:l'|l |il |lo |la |i |gli |le |un |una )?(.+)$")
_CLOSE = re.compile(r"^(?:chiudi|chiudimi|esci da|termina)\s+(?:l'|l |il |lo |la |i |gli |le )?(.+)$")
_YOUTUBE = re.compile(r"^(?:metti|mettimi|riproduci|fammi sentire|suona|fai partire|cerca)\s+(.+?)\s+su youtube$")
_VOLUME_LEVEL = re.compile(r"\bvolume\s+(?:al|a|allo|a quota)?\s*(\d{1,3})\s*(?:%|per ?cento)?$")
_WEATHER = re.compile(r"\b(meteo|che tempo (?:fa|fara|ce|c e|c'e)|previsioni|piove|pioggia domani|temperatura fuori)\b")
_CITY = re.compile(r"\b(?:a|ad|su|per|in|di)\s+([a-z' ]{2,40}?)(?:\s+(?:oggi|domani|adesso|ora|questa settimana))?$")
_USAGE = re.compile(
    r"\b(usage|utilizzo|limit[ei]|consumo|credit[oi]|token|richieste)\b.*\b(rest\w*|riman\w*|ho|api|chiav\w*)\b|"
    r"\bquanto (?:mi )?(?:resta|rimane|ne resta|ne rimane)\b.*\b(api|chiav\w*|groq|gemini|claude|openrouter)\b"
)
_NOT_AN_APP = re.compile(
    r"\b(e poi|e scrivi|e metti|e cerca|e manda|e apri|e chiudi|scrivi|manda|messaggio|file|cartella|documento|"
    r"foto|immagine|che|come|dove|perche|quando|sito|pagina|link|chat|canale|server|conversazione|cosa)\b"
)
_FILE_TYPES = frozenset({"txt", "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "exe", "png", "jpg", "jpeg",
                         "gif", "mp3", "mp4", "wav", "zip", "rar", "py", "json", "csv", "lnk", "bat", "msi"})
_KNOWN_SITES = frozenset({
    "youtube", "gmail", "google", "netflix", "twitch", "instagram", "facebook", "tiktok", "amazon", "github",
    "reddit", "chatgpt", "whatsapp web", "twitter", "x", "linkedin", "wikipedia", "google maps", "maps", "drive",
    "google drive", "outlook", "prime video", "disney plus", "disney+",
})

_MEDIA = (
    (re.compile(r"^(?:metti in pausa|pausa|ferma la musica|stoppa la musica|metti pausa)$"), "play_pause"),
    (re.compile(r"^(?:riprendi|play|fai ripartire la musica|riprendi la musica|continua la musica)$"), "play_pause"),
    (re.compile(r"^(?:prossima|successiva|avanti|skip|salta)(?: canzone| traccia| brano)?$|"
                r"^(?:canzone|traccia|brano) successiv[ao]$|^metti la prossima(?: canzone)?$"), "next"),
    (re.compile(r"^(?:precedente|indietro|torna indietro)(?: canzone| traccia| brano)?$|"
                r"^(?:canzone|traccia|brano) precedente$"), "previous"),
)


def match(text: str) -> Quick | None:
    t = _clean(text)
    if not t or len(t.split()) > 12:
        return None

    if re.fullmatch(r"(?:che ore sono|che ora e|mi dici l'ora|dimmi l'ora|ore)", t):
        now = dt.datetime.now()
        return Quick(answer=f"Sono le {now.hour}:{now.minute:02d}.")
    if re.fullmatch(r"(?:che giorno e(?: oggi)?|che data e(?: oggi)?|quanti ne abbiamo(?: oggi)?)", t):
        today = dt.date.today()
        return Quick(answer=f"Oggi è {_DAYS[today.weekday()]} {today.day} {_MONTHS[today.month - 1]} {today.year}.")

    if _USAGE.search(t):
        return Quick(special="usage")

    site = _SITE.match(t)
    if site and site.group(1).rsplit(".", 1)[-1] not in _FILE_TYPES:
        return Quick("open_url", {"url": site.group(1)})

    youtube = _YOUTUBE.match(t)
    if youtube:
        return Quick("play_youtube", {"query": youtube.group(1)})

    if _WEATHER.search(t) and len(t.split()) <= 9:
        args: dict[str, Any] = {}
        city = _CITY.search(t)
        if city and not re.search(r"\b(qui|casa|fuori|oggi|domani|adesso)$", city.group(1)):
            args["city"] = city.group(1).strip().title()
        if "settimana" in t:
            args["days"] = 7
        return Quick("weather", args)

    level = _VOLUME_LEVEL.search(t)
    if level and int(level.group(1)) <= 100:
        return Quick("set_volume", {"level": int(level.group(1))})
    if re.fullmatch(r"alza(?: un po'?| un po)?(?: il)? volume(?: un po'?)?|piu forte|volume piu alto", t):
        return Quick("set_volume", {"change": "up", "steps": 5})
    if re.fullmatch(r"abbassa(?: un po'?| un po)?(?: il)? volume(?: un po'?)?|piu piano|volume piu basso", t):
        return Quick("set_volume", {"change": "down", "steps": 5})
    if re.fullmatch(r"(?:muto|togli l'audio|togli l audio|silenzia(?: il pc)?|metti (?:il )?muto)", t):
        return Quick("set_volume", {"change": "mute"})

    for pattern, action in _MEDIA:
        if pattern.fullmatch(t):
            return Quick("media_control", {"action": action})

    if re.fullmatch(r"(?:fai|fammi|scatta) (?:uno |lo )?screenshot(?: dello schermo)?|screenshot", t):
        return Quick("take_screenshot", {})

    opened = _OPEN.match(t)
    if opened and not _NOT_AN_APP.search(opened.group(1)) and len(opened.group(1).split()) <= 4 \
            and "." not in opened.group(1):
        name = opened.group(1).strip()
        if name in _KNOWN_SITES:
            return Quick("open_url", {"url": name})
        return Quick("open_app", {"name": name})

    closed = _CLOSE.match(t)
    if closed and not _NOT_AN_APP.search(closed.group(1)) and len(closed.group(1).split()) <= 4:
        return Quick("close_app", {"name": closed.group(1).strip()})
    return None


def spoken(tool: str, outcome: str) -> str:
    if tool == "weather":
        sentences = re.split(r"(?<=\.)\s+", outcome)
        return " ".join(sentences[:3])
    return outcome
