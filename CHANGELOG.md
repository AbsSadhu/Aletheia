# Changelog

All notable changes to Aletheia are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). While the version is `0.x`, anything may change
between releases.

## [Unreleased]

### Added
- **BSE website quote source** (`live_feed_provider=bse_web`, free, no account, UNOFFICIAL): polls BSE's public
  API every ~2 s with an 8 requests/s overall cap and exponential backoff on 403/429/5xx. Each quote carries
  BSE's own 'as on' time, so Live Market shows when the exchange's data trails your clock instead of calling
  it live. Rows are labelled "BSE price", and the feed is flagged unofficial on screen. `scripts/bse_check.py`
  measures its real-time-ness on a trading day; `docs/FREE_LIVE_DATA.md` records which free sources were
  tested and why most fail (NSE blocks scripts; `maanavshah/stock-market-india` targets a dead host).
- **Free per-second crypto feed** from Binance's public WebSocket (no account or key): subscribe/unsubscribe
  follows the watchlist live, falls back to Binance's market-data host, reconnects on drops and silence,
  and runs alongside whichever stock feed is active. Live Market now says which parts are live and which are
  delayed, and treats a quiet crypto row as stale at any hour (crypto trades 24/7). `scripts/crypto_check.py`
  verifies it. Measured against the live service: about 1 update per second, ~0.08 s from Binance's event time to
  arrival, prices within 0.15% of Yahoo.
- **Fyers per-second feed** as an alternative to Angel One (`live_feed_provider`). It runs Fyers' official
  `fyers-apiv3` SDK in an isolated virtualenv helper process (`aletheia/extensions/data/fyers_bridge.py`),
  created by `scripts/fyers_setup.py`, because the SDK's dependencies (boto3, AWS packages, older `requests`
  and `aiohttp`) break the main environment. Daily OAuth login via Settings (`/brokers/fyers/*`), expiry
  handling at 06:30 IST, `scripts/fyers_check.py`, and `docs/FYERS_SETUP.md`.
- **Per-second live feed:** Angel One SmartAPI WebSocket client (reconnect with backoff, heartbeat,
  token/headers per the official SDK, paise-to-rupee scaling checked against a REST quote), a saved
  watchlist (`GET/PUT /watchlist`), feed health (`/marketdata/feed-status`), a quote snapshot for late
  joiners, market-hours awareness, and a **Live Market** page with flashing prices, source/age per row,
  and explicit closed/delayed/stale/unverified states.
- `docs/ANGEL_ONE_SETUP.md` and `scripts/angel_check.py` (step-by-step verification of an Angel One setup);
  the config wizard now asks for Angel One credentials.
- **Live data:** Angel One SmartAPI provider (free, official) as the first quote source when
  `ALETHEIA_ANGEL_ONE_ENABLED=true`. Static demo prices are opt-in and last.
- **Zerodha:** OAuth login (`/brokers/zerodha/*`), real holdings sync, and a guarded live-order
  endpoint (`/execution/live-order`) with six independent checks, a daily cap and an order ledger.
  Off by default; tested against mocked HTTP only.
- Options pricing page and `/options/price` (Black-Scholes + Greeks), light theme with a toggle,
  native run-complete notifications and `aletheia://run/<id>` deep links in the desktop app.
- Run events now flow through the event bus (persistence and WebSocket fan-out are subscribers).
- Presets `quant_team` (documented but missing until now), `crypto_team`, `macro_team`,
  `smallcap_team`, each with asset-class-specific instructions.
- Calibration loop: a scheduled job (`calibration_resolve_interval_secs`, default 6h) scores past
  Oracle predictions against realised 7d/30d returns and stores Brier scores, which activates the
  PM's poor-calibration confidence haircut (previously outcomes were never filled in).
- Helm chart: optional chart-managed Secret (`secret.create`, off by default) and
  `secret.existingSecret` to name your own; the default behaviour is unchanged.
- Frontend tests for the warnings banner and sidebar (14 tests, up from 8), and a test that every
  manifest (pyproject, frontend, desktop, Tauri, Cargo) matches `aletheia.__version__`.

### Changed
- **Oracle signals are now deterministic.** The signal is the factor-registry composite (momentum,
  mean-reversion, volume, technicals) on real daily OHLCV. The LLM only writes commentary; it can no
  longer set or upgrade a signal, and the debate node can only de-risk. Confidence is the shrunk
  walk-forward hit rate of that same composite on that symbol (no look-ahead; capped at 0.55 under
  20 samples) instead of a hardcoded or LLM-reported number.
- With no usable price history (under 120 bars, or older than 7 days) Oracle returns HOLD at
  confidence 0 with `data_quality` set, rather than inventing prices. Shadow Trader ignores those.
- `stop_loss` / `target_price` on recommendations are now absolute ATR-based prices (2x / 3x ATR)
  instead of percentages. Cost-basis P&L (`fair_value_gap_pct`) no longer influences the signal.
- Portfolio Manager overrides keep all Oracle fields instead of dropping them.
- The frontend is split by route: the entry bundle drops from 782 kB to 236 kB, with the charting
  library in its own chunk.
- CI uses current major versions of `actions/checkout`, `setup-python`, `setup-node` and
  `upload-artifact` (no more Node 20 deprecation warning).
- The version now has one source per ecosystem: `aletheia.__version__` for Python and
  `package.json` for the UI.

