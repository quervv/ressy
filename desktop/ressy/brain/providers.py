from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any, Callable

import httpx

from ..config import CLAUDE_MODELS, PROVIDER_NAMES, Settings
from .groq import (
    ChatResult,
    GroqAuthError,
    GroqClient,
    GroqError,
    GroqRateLimited,
    GroqUnavailable,
    strip_citations,
)
from ..i18n import tr

log = logging.getLogger("ressy.providers")

WEB_SYSTEM_IT = (
    "Rispondi in italiano in modo conciso (al massimo 4 frasi), con i fatti principali e le date "
    "quando contano. Niente link, niente markdown."
)
WEB_SYSTEM_EN = "Answer concisely (at most 4 sentences) with the key facts and dates. No links, no markdown."


class GeminiClient(GroqClient):

    NAME = "Gemini"
    PROVIDER = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
    NATIVE = "https://generativelanguage.googleapis.com/v1beta"

    def params_for(self, model: str) -> dict[str, Any]:
        return {"reasoning_effort": "low"} if "flash" in model or "2.5" in model or "3" in model else {}

    def _key(self, key: str | None = None) -> str:
        key = (key if key is not None else self._api_key() or "").strip()
        if not key:
            raise GroqAuthError(tr("Manca la chiave API di Gemini."), status=401, provider=self.NAME)
        return key

    async def _native(self, model: str, body: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        try:
            response = await self._http().post(
                f"{self.NATIVE}/models/{model}:generateContent",
                json=body,
                headers={"x-goog-api-key": self._key()},
                timeout=httpx.Timeout(timeout, connect=10.0),
            )
        except httpx.TimeoutException as exc:
            raise GroqUnavailable(tr("Gemini non risponde (timeout)."), provider=self.NAME) from exc
        except httpx.HTTPError as exc:
            raise GroqUnavailable(tr("Non riesco a contattare Gemini."), provider=self.NAME) from exc
        if self.usage is not None:
            try:
                if response.status_code == 429:
                    self.usage.record_limited(self.PROVIDER, model, None)
                elif response.status_code < 400:
                    meta = response.json().get("usageMetadata") or {}
                    self.usage.record(self.PROVIDER, model, None, meta.get("totalTokenCount"))
            except Exception:
                log.debug("usage bookkeeping failed", exc_info=True)
        self._raise_for(response)
        return response.json()

    @staticmethod
    def _text(data: dict[str, Any]) -> str:
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return "".join(str(p.get("text") or "") for p in parts).strip()

    async def web_answer(self, question: str, *, language: str = "it", model: str = "gemini-flash-latest") -> str:
        data = await self._native(
            model,
            {
                "systemInstruction": {"parts": [{"text": WEB_SYSTEM_IT if language == "it" else WEB_SYSTEM_EN}]},
                "contents": [{"role": "user", "parts": [{"text": question}]}],
                "tools": [{"google_search": {}}],
            },
        )
        return strip_citations(self._text(data))

    async def transcribe(self, data: bytes, *, filename: str, mime: str, model: str, language: str | None = None,
                         prompt: str | None = None) -> dict[str, Any]:
        lang = "italiano" if (language or "it") == "it" else "English"
        hint = tr(" Nomi che potrebbero comparire: {prompt}").format(prompt=prompt) if prompt else ""
        result = await self._native(
            model,
            {
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}},
                        {"text": f"Trascrivi esattamente le parole dette in questo audio ({lang}). "
                                 f"Rispondi solo con il testo, senza commenti. Se non c'è voce rispondi con una "
                                 f"stringa vuota.{hint}"},
                    ],
                }],
                "generationConfig": {"temperature": 0},
            },
            timeout=45.0,
        )
        return {"text": self._text(result)}

    async def list_models(self, key: str | None = None) -> list[str]:
        response = await self._request("GET", "/models", headers=self._auth(key))
        data = response.json().get("data") or []
        ids = [str(item.get("id") or "").removeprefix("models/") for item in data]
        return sorted(i for i in ids if i.startswith("gemini") and "embedding" not in i and "tts" not in i
                      and "image" not in i and "audio" not in i and "live" not in i)


