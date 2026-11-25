from __future__ import annotations

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Union

log = logging.getLogger("ressy.tools")


@dataclass(frozen=True)
class Channel:
    kind: str
    user_id: str = ""
    display: str = ""

    @property
    def remote(self) -> bool:
        return self.kind != "voice"

    @property
    def key(self) -> str:
        return "voice" if self.kind == "voice" else f"{self.kind}:{self.user_id}"

    @property
    def label(self) -> str:
        return {"voice": "voce", "telegram": "Telegram", "discord": "Discord"}.get(self.kind, self.kind)


@dataclass
class Attachment:
    data: bytes
    name: str
    mime: str


@dataclass
class ToolContext:
    channel: Channel
    services: Any
    images: list[Attachment] = field(default_factory=list)
    sleep_requested: bool = False
    performed: list[str] = field(default_factory=list)
    deferred: list[Callable[[], object]] = field(default_factory=list)
    snapshot_taken: bool = False


class ToolError(Exception):
    pass


ToolFunc = Callable[[ToolContext, dict[str, Any]], Union[str, Awaitable[str]]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    func: ToolFunc
    voice: bool = True
    remote: bool = True
    timeout: float = 45.0
    snapshot_on_error: bool = False

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


def params(properties: dict[str, dict[str, Any]] | None = None, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties or {}, "required": required or []}


_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool}


def coerce_args(tool: Tool, raw: dict[str, Any]) -> dict[str, Any]:
    props: dict[str, dict] = tool.parameters.get("properties", {})
    out: dict[str, Any] = {}
    for name, spec in props.items():
        if name not in raw or raw[name] is None:
            continue
        value = raw[name]
        kind = spec.get("type")
        try:
            if kind == "integer" and not isinstance(value, bool):
                value = int(float(value))
            elif kind == "number" and not isinstance(value, bool):
                value = float(value)
            elif kind == "boolean" and isinstance(value, str):
                value = value.strip().lower() in ("true", "1", "si", "sì", "yes")
            elif kind == "string" and not isinstance(value, str):
                value = str(value)
        except (TypeError, ValueError) as exc:
            raise ToolError(f"argomento '{name}' non valido") from exc
        expected = _TYPES.get(kind)
        if expected is not None and not isinstance(value, expected):
            raise ToolError(f"argomento '{name}' non valido")
        if "enum" in spec and value not in spec["enum"]:
            raise ToolError(f"'{name}' deve essere uno tra: {', '.join(map(str, spec['enum']))}")
        out[name] = value
    missing = [name for name in tool.parameters.get("required", []) if name not in out or out[name] in ("", None)]
    if missing:
        raise ToolError(f"mancano gli argomenti: {', '.join(missing)}")
    return out


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool {tool.name}")
        self._tools[tool.name] = tool

    def extend(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.add(tool)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def available(self, channel: Channel) -> list[Tool]:
        return [t for t in self._tools.values() if (t.remote if channel.remote else t.voice)]

    def schemas(self, channel: Channel) -> list[dict[str, Any]]:
        return [t.schema() for t in self.available(channel)]

    async def invoke(self, name: str, raw_arguments: str | dict | None, ctx: ToolContext) -> str:
        tool = self._tools.get(name)
        if tool is None or tool not in self.available(ctx.channel):
            return _result(False, f"Lo strumento '{name}' non esiste o non è disponibile qui.")
        try:
            if isinstance(raw_arguments, dict):
                raw = raw_arguments
            else:
                raw = json.loads(raw_arguments or "{}") or {}
            if not isinstance(raw, dict):
                raise ToolError("argomenti non validi")
            args = coerce_args(tool, raw)
        except (ValueError, ToolError) as exc:
            return _result(False, f"Argomenti non validi: {exc}")

        log.info("tool %s %s", name, _redact(args))
        try:
            if inspect.iscoroutinefunction(tool.func):
                outcome = await asyncio.wait_for(tool.func(ctx, args), timeout=tool.timeout)
            else:
                outcome = await asyncio.wait_for(asyncio.to_thread(tool.func, ctx, args), timeout=tool.timeout)
        except ToolError as exc:
            log.info("tool %s refused: %s", name, exc)
            return _result(False, str(exc) + await self._snapshot(tool, ctx))
        except asyncio.TimeoutError:
            log.warning("tool %s timed out", name)
            return _result(
                False, "L'operazione ha impiegato troppo tempo ed è stata interrotta." + await self._snapshot(tool, ctx)
            )
        except Exception as exc:
            log.exception("tool %s crashed", name)
            return _result(False, f"Errore imprevisto: {type(exc).__name__}" + await self._snapshot(tool, ctx))
        text = str(outcome or "Fatto.")
        ctx.performed.append(f"{name}: {text}")
        return _result(True, text)


    @staticmethod
    async def _snapshot(tool: Tool, ctx: ToolContext) -> str:
        if not tool.snapshot_on_error or ctx.snapshot_taken:
            return ""
        ctx.snapshot_taken = True
        try:
            from . import screen

            def shoot() -> tuple[str, object]:
                image = screen.grab()
                path = screen.save_screenshot(image, prefix="bloccata")
                return str(path), image

            path, image = await asyncio.to_thread(shoot)
            if ctx.channel.remote:
                ctx.images.append(await asyncio.to_thread(screen.as_attachment, image, "dove-mi-sono-bloccata.jpg"))
                return " Ho allegato uno screenshot di dove mi sono bloccata."
            return f" Ho salvato uno screenshot di dove mi sono bloccata in Immagini\\Ressy ({Path(path).name})."
        except Exception:
            log.warning("could not take the error screenshot", exc_info=True)
            return ""


def _result(ok: bool, message: str) -> str:
    return json.dumps({"ok": ok, "esito" if ok else "errore": message}, ensure_ascii=False)


_PRIVATE_ARGS = frozenset({"message", "text", "content"})


def _redact(args: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in args.items():
        if key in _PRIVATE_ARGS and isinstance(value, str):
            value = f"<{len(value)} caratteri>"
        elif isinstance(value, str) and len(value) > 80:
            value = value[:77] + "..."
        out[key] = value
    return out
