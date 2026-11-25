from __future__ import annotations

import logging
import threading
from typing import Callable

import numpy as np

from . import devices
from .meter import Meter
from .pcm import resample

log = logging.getLogger("ressy.player")


class AudioPlayer:
    def __init__(self, device_name: Callable[[], str]) -> None:
        self._device_name = device_name
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._active = False
        self.meter = Meter()

    @property
    def playing(self) -> bool:
        return self._active

    def stop(self) -> None:
        self._stop.set()

    def play(
        self, pcm: np.ndarray, rate: int, *, meter: bool = True, cancel: threading.Event | None = None
    ) -> bool:
        samples = np.asarray(pcm, dtype=np.int16).reshape(-1)
        if samples.size == 0:
            return True
        if cancel is not None and cancel.is_set():
            return False
        with self._lock:
            self._stop.clear()
            self._active = True
            try:
                return self._play_locked(samples, int(rate), meter, cancel)
            except Exception:
                log.exception("playback failed")
                return False
            finally:
                self._active = False
                if meter:
                    self.meter.clear()

    def _open(self, rate: int, callback, finished: threading.Event):
        import sounddevice as sd

        device = devices.resolve(self._device_name(), "output")
        return sd.OutputStream(
            samplerate=rate,
            channels=1,
            dtype="int16",
            device=device,
            blocksize=max(64, rate // 50),
            callback=callback,
            finished_callback=finished.set,
        )

    def _stopped(self, cancel: threading.Event | None) -> bool:
        return self._stop.is_set() or (cancel is not None and cancel.is_set())

    def _play_locked(self, samples: np.ndarray, rate: int, use_meter: bool, cancel: threading.Event | None) -> bool:
        import sounddevice as sd

        state = {"pos": 0, "latency": 0.0, "data": samples, "aborted": False}
        finished = threading.Event()

        def callback(outdata, frames, time_info, status) -> None:
            if self._stopped(cancel):
                outdata.fill(0)
                state["aborted"] = True
                raise sd.CallbackAbort
            data = state["data"]
            pos = state["pos"]
            chunk = data[pos : pos + frames]
            n = chunk.size
            outdata[:n, 0] = chunk
            if n < frames:
                outdata[n:, 0] = 0
            state["pos"] = pos + n
            if use_meter and n:
                try:
                    self.meter.push(chunk, state["rate"], delay=state["latency"])
                except Exception:
                    pass
            if n < frames:
                raise sd.CallbackStop

        state["rate"] = rate
        try:
            stream = self._open(rate, callback, finished)
        except Exception:
            info = sd.query_devices(devices.resolve(self._device_name(), "output"), "output")
            native = int(info["default_samplerate"])
            state["data"] = resample(samples, rate, native)
            state["rate"] = native
            rate = native
            stream = self._open(rate, callback, finished)

        try:
            state["latency"] = float(stream.latency or 0.0)
            stream.start()
            duration = state["data"].size / float(rate)
            finished.wait(timeout=duration + 4.0)
        finally:
            try:
                if stream.active:
                    stream.abort()
            finally:
                stream.close()
        return finished.is_set() and not state["aborted"] and not self._stopped(cancel)
