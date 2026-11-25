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


SILENT_DB = -88.0


def probe_inputs(seconds: float = 0.5, skip: str = "") -> list[tuple[str, float]]:
    try:
        import numpy as np
        import sounddevice as sd
    except Exception:
        return []
    from .pcm import rms_dbfs

    hostapi = _default_hostapi()
    out: list[tuple[str, float]] = []
    for index, dev in enumerate(_query()):
        name = str(dev.get("name", "")).strip()
        if dev.get("max_input_channels", 0) <= 0 or not name or name == skip:
            continue
        if hostapi is not None and dev.get("hostapi") != hostapi:
            continue
        if "mapper" in name.lower() or name.lower().startswith(("driver primario", "primary sound")):
            continue
        rate = int(dev.get("default_samplerate") or 16000)
        try:
            rec = sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="int16", device=index)
            sd.wait()
            out.append((name, rms_dbfs(np.asarray(rec[:, 0]))))
        except Exception:
            log.debug("cannot probe %s", name, exc_info=True)
    return out


def live_input(skip: str = "") -> str:
    alive = [(db, name) for name, db in probe_inputs(skip=skip) if db > SILENT_DB]
    return max(alive)[1] if alive else ""


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
