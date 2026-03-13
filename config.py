"""
Configuration for TradingView Webhook Bot.
Loads from environment variables (use .env for local dev).
"""
from __future__ import annotations

from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Webhook
    webhook_secret: str = ""
    require_webhook_secret: bool = True  # If True and secret is set, reject missing/wrong secret
    rate_limit_per_minute: int = 30  # Max webhook requests per minute per client
    idempotency_ttl_seconds: int = 86400  # 24h - remember request_id for this long

    # Binance
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = False

    # Bybit
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    bybit_testnet: bool = False

    # OKX
    okx_api_key: str = ""
    okx_api_secret: str = ""
    okx_passphrase: str = ""
    okx_sandbox: bool = False

    # Hyperliquid (private key required; wallet address optional)
    hyperliquid_private_key: str = ""
    hyperliquid_wallet_address: str = ""
    hyperliquid_testnet: bool = False

    # Risk
    max_position_size_usdt: float = 1000.0
    max_leverage: int = 10
    max_daily_loss_usdt: float = 500.0
    allowed_symbols: str = "BTCUSDT,ETHUSDT"
    max_position_per_symbol_usdt: float = 0.0  # 0 = use max_position_size_usdt for all
    max_total_exposure_usdt: float = 0.0  # 0 = no cap on total notional
    cooldown_after_loss_minutes: int = 60  # Block new orders for N min after daily loss limit hit
    max_spread_pct: float = 0.0  # 0 = disabled; reject if (ask-bid)/mid > this

    # Execution
    dry_run: bool = False  # Log only, do not send orders
    order_retries: int = 2  # Retries with backoff for place_market_order
    order_retry_delay_seconds: float = 1.0

    # Trailing stop
    trailing_stop_check_interval_seconds: int = 30

    # DB & state
    db_path: str = "webhook_bot.db"

    # AI / LLM
    openai_api_key: str = ""  # Or set OPENAI_BASE_URL for compatible APIs (e.g. Azure, local)
    openai_base_url: str = ""  # Optional; default OpenAI
    llm_model: str = "gpt-4o-mini"  # Model for advisor and enhancer
    llm_advisor_enabled: bool = False  # Require LLM approval before placing order
    ai_enhancer_enabled: bool = False  # Filter or adjust TradingView alerts via LLM
    ai_signal_enabled: bool = False  # Allow /signals/generate to produce executable signals
    ai_signal_secret: str = ""  # Optional secret for POST /signals/generate (and execute)

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def allowed_symbols_list(self) -> List[str]:
        return [s.strip().upper() for s in self.allowed_symbols.split(",") if s.strip()]

    def exchange_enabled(self, name: str) -> bool:
        if name == "binance":
            return bool(self.binance_api_key and self.binance_api_secret)
        if name == "bybit":
            return bool(self.bybit_api_key and self.bybit_api_secret)
        if name == "okx":
            return bool(self.okx_api_key and self.okx_api_secret and self.okx_passphrase)
        if name == "hyperliquid":
            return bool(self.hyperliquid_private_key.strip())
        return False


settings = Settings()
