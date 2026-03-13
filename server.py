"""
FastAPI webhook server for TradingView alerts.
Idempotency, rate limit, risk (daily PnL, exposure, cooldown, spread), dry-run, metrics, health, status.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from config import settings
from db import (
    get_recent_orders,
    idempotency_seen,
    idempotency_set,
    init_db,
    risk_state_get,
    risk_state_set,
    save_order,
)
from exchanges.registry import get_exchange, get_all_exchanges, reset_all_clients
from runtime_settings import get_effective_use_testnet, set_use_testnet_override
from logging_config import setup_logging
from metrics import get_all as get_metrics, inc
from models import WebhookPayload, Side, ExchangeName
from rate_limit import get_rate_limiter
from ai.enhancer import enhancer_process
from ai.advisor import advisor_review
from ai.signals import generate_signal
from risk import run_risk_checks
from tpsl import amount_base_from_size_usdt, set_tp_sl_after_order
from retry import with_retry
from trailing_stop import add_trailing_pending, trailing_stop_loop

setup_logging(use_json=True)
logger = logging.getLogger(__name__)

COOLDOWN_KEY = "cooldown_until_ts"
_trailing_task: Optional[asyncio.Task] = None
_exchange_connected: dict[str, bool] = {}


def _ensure_exchange_connected() -> None:
    if _exchange_connected:
        return
    for name in get_all_exchanges():
        _exchange_connected.setdefault(name, True)


def _balance_for_exchange(exchange_name: str) -> Optional[float]:
    ex = get_exchange(exchange_name)
    if not ex:
        return None
    try:
        client = ex._get_client()
        bal = client.fetch_balance()
        usdt = (bal.get("USDT") or bal.get("usdt")) or {}
        total = usdt.get("total")
        if total is not None:
            return float(total)
        return None
    except Exception:
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _trailing_task
    init_db()
    logger.info("TradingView Webhook Bot starting", extra={"dry_run": settings.dry_run})
    _trailing_task = asyncio.create_task(trailing_stop_loop())
    yield
    if _trailing_task:
        _trailing_task.cancel()
        try:
            await _trailing_task
        except asyncio.CancelledError:
            pass
    logger.info("Shutting down")


app = FastAPI(title="TradingView Webhook Bot", lifespan=lifespan)

_DASHBOARD_PATH = Path(__file__).resolve().parent / "static" / "dashboard.html"


@app.get("/", response_class=RedirectResponse)
async def root():
    """Redirect root to dashboard."""
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/dashboard", response_class=FileResponse)
async def dashboard():
    """Professional dashboard: exchange status, metrics, daily PnL, recent orders."""
    if not _DASHBOARD_PATH.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(_DASHBOARD_PATH, media_type="text/html")


def _verify_secret(payload: WebhookPayload) -> bool:
    if not settings.webhook_secret:
        return not settings.require_webhook_secret
    return payload.secret == settings.webhook_secret


def _daily_pnl_for_exchange(exchange_name: str) -> float:
    ex = get_exchange(exchange_name)
    if not ex:
        return 0.0
    try:
        return ex.fetch_daily_pnl_usdt()
    except Exception:
        return 0.0


def _exposure_for_exchange(exchange_name: str) -> float:
    ex = get_exchange(exchange_name)
    if not ex:
        return 0.0
    try:
        return ex.fetch_total_exposure_usdt()
    except Exception:
        return 0.0


def _exposure_by_symbol(exchange_name: str) -> dict[str, float]:
    """Return symbol -> notional USDT for open positions."""
    ex = get_exchange(exchange_name)
    if not ex:
        return {}
    try:
        client = ex._get_client()
        positions = client.fetch_positions()
        out: dict[str, float] = {}
        for p in positions or []:
            sym = (p.get("symbol") or p.get("symbolId") or "").replace("/", "").upper()
            if not sym:
                continue
            notional = abs(float(p.get("notional", 0) or 0))
            if notional <= 0 and p.get("contracts"):
                notional = abs(float(p.get("contracts", 0) or 0) * float(p.get("markPrice") or p.get("last", 0) or 0))
            if sym not in out:
                out[sym] = 0.0
            out[sym] += notional
        return out
    except Exception:
        return {}


def _cooldown_active() -> bool:
    raw = risk_state_get(COOLDOWN_KEY)
    if not raw:
        return False
    try:
        return time.time() < float(raw)
    except Exception:
        return False


def _execute_payload(payload: WebhookPayload, request_key: str) -> tuple[int, dict]:
    """
    Run risk checks, optional advisor, then place order (or dry-run). Returns (status_code, content_dict).
    """
    _ensure_exchange_connected()
    if not _exchange_connected.get(payload.exchange.value, True):
        return 400, {"ok": False, "error": f"Exchange {payload.exchange.value} is disconnected"}
    exchange = get_exchange(payload.exchange.value)
    if not exchange:
        return 400, {"ok": False, "error": f"Exchange {payload.exchange.value} not enabled or configured"}

    daily_pnl = _daily_pnl_for_exchange(payload.exchange.value)
    total_exposure = _exposure_for_exchange(payload.exchange.value)
    _by_sym = _exposure_by_symbol(payload.exchange.value)
    exposure_by_symbol = lambda s: _by_sym.get(s, 0.0)
    cooldown_active = _cooldown_active()

    spread_bid, spread_ask, spread_mid = 0.0, 0.0, 0.0
    if settings.max_spread_pct > 0:
        spread_bid, spread_ask, spread_mid = exchange.get_orderbook(payload.symbol_upper(), 5)

    risk_result = run_risk_checks(
        payload,
        daily_pnl_usdt=daily_pnl,
        current_total_exposure_usdt=total_exposure,
        current_exposure_by_symbol=exposure_by_symbol,
        cooldown_active=cooldown_active,
        spread_bid=spread_bid,
        spread_ask=spread_ask,
        spread_mid=spread_mid,
    )
    if not risk_result.ok:
        inc("webhooks_risk_rejected")
        if "Daily loss limit" in risk_result.message and settings.cooldown_after_loss_minutes > 0:
            cooldown_until = time.time() + settings.cooldown_after_loss_minutes * 60
            risk_state_set(COOLDOWN_KEY, str(cooldown_until))
        return 400, {"ok": False, "error": risk_result.message}

    size_usdt = risk_result.adjusted_size_usdt or payload.size_usdt
    leverage = risk_result.adjusted_leverage

    current_price = exchange.get_last_price(payload.symbol_upper()) or 1.0
    advisor_result = advisor_review(payload, size_usdt, leverage, current_price)
    if not advisor_result.approve:
        return 400, {"ok": False, "error": f"Advisor rejected: {advisor_result.reason}"}
    if advisor_result.modify:
        if "size_usdt" in advisor_result.modify and advisor_result.modify["size_usdt"] is not None:
            size_usdt = min(float(advisor_result.modify["size_usdt"]), size_usdt)
        if "leverage" in advisor_result.modify and advisor_result.modify["leverage"] is not None:
            leverage = int(advisor_result.modify["leverage"])
        if "take_profit" in advisor_result.modify or "stop_loss" in advisor_result.modify:
            updates = {}
            if advisor_result.modify.get("take_profit") is not None:
                updates["take_profit"] = float(advisor_result.modify["take_profit"])
            if advisor_result.modify.get("stop_loss") is not None:
                updates["stop_loss"] = float(advisor_result.modify["stop_loss"])
            if updates:
                payload = payload.model_copy(update=updates)

    if settings.dry_run:
        inc("orders_dry_run")
        idempotency_set(request_key, settings.idempotency_ttl_seconds)
        return 200, {"ok": True, "dry_run": True, "size_usdt": size_usdt, "leverage": leverage}

    def _place():
        return exchange.place_from_payload(payload, size_usdt=size_usdt, leverage=leverage)

    try:
        order_result = with_retry(_place)
    except Exception as e:
        inc("orders_failed")
        inc("errors")
        save_order(request_key, payload.exchange.value, payload.symbol_upper(), payload.side.value, size_usdt, leverage, None, False, str(e))
        return 502, {"ok": False, "error": str(e)}

    if not order_result.success:
        inc("orders_failed")
        save_order(request_key, payload.exchange.value, payload.symbol_upper(), payload.side.value, size_usdt, leverage, order_result.order_id, False, order_result.message)
        return 502, {"ok": False, "error": order_result.message, "order_id": order_result.order_id}

    inc("orders_placed")
    idempotency_set(request_key, settings.idempotency_ttl_seconds)
    save_order(request_key, payload.exchange.value, payload.symbol_upper(), payload.side.value, size_usdt, leverage, order_result.order_id, True, order_result.message)

    if payload.take_profit or payload.stop_loss:
        try:
            price = exchange.get_last_price(payload.symbol_upper()) or 1.0
            amount_base = amount_base_from_size_usdt(size_usdt, price)
            tpsl_result = set_tp_sl_after_order(
                exchange, payload.symbol_upper(), payload.side.value, amount_base,
                payload.take_profit, payload.stop_loss,
            )
            if tpsl_result.success:
                inc("tpsl_placed")
            else:
                inc("tpsl_failed")
        except Exception:
            inc("tpsl_failed")

    if payload.trailing_stop and payload.trailing_activation_pct is not None:
        try:
            entry_price = exchange.get_last_price(payload.symbol_upper())
            if entry_price > 0:
                add_trailing_pending(
                    payload.exchange.value, payload.symbol_upper(), payload.side.value,
                    entry_price, payload.trailing_activation_pct, size_usdt,
                )
        except Exception:
            pass

    return 200, {
        "ok": True,
        "order_id": order_result.order_id,
        "message": order_result.message,
        "size_usdt": size_usdt,
        "leverage": leverage,
    }


@app.get("/health")
async def health():
    """Basic liveness."""
    return {"status": "ok"}


@app.get("/health/exchanges")
async def health_exchanges():
    """Per-exchange connectivity (fetch balance or minimal read)."""
    result = {}
    for name, ex in get_all_exchanges().items():
        try:
            client = ex._get_client()
            client.load_markets()
            client.fetch_balance()
            result[name] = "ok"
        except Exception as e:
            result[name] = f"error: {str(e)}"
    return {"exchanges": result}


@app.get("/exchanges/status")
async def exchanges_status():
    """Which exchanges are connected (allowed to receive orders)."""
    _ensure_exchange_connected()
    return dict(_exchange_connected)


@app.put("/exchanges/status")
async def exchanges_status_update(request: Request):
    """Set connect/disconnect per exchange. Body: { \"binance\": true, \"bybit\": false, ... }."""
    _ensure_exchange_connected()
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a map of exchange -> boolean")
    for name, connected in body.items():
        name = name.lower()
        if name in _exchange_connected:
            _exchange_connected[name] = bool(connected)
    return {"exchanges": dict(_exchange_connected)}


@app.get("/balance")
async def balance():
    """USDT balance per exchange (total from fetch_balance). None if unavailable."""
    _ensure_exchange_connected()
    result = {}
    for name in get_all_exchanges():
        if _exchange_connected.get(name, True):
            result[name] = _balance_for_exchange(name)
        else:
            result[name] = None
    return result


@app.get("/metrics")
async def metrics():
    """Observability: counters."""
    return get_metrics()


@app.get("/status")
async def status():
    """Admin: recent orders, daily PnL hint, risk state."""
    orders = get_recent_orders(limit=20)
    daily_pnl_by_exchange = {}
    for name in get_all_exchanges():
        daily_pnl_by_exchange[name] = _daily_pnl_for_exchange(name)
    cooldown = _cooldown_active()
    return {
        "recent_orders": orders,
        "daily_pnl_by_exchange": daily_pnl_by_exchange,
        "cooldown_active": cooldown,
        "dry_run": settings.dry_run,
        "use_testnet": get_effective_use_testnet(),
    }


@app.put("/settings/network")
async def settings_network(request: Request):
    """Switch all exchanges between live and testnet. Body: { "use_testnet": true | false }."""
    try:
        body = await request.json() or {}
    except Exception:
        body = {}
    use_testnet = body.get("use_testnet")
    if use_testnet is None:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Missing use_testnet (true or false)"})
    use_testnet = bool(use_testnet)
    set_use_testnet_override(use_testnet)
    reset_all_clients()
    return {"ok": True, "use_testnet": use_testnet}


@app.post("/webhook")
async def webhook(request: Request):
    """Receive TradingView webhook JSON and execute trade with risk checks."""
    inc("webhooks_received")
    client_ip = request.client.host if request.client else "unknown"

    try:
        body = await request.json()
    except Exception as e:
        inc("webhooks_validation_error")
        inc("errors")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    try:
        payload = WebhookPayload.model_validate(body)
    except Exception as e:
        inc("webhooks_validation_error")
        inc("errors")
        raise HTTPException(status_code=422, detail=f"Invalid payload: {e}")

    request_key = payload.idempotency_key()
    if idempotency_seen(request_key):
        inc("webhooks_duplicate")
        return JSONResponse(status_code=200, content={"ok": True, "duplicate": True, "message": "Already processed"})
    if not get_rate_limiter().allow(client_ip):
        inc("webhooks_rate_limited")
        return JSONResponse(status_code=429, content={"ok": False, "error": "Rate limit exceeded"})

    if not _verify_secret(payload):
        inc("webhooks_auth_failed")
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # AI enhancer: filter or adjust alert
    enhancer_result = enhancer_process(payload)
    if not enhancer_result.allow:
        return JSONResponse(status_code=400, content={"ok": False, "error": f"Enhancer rejected: {enhancer_result.reason}"})
    if enhancer_result.adjustments:
        allowed = {"size_usdt", "take_profit", "stop_loss", "leverage"}
        updates = {k: v for k, v in enhancer_result.adjustments.items() if k in allowed and v is not None}
        if updates:
            payload = payload.model_copy(update=updates)

    status_code, content = _execute_payload(payload, request_key)
    if status_code == 400 and "Risk check" in str(content.get("error", "")):
        logger.warning("Risk check failed", extra={"message": content.get("error"), "symbol": payload.symbol_upper()})
    elif content.get("ok") and content.get("order_id"):
        logger.info("Order placed", extra={"exchange": payload.exchange.value, "symbol": payload.symbol_upper(), "side": payload.side.value, "order_id": content["order_id"]})
    return JSONResponse(status_code=status_code, content=content)


@app.post("/signals/generate")
async def signals_generate(request: Request):
    """
    AI signal layer: generate buy/sell/hold from market context.
    Body: { "exchange": "binance", "symbol": "BTCUSDT", "default_size_usdt": 100, "execute": false, "secret": "optional" }
    If execute=true and signal is buy/sell, runs through same risk + execution as webhook.
    """
    try:
        body = await request.json() or {}
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    exchange_name = (body.get("exchange") or "binance").lower()
    symbol = (body.get("symbol") or "BTCUSDT").upper().strip()
    default_size = float(body.get("default_size_usdt") or 100)
    execute = bool(body.get("execute", False))
    secret = body.get("secret") or settings.webhook_secret

    if not settings.ai_signal_enabled:
        return JSONResponse(status_code=400, content={"ok": False, "error": "AI signal layer is disabled (AI_SIGNAL_ENABLED=false)"})

    signal = generate_signal(exchange_name, symbol, default_size_usdt=default_size)
    out = {"ok": True, "signal": signal}

    if signal.get("action") == "hold" or not signal.get("size_usdt"):
        return JSONResponse(status_code=200, content={**out, "executed": False})

    if not execute:
        return JSONResponse(status_code=200, content={**out, "executed": False})

    if settings.ai_signal_secret and secret != settings.ai_signal_secret:
        return JSONResponse(status_code=401, content={"ok": False, "error": "Invalid secret for signal execution"})

    try:
        payload = WebhookPayload(
            secret=secret,
            exchange=ExchangeName(exchange_name),
            symbol=symbol,
            side=Side(signal["action"]),
            size_usdt=float(signal["size_usdt"]),
            leverage=signal.get("leverage"),
            take_profit=signal.get("take_profit"),
            stop_loss=signal.get("stop_loss"),
            request_id=f"signal-{int(time.time())}-{symbol}",
        )
    except Exception as e:
        return JSONResponse(status_code=422, content={"ok": False, "error": str(e), "signal": signal})

    request_key = payload.idempotency_key()
    if idempotency_seen(request_key):
        return JSONResponse(status_code=200, content={**out, "executed": True, "duplicate": True})
    status_code, content = _execute_payload(payload, request_key)
    out["execution"] = content
    out["executed"] = status_code == 200 and content.get("ok") is True
    return JSONResponse(status_code=status_code, content=out)
