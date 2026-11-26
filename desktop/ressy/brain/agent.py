from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import Settings
from ..i18n import tr
from ..tools.registry import Attachment, Channel, ToolContext, ToolRegistry
from . import planner, quick
from .memory import Memory
from .prompts import system_prompt

log = logging.getLogger("ressy.brain")

MAX_STEPS = 16
MAX_CALLS_PER_STEP = 10
MAX_CONTEXT_TURNS = 3
MAX_MEMORY_CHARS = 500
_INVISIBLE = re.compile("[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in (
    (0x200B, 0x200F), (0x2028, 0x202E), (0x2060, 0x2064), (0xFEFF, 0xFEFF))) + "]")

_FOLLOWUP_CUE = re.compile(
    r"(?:^(?:e|ed|ma|per[oò]|invece|anzi|allora|quindi|poi|dopo|ancora|anche|pure|riprova|continua|aggiungi|"
    r"aspetta|no|s[iì]|ok|okay|va bene|and|but|instead|then|also|too|again|retry|continue|add|wait|yes|no)\b|"
    r"\b(?:quell[oaie]|quest[oaie]|stess[oaie]|precedente|prima|sopra|appena|scors[oa]|avevo chiesto|"
    r"that|those|these|this one|it|them|him|her|previous|earlier|before|above|same|again|instead)\b|"
    r"^(?:lo|la|li|le|gli|glielo|gliela|glieli|gliele|ne|ci)\s+|"
    r"\b(?:apri|chiudi|avvia|lancia|scrivi|manda|invia|rispondi|crea|cancella|elimina|metti|fai|cerca|trova|"
    r"leggi|copia|incolla|salva|sposta|rinomina|esegui|scarica|edita|monta|aggiungi|togli|dici|di'|fall|fagl|"
    r"digl|dill|dagl|open|close|run|send|write|edit|delete|move|copy|save)(?:lo|la|li|le|gli|glielo|gliela|glieli|gliele|ci|ne)\b)",
    re.IGNORECASE,
)
_QUESTION_ASKED = re.compile(
    r"(?:\?\s*$|forse intendevi|controlla il nome|carica o dimmi|a chi devo|quale |che file|"
    r"maybe you meant|check the .*name|upload or tell me|who should|which )",
    re.IGNORECASE,
)
_STANDALONE_START = re.compile(
    r"^\W*(?:ressy\W+)?(?:puoi\s+|potresti\s+|per\s+favore\s+|can\s+you\s+|could\s+you\s+|please\s+)?"
    r"(?:apri\w*|avvia\w*|lancia\w*|chiudi\w*|cerca\w*|trova\w*|crea\w*|scarica\w*|esegui\w*|edita\w*|monta\w*|"
    r"scriv\w*\s+(?:a|su|in|nel|nella)\s+|mand\w*\s+(?:a|su)\s+|invi\w*\s+(?:a|su)\s+|"
    r"che\s+(?:ore|giorno|tempo|meteo)\b|quant[oa]\s+(?:fa|e|è|resta|rimane)\b|quanti\s+(?:timer|promemoria)\b|"
    r"metti\s+(?:un\s+timer|in\s+pausa|il\s+volume)|alza|abbassa|muta|smuta|fai\s+(?:uno\s+)?screenshot|"
    r"ricordami|open|launch|start|close|search|find|create|download|run|edit|play|what\s+time|what(?:'s|\s+is)\s+the\s+(?:time|weather))\b",
    re.IGNORECASE,
)
_REFUSAL = re.compile(
    r"(?:\bnon\s+(?:posso|riesco|sono\s+in\s+grado|ho\s+(?:uno\s+strumento|accesso|modo|la\s+possibilit[aà]))\b|"
    r"\bnon\s+[eè]\s+possibile\b|\bmi\s+dispiace\b|\bpurtroppo\s+non\b|"
    r"\bquesto\s+con\s+l'ai\s+sul\s+pc\s+non\s+riesco\b|"
    r"\b(?:i\s+(?:can't|cannot)|i(?:'m|\s+am)\s+unable|i\s+don't\s+have\s+(?:a\s+tool|access)|not\s+possible)\b)",
    re.IGNORECASE,
)
_REAL_BLOCK = re.compile(
    r"(?:chiave\s+api|api\s+key|pc\s+[eè]\s+bloccato|pc\s+is\s+locked|microfono|microphone|"
    r"non\s+sembra\s+installato|not\s+seem\s+installed|permessi\s+insufficienti|insufficient\s+permissions|"
    r"cartelle\s+di\s+sistema|system\s+folders)",
    re.IGNORECASE,
)
_FAKE_DONE = re.compile(
    r"^\s*(?:fatto\b|ho\s+(?:aperto|avviato|scritto|mandato|inviato|messo|chiuso|cercato|impostato|creato|scaricato|eseguito)|"
    r"done\b|i(?:'ve|\s+have)?\s+(?:opened|started|written|sent|closed|created|downloaded|executed))\b",
    re.IGNORECASE,
)