_OPENROUTER_PREFERRED = ("gemma-4-31b", "nemotron-3.5-super", "nemotron-3-ultra", "gpt-oss-120b", "gemma-4-26b",
                         "llama-3.3-70b", "qwen3", "deepseek", "nemotron-3.5-lightning")
_OPENROUTER_TTL = 6 * 3600


def pick_free_models(models: list[dict[str, Any]]) -> list[str]:
    free = []
    for m in models:
        pricing = m.get("pricing") or {}
        mid = str(m.get("id") or "")
        if not mid or mid.startswith("openrouter/"):
            continue
        if not (mid.endswith(":free") or (str(pricing.get("prompt")) == "0" and str(pricing.get("completion")) == "0")):
            continue
        params = m.get("supported_parameters")
        if params is not None and "tools" not in params:
            continue
        free.append(mid)

    def rank(mid: str) -> tuple[int, str]:
        for index, tag in enumerate(_OPENROUTER_PREFERRED):
            if tag in mid:
                return index, mid
        return len(_OPENROUTER_PREFERRED), mid

    return sorted(free, key=rank)


class OpenRouterClient(GroqClient):

    NAME = "OpenRouter"
    PROVIDER = "openrouter"
    BASE = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: Callable[[], str]) -> None:
        super().__init__(api_key)
        self._free: list[str] = []
        self._free_at = 0.0

    def params_for(self, model: str) -> dict[str, Any]:
        return {}

    def _http(self) -> httpx.AsyncClient:
        client = super()._http()
        client.headers.update({"HTTP-Referer": "https://ressy.top", "X-Title": "Ressy"})
        return client

    async def free_models(self) -> list[str]:
        if self._free and time.time() - self._free_at < _OPENROUTER_TTL:
            return self._free
        try:
            response = await self._request("GET", "/models", params={"supported_parameters": "tools"})
            found = pick_free_models(response.json().get("data") or [])
        except GroqError:
            log.warning("could not list the free OpenRouter models", exc_info=True)
            found = []
        if found:
            self._free, self._free_at = found, time.time()
        return self._free

    async def chat(self, messages: list[dict[str, Any]], *, models: list[str] | tuple[str, ...],
                   **kwargs: Any) -> ChatResult:
        if not models or list(models) == ["auto"]:
            models = (await self.free_models())[:4]
        if not models:
            raise GroqUnavailable(tr("OpenRouter non ha modelli gratuiti disponibili adesso."), provider=self.NAME)
        return await super().chat(messages, models=models, **kwargs)

    async def web_answer(self, question: str, *, language: str = "it") -> str:
        result = await self.chat(
            [{"role": "system", "content": WEB_SYSTEM_IT if language == "it" else WEB_SYSTEM_EN},
             {"role": "user", "content": question}],
            models=["auto"], max_tokens=800,
        )
        return strip_citations(str(result.message.get("content") or ""))

    async def key_info(self, key: str | None = None) -> dict[str, Any]:
        response = await self._request("GET", "/key", headers=self._auth(key))
        return response.json().get("data") or {}

    async def list_models(self, key: str | None = None) -> list[str]:
        info = await self.key_info(key)
        if self.usage is not None:
            self.usage.set_account(self.PROVIDER, info)
        return await self.free_models()


