from __future__ import annotations

import threading
import time

import pytest

from ressy.core.hotkey import LLKHF_INJECTED, WM_KEYDOWN, WM_KEYUP, HoldHotkey

K = 0x4B
O = 0x4F
CTRL = 0x11


class Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.held = threading.Event()
        self.modifiers: set[int] = set()

    def hold(self) -> None:
        self.events.append("hold")
        self.held.set()

    def release(self) -> None:
        self.events.append("release")


@pytest.fixture()
def hk():
    rec = Recorder()
    hotkey = HoldHotkey(lambda: K, lambda: 120, rec.hold, rec.release, modifier_state=lambda vk: vk in rec.modifiers)
    hotkey._running = True
    worker = threading.Thread(target=hotkey._timer_loop, daemon=True)
    worker.start()
    yield hotkey, rec
    hotkey.stop()


def test_quick_tap_types_the_letter_and_does_not_activate(hk):
    hotkey, rec = hk
    assert hotkey.handle(WM_KEYDOWN, K, 0) is False
    time.sleep(0.03)
    assert hotkey.handle(WM_KEYUP, K, 0) is False
    time.sleep(0.2)
    assert rec.events == []


def test_hold_activates_then_release(hk):
    hotkey, rec = hk
    hotkey.handle(WM_KEYDOWN, K, 0)
    assert rec.held.wait(1.0)
    assert hotkey.handle(WM_KEYDOWN, K, 0) is True
    hotkey.handle(WM_KEYUP, K, 0)
    assert rec.events == ["hold", "release"]


def test_auto_repeat_is_swallowed_before_activation_too(hk):
    hotkey, rec = hk
    hotkey.handle(WM_KEYDOWN, K, 0)
    assert hotkey.handle(WM_KEYDOWN, K, 0) is True
    hotkey.handle(WM_KEYUP, K, 0)
    time.sleep(0.2)
    assert rec.events == []


def test_typing_another_key_cancels_the_hold(hk):
    hotkey, rec = hk
    hotkey.handle(WM_KEYDOWN, K, 0)
    hotkey.handle(WM_KEYDOWN, O, 0)
    time.sleep(0.25)
    hotkey.handle(WM_KEYUP, K, 0)
    assert rec.events == []


def test_ctrl_k_belongs_to_the_app(hk):
    hotkey, rec = hk
    rec.modifiers.add(CTRL)
    hotkey.handle(WM_KEYDOWN, K, 0)
    assert hotkey.handle(WM_KEYDOWN, K, 0) is False
    time.sleep(0.25)
    hotkey.handle(WM_KEYUP, K, 0)
    assert rec.events == []


def test_injected_keys_are_ignored(hk):
    hotkey, rec = hk
    hotkey.handle(WM_KEYDOWN, K, LLKHF_INJECTED)
    time.sleep(0.25)
    assert rec.events == []
    assert hotkey._down is False


def test_lost_key_up_does_not_lock_the_key(hk):
    hotkey, rec = hk
    hotkey.handle(WM_KEYDOWN, K, 0)
    hotkey._last_event -= 5
    assert hotkey.handle(WM_KEYDOWN, K, 0) is False


def test_disabled_hotkey_passes_everything(hk):
    hotkey, rec = hk
    hotkey.enabled = False
    hotkey.handle(WM_KEYDOWN, K, 0)
    time.sleep(0.25)
    assert rec.events == []