LOOKING = frozenset({
    "list_windows", "read_screen", "list_folder", "read_file", "system_status",
    "api_usage", "find_files", "read_webpage", "read_discord_chat", "clipboard",
})
DATA_TOOLS = LOOKING | frozenset({"weather", "web_answer", "notes", "system_control", "run_python", "run_powershell"})
PREPARING = frozenset({"open_app", "focus_app", "open_url", "open_folder", "window_action"})
ONCE = frozenset({"send_discord_message", "compose_email"})
_OPENING = re.compile(
    r"^\W*(?:apri\w*|avvia\w*|lancia\w*|esegui\w*|vai\b|porta\w*|passa\b|torna\b|open|launch|start|run|go|switch|"
    r"bring|focus)", re.IGNORECASE)
_MORE_THAN_OPEN = re.compile(
    r"\b(?:scriv\w*|mand\w*|invi\w*|clicca\w*|leggi\w*|cerca\w*|crea\w*|copia\w*|incolla\w*|salva\w*|"
    r"esegui\w*|scarica\w*|edita\w*|monta\w*|aggiung\w*|metti|convert\w*|sinistra|destra|schermo intero|"
    r"primo piano|write|send|click|read|search|create|copy|paste|save|run|execute|download|edit|add|left|right|fullscreen)\b",
    re.IGNORECASE,
)
_SECONDARY_IN_STEP = re.compile(
    r"\b(?:e\s+(?:poi|dopo|subito|esegui\w*|lancia\w*|apri\w*|salva\w*|manda\w*|invia\w*|scriv\w*|verifica\w*)|"
    r"ed\s+(?:esegui\w*|apri\w*|edita\w*)|and\s+(?:then|run|execute|open|save|send|write|check))\b",
    re.IGNORECASE,
)

StepHook = Callable[[int, int, str], None]


def clean_answer(text: str) -> str:
    return re.sub(" {2,}", " ", _INVISIBLE.sub("", text or "")).strip()


@dataclass
class TurnResult:
    text: str
    images: list[Attachment] = field(default_factory=list)
    sleep: bool = False
    performed: list[str] = field(default_factory=list)
    deferred: list[Callable[[], object]] = field(default_factory=list)


@dataclass
class _Call:
    name: str
    ok: bool
    text: str
    ran: bool = True


@dataclass
class _StepOutcome:
    status: str
    answer: str = ""
    context: str = ""


@dataclass
class _Turn:
    ctx: ToolContext
    on_tool: Callable[[str], None] | None = None
    done_once: dict[tuple[str, str], str] = field(default_factory=dict)


def _parse(output: str) -> dict[str, Any]:
    try:
        data = json.loads(output)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _arguments_key(raw: Any) -> str:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return str(raw)
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _not_run(text: str) -> str:
    return json.dumps({"ok": False, "errore": text}, ensure_ascii=False)


