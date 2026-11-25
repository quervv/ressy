from __future__ import annotations

import collections
import logging
from typing import Callable

import numpy as np

from .mic import FRAME, RATE

log = logging.getLogger("ressy.vad")

FRAME_MS = 30

try:
    import webrtcvad
except Exception:
    webrtcvad = None


class UtteranceDetector:
    def __init__(
        self,
        on_start: Callable[[], None],
        on_utterance: Callable[[np.ndarray], None],
        *,
        pre_roll_ms: int = 360,
        start_ms: int = 150,
        end_silence_ms: int = 750,
        min_speech_ms: int = 420,
        max_utterance_ms: int = 20000,
        aggressiveness: int = 2,
        on_discard: Callable[[], None] | None = None,
    ) -> None:
        self.on_start = on_start
        self.on_utterance = on_utterance
        self.on_discard = on_discard
        self.pre_roll = collections.deque(maxlen=max(1, pre_roll_ms // FRAME_MS))
        self.start_frames = max(1, start_ms // FRAME_MS)
        self.end_frames = max(1, end_silence_ms // FRAME_MS)
        self.min_speech_frames = max(1, min_speech_ms // FRAME_MS)
        self.max_frames = max_utterance_ms // FRAME_MS
        self._vad = webrtcvad.Vad(aggressiveness) if webrtcvad is not None else None
        self.noise_floor = -55.0
        self.enabled = True
        self.reset()

    def reset(self) -> None:
        self.in_speech = False
        self._candidate = 0
        self._silence = 0
        self._voiced = 0
        self._frames: list[np.ndarray] = []
        self.pre_roll.clear()

    def _is_speech(self, frame: np.ndarray, db: float) -> bool:
        threshold = max(self.noise_floor + 11.0, -50.0)
        if db < threshold:
            return False
        if self._vad is None:
            return True
        try:
            return bool(self._vad.is_speech(frame.tobytes(), RATE))
        except Exception:
            return True

    def _adapt_floor(self, db: float) -> None:
        if db < self.noise_floor:
            self.noise_floor = 0.7 * self.noise_floor + 0.3 * db
        else:
            self.noise_floor = 0.985 * self.noise_floor + 0.015 * db
        self.noise_floor = float(min(-30.0, max(-75.0, self.noise_floor)))

    def process(self, frame: np.ndarray, db: float) -> None:
        if not self.enabled or frame.size != FRAME:
            return
        speech = self._is_speech(frame, db)
        if not self.in_speech:
            self.pre_roll.append(frame)
            if speech:
                self._candidate += 1
                if self._candidate >= self.start_frames:
                    self.in_speech = True
                    self._frames = list(self.pre_roll)
                    self._voiced = self._candidate
                    self._silence = 0
                    self.pre_roll.clear()
                    try:
                        self.on_start()
                    except Exception:
                        log.exception("on_start failed")
            else:
                self._candidate = 0
                self._adapt_floor(db)
            return

        self._frames.append(frame)
        if speech:
            self._voiced += 1
            self._silence = 0
        else:
            self._silence += 1
        if self._silence >= self.end_frames or len(self._frames) >= self.max_frames:
            frames, voiced = self._frames, self._voiced
            keep_tail = min(self._silence, 6)
            if self._silence > keep_tail:
                frames = frames[: len(frames) - (self._silence - keep_tail)]
            self.reset()
            if voiced >= self.min_speech_frames:
                try:
                    self.on_utterance(np.concatenate(frames))
                except Exception:
                    log.exception("on_utterance failed")
            elif self.on_discard is not None:
                try:
                    self.on_discard()
                except Exception:
                    log.exception("on_discard failed")


class PushToTalkBuffer:

    def __init__(self, max_seconds: int = 60) -> None:
        self._frames: list[np.ndarray] = []
        self._max = max_seconds * 1000 // FRAME_MS
        self.active = False

    def begin(self, prefill: list[np.ndarray] | None = None) -> None:
        self._frames = list(prefill or [])[: self._max]
        self.active = True

    def add(self, frame: np.ndarray) -> None:
        if self.active and len(self._frames) < self._max:
            self._frames.append(frame)

    def end(self) -> np.ndarray:
        self.active = False
        frames, self._frames = self._frames, []
        return np.concatenate(frames) if frames else np.zeros(0, dtype=np.int16)


def voiced_seconds(pcm: np.ndarray, rate: int = 16000, aggressiveness: int = 2) -> float | None:
    if webrtcvad is None or rate not in (8000, 16000, 32000, 48000):
        return None
    vad = webrtcvad.Vad(aggressiveness)
    step = rate * 30 // 1000
    data = np.ascontiguousarray(pcm, dtype=np.int16)
    voiced = 0
    for start in range(0, len(data) - step + 1, step):
        frame = data[start:start + step]
        if np.abs(frame).max() < 200:
            continue
        if vad.is_speech(frame.tobytes(), rate):
            voiced += 1
    return voiced * 0.03
