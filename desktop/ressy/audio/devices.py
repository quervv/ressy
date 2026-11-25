from __future__ import annotations

import logging

log = logging.getLogger("ressy.audio")


def _query() -> list[dict]:
    try:
        import sounddevice as sd

        return [dict(d) for d in sd.query_devices()]
    except Exception:
        log.exception("cannot query audio devices")
        return []


def _default_hostapi() -> int | None:
    try:
        import sounddevice as sd

        return int(sd.default.hostapi)
    except Exception:
        return None


def input_devices() -> list[str]:
    hostapi = _default_hostapi()
    names: list[str] = []
    for dev in _query():
        if dev.get("max_input_channels", 0) > 0 and (hostapi is None or dev.get("hostapi") == hostapi):
            name = str(dev.get("name", "")).strip()
            if name and name not in names:
                names.append(name)
    return names


def output_devices() -> list[str]:
    hostapi = _default_hostapi()
    names: list[str] = []
    for dev in _query():
        if dev.get("max_output_channels", 0) > 0 and (hostapi is None or dev.get("hostapi") == hostapi):
            name = str(dev.get("name", "")).strip()
            if name and name not in names:
                names.append(name)
    return names


def resolve(name: str, kind: str) -> int | None:
    if not name:
        return None
    hostapi = _default_hostapi()
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    for index, dev in enumerate(_query()):
        if dev.get(key, 0) > 0 and str(dev.get("name", "")).strip() == name:
            if hostapi is None or dev.get("hostapi") == hostapi:
                return index
    log.warning("audio device %r not found, using the default", name)
    return None
