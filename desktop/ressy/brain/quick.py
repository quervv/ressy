from __future__ import annotations

import ast
import datetime as dt
import math
import operator
import random
import re
from dataclasses import dataclass, field
from typing import Any

from ..i18n import language, tr
from ..speech.textnorm import fix_spoken_text, strip_accents
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
    fixed = fix_spoken_text(text or "")
    low = strip_accents(fixed.casefold()).strip().replace("’", "'")
    low = re.sub(r"(\d)[,.](\d)", r"\1.\2", low)
    low = re.sub(r"[!?¿¡;,\"«»]+", " ", low)
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
_SPOKEN_SITE = re.compile(
    r"^(?:apri|aprimi|vai su|vai a|portami su|mostrami|apri il sito(?: di)?)\s+(?:il sito\s+)?"
    r"([a-z0-9-]+)\s+punto\s+([a-z]{2,10})$"
)
_OPEN = re.compile(r"^(?:apri|aprimi|avvia|lancia|fai partire|esegui)\s+(?:l'|l |il |lo |la |i |gli |le |un |una )?(.+)$")
_CLOSE = re.compile(r"^(?:chiudi|chiudimi|esci da|termina)\s+(?:l'|l |il |lo |la |i |gli |le )?(.+)$")
_FOCUS = re.compile(r"^(?:passa a|porta avanti|metti in primo piano|torna su|focus su|vai su)\s+(?:l'|l |il |lo |la )?(.+)$")
_YOUTUBE = re.compile(r"^(?:metti|mettimi|riproduci|fammi sentire|suona|fai partire)\s+(.+?)\s+su youtube$")
_SEARCH_SITE = re.compile(
    r"^(?:cerca|cercami|trova)\s+(.+?)\s+su\s+(google|immagini|google immagini|youtube|amazon|wikipedia|maps|google maps|github|reddit)\s*$"
)
_SEARCH_SITE_FIRST = re.compile(
    r"^(?:cerca|cercami|trova)\s+su\s+(google|immagini|google immagini|youtube|amazon|wikipedia|maps|google maps|github|reddit)\s+(.+)$"
)
_VOLUME_LEVEL = re.compile(r"\bvolume\s+(?:al|a|allo|a quota)?\s*(\d{1,3})\s*(?:%|per ?cento)?$")
_BRIGHTNESS_LEVEL = re.compile(r"\bluminosita\s+(?:al|a|allo)?\s*(\d{1,3})\s*(?:%|per ?cento)?$")
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
    "google drive", "outlook", "prime video", "disney plus", "disney+", "claude", "gemini", "perplexity", "speedtest",
    "ansa", "repubblica", "corriere", "ebay", "subito", "traduttore", "translate",
})

_MEDIA = (
    (re.compile(r"^(?:metti in pausa|pausa|ferma|stoppa|metti pausa)(?: la musica| spotify| youtube| il video)?$"), "play_pause"),
    (re.compile(r"^(?:riprendi|play|fai ripartire|continua)(?: la musica| spotify| il video)?$"), "play_pause"),
    (re.compile(r"^(?:prossima|successiva|avanti|skip|salta)(?: questa)?(?: canzone| traccia| brano)?$|"
                r"^(?:canzone|traccia|brano) successiv[ao]$|^metti la prossima(?: canzone)?$"), "next"),
    (re.compile(r"^(?:precedente|indietro|torna indietro)(?: canzone| traccia| brano)?$|"
                r"^(?:canzone|traccia|brano) precedente$"), "previous"),
)

_OPEN_FOLDER = re.compile(
    r"^(?:apri|aprimi|mostra|mostrami)\s+(?:la cartella(?:\s+dei|\s+delle|\s+di)?\s+|i\s+|le\s+|il\s+)?"
    r"(desktop|scrivania|documenti|download|scaricati|immagini|foto|musica|video|screenshot(?:\s+ressy)?)$"
)
_OPEN_NAMED_FOLDER = re.compile(r"^(?:apri|aprimi)\s+(?:la )?cartella\s+(?:chiamata\s+)?(.+)$")
_CREATE_FOLDER = re.compile(
    r"^(?:crea|creami|fai|fammi)\s+(?:una |la )?cartella\s+(?:chiamata\s+)?(.+?)(?:\s+(?:su|sul|in|nei|nel)\s+(desktop|scrivania|documenti|download))?$"
)

