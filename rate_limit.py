"""
In-memory rate limiter: max N requests per minute per key (e.g. client IP or global).
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import DefaultDict, List

from config import settings


class RateLimiter:
    def __init__(self, max_per_minute: int) -> None:
        self.max_per_minute = max_per_minute
        self._requests: DefaultDict[str, List[float]] = defaultdict(list)

    def _prune(self, key: str, now: float) -> None:
        cutoff = now - 60.0
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

    def allow(self, key: str = "global") -> bool:
        now = time.time()
        self._prune(key, now)
        if len(self._requests[key]) >= self.max_per_minute:
            return False
        self._requests[key].append(now)
        return True


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(settings.rate_limit_per_minute)
    return _limiter
