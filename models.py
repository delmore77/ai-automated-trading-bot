"""
Webhook payload and trade models for TradingView alerts.
"""
from __future__ import annotations

import hashlib
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class ExchangeName(str, Enum):
    BINANCE = "binance"
    BYBIT = "bybit"
    OKX = "okx"
    HYPERLIQUID = "hyperliquid"


class WebhookPayload(BaseModel):
    """Payload expected from TradingView webhook (JSON)."""

    secret: str = Field(..., description="Webhook secret for auth")
    exchange: ExchangeName = Field(..., description="Target exchange")
    symbol: str = Field(..., description="Trading pair, e.g. BTCUSDT")
    side: Side = Field(..., description="buy or sell")
    size_usdt: float = Field(..., gt=0, description="Position size in USDT")
    leverage: Optional[int] = Field(None, ge=1, le=125, description="Leverage (optional)")
    take_profit: Optional[float] = Field(None, gt=0, description="Take-profit price")
    stop_loss: Optional[float] = Field(None, gt=0, description="Stop-loss price")
    trailing_stop: bool = Field(False, description="Enable trailing stop")
    trailing_activation_pct: Optional[float] = Field(
        None, ge=0, le=100, description="Activate trailing after this % profit"
    )
    request_id: Optional[str] = Field(None, description="Unique id for idempotency (e.g. alert id)")

    def symbol_upper(self) -> str:
        return self.symbol.strip().upper()

    def idempotency_key(self) -> str:
        """Key for idempotency: request_id if set, else hash of main fields."""
        if self.request_id:
            return self.request_id
        raw = f"{self.exchange}:{self.symbol_upper()}:{self.side}:{self.size_usdt}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
