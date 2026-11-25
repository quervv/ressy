from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable

import numpy as np

from . import devices
from .meter import Meter
from .pcm import StreamResampler, level_from_dbfs, rms_dbfs

log = logging.getLogger("ressy.mic")

RATE = 16000
FRAME = 480

FrameCallback = Callable[[np.ndarray, float], None]


class MicError(RuntimeError):
    pass


class _Session:

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.loudest = -120.0
        self.frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=600)
        self.stop = threading.Event()
        self.resampler: StreamResampler | None = None
        self.carry = np.zeros(0, dtype=np.int16)
        self.stream = None
        self.thread: threading.Thread | None = None


class Microphone:
    def __init__(self, device_name: Callable[[], str]) -> None:
        self._device_name = device_name
        self._session: _Session | None = None
        self._lock = threading.Lock()
        self._on_frame: FrameCallback | None = None
        self.fallback = ""
        self._fallback_checked = False
        self.on_switch: Callable[[str], None] | None = None
        self.level = 0.0
        self.meter = Meter()

    @property
    def running(self) -> bool:
        return self._session is not None

    def set_consumer(self, on_frame: FrameCallback | None) -> None:
        self._on_frame = on_frame

    def start(self, on_frame: FrameCallback | None = None) -> None:
        with self._lock:
            if on_frame is not None:
                self._on_frame = on_frame
            if self._session is not None:
                return
            import sounddevice as sd

            session = _Session()
            chosen = self._device_name()
            device = devices.resolve(chosen or self.fallback, "input")
            callback = self._make_callback(session)
            try:
                stream = sd.InputStream(
                    samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME, device=device, callback=callback
                )
            except Exception:
                try:
                    info = sd.query_devices(device, "input")
                    native = int(info["default_samplerate"])
                    session.resampler = StreamResampler(native, RATE)
                    stream = sd.InputStream(
                        samplerate=native,
                        channels=1,
                        dtype="int16",
                        blocksize=int(native * 0.03),
                        device=device,
                        callback=callback,
                    )
                    log.info("microphone opened at %d Hz (resampling to 16 kHz)", native)
                except Exception as exc:
                    raise MicError(f"Impossibile aprire il microfono: {exc}") from exc
            session.stream = stream
            session.thread = threading.Thread(target=self._consume, args=(session,), name="mic-consumer", daemon=True)
            session.thread.start()
            try:
                stream.start()
            except Exception as exc:
                session.stop.set()
                stream.close()
                raise MicError(f"Impossibile avviare il microfono: {exc}") from exc
            self._session = session
            log.debug("microphone started")

    def stop(self) -> None:
        with self._lock:
            session, self._session = self._session, None
            if session is None:
                return
            session.stop.set()
            try:
                session.stream.stop()
                session.stream.close()
            except Exception:
                log.exception("error closing microphone")
        if session.thread is not None and session.thread is not threading.current_thread():
            session.thread.join(timeout=1.0)
        self.level = 0.0
        self.meter.clear()
        log.debug("microphone stopped")

    def _find_live_input(self) -> None:
        log.warning("the default microphone sends only silence: looking for one that works")
        was_running = self.running
        self.stop()
        name = devices.live_input()
        if name:
            self.fallback = name
            log.info("using the microphone %r instead of the silent default", name)
        if was_running:
            try:
                self.start()
            except MicError:
                log.exception("cannot restart the microphone")
                return
        if name and self.on_switch is not None:
            try:
                self.on_switch(name)
            except Exception:
                log.exception("on_switch failed")

    @staticmethod
    def _make_callback(session: _Session):
        def callback(indata, frames, time_info, status) -> None:
            block = np.array(indata[:, 0] if indata.ndim == 2 else indata, dtype=np.int16, copy=True)
            if session.resampler is not None:
                block = session.resampler.process(block)
            data = np.concatenate([session.carry, block]) if session.carry.size else block
            offset = 0
            while data.size - offset >= FRAME:
                try:
                    session.frames.put_nowait(data[offset : offset + FRAME])
                except queue.Full:
                    pass
                offset += FRAME
            session.carry = data[offset:].copy()

        return callback

    def _consume(self, session: _Session) -> None:
        while not session.stop.is_set():
            try:
                frame = session.frames.get(timeout=0.2)
            except queue.Empty:
                continue
            if session.stop.is_set():
                break
            db = rms_dbfs(frame)
            if db > session.loudest:
                session.loudest = db
            if not self._fallback_checked and time.monotonic() - session.started > 2.5:
                self._fallback_checked = True
                if session.loudest <= devices.SILENT_DB and not self._device_name() and not self.fallback:
                    threading.Thread(target=self._find_live_input, name="mic-fallback", daemon=True).start()
            target = level_from_dbfs(db)
            self.level = target if target > self.level else self.level * 0.82 + target * 0.18
            self.meter.push(frame, RATE)
            callback = self._on_frame
            if callback is not None:
                try:
                    callback(frame, db)
                except Exception:
                    log.exception("frame consumer failed")