_DISCORD_QUOTED = re.compile(
    r"^(?:su discord\s+)?(?:manda|invia|scrivi)(?:\s+su discord)?\s+a\s+([^\s:]{1,40}(?:\s+[^\s:]{1,30})?)\s+"
    r"(?:su discord\s+)?(?:il messaggio\s+)?[\"«“](.+?)[\"»”]$"
)
_DISCORD_COLON = re.compile(
    r"^(?:su discord\s+)?(?:manda|invia|scrivi)(?:\s+su discord)?\s+a\s+([^:]{1,50}?)\s*:\s*(.+)$"
)
_DISCORD_CHE = re.compile(
    r"^(?:su discord\s+(?:manda|invia|scrivi|di'|dici)|(?:manda|invia|scrivi|di'|dici)\s+su discord)\s+"
    r"(?:un messaggio\s+)?a\s+([^\s].{0,40}?)\s+che\s+(.+)$"
)
_DISCORD_GREETING = frozenset({
    "ciao", "ehi", "hey", "salve", "buongiorno", "buonasera", "buonanotte", "eccomi", "arrivo", "ok", "okay",
    "si", "no", "fatto", "pronto", "ci sono", "sto arrivando", "come stai", "come va", "tutto bene",
})
_DISCORD_DIRECT = re.compile(
    r"^(?:su discord\s+(?:manda|invia|scrivi)|(?:manda|invia|scrivi)\s+su discord)\s+(?:un messaggio\s+)?a\s+([^\s]{1,35})\s+(.+)$"
)
_DISCORD_CURRENT = re.compile(
    r"^(?:su discord\s+)?(?:scrivi|manda|invia)(?:\s+su discord)?\s+(?:qui|nella chat aperta|in questa chat)(?:\s+su discord)?\s*:?\s+(.+)$"
)
_DISCORD_READ = re.compile(
    r"^leggi\s+(?:i messaggi\s+(?:di|da|su)\s+)?discord(?:\s+(?:di|con)\s+(.+))?$"
)
_PRONOUN_AMBIGUOUS = re.compile(r"^che\s+.*\b(lo|la|li|le|gli|glielo|gliela)\b")

_WIN_MIN_ALL = re.compile(r"^(?:mostra (?:il )?desktop|minimizza tutto|abbassa tutto|riduci tutto a icona)$")
_WIN_ACT = re.compile(
    r"^(minimizza|riduci a icona|massimizza|ingrandisci|ripristina|fissa|tieni in primo piano|metti a schermo intero|"
    r"schermo intero su)\s+(?:la finestra(?:\s+di)?\s+)?(.+)$"
)
_WIN_SNAP = re.compile(r"^(?:metti|affianca|sposta)\s+(.+?)\s+(?:a )?(sinistra|destra)$")

_TIMER_START = re.compile(
    r"^(?:metti|imposta|avvia|fai partire)\s+(?:un )?timer\s+(?:di|da)\s+(\d+|un|una|mezz|due|tre|cinque|dieci|quindici|venti|trenta)\s*'?\s*(second[oi]|minut[oi]|or[ae])(?:\s+(?:per|chiamato)\s+(.+))?$"
)
_NOTE_ADD = re.compile(
    r"^(?:segna|aggiungi|scrivi)\s+(?:(?:nella|alla|sulla)\s+(?:lista\s+(?:della\s+)?|nota\s+)?(spesa|note|lavoro|cose da fare)|(?:una )?nota)\s*:?\s+(.+)$"
)
_NOTE_LIST = re.compile(r"^(?:leggi|mostra|dimmi|quali sono)\s+(?:le mie\s+|la\s+)?(?:note|lista(?:\s+della\s+spesa)?)$")
_NOTE_CLEAR = re.compile(r"^(?:svuota|cancella|pulisci)\s+(?:tutte\s+)?(?:le\s+)?(?:note|lista(?:\s+della\s+spesa)?)$")

_SEARCH_MAP = {
    "google": "google", "immagini": "images", "google immagini": "images",
    "youtube": "youtube", "amazon": "amazon", "wikipedia": "wikipedia",
    "maps": "maps", "google maps": "maps", "github": "github", "reddit": "reddit",
}


def _strip_colon(t: str) -> str:
    return re.sub(r"\s*:\s*", " ", t).strip()


