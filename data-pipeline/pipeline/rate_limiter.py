from __future__ import annotations

import threading
import time
from collections import deque


class RequestsPerMinuteLimiter:
    """Thread-safe sliding-window limiter for API requests."""

    def __init__(self, max_requests_per_minute: int | None) -> None:
        self.max_rpm = max_requests_per_minute or 0
        self._lock = threading.Lock()
        self._events: deque[float] = deque()

    def acquire(self) -> None:
        if self.max_rpm <= 0:
            return

        while True:
            now = time.monotonic()
            with self._lock:
                cutoff = now - 60.0
                while self._events and self._events[0] <= cutoff:
                    self._events.popleft()

                if len(self._events) < self.max_rpm:
                    self._events.append(now)
                    return

                sleep_for = max(0.01, 60.0 - (now - self._events[0]))
            time.sleep(sleep_for)
