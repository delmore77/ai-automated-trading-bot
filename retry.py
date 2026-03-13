"""
Retry with backoff for exchange calls.
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

from config import settings

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    max_attempts: int | None = None,
    delay_seconds: float | None = None,
) -> T:
    if max_attempts is None:
        max_attempts = max(1, settings.order_retries) + 1
    if delay_seconds is None:
        delay_seconds = settings.order_retry_delay_seconds
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < max_attempts - 1:
                time.sleep(delay_seconds * (attempt + 1))
    raise last_exc
