# Changelog

All notable changes to Aletheia are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). While the version is `0.x`, anything may change
between releases.

## [Unreleased]

### Added
- Helm chart: optional chart-managed Secret (`secret.create`, off by default) and
  `secret.existingSecret` to name your own; the default behaviour is unchanged.
- Frontend tests for the warnings banner and sidebar (14 tests, up from 8), and a test that every
  manifest (pyproject, frontend, desktop, Tauri, Cargo) matches `aletheia.__version__`.

### Changed
- The frontend is split by route: the entry bundle drops from 782 kB to 236 kB, with the charting
  library in its own chunk.
- CI uses current major versions of `actions/checkout`, `setup-python`, `setup-node` and
  `upload-artifact` (no more Node 20 deprecation warning).
- The version now has one source per ecosystem: `aletheia.__version__` for Python and
  `package.json` for the UI.

### Fixed
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
