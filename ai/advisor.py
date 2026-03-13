"""
LLM advisor: approve, reject, or suggest modifications for a trade before execution.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from config import settings
from models import WebhookPayload

from .llm import llm_json

logger = logging.getLogger(__name__)


@dataclass
class AdvisorResult:
    approve: bool
    reason: str
    modify: Optional[Dict[str, Any]] = None  # Optional overrides: size_usdt, take_profit, stop_loss, leverage


def _trade_summary(payload: WebhookPayload, size_usdt: float, leverage: Optional[int], current_price: float) -> str:
    return (
        f"Exchange: {payload.exchange.value}, Symbol: {payload.symbol}, Side: {payload.side.value}, "
        f"Size: {size_usdt} USDT, Leverage: {leverage or 'none'}, "
        f"Take profit: {payload.take_profit or 'none'}, Stop loss: {payload.stop_loss or 'none'}, "
        f"Current price (approx): {current_price}"
    )


def advisor_review(
    payload: WebhookPayload,
    size_usdt: float,
    leverage: Optional[int],
    current_price: float,
) -> AdvisorResult:
    """
    Ask LLM to review the trade. Returns approve/reject and optional modify fields.
    If LLM fails or API key missing, returns approve=True (no block).
    """
    if not settings.llm_advisor_enabled or not settings.openai_api_key:
        return AdvisorResult(approve=True, reason="Advisor disabled or no API key")

    summary = _trade_summary(payload, size_usdt, leverage, current_price)
    prompt = f"""You are a cautious trading risk advisor. Review this crypto futures trade and respond with JSON only.

Trade: {summary}

Rules:
- Approve if the trade seems reasonable (size, direction, TP/SL present).
- Reject if size is very large vs typical, or no stop loss on a leveraged position, or obvious misconfiguration.
- You may suggest modifications (smaller size, add stop_loss, add take_profit) via the "modify" object.

Respond with exactly this JSON structure (no markdown, no extra text):
{{"approve": true or false, "reason": "one short sentence", "modify": null or {{"size_usdt": number, "take_profit": number, "stop_loss": number, "leverage": number}}}}

If you approve with no changes, use "modify": null. Only include keys in "modify" that you want to change."""

    try:
        out = llm_json([{"role": "user", "content": prompt}])
        approve = out.get("approve", True)
        reason = str(out.get("reason") or "No reason given").strip() or "No reason given"
        modify = out.get("modify")
        if modify and not isinstance(modify, dict):
            modify = None
        return AdvisorResult(approve=approve, reason=reason, modify=modify)
    except Exception as e:
        logger.warning("Advisor LLM call failed: %s", e)
        return AdvisorResult(approve=True, reason=f"Advisor error: {e}")
