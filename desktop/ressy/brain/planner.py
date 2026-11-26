from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from ..speech.textnorm import fix_spoken_text, strip_accents

log = logging.getLogger("ressy.brain")

MAX_PLAN_STEPS = 12


@dataclass(frozen=True)
class Step:
    text: str
    needs_previous: bool = False


_IMPERATIVES = (
    "apri", "chiudi", "avvia", "lancia", "esegui", "scrivi", "manda", "invia", "rispondi", "crea", "cancella",
    "elimina", "metti", "suona", "riproduci", "fai", "cerca", "trova", "leggi", "controlla", "imposta", "alza",
    "abbassa", "togli", "spegni", "riavvia", "sospendi", "blocca", "ferma", "riprendi", "salta", "copia", "incolla",
    "premi", "clicca", "porta", "vai", "torna", "ricorda", "salva", "sposta", "rinomina", "cambia", "accendi",
    "attiva", "disattiva", "scarica", "mostra", "guarda", "aggiungi", "svuota", "minimizza", "ingrandisci", "silenzia",
    "aumenta", "diminuisci", "seleziona", "digita", "passa", "prendi", "segna", "programma", "rimuovi", "registra",
    "fotografa", "calcola", "traduci", "spiega", "riassumi", "elenca", "conta", "verifica", "aggiorna", "installa",
    "muta", "smuta", "zittisci", "riattiva", "cestina", "taglia", "annulla", "ripeti", "zoomma", "scorri", "scrolla",
    "riduci", "massimizza", "affianca", "organizza", "avvisa", "contatta", "chiama", "chiedi", "nascondi", "pulisci",
    "riordina", "ordina", "connetti", "disconnetti", "collega", "scollega", "riapri", "ricarica", "sblocca",
    "iberna", "applica", "regola", "modifica", "edita", "converti", "estrai", "comprimi", "zippa", "decomprimi",
    "scatta", "cattura", "stampa", "ascolta", "pausa", "stoppa", "dici", "fissa", "appunta",
)
_WHOLE = frozenset({"fammi", "dimmi", "dammi", "fallo", "falla", "fagli", "digli", "dille", "dagli", "di'", "di’",
                    "vammi", "stammi"})
_CLITICS = ("", "mi", "ti", "gli", "le", "lo", "la", "li", "ci", "ne", "glielo", "gliela", "glieli", "gliele",
            "gliene", "melo", "mela", "meli", "mele", "telo", "tela", "celo", "cela", "mene", "cene", "vi")
_ENGLISH = frozenset({
    "open", "close", "start", "launch", "run", "write", "send", "message", "text", "tell", "create", "make", "delete",
    "remove", "play", "pause", "stop", "resume", "skip", "search", "find", "look", "read", "check", "set", "turn",
    "mute", "unmute", "raise", "lower", "shut", "restart", "reboot", "lock", "copy", "paste", "press", "click", "go",
    "remind", "save", "move", "rename", "show", "take", "put", "type", "switch", "bring", "add", "empty", "minimize",
    "maximize", "download", "install", "translate", "explain", "summarize", "list", "calculate", "give", "email",
    "scroll", "snap", "pin", "zip", "unzip", "extract", "compress", "compose", "reply",
})
_FILLERS = frozenset({
    "e", "ed", "poi", "dopo", "quindi", "infine", "anche", "inoltre", "pure", "per", "favore", "piacere", "ressy",
    "ora", "adesso", "subito", "anzi", "allora", "ok", "okay", "ah", "eh", "si", "dopodiche", "successivamente",
    "prima", "di", "tutto", "mi", "ti", "ci", "gli", "le", "lo", "la", "li", "ne", "vi", "me", "te", "ce", "ve",
    "glielo", "gliela", "glieli", "gliele", "melo", "mela", "intanto", "mentre", "frattempo", "nel", "cosi", "magari",
    "infatti", "and", "then", "also", "after", "that", "now", "please", "finally", "next", "lastly", "first",
    "afterwards", "so", "okay", "while", "meanwhile",
})
_MODALS = frozenset({"puoi", "potresti", "riesci", "riusciresti", "vorrei", "voglio", "devi", "dovresti", "can",
                     "could", "would", "will", "a", "ad", "che", "tu", "you"})
