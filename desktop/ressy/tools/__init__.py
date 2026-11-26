from __future__ import annotations

from .registry import Attachment, Channel, Tool, ToolContext, ToolError, ToolRegistry, params
from ..i18n import tr


def _go_to_sleep(ctx: ToolContext, args: dict) -> str:
    ctx.sleep_requested = True
    return tr("Dopo la risposta torno a dormire.")


async def _api_usage(ctx: ToolContext, args: dict) -> str:
    llm = getattr(ctx.services, "llm", None)
    if llm is None or not hasattr(llm, "usage_report"):
        raise ToolError(tr("Non ho dati sui consumi."))
    return await llm.usage_report()


def build_registry() -> ToolRegistry:
    from . import apps, discord, more, reminders, system, video, web

    registry = ToolRegistry()
    registry.extend(apps.TOOLS + discord.TOOLS + web.TOOLS + system.TOOLS + reminders.TOOLS + more.TOOLS + video.TOOLS)
    registry.add(
        Tool(
            "go_to_sleep",
            "Torna a dormire e chiude la finestra di Ressy (quando l'utente ti congeda o ha finito).",
            params(),
            _go_to_sleep,
            remote=False,
        )
    )
    registry.add(
        Tool(
            "api_usage",
            "Quanto resta dei limiti delle chiavi API (richieste e token rimasti per Groq, Gemini, OpenRouter, "
            "Claude) e quanto Ressy ha usato oggi.",
            params(),
            _api_usage,
        )
    )
    return registry


__all__ = ["Attachment", "Channel", "Tool", "ToolContext", "ToolError", "ToolRegistry", "build_registry", "params"]
