"""
AI enhancer: filter or adjust TradingView webhook payloads using LLM.
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
class EnhancerResult:
    allow: bool  # If False, do not execute this alert
    reason: str
    adjustments: Optional[Dict[str, Any]] = None  # Optional overrides to apply to payload (e.g. size_usdt, take_profit, stop_loss)
    request_id: Optional[str] = None


def enhancer_process(payload: WebhookPayload, context: Optional[Dict[str, Any]] = None) -> EnhancerResult:
    """
    Run LLM on the alert: filter (allow/block) and optionally suggest adjustments.
    If enhancer disabled or API key missing, returns allow=True and no adjustments.
    """
    if not settings.ai_enhancer_enabled or not settings.openai_api_key:
        return EnhancerResult(allow=True, reason="Enhancer disabled or no API key")

    context = context or {}
    summary = (
        f"Exchange: {payload.exchange.value}, Symbol: {payload.symbol}, Side: {payload.side.value}, "
        f"Size: {payload.size_usdt} USDT, Leverage: {payload.leverage}, "
        f"TP: {payload.take_profit}, SL: {payload.stop_loss}, Trailing: {payload.trailing_stop}"
    )
    extra = ""
    if context:
        extra = f"\nExtra context: {context}"

    prompt = f"""You are an alert filter for a crypto trading bot. A TradingView alert is about to be executed.

Alert: {summary}{extra}

Respond with JSON only (no markdown):
{{"allow": true or false, "reason": "one short sentence", "adjustments": null or {{"size_usdt": number, "take_profit": number, "stop_loss": number, "leverage": number}}}}

- Set "allow": false if the alert seems wrong (e.g. duplicate, bad timing, or clearly misconfigured).
- Set "allow": true to let it through. You may suggest "adjustments" (e.g. reduce size, add SL) that the bot will apply.
- Use "adjustments": null if no changes. Only include keys you want to override."""

    try:
        out = llm_json([{"role": "user", "content": prompt}])
        allow = out.get("allow", True)
        reason = str(out.get("reason") or "No reason").strip() or "No reason"
        adjustments = out.get("adjustments")
        if adjustments and not isinstance(adjustments, dict):
            adjustments = None
        return EnhancerResult(allow=allow, reason=reason, adjustments=adjustments)
    except Exception as e:
        logger.warning("Enhancer LLM call failed: %s", e)
        return EnhancerResult(allow=True, reason=f"Enhancer error: {e}")
