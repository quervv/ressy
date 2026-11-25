from __future__ import annotations

import collections
import math
import threading
import time

import numpy as np

BANDS = 24
_LOW_HZ = 90.0
_HIGH_HZ = 7000.0


class Meter:
    def __init__(self, bands: int = BANDS, floor_db: float = -60.0, ceil_db: float = -14.0) -> None:
        self.n = bands
        self.floor_db = floor_db
        self.ceil_db = ceil_db
        self._queue: collections.deque[tuple[float, float, np.ndarray]] = collections.deque(maxlen=128)
        self._lock = threading.Lock()
        self._current: tuple[float, float, np.ndarray] = (0.0, 0.0, np.zeros(bands, dtype=np.float32))
        self._windows: dict[int, np.ndarray] = {}

    def analyse(self, block: np.ndarray, rate: int) -> tuple[float, np.ndarray]:
        x = np.asarray(block, dtype=np.float32).reshape(-1) / 32768.0
        n = x.size
        if n < 64 or rate <= 0:
            return 0.0, np.zeros(self.n, dtype=np.float32)
        rms = float(np.sqrt(np.mean(x * x)))
        db = 20.0 * math.log10(rms) if rms > 1e-7 else -140.0
        level = min(1.0, max(0.0, (db - self.floor_db) / (self.ceil_db - self.floor_db)))

        window = self._windows.get(n)
        if window is None:
            window = np.hanning(n).astype(np.float32)
            self._windows[n] = window
        spectrum = np.abs(np.fft.rfft(x * window)) / (n / 4.0)
        freqs = np.fft.rfftfreq(n, 1.0 / rate)
        top_hz = min(_HIGH_HZ, rate * 0.45)
        top = int(np.searchsorted(freqs, top_hz))
        if top < 2:
            return level, np.zeros(self.n, dtype=np.float32)
        spectrum = spectrum[:top]
        edges = np.geomspace(_LOW_HZ, top_hz, self.n + 1)[:-1]
        starts = np.clip(np.searchsorted(freqs[:top], edges), 0, top - 1)
        peaks = np.maximum.reduceat(spectrum, starts)
        band_db = 20.0 * np.log10(peaks + 1e-9)
        bands = np.clip((band_db - (self.floor_db - 6.0)) / (self.ceil_db - self.floor_db + 6.0), 0.0, 1.0)
        return level, bands.astype(np.float32)

    def push(self, block: np.ndarray, rate: int, delay: float = 0.0) -> None:
        level, bands = self.analyse(block, rate)
        due = time.monotonic() + max(0.0, delay)
        with self._lock:
            self._queue.append((due, level, bands))

    def read(self, stale_after: float = 0.25) -> tuple[float, np.ndarray]:
        now = time.monotonic()
        with self._lock:
            while self._queue and self._queue[0][0] <= now:
                self._current = self._queue.popleft()
            due, level, bands = self._current
        if now - due > stale_after:
            return 0.0, np.zeros(self.n, dtype=np.float32)
        return level, bands

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()
            self._current = (0.0, 0.0, np.zeros(self.n, dtype=np.float32))