def match(text: str) -> Quick | None:
    raw = (text or "").strip()
    t = _clean(raw)
    if not t or len(t.split()) > 22:
        return None
    t_no_colon = _strip_colon(t)

    if re.fullmatch(r"(?:che ore sono|che ora e|mi dici l'ora|dimmi l'ora|ore|what time is it|what's the time|"
                    r"what is the time|tell me the time|time)", t_no_colon):
        now = dt.datetime.now()
        if language() == "en":
            return Quick(answer=f"It's {now.hour}:{now.minute:02d}.")
        return Quick(answer=f"Sono le {now.hour}:{now.minute:02d}.")
    if re.fullmatch(r"(?:che giorno e(?: oggi)?|che data e(?: oggi)?|quanti ne abbiamo(?: oggi)?|what day is (?:it|today)|"
                    r"what's the date(?: today)?|what is the date(?: today)?|what's today's date)", t_no_colon):
        today = dt.date.today()
        if language() == "en":
            return Quick(answer=f"Today is {_DAYS_EN[today.weekday()]}, {_MONTHS_EN[today.month - 1]} {today.day}, "
                                f"{today.year}.")
        return Quick(answer=f"Oggi è {_DAYS[today.weekday()]} {today.day} {_MONTHS[today.month - 1]} {today.year}.")

    if re.fullmatch(r"(?:lancia una moneta|testa o croce|flip a coin|toss a coin)", t_no_colon):
        if language() == "en":
            return Quick(answer=random.choice(["Heads!", "Tails!"]))
        return Quick(answer=random.choice(["Testa!", "Croce!"]))
    if re.fullmatch(r"(?:tira un dado|lancia un dado|roll a dice|roll a die)", t_no_colon):
        n = random.randint(1, 6)
        return Quick(answer=f"È uscito {n}." if language() != "en" else f"You rolled {n}.")
    rand_m = re.fullmatch(r"(?:dimmi un numero|scegli un numero|numero casuale)\s+(?:da|tra)\s+(\d+)\s+(?:a|e)\s+(\d+)", t_no_colon)
    if rand_m:
        lo, hi = int(rand_m.group(1)), int(rand_m.group(2))
        if lo <= hi <= 1_000_000:
            n = random.randint(lo, hi)
            return Quick(answer=f"{n}." if language() == "en" else f"Scelgo {n}.")

    math_ans = _try_math(t)
    if math_ans:
        return Quick(answer=math_ans)

    if re.fullmatch(r"(?:quali promemoria ho|leggi i promemoria|lista promemoria|what reminders do i have|list reminders)", t_no_colon):
        return Quick("reminder", {"action": "list"})
    reminder = _REMINDER.fullmatch(t_no_colon)
    if reminder:
        amount = _amount(reminder.group(1))
        if amount:
            minutes = amount * (60 if reminder.group(2).startswith("or") else 1)
            msg = _as_said(raw, reminder.group(3).strip())
            return Quick("reminder", {"action": "add", "text": msg[:1].upper() + msg[1:], "minutes": minutes})
    rem_at = _REMINDER_AT.fullmatch(t)
    if rem_at:
        hh, mm = int(rem_at.group(1)), int(rem_at.group(2) or 0)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            msg = _as_said(raw, rem_at.group(3).strip())
            return Quick("reminder", {"action": "add", "text": msg[:1].upper() + msg[1:], "at": f"{hh:02d}:{mm:02d}"})
    reminder = _EN_REMINDER.fullmatch(t_no_colon)
    if reminder:
        amount = _amount(reminder.group(1))
        if amount:
            minutes = amount * (60 if reminder.group(2).startswith("hour") else 1)
            msg = _as_said(raw, reminder.group(3).strip())
            return Quick("reminder", {"action": "add", "text": msg[:1].upper() + msg[1:], "minutes": minutes})

    if re.fullmatch(r"(?:avvia|fai partire|inizia) (?:il )?cronometro", t_no_colon):
        return Quick("timer", {"action": "stopwatch_start"})
    if re.fullmatch(r"(?:ferma|stoppa) (?:il )?cronometro", t_no_colon):
        return Quick("timer", {"action": "stopwatch_stop"})
    if re.fullmatch(r"(?:quanto segna|stato del|tempo del) (?:il )?cronometro", t_no_colon):
        return Quick("timer", {"action": "stopwatch_status"})
    if re.fullmatch(r"(?:quanti timer ho|lista timer|timer attivi)", t_no_colon):
        return Quick("timer", {"action": "list"})
    if re.fullmatch(r"(?:annulla|ferma|cancella) (?:il )?timer", t_no_colon):
        return Quick("timer", {"action": "cancel"})
    tm = _TIMER_START.fullmatch(t_no_colon)
    if tm:
        amount = _amount(tm.group(1))
        if amount:
            unit = tm.group(2)
            args: dict[str, Any] = {"action": "start"}
            if unit.startswith("second"):
                args["seconds"] = amount
            elif unit.startswith("or"):
                args["minutes"] = amount * 60
            else:
                args["minutes"] = amount
            if tm.group(3):
                args["label"] = _as_said(raw, tm.group(3).strip())
            return Quick("timer", args)

    if _NOTE_LIST.fullmatch(t_no_colon):
        cat = "spesa" if "spesa" in t_no_colon else ""
        return Quick("notes", {"action": "list", **({"category": cat} if cat else {})})
    if _NOTE_CLEAR.fullmatch(t_no_colon):
        cat = "spesa" if "spesa" in t_no_colon else ""
        return Quick("notes", {"action": "clear", **({"category": cat} if cat else {})})
    nm = _NOTE_ADD.fullmatch(t)
    if nm:
        cat = "spesa" if (nm.group(1) or "").startswith("spesa") else "generale"
        item_text = _as_said(raw, _strip_colon(nm.group(2)))
        return Quick("notes", {"action": "add", "text": item_text, "category": cat})

    if _USAGE.search(t_no_colon) or _EN_USAGE.search(t_no_colon):
        return Quick(special="usage")

    vm = re.fullmatch(
        r"(?:(?:fammi\s+)?(?:edita\w*|monta\w*|modifica\w*|crea\w*)\s+(?:un|il|questo)?\s*video(?:\s+(?:con|in|su)\s+(capcut|davinci(?:\s+resolve)?))?|"
        r"(?:apri\s+(capcut|davinci(?:\s+resolve)?)\s+(?:per|e)\s+(?:editare|montare)\s+(?:un\s+)?video))",
        t_no_colon,
    )
    if vm:
        raw_ed = (vm.group(1) or vm.group(2) or "auto").lower()
        ed = "davinci" if "davinci" in raw_ed else ("capcut" if "capcut" in raw_ed else "auto")
        return Quick("edit_video", {"editor": ed})

    dq = _DISCORD_QUOTED.match(fix_spoken_text(raw.casefold()))
    if dq:
        who = _preserve_case(raw, dq.group(1).strip())
        msg = _preserve_case(raw, dq.group(2).strip())
        if who and msg:
            return Quick("send_discord_message", {"recipient": who, "message": msg, "kind": "user"})
    dc = _DISCORD_COLON.match(t)
    if dc:
        who = _preserve_case(raw, dc.group(1).strip())
        msg = _as_said(raw, dc.group(2).strip())
        if who and msg and not dc.group(1).strip().startswith(("qui", "nella chat", "in questa")):
            return Quick("send_discord_message", {"recipient": who, "message": msg, "kind": "user"})
    dcur = _DISCORD_CURRENT.match(t)
    if dcur and dcur.group(1).strip():
        return Quick("send_discord_message", {"message": _as_said(raw, dcur.group(1).strip()), "kind": "current"})
    dche = _DISCORD_CHE.match(t_no_colon)
    if dche:
        who = dche.group(1).strip()
        msg = dche.group(2).strip()
        if who and msg and not _PRONOUN_AMBIGUOUS.match("che " + msg) and len(who.split()) <= 3:
            return Quick("send_discord_message", {"recipient": _preserve_case(raw, who),
                                                  "message": _as_said(raw, msg), "kind": "user"})
    dd = _DISCORD_DIRECT.match(t_no_colon)
    if dd:
        who = dd.group(1).strip()
        msg_raw = dd.group(2).strip()
        if who and msg_raw in _DISCORD_GREETING:
            return Quick("send_discord_message", {"recipient": _preserve_case(raw, who),
                                                  "message": _as_said(raw, msg_raw), "kind": "user"})
    dr = _DISCORD_READ.fullmatch(t_no_colon)
    if dr:
        who = _preserve_case(raw, dr.group(1).strip()) if dr.group(1) else ""
        return Quick("read_discord_chat", {"recipient": who, "kind": "user" if who else "current"})

    spoken_site = _SPOKEN_SITE.match(t_no_colon)
    if spoken_site:
        return Quick("open_url", {"url": f"{spoken_site.group(1)}.{spoken_site.group(2)}"})
    site = _SITE.match(t_no_colon)
    if site and site.group(1).rsplit(".", 1)[-1] not in _FILE_TYPES:
        return Quick("open_url", {"url": site.group(1)})

    youtube = _YOUTUBE.match(t_no_colon)
    if youtube:
        return Quick("play_youtube", {"query": youtube.group(1)})

    ss = _SEARCH_SITE.match(t_no_colon)
    if ss:
        return Quick("web_search", {"query": ss.group(1).strip(), "site": _SEARCH_MAP[ss.group(2)]})
    ssf = _SEARCH_SITE_FIRST.match(t_no_colon)
    if ssf:
        return Quick("web_search", {"query": ssf.group(2).strip(), "site": _SEARCH_MAP[ssf.group(1)]})

    if _WEATHER.search(t_no_colon) and len(t_no_colon.split()) <= 9:
        args = {}
        city = _CITY.search(t_no_colon)
        if city and not re.search(r"\b(qui|casa|fuori|oggi|domani|adesso)$", city.group(1)):
            args["city"] = city.group(1).strip().title()
        if "settimana" in t_no_colon:
            args["days"] = 7
        return Quick("weather", args)

    level = _VOLUME_LEVEL.search(t_no_colon)
    if level and int(level.group(1)) <= 100:
        return Quick("set_volume", {"level": int(level.group(1))})
    if re.fullmatch(r"volume (?:al )?massimo|massimo volume", t_no_colon):
        return Quick("set_volume", {"level": 100})
    if re.fullmatch(r"volume a zero|azzera (?:il )?volume", t_no_colon):
        return Quick("set_volume", {"level": 0})
    if re.fullmatch(r"alza(?: un po'?| un po)?(?: il)? volume(?: un po'?)?|piu forte|volume piu alto", t_no_colon):
        return Quick("set_volume", {"change": "up", "steps": 5})
    if re.fullmatch(r"abbassa(?: un po'?| un po)?(?: il)? volume(?: un po'?)?|piu piano|volume piu basso", t_no_colon):
        return Quick("set_volume", {"change": "down", "steps": 5})
    if re.fullmatch(r"(?:muto|togli l'audio|togli l audio|togli il muto|riattiva l'audio|riattiva l audio|rimetti l'audio|silenzia(?: il pc)?|metti (?:il )?muto)", t_no_colon):
        return Quick("set_volume", {"change": "mute"})

    bright = _BRIGHTNESS_LEVEL.search(t_no_colon)
    if bright and int(bright.group(1)) <= 100:
        return Quick("system_control", {"action": "brightness_set", "level": int(bright.group(1))})
    if re.fullmatch(r"alza(?: un po)? la luminosita|piu luminosita", t_no_colon):
        return Quick("system_control", {"action": "brightness_up"})
    if re.fullmatch(r"abbassa(?: un po)? la luminosita|meno luminosita", t_no_colon):
        return Quick("system_control", {"action": "brightness_down"})

    for pattern, action in _MEDIA:
        if pattern.fullmatch(t_no_colon):
            return Quick("media_control", {"action": action})

    if re.fullmatch(r"(?:attiva |metti )?(?:la )?modalita scura|(?:metti |attiva )(?:il )?tema scuro", t_no_colon):
        return Quick("system_control", {"action": "dark_mode"})
    if re.fullmatch(r"(?:attiva |metti )?(?:la )?modalita chiara|(?:metti |attiva )(?:il )?tema chiaro", t_no_colon):
        return Quick("system_control", {"action": "light_mode"})
    if re.fullmatch(r"svuota (?:il )?cestino", t_no_colon):
        return Quick("system_control", {"action": "empty_recycle_bin"})
    if re.fullmatch(r"(?:come sta il pc|stato del pc|quanta ram ho|quanta batteria ho|controlla il pc)", t_no_colon):
        return Quick("system_status", {})
    if re.fullmatch(r"(?:cosa|quali programmi|chi) (?:consuma|usa) piu ram|processi ram", t_no_colon):
        return Quick("system_control", {"action": "top_processes"})
    if re.fullmatch(r"(?:quanto spazio ho sul disco|spazio su disco|spazio libero)", t_no_colon):
        return Quick("system_control", {"action": "disk_space"})
    if re.fullmatch(r"(?:qual e il mio ip|stato della rete|stato rete|che wifi uso)", t_no_colon):
        return Quick("system_control", {"action": "network_info"})
    if re.fullmatch(r"blocca (?:il )?pc", t_no_colon):
        return Quick("pc_power", {"action": "lock"})
    if re.fullmatch(r"annulla (?:lo )?spegnimento|annulla (?:il )?riavvio", t_no_colon):
        return Quick("pc_power", {"action": "cancel"})

    if re.fullmatch(r"(?:leggi gli appunti|cosa ho negli appunti|cosa ho copiato|mostra gli appunti)", t_no_colon):
        return Quick("clipboard", {"action": "get"})
    if re.fullmatch(r"(?:scorri|scrolla)(?: verso il| in)? (?:giu|basso)", t_no_colon):
        return Quick("mouse_action", {"action": "scroll_down"})
    if re.fullmatch(r"(?:scorri|scrolla)(?: verso l'| in)? (?:su|alto)", t_no_colon):
        return Quick("mouse_action", {"action": "scroll_up"})

    english = _english(t_no_colon)
    if english is not None:
        return english

    if re.fullmatch(r"(?:fai|fammi|scatta) (?:uno |lo )?screenshot(?: dello schermo)?|screenshot", t_no_colon):
        return Quick("take_screenshot", {})
    shot_app = re.fullmatch(r"(?:fai|fammi|scatta) (?:uno |lo )?screenshot (?:di|a|su) (.+)", t_no_colon)
    if shot_app and len(shot_app.group(1).split()) <= 3:
        return Quick("take_screenshot", {"app": shot_app.group(1).strip()})

    if _WIN_MIN_ALL.fullmatch(t_no_colon):
        return Quick("window_action", {"action": "minimize_all"})
    if re.fullmatch(r"cambia finestra|prossima finestra|finestra precedente", t_no_colon):
        return Quick("window_action", {"action": "switch_next"})
    if re.fullmatch(r"(?:quali finestre sono aperte|che finestre sono aperte|finestre aperte|che app sono aperte)", t_no_colon):
        return Quick("list_windows", {})
    if re.fullmatch(r"schermo intero|togli schermo intero|metti a schermo intero", t_no_colon):
        return Quick("window_action", {"action": "fullscreen"})
    ws = _WIN_SNAP.fullmatch(t_no_colon)
    if ws and len(ws.group(1).split()) <= 3:
        return Quick("window_action", {
            "action": "snap_left" if ws.group(2) == "sinistra" else "snap_right",
            "app": ws.group(1).strip(),
        })
    wa = _WIN_ACT.fullmatch(t_no_colon)
    if wa and len(wa.group(2).split()) <= 3:
        verb, target_app = wa.group(1), wa.group(2).strip()
        act_map = {
            "minimizza": "minimize", "riduci a icona": "minimize",
            "massimizza": "maximize", "ingrandisci": "maximize",
            "ripristina": "restore",
            "fissa": "always_on_top", "tieni in primo piano": "always_on_top",
            "metti a schermo intero": "fullscreen", "schermo intero su": "fullscreen",
        }
        return Quick("window_action", {"action": act_map[verb], "app": target_app})

    known_f = _OPEN_FOLDER.fullmatch(t_no_colon)
    if known_f:
        return Quick("open_folder", {"name": known_f.group(1).strip()})
    named_f = _OPEN_NAMED_FOLDER.fullmatch(t_no_colon)
    if named_f and len(named_f.group(1).split()) <= 4:
        return Quick("open_folder", {"name": _as_said(raw, named_f.group(1).strip())})
    cf = _CREATE_FOLDER.fullmatch(t_no_colon)
    if cf and len(cf.group(1).split()) <= 5 and not _NOT_AN_APP.search(cf.group(1)):
        args = {"name": _preserve_case(raw, cf.group(1).strip())}
        if cf.group(2):
            args["folder"] = cf.group(2).strip()
        return Quick("create_folder", args)

    focused = _FOCUS.match(t_no_colon)
    if focused and not _NOT_AN_APP.search(focused.group(1)) and len(focused.group(1).split()) <= 4 and "." not in focused.group(1):
        name = focused.group(1).strip()
        if name in _KNOWN_SITES:
            return Quick("open_url", {"url": name})
        return Quick("focus_app", {"name": name})

    opened = _OPEN.match(t_no_colon)
    if opened and not _NOT_AN_APP.search(opened.group(1)) and len(opened.group(1).split()) <= 4 \
            and "." not in opened.group(1):
        name = opened.group(1).strip()
        if name in _KNOWN_SITES:
            return Quick("open_url", {"url": name})
        return Quick("open_app", {"name": name})

    closed = _CLOSE.match(t_no_colon)
    if closed and not _NOT_AN_APP.search(closed.group(1)) and len(closed.group(1).split()) <= 4:
        return Quick("close_app", {"name": closed.group(1).strip()})
    return None


