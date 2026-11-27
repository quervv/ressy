from __future__ import annotations

import hashlib
import logging
import math
import os
import struct
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import httpx

if TYPE_CHECKING:
    import numpy as np

from .. import __version__
from ..config import LOCAL_STT_MODELS
from ..i18n import tr
from ..paths import app_dir

log = logging.getLogger("ressy.stt.local")

MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{name}.bin"
RATE = 16000

Progress = Callable[[int, int], None]


def models_dir() -> Path:
    path = app_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_path(name: str) -> Path:
    return models_dir() / f"ggml-{name}.bin"


def is_downloaded(name: str) -> bool:
    path = model_path(name)
    return path.is_file() and path.stat().st_size > LOCAL_STT_MODELS.get(name, ("", 20))[1] * 0.7e6


def size_mb(name: str) -> int:
    return LOCAL_STT_MODELS.get(name, ("", 0))[1]


class DownloadCancelled(Exception):
    pass


def download_model(name: str, progress: Progress | None = None, cancel: threading.Event | None = None) -> Path:
    if name not in LOCAL_STT_MODELS:
        raise ValueError(f"modello sconosciuto: {name}")
    if is_downloaded(name):
        return model_path(name)
    return download_file(MODEL_URL.format(name=name), model_path(name), size_mb(name), progress, cancel)


def download_file(url: str, target: Path, expected_mb: int, progress: Progress | None = None,
                  cancel: threading.Event | None = None) -> Path:
    part = target.with_suffix(".part")
    headers = {"User-Agent": f"Ressy/{__version__} (+https://ressy.top)"}
    try:
        with httpx.stream("GET", url, headers=headers, follow_redirects=True,
                          timeout=httpx.Timeout(30.0, connect=15.0)) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or expected_mb * 1_000_000)
            done = 0
            digest = hashlib.sha256()
            with part.open("wb") as fh:
                for chunk in response.iter_bytes(1 << 16):
                    if cancel is not None and cancel.is_set():
                        raise DownloadCancelled()
                    fh.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total)
        if done < total * 0.98:
            raise OSError("download incompleto")
        os.replace(part, target)
        log.info("downloaded %s (%.0f MB, sha256 %s)", target.name, done / 1e6, digest.hexdigest()[:12])
        return target
    finally:
        part.unlink(missing_ok=True)


def installed_models() -> list[str]:
    return [name for name in LOCAL_STT_MODELS if is_downloaded(name)]


def delete_other_models(keep: str) -> None:
    for name in LOCAL_STT_MODELS:
        if name != keep:
            model_path(name).unlink(missing_ok=True)


IDLE_UNLOAD_S = 180.0


class LocalWhisper:

    def __init__(self) -> None:
        self._model: Any = None
        self._name = ""
        self._lock = threading.Lock()
        self._idle_timer: threading.Timer | None = None

    def _schedule_unload_locked(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.cancel()
        timer = threading.Timer(IDLE_UNLOAD_S, self.release)
        timer.daemon = True
        timer.start()
        self._idle_timer = timer

    def release(self) -> None:
        import gc

        with self._lock:
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None
            if self._model is not None:
                self._model = None
                self._name = ""
                gc.collect()
                log.info("speech model unloaded to free RAM")

    def _load(self, name: str) -> Any:
        if self._model is not None and self._name == name:
            return self._model
        if not is_downloaded(name):
            raise FileNotFoundError(name)
        from pywhispercpp.model import Model

        self._model = None
        self._model = Model(
            str(model_path(name)),
            n_threads=max(2, min(6, (os.cpu_count() or 4) - 1)),
            params_sampling_strategy=1,
            print_progress=False,
            print_realtime=False,
            print_timestamps=False,
            redirect_whispercpp_logs_to=False,
        )
        self._name = name
        log.info("speech model %s loaded", name)
        return self._model

    def preload(self, name: str) -> None:
        with self._lock:
            self._load(name)
            self._schedule_unload_locked()

    def transcribe(self, audio: np.ndarray, *, name: str, language: str, prompt: str) -> dict[str, Any]:
        import numpy as np

        with self._lock:
            model = self._load(name)
            segments = model.transcribe(
                audio.astype(np.float32),
                language=language or "it",
                initial_prompt=prompt or "",
                extract_probability=True,
                no_context=True,
                single_segment=False,
                suppress_blank=True,
                no_speech_thold=0.55,
                beam_search={"beam_size": 2, "patience": -1.0},
            )
            self._schedule_unload_locked()
        out = []
        for seg in segments:
            text = str(seg.text or "").strip()
            if not text:
                continue
            if (text.startswith("[") and text.endswith("]")) or (text.startswith("(") and text.endswith(")")) or (
                text.startswith("*") and text.endswith("*") and len(text) > 2
            ):
                continue
            p = getattr(seg, "probability", float("nan"))
            logprob = math.log(max(p, 1e-6)) if p == p else -0.3
            t0 = round(max(0.0, float(getattr(seg, "t0", 0) or 0) / 100.0), 3)
            t1 = round(max(t0, float(getattr(seg, "t1", 0) or 0) / 100.0), 3)
            out.append({
                "text": text,
                "start": t0,
                "end": t1,
                "avg_logprob": logprob,
                "no_speech_prob": 0.0,
                "compression_ratio": 1.0,
            })
        return {"text": " ".join(s["text"] for s in out), "segments": out}


def _ogg_packets(data: bytes) -> list[bytes]:
    packets: list[bytes] = []
    current = bytearray()
    pos = 0
    while pos + 27 <= len(data):
        if data[pos:pos + 4] != b"OggS":
            raise ValueError(tr("non è un file Ogg"))
        segments = data[pos + 26]
        table = data[pos + 27:pos + 27 + segments]
        pos += 27 + segments
        for lacing in table:
            current += data[pos:pos + lacing]
            pos += lacing
            if lacing < 255:
                packets.append(bytes(current))
                current.clear()
    return packets


def decode_opus_ogg(data: bytes, rate: int = RATE) -> np.ndarray:
    import discord.opus as opus
    import numpy as np

    if not opus.is_loaded() and not opus._load_default():
        raise RuntimeError(tr("libopus non disponibile"))
    packets = _ogg_packets(data)
    if not packets or not packets[0].startswith(b"OpusHead"):
        raise ValueError(tr("non è una nota vocale Opus"))
    pre_skip = struct.unpack_from("<H", packets[0], 10)[0] if len(packets[0]) >= 12 else 0
    decoder = opus.Decoder()
    pcm = bytearray()
    for packet in packets[1:]:
        if packet.startswith(b"OpusTags") or not packet:
            continue
        pcm += decoder.decode(packet, fec=False)
    stereo = np.frombuffer(bytes(pcm), dtype=np.int16).reshape(-1, 2)[pre_skip:]
    mono = stereo.astype(np.float32).mean(axis=1)
    if rate == 16000:
        usable = mono[: len(mono) // 3 * 3]
        mono = usable.reshape(-1, 3).mean(axis=1)
    elif rate != 48000:
        positions = np.linspace(0, len(mono) - 1, int(len(mono) * rate / 48000))
        mono = np.interp(positions, np.arange(len(mono)), mono)
    return np.clip(mono, -32768, 32767).astype(np.int16)


def decode_any(data: bytes, mime: str, rate: int = RATE) -> np.ndarray:
    import numpy as np

    if data[:4] == b"OggS" and b"OpusHead" in data[:200]:
        return decode_opus_ogg(data, rate)
    import miniaudio

    decoded = miniaudio.decode(data, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=rate)
    return np.frombuffer(decoded.samples, dtype=np.int16).copy()
