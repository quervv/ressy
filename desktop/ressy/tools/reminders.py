from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import re
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Awaitable, Callable

from ..speech.textnorm import normalize, similarity
from .registry import Tool, ToolContext, ToolError, params
from ..i18n import tr

log = logging.getLogger("ressy.reminders")

MAX_AHEAD_S = 30 * 24 * 3600
LATE_GRACE_S = 3600


@dataclass
class Reminder:
    id: str
    due: float
    text: str
    platform: str = ""
    user_id: str = ""
    kind: str = "reminder"
    command: str = ""

    def when(self) -> str:
        due = dt.datetime.fromtimestamp(self.due)
        today = dt.date.today()
        if due.date() == today:
            return tr("oggi alle {due:%H:%M}").format(due=due)
        if due.date() == today + dt.timedelta(days=1):
            return tr("domani alle {due:%H:%M}").format(due=due)
        return tr("il {due:%d/%m} alle {due:%H:%M}").format(due=due)


Announce = Callable[[Reminder, bool], Awaitable[None]]


class ReminderService:
    def __init__(self, path: Path, announce: Announce) -> None:
        self.path = path
        self.announce = announce
        self._items: dict[str, Reminder] = {}
        self._handles: dict[str, asyncio.TimerHandle] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self.stopwatch_started: float | None = None

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                reminder = Reminder(**item)
                self._items[reminder.id] = reminder
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            log.warning("reminders file unreadable, starting empty", exc_info=True)

    def _save(self) -> None:
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps([asdict(r) for r in self._items.values()], ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            log.warning("could not save reminders", exc_info=True)

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._load()
        now = time.time()
        for reminder in list(self._items.values()):
            if reminder.due < now - LATE_GRACE_S:
                log.info("dropping reminder %s missed long ago", reminder.id)
                del self._items[reminder.id]
            else:
                self._schedule(reminder)
        self._save()
        self._sweeper = self._loop.create_task(self._sweep())

    async def _sweep(self) -> None:
        while True:
            await asyncio.sleep(15)
            now = time.time()
            for reminder in list(self._items.values()):
                if reminder.due <= now:
                    self._fire(reminder.id, reminder.due < now - 60)

    def stop(self) -> None:
        sweeper = getattr(self, "_sweeper", None)
        if sweeper is not None:
            sweeper.cancel()
        for handle in self._handles.values():
            handle.cancel()
        self._handles.clear()

    def _schedule(self, reminder: Reminder) -> None:
        assert self._loop is not None
        delay = max(0.0, reminder.due - time.time())
        late = reminder.due < time.time() - 5
        self._handles[reminder.id] = self._loop.call_later(delay, self._fire, reminder.id, late)

    def _fire(self, reminder_id: str, late: bool) -> None:
        handle = self._handles.pop(reminder_id, None)
        if handle is not None:
            handle.cancel()
        reminder = self._items.pop(reminder_id, None)
        if reminder is None:
            return
        self._save()
        task = asyncio.ensure_future(self.announce(reminder, late))
        task.add_done_callback(_log_failure)

    def add(
        self, text: str, due: float, platform: str = "", user_id: str = "",
        *, kind: str = "reminder", command: str = "",
    ) -> Reminder:
        reminder = Reminder(secrets.token_hex(2), due, text.strip(), platform, user_id, kind, command.strip())
        while reminder.id in self._items:
            reminder.id = secrets.token_hex(2)
        self._items[reminder.id] = reminder
        self._save()
        self._schedule(reminder)
        return reminder

    def cancel(self, reminder_id: str) -> Reminder | None:
        reminder = self._items.pop(reminder_id, None)
        handle = self._handles.pop(reminder_id, None)
        if handle is not None:
            handle.cancel()
        if reminder is not None:
            self._save()
        return reminder

    def list(self) -> list[Reminder]:
        return sorted(self._items.values(), key=lambda r: r.due)


def _log_failure(task: asyncio.Future) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error("reminder announcement failed", exc_info=task.exception())


_TIME = re.compile(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*$")


def parse_due(minutes: float | None, at: str | None, now: dt.datetime | None = None) -> float:
    now = now or dt.datetime.now()
    if minutes is not None:
        if minutes <= 0:
            raise ToolError(tr("Il promemoria deve essere nel futuro."))
        due = now + dt.timedelta(minutes=minutes)
    elif at:
        match = _TIME.match(at)
        if match is None:
            raise ToolError(tr("Orario non valido: usa il formato HH:MM."))
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        if hour > 23 or minute > 59:
            raise ToolError(tr("Orario non valido."))
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= now:
            due += dt.timedelta(days=1)
    else:
        raise ToolError(tr("Quando? Indica tra quanti minuti oppure l'orario (HH:MM)."))
    if (due - now).total_seconds() > MAX_AHEAD_S:
        raise ToolError(tr("Posso ricordare cose al massimo tra 30 giorni."))
    return due.timestamp()


async def reminder_tool(ctx: ToolContext, args: dict) -> str:
    service: ReminderService = ctx.services.reminders
    action = args["action"]
    if action == "add":
        text = (args.get("text") or "").strip()
        if not text:
            raise ToolError(tr("Cosa devo ricordarti?"))
        due = parse_due(args.get("minutes"), args.get("at"))
        channel = ctx.channel
        reminder = service.add(text, due, channel.kind if channel.remote else "", channel.user_id if channel.remote else "")
        return tr("Promemoria impostato {when}: {text}.").format(when=reminder.when(), text=reminder.text)
    if action == "list":
        items = service.list()
        if not items:
            return tr("Non ci sono promemoria.")
        return tr("Promemoria:\n") + "\n".join(f"[{r.id}] {r.when()}: {r.text}" for r in items)
    if action == "cancel":
        items = service.list()
        wanted_id = (args.get("id") or "").strip().lower()
        if wanted_id:
            removed = service.cancel(wanted_id)
            if removed is None:
                raise ToolError(tr("Nessun promemoria con codice {wanted_id}.").format(wanted_id=wanted_id))
            return tr("Ho cancellato il promemoria {when}: {text}.").format(when=removed.when(), text=removed.text)
        text = normalize(args.get("text") or "")
        if not items:
            raise ToolError(tr("Non ci sono promemoria da cancellare."))
        if not text and len(items) > 1:
            raise ToolError(tr("Quale promemoria? ") + "; ".join(f"[{r.id}] {r.text}" for r in items))
        target = items[0] if not text else max(items, key=lambda r: similarity(normalize(r.text), text))
        if text and similarity(normalize(target.text), text) < 0.5 and text not in normalize(target.text):
            raise ToolError(tr("Non trovo quel promemoria."))
        service.cancel(target.id)
        return tr("Ho cancellato il promemoria {when}: {text}.").format(when=target.when(), text=target.text)
    raise ToolError(tr("Azione non valida."))


def _format_span(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(tr("{n} ore").format(n=hours) if hours != 1 else tr("1 ora"))
    if minutes:
        parts.append(tr("{n} minuti").format(n=minutes) if minutes != 1 else tr("1 minuto"))
    if secs or not parts:
        parts.append(tr("{n} secondi").format(n=secs) if secs != 1 else tr("1 secondo"))
    return " e ".join(parts) if len(parts) <= 2 else ", ".join(parts[:-1]) + " e " + parts[-1]


async def timer_tool(ctx: ToolContext, args: dict) -> str:
    service: ReminderService = ctx.services.reminders
    action = args["action"]
    if action == "stopwatch_start":
        service.stopwatch_started = time.monotonic()
        return tr("Cronometro avviato.")
    if action == "stopwatch_status":
        if service.stopwatch_started is None:
            return tr("Il cronometro non è avviato.")
        elapsed = time.monotonic() - service.stopwatch_started
        return tr("Cronometro: {span}.").format(span=_format_span(elapsed))
    if action == "stopwatch_stop":
        if service.stopwatch_started is None:
            return tr("Il cronometro non è avviato.")
        elapsed = time.monotonic() - service.stopwatch_started
        service.stopwatch_started = None
        return tr("Cronometro fermato a {span}.").format(span=_format_span(elapsed))
    if action == "start":
        seconds = float(args.get("seconds") or 0) + float(args.get("minutes") or 0) * 60.0
        if seconds <= 0:
            raise ToolError(tr("Indica la durata del timer (secondi o minuti)."))
        if seconds > MAX_AHEAD_S:
            raise ToolError(tr("Posso impostare timer al massimo per 30 giorni."))
        command = (args.get("command") or "").strip()
        label = (args.get("label") or "").strip() or (command or tr("Timer"))
        due = time.time() + seconds
        channel = ctx.channel
        kind = "command" if command else "timer"
        service.add(
            label, due, channel.kind if channel.remote else "", channel.user_id if channel.remote else "",
            kind=kind, command=command,
        )
        if command:
            return tr("Eseguirò «{command}» tra {span}.").format(command=command, span=_format_span(seconds))
        return tr("Timer impostato per {span}: {label}.").format(span=_format_span(seconds), label=label)
    if action == "list":
        timers = [r for r in service.list() if r.kind in ("timer", "command")]
        if not timers:
            return tr("Non ci sono timer attivi.")
        now = time.time()
        return tr("Timer attivi:\n") + "\n".join(
            tr("[{id}] {text} (tra {span})").format(id=r.id, text=r.text, span=_format_span(max(0.0, r.due - now)))
            for r in timers
        )
    if action == "cancel":
        timers = [r for r in service.list() if r.kind in ("timer", "command")]
        wanted_id = (args.get("id") or "").strip().lower()
        if wanted_id:
            removed = service.cancel(wanted_id)
            if removed is None:
                raise ToolError(tr("Nessun timer con codice {wanted_id}.").format(wanted_id=wanted_id))
            return tr("Ho annullato il timer «{text}».").format(text=removed.text)
        if not timers:
            raise ToolError(tr("Non ci sono timer attivi da annullare."))
        label = normalize(args.get("label") or "")
        target = timers[0] if not label else max(timers, key=lambda r: similarity(normalize(r.text), label))
        service.cancel(target.id)
        return tr("Ho annullato il timer «{text}».").format(text=target.text)
    raise ToolError(tr("Azione timer non valida."))


TOOLS = [
    Tool(
        "reminder",
        "Promemoria: action=add (text + minutes, oppure at 'HH:MM'), list, cancel (id o text).",
        params(
            {
                "action": {"type": "string", "enum": ["add", "list", "cancel"]},
                "text": {"type": "string"},
                "minutes": {"type": "number", "description": "tra quanti minuti"},
                "at": {"type": "string", "description": "orario HH:MM (oggi, o domani se già passato)"},
                "id": {"type": "string"},
            },
            ["action"],
        ),
        reminder_tool,
    ),
    Tool(
        "timer",
        "Timer, cronometro e azioni programmate (start con seconds/minutes + label/command, list, cancel, stopwatch_*).",
        params(
            {
                "action": {
                    "type": "string",
                    "enum": ["start", "list", "cancel", "stopwatch_start", "stopwatch_stop", "stopwatch_status"],
                },
                "seconds": {"type": "number"},
                "minutes": {"type": "number"},
                "label": {"type": "string"},
                "command": {"type": "string", "description": "comando da eseguire allo scadere (es. metti in pausa)"},
                "id": {"type": "string"},
            },
            ["action"],
        ),
        timer_tool,
    ),
]