def _to_anthropic(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []
    pending_results: list[dict[str, Any]] = []

    def flush_results() -> None:
        if pending_results:
            out.append({"role": "user", "content": list(pending_results)})
            pending_results.clear()

    for message in messages:
        role = message.get("role")
        if role == "system":
            system_parts.append(str(message.get("content") or ""))
            continue
        if role == "tool":
            content = str(message.get("content") or "")
            block: dict[str, Any] = {"type": "tool_result", "tool_use_id": message.get("tool_call_id"), "content": content}
            try:
                if json.loads(content).get("ok") is False:
                    block["is_error"] = True
            except (ValueError, AttributeError):
                pass
            pending_results.append(block)
            continue
        flush_results()
        if role == "assistant":
            raw = message.get("_claude")
            if raw:
                out.append({"role": "assistant", "content": raw})
                continue
            blocks: list[dict[str, Any]] = []
            if message.get("content"):
                blocks.append({"type": "text", "text": str(message["content"])})
            for call in message.get("tool_calls") or []:
                fn = call.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                blocks.append({"type": "tool_use", "id": call.get("id"), "name": fn.get("name"), "input": args})
            if blocks:
                out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": "user", "content": str(message.get("content") or "")})
    flush_results()
    return "\n\n".join(p for p in system_parts if p), out


def _tools_to_anthropic(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out = []
    for tool in tools or []:
        fn = tool.get("function") or {}
        out.append({
            "name": fn.get("name"),
            "description": fn.get("description") or "",
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return out


def _from_anthropic(blocks: list[Any]) -> dict[str, Any]:
    texts: list[str] = []
    calls: list[dict[str, Any]] = []
    for block in blocks:
        kind = getattr(block, "type", None)
        if kind == "text":
            texts.append(block.text)
        elif kind == "tool_use":
            calls.append({
                "id": block.id,
                "type": "function",
                "function": {"name": block.name, "arguments": json.dumps(block.input, ensure_ascii=False)},
            })
    message: dict[str, Any] = {"role": "assistant", "content": "".join(texts).strip()}
    if calls:
        message["tool_calls"] = calls
    message["_claude"] = [block.to_dict() for block in blocks]
    return message


_FALLBACK_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5")
_WEB_SEARCH_NEW = ("claude-opus-5-5", "claude-sonnet-5-5")


class ClaudeClient:
    NAME = "Claude"
    PROVIDER = "claude"
    usage: Any = None

    def __init__(self, api_key: Callable[[], str]) -> None:
        self._api_key = api_key
        self._client = None
        self._client_key = ""

    def _anthropic(self, key: str | None = None):
        import anthropic

        key = (key if key is not None else self._api_key() or "").strip()
        if not key:
            raise GroqAuthError(tr("Manca la chiave API di Claude."), status=401, provider=self.NAME)
        if key != self._client_key or self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=key, timeout=60.0, max_retries=2)
            self._client_key = key
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
        self._client = None

    @staticmethod
    def _translate(exc: Exception) -> GroqError:
        import anthropic

        name = "Claude"
        if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
            return GroqAuthError(tr("La chiave API di Claude non è valida."), status=401, provider=name)
        if isinstance(exc, anthropic.RateLimitError):
            return GroqRateLimited(
                tr("Ho raggiunto il limite di richieste del tuo account Claude: riprova tra un minuto."),
                status=429, provider=name,
            )
        if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
            return GroqUnavailable(tr("Non riesco a contattare Claude: controlla la connessione."), provider=name)
        if isinstance(exc, anthropic.APIStatusError):
            return GroqError(tr("Errore Claude {status_code}: {message}").format(status_code=exc.status_code, message=exc.message), status=exc.status_code, provider=name)
        return GroqError(tr("Errore Claude: {name}").format(name=type(exc).__name__), provider=name)

    async def _create(self, model: str, **kwargs: Any):
        import anthropic

        client = self._anthropic()
        try:
            if model in _FALLBACK_MODELS:
                raw = await client.beta.messages.with_raw_response.create(
                    model=model, betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                )
            else:
                raw = await client.messages.with_raw_response.create(model=model, **kwargs)
            response = await raw.parse()
        except anthropic.APIError as exc:
            if self.usage is not None and isinstance(exc, anthropic.RateLimitError):
                try:
                    retry = exc.response.headers.get("retry-after")
                    self.usage.record_limited(self.PROVIDER, model, float(retry) if retry else None,
                                              exc.response.headers)
                except Exception:
                    log.debug("usage bookkeeping failed", exc_info=True)
            raise self._translate(exc) from exc
        if self.usage is not None:
            try:
                used = response.usage
                tokens = (used.input_tokens or 0) + (used.output_tokens or 0) if used is not None else None
                self.usage.record(self.PROVIDER, model, raw.headers, tokens)
            except Exception:
                log.debug("usage bookkeeping failed", exc_info=True)
        return response

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        models: list[str] | tuple[str, ...],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        max_tokens: int = 1500,
        temperature: float = 0.4,
        extra: dict[str, Any] | None = None,
    ) -> ChatResult:
        model = models[0]
        system, history = _to_anthropic(messages)
        kwargs: dict[str, Any] = {
            "max_tokens": max(4096, max_tokens * 2),
            "system": system,
            "messages": history,
            "output_config": {"effort": "low"},
        }
        if tools:
            kwargs["tools"] = _tools_to_anthropic(tools)
            kwargs["tool_choice"] = {"type": "none" if tool_choice == "none" else "auto"}
        response = await self._create(model, **kwargs)
        if response.stop_reason == "refusal":
            return ChatResult(
                message={"role": "assistant", "content": tr("Mi dispiace, con questo non posso aiutarti.")},
                model=model, finish_reason="refusal",
            )
        return ChatResult(message=_from_anthropic(response.content), model=model, finish_reason=response.stop_reason)

    async def web_answer(self, question: str, *, language: str = "it", model: str = "claude-opus-5-5") -> str:
        tool_type = "web_search_20260209" if model in _WEB_SEARCH_NEW else "web_search_20250305"
        messages: list[Any] = [{"role": "user", "content": question}]
        response = None
        for _ in range(3):
            response = await self._create(
                model,
                max_tokens=8000,
                system=WEB_SYSTEM_IT if language == "it" else WEB_SYSTEM_EN,
                messages=messages,
                tools=[{"type": tool_type, "name": "web_search", "max_uses": 3}],
                output_config={"effort": "low"},
            )
            if response.stop_reason != "pause_turn":
                break
            messages = [*messages, {"role": "assistant", "content": response.content}]
        if response is None or response.stop_reason == "refusal":
            return ""
        return strip_citations("".join(b.text for b in response.content if getattr(b, "type", "") == "text"))

    async def list_models(self, key: str | None = None) -> list[str]:
        import anthropic

        client = self._anthropic(key)
        try:
            page = await client.models.list(limit=100)
        except anthropic.APIError as exc:
            raise self._translate(exc) from exc
        available = {m.id for m in page.data}
        return [m for m in CLAUDE_MODELS if m in available] or list(CLAUDE_MODELS)


_CLIENTS = {"groq": GroqClient, "claude": ClaudeClient, "gemini": GeminiClient, "openrouter": OpenRouterClient}
_KEYLESS = ("local",)


class LLMRouter:

    def __init__(self, settings: Settings, usage: Any = None) -> None:
        self.settings = settings
        if usage is None:
            from ..paths import app_dir
            from .usage import UsageTracker

            usage = UsageTracker(app_dir() / "usage.json")
        self.usage = usage
        self.groq = GroqClient(lambda: settings.groq_api_key)
        self.claude = ClaudeClient(lambda: settings.anthropic_api_key)
        self.gemini = GeminiClient(lambda: settings.gemini_api_key)
        self.openrouter = OpenRouterClient(lambda: settings.openrouter_api_key)
        from .local_llm import LocalLLMClient

        self.local = LocalLLMClient(lambda: settings.local_llm_model, lambda: settings.user_name)
        for client in self._all():
            client.usage = usage
        self.last_provider = ""

    def _all(self) -> tuple[Any, ...]:
        return (self.groq, self.claude, self.gemini, self.openrouter, self.local)

    def client(self, provider: str | None = None):
        return {"groq": self.groq, "claude": self.claude, "gemini": self.gemini, "openrouter": self.openrouter,
                "local": self.local}[provider or self.settings.llm_provider]

    @property
    def name(self) -> str:
        return PROVIDER_NAMES.get(self.settings.llm_provider, "Groq")

    def models(self, provider: str | None = None) -> list[str]:
        provider = provider or self.settings.llm_provider
        if provider == "claude":
            return [self.settings.claude_model]
        if provider == "gemini":
            ordered = [self.settings.gemini_model, "gemini-flash-latest", "gemini-flash-lite-latest"]
            return list(dict.fromkeys(m for m in ordered if m))
        if provider == "openrouter":
            return [self.settings.openrouter_model] if self.settings.openrouter_model else ["auto"]
        if provider == "local":
            return [self.settings.local_llm_model]
        return self.settings.llm_models()

    def chain(self) -> list[str]:
        chosen = self.settings.llm_provider
        if not self.settings.llm_fallback:
            return [chosen]
        others = [p for p in self.settings.providers_with_keys() if p != chosen]
        others.sort(key=lambda p: (p == "local", self.usage.blocked_for(p) > 0))
        return [chosen, *others]

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> ChatResult:
        requested = kwargs.pop("models", None)
        chain = self.chain()
        last: GroqError | None = None
        for index, provider in enumerate(chain):
            models = requested if (index == 0 and requested) else self.models(provider)
            try:
                result = await self.client(provider).chat(messages, models=models, **kwargs)
            except GroqAuthError as exc:
                if index == 0 and len(chain) == 1:
                    raise
                log.warning("%s refused the key, trying the next brain", provider)
                last = exc
                continue
            except (GroqRateLimited, GroqUnavailable) as exc:
                if isinstance(exc, GroqRateLimited):
                    self.usage.record_limited(provider, "", exc.retry_after)
                log.warning("%s unavailable (%s), trying the next brain", provider, type(exc).__name__)
                last = exc
                continue
            except GroqError as exc:
                log.warning("%s failed (%s), trying the next brain", provider, exc)
                last = exc
                continue
            if provider != self.last_provider:
                log.info("brain in use: %s (%s)", provider, result.model)
            self.last_provider = provider
            return result
        if isinstance(last, GroqRateLimited) or last is None:
            first = PROVIDER_NAMES.get(chain[0], chain[0])
            hint = "" if len(chain) > 1 else (
                tr(" Per non fermarti mai aggiungi una seconda chiave gratuita (Gemini o OpenRouter) nelle impostazioni.")
            )
            raise GroqRateLimited(
                tr("Ho raggiunto il limite di richieste del tuo account {first}: riprova tra un minuto.{hint}").format(first=first, hint=hint),
                status=429, provider=first,
            )
        raise last

    async def web_answer(self, question: str, *, language: str = "it") -> str:
        last: Exception | None = None
        for provider in self.chain():
            if provider == "local":
                continue
            try:
                if provider == "claude":
                    return await self.claude.web_answer(question, language=language, model=self.settings.claude_model)
                if provider == "gemini":
                    return await self.gemini.web_answer(question, language=language, model=self.settings.gemini_model)
                if provider == "openrouter":
                    return await self.openrouter.web_answer(question, language=language)
                return await self.groq.web_answer(question, language=language)
            except GroqAuthError:
                raise
            except GroqError as exc:
                last = exc
                log.warning("web answer with %s failed, trying the next brain", provider)
        raise last or GroqError(tr("Nessun servizio di ricerca disponibile."))

    async def list_models(self, key: str | None = None, provider: str | None = None) -> list[str]:
        return await self.client(provider).list_models(key)

    async def usage_report(self, refresh: bool = True) -> str:
        providers = self.settings.providers_with_keys()
        if refresh and "openrouter" in providers:
            try:
                self.usage.set_account("openrouter", await self.openrouter.key_info())
            except GroqError:
                log.debug("OpenRouter key info failed", exc_info=True)
        return self.usage.report(providers)

    async def aclose(self) -> None:
        for client in self._all():
            try:
                await client.aclose()
            except Exception:
                log.debug("close failed", exc_info=True)


def make_client(provider: str, key: str = ""):
    cls = _CLIENTS[provider]
    return cls(lambda: key)


def verify_key_blocking(provider: str, key: str) -> list[str]:
    import asyncio

    async def go() -> list[str]:
        client = make_client(provider, key)
        try:
            return await client.list_models(key)
        finally:
            await client.aclose()

    return asyncio.run(go())
