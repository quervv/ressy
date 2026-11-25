from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .. import __version__

log = logging.getLogger("ressy.groq")

API_BASE = "https://api.groq.com/openai/v1"
WEB_SEARCH_MODELS = ("openai/gpt-oss-20b", "openai/gpt-oss-120b")
STT_FALLBACK = "whisper-large-v3"

_CITATION = re.compile(r"\s*【[^】]*】")
_NON_CHAT = ("whisper", "tts", "orpheus", "playai", "guard", "prompt-guard", "compound", "distil")


class GroqError(RuntimeError):

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        retry_after: float | None = None,
        provider: str = "Groq",
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retry_after = retry_after
        self.provider = provider


class GroqAuthError(GroqError):
    pass


class GroqUnavailable(GroqError):
    pass


class GroqRateLimited(GroqError):
    pass


@dataclass
class ChatResult:
    message: dict[str, Any]
    model: str
    finish_reason: str | None = None


def model_params(model: str) -> dict[str, Any]:
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": "low", "include_reasoning": False}
    if model.startswith("qwen/qwen3"):
        return {"reasoning_effort": "none"}
    return {}


def strip_citations(text: str) -> str:
    return _CITATION.sub("", text or "").strip()


def is_chat_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(tag in lowered for tag in _NON_CHAT)


_NO_SIGNATURE = "skip_thought_signature_validator"


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


