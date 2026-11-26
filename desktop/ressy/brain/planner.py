from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from ..speech.textnorm import strip_accents

log = logging.getLogger("ressy.brain")

MAX_PLAN_STEPS = 8


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
})
_FILLERS = frozenset({
    "e", "ed", "poi", "dopo", "quindi", "infine", "anche", "inoltre", "pure", "per", "favore", "piacere", "ressy",
    "ora", "adesso", "subito", "anzi", "allora", "ok", "okay", "ah", "eh", "si", "dopodiche", "successivamente",
    "prima", "di", "tutto", "mi", "ti", "ci", "infatti", "and", "then", "also", "after", "that", "now", "please",
    "finally", "next", "lastly", "first", "afterwards", "so", "okay",
})
_MODALS = frozenset({"puoi", "potresti", "riesci", "riusciresti", "vorrei", "voglio", "devi", "dovresti", "can",
                     "could", "would", "will", "a", "che", "tu", "you"})
_INFINITIVE_STEMS = (
    "aprir", "chiuder", "avviar", "lanciar", "eseguir", "scriver", "mandar", "inviar", "risponder", "crear",
    "cancellar", "eliminar", "metter", "suonar", "riprodurr", "far", "cercar", "trovar", "legger", "controllar",
    "impostar", "alzar", "abbassar", "toglier", "spegner", "riavviar", "sospender", "bloccar", "fermar", "riprender",
    "saltar", "copiar", "incollar", "premer", "cliccar", "portar", "andar", "tornar", "ricordar", "salvar",
    "spostar", "rinominar", "cambiar", "accender", "attivar", "disattivar", "scaricar", "mostrar", "guardar",
    "aggiunger", "dir", "dar", "calcolar", "tradurr",
)
_INFINITIVE_ENDINGS = ("e", "mi", "ti", "gli", "le", "lo", "la", "li", "ci", "ne", "glielo", "gliela")

_CUT = re.compile(
    r"([.;!?]+\s+|,\s*|\s+(?:e|ed|poi|dopo|dopodich[eé]|quindi|infine|and|then)\s+)",
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


def starts_action(segment: str) -> bool:
    polite = False
    for word in _words(segment)[:6]:
        if word in _MODALS:
            polite = True
            continue
        if word in _FILLERS:
            continue
        return _is_imperative(word) or (polite and _is_infinitive(word))
    return False


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
_STRONG = re.compile(r"^\s*(?:[.;!?,]+\s*)?(?:(?:e|ed|and)\s+)?(?:poi|dopo|dopodich[eé]|infine|then|after\s+that)\b",
                     re.IGNORECASE)


def split_actions(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = _CUT.split(text)
    pieces: list[list[str]] = [["", parts[0]]]
    in_message = _open_message(parts[0])
    for index in range(1, len(parts), 2):
        cut, piece = parts[index], parts[index + 1] if index + 1 < len(parts) else ""
        new_action = starts_action(piece) and (not in_message or bool(_STRONG.match(cut + piece)))
        if new_action and piece.strip():
            pieces.append([cut, piece])
        else:
            pieces[-1][1] += cut + piece
        in_message = _open_message(pieces[-1][1])
    if len(pieces) > 1 and not starts_action(pieces[0][1]):
        pieces[0:2] = [["", pieces[0][1] + pieces[1][0] + pieces[1][1]]]
    out = [re.sub(r"^[\s,;.]+|[\s,;]+$", "", piece) for _, piece in pieces]
    out = out[:1] + [_LEADING.sub("", piece) for piece in out[1:]]
    return [piece for piece in out if piece]


_LEADING = re.compile(r"^(?:(?:e|ed|poi|dopo|dopodich[eé]|quindi|infine|anche|inoltre|and|then|also|finally)\b[\s,]*)+",
                      re.IGNORECASE)


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


def fallback_plan(text: str) -> list[Step]:
    pieces = split_actions(text)[:MAX_PLAN_STEPS]
    return [Step(piece) for piece in pieces] or [Step(text)]
