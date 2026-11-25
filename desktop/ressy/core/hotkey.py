from __future__ import annotations

import logging
import threading
import time
from typing import Callable

log = logging.getLogger("ressy.hotkey")

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
LLKHF_INJECTED = 0x10
_BLOCKING_MODIFIERS = (0x11, 0x12, 0x5B, 0x5C)
TYPING_GAP_S = 0.6
_MODIFIER_VKS = frozenset({0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5})


class HoldHotkey:
    def __init__(
        self,
        vk: Callable[[], int],
        hold_ms: Callable[[], int],
        on_hold: Callable[[], None],
        on_release: Callable[[], None],
        modifier_state: Callable[[int], bool] | None = None,
        on_press: Callable[[], None] | None = None,
    ) -> None:
        self._vk = vk
        self._hold_ms = hold_ms
        self._on_hold = on_hold
        self._on_release = on_release
        self._on_press = on_press
        self._last_other_key = 0.0
        self._modifier_down = modifier_state or _async_key_down
        self.enabled = True
        self._down = False
        self._active = False
        self._cancelled = False
        self._last_event = 0.0
        self._press_id = 0
        self._cond = threading.Condition()
        self._pending: tuple[int, float] | None = None
        self._listener = None
        self._worker: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        from pynput import keyboard

        self._running = True
        self._worker = threading.Thread(target=self._timer_loop, name="hotkey-timer", daemon=True)
        self._worker.start()
        self._listener = keyboard.Listener(win32_event_filter=self._filter)
        self._listener.start()
        log.info("hotkey listener started")

    def stop(self) -> None:
        self._running = False
        with self._cond:
            self._cond.notify_all()
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _filter(self, msg: int, data) -> bool:
        try:
            suppress = self.handle(msg, int(data.vkCode), int(data.flags))
        except Exception:
            log.exception("hotkey filter error")
            return False
        if suppress and self._listener is not None:
            self._listener.suppress_event()
        return False

    def handle(self, msg: int, vk: int, flags: int) -> bool:
        if flags & LLKHF_INJECTED or not self.enabled:
            return False
        is_down = msg in (WM_KEYDOWN, WM_SYSKEYDOWN)
        is_up = msg in (WM_KEYUP, WM_SYSKEYUP)
        hotkey = self._vk()

        now = time.monotonic()
        if vk != hotkey:
            if is_down and vk not in _MODIFIER_VKS:
                self._last_other_key = now
            if is_down and self._down and not self._active and vk not in _MODIFIER_VKS:
                self._cancel_pending()
            return False

        if is_down:
            with self._cond:
                if self._down and now - self._last_event < 1.2:
                    self._last_event = now
                    return not self._cancelled
                self._last_event = now
                self._down = True
                self._active = False
                self._cancelled = any(self._modifier_down(m) for m in _BLOCKING_MODIFIERS)
                if self._cancelled:
                    self._pending = None
                else:
                    self._press_id += 1
                    self._pending = (self._press_id, now + self._hold_ms() / 1000.0)
                self._cond.notify_all()
            typing = now - self._last_other_key < TYPING_GAP_S
            if not self._cancelled and not typing and self._on_press is not None:
                self._fire(self._on_press)
            return False

        if is_up:
            with self._cond:
                was_active = self._active
                self._down = False
                self._active = False
                self._pending = None
                self._last_event = now
                self._cond.notify_all()
            if was_active:
                self._fire(self._on_release)
            return False
        return False

    def _cancel_pending(self) -> None:
        with self._cond:
            self._pending = None
            self._cond.notify_all()

    def _timer_loop(self) -> None:
        while self._running:
            with self._cond:
                while self._running and self._pending is None:
                    self._cond.wait()
                if not self._running:
                    return
                press_id, deadline = self._pending
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    self._cond.wait(remaining)
                    continue
                self._pending = None
                if press_id != self._press_id or not self._down or self._cancelled:
                    continue
                self._active = True
                self._fire(self._on_hold)

    @staticmethod
    def _fire(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            log.exception("hotkey callback failed")


def _async_key_down(vk: int) -> bool:
    from ..tools.winapi import user32

    return bool(user32.GetAsyncKeyState(vk) & 0x8000)
