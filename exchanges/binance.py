"""
Binance Futures connector (CCXT).
"""
from __future__ import annotations

from typing import Optional

import ccxt

from config import settings
from exchanges.base import ExchangeBase, OrderResult
from runtime_settings import get_use_testnet
from utils import ccxt_symbol


class BinanceExchange(ExchangeBase):
    def __init__(self) -> None:
        self._client: Optional[ccxt.Exchange] = None

    def reset_client(self) -> None:
        self._client = None

    def _get_client(self) -> ccxt.Exchange:
        if self._client is None:
            self._client = ccxt.binance({
                "apiKey": settings.binance_api_key,
                "secret": settings.binance_api_secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "future",
                },
            })
            if get_use_testnet(self.name()):
                self._client.set_sandbox_mode(True)
        return self._client

    def name(self) -> str:
        return "binance"

    def get_last_price(self, symbol: str) -> float:
        try:
            client = self._get_client()
            ticker = client.fetch_ticker(ccxt_symbol(symbol))
            return float(ticker.get("last") or ticker.get("close") or 0)
        except Exception:
            return 0.0

    def get_orderbook(self, symbol: str, limit: int = 5) -> tuple[float, float, float]:
        try:
            client = self._get_client()
            ob = client.fetch_order_book(ccxt_symbol(symbol), limit)
            bids = ob.get("bids") or []
            asks = ob.get("asks") or []
            bid = float(bids[0][0]) if bids else 0.0
            ask = float(asks[0][0]) if asks else 0.0
            mid = (bid + ask) / 2.0 if (bid and ask) else 0.0
            return bid, ask, mid
        except Exception:
            return 0.0, 0.0, 0.0

    def fetch_daily_pnl_usdt(self) -> float:
        try:
            client = self._get_client()
            # Binance futures: fapiPrivateGetIncome returns list of income records
            if hasattr(client, "fapiPrivateGetIncome"):
                items = client.fapiPrivateGetIncome({"incomeType": "REALIZED_PNL", "limit": 100})
                if isinstance(items, list):
                    from datetime import datetime, timezone
                    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
                    total = sum(float(i.get("income", 0) or 0) for i in items if float(i.get("time", 0) or 0) >= today_start)
                    return total
            return 0.0
        except Exception:
            return 0.0

    def fetch_total_exposure_usdt(self) -> float:
        try:
            client = self._get_client()
            positions = client.fetch_positions()
            total = 0.0
            for p in positions or []:
                if p.get("contracts") and float(p.get("contracts", 0) or 0) != 0:
                    notional = abs(float(p.get("notional", 0) or 0)) or abs(float(p.get("contractSize", 0) or 0) * float(p.get("contracts", 0) or 0) * float(p.get("markPrice") or p.get("last", 0) or 0))
                    total += notional
            return total
        except Exception:
            return 0.0

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        try:
            client = self._get_client()
            client.set_leverage(leverage, ccxt_symbol(symbol))
            return True
        except Exception as e:
            # Some exchanges ignore if already set
            return False

    def place_market_order(
        self,
        symbol: str,
        side: str,
        size_usdt: float,
        leverage: Optional[int] = None,
    ) -> OrderResult:
        try:
            client = self._get_client()
            client.load_markets()
            sym = ccxt_symbol(symbol)
            ticker = client.fetch_ticker(sym)
            price = float(ticker.get("last") or ticker.get("close") or 1)
            if price <= 0:
                return OrderResult(success=False, message="Could not get price")
            amount = size_usdt / price
            order = client.create_order(
                symbol=sym,
                type="market",
                side=side,
                amount=amount,
                params={"positionSide": "BOTH"},
            )
            order_id = order.get("id") or order.get("clientOrderId") or ""
            return OrderResult(success=True, order_id=str(order_id), message="Order placed")
        except Exception as e:
            return OrderResult(success=False, message=str(e))

    def place_tp_sl_orders(
        self,
        symbol: str,
        side: str,
        amount_base: float,
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
    ) -> OrderResult:
        """Place STOP_MARKET and TAKE_PROFIT_MARKET orders on Binance Futures."""
        if not take_profit_price and not stop_loss_price:
            return OrderResult(success=True, message="No TP/SL to set")
        close_side = "sell" if side == "buy" else "buy"
        try:
            client = self._get_client()
            client.load_markets()
            sym = ccxt_symbol(symbol)
            if stop_loss_price:
                client.create_order(
                    symbol=sym,
                    type="STOP_MARKET",
                    side=close_side,
                    amount=amount_base,
                    params={"stopPrice": stop_loss_price, "positionSide": "BOTH", "closePosition": "false"},
                )
            if take_profit_price:
                client.create_order(
                    symbol=sym,
                    type="TAKE_PROFIT_MARKET",
                    side=close_side,
                    amount=amount_base,
                    params={"stopPrice": take_profit_price, "positionSide": "BOTH", "closePosition": "false"},
                )
            return OrderResult(success=True, message="TP/SL orders placed")
        except Exception as e:
            return OrderResult(success=False, message=str(e))
