from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

from ..i18n import language, tr
from ..speech.textnorm import strip_accents
from ..speech.wake import strip_name

_DAYS = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
_MONTHS = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
           "novembre", "dicembre")
_DAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December")


@dataclass
class Quick:
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    answer: str = ""
    special: str = ""


def _clean(text: str) -> str:
    low = strip_accents((text or "").casefold()).strip().replace("’", "'")
    low = re.sub(r"(\d)[,.](\d)", r"\1.\2", low)
    low = re.sub(r"[!?¿¡;,:\"«»]+", " ", low)
    low = re.sub(r"\.(\s|$)", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    words = low.split()
    if words and strip_name(words[0]) == "":
        low = " ".join(words[1:])
    for lead in ("per favore ", "per piacere ", "puoi ", "potresti ", "mi ", "ehi ", "hey ", "please ", "can you ",
                 "could you "):
        if low.startswith(lead):
            low = low[len(lead):]
    words = low.split()
    if words and strip_name(words[0]) == "":
        low = " ".join(words[1:])
    return re.sub(r"\s+(per favore|grazie|please|thanks|thank you)$", "", low).strip()


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

    if re.fullmatch(r"(?:che ore sono|che ora e|mi dici l'ora|dimmi l'ora|ore|what time is it|what's the time|"
                    r"what is the time|tell me the time|time)", t):
        now = dt.datetime.now()
        if language() == "en":
            return Quick(answer=f"It's {now.hour}:{now.minute:02d}.")
        return Quick(answer=f"Sono le {now.hour}:{now.minute:02d}.")
    if re.fullmatch(r"(?:che giorno e(?: oggi)?|che data e(?: oggi)?|quanti ne abbiamo(?: oggi)?|what day is (?:it|today)|"
                    r"what's the date(?: today)?|what is the date(?: today)?|what's today's date)", t):
        today = dt.date.today()
        if language() == "en":
            return Quick(answer=f"Today is {_DAYS_EN[today.weekday()]}, {_MONTHS_EN[today.month - 1]} {today.day}, "
                                f"{today.year}.")
        return Quick(answer=f"Oggi è {_DAYS[today.weekday()]} {today.day} {_MONTHS[today.month - 1]} {today.year}.")

    math = _MATH.fullmatch(t) or _EN_MATH.fullmatch(t)
    if math:
        answer = _calculate(math.group(1), math.group(2), math.group(3))
        if answer:
            return Quick(answer=answer)

    reminder = _REMINDER.fullmatch(t)
    if reminder:
        amount = _amount(reminder.group(1))
        if amount:
            minutes = amount * (60 if reminder.group(2).startswith("or") else 1)
            text = _as_said(text, reminder.group(3).strip())
            return Quick("reminder", {"action": "add", "text": text[:1].upper() + text[1:], "minutes": minutes})
    reminder = _EN_REMINDER.fullmatch(t)
    if reminder:
        amount = _amount(reminder.group(1))
        if amount:
            minutes = amount * (60 if reminder.group(2).startswith("hour") else 1)
            text = _as_said(text, reminder.group(3).strip())
            return Quick("reminder", {"action": "add", "text": text[:1].upper() + text[1:], "minutes": minutes})

    if _USAGE.search(t) or _EN_USAGE.search(t):
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

    english = _english(t)
    if english is not None:
        return english

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


_NUM = r"(-?\d+(?:[.,]\d+)?)"
_MATH = re.compile(rf"(?:quanto fa|quanto e|calcola|fammi)\s+{_NUM}\s*(per|x|\*|piu|\+|meno|-|diviso|/|:)\s*{_NUM}")
_OPS = {"per": "*", "x": "*", "*": "*", "piu": "+", "+": "+", "meno": "-", "-": "-", "diviso": "/", "/": "/", ":": "/",
        "times": "*", "plus": "+", "minus": "-", "divided by": "/", "over": "/"}
_EN_MATH = re.compile(rf"(?:how much is|what is|what's|calculate)\s+{_NUM}\s*(times|x|\*|plus|\+|minus|-|divided by|"
                      rf"over|/)\s*{_NUM}")


_REMINDER = re.compile(r"(?:ricordami|ricordarmi|fammi ricordare)\s+(?:tra|fra)\s+(\d+|un|una|mezz|due|tre|cinque|dieci|"
                       r"quindici|venti|trenta)\s*'?\s*(minut[oi]|or[ae])\s+(?:di|che|del|della|dello|il|la|lo)?\s*(.{2,})")
_WORDS = {"un": 1, "una": 1, "mezz": 0.5, "due": 2, "tre": 3, "cinque": 5, "dieci": 10, "quindici": 15, "venti": 20,
          "trenta": 30, "a": 1, "an": 1, "one": 1, "half an": 0.5, "two": 2, "three": 3, "five": 5, "ten": 10,
          "fifteen": 15, "twenty": 20, "thirty": 30}
_EN_REMINDER = re.compile(r"remind me\s+in\s+(\d+|a|an|one|half an|two|three|five|ten|fifteen|twenty|thirty)\s+"
                          r"(minutes?|mins?|hours?)\s+(?:to|about|that)?\s*(.{2,})")


def _as_said(original: str, cleaned: str) -> str:
    tail = re.sub(r"[.!?\s]+$", "", original or "")[-len(cleaned):]
    return tail if strip_accents(tail.casefold()) == cleaned else cleaned


def _amount(word: str) -> float:
    return float(word) if word.isdigit() else _WORDS.get(word, 0)


def _calculate(a: str, op: str, b: str) -> str:
    x, y = float(a.replace(",", ".")), float(b.replace(",", "."))
    sign = _OPS[op]
    if sign == "/" and y == 0:
        return tr("Non si può dividere per zero.")
    value = {"*": x * y, "+": x + y, "-": x - y, "/": x / y if y else 0}[sign]
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    if language() == "en":
        return f"That's {text}."
    return f"Fa {text.replace('.', ',')}."


_EN_OPEN = re.compile(r"^(?:open|launch|start|run)\s+(?:the |my )?(.+?)(?:\s+app)?$")
_EN_CLOSE = re.compile(r"^(?:close|quit|exit)\s+(?:the |my )?(.+?)(?:\s+app)?$")
_EN_VOLUME = re.compile(r"^(?:set (?:the )?)?volume (?:to |at )?(\d{1,3})\s*(?:%|percent)?$")
_EN_MEDIA = (
    (re.compile(r"^(?:pause|pause (?:the )?music|stop (?:the )?music)$"), "play_pause"),
    (re.compile(r"^(?:play|resume|resume (?:the )?music|play (?:the )?music)$"), "play_pause"),
    (re.compile(r"^(?:next|skip|next (?:song|track)|skip (?:this )?(?:song|track))$"), "next"),
    (re.compile(r"^(?:previous|previous (?:song|track)|go back)$"), "previous"),
)
_EN_NOT_AN_APP = re.compile(r"\b(and|then|write|send|message|file|folder|document|photo|image|what|how|where|why|"
                            r"when|site|page|link|chat|channel|server)\b")
_EN_SITE = re.compile(
    r"^(?:open|go to|show me|take me to|visit)\s+(?:the (?:site|website) )?"
    r"((?:https?://)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:/\S*)?)"
    r"(?:\s+(?:in|on|with)\s+(?:the\s+)?(?:browser|chrome|edge|brave|firefox|opera))?$"
)
_EN_YOUTUBE = re.compile(r"^(?:play|put on|search(?: for)?)\s+(.+?)\s+on youtube$")
_EN_WEATHER = re.compile(r"\b(weather|forecast|is it (?:going to )?rain(?:ing)?|will it rain|temperature outside)\b")
_EN_CITY = re.compile(r"\b(?:in|for|at)\s+([a-z' ]{2,40}?)(?:\s+(?:today|tomorrow|now|this week|like))?$")
_EN_USAGE = re.compile(
    r"\bhow much\b.*\b(api|apis|key|keys|groq|gemini|claude|openrouter|credit|quota)\b.*\b(left|remaining)\b|"
    r"\b(api|key)s? (?:usage|limits?)\b"
)


def _english(t: str) -> Quick | None:
    level = _EN_VOLUME.fullmatch(t)
    if level and int(level.group(1)) <= 100:
        return Quick("set_volume", {"level": int(level.group(1))})
    if re.fullmatch(r"(?:turn (?:the )?volume up|volume up|louder)", t):
        return Quick("set_volume", {"change": "up", "steps": 5})
    if re.fullmatch(r"(?:turn (?:the )?volume down|volume down|quieter|softer)", t):
        return Quick("set_volume", {"change": "down", "steps": 5})
    if re.fullmatch(r"(?:mute|unmute|mute (?:the )?(?:pc|sound|audio))", t):
        return Quick("set_volume", {"change": "mute"})
    for pattern, action in _EN_MEDIA:
        if pattern.fullmatch(t):
            return Quick("media_control", {"action": action})
    if re.fullmatch(r"(?:take a screenshot|screenshot|take a screen shot)", t):
        return Quick("take_screenshot", {})
    site = _EN_SITE.match(t)
    if site and site.group(1).rsplit(".", 1)[-1] not in _FILE_TYPES:
        return Quick("open_url", {"url": site.group(1)})
    youtube = _EN_YOUTUBE.match(t)
    if youtube:
        return Quick("play_youtube", {"query": youtube.group(1)})
    if _EN_WEATHER.search(t) and len(t.split()) <= 9:
        args: dict[str, Any] = {}
        city = _EN_CITY.search(t)
        if city and not re.search(r"\b(here|home|outside|today|tomorrow|now)$", city.group(1)):
            args["city"] = city.group(1).strip().title()
        if "week" in t:
            args["days"] = 7
        return Quick("weather", args)
    opened = _EN_OPEN.match(t)
    if opened and not _EN_NOT_AN_APP.search(opened.group(1)) and len(opened.group(1).split()) <= 4:
        name = opened.group(1).strip()
        if "." in name:
            return Quick("open_url", {"url": name})
        if name in _KNOWN_SITES:
            return Quick("open_url", {"url": name})
        return Quick("open_app", {"name": name})
    closed = _EN_CLOSE.match(t)
    if closed and not _EN_NOT_AN_APP.search(closed.group(1)) and len(closed.group(1).split()) <= 4:
        return Quick("close_app", {"name": closed.group(1).strip()})
    return None


def spoken(tool: str, outcome: str) -> str:
    if tool == "weather":
        sentences = re.split(r"(?<=\.)\s+", outcome)
        return " ".join(sentences[:3])
    return outcome
