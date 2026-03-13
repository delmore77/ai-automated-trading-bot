"""Tests for webhook payload and idempotency key."""
import pytest
from pydantic import ValidationError

from models import WebhookPayload, Side, ExchangeName


def test_webhook_payload_minimal():
    p = WebhookPayload(
        secret="x",
        exchange="binance",
        symbol="BTCUSDT",
        side="buy",
        size_usdt=100,
    )
    assert p.symbol_upper() == "BTCUSDT"
    assert p.side == Side.BUY
    assert p.exchange == ExchangeName.BINANCE
    assert p.leverage is None
    assert p.request_id is None


def test_webhook_payload_with_request_id():
    p = WebhookPayload(
        secret="x",
        exchange="bybit",
        symbol="ETHUSDT",
        side="sell",
        size_usdt=50,
        request_id="alert-123",
    )
    assert p.idempotency_key() == "alert-123"


def test_webhook_payload_idempotency_key_without_request_id():
    p = WebhookPayload(
        secret="x",
        exchange="binance",
        symbol="BTCUSDT",
        side="buy",
        size_usdt=100,
    )
    key = p.idempotency_key()
    assert isinstance(key, str)
    assert len(key) == 32
    # Same payload -> same key
    p2 = WebhookPayload(secret="x", exchange="binance", symbol="BTCUSDT", side="buy", size_usdt=100)
    assert p2.idempotency_key() == key


def test_webhook_payload_invalid():
    with pytest.raises(ValidationError):
        WebhookPayload(
            secret="x",
            exchange="binance",
            symbol="BTCUSDT",
            side="buy",
            size_usdt=-1,
        )
    with pytest.raises(ValidationError):
        WebhookPayload(
            secret="x",
            exchange="invalid",
            symbol="BTCUSDT",
            side="buy",
            size_usdt=100,
        )