def _is_followup(text: str, history: list[dict[str, Any]]) -> bool:
    if not history:
        return False
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if not cleaned:
        return False
    if _FOLLOWUP_CUE.search(cleaned):
        return True
    last_assistant = next((str(m.get("content") or "") for m in reversed(history) if m.get("role") == "assistant"), "")
    asked_question = bool(_QUESTION_ASKED.search(last_assistant))
    words = re.findall(r"[\w'’]+", cleaned)
    if _STANDALONE_START.match(cleaned):
        return False
    if asked_question:
        return True
    return len(words) <= 4


def _should_nudge(answer: str, turn: _Turn, user_text: str, nudged: bool) -> bool:
    if nudged or turn.ctx.performed:
        return False
    text = (answer or "").strip()
    if not text or text.endswith("?") or _REAL_BLOCK.search(text):
        return False
    if _REFUSAL.search(text):
        return True
    if _FAKE_DONE.match(text):
        from . import quick

        if quick.match(user_text) is None:
            return True
    return False


class Brain:
    def __init__(self, settings: Settings, llm: Any, registry: ToolRegistry, services: Any) -> None:
        self.settings = settings
        self.llm = llm
        self.registry = registry
        self.services = services
        self.memory = Memory()

    async def respond(
        self, text: str, channel: Channel, *, on_tool: Callable[[str], None] | None = None,
        on_step: StepHook | None = None,
    ) -> TurnResult:
        ctx = ToolContext(channel=channel, services=self.services)
        turn = _Turn(ctx=ctx, on_tool=on_tool)
        if planner.looks_compound(text):
            steps = await self._plan(text)
            if len(steps) > 1:
                log.info("request split into %d steps", len(steps))
                answer = await self._run_plan(steps, text, turn, on_step)
                self.memory.add(channel.key, text, answer)
                return self._result(answer, ctx)
        if getattr(self.settings, "quick_commands", True):
            fast = await self._quick_answer(text, turn)
            if fast is not None:
                self.memory.add(channel.key, text, fast)
                return self._result(fast, ctx)
        answer = await self._converse(self._messages(channel, text), turn, user_text=text)
        self.memory.add(channel.key, text, answer)
        return self._result(answer, ctx)

    def _result(self, answer: str, ctx: ToolContext) -> TurnResult:
        return TurnResult(
            text=answer,
            images=ctx.images,
            sleep=ctx.sleep_requested,
            performed=ctx.performed,
            deferred=ctx.deferred,
        )

    def _select_history(self, channel: Channel, probe_text: str) -> list[dict[str, Any]]:
        history = self.memory.history(channel.key)
        if not _is_followup(probe_text, history):
            return []
        recent = history[-(MAX_CONTEXT_TURNS * 2):]
        trimmed: list[dict[str, Any]] = []
        for msg in recent:
            content = str(msg.get("content") or "")
            if msg.get("role") == "assistant" and len(content) > MAX_MEMORY_CHARS:
                content = content[: MAX_MEMORY_CHARS - 1] + "…"
            trimmed.append({"role": msg.get("role", "user"), "content": content})
        return trimmed

    def _messages(self, channel: Channel, text: str, *, probe_text: str | None = None) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": system_prompt(
                    user_name=self.settings.user_name, device_name=self.settings.device_name, channel=channel,
                    language=getattr(self.settings, "language", "it"),
                ),
            },
            *self._select_history(channel, text if probe_text is None else probe_text),
            {"role": "user", "content": text},
        ]

    def _models(self) -> Any:
        return self.llm.models() if hasattr(self.llm, "models") else self.settings.llm_models()

    def _on_pc(self) -> bool:
        chain = getattr(self.llm, "chain", None)
        try:
            return bool(chain) and (chain() or [""])[0] == "local"
        except Exception:
            return False

    def _recovery_nudge(self, user_text: str) -> str:
        if getattr(self.settings, "language", "it") == "en":
            return (
                f"Do NOT refuse or pretend it is done. Solve the current request («{user_text}») right now using "
                "your tools: open_app, find_files, web_answer, read_webpage, download_file, run_python, "
                "run_powershell, read_screen + click_text, write_in_app or press_keys."
            )
        return (
            f"NON dire «non posso» e non fingere di averlo fatto. Risolvi subito la richiesta attuale («{user_text}») "
            "usando gli strumenti: open_app, find_files, web_answer, read_webpage, download_file, run_python, "
            "run_powershell, read_screen + click_text, write_in_app o press_keys."
        )

    async def _converse(self, messages: list[dict[str, Any]], turn: _Turn, *, user_text: str = "") -> str:
        tools = self.registry.schemas(turn.ctx.channel)
        models = self._models()
        answer: str | None = None
        nudged = False
        for step in range(MAX_STEPS):
            result = await self.llm.chat(messages, models=models, tools=tools, tool_choice="auto")
            message = result.message
            calls = message.get("tool_calls") or []
            if not calls:
                candidate = clean_answer(str(message.get("content") or ""))
                if step < MAX_STEPS - 1 and _should_nudge(candidate, turn, user_text, nudged):
                    nudged = True
                    messages.append({"role": "assistant", "content": candidate})
                    messages.append({"role": "user", "content": self._recovery_nudge(user_text)})
                    log.info("intercepted refusal/pretend-done, nudging model to solve with tools")
                    continue
                answer = candidate
                break
            await self._run_calls(message, calls, messages, turn, step)
            log.debug("step %d done with %d tool call(s) on %s", step + 1, len(calls), result.model)

        if answer is None:
            result = await self.llm.chat(messages, models=models, tools=tools, tool_choice="none")
            answer = clean_answer(str(result.message.get("content") or ""))
        if not answer or not re.search(r"\w", answer):
            answer = tr("Fatto.") if turn.ctx.performed else tr("Non ho una risposta per questo.")
        return answer

    async def _run_calls(self, message: dict[str, Any], calls: list[dict[str, Any]], messages: list[dict[str, Any]],
                         turn: _Turn, step: int) -> list[_Call]:
        assistant: dict[str, Any] = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": call.get("id") or f"call_{step}_{index}",
                    "type": "function",
                    "function": {
                        "name": (call.get("function") or {}).get("name", ""),
                        "arguments": (call.get("function") or {}).get("arguments") or "{}",
                    },
                    **({"extra_content": call["extra_content"]} if call.get("extra_content") else {}),
                }
                for index, call in enumerate(calls)
            ],
        }
        if message.get("content"):
            assistant["content"] = message["content"]
        if message.get("_claude"):
            assistant["_claude"] = message["_claude"]
        messages.append(assistant)

        out: list[_Call] = []
        failed = False
        for call in assistant["tool_calls"]:
            name = call["function"]["name"]
            arguments = call["function"]["arguments"]
            key = (name, _arguments_key(arguments))
            if failed:
                output = _not_run(tr("Non eseguito: l'azione prima non è riuscita. Se serve ancora, richiedila."))
                ran = False
            elif name in ONCE and key in turn.done_once:
                output = json.dumps({"ok": True, "esito": tr("Già fatto poco fa: ") + turn.done_once[key]},
                                    ensure_ascii=False)
                ran = False
            else:
                if turn.on_tool is not None:
                    try:
                        turn.on_tool(name)
                    except Exception:
                        log.debug("on_tool callback failed", exc_info=True)
                output = await self.registry.invoke(name, arguments, turn.ctx)
                ran = True
            messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": output})
            data = _parse(output)
            ok = bool(data.get("ok"))
            said = str(data.get("esito") if ok else data.get("errore") or "")
            if ran and ok and name in ONCE:
                turn.done_once[key] = said
            out.append(_Call(name, ok, said, ran))
            if ran and not ok:
                failed = True
        return out

    async def _plan(self, text: str) -> list[planner.Step]:
        if self._on_pc():
            return planner.fallback_plan(text)
        language = getattr(self.settings, "language", "it")
        try:
            result = await self.llm.chat(planner.plan_messages(text, language), models=self._models(),
                                         max_tokens=600)
            steps = planner.parse_plan(str(result.message.get("content") or ""))
        except Exception:
            log.warning("planning failed, cutting the request by its words", exc_info=True)
            steps = None
        if not steps:
            return planner.fallback_plan(text)
        return steps

    async def _run_plan(self, steps: list[planner.Step], request_text: str, turn: _Turn, on_step: StepHook | None) -> str:
        outcomes: list[tuple[planner.Step, _StepOutcome]] = []
        previous_ok = True
        for index, step in enumerate(steps, 1):
            if step.needs_previous and not previous_ok:
                log.info("step %d/%d skipped: the one before did not work", index, len(steps))
                outcomes.append((step, _StepOutcome("skipped")))
                continue
            if on_step is not None:
                try:
                    on_step(index, len(steps), step.text)
                except Exception:
                    log.debug("on_step callback failed", exc_info=True)
            outcome = await self._do_step(step, index, len(steps), outcomes, request_text, turn)
            log.info("step %d/%d %s", index, len(steps), outcome.status)
            outcomes.append((step, outcome))
            previous_ok = outcome.status == "done"
            if outcome.status == "asked":
                break
        return self._plan_answer(steps, outcomes)

    async def _do_step(self, step: planner.Step, index: int, total: int,
                       outcomes: list[tuple[planner.Step, _StepOutcome]], request_text: str, turn: _Turn) -> _StepOutcome:
        if getattr(self.settings, "quick_commands", True):
            fast = await self._quick_answer(step.text, turn)
            if fast is not None:
                return _StepOutcome("done", fast)
        note = self._step_note(step, index, total, outcomes, compact=self._on_pc())
        messages = self._messages(turn.ctx.channel, note, probe_text=request_text)
        return await self._step_loop(messages, step, turn)

    def _step_note(self, step: planner.Step, index: int, total: int,
                   outcomes: list[tuple[planner.Step, _StepOutcome]], *, compact: bool = False) -> str:
        done = []
        for number, (previous, outcome) in enumerate(outcomes, 1):
            if outcome.status == "done":
                info = outcome.context or outcome.answer or tr("fatto")
                if len(info) > 400:
                    info = info[:397] + "…"
                done.append(f"{number}) {previous.text} → {info}")
            elif outcome.status == "failed":
                done.append(f"{number}) {previous.text} → " + tr("non riuscito: ") + (outcome.answer or "?"))
        if compact:
            lines = []
            if done:
                lines.append(tr("Già fatto:") + " " + "; ".join(done))
            lines.append(tr("Ora fai solo l'azione {index}: {step}").format(index=index, step=step.text))
            return "\n".join(lines)
        lines = [tr("La richiesta ha {total} azioni: le fai una alla volta, in ordine.").format(total=total)]
        if done:
            lines.append(tr("Già fatto:") + " " + "; ".join(done))
        lines.append(tr("Ora fai solo l'azione {index}: {step}").format(index=index, step=step.text))
        lines.append(tr("Non rifare le azioni già fatte e non anticipare le prossime. "
                        "Alla fine rispondi con una frase breve su cosa hai fatto."))
        return "\n".join(lines)

    async def _step_loop(self, messages: list[dict[str, Any]], step: planner.Step, turn: _Turn) -> _StepOutcome:
        tools = self.registry.schemas(turn.ctx.channel)
        models = self._models()
        last: _Call | None = None
        gathered: list[str] = []
        nudged = False
        for round_ in range(MAX_CALLS_PER_STEP):
            result = await self.llm.chat(messages, models=models, tools=tools, tool_choice="auto")
            message = result.message
            calls = message.get("tool_calls") or []
            if not calls:
                answer = clean_answer(str(message.get("content") or ""))
                if round_ < MAX_CALLS_PER_STEP - 1 and _should_nudge(answer, turn, step.text, nudged):
                    nudged = True
                    messages.append({"role": "assistant", "content": answer})
                    messages.append({"role": "user", "content": self._recovery_nudge(step.text)})
                    log.info("step intercepted refusal/pretend-done, nudging model to solve with tools")
                    continue
                ctx_text = "\n".join(gathered)[:900]
                if last is None:
                    return _StepOutcome("asked" if answer.endswith("?") else "done", answer, ctx_text)
                return _StepOutcome("done" if last.ok else "failed", answer or last.text, ctx_text)
            ran = [c for c in await self._run_calls(message, calls, messages, turn, round_) if c.ran]
            for c in ran:
                if c.ok and c.name in DATA_TOOLS and c.text:
                    gathered.append(c.text)
            if ran:
                last = ran[-1]
            if ran and all(c.ok for c in ran) and self._step_finished(step.text, ran):
                ctx_text = "\n".join(gathered)[:900]
                return _StepOutcome("done", " ".join(quick.spoken(c.name, c.text) for c in ran), ctx_text)
        result = await self.llm.chat(messages, models=models, tools=tools, tool_choice="none")
        answer = clean_answer(str(result.message.get("content") or ""))
        ok = last is not None and last.ok
        return _StepOutcome("done" if ok else "failed", answer or (last.text if last else ""), "\n".join(gathered)[:900])

    @staticmethod
    def _step_finished(step_text: str, ran: list[_Call]) -> bool:
        names = {c.name for c in ran}
        if names <= LOOKING:
            return False
        if names <= PREPARING | LOOKING and (not _OPENING.match(step_text) or _MORE_THAN_OPEN.search(step_text)):
            return False
        if _SECONDARY_IN_STEP.search(step_text) and not (names & {"send_discord_message", "edit_video", "run_python", "run_powershell"}):
            return False
        return True

    @staticmethod
    def _plan_answer(steps: list[planner.Step], outcomes: list[tuple[planner.Step, _StepOutcome]]) -> str:
        parts: list[str] = []
        skipped: list[str] = []
        question = ""
        for step, outcome in outcomes:
            if outcome.status == "skipped":
                skipped.append(step.text)
            elif outcome.status == "asked":
                question = outcome.answer
            elif outcome.status == "done":
                parts.append(outcome.answer or tr("Fatto."))
            else:
                parts.append(outcome.answer or tr("«{step}» non è riuscito.").format(step=step.text))
        if skipped:
            parts.append(tr("Non ho fatto {steps}, perché serviva il passo prima.").format(
                steps=", ".join(f"«{s}»" for s in skipped)))
        waiting = [s.text for s in steps[len(outcomes):]]
        if waiting:
            parts.append(tr("Poi devo ancora: {steps}.").format(steps=", ".join(f"«{s}»" for s in waiting)))
        if question:
            parts.append(question)
        return " ".join(p.strip() for p in parts if p and p.strip())

    async def _quick_answer(self, text: str, turn: _Turn) -> str | None:
        found = quick.match(text)
        if found is None:
            return None
        if found.answer:
            answer = found.answer
        elif found.special == "usage":
            report = getattr(self.llm, "usage_report", None)
            if report is None:
                return None
            answer = await report()
        else:
            if turn.on_tool is not None:
                try:
                    turn.on_tool(found.tool)
                except Exception:
                    log.debug("on_tool callback failed", exc_info=True)
            mark = len(turn.ctx.performed)
            output = await self.registry.invoke(found.tool, found.args, turn.ctx)
            outcome = _parse(output)
            if not outcome.get("ok"):
                log.info("quick %s did not work, asking the AI instead", found.tool)
                del turn.ctx.performed[mark:]
                return None
            answer = quick.spoken(found.tool, str(outcome.get("esito") or tr("Fatto.")))
        log.info("quick command: %s", found.tool or found.special or "answer")
        return answer