_NUM = r"(-?\d+(?:[.,]\d+)?)"
_MATH = re.compile(rf"(?:quanto fa|quanto e|calcola|fammi)\s+{_NUM}\s*(per|x|\*|piu|\+|meno|-|diviso|/|:)\s*{_NUM}")
_OPS = {"per": "*", "x": "*", "*": "*", "piu": "+", "+": "+", "meno": "-", "-": "-", "diviso": "/", "/": "/", ":": "/",
        "times": "*", "plus": "+", "minus": "-", "divided by": "/", "over": "/"}
_EN_MATH = re.compile(rf"(?:how much is|what is|what's|calculate)\s+{_NUM}\s*(times|x|\*|plus|\+|minus|-|divided by|"
                      rf"over|/)\s*{_NUM}")
_PERCENT = re.compile(rf"(?:quanto e|quanto fa|calcola|what is|what's)?\s*(?:il |l')?{_NUM}\s*(?:%|per ?cento|percent)\s+(?:di|of)\s+{_NUM}")
_SQRT = re.compile(rf"(?:radice(?: quadrata)? di|square root of)\s+{_NUM}")
_EXPR_HEAD = re.compile(r"^(?:quanto fa|quanto e|calcola|how much is|what is|what's|calculate)\s+(.+)$")
_SAFE_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
                ast.Pow: operator.pow, ast.Mod: operator.mod}


