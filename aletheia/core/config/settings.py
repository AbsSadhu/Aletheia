from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ALETHEIA_",
        case_sensitive=False,
        extra="ignore",
    )

    env: str = "development"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = 8899
    # tauri://localhost covers macOS/Linux; http(s)://tauri.localhost covers
    # Windows and Android, where WebView2/webview map the custom protocol to
    # a virtual host instead of a custom scheme (see tauri::WebviewWindow's
    # `use_https_scheme` docs — defaults to plain http on Windows).
    allowed_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "tauri://localhost,http://tauri.localhost,https://tauri.localhost"
    )
    sqlite_path: Path = Field(default=Path("./data/aletheia.sqlite3"))
    duckdb_path: Path = Field(default=Path("./data/aletheia.duckdb"))
    data_dir: Path = Field(default=Path("./data"))
    reports_dir: Path = Field(default=Path("./data/reports"))
    exports_dir: Path = Field(default=Path("./data/exports"))
    log_dir: Path = Field(default=Path("./data/logs"))
    plugin_dir: Path = Field(default=Path("./plugins"))
    memory_dir: str = "~/.aletheia/memory"
    retention_days: int | None = Field(default=30)
    db_encryption_key: str | None = Field(default=None)
    api_keys: list[str] = Field(default_factory=list)
    # Gates the Sage agent (RunService.execute_run removes "sage" from the
    # active agent list when this is unset) — India-first product, so this
    # defaults on rather than requiring every user to discover and set an
    # env var just to see the platform's flagship tax-aware feature. Set to
    # None (ALETHEIA_TAX_JURISDICTION=) to disable tax-aware projections.
    tax_jurisdiction: str | None = Field(default="IN")
    # Per-node time budget. Collector fans out to several LLM-backed analysts that
    # queue on one local Ollama instance, so a mid-size local model on modest
    # hardware routinely needs well over 30s per node; 120s was reliable in testing.
    node_timeout_secs: int = Field(default=120, gt=0)
    enabled_agents: list[str] = Field(
        default_factory=lambda: [
            "collector",
            "oracle",
            "sentinel",
            "sage",
            "scribe",
            "sentiment",
            "fundamental",
            "options_flow",
            "critic",
        ]
    )

    # --- Portfolio Manager Constraints ---
    pm_max_position_size_pct: float = Field(default=20.0)
    pm_max_sector_concentration_pct: float = Field(default=30.0)
    pm_max_portfolio_var_pct: float = Field(default=15.0)
    pm_min_cash_reserve_pct: float = Field(default=5.0)
    # Paper/shadow sizing: lose at most this % of equity if the ATR stop is hit; with no
    # stop available, use a fixed slice of equity instead.
    risk_per_trade_pct: float = Field(default=1.0, gt=0, le=10)
    fallback_position_pct: float = Field(default=5.0, gt=0, le=100)
    paper_starting_cash: float = Field(default=1_000_000.0, gt=0)

    # --- LLM Configuration ---
    ollama_base_url: str = "http://127.0.0.1:11434"
    default_llm_provider: str = "ollama"
    default_llm_model: str = "mistral:7b"
    # Ordered priority list: first available provider wins
    llm_provider_priority: list[str] = Field(
        default_factory=lambda: ["ollama", "openai", "anthropic", "gemini"]
    )
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-pro"
    enable_cloud_llm_fallback: bool = False
    llm_max_retries: int = 2
    llm_retry_delay_secs: float = 1.0
    # Fail app startup if the configured LLM provider is unreachable. Off by
    # default so the app (and its non-LLM pages: runs list, portfolio,
    # backtest, hypotheses, factors) still boots without Ollama installed.
    require_llm_preflight: bool = False

    # --- Hypothesis auto-validation ---
    # Heuristic default, not a claim of statistical rigor — a widely-cited
    # "acceptable risk-adjusted return" cutoff, configurable per deployment.
    hypothesis_validation_sharpe_threshold: float = 1.0

    # --- Live Market Feed ---
    market_feed_enabled: bool = True
    market_feed_interval_secs: float = 15.0  # polling fallback cadence
    # With Angel One enabled the live feed streams over a WebSocket; each symbol is pushed to
    # the UI at most this often (seconds).
    market_feed_emit_interval_secs: float = Field(default=1.0, ge=0.2, le=60)
    angel_one_stream_enabled: bool = True
    # "angel_one" or "fyers": which broker supplies the per-second stream.
    live_feed_provider: str = "angel_one"  # "angel_one" | "fyers" | "bse_web" (free, unofficial)
    # bse_web polls BSE's public website API; never faster than 1 s, and rate-limited regardless.
    bse_web_poll_secs: float = Field(default=2.0, ge=1.0, le=60)
    # Free per-second crypto quotes from Binance's public stream (no account). Only connects
    # when the watchlist contains a crypto pair.
    crypto_stream_enabled: bool = True

    # --- Signal track record ---
    # How often to score past Oracle predictions against realised prices (0 disables).
    calibration_resolve_interval_secs: float = 21600.0

    # --- Rust Compute Engine Sidecar ---
    compute_engine_url: str = "http://127.0.0.1:18899"
    compute_engine_enabled: bool = False  # Set True when aletheia-engine binary is running

    execution_db_path: Path = Field(default=Path("./data/execution.sqlite3"))
    execution_mode: str = "simulation"
    execution_observation_days_required: int = 7

    # --- Live broker orders (real money) ---
    # Off by default. Even when on, an order must pass the execution gate (LIVE mode, not
    # paused, enough real paper-trading history), require API-key auth to be configured,
    # and stay inside these hard caps.
    live_trading_enabled: bool = False
    live_max_order_value: float = 25000.0  # INR per order
    live_max_order_qty: int = 500
    live_max_orders_per_day: int = 10

    enable_audit_logs: bool = True
    enable_desktop_bridge: bool = True
    yfinance_enabled: bool = True
    ccxt_enabled: bool = True
    # Angel One SmartAPI: free live NSE/BSE quotes. Credentials live in ConfigManager.
    angel_one_enabled: bool = False
    static_seed_enabled: bool = False  # hardcoded demo prices; offline dev only
    nse_enabled: bool = True
    rbi_enabled: bool = True

    # --- Observability ---
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "aletheia"

    cache_default_ttl_secs: float = 300.0
    cache_max_size: int = 256
    log_level: str = "INFO"

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.reports_dir,
            self.exports_dir,
            self.log_dir,
            self.plugin_dir,
            self.execution_db_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)

        import os

        if self.langsmith_tracing:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            if self.langsmith_api_key:
                os.environ["LANGCHAIN_API_KEY"] = self.langsmith_api_key
            os.environ["LANGCHAIN_PROJECT"] = self.langsmith_project

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
