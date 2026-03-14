# TradingView Webhook Bot

Automated execution of TradingView alerts on **Binance**, **Bybit**, **OKX**, and **Hyperliquid** with configurable risk limits, take-profit/stop-loss, and optional AI review. Strategy logic remains in TradingView; the bot executes orders safely via a single webhook endpoint.

[![Telegram](https://img.shields.io/badge/Telegram-Contact-blue?style=for-the-badge&logo=telegram)](https://t.me/galileo0000)

I have extensive experience building and operating automated trading systems in live markets. For help tailoring this bot to your strategy or improving your setup, you can reach me on Telegram at any time.

---

## Overview

- **Single webhook** — One TradingView alert URL; choose exchange, symbol, size, and TP/SL in the alert message.
- **Risk controls** — Max position size, daily loss limit, symbol allowlist, per-symbol and total exposure caps, leverage cap, cooldown after loss, optional spread filter.
- **Execution** — Market order with optional TP/SL and trailing stop on all supported exchanges. Idempotency and rate limiting to avoid duplicate or abusive requests.
- **Optional AI** — LLM can filter or adjust alerts (enhancer), approve or modify orders before execution (advisor), or generate buy/sell/hold signals with optional execution.

Performance outcomes depend on your strategy, market conditions, and risk settings. The bot does not select when or what to trade; it executes your signals under the limits you configure.

---

## Dashboard

The web dashboard (`GET /dashboard`) displays exchange connectivity, USDT balance, daily PnL, recent orders, metrics, and a Live/Testnet toggle. Data refreshes every 30 seconds.

### Screenshots

| | |
|---|---|
| ![Screenshot 0](images/Screenshot_0.png) | ![Screenshot 1](images/Screenshot_1.png) |
| *Screenshot 0* | *Screenshot 1* |
| ![Screenshot 2](images/Screenshot_2.png) | ![Screenshot 3](images/Screenshot_3.png) |
| *Screenshot 2* | *Screenshot 3* |

Place your assets in `images/Screenshot_0.png` through `Screenshot_3.png`.

### Demo video

<video src="videos/video_0.mp4" controls width="640" style="max-width:100%; border-radius:8px; border:1px solid #1e2128;"></video>

[Open or download](videos/video_0.mp4) if the player is not supported. Place your file at `videos/video_0.mp4`.

---

## Execution pipeline

For each webhook (or executed AI signal), the bot runs in order:

1. **Authentication and idempotency** — Validate webhook secret when required. If `request_id` was already processed within the idempotency window, return duplicate and do not trade.
2. **AI enhancer (optional)** — If enabled, the LLM may allow, reject, or adjust the payload (e.g. size, stop-loss) before risk checks. Rejected alerts do not reach the exchange.
3. **Risk checks** — Apply symbol allowlist, position size cap, per-symbol cap, total exposure cap, leverage cap, daily loss limit, cooldown, and optional spread check. Rejects abort the order; caps reduce size/leverage and execution continues with adjusted values.
4. **LLM advisor (optional)** — If enabled, the LLM may approve, reject, or modify size/leverage/TP/SL. Rejected orders are not sent.
5. **Place order** — Send the market order to the selected exchange with retries and backoff on transient errors.
6. **TP/SL** — If the order fills and take-profit and/or stop-loss are provided, place the corresponding TP/SL orders on the exchange.
7. **Trailing stop (optional)** — If configured, record a pending trailing stop; a background loop moves the stop toward break-even and beyond as price moves in your favor.

Strategy (what to trade and when) stays in your TradingView alerts or AI signals; the bot enforces risk, optionally consults the LLM, sends one market order, then attaches TP/SL and optional trailing stop.

### Risk checks (order of application)

| # | Check | Behavior |
|---|--------|----------|
| 1 | Symbol allowlist (`ALLOWED_SYMBOLS`) | Reject if symbol not in list; empty list allows all. |
| 2 | Max position size (`MAX_POSITION_SIZE_USDT`) | Cap size to this maximum; do not reject on size alone. |
| 3 | Per-symbol cap (`MAX_POSITION_PER_SYMBOL_USDT`) | Reject or cap so current exposure plus new size does not exceed cap. |
| 4 | Total exposure cap (`MAX_TOTAL_EXPOSURE_USDT`) | Reject if total notional would exceed cap. |
| 5 | Leverage (`MAX_LEVERAGE`) | Cap leverage; do not reject on leverage alone. |
| 6 | Daily loss limit (`MAX_DAILY_LOSS_USDT`) | Reject if today’s realized PnL has reached the loss limit. |
| 7 | Cooldown | Reject if cooldown is active (e.g. after daily loss limit for `COOLDOWN_AFTER_LOSS_MINUTES`). |
| 8 | Spread (`MAX_SPREAD_PCT`) | Reject if (ask−bid)/mid exceeds this; set to 0 to disable. |

No order is sent until all checks pass (with caps applied where applicable).

### Live vs testnet

The dashboard Live/Testnet switch applies to all configured exchanges and clears cached API clients. In Live mode the bot uses each exchange’s mainnet API; in Testnet it uses the exchange’s testnet/sandbox. Use testnet and test funds before going live.

---

## Features

| Area | Capabilities |
|------|--------------|
| Exchanges | Binance, Bybit, OKX, Hyperliquid (futures) |
| Risk | Max position, max leverage, daily loss cap, symbol allowlist, per-symbol and total exposure caps, cooldown, max spread |
| Orders | Take-profit and stop-loss on all exchanges; optional trailing stop with break-even activation |
| Safety | Webhook secret, rate limiting, idempotency, retries with backoff |
| Observability | JSON logging, `/metrics`, `/health`, `/status`, dashboard |
| Testing | Dry-run mode; testnet support per exchange |
| AI (optional) | LLM advisor, alert enhancer, AI signal generation with optional execution |

---

## Optional AI layer

- **LLM advisor** — Approve, reject, or adjust (size, TP/SL, leverage) before each order.
- **AI enhancer** — Filter or adjust TradingView alerts before risk checks (e.g. reduce size, add stop-loss).
- **AI signals** — `POST /signals/generate` returns buy/sell/hold from market context; optional `execute=true` runs the same risk and execution pipeline as the webhook.

---

## Quick start

**Requirements:** Python 3.10+

1. **Install**
   ```bash
   cd ai-automated-trading-bot
   pip install -r requirements.txt
   ```

2. **Configure**
   - Copy `.env.example` to `.env`.
   - Set API keys for the exchanges you use.
   - Set `WEBHOOK_SECRET` and `REQUIRE_WEBHOOK_SECRET=true` for production.
   - Adjust risk limits (see [Environment variables](#environment-variables)).

3. **Run**
   ```bash
   python main.py
   ```
   Server listens on `http://0.0.0.0:8000`. Webhook: `POST /webhook`.

4. **TradingView alert** — POST JSON to `/webhook`. Required: `secret`, `exchange`, `symbol`, `side`, `size_usdt`. Optional: `leverage`, `take_profit`, `stop_loss`, `trailing_stop`, `trailing_activation_pct`, `request_id`.

   Example:
   ```json
   {
     "secret": "your_webhook_secret_here",
     "exchange": "binance",
     "symbol": "BTCUSDT",
     "side": "buy",
     "size_usdt": 100,
     "leverage": 5,
     "take_profit": 50000,
     "stop_loss": 45000,
     "trailing_stop": true,
     "trailing_activation_pct": 2,
     "request_id": "alert-123"
   }
   ```
   Use `request_id` (e.g. alert id) to prevent duplicate orders. If `REQUIRE_WEBHOOK_SECRET` is false, you may send `"secret": ""`.

---

## Project structure

| Path | Purpose |
|------|---------|
| `main.py` | Entrypoint; runs uvicorn with `server:app`. |
| `server.py` | FastAPI app: webhook, signals, health, metrics, status, dashboard, balance, exchange status, network switch. |
| `config.py` | Pydantic settings from environment (`.env`). |
| `models.py` | `WebhookPayload`, `Side`, `ExchangeName`. |
| `risk.py` | Risk checks (allowlist, size, per-symbol/total exposure, leverage, daily loss, cooldown, spread). |
| `db.py` | SQLite: idempotency, order history, risk state. |
| `tpsl.py` | Take-profit/stop-loss placement after order. |
| `trailing_stop.py` | Trailing-stop state and background loop. |
| `exchanges/` | `base.py`, `registry.py`, `binance.py`, `bybit.py`, `okx.py`, `hyperliquid.py`. |
| `ai/` | `llm.py` (OpenAI-compatible), `enhancer.py`, `advisor.py`, `signals.py`. |
| `static/dashboard.html` | Single-page dashboard (Tailwind, Lightweight Charts). |

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Redirects to `/dashboard`. |
| GET | `/dashboard` | Dashboard: exchange status, balance, daily PnL, recent orders, metrics, Live/Testnet. Auto-refresh 30s. |
| POST | `/webhook` | TradingView webhook; optional enhancer and advisor, then risk and execution. |
| POST | `/signals/generate` | AI signal (buy/sell/hold); optional `execute=true` for same pipeline as webhook. |
| GET | `/health` | Liveness. |
| GET | `/health/exchanges` | Per-exchange connectivity check. |
| GET | `/exchanges/status` | Which exchanges are connected (allowed to receive orders). |
| PUT | `/exchanges/status` | Set connect/disconnect per exchange. Body: `{"binance": true, "bybit": false, ...}`. |
| GET | `/balance` | USDT balance per exchange; `null` if disconnected or unavailable. |
| GET | `/metrics` | Counters: webhooks, orders, rejections, tpsl, errors. |
| GET | `/status` | Recent orders, daily PnL by exchange, cooldown, dry_run, use_testnet. |
| PUT | `/settings/network` | Switch all exchanges between live and testnet. Body: `{"use_testnet": true \| false}`. Clears cached clients. |

---

## Environment variables

Copy `.env.example` to `.env` and set values as needed. Only variables for the features you use are required.

| Variable | Description |
|----------|-------------|
| **Webhook** | |
| `WEBHOOK_SECRET` | Must match `secret` in webhook body when `REQUIRE_WEBHOOK_SECRET=true`. Empty allows any secret when requirement is false. |
| `REQUIRE_WEBHOOK_SECRET` | Reject wrong or missing secret (default: true). If true and `WEBHOOK_SECRET` is empty, all requests pass. |
| `RATE_LIMIT_PER_MINUTE` | Max webhook requests per minute per client IP (default: 30). |
| `IDEMPOTENCY_TTL_SECONDS` | How long to remember `request_id` (default: 86400). |
| **Exchanges** | |
| `BINANCE_API_KEY`, `BINANCE_API_SECRET` | Binance futures. Empty to disable. |
| `BINANCE_TESTNET` | Use Binance testnet (default: false). Overridden by dashboard when set. |
| `BYBIT_API_KEY`, `BYBIT_API_SECRET` | Bybit. Empty to disable. |
| `BYBIT_TESTNET` | Bybit testnet (default: false). |
| `OKX_API_KEY`, `OKX_API_SECRET`, `OKX_PASSPHRASE` | OKX. Empty to disable. |
| `OKX_SANDBOX` | OKX sandbox (default: false). |
| `HYPERLIQUID_PRIVATE_KEY` | Hyperliquid; required. `HYPERLIQUID_WALLET_ADDRESS` optional. |
| `HYPERLIQUID_TESTNET` | Hyperliquid testnet (default: false). |
| **Risk** | |
| `MAX_POSITION_SIZE_USDT` | Cap single order size (USDT). |
| `MAX_LEVERAGE` | Cap leverage; never reject on leverage alone. |
| `MAX_DAILY_LOSS_USDT` | Reject new orders when today’s realized loss reaches this. |
| `ALLOWED_SYMBOLS` | Comma-separated allowlist (e.g. `BTCUSDT,ETHUSDT`). Empty = allow all. |
| `MAX_POSITION_PER_SYMBOL_USDT` | Per-symbol exposure cap (0 = use global max only). |
| `MAX_TOTAL_EXPOSURE_USDT` | Total open notional cap (0 = disabled). |
| `COOLDOWN_AFTER_LOSS_MINUTES` | Block new orders for N minutes after daily loss limit. |
| `MAX_SPREAD_PCT` | Reject if (ask−bid)/mid > this (0 = disabled). |
| **Execution** | |
| `DRY_RUN` | If true, no real orders are sent. |
| `ORDER_RETRIES` | Retries for place_market_order (default: 2). |
| `ORDER_RETRY_DELAY_SECONDS` | Delay between retries (default: 1.0). |
| **Trailing stop** | |
| `TRAILING_STOP_CHECK_INTERVAL_SECONDS` | Trailing-stop loop interval (default: 30). |
| **DB & server** | |
| `DB_PATH` | SQLite path for idempotency, orders, risk state (default: webhook_bot.db). |
| `HOST` | Bind address (default: 0.0.0.0). |
| `PORT` | Server port (default: 8000). |
| **AI / LLM** | |
| `OPENAI_API_KEY` | Required for advisor, enhancer, and signals. |
| `OPENAI_BASE_URL` | Optional (e.g. Azure or local proxy). |
| `LLM_MODEL` | Model name (default: gpt-4o-mini). |
| `LLM_ADVISOR_ENABLED` | LLM approve/reject/modify before each order (default: false). |
| `AI_ENHANCER_ENABLED` | LLM filter/adjust TradingView alerts (default: false). |
| `AI_SIGNAL_ENABLED` | Enable `POST /signals/generate` (default: false). |
| `AI_SIGNAL_SECRET` | If set, body must include matching `secret` when calling with `execute=true`. |

---

## Tests

```bash
pytest tests/ -v
```

---

## Contact

For setup help, strategy tuning, or customisation, contact me on Telegram:

[![Telegram](https://img.shields.io/badge/Telegram-Contact-blue?style=for-the-badge&logo=telegram)](https://t.me/galileo0000)

---

## Disclaimer

This software can execute real trades. Use testnets and test funds first. You are responsible for your own risk management and for complying with each exchange’s terms of service.
