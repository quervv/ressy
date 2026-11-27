from __future__ import annotations

import io
import math
import wave

import numpy as np


def to_wav(pcm: np.ndarray, sample_rate: int) -> bytes:
    samples = np.asarray(pcm, dtype=np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(samples.tobytes())
    return buffer.getvalue()


def from_wav(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if width == 2:
        samples = np.frombuffer(frames, dtype=np.int16)
    elif width == 1:
        samples = ((np.frombuffer(frames, dtype=np.uint8).astype(np.int16) - 128) << 8).astype(np.int16)
    elif width == 4:
        samples = (np.frombuffer(frames, dtype=np.int32) >> 16).astype(np.int16)
    else:
        raise ValueError(f"unsupported WAV sample width: {width}")
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return samples.copy(), rate


def rms_dbfs(samples: np.ndarray) -> float:
    if samples.size == 0:
        return -120.0
    x = samples.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(x * x)))
    return 20.0 * math.log10(rms) if rms > 1e-6 else -120.0


def level_from_dbfs(db: float, floor: float = -58.0, ceiling: float = -12.0) -> float:
    return float(min(1.0, max(0.0, (db - floor) / (ceiling - floor))))


def resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or samples.size == 0:
        return np.asarray(samples, dtype=np.int16)
    duration = samples.size / float(src_rate)
    n_out = max(1, int(round(duration * dst_rate)))
    src_t = np.arange(samples.size, dtype=np.float64) / src_rate
    dst_t = np.arange(n_out, dtype=np.float64) / dst_rate
    out = np.interp(dst_t, src_t, samples.astype(np.float64))
    return np.clip(np.round(out), -32768, 32767).astype(np.int16)


class StreamResampler:

    def __init__(self, src_rate: int, dst_rate: int) -> None:
        self.src_rate = src_rate
        self.dst_rate = dst_rate
        self._step = src_rate / float(dst_rate)
        self._pos = 0.0
        self._pending = np.zeros(0, dtype=np.float64)

    def process(self, block: np.ndarray) -> np.ndarray:
        if self.src_rate == self.dst_rate:
            return np.asarray(block, dtype=np.int16)
        self._pending = np.concatenate([self._pending, block.astype(np.float64)])
        last = self._pending.size - 1
        if last < 1:
            return np.zeros(0, dtype=np.int16)
        count = int(math.floor((last - self._pos) / self._step)) + 1
        if count <= 0:
            return np.zeros(0, dtype=np.int16)
        positions = self._pos + np.arange(count) * self._step
        out = np.interp(positions, np.arange(self._pending.size), self._pending)
        next_pos = self._pos + count * self._step
        drop = int(math.floor(next_pos))
        if drop >= self._pending.size:
            self._pos = next_pos - self._pending.size
            self._pending = np.zeros(0, dtype=np.float64)
        else:
            self._pending = self._pending[drop:]
            self._pos = next_pos - drop
        return np.clip(np.round(out), -32768, 32767).astype(np.int16)


def prepare_for_stt(pcm: np.ndarray, rate: int) -> np.ndarray:
    samples = np.asarray(pcm, dtype=np.int16)
    if samples.size == 0:
        return samples
    arr = samples.astype(np.float32)
    arr -= float(np.mean(arr))
    win = max(3, int(rate / 80))
    if arr.size > win * 2:
        kernel = np.ones(win, dtype=np.float32) / float(win)
        arr = arr - np.convolve(arr, kernel, mode="same")
    samples = np.clip(arr, -32768.0, 32767.0).astype(np.int16)

    frame = max(1, int(rate * 0.03))
    count = samples.size // frame
    if count < 3:
        return samples
    blocks = samples[: count * frame].astype(np.float32).reshape(count, frame)
    rms = np.sqrt(np.mean(blocks * blocks, axis=1)) + 1e-9
    db = 20 * np.log10(rms / 32768.0)
    ref_db = min(-15.0, float(np.percentile(db, 92)))
    loud = np.flatnonzero(db > max(-56.0, ref_db - 36.0))
    if loud.size:
        margin = int(0.35 / 0.03)
        first = max(0, loud[0] - margin)
        last = min(count, loud[-1] + margin + 1)
        samples = samples[first * frame : last * frame] if last * frame <= samples.size else samples[first * frame :]

    if samples.size:
        s_float = samples.astype(np.float32)
        f_count = s_float.size // frame
        if f_count >= 1:
            f_blocks = s_float[: f_count * frame].reshape(f_count, frame)
            speech_level = float(np.percentile(np.max(np.abs(f_blocks), axis=1), 95))
        else:
            speech_level = float(np.abs(s_float).max())
        if 0 < speech_level < 20000.0:
            gain = min(10.0, 20000.0 / speech_level)
            s_float = s_float * gain
            over = np.abs(s_float) > 26000.0
            if np.any(over):
                s_float[over] = np.sign(s_float[over]) * (
                    26000.0 + 6000.0 * np.tanh((np.abs(s_float[over]) - 26000.0) / 8000.0)
                )
            samples = np.clip(s_float, -32767.0, 32767.0).astype(np.int16)

    head = np.zeros(int(rate * 0.16), dtype=np.int16)
    tail = np.zeros(int(rate * 0.32), dtype=np.int16)
    return np.concatenate([head, samples, tail])
