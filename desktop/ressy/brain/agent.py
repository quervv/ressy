from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import Settings
from ..tools.registry import Attachment, Channel, ToolContext, ToolRegistry
from . import quick
from .memory import Memory
from .prompts import system_prompt

log = logging.getLogger("ressy.brain")

MAX_STEPS = 6
_INVISIBLE = re.compile("[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in (
    (0x200B, 0x200F), (0x2028, 0x202E), (0x2060, 0x2064), (0xFEFF, 0xFEFF))) + "]")


def clean_answer(text: str) -> str:
    return re.sub(" {2,}", " ", _INVISIBLE.sub("", text or "")).strip()


@dataclass
class TurnResult:
    text: str
    images: list[Attachment] = field(default_factory=list)
    sleep: bool = False
    performed: list[str] = field(default_factory=list)
    deferred: list[Callable[[], object]] = field(default_factory=list)


class Brain:
    def __init__(self, settings: Settings, llm: Any, registry: ToolRegistry, services: Any) -> None:
        self.settings = settings
        self.llm = llm
        self.registry = registry
        self.services = services
        self.memory = Memory()

    async def respond(
        self, text: str, channel: Channel, *, on_tool: Callable[[str], None] | None = None
    ) -> TurnResult:
        ctx = ToolContext(channel=channel, services=self.services)
        if getattr(self.settings, "quick_commands", True):
            fast = await self._quick(text, ctx, on_tool)
            if fast is not None:
                return fast
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": system_prompt(
                    user_name=self.settings.user_name, device_name=self.settings.device_name, channel=channel
                ),
            },
            *self.memory.history(channel.key),
            {"role": "user", "content": text},
        ]
        tools = self.registry.schemas(channel)
        models = self.llm.models() if hasattr(self.llm, "models") else self.settings.llm_models()
        answer: str | None = None

        for step in range(MAX_STEPS):
            result = await self.llm.chat(messages, models=models, tools=tools, tool_choice="auto")
            message = result.message
            calls = message.get("tool_calls") or []
            if not calls:
                answer = clean_answer(str(message.get("content") or ""))
                break
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
            for call in assistant["tool_calls"]:
                name = call["function"]["name"]
                if on_tool is not None:
                    try:
                        on_tool(name)
                    except Exception:
                        log.debug("on_tool callback failed", exc_info=True)
                output = await self.registry.invoke(name, call["function"]["arguments"], ctx)
                messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": output})
            log.debug("step %d done with %d tool call(s) on %s", step + 1, len(calls), result.model)

        if answer is None:
            result = await self.llm.chat(messages, models=models, tools=tools, tool_choice="none")
            answer = clean_answer(str(result.message.get("content") or ""))
        if not answer or not re.search(r"\w", answer):
            answer = "Fatto." if ctx.performed else "Non ho una risposta per questo."

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

    async def _quick(
        self, text: str, ctx: ToolContext, on_tool: Callable[[str], None] | None
    ) -> TurnResult | None:
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
            if on_tool is not None:
                try:
                    on_tool(found.tool)
                except Exception:
                    log.debug("on_tool callback failed", exc_info=True)
            output = await self.registry.invoke(found.tool, found.args, ctx)
            try:
                outcome = json.loads(output)
            except ValueError:
                return None
            if not outcome.get("ok"):
                log.info("quick %s did not work, asking the AI instead", found.tool)
                ctx.performed.clear()
                return None
            answer = quick.spoken(found.tool, str(outcome.get("esito") or "Fatto."))
        log.info("quick command: %s", found.tool or found.special or "answer")
        self.memory.add(ctx.channel.key, text, answer)
        return self._result(answer, ctx)
