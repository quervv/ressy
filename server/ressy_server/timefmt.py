from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_zone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def format_last_seen(ts: float | None, now: float, tz: tzinfo) -> str:
    if not ts:
        return "mai"
    delta = max(0.0, now - ts)
    if delta < 60:
        return "pochi secondi fa"
    if delta < 3600:
        minutes = int(delta // 60)
        return "1 minuto fa" if minutes == 1 else f"{minutes} minuti fa"
    then = datetime.fromtimestamp(ts, tz)
    today = datetime.fromtimestamp(now, tz).date()
    if then.date() == today:
        return f"oggi alle {then:%H:%M}"
    if (today - then.date()).days == 1:
        return f"ieri alle {then:%H:%M}"
    return f"il {then:%d/%m/%Y} alle {then:%H:%M}"