_INFINITIVE_STEMS = (
    "aprir", "chiuder", "avviar", "lanciar", "eseguir", "scriver", "mandar", "inviar", "risponder", "crear",
    "cancellar", "eliminar", "metter", "suonar", "riprodurr", "far", "cercar", "trovar", "legger", "controllar",
    "impostar", "alzar", "abbassar", "toglier", "spegner", "riavviar", "sospender", "bloccar", "fermar", "riprender",
    "saltar", "copiar", "incollar", "premer", "cliccar", "portar", "andar", "tornar", "ricordar", "salvar",
    "spostar", "rinominar", "cambiar", "accender", "attivar", "disattivar", "scaricar", "mostrar", "guardar",
    "aggiunger", "dir", "dar", "calcolar", "tradurr", "scorr", "scrollar", "minimizzar", "massimizzar",
    "ingrandir", "affiancar", "svuotar", "cestinar", "estrarr", "comprimer", "zippar", "riassumer", "spiegar",
)
_INFINITIVE_ENDINGS = ("e", "mi", "ti", "gli", "le", "lo", "la", "li", "ci", "ne", "glielo", "gliela")

_CUT = re.compile(
    r"([.;!?]+\s+|,\s*|\s+(?:e|ed|poi|dopo|dopodich[eé]|quindi|infine|intanto|mentre|nel\s+frattempo|subito\s+dopo|"
    r"cos[iì]|and|then|while|meanwhile)\s+)",
    re.IGNORECASE,
)


def _words(text: str) -> list[str]:
    return re.findall(r"[\w'’]+", strip_accents(text.casefold()))


def _is_imperative(word: str) -> bool:
    if word in _WHOLE or word in _ENGLISH:
        return True
    for stem in _IMPERATIVES:
        if word.startswith(stem) and word[len(stem):] in _CLITICS:
            return True
    return False


def _is_infinitive(word: str) -> bool:
    for stem in _INFINITIVE_STEMS:
        if word.startswith(stem) and word[len(stem):] in _INFINITIVE_ENDINGS:
            return True
    return False


def starts_action(segment: str, *, allow_infinitive: bool = False) -> bool:
    polite = allow_infinitive
    for word in _words(segment)[:6]:
        if word in _MODALS:
            polite = True
            continue
        if word in _FILLERS:
            continue
        return _is_imperative(word) or (polite and _is_infinitive(word))
    return False


def _uses_modal(segment: str) -> bool:
    return any(w in _MODALS for w in _words(segment)[:4])


_MESSAGE_VERBS = re.compile(
    r"^\W*(?:(?:e|poi|ed|and|then)\s+)*(?:scriv\w*|mand\w*|invi\w*|rispond\w*|digit\w*|di'|digli|dille|"
    r"write|send|text|message|tell|type|reply)\b", re.IGNORECASE,
)
_QUOTES = (("«", "»"), ("“", "”"))


def _open_message(piece: str) -> bool:
    if not _MESSAGE_VERBS.match(piece):
        return False
    for left, right in _QUOTES:
        if piece.count(left) > piece.count(right):
            return True
    if piece.count('"') % 2:
        return True
    quoted = any(left in piece for left, _ in _QUOTES) or '"' in piece
    return ":" in piece and not quoted
_STRONG = re.compile(r"^\s*(?:[.;!?,]+\s*)?(?:(?:e|ed|and)\s+)?(?:poi|dopo|dopodich[eé]|infine|intanto|then|after\s+that)\b",
                     re.IGNORECASE)
_UNJOINED = re.compile(
    r"^((?:(?:e|poi|ressy|ciao|ehi|hey|puoi|potresti|vorrei|per\s+favore)\s+)*"
    r"(?:apri\w*|avvia\w*|lancia\w*|chiudi\w*|passa\s+a|vai\s+su|open|launch|start)\s+"
    r"(?:(?:il|lo|la|l'|un|una)\s+)?[\w.+-]+(?:\s+[\w.+-]+){0,2}?)\s+"
    r"(?=(?:scriv\w*|mand\w*|invi\w*|crea\w*|cerca\w*|mett\w*|alza\w*|abbassa\w*|fai|fammi|leggi\w*|"
    r"copia\w*|incolla\w*|clicca\w*|minimizz\w*|massimizz\w*|affianc\w*|write|send|create|search|play)\b)",
    re.IGNORECASE,
)


def _split_unjoined(piece: str) -> list[str]:
    if _open_message(piece):
        return [piece]
    match = _UNJOINED.match(piece.strip())
    if match is None:
        return [piece]
    head = match.group(1).strip()
    tail = piece.strip()[match.end(1):].strip()
    last_word = _words(head)[-1] if _words(head) else ""
    if last_word in ("che", "di", "a", "per", "da", "con", "su", "in"):
        return [piece]
    if head and tail and starts_action(tail):
        return [head, tail]
    return [piece]


