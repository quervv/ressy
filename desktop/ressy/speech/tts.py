from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from typing import Callable

import numpy as np

from ..audio.pcm import from_wav, to_wav
from ..audio.player import AudioPlayer
from ..config import Settings

log = logging.getLogger("ressy.tts")

EDGE_RATE = 24000
CREATE_NO_WINDOW = 0x08000000

_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_BULLET = re.compile(r"^\s*(?:[-*•]+|#+)\s*", re.MULTILINE)
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U0000FE0F\U0000200D\U000020E3]"
)
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def clean_for_speech(text: str, max_chars: int = 900) -> str:
    t = _CODE_BLOCK.sub(" ", text or "")
    t = _MD_LINK.sub(r"\1", t)
    t = _URL.sub("il link", t)
    t = _BULLET.sub("", t)
    t = re.sub(r"[*_~`|>]+", "", t)
    t = _EMOJI.sub("", t)
    lines = [line.strip() for line in t.splitlines() if line.strip()]
    t = " ".join(line if line[-1] in ".!?:;,…" else line + "." for line in lines)
    t = " ".join(t.split())
    if len(t) > max_chars:
        cut = t[:max_chars]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        t = cut[: end + 1] if end > max_chars // 3 else cut.rstrip() + "…"
    return t


def split_for_speech(text: str, target: int = 220) -> list[str]:
    sentences = [s for s in _SENTENCE_END.split(text) if s.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        limit = 120 if not chunks else target
        if current and len(current) + 1 + len(sentence) > limit:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def decode_mp3(data: bytes, rate: int = EDGE_RATE) -> np.ndarray:
    import miniaudio

    decoded = miniaudio.decode(data, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=rate)
    return np.frombuffer(decoded.samples, dtype=np.int16).copy()


def _ps_quote(path: str) -> str:
    return "'" + path.replace("'", "''") + "'"


class Speaker:
    def __init__(self, settings: Settings, player: AudioPlayer) -> None:
        self.settings = settings
        self.player = player
        self._cancel = threading.Event()

    async def edge_mp3(self, text: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(
            text, self.settings.tts_voice, rate=f"{int(self.settings.tts_rate):+d}%", receive_timeout=30
        )
        audio = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                audio.extend(chunk["data"])
        if not audio:
            raise RuntimeError("edge-tts returned no audio")
        return bytes(audio)

    def sapi_wav(self, text: str) -> bytes:
        workdir = tempfile.mkdtemp(prefix="ressy-tts-")
        try:
            txt_path = os.path.join(workdir, "testo.txt")
            wav_path = os.path.join(workdir, "voce.wav")
            with open(txt_path, "w", encoding="utf-8") as fh:
                fh.write(text)
            culture = "en" if self.settings.language == "en" else "it"
            rate = max(-10, min(10, round(int(self.settings.tts_rate) / 5)))
            script = (
                "$ErrorActionPreference = 'Stop'\n"
                "Add-Type -AssemblyName System.Speech\n"
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
                "try {\n"
                f"  $v = $s.GetInstalledVoices() | Where-Object {{ $_.Enabled -and "
                f"$_.VoiceInfo.Culture.Name -like '{culture}*' }} | Select-Object -First 1\n"
                "  if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }\n"
                f"  $s.Rate = {rate}\n"
                f"  $s.SetOutputToWaveFile({_ps_quote(wav_path)})\n"
                f"  $s.Speak([System.IO.File]::ReadAllText({_ps_quote(txt_path)}, [System.Text.Encoding]::UTF8))\n"
                "} finally { $s.Dispose() }\n"
            )
            encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-EncodedCommand", encoded],
                check=True,
                capture_output=True,
                timeout=90,
                creationflags=CREATE_NO_WINDOW,
            )
            with open(wav_path, "rb") as fh:
                return fh.read()
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    async def synthesize(self, text: str) -> tuple[np.ndarray, int] | None:
        if self.settings.tts_engine == "edge":
            try:
                mp3 = await asyncio.wait_for(self.edge_mp3(text), timeout=30)
                return await asyncio.to_thread(decode_mp3, mp3), EDGE_RATE
            except Exception as exc:
                log.warning("edge-tts failed (%s), using the Windows voice", exc)
        try:
            wav = await asyncio.to_thread(self.sapi_wav, text)
            return from_wav(wav)
        except Exception:
            log.exception("Windows speech synthesis failed")
            return None

    async def voice_note(self, text: str) -> tuple[bytes, str] | None:
        clean = clean_for_speech(text, max_chars=2500)
        if not clean:
            return None
        if self.settings.tts_engine == "edge":
            try:
                return await asyncio.wait_for(self.edge_mp3(clean), timeout=60), "audio/mpeg"
            except Exception as exc:
                log.warning("edge-tts failed for a voice note (%s)", exc)
        try:
            return await asyncio.to_thread(self.sapi_wav, clean), "audio/wav"
        except Exception:
            log.exception("Windows speech synthesis failed")
            return None

    def interrupt(self) -> None:
        self._cancel.set()
        self.player.stop()

    async def speak(self, text: str, *, on_chunk: Callable[[str], None] | None = None) -> bool:
        clean = clean_for_speech(text)
        if not clean:
            return True
        cancel = threading.Event()
        self._cancel = cancel
        chunks = split_for_speech(clean)
        pending = asyncio.ensure_future(self.synthesize(chunks[0]))
        played = False
        try:
            for index, chunk in enumerate(chunks):
                audio = await pending
                if index + 1 < len(chunks):
                    pending = asyncio.ensure_future(self.synthesize(chunks[index + 1]))
                if cancel.is_set():
                    return False
                if audio is None:
                    continue
                if on_chunk is not None:
                    on_chunk(chunk)
                completed = await asyncio.to_thread(self.player.play, audio[0], audio[1], cancel=cancel)
                if not completed:
                    return False
                played = True
            return played
        finally:
            if not pending.done():
                pending.cancel()

    @staticmethod
    def wav_bytes(pcm: np.ndarray, rate: int) -> bytes:
        return to_wav(pcm, rate)
