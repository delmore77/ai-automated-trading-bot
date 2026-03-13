"""
Take-profit / stop-loss and trailing stop helpers.
TP/SL are placed per-exchange after the main order.
Trailing stop: optional; activate after X% profit (documented for manual or exchange UI).
"""
from __future__ import annotations

from typing import Optional

from exchanges.base import ExchangeBase, OrderResult


def set_tp_sl_after_order(
    exchange: ExchangeBase,
    symbol: str,
    side: str,
    amount_base: float,
    take_profit_price: Optional[float] = None,
    stop_loss_price: Optional[float] = None,
) -> OrderResult:
    """Call exchange's place_tp_sl_orders after a market order is filled."""
    return exchange.place_tp_sl_orders(
        symbol=symbol,
        side=side,
        amount_base=amount_base,
        take_profit_price=take_profit_price,
        stop_loss_price=stop_loss_price,
    )


def amount_base_from_size_usdt(size_usdt: float, price: float) -> float:
    """Convert notional USDT to base amount for TP/SL orders."""
    if price <= 0:
        return 0.0
    return size_usdt / price
