"""
Risk management: position size, leverage, daily loss, symbol allowlist,
per-symbol limits, total exposure, cooldown after loss, spread check.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from config import settings
from models import WebhookPayload


@dataclass
class RiskResult:
    ok: bool
    message: str
    adjusted_size_usdt: Optional[float] = None
    adjusted_leverage: Optional[int] = None


def check_symbol_allowed(symbol: str) -> RiskResult:
    allowed: List[str] = settings.allowed_symbols_list
    sym = symbol.upper()
    if not allowed:
        return RiskResult(True, "No symbol allowlist set")
    if sym in allowed:
        return RiskResult(True, "Symbol allowed")
    return RiskResult(False, f"Symbol {sym} not in allowlist: {allowed}")


def check_position_size(size_usdt: float) -> RiskResult:
    max_size = settings.max_position_size_usdt
    if size_usdt <= max_size:
        return RiskResult(True, "Position size OK", adjusted_size_usdt=size_usdt)
    return RiskResult(
        True,
        f"Capped size from {size_usdt} to {max_size} USDT",
        adjusted_size_usdt=max_size,
    )


def check_per_symbol_cap(symbol: str, size_usdt: float, current_exposure_by_symbol: Callable[[str], float]) -> RiskResult:
    """Reject or cap if symbol exposure would exceed max per symbol."""
    cap = settings.max_position_per_symbol_usdt
    if cap <= 0:
        return RiskResult(True, "No per-symbol cap", adjusted_size_usdt=size_usdt)
    current = current_exposure_by_symbol(symbol.upper())
    if current + size_usdt <= cap:
        return RiskResult(True, "Within per-symbol cap", adjusted_size_usdt=size_usdt)
    allowed_more = max(0.0, cap - current)
    if allowed_more <= 0:
        return RiskResult(False, f"Per-symbol cap reached for {symbol}: {current:.2f} >= {cap}")
    return RiskResult(
        True,
        f"Capped to {allowed_more:.2f} USDT (per-symbol cap)",
        adjusted_size_usdt=allowed_more,
    )


def check_total_exposure(
    new_notional_usdt: float,
    current_total_exposure_usdt: float,
) -> RiskResult:
    """Reject if total exposure would exceed max."""
    cap = settings.max_total_exposure_usdt
    if cap <= 0:
        return RiskResult(True, "No total exposure cap")
    total = current_total_exposure_usdt + new_notional_usdt
    if total <= cap:
        return RiskResult(True, "Within total exposure cap")
    return RiskResult(False, f"Total exposure cap would be exceeded: {total:.2f} > {cap}")


def check_leverage(leverage: Optional[int]) -> RiskResult:
    max_lev = settings.max_leverage
    if leverage is None:
        return RiskResult(True, "No leverage specified", adjusted_leverage=None)
    if leverage <= max_lev:
        return RiskResult(True, "Leverage OK", adjusted_leverage=leverage)
    return RiskResult(
        True,
        f"Capped leverage from {leverage} to {max_lev}",
        adjusted_leverage=max_lev,
    )


def check_daily_loss(daily_pnl_usdt: float) -> RiskResult:
    """Call with current day's realized PnL (negative = loss)."""
    if daily_pnl_usdt >= 0:
        return RiskResult(True, "Daily PnL OK")
    loss = abs(daily_pnl_usdt)
    if loss < settings.max_daily_loss_usdt:
        return RiskResult(True, "Within daily loss limit")
    return RiskResult(False, f"Daily loss limit reached: {loss:.2f} >= {settings.max_daily_loss_usdt}")


def check_cooldown(cooldown_active: bool) -> RiskResult:
    """Block if we are in cooldown after hitting daily loss limit."""
    if not cooldown_active:
        return RiskResult(True, "No cooldown")
    return RiskResult(False, f"Cooldown active: wait {settings.cooldown_after_loss_minutes} min after daily loss limit")


def check_spread(bid: float, ask: float, mid: float, max_spread_pct: float) -> RiskResult:
    """Reject if spread (ask-bid)/mid > max_spread_pct. Pass 0 for mid to skip."""
    if max_spread_pct <= 0 or mid <= 0:
        return RiskResult(True, "Spread check disabled")
    if bid <= 0 or ask <= 0:
        return RiskResult(True, "No orderbook data")
    spread_pct = 100.0 * (ask - bid) / mid
    if spread_pct <= max_spread_pct:
        return RiskResult(True, "Spread OK")
    return RiskResult(False, f"Spread too wide: {spread_pct:.2f}% > {max_spread_pct}%")


def run_risk_checks(
    payload: WebhookPayload,
    daily_pnl_usdt: float = 0.0,
    current_total_exposure_usdt: float = 0.0,
    current_exposure_by_symbol: Optional[Callable[[str], float]] = None,
    cooldown_active: bool = False,
    spread_bid: float = 0.0,
    spread_ask: float = 0.0,
    spread_mid: float = 0.0,
) -> RiskResult:
    """Run all risk checks. Returns first failure or success with any adjusted values."""
    r = check_symbol_allowed(payload.symbol_upper())
    if not r.ok:
        return r

    r = check_position_size(payload.size_usdt)
    if not r.ok:
        return r
    size_usdt = r.adjusted_size_usdt or payload.size_usdt

    if current_exposure_by_symbol:
        r = check_per_symbol_cap(payload.symbol_upper(), size_usdt, current_exposure_by_symbol)
        if not r.ok:
            return r
        size_usdt = r.adjusted_size_usdt or size_usdt

    r = check_total_exposure(size_usdt, current_total_exposure_usdt)
    if not r.ok:
        return r

    r_lev = check_leverage(payload.leverage)
    if not r_lev.ok:
        return r_lev
    leverage = r_lev.adjusted_leverage if r_lev.adjusted_leverage is not None else payload.leverage

    r = check_daily_loss(daily_pnl_usdt)
    if not r.ok:
        return r

    r = check_cooldown(cooldown_active)
    if not r.ok:
        return r

    r = check_spread(spread_bid, spread_ask, spread_mid, settings.max_spread_pct)
    if not r.ok:
        return r

    return RiskResult(
        True,
        "All risk checks passed",
        adjusted_size_usdt=size_usdt,
        adjusted_leverage=leverage,
    )
