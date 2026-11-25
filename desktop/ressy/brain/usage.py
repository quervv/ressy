from __future__ import annotations

import datetime as dt
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Mapping

log = logging.getLogger("ressy.usage")

NAMES = {"groq": "Groq", "claude": "Claude", "gemini": "Gemini", "openrouter": "OpenRouter", "local": "AI sul PC"}
CONSOLES = {
    "groq": "console.groq.com/settings/limits",
    "claude": "console.anthropic.com/settings/limits",
    "gemini": "aistudio.google.com/usage",
    "openrouter": "openrouter.ai/settings/keys",
}

_DURATION = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")


def parse_duration(value: str | None) -> float | None:
    if not value:
        return None
    total, found = 0.0, False
    for number, unit in _DURATION.findall(value):
        found = True
        total += float(number) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    if found:
        return total
    try:
        return float(value)
    except ValueError:
        return None


def _seconds_until(value: str | None) -> float | None:
    if not value:
        return None
    try:
        when = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (when - dt.datetime.now(dt.timezone.utc)).total_seconds())


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def limits_from_headers(provider: str, headers: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    h = {k.lower(): v for k, v in headers.items()}
    out: dict[str, dict[str, Any]] = {}
    if "x-ratelimit-remaining-requests" in h or "x-ratelimit-remaining-tokens" in h:
        for kind, window in (("requests", "day"), ("tokens", "minute")):
            remaining = _int(h.get(f"x-ratelimit-remaining-{kind}"))
            limit = _int(h.get(f"x-ratelimit-limit-{kind}"))
            if remaining is not None or limit is not None:
                out[kind] = {
                    "remaining": remaining, "limit": limit, "window": window,
                    "reset_s": parse_duration(h.get(f"x-ratelimit-reset-{kind}")),
                }
    for kind in ("requests", "tokens", "input-tokens", "output-tokens"):
        remaining = _int(h.get(f"anthropic-ratelimit-{kind}-remaining"))
        limit = _int(h.get(f"anthropic-ratelimit-{kind}-limit"))
        if remaining is not None or limit is not None:
            out[kind.replace("-", "_")] = {
                "remaining": remaining, "limit": limit, "window": "minute",
                "reset_s": _seconds_until(h.get(f"anthropic-ratelimit-{kind}-reset")),
            }
    return out


def _fmt(n: int | float | None) -> str:
    if n is None:
        return "?"
    return f"{int(n):,}".replace(",", ".")


def _when(seconds: float | None) -> str:
    if seconds is None:
        return ""
    if seconds < 90:
        return f"tra {max(1, round(seconds))} secondi"
    if seconds < 5400:
        return f"tra {round(seconds / 60)} minuti"
    return f"tra {round(seconds / 3600)} ore"


class UsageTracker:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._limits: dict[str, dict[str, Any]] = {}
        self._blocked: dict[str, dict[str, Any]] = {}
        self._accounts: dict[str, dict[str, Any]] = {}
        self._days: dict[str, dict[str, dict[str, int]]] = {}
        self._load()

    def _load(self) -> None:
        if self._path is None:
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            self._days = {k: v for k, v in (data.get("days") or {}).items() if isinstance(v, dict)}
            self._limits = data.get("limits") or {}
            self._accounts = data.get("accounts") or {}

    def _save(self) -> None:
        if self._path is None:
            return
        keep = sorted(self._days)[-14:]
        data = {"days": {k: self._days[k] for k in keep}, "limits": self._limits, "accounts": self._accounts}
        try:
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(self._path)
        except OSError:
            log.debug("could not save usage", exc_info=True)

    @staticmethod
    def _today() -> str:
        return dt.date.today().isoformat()

    def record(self, provider: str, model: str, headers: Mapping[str, str] | None = None, tokens: int | None = None,
               *, count: bool = True) -> None:
        limits = limits_from_headers(provider, headers or {})
        with self._lock:
            if count:
                day = self._days.setdefault(self._today(), {}).setdefault(provider, {"requests": 0, "tokens": 0})
                day["requests"] += 1
                day["tokens"] += int(tokens or 0)
            if limits:
                self._limits[f"{provider}|{model}"] = {**limits, "at": time.time()}
            self._blocked.pop(provider, None)
            self._save()

    def record_limited(self, provider: str, model: str, retry_after: float | None,
                       headers: Mapping[str, str] | None = None) -> None:
        limits = limits_from_headers(provider, headers or {})
        with self._lock:
            self._blocked[provider] = {"model": model, "until": time.time() + (retry_after or 60), "at": time.time()}
            if limits:
                self._limits[f"{provider}|{model}"] = {**limits, "at": time.time()}
            self._save()

    def set_account(self, provider: str, info: dict[str, Any]) -> None:
        with self._lock:
            self._accounts[provider] = {**info, "at": time.time()}
            self._save()

    def blocked_for(self, provider: str) -> float:
        blocked = self._blocked.get(provider)
        if not blocked:
            return 0.0
        return max(0.0, blocked["until"] - time.time())

    def today(self, provider: str) -> dict[str, int]:
        return dict(self._days.get(self._today(), {}).get(provider) or {"requests": 0, "tokens": 0})

    def latest(self, provider: str, model: str | None = None) -> dict[str, Any] | None:
        best = None
        for key, value in self._limits.items():
            p, m = key.split("|", 1)
            if p != provider or (model and m != model):
                continue
            if best is None or value.get("at", 0) > best[1].get("at", 0):
                best = (m, value)
        if best is None:
            return None
        return {"model": best[0], **best[1]}

    def lines(self, provider: str, model: str | None = None) -> list[str]:
        name = NAMES.get(provider, provider)
        out: list[str] = []
        if provider == "local":
            used = self.today(provider)
            return ["Nessun limite, gratis e offline."] + (
                [f"Oggi ha risposto {_fmt(used['requests'])} volte."] if used["requests"] else [])
        latest = self.latest(provider, model) or (self.latest(provider) if model else None)
        if latest:
            age = time.time() - latest.get("at", 0)
            req, tok = latest.get("requests"), latest.get("tokens")
            if provider == "groq":
                if req:
                    out.append(f"Richieste oggi: ne restano {_fmt(req['remaining'])} su {_fmt(req['limit'])}"
                               f" (modello {latest['model']}).")
                if tok:
                    fresh = age < 60
                    out.append(
                        f"Token al minuto: {_fmt(tok['remaining'] if fresh else tok['limit'])} su {_fmt(tok['limit'])}"
                        + ("" if fresh else " (si è già ricaricato)") + "."
                    )
            else:
                if req:
                    out.append(f"Richieste al minuto: ne restano {_fmt(req['remaining'])} su {_fmt(req['limit'])}.")
                for key, label in (("input_tokens", "Token in entrata"), ("output_tokens", "Token in uscita"),
                                   ("tokens", "Token")):
                    if latest.get(key):
                        out.append(f"{label} al minuto: {_fmt(latest[key]['remaining'])} su {_fmt(latest[key]['limit'])}.")
                        break
        account = self._accounts.get(provider)
        if account:
            free = account.get("free_model_daily_requests") or {}
            if free.get("limit"):
                out.append(f"Richieste gratuite oggi: ne restano {_fmt(free.get('remaining'))} su {_fmt(free['limit'])}.")
            if account.get("limit") is not None and account.get("limit_remaining") is not None:
                out.append(f"Credito della chiave: {account['limit_remaining']:.2f} $ su {account['limit']:.2f} $.")
            elif account.get("is_free_tier"):
                out.append("Account gratuito: 20 richieste al minuto sui modelli gratis.")
        wait = self.blocked_for(provider)
        if wait > 0:
            out.append(f"Adesso è al limite: torna disponibile {_when(wait)}.")
        used = self.today(provider)
        if used["requests"]:
            noun = "richiesta" if used["requests"] == 1 else "richieste"
            out.append(f"Oggi Ressy ha fatto {_fmt(used['requests'])} {noun} a {name}"
                       + (f" ({_fmt(used['tokens'])} token)." if used["tokens"] else "."))
        if not latest and not account and provider in ("gemini",):
            out.append(f"{name} non comunica quanto resta: i limiti esatti sono su {CONSOLES[provider]}.")
        if not out:
            out.append(f"Nessun dato ancora: lo saprò dopo la prima richiesta a {name}.")
        return out

    def report(self, providers: list[str]) -> str:
        parts = []
        for provider in providers:
            parts.append(f"{NAMES.get(provider, provider)}: " + " ".join(self.lines(provider)))
        return "\n".join(parts) if parts else "Non hai ancora inserito chiavi API."
