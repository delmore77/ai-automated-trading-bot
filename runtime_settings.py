"""
Runtime settings that can change without restart (e.g. live vs testnet).
"""
from __future__ import annotations

from typing import Optional

from config import settings

_use_testnet_override: Optional[bool] = None


def get_use_testnet(exchange_name: str) -> bool:
    """Return whether to use testnet for this exchange. Override wins over env."""
    if _use_testnet_override is not None:
        return _use_testnet_override
    name = exchange_name.lower()
    if name == "binance":
        return settings.binance_testnet
    if name == "bybit":
        return settings.bybit_testnet
    if name == "okx":
        return settings.okx_sandbox
    if name == "hyperliquid":
        return settings.hyperliquid_testnet
    return False


def set_use_testnet_override(value: Optional[bool]) -> None:
    """Set global testnet override. None = use env per exchange."""
    global _use_testnet_override
    _use_testnet_override = value


def get_use_testnet_override() -> Optional[bool]:
    """Current override (None = use env)."""
    return _use_testnet_override


def get_effective_use_testnet() -> bool:
    """Single effective value for UI: testnet on if override or any exchange uses testnet."""
    if _use_testnet_override is not None:
        return _use_testnet_override
    for name in ("binance", "bybit", "okx", "hyperliquid"):
        if get_use_testnet(name):
            return True
    return False
