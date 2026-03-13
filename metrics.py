"""
In-memory metrics for observability. Exposed via GET /metrics.
"""
from __future__ import annotations

import threading
from typing import Dict

_lock = threading.Lock()
_metrics: Dict[str, int] = {
    "webhooks_received": 0,
    "webhooks_duplicate": 0,
    "webhooks_rate_limited": 0,
    "webhooks_auth_failed": 0,
    "webhooks_risk_rejected": 0,
    "webhooks_validation_error": 0,
    "orders_placed": 0,
    "orders_failed": 0,
    "orders_dry_run": 0,
    "tpsl_placed": 0,
    "tpsl_failed": 0,
    "errors": 0,
}


def inc(name: str, delta: int = 1) -> None:
    with _lock:
        _metrics[name] = _metrics.get(name, 0) + delta


def get_all() -> Dict[str, int]:
    with _lock:
        return dict(_metrics)


def reset() -> None:
    with _lock:
        for k in _metrics:
            _metrics[k] = 0