### Fixed
- Live Market banners no longer name Angel One when another broker is streaming, and an auth problem is
  shown once instead of twice.
- The live-feed path was documented as `/ws/market-feed`; it is `/api/v1/ws/market`. The frontend also
  never connected to it, so no screen showed live quotes until the Live Market page.
- **Stale prices:** the static seed provider used to be first in the chain, so RELIANCE, TCS, INFY,
  HDFCBANK, ICICIBANK and SBIN were served hardcoded 2024 prices in real runs.
- **Mock holdings on real failure:** a failed Zerodha sync used to insert mock holdings into the
  portfolio; it now returns an error.
- **Self-reported paper-trading period:** `POST /execution/mode` trusted the caller's
  `paper_observation_days`; it is now measured from recorded paper trades.
- The Zerodha sync passed the API secret as the access token.
- Node failures caused by a timeout no longer show a blank reason; the message states the limit and
  names `ALETHEIA_NODE_TIMEOUT_SECS`.
- Exported reports and the sidebar still said v0.1.0; both now show the real version.

## [0.1.1] - 2026-10-19

### Changed
- Default per-node timeout raised from 30 s to 120 s (`ALETHEIA_NODE_TIMEOUT_SECS`). At 30 s, runs
  with a mid-size local model on modest hardware came back `partial` with healthy agents marked
  failed. The setting is now validated to be positive and documented in `.env.example`.
- Version number bumped to 0.1.1 across the Python package, API/CLI output, frontend, desktop
  app and Rust crates.

## [0.1.0] - 2026-10-19 — first alpha release

First tagged release. Aletheia is alpha software: the core loop works end to end, but see
[Known Limitations](README.md#known-limitations) and [What's Left](README.md#whats-left) before
relying on it. Nothing it produces is financial advice.

### Added
- **Multi-agent analysis pipeline** (LangGraph) for Indian equities and crypto: collector,
  oracle, risk, tax, sentiment, fundamentals, options-flow, debate and portfolio-manager nodes
  with per-node timeouts, partial-failure tolerance and Pydantic role contracts.
- **Local-first LLM routing** via Ollama with retry/circuit-breaker and a multi-provider router;
  runs fall back to templated summaries when no model is loaded.
- **Rust compute layer**: PyO3 extension (`aletheia_rust`) and standalone Axum sidecar
  (`aletheia_engine`) behind `ComputeClient`, with a Python fallback.
- **React frontend** (dashboard, runs, portfolio, backtest, hypotheses, factor
  explorer, shadow trader, paper trades, settings) with live WebSocket agent streaming.
- **Tauri desktop app** with a frozen backend and the Rust sidecar bundled into the installer.
- **Backtesting**, hypothesis lifecycle with automatic Sharpe-threshold validation, paper
  trading and shadow account, alpha-factor explorer, F&O expiry calendar, STCG/LTCG-aware tax
  scenarios.
- **Live market feed**: watchlist poller streaming over `/ws/market-feed` (polling through the
  provider chain, not an exchange feed).
- **PDF/Excel report export**, terminal dashboard (`aletheia tui`), MCP server (`aletheia mcp`),
  swarm presets, plugin contracts for strategies and data providers.
- **Deployment**: Docker Compose (backend, engine, frontend, Ollama; opt-in Prometheus/Grafana)
  and Kubernetes manifests with a Helm ConfigMap.
- `docs/sample_portfolio.csv` — a ready-to-import example portfolio.
- README "not financial advice" notice.
- Runs now carry a `warnings` list, shown as a banner on the Overview tab, when any symbol was
  priced from built-in sample data (`static_seed`) or could not be priced at all, instead of
  looking identical to a live-priced run.

### Fixed
- `GET /api/v1/factors/{ticker}` failed with `'Candle' object has no attribute 'date'`; it now
  reads `Candle.ts`, with a regression test.
- `poetry.lock` was out of sync with `pyproject.toml`, so `poetry install` failed for
  contributors and CI. `pyinstaller` is now restricted to `python<3.16` so the lock resolves.
- `cargo test` for `aletheia_rust` failed to link on Linux; removed the hard-coded PyO3
  `extension-module` feature (maturin enables it when building the wheel).
- The bundled Ollama container no longer fails with a port conflict on machines that already run
  Ollama (host port is now `127.0.0.1:11435`, override with `OLLAMA_HOST_PORT`) and is no longer
  exposed on all network interfaces.
- Sidecar integration tests now skip when the sidecar is not running instead of failing.
- Dependency advisories: bumped `pyjwt`, `urllib3`, `soupsieve`, `virtualenv`, `weasyprint`,
  `anyio`, `mcp`, `multidict`, `langgraph-sdk` (Python) and `source-map-js`, `undici` (npm).
- Code was not `ruff`-clean; formatted and removed an unused import.

### Security
- Dependency audits for Python, npm and Rust run in CI; the vulnerabilities above were cleared
  as part of making them pass. See [SECURITY.md](SECURITY.md) to report issues.

### Known issues
- Default per-node timeout (30 s) can mark runs `partial` with larger local models; raise
  `ALETHEIA_NODE_TIMEOUT_SECS`.
- Live broker execution (Zerodha) is a non-functional blueprint; use paper trading.
- No NSE/BSE real-time data source; the dark theme is the only theme.

[0.1.1]: https://github.com/AbsSadhu/Aletheia/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/AbsSadhu/Aletheia/releases/tag/v0.1.0
