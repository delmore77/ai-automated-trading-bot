"""Tests for risk checks."""
import pytest

# Import after conftest or rely on default .env; override via monkeypatch in tests if needed
from risk import (
    check_symbol_allowed,
    check_position_size,
    check_leverage,
    check_daily_loss,
    check_cooldown,
    check_spread,
    check_total_exposure,
    check_per_symbol_cap,
)


def test_check_symbol_allowed():
    r = check_symbol_allowed("BTCUSDT")
    assert r.ok is True
    r = check_symbol_allowed("btcusdt")
    assert r.ok is True
    r = check_symbol_allowed("XRPUSDT")
    assert r.ok is False
    assert "allowlist" in r.message


def test_check_position_size():
    r = check_position_size(500)
    assert r.ok is True
    assert r.adjusted_size_usdt == 500
    r = check_position_size(2000)
    assert r.ok is True
    assert r.adjusted_size_usdt == 1000


def test_check_leverage():
    r = check_leverage(None)
    assert r.ok is True
    assert r.adjusted_leverage is None
    r = check_leverage(5)
    assert r.ok is True
    assert r.adjusted_leverage == 5
    r = check_leverage(20)
    assert r.ok is True
    assert r.adjusted_leverage == 10


def test_check_daily_loss():
    r = check_daily_loss(0)
    assert r.ok is True
    r = check_daily_loss(-100)
    assert r.ok is True
    r = check_daily_loss(-600)
    assert r.ok is False
    assert "Daily loss limit" in r.message


def test_check_cooldown():
    r = check_cooldown(False)
    assert r.ok is True
    r = check_cooldown(True)
    assert r.ok is False


def test_check_spread():
    r = check_spread(100, 101, 100.5, 0)
    assert r.ok is True
    r = check_spread(100, 105, 102.5, 2)
    assert r.ok is False
    r = check_spread(100, 101, 100.5, 2)
    assert r.ok is True


def test_check_total_exposure():
    # With MAX_TOTAL_EXPOSURE_USDT=0 (no cap), any exposure is ok
    r = check_total_exposure(100, 0)
    assert r.ok is True
    r = check_total_exposure(1000, 0)
    assert r.ok is True


def test_check_per_symbol_cap():
    # With max_position_per_symbol_usdt=0, cap check is skipped (returns ok, adjusted_size_usdt=size_usdt)
    def no_exposure(s):
        return 0.0
    r = check_per_symbol_cap("BTCUSDT", 100, no_exposure)
    assert r.ok is True
    assert r.adjusted_size_usdt == 100
