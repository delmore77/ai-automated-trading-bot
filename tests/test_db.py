"""Tests for DB idempotency and orders (use temp SQLite file)."""
import os
import tempfile
import pytest


@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr("config.settings.db_path", path)
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


def test_idempotency(use_temp_db):
    import db
    db.init_db()
    assert db.idempotency_seen("key1") is False
    db.idempotency_set("key1", 3600)
    assert db.idempotency_seen("key1") is True
    assert db.idempotency_seen("key2") is False


def test_save_and_get_orders(use_temp_db):
    import db
    db.init_db()
    db.save_order("req1", "binance", "BTCUSDT", "buy", 100.0, 5, "ord-1", True, "OK")
    orders = db.get_recent_orders(10)
    assert len(orders) == 1
    assert orders[0]["exchange"] == "binance"
    assert orders[0]["symbol"] == "BTCUSDT"
    assert orders[0]["success"] == 1
    assert orders[0]["order_id"] == "ord-1"


def test_risk_state(use_temp_db):
    import db
    db.init_db()
    assert db.risk_state_get("cooldown") is None
    db.risk_state_set("cooldown", "123.45")
    assert db.risk_state_get("cooldown") == "123.45"
