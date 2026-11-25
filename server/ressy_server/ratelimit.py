from __future__ import annotations

import time
from collections import deque
from typing import Callable, Hashable


class SlidingWindow:
    def __init__(self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[Hashable, deque[float]] = {}

    def _prune(self, key: Hashable, now: float) -> deque[float] | None:
        hits = self._hits.get(key)
        if hits is None:
            return None
        cutoff = now - self.window_s
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if not hits:
            del self._hits[key]
            return None
        return hits

    def count(self, key: Hashable) -> int:
        hits = self._prune(key, self._clock())
        return len(hits) if hits else 0

    def allowed(self, key: Hashable) -> bool:
        return self.count(key) < self.limit

    def hit(self, key: Hashable) -> bool:
        now = self._clock()
        hits = self._prune(key, now)
        if hits is not None and len(hits) >= self.limit:
            return False
        if hits is None:
            hits = self._hits.setdefault(key, deque())
        hits.append(now)
        return True

    def reset(self, key: Hashable) -> None:
        self._hits.pop(key, None)