class GroqClient:

    NAME = "Groq"
    PROVIDER = "groq"
    BASE = API_BASE
    usage: Any = None

    def __init__(self, api_key: Callable[[], str]) -> None:
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    def params_for(self, model: str) -> dict[str, Any]:
        return model_params(model)

    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE,
                timeout=httpx.Timeout(45.0, connect=10.0),
                headers={"User-Agent": f"Ressy/{__version__} (+https://ressy.top)"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    def _auth(self, key: str | None = None) -> dict[str, str]:
        key = (key if key is not None else self._api_key() or "").strip()
        if not key:
            raise GroqAuthError(
                f"Manca la chiave API di {self.NAME}: inseriscila nelle impostazioni di Ressy.", status=401, provider=self.NAME
            )
        return {"Authorization": f"Bearer {key}"}

    def _raise_for(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        message, code = "", None
        try:
            body = response.json()
            if isinstance(body, list) and body:
                body = body[0]
            error = body.get("error") or {}
            message = str(error.get("message") or "")
            code = error.get("code") or error.get("type") or error.get("status")
            code = str(code) if code is not None else None
        except (ValueError, AttributeError):
            message = response.text[:300]
        status = response.status_code
        name = self.NAME
        if status == 401 or (status == 400 and "api key" in message.lower()):
            raise GroqAuthError(f"La chiave API di {name} non è valida.", status=status, code=code, provider=name)
        if status == 403:
            raise GroqAuthError(message or f"Accesso negato da {name}.", status=status, code=code, provider=name)
        raise GroqError(
            message or f"Errore {name} {status}", status=status, code=code, retry_after=_retry_after(response),
            provider=name,
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._http().request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise GroqUnavailable(f"{self.NAME} non risponde (timeout).", provider=self.NAME) from exc
        except httpx.HTTPError as exc:
            raise GroqUnavailable(
                f"Non riesco a contattare {self.NAME}: controlla la connessione.", provider=self.NAME
            ) from exc
        self._note_usage(path, response, kwargs)
        self._raise_for(response)
        return response

    def _note_usage(self, path: str, response: httpx.Response, kwargs: dict[str, Any]) -> None:
        if self.usage is None or path not in ("/chat/completions", "/audio/transcriptions"):
            return
        try:
            model = str((kwargs.get("json") or {}).get("model") or (kwargs.get("data") or {}).get("model") or "")
            if response.status_code == 429:
                self.usage.record_limited(self.PROVIDER, model, _retry_after(response), response.headers)
            elif response.status_code < 400:
                tokens = None
                if path == "/chat/completions":
                    tokens = (response.json().get("usage") or {}).get("total_tokens")
                self.usage.record(self.PROVIDER, model, response.headers, tokens)
        except Exception:
            log.debug("usage bookkeeping failed", exc_info=True)

    def _outgoing(self, message: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in message.items() if not k.startswith("_")}
        if out.get("tool_calls") and self.PROVIDER != "gemini":
            out["tool_calls"] = [{k: v for k, v in c.items() if k != "extra_content"} for c in out["tool_calls"]]
        elif out.get("tool_calls"):
            out["tool_calls"] = [c if c.get("extra_content") else
                                 {**c, "extra_content": {"google": {"thought_signature": _NO_SIGNATURE}}}
                                 for c in out["tool_calls"]]
        return out

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
        headers = self._auth()
        last_error: GroqError | None = None
        rate_limited = 0
        for model in models:
            for attempt in range(2):
                payload: dict[str, Any] = {
                    "model": model,
                    "messages": [self._outgoing(m) for m in messages],
                    "max_completion_tokens": max_tokens,
                    "temperature": temperature,
                    **self.params_for(model),
                    **(extra or {}),
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = tool_choice or "auto"
                try:
                    response = await self._request("POST", "/chat/completions", json=payload, headers=headers)
                except (GroqAuthError, GroqUnavailable):
                    raise
                except GroqError as exc:
                    last_error = exc
                    log.warning("model %s failed (%s %s): %s", model, exc.status, exc.code, exc)
                    if exc.status == 429:
                        if attempt == 0 and exc.retry_after is not None and exc.retry_after <= 6:
                            await asyncio.sleep(exc.retry_after + 0.2)
                            continue
                        rate_limited += 1
                        break
                    if exc.status == 400 and exc.code == "tool_use_failed" and attempt == 0:
                        continue
                    break
                data = response.json()
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                return ChatResult(message=message, model=model, finish_reason=choice.get("finish_reason"))
        if rate_limited and rate_limited == len(models):
            raise GroqRateLimited(
                f"Ho raggiunto il limite di richieste del tuo account {self.NAME}: riprova tra un minuto.",
                status=429,
                provider=self.NAME,
            )
        raise last_error or GroqError(f"Nessun modello {self.NAME} disponibile.", provider=self.NAME)

    async def web_answer(self, question: str, *, language: str = "it") -> str:
        system = (
            "Rispondi in italiano in modo conciso (al massimo 4 frasi), con i fatti principali e le date "
            "quando contano. Niente link, niente markdown."
            if language == "it"
            else "Answer concisely (at most 4 sentences) with the key facts and dates. No links, no markdown."
        )
        result = await self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": question}],
            models=WEB_SEARCH_MODELS,
            tools=[{"type": "browser_search"}],
            tool_choice="required",
            max_tokens=2500,
            temperature=0.3,
        )
        return strip_citations(str(result.message.get("content") or ""))

    async def transcribe(
        self,
        data: bytes,
        *,
        filename: str,
        mime: str,
        model: str,
        language: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        headers = self._auth()
        form: dict[str, str] = {"model": model, "response_format": "verbose_json", "temperature": "0"}
        if language:
            form["language"] = language
        if prompt:
            form["prompt"] = prompt
        models = [model] if model == STT_FALLBACK else [model, STT_FALLBACK]
        last_error: GroqError | None = None
        for candidate in models:
            form["model"] = candidate
            try:
                response = await self._request(
                    "POST",
                    "/audio/transcriptions",
                    data=form,
                    files={"file": (filename, data, mime)},
                    headers=headers,
                    timeout=httpx.Timeout(60.0, connect=10.0),
                )
                return response.json()
            except (GroqAuthError, GroqUnavailable):
                raise
            except GroqError as exc:
                last_error = exc
                log.warning("transcription with %s failed: %s", candidate, exc)
                if exc.status == 400 and exc.code not in ("model_not_found", "model_decommissioned"):
                    raise
        raise last_error or GroqError("Trascrizione non disponibile.")

    async def list_models(self, key: str | None = None) -> list[str]:
        response = await self._request("GET", "/models", headers=self._auth(key))
        data = response.json().get("data") or []
        return sorted(str(item.get("id")) for item in data if item.get("id") and item.get("active", True))
