"""
Base interface for exchange connectors.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from models import WebhookPayload


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    message: str = ""


class ExchangeBase(ABC):
    """Abstract base for all exchange connectors."""

    @abstractmethod
    def name(self) -> str:
        pass

    def reset_client(self) -> None:
        """Clear cached client so next use recreates it (e.g. after network switch). Override if needed."""
        pass

    @abstractmethod
    def place_market_order(
        self,
        symbol: str,
        side: str,
        size_usdt: float,
        leverage: Optional[int] = None,
    ) -> OrderResult:
        """Place a market order. size_usdt is notional (margin * leverage)."""
        pass

    @abstractmethod
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for the symbol. Return True on success."""
        pass

    def get_last_price(self, symbol: str) -> float:
        """Optional: last price for the symbol. Default 0 (TP/SL may be skipped)."""
        return 0.0

    def get_orderbook(self, symbol: str, limit: int = 5) -> tuple[float, float, float]:
        """Optional: (bid, ask, mid). Return (0,0,0) if not available."""
        return 0.0, 0.0, 0.0

    def fetch_daily_pnl_usdt(self) -> float:
        """Optional: today's realized PnL in USDT (negative = loss). Default 0."""
        return 0.0

    def fetch_total_exposure_usdt(self) -> float:
        """Optional: total open position notional in USDT. Default 0."""
        return 0.0

    def place_tp_sl_orders(
        self,
        symbol: str,
        side: str,
        amount_base: float,
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
    ) -> OrderResult:
        """Optional: place take-profit and/or stop-loss orders. Default: no-op."""
        return OrderResult(success=True, message="TP/SL not configured for this exchange")

    def place_from_payload(
        self,
        payload: WebhookPayload,
        size_usdt: float,
        leverage: Optional[int],
    ) -> OrderResult:
        """Convenience: place order from webhook payload with adjusted size/leverage."""
        symbol = payload.symbol_upper()
        if leverage:
            self.set_leverage(symbol, leverage)
        return self.place_market_order(
            symbol=symbol,
            side=payload.side.value,
            size_usdt=size_usdt,
            leverage=leverage,
        )
