from __future__ import annotations

import datetime as dt
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Mapping
from ..i18n import N_, language, tr

log = logging.getLogger("ressy.usage")

NAMES = {"groq": "Groq", "claude": "Claude", "gemini": "Gemini", "openrouter": "OpenRouter", "local": tr("AI sul PC")}
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
    text = f"{int(n):,}"
    return text if language() == "en" else text.replace(",", ".")


def _when(seconds: float | None) -> str:
    if seconds is None:
        return ""
    if seconds < 90:
        return tr("tra {max} secondi").format(max=max(1, round(seconds)))
    if seconds < 5400:
        return tr("tra {round} minuti").format(round=round(seconds / 60))
    return tr("tra {round} ore").format(round=round(seconds / 3600))


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
            return [tr("Nessun limite, gratis e offline.")] + (
                [tr("Oggi ha risposto {fmt} volte.").format(fmt=_fmt(used['requests']))] if used["requests"] else [])
        latest = self.latest(provider, model) or (self.latest(provider) if model else None)
        if latest:
            age = time.time() - latest.get("at", 0)
            req, tok = latest.get("requests"), latest.get("tokens")
            if provider == "groq":
                if req:
                    out.append(tr("Richieste oggi: ne restano {fmt} su {fmt2} (modello {value}).").format(fmt=_fmt(req['remaining']), fmt2=_fmt(req['limit']), value=latest['model']))
                if tok:
                    fresh = age < 60
                    out.append(
                        tr("Token al minuto: {fmt} su {fmt2}").format(fmt=_fmt(tok['remaining'] if fresh else tok['limit']), fmt2=_fmt(tok['limit']))
                        + ("" if fresh else tr(" (si è già ricaricato)")) + "."
                    )
            else:
                if req:
                    out.append(tr("Richieste al minuto: ne restano {fmt} su {fmt2}.").format(fmt=_fmt(req['remaining']), fmt2=_fmt(req['limit'])))
                for key, label in (("input_tokens", N_("Token in entrata")), ("output_tokens", N_("Token in uscita")),
                                   ("tokens", N_("Token"))):
                    if latest.get(key):
                        out.append(tr("{label} al minuto: {fmt} su {fmt2}.").format(label=tr(label), fmt=_fmt(latest[key]['remaining']), fmt2=_fmt(latest[key]['limit'])))
                        break
        account = self._accounts.get(provider)
        if account:
            free = account.get("free_model_daily_requests") or {}
            if free.get("limit"):
                out.append(tr("Richieste gratuite oggi: ne restano {fmt} su {fmt2}.").format(fmt=_fmt(free.get('remaining')), fmt2=_fmt(free['limit'])))
            if account.get("limit") is not None and account.get("limit_remaining") is not None:
                out.append(tr("Credito della chiave: {value:.2f} $ su {value2:.2f} $.").format(value=account['limit_remaining'], value2=account['limit']))
            elif account.get("is_free_tier"):
                out.append(tr("Account gratuito: 20 richieste al minuto sui modelli gratis."))
        wait = self.blocked_for(provider)
        if wait > 0:
            out.append(tr("Adesso è al limite: torna disponibile {when}.").format(when=_when(wait)))
        used = self.today(provider)
        if used["requests"]:
            made = (tr("Oggi Ressy ha fatto {fmt} richiesta a {name}") if used["requests"] == 1
                    else tr("Oggi Ressy ha fatto {fmt} richieste a {name}"))
            out.append(made.format(fmt=_fmt(used['requests']), name=name)
                       + (tr(" ({fmt} token).").format(fmt=_fmt(used['tokens'])) if used["tokens"] else "."))
        if not latest and not account and provider in ("gemini",):
            out.append(tr("{name} non comunica quanto resta: i limiti esatti sono su {value}.").format(name=name, value=CONSOLES[provider]))
        if not out:
            out.append(tr("Nessun dato ancora: lo saprò dopo la prima richiesta a {name}.").format(name=name))
        return out

    def report(self, providers: list[str]) -> str:
        parts = []
        for provider in providers:
            parts.append(f"{NAMES.get(provider, provider)}: " + " ".join(self.lines(provider)))
        return "\n".join(parts) if parts else tr("Non hai ancora inserito chiavi API.")
