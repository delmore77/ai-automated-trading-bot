"""
Shared utilities.
"""


def ccxt_symbol(symbol: str) -> str:
    """Convert TradingView-style symbol (BTCUSDT) to CCXT format (BTC/USDT) if needed."""
    s = symbol.upper().strip()
    if "/" in s:
        return s
    if s.endswith("USDT"):
        return s[:-4] + "/USDT"
    return s
