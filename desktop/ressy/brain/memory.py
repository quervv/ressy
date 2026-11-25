from __future__ import annotations

import threading
import time
from collections import deque


class Memory:
    def __init__(self, max_turns: int = 8, idle_reset_s: float = 30 * 60) -> None:
        self.max_turns = max_turns
        self.idle_reset_s = idle_reset_s
        self._threads: dict[str, tuple[float, deque[dict]]] = {}
        self._lock = threading.Lock()

    def history(self, key: str) -> list[dict]:
        with self._lock:
            entry = self._threads.get(key)
            if entry is None:
                return []
            last, messages = entry
            if time.monotonic() - last > self.idle_reset_s:
                del self._threads[key]
                return []
            return list(messages)

    def add(self, key: str, user_text: str, assistant_text: str) -> None:
        with self._lock:
            _, messages = self._threads.get(key, (0.0, deque(maxlen=self.max_turns * 2)))
            messages.append({"role": "user", "content": user_text})
            messages.append({"role": "assistant", "content": assistant_text})
            self._threads[key] = (time.monotonic(), messages)

    def clear(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._threads.clear()
            else:
                self._threads.pop(key, None)
