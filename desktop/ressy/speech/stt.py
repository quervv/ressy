from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from ..audio.pcm import prepare_for_stt, to_wav
from ..audio.vad import voiced_seconds
from ..brain.groq import GroqError
from ..config import Settings
from . import local_stt
from .textnorm import normalize

log = logging.getLogger("ressy.stt")

MIN_SECONDS = 0.3
MIN_VOICED_SECONDS = 0.15

_HALLUCINATION_MARKERS = (
    "amara org",
    "qtss",
    "sottotitoli creati",
    "sottotitoli a cura",
    "sottotitoli e revisione",
    "iscriviti al canale",
    "grazie per la visione",
    "grazie a tutti per la visione",
    "thanks for watching",
    "thank you for watching",
    "please subscribe",
    "subscribe",
    "subscribe to my channel",
)
_WEAK_PHRASES = frozenset({"grazie", "grazie mille", "ciao", "ok", "okay", "si", "no", "thank you", "thanks", "bye"})

_EXTENSIONS = {
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/webm": "webm",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
}


@dataclass(frozen=True)
class Transcript:
    text: str
    rejected: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.text) and self.rejected is None


def clean_transcription(payload: dict[str, Any], lenient: bool = False) -> Transcript:
    segments = payload.get("segments")
    confident = True
    if isinstance(segments, list) and segments:
        kept: list[str] = []
        for seg in segments:
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            no_speech = float(seg.get("no_speech_prob") or 0.0)
            logprob = float(seg.get("avg_logprob") or 0.0)
            compression = float(seg.get("compression_ratio") or 1.0)
            if not lenient:
                if no_speech > 0.6 and logprob < -0.7:
                    continue
                if compression > 2.6 or logprob < -1.25:
                    continue
            elif compression > 3.0:
                continue
            if no_speech > 0.3 or logprob < -0.6:
                confident = False
            kept.append(text)
        text = " ".join(kept)
    else:
        text = str(payload.get("text") or "")
    text = " ".join(text.split())
    norm = normalize(text)
    if not norm:
        return Transcript("", "empty")
    if any(marker in norm for marker in _HALLUCINATION_MARKERS):
        return Transcript("", "hallucination")
    if norm in _WEAK_PHRASES and not confident and not lenient:
        return Transcript("", "unsure")
    return Transcript(text)


def extension_for(mime: str) -> str:
    return _EXTENSIONS.get((mime or "").split(";")[0].strip().lower(), "ogg")


class SpeechToText:
    def __init__(self, settings: Settings, llm: Any, vocabulary: Callable[[], list[str]] | None = None) -> None:
        self.settings = settings
        self.llm = llm
        self.vocabulary = vocabulary
        self.local = local_stt.LocalWhisper()

    @property
    def engine(self) -> str:
        return self.settings.speech_engine

    async def _run(self, *, wav: bytes | None = None, pcm: np.ndarray | None = None, rate: int = 16000,
                   data: bytes | None = None, mime: str = "audio/wav", filename: str = "voce.wav") -> dict[str, Any]:
        engine = self.engine
        prompt = self._prompt()
        if engine == "local":
            name = self.settings.local_stt_model
            if not local_stt.is_downloaded(name):
                raise GroqError(
                    "Il modello vocale sul PC non è ancora scaricato: scaricalo in Impostazioni › Voce.",
                    code="model_missing", provider="PC",
                )
            if pcm is None:
                try:
                    pcm = await asyncio.to_thread(local_stt.decode_any, data or b"", mime, 16000)
                except Exception as exc:
                    raise GroqError(
                        "Non riesco a leggere questo audio sul PC: manda una nota vocale normale "
                        "o scegli di capire la voce online.", code="audio_format", provider="PC",
                    ) from exc
                rate = 16000
            audio = prepare_for_stt(pcm, rate)
            if rate != 16000:
                positions = np.linspace(0, len(audio) - 1, int(len(audio) * 16000 / rate))
                audio = np.interp(positions, np.arange(len(audio)), audio)
            floats = np.asarray(audio, dtype=np.float32) / 32768.0
            try:
                return await asyncio.to_thread(
                    self.local.transcribe, floats, name=name, language=self.settings.language, prompt=prompt
                )
            except Exception as exc:
                log.warning("local transcription failed", exc_info=True)
                raise GroqError(
                    "Il modello vocale sul PC non è riuscito a capire l'audio, riprova.",
                    code="local_failed", provider="PC",
                ) from exc
        if wav is None and pcm is not None:
            wav = to_wav(prepare_for_stt(pcm, rate), rate)
        body = wav if wav is not None else (data or b"")
        if engine == "gemini":
            return await self.llm.gemini.transcribe(
                body, filename=filename, mime=mime, model=self.settings.gemini_model,
                language=self.settings.language, prompt=prompt,
            )
        return await self.llm.groq.transcribe(
            body, filename=filename, mime=mime, model=self.settings.stt_model,
            language=self.settings.language, prompt=prompt,
        )

    def _prompt(self) -> str:
        if self.settings.language == "en":
            base = "Ressy, wake up! Hi Ressy, open Discord. What's the weather? Open time.is in the browser."
        else:
            base = "Ressy, sveglia! Ciao Ressy, apri Discord, Spotify o time.is. Che meteo c'è?"
        names: list[str] = []
        if self.settings.user_name:
            names.append(self.settings.user_name)
        if self.vocabulary is not None:
            try:
                names += self.vocabulary()
            except Exception:
                log.debug("vocabulary failed", exc_info=True)
        extra = ""
        for name in dict.fromkeys(n.strip() for n in names if n and n.strip()):
            if len(extra) + len(name) > 380:
                break
            extra += f"{name}, "
        return f"{base} {extra.rstrip(', ')}." if extra else base

    async def transcribe_pcm(self, pcm: np.ndarray, rate: int, *, lenient: bool = False) -> Transcript:
        if pcm.size < rate * MIN_SECONDS:
            return Transcript("", "too_short")
        voiced = voiced_seconds(pcm, rate)
        if voiced is not None and voiced < MIN_VOICED_SECONDS:
            log.info("no voice in %.1fs of audio", pcm.size / rate)
            return Transcript("", "silence")
        payload = await self._run(pcm=pcm, rate=rate)
        result = clean_transcription(payload, lenient=lenient)
        log.info("heard %d characters%s", len(result.text), f" (rejected: {result.rejected})" if result.rejected else "")
        return result

    async def transcribe_file(self, data: bytes, mime: str) -> Transcript:
        mime = (mime or "audio/ogg").split(";")[0]
        payload = await self._run(data=data, mime=mime, filename=f"nota-vocale.{extension_for(mime)}")
        return clean_transcription(payload)

    def preload(self) -> None:
        if self.engine == "local" and local_stt.is_downloaded(self.settings.local_stt_model):
            self.local.preload(self.settings.local_stt_model)
