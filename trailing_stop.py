"""
Trailing stop: background task that activates stop at break-even (or entry) once price moves
activation_pct in favor. Entries are stored in DB and processed periodically.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import List, Optional

from config import settings
from db import get_cursor
from exchanges.registry import get_exchange

logger = logging.getLogger(__name__)


def init_trailing_table() -> None:
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trailing_stop_pending (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                activation_pct REAL NOT NULL,
                size_usdt REAL NOT NULL,
                created_at REAL NOT NULL
            )
        """)


def add_trailing_pending(exchange: str, symbol: str, side: str, entry_price: float, activation_pct: float, size_usdt: float) -> None:
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO trailing_stop_pending (exchange, symbol, side, entry_price, activation_pct, size_usdt, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (exchange, symbol, side, entry_price, activation_pct, size_usdt, time.time()),
        )


def get_trailing_pending(limit: int = 100) -> List[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, exchange, symbol, side, entry_price, activation_pct, size_usdt
               FROM trailing_stop_pending ORDER BY id ASC LIMIT ?""",
            (limit,),
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def remove_trailing_pending(row_id: int) -> None:
    with get_cursor() as cur:
        cur.execute("DELETE FROM trailing_stop_pending WHERE id = ?", (row_id,))


async def trailing_stop_loop() -> None:
    """Periodically check pending trailing stops and place stop at entry when activation_pct reached."""
    init_trailing_table()
    interval = max(10, settings.trailing_stop_check_interval_seconds)
    while True:
        try:
            for row in get_trailing_pending():
                ex = get_exchange(row["exchange"])
                if not ex:
                    continue
                try:
                    price = ex.get_last_price(row["symbol"])
                    if price <= 0:
                        continue
                    entry = float(row["entry_price"])
                    side = row["side"]
                    activation_pct = float(row["activation_pct"])
                    # Long: activate when price >= entry * (1 + activation_pct/100)
                    # Short: activate when price <= entry * (1 - activation_pct/100)
                    if side == "buy":
                        threshold = entry * (1 + activation_pct / 100.0)
                        activated = price >= threshold
                        stop_price = entry
                    else:
                        threshold = entry * (1 - activation_pct / 100.0)
                        activated = price <= threshold
                        stop_price = entry
                    if not activated:
                        continue
                    # Place stop at entry (break-even)
                    amount_base = float(row["size_usdt"]) / price
                    result = ex.place_tp_sl_orders(
                        row["symbol"],
                        row["side"],
                        amount_base,
                        take_profit_price=None,
                        stop_loss_price=stop_price,
                    )
                    if result.success:
                        remove_trailing_pending(row["id"])
                        logger.info("Trailing stop activated", extra={"symbol": row["symbol"], "stop_price": stop_price})
                except Exception as e:
                    logger.warning("Trailing stop check failed", extra={"row_id": row["id"], "error": str(e)})
        except Exception as e:
            logger.warning("Trailing stop loop error", extra={"error": str(e)})
        await asyncio.sleep(interval)