def split_actions(text: str) -> list[str]:
    text = fix_spoken_text((text or "").strip())
    if not text:
        return []
    parts = _CUT.split(text)
    pieces: list[list[str]] = [["", parts[0]]]
    in_message = _open_message(parts[0])
    polite_chain = _uses_modal(parts[0])
    for index in range(1, len(parts), 2):
        cut, piece = parts[index], parts[index + 1] if index + 1 < len(parts) else ""
        new_action = starts_action(piece, allow_infinitive=polite_chain) and (
            not in_message or bool(_STRONG.match(cut + piece))
        )
        if new_action and piece.strip():
            pieces.append([cut, piece])
            polite_chain = polite_chain or _uses_modal(piece)
        else:
            pieces[-1][1] += cut + piece
        in_message = _open_message(pieces[-1][1])
    if len(pieces) > 1 and not starts_action(pieces[0][1]):
        pieces[0:2] = [["", pieces[0][1] + pieces[1][0] + pieces[1][1]]]
    out = [re.sub(r"^[\s,;.]+|[\s,;]+$", "", piece) for _, piece in pieces]
    out = out[:1] + [_LEADING.sub("", piece) for piece in out[1:]]
    expanded: list[str] = []
    for piece in out:
        if piece:
            expanded.extend(_split_unjoined(piece))
    return [p for p in expanded if p]


_LEADING = re.compile(
    r"^(?:(?:e|ed|poi|dopo|dopodich[eé]|quindi|infine|anche|inoltre|intanto|mentre|nel\s+frattempo|"
    r"subito\s+dopo|cos[iì]|and|then|also|finally|while|meanwhile)\b[\s,]*)+",
    re.IGNORECASE,
)


def looks_compound(text: str) -> bool:
    return len(split_actions(text)) >= 2


PLAN_SYSTEM_IT = """Sei il pianificatore di Ressy, un'assistente che agisce sul PC Windows dell'utente.
Ricevi una richiesta e la dividi nelle azioni da fare, nell'ordine in cui vanno fatte.
Rispondi solo con JSON: {"steps": [{"do": "...", "needs_previous": false}]}

Regole:
- Un passo = una sola azione (aprire un'app, mandare un messaggio, creare una cartella, cercare, rispondere a una domanda...), scritta come un ordine breve e completo, con i nomi espliciti al posto di «lo», «ci», «quello».
- Rispetta l'ordine dell'utente. Non aggiungere azioni che non ha chiesto e non saltarne nessuna.
- Il testo di un messaggio o di un documento da scrivere resta intero e identico in un solo passo, anche se contiene «e», virgole o verbi.
- needs_previous=true solo se il passo ha senso unicamente se il precedente è riuscito (es. scrivere nell'app appena aperta, aprire il file appena creato).
- Se c'è una sola azione, o è una domanda o una chiacchierata, rispondi con un solo passo che contiene la richiesta così com'è.
- Al massimo 8 passi.

Esempio: «apri discord e scrivi a marco che arrivo tra 10 minuti e poi crea una cartella compiti»
{"steps": [{"do": "apri Discord", "needs_previous": false}, {"do": "manda su Discord a Marco il messaggio «arrivo tra 10 minuti»", "needs_previous": false}, {"do": "crea la cartella «compiti»", "needs_previous": false}]}

Esempio: «scrivi a luca: compra il pane e passa da me»
{"steps": [{"do": "manda a Luca il messaggio «compra il pane e passa da me»", "needs_previous": false}]}

Esempio: «apri il blocco note e scrivici la lista: latte, uova»
{"steps": [{"do": "apri il Blocco note", "needs_previous": false}, {"do": "scrivi nel Blocco note «la lista: latte, uova»", "needs_previous": true}]}"""