def _eval_expr(expr: str) -> float | None:
    expr = re.sub(r"\b(per|times)\b", "*", expr)
    expr = re.sub(r"\b(piu|plus)\b", "+", expr)
    expr = re.sub(r"\b(meno|minus)\b", "-", expr)
    expr = re.sub(r"\b(diviso|divided by|over)\b", "/", expr)
    expr = expr.replace("x", "*").replace(":", "/")
    if not re.fullmatch(r"[\d\s.+\-*/()%]+", expr) or len(expr) > 60:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            val = ev(node.operand)
            return val if isinstance(node.op, ast.UAdd) else -val
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BINOPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("exponent too large")
            return _SAFE_BINOPS[type(node.op)](left, right)
        raise ValueError("unsupported")

    return ev(tree)


def _format_num(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    if text == "-0":
        text = "0"
    if language() == "en":
        return f"That's {text}."
    return f"Fa {text.replace('.', ',')}."


def _try_math(t: str) -> str | None:
    m = _MATH.fullmatch(t) or _EN_MATH.fullmatch(t)
    if m:
        return _calculate(m.group(1), m.group(2), m.group(3))
    pct = _PERCENT.fullmatch(t)
    if pct:
        a = float(pct.group(1).replace(",", "."))
        b = float(pct.group(2).replace(",", "."))
        return _format_num(a * b / 100.0)
    sq = _SQRT.fullmatch(t)
    if sq:
        v = float(sq.group(1).replace(",", "."))
        if v < 0:
            return tr("Non posso calcolare la radice di un numero negativo.")
        return _format_num(math.sqrt(v))
    em = _EXPR_HEAD.fullmatch(t)
    if em:
        try:
            val = _eval_expr(em.group(1))
        except ZeroDivisionError:
            return tr("Non si può dividere per zero.")
        except (ValueError, OverflowError):
            return None
        if val is not None:
            return _format_num(val)
    return None


_REMINDER = re.compile(r"(?:ricordami|ricordarmi|fammi ricordare)\s+(?:tra|fra)\s+(\d+|un|una|mezz|due|tre|cinque|dieci|"
                       r"quindici|venti|trenta)\s*'?\s*(minut[oi]|or[ae])\s+(?:di|che|del|della|dello|il|la|lo)?\s*(.{2,})")
_REMINDER_AT = re.compile(r"(?:ricordami|ricordarmi|fammi ricordare)\s+alle\s+(\d{1,2})(?::(\d{2}))?\s+(?:di|che|il|la|lo)?\s*(.{2,})")
_WORDS = {"un": 1, "una": 1, "mezz": 0.5, "due": 2, "tre": 3, "cinque": 5, "dieci": 10, "quindici": 15, "venti": 20,
          "trenta": 30, "a": 1, "an": 1, "one": 1, "half an": 0.5, "two": 2, "three": 3, "five": 5, "ten": 10,
          "fifteen": 15, "twenty": 20, "thirty": 30}
_EN_REMINDER = re.compile(r"remind me\s+in\s+(\d+|a|an|one|half an|two|three|five|ten|fifteen|twenty|thirty)\s+"
                          r"(minutes?|mins?|hours?)\s+(?:to|about|that)?\s*(.{2,})")


def _as_said(original: str, cleaned: str) -> str:
    tail = re.sub(r"[.!?\s]+$", "", original or "")[-len(cleaned):]
    return tail if strip_accents(tail.casefold()) == cleaned else cleaned


def _preserve_case(original: str, cleaned: str) -> str:
    if not cleaned:
        return ""
    found = re.search(re.escape(cleaned), original or "", re.IGNORECASE)
    if found:
        return found.group(0)
    words = cleaned.split()
    if len(words) == 1:
        for tok in re.findall(r"[^\s,;:.!?\"«»“”]+", original or ""):
            if strip_accents(tok.casefold()) == cleaned:
                return tok
    return cleaned


def _amount(word: str) -> float:
    return float(word) if word.isdigit() else _WORDS.get(word, 0)


def _calculate(a: str, op: str, b: str) -> str:
    x, y = float(a.replace(",", ".")), float(b.replace(",", "."))
    sign = _OPS[op]
    if sign == "/" and y == 0:
        return tr("Non si può dividere per zero.")
    value = {"*": x * y, "+": x + y, "-": x - y, "/": x / y if y else 0}[sign]
    return _format_num(value)


_EN_OPEN = re.compile(r"^(?:open|launch|start|run)\s+(?:the |my )?(.+?)(?:\s+app)?$")
_EN_CLOSE = re.compile(r"^(?:close|quit|exit)\s+(?:the |my )?(.+?)(?:\s+app)?$")
_EN_FOCUS = re.compile(r"^(?:switch to|focus|bring up)\s+(?:the |my )?(.+?)(?:\s+app)?$")
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
_EN_YOUTUBE = re.compile(r"^(?:play|put on)\s+(.+?)\s+on youtube$")
_EN_SEARCH = re.compile(r"^search(?: for)?\s+(.+?)\s+on\s+(google|youtube|amazon|wikipedia|maps|github|reddit)$")
_EN_WEATHER = re.compile(r"\b(weather|forecast|is it (?:going to )?rain(?:ing)?|will it rain|temperature outside)\b")
_EN_CITY = re.compile(r"\b(?:in|for|at)\s+([a-z' ]{2,40}?)(?:\s+(?:today|tomorrow|now|this week|like))?$")
_EN_USAGE = re.compile(
    r"\bhow much\b.*\b(api|apis|key|keys|groq|gemini|claude|openrouter|credit|quota)\b.*\b(left|remaining)\b|"
    r"\b(api|key)s? (?:usage|limits?)\b"
)
_EN_TIMER = re.compile(
    r"^(?:set|start) a timer for\s+(\d+|a|an|one|half an|two|three|five|ten|fifteen|twenty|thirty)\s+"
    r"(seconds?|secs?|minutes?|mins?|hours?)(?:\s+(?:for|named)\s+(.+))?$"
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
    if re.fullmatch(r"(?:show desktop|minimize all(?: windows)?)", t):
        return Quick("window_action", {"action": "minimize_all"})
    if re.fullmatch(r"(?:start stopwatch|start the stopwatch)", t):
        return Quick("timer", {"action": "stopwatch_start"})
    if re.fullmatch(r"(?:stop stopwatch|stop the stopwatch)", t):
        return Quick("timer", {"action": "stopwatch_stop"})
    if re.fullmatch(r"(?:read clipboard|what's on my clipboard|what is on my clipboard)", t):
        return Quick("clipboard", {"action": "get"})
    if re.fullmatch(r"(?:scroll down)", t):
        return Quick("mouse_action", {"action": "scroll_down"})
    if re.fullmatch(r"(?:scroll up)", t):
        return Quick("mouse_action", {"action": "scroll_up"})
    if re.fullmatch(r"(?:lock (?:the )?pc|lock screen)", t):
        return Quick("pc_power", {"action": "lock"})
    if re.fullmatch(r"(?:empty (?:the )?(?:recycle )?bin|empty trash)", t):
        return Quick("system_control", {"action": "empty_recycle_bin"})
    if re.fullmatch(r"(?:enable |turn on )?dark mode", t):
        return Quick("system_control", {"action": "dark_mode"})
    if re.fullmatch(r"(?:enable |turn on )?light mode", t):
        return Quick("system_control", {"action": "light_mode"})
    evm = re.fullmatch(
        r"(?:(?:edit|make|create)\s+(?:a\s+|my\s+|this\s+)?video(?:\s+(?:with|in|on|using)\s+(capcut|davinci(?:\s+resolve)?))?|"
        r"open\s+(capcut|davinci(?:\s+resolve)?)\s+(?:to|and)\s+edit\s+(?:a\s+)?video)",
        t,
    )
    if evm:
        raw_ed = (evm.group(1) or evm.group(2) or "auto").lower()
        ed = "davinci" if "davinci" in raw_ed else ("capcut" if "capcut" in raw_ed else "auto")
        return Quick("edit_video", {"editor": ed})
    et = _EN_TIMER.fullmatch(t)
    if et:
        amount = _amount(et.group(1))
        if amount:
            unit = et.group(2)
            args: dict[str, Any] = {"action": "start"}
            if unit.startswith("sec"):
                args["seconds"] = amount
            elif unit.startswith("hour"):
                args["minutes"] = amount * 60
            else:
                args["minutes"] = amount
            if et.group(3):
                args["label"] = et.group(3).strip()
            return Quick("timer", args)
    site = _EN_SITE.match(t)
    if site and site.group(1).rsplit(".", 1)[-1] not in _FILE_TYPES:
        return Quick("open_url", {"url": site.group(1)})
    youtube = _EN_YOUTUBE.match(t)
    if youtube:
        return Quick("play_youtube", {"query": youtube.group(1)})
    es = _EN_SEARCH.match(t)
    if es:
        return Quick("web_search", {"query": es.group(1).strip(), "site": es.group(2)})
    if _EN_WEATHER.search(t) and len(t.split()) <= 9:
        args = {}
        city = _EN_CITY.search(t)
        if city and not re.search(r"\b(here|home|outside|today|tomorrow|now)$", city.group(1)):
            args["city"] = city.group(1).strip().title()
        if "week" in t:
            args["days"] = 7
        return Quick("weather", args)
    focused = _EN_FOCUS.match(t)
    if focused and not _EN_NOT_AN_APP.search(focused.group(1)) and len(focused.group(1).split()) <= 4:
        return Quick("focus_app", {"name": focused.group(1).strip()})
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
