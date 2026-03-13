"""
Bybit connector (CCXT).
"""
from __future__ import annotations

from typing import Optional

import ccxt

from config import settings
from exchanges.base import ExchangeBase, OrderResult
from runtime_settings import get_use_testnet
from utils import ccxt_symbol


class BybitExchange(ExchangeBase):
    def __init__(self) -> None:
        self._client: Optional[ccxt.Exchange] = None

    def reset_client(self) -> None:
        self._client = None

    def _get_client(self) -> ccxt.Exchange:
        if self._client is None:
            self._client = ccxt.bybit({
                "apiKey": settings.bybit_api_key,
                "secret": settings.bybit_api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "linear"},
            })
            if get_use_testnet(self.name()):
                self._client.set_sandbox_mode(True)
        return self._client

    def name(self) -> str:
        return "bybit"

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
            if hasattr(self._get_client(), "private_get_v5_position_closed_pnl"):
                result = self._get_client().private_get_v5_position_closed_pnl({"category": "linear"})
                data = (result or {}).get("result", {}).get("list", [])
                from datetime import datetime, timezone
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                return sum(float(row.get("closedPnl", 0) or 0) for row in data if isinstance(row, dict) and str(row.get("updatedTime", ""))[:10] == today)
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
        except Exception:
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
                params={},
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
        """Set TP/SL on Bybit via position trading-stop API (v5)."""
        if not take_profit_price and not stop_loss_price:
            return OrderResult(success=True, message="No TP/SL to set")
        try:
            client = self._get_client()
            # Bybit v5 expects symbol without slash, e.g. BTCUSDT
            sym = symbol.replace("/", "").upper()
            params = {"category": "linear", "symbol": sym}
            if take_profit_price:
                params["takeProfit"] = str(take_profit_price)
            if stop_loss_price:
                params["stopLoss"] = str(stop_loss_price)
            client.private_post_v5_position_trading_stop(params)
            return OrderResult(success=True, message="TP/SL set")
        except Exception as e:
            return OrderResult(success=False, message=str(e))