PLAN_SYSTEM_EN = """You are the planner of Ressy, an assistant that acts on the user's Windows PC.
You receive a request and split it into the actions to do, in the order they must be done.
Answer only with JSON: {"steps": [{"do": "...", "needs_previous": false}]}

Rules:
- One step = one action (open an app, send a message, create a folder, search, answer a question...), written as a short complete order, with explicit names instead of "it", "there", "that".
- Keep the user's order. Do not add actions they did not ask for and do not skip any.
- The text of a message or document to write stays whole and identical in a single step, even if it contains "and", commas or verbs.
- needs_previous=true only if the step only makes sense when the previous one worked (e.g. type into the app just opened, open the file just created).
- If there is a single action, or it is a question or small talk, answer with one step holding the request as it is.
- At most 8 steps.

Example: "open discord and tell marco I'll be there in 10 minutes then create a folder called homework"
{"steps": [{"do": "open Discord", "needs_previous": false}, {"do": "send Marco on Discord the message \\"I'll be there in 10 minutes\\"", "needs_previous": false}, {"do": "create the folder \\"homework\\"", "needs_previous": false}]}

Example: "text luca: buy bread and come over"
{"steps": [{"do": "send Luca the message \\"buy bread and come over\\"", "needs_previous": false}]}"""


def plan_messages(text: str, language: str = "it") -> list[dict[str, Any]]:
    system = PLAN_SYSTEM_EN if language == "en" else PLAN_SYSTEM_IT
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


def parse_plan(raw: str) -> list[Step] | None:
    raw = (raw or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except ValueError:
        return None
    items = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    steps: list[Step] = []
    for item in items:
        if isinstance(item, str):
            text, needs = item, False
        elif isinstance(item, dict):
            text = str(item.get("do") or item.get("step") or item.get("text") or "")
            needs = item.get("needs_previous") is True
        else:
            continue
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            steps.append(Step(text[:600], needs and bool(steps)))
    if not steps:
        return None
    return steps[:MAX_PLAN_STEPS]


_DISCORD_OPEN = re.compile(r"\b(?:apri\w*|avvia\w*|vai\s+su|passa\s+a|open|launch|start)\s+(?:il\s+)?discord\b", re.I)
_VIDEO_EDITOR_OPEN = re.compile(
    r"\b(?:apri\w*|avvia\w*|usa\w*|open|launch|use)\s+(capcut|davinci(?:\s+resolve)?)\b", re.I
)
_VIDEO_EDIT_STEP = re.compile(r"^(?:edita\w*|monta\w*|edit)\b.*\bvideo\b", re.I)
_EDITOR_OPEN = re.compile(
    r"\b(?:apri\w*|avvia\w*|vai\s+su|passa\s+a|open|launch|start)\s+(?:il\s+|la\s+)?(blocco\s+note|notepad|wordpad|word|whatsapp|telegram)\b",
    re.I,
)
_MESSAGE_STEP = re.compile(
    r"^(?:scriv\w*|mand\w*|invi\w*|digli|dille|dici|rispond\w*|leggi\w*|write|send|text|message|tell|reply)\b",
    re.I,
)
_WRITE_STEP = re.compile(r"^(?:scriv\w*|digit\w*|incoll\w*|write|type|paste)\b", re.I)
_OTHER_TARGET = re.compile(
    r"\b(?:discord|whatsapp|telegram|capcut|davinci|blocco\s*note|notepad|word|wordpad|email|mail|file|cartella|"
    r"(?:nella|alla|sulla|una)\s+(?:lista|nota|spesa))\b",
    re.I,
)


def fallback_plan(text: str) -> list[Step]:
    pieces = split_actions(text)[:MAX_PLAN_STEPS]
    if not pieces:
        return [Step(text)]
    steps: list[Step] = []
    active_app = ""
    for piece in pieces:
        rewritten = piece
        needs = False
        if active_app == "Discord" and _MESSAGE_STEP.match(piece) and not _OTHER_TARGET.search(piece):
            rewritten = f"su Discord, {piece}"
        elif active_app in ("CapCut", "DaVinci Resolve") and _VIDEO_EDIT_STEP.match(piece) and not _OTHER_TARGET.search(piece):
            rewritten = f"con {active_app}, {piece}"
        elif active_app and active_app not in ("Discord", "CapCut", "DaVinci Resolve") and _WRITE_STEP.match(piece) and not _OTHER_TARGET.search(piece):
            rewritten = f"in {active_app}, {piece}"
            needs = True
        steps.append(Step(rewritten, needs and bool(steps)))
        if _DISCORD_OPEN.search(piece):
            active_app = "Discord"
        else:
            ve = _VIDEO_EDITOR_OPEN.search(piece)
            if ve:
                active_app = "CapCut" if "cap" in ve.group(1).lower() else "DaVinci Resolve"
            else:
                ed = _EDITOR_OPEN.search(piece)
                if ed:
                    active_app = ed.group(1)
    return steps
