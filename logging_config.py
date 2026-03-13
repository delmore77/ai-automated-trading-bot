"""
Structured logging: JSON-like format for key fields.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_dict: Dict[str, Any] = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_dict["request_id"] = getattr(record, "request_id", "")
        if hasattr(record, "exchange"):
            log_dict["exchange"] = getattr(record, "exchange", "")
        if hasattr(record, "symbol"):
            log_dict["symbol"] = getattr(record, "symbol", "")
        if hasattr(record, "order_id"):
            log_dict["order_id"] = getattr(record, "order_id", "")
        if record.exc_info:
            log_dict["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_dict, default=str)


def setup_logging(use_json: bool = True) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        if use_json:
            handler.setFormatter(StructuredFormatter())
        else:
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        root.addHandler(handler)
