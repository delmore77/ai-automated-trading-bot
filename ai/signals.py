"""
AI signal layer: generate buy/sell/hold signals from market context (and optionally execute).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from config import settings
from exchanges.registry import get_exchange

from .llm import llm_json

logger = logging.getLogger(__name__)


def _market_context(exchange_name: str, symbol: str) -> Dict[str, Any]:
    """Fetch price and optional orderbook for symbol."""
    ex = get_exchange(exchange_name)
    if not ex:
        return {}
    try:
        price = ex.get_last_price(symbol)
        bid, ask, mid = ex.get_orderbook(symbol, 5)
        return {
            "price": price,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread_pct": 100 * (ask - bid) / mid if mid and bid and ask else None,
        }
    except Exception as e:
        logger.warning("Market context failed: %s", e)
        return {"price": 0, "error": str(e)}


def generate_signal(
    exchange: str,
    symbol: str,
    default_size_usdt: float = 100.0,
    context_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Use LLM to produce a trading signal (action, size, tp, sl) from current market context.
    Returns a dict that can be turned into a WebhookPayload or used for execution:
    { "action": "buy"|"sell"|"hold", "size_usdt": float, "take_profit": float|null, "stop_loss": float|null, "leverage": int|null, "reason": str }
    If action is "hold", no order should be placed.
    """
    if not settings.ai_signal_enabled or not settings.openai_api_key:
        return {"action": "hold", "reason": "AI signal disabled or no API key", "size_usdt": 0}

    ctx = _market_context(exchange, symbol)
    ctx.update(context_extra or {})
    if ctx.get("price", 0) <= 0:
        return {"action": "hold", "reason": "No price data", "size_usdt": 0}

    prompt = f"""You are a crypto trading signal generator. Given the current market context, output a single signal as JSON.

Market: exchange={exchange}, symbol={symbol}. Price: {ctx.get('price')}, Bid: {ctx.get('bid')}, Ask: {ctx.get('ask')}, Spread%: {ctx.get('spread_pct')}.

Respond with JSON only (no markdown):
{{"action": "buy" or "sell" or "hold", "reason": "one short sentence", "size_usdt": number (0 if hold), "take_profit": number or null, "stop_loss": number or null, "leverage": number or null}}

- Use "hold" if you would not take a position (e.g. unclear trend, high spread).
- For buy/sell, suggest reasonable size_usdt (default max {default_size_usdt}), and always suggest stop_loss. take_profit is optional.
- Only output valid JSON."""

    try:
        out = llm_json([{"role": "user", "content": prompt}])
        action = (out.get("action") or "hold").lower()
        if action not in ("buy", "sell", "hold"):
            action = "hold"
        size = float(out.get("size_usdt") or 0)
        if action == "hold":
            size = 0
        return {
            "action": action,
            "reason": str(out.get("reason") or "No reason"),
            "size_usdt": min(size, default_size_usdt) if size else 0,
            "take_profit": out.get("take_profit"),
            "stop_loss": out.get("stop_loss"),
            "leverage": out.get("leverage"),
            "exchange": exchange,
            "symbol": symbol,
        }
    except Exception as e:
        logger.warning("Signal generation failed: %s", e)
        return {"action": "hold", "reason": str(e), "size_usdt": 0, "exchange": exchange, "symbol": symbol}
