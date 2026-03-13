"""
OKX connector (CCXT).
"""
from __future__ import annotations

from typing import Optional

import ccxt

from config import settings
from exchanges.base import ExchangeBase, OrderResult
from runtime_settings import get_use_testnet
from utils import ccxt_symbol


class OKXExchange(ExchangeBase):
    def __init__(self) -> None:
        self._client: Optional[ccxt.Exchange] = None

    def reset_client(self) -> None:
        self._client = None

    def _get_client(self) -> ccxt.Exchange:
        if self._client is None:
            self._client = ccxt.okx({
                "apiKey": settings.okx_api_key,
                "secret": settings.okx_api_secret,
                "password": settings.okx_passphrase,
                "enableRateLimit": True,
                "options": {"defaultType": "swap"},
            })
            if get_use_testnet(self.name()):
                self._client.set_sandbox_mode(True)
        return self._client

    def name(self) -> str:
        return "okx"

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
            # OKX: fetch ledger for realized PnL today
            client = self._get_client()
            from datetime import datetime, timezone
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            ledger = getattr(client, "private_get_account_bills_archive", None)
            if ledger:
                result = ledger({"instType": "SWAP"})
                bills = (result or {}).get("data", [])
                total = 0.0
                for b in bills:
                    ts = int(b.get("ts", 0) or 0) / 1000
                    if ts >= today_start.timestamp():
                        total += float(b.get("pnl", 0) or b.get("balChg", 0) or 0)
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
        """Place TP/SL as algo orders (OKX conditional orders)."""
        if not take_profit_price and not stop_loss_price:
            return OrderResult(success=True, message="No TP/SL to set")
        close_side = "sell" if side == "buy" else "buy"
        try:
            client = self._get_client()
            client.load_markets()
            sym = ccxt_symbol(symbol)
            # OKX: order with slTriggerPx and tpTriggerPx in params
            params = {"reduceOnly": True}
            if stop_loss_price:
                params["slTriggerPx"] = str(stop_loss_price)
                params["slOrdPx"] = "-1"  # market
            if take_profit_price:
                params["tpTriggerPx"] = str(take_profit_price)
                params["tpOrdPx"] = "-1"  # market
            if params.get("slTriggerPx") or params.get("tpTriggerPx"):
                client.create_order(sym, "market", close_side, amount_base, None, params)
            return OrderResult(success=True, message="TP/SL set")
        except Exception as e:
            return OrderResult(success=False, message=str(e))
