# ALETHEIA Roadmap

**Last updated: 2026-09-04**

> This document was reconciled against actual code (not prior doc claims) on
> 2026-09-03 — every status below is backed by a file:line check, not
> inherited from the previous version of this file, which had drifted
> (several "planned" items were already done; a couple of "done" items were
> only partially wired).

---

## Phase Overview

| Phase | Name | Status |
|-------|------|--------|
| 1 | Skeleton & Data Layer | ✅ Done |
| 2 | Engine Foundations | ✅ Done |
| 4 | LLM Integration & Smart Agents | ✅ Done (Basic) |
| 5 | Production Polish & Desktop | 🟡 Mostly Done (Docker/K8s/Grafana real; Helm ConfigMap/Secret templates + docker-compose Ollama/engine services still missing) |
| **A** | **Agentic Core — ReAct Loop, Tool Registry, Memory** | ✅ **Done (Scaffold)** |
| **Sprint 1** | **Make It Actually Work — LLM Router, Semantic Memory, Backtest Feed** | ✅ **Done** |
| **Sprint 2** | **Rust Berserk Mode — Engine Sidecar, Custom Ingestion, Broker Blueprints** | ✅ **Done** (Streaming ❌ — see Sprint 3A) |
| **Sprint 2.5** | **Resilience & Org-Chart — State Machine, Timeout, Debate, PM Node, Contracts** | ✅ **Done** |
| **Sprint 3** | **Real Intelligence — Live Feed, Shadow Account, Frontend Wire-up** | 🟡 **Mostly Done** — 3A (live feed) is the one real gap left; 3B/3C are further along than this doc previously credited |
| **Sprint 3.5** | **Intelligence Upgrade — Vector Memory, Sage/Sentinel LLM Enrichment** | ✅ **Done** |
| **Sprint 4** | **Production Hardening — PDF Reports, LangSmith, Tauri, Prometheus** | 🟡 **Mostly Done** — 4A/4C/4D done, 4B partial (see below) |
| **Sprint 5** | **Moat — Full MCP, Multi-Swarm, Domain Fine-tuning** | 🔲 Future (unchanged, nothing started) |

---

## Completed Work

### Phase 1 — Skeleton & Data Layer ✅
- Monorepo layout (backend / frontend / desktop / docs / scripts)
- Pydantic settings with `ALETHEIA_` env prefix
- 20+ Pydantic data models covering all agent outputs
- Provider chain architecture: Static Seed → yfinance → CCXT
- CollectorAgent with provider fallback and provenance logging
- Data normalizer (NSE/BSE suffix stripping, asset type inference)
- SQLite run store (upsert, list, get by ID)
- DuckDB market quote store (analytical persistence)
- FastAPI app with CORS, health, runs, portfolio-analysis, WebSocket endpoints
- Frontend React 19 + Vite scaffold
- Tauri 2 desktop shell scaffold
- Docker Compose (backend + frontend)
- GitHub Actions CI (pytest + frontend build + dep audits + secret scan)

### Phase 2 — Engine Foundations ✅
- OracleAgent: heuristic signal generation (BUY / HOLD / REDUCE)
- SentinelAgent: portfolio risk assessment (VaR95, concentration risk, market regime)
- SageAgent: tax-aware scenario projection per holding (India STCG/LTCG)
- ScribeAgent: cross-agent recommendation synthesis with disagreement detection
- RunService: full 5-agent orchestration via LangGraph StateGraph
- AgentEvent recording for WebSocket replay
- LangGraph MemorySaver checkpointer integration

### Phase 4 — LLM Integration ✅ (Basic)
- Ollama async HTTP client (`aletheia/core/llm/client.py`)
- Prompt templates for Oracle and Scribe (`prompts.py`)
- Structured output parsers (`parsers.py`)
- Oracle and Scribe agents upgraded with LLM + heuristic fallback
- Interactive CLI setup wizard (`aletheia setup`)
- K8s manifests: Deployment, Service, Ingress, PVC
- Multi-stage Dockerfile

### Phase A — Agentic Core ✅ (Scaffold)
- `BaseTool` + `ToolRegistry` with auto-discovery
- 15 tool stubs: market_data, web_search, web_reader, sec_filings, technical_analysis,
  fundamental_data, options_pricing, sector_peers, portfolio_analytics, backtest,
  remember, hypothesis, report_generate, news_search, sector_peers
- `ReActLoop`: full Reasoning + Acting loop with SSE streaming
- `OllamaChatLLM`: single-provider chat interface with tool calling
- `PersistentMemory`: file-based storage (keyword search only)
- `SwarmRuntime`: parallel worker orchestration scaffold
- Swarm presets: `investment_team`, `quant_team`
- Hypothesis models + registry
- Backtest runner (event-driven)
- MCP server via FastMCP (dynamic tool wrapping)
- Rust PyO3 module: 6 core functions

### Sprint 1 — Make It Actually Work ✅

#### 1A. Multi-Provider LLM Router ✅
- [x] `OpenAIChatLLM` implementation
- [x] `AnthropicChatLLM` implementation
- [x] `LLMRouter` with priority list, retry, circuit breaker
- [x] Token usage + cost tracking per call
- [x] `llm_provider_priority` setting

#### 1B. Semantic Memory Upgrade ✅
- [x] `EpisodicMemory` — SQLite FTS5 over run history
- [x] Rust `bm25_score_rust()` function for relevance ranking
- [x] Working / Episodic / Semantic 3-tier architecture
- [x] Auto-ingest run results into episodic store
- [x] Snapshot injection into agent system prompts

#### 1C. Historical Data Feed for Backtest ✅
- [x] `HistoricalDataFeed` — yfinance → DuckDB ingestion
- [x] `BacktestRunner` wired to real data feed
- [x] Lookahead bias guard (strict timestamp ordering)
- [x] `POST /api/v1/backtest` endpoint

#### 1D. Hypothesis Lifecycle ✅
- [x] State machine: proposed → testing → validated → rejected
- [x] `link_to_backtest()` — connect hypothesis to backtest run, now exposed
  via `POST /api/v1/hypotheses/{id}/link-backtest` (previously registry-only,
  unreachable from the API). Fixed 2026-09-04 along with two other real
  bugs found while researching the frontend page: `save()` omitted
  `backtest_run_id` from its column list, so any later save (e.g. via
  `transition()`) silently wiped the link back to NULL; and
  `add_evidence()` constructed `Evidence` with kwargs (`summary`/`supports`)
  that don't exist on the model (`description`/`supports_hypothesis` are the
  real fields), so every call to `POST /hypotheses/{id}/evidence` raised a
  pydantic `ValidationError`. See `tests/unit/test_hypothesis_registry.py`.
- [x] CLI commands: `aletheia hypothesis propose/test/validate/reject`
- [x] `GET/POST /api/v1/hypotheses` endpoint

### Sprint 2 — Rust Berserk Mode & Custom Ingestion ✅

#### 2A. Expanded `aletheia_rust` PyO3 Module (30+ functions) ✅
- [x] MACD, Bollinger Bands, ATR, Stochastic, VWAP, OBV
- [x] Portfolio optimization (mean-variance), Monte Carlo paths
- [x] Correlation matrix, rolling correlation, covariance matrix
- [x] Sharpe, Sortino, Calmar, max drawdown
- [x] BM25 scoring: `bm25_score_rust()`
- [x] Rate limiter class: `RateLimiter` (token bucket, thread-safe)
- [x] Cargo.toml upgrade: add `ndarray`, `statrs`

#### 2B. `aletheia-engine` — Standalone Rust HTTP Sidecar ✅
- [x] New crate `aletheia_engine/` at workspace root
- [x] Tokio + Hyper HTTP server on `127.0.0.1:18899`
- [x] DuckDB connection pool (Rust-owned, no Python GIL)
- [x] `POST /compute/indicators` — full indicator suite
- [x] `POST /compute/portfolio-optimization`
- [x] `POST /compute/monte-carlo`
- [x] `POST /ingest/quotes` — bulk DuckDB insert
- [x] `GET /query/quotes` — time-range query
- [x] Python `ComputeClient` (thin async HTTP wrapper with PyO3 fallback)

#### 2C. `aletheia-stream` — Tokio WebSocket Ingestion
- [ ] Binance WebSocket feed integration
- [ ] OHLCV normalization → DuckDB insert pipeline
- [ ] Yahoo Finance polling fallback
- [ ] Python `start_market_stream()` / `stop_market_stream()` interface

#### 2D. Custom Ingestion, Broker Blueprints, and CLI NLP Runner ✅
- [x] Ingest CSV/Parquet/DuckDB into unified DuckDB store (`local_importer.py`)
- [x] Define `BaseBrokerConnector` interface (`brokers/base.py`)
- [x] Create `Zerodha` connector blueprint (`brokers/zerodha.py`)
- [x] Create `TradingView` webhook connector blueprint (`brokers/tradingview.py`)
- [x] Add `run` CLI command with agent executor stream (`cli/main.py`)

### Sprint 2.5 — Resilience & Agent Org-Chart Discipline ✅

#### Pydantic Role Contracts ✅
- [x] `AnalystContract` base — Oracle, Collector: forbidden from emitting final decisions
- [x] `RiskConstraintContract` base — Sage, Sentinel: forbidden from emitting synthesis
- [x] `SynthesisContract` base — Scribe: forbidden from emitting raw data
- [x] `__init_subclass__` enforcement at class-definition time
- [x] `model_validator` enforcement at runtime
- [x] 60-test integration suite (100% pass rate)

#### LangGraph Resilience ✅
- [x] Per-node timeout handling
- [x] Partial-failure mode: Scribe produces gap-noting report if any upstream fails
- [x] Run-level state machine persisted in SQLite (`pending → running → partial → complete → failed`)
- [x] Per-agent status tracking in SQLite
- [x] Configurable graph: skip agents via `agent_config` flags (e.g., skip Sage if no tax jurisdiction)

#### Debate & Override Nodes ✅
- [x] `debate_node` — Oracle ↔ Sentinel material disagreement → re-prompt with each other's reasoning
- [x] Unresolved disagreements registered as flag for Scribe to surface in narrative
- [x] `portfolio_manager_node` — deterministic rule enforcement post-Sage (exposure limits, max size)
- [x] PM node can override LLM recommendation; override recorded in final output

---

## Sprint 3 — Real Intelligence 🟡 Mostly Done

### 3A. Live Market Feed — 🔴 Still the real gap (highest-impact remaining item)
- [ ] `aletheia-stream` in engine sidecar: Tokio Tungstenite → Binance WebSocket
- [ ] Yahoo Finance polling fallback with configurable interval
- [ ] Python `start_market_stream()` / `stop_market_stream()` interface
- [ ] NSE/BSE live feed (jugaad-trader or Angel One SmartAPI — India-specific)
- [ ] Live quote injection into Collector's provider chain (streaming overrides static/yfinance)

Confirmed completely absent as of 2026-09-03: `aletheia_engine/src/main.rs` is
pure HTTP/Axum with zero websocket deps in `Cargo.toml`; no
`start_market_stream()`/`stop_market_stream()` anywhere in `aletheia/`. This
is a from-scratch subsystem, not a partial build.

### 3B. Frontend Real Wire-up — 🟡 Partial, further along than previously tracked
- [x] Dashboard: the "Agent Pipeline" widget (`frontend/src/pages/Dashboard.tsx`)
  used to hardcode "Last run: completed" for every agent whenever *any*
  latest run existed, regardless of whether that agent actually produced
  output — misleading. Fixed 2026-09-04: `agentPipelineState()` now checks
  each agent's actual output field (`collector_output`/`oracle_output`/
  `sentinel_output`/`sage_output`/`scribe_output`) and the run's real
  `summary.status`, so it correctly shows completed / in-progress / failed
  / skipped per agent, plus the page now polls every 15s (matching the
  `PaperTrades.tsx`/`ShadowTrader.tsx` pattern) instead of loading once.
  Note: this is polling, not a WebSocket thought-stream — true live
  per-token streaming for an in-progress run remains RunDetail's job (new
  runs auto-navigate there), which is the right split, not a shortcut.
- [x] RunDetail: all 8 pipeline agents (Collector/Oracle/Sentinel/Sage/Scribe
  plus Sentiment/Fundamental/OptionsFlow) are rendered from real API status
  (`frontend/src/pages/RunDetail.tsx`), the last 3 via a new "Extended
  Signals" tab. Collector/Oracle/Sentinel/Sage/Scribe additionally get live
  WebSocket updates; Sentiment/Fundamental/OptionsFlow render from the
  final `RunResult` payload only (no incremental WS events for them yet).
- [x] Portfolio page: real CRUD wired to `/api/v1/portfolios`
  (`frontend/src/pages/Portfolio.tsx`, `frontend/src/lib/api.ts:131-149`).
- [x] Backtest page: built 2026-09-04 (`frontend/src/pages/Backtest.tsx`) —
  form for symbols/date range/strategy/capital, metrics cards, equity-curve
  chart (Recharts, same pattern as `ShadowTrader.tsx`), orders table.
  `runBacktest()` (`frontend/src/lib/api.ts`) is now properly typed against
  `BacktestResult` instead of returning `any`.
- [x] Hypotheses page: built 2026-09-04 (`frontend/src/pages/Hypotheses.tsx`)
  — propose form, list with status filter, detail panel with status
  transitions, evidence log + add-evidence form, and backtest linking via
  the new `link-backtest` endpoint (see §1D above for the backend bugs
  fixed alongside this).
- [x] RunsList: fixed 2026-09-04 — now polls every 15s
  (`frontend/src/pages/RunsList.tsx`), same pattern as Dashboard above.

### 3C. Shadow Account (Paper Trading) — ✅ Done
- [x] `ShadowAccount` / `VirtualPosition` / `VirtualOrder` management
  (`aletheia/extensions/shadow_account/account.py`, `models.py`)
- [x] `EntryExitScanner` — auto-generates virtual trades from Oracle signals
  (`aletheia/extensions/shadow_account/scanner.py:13`,
  `async def scan(self, oracle_outputs, exchange="NSE")`)
- [x] SQLite persistence for positions, orders, and P&L
  (`aletheia/extensions/shadow_account/storage.py`)
- [x] Equity curve tracking (`aletheia/extensions/shadow_account/reporter.py`)
- [x] Shadow endpoints wired (positions/orders/performance/trade)
- [x] Frontend `ShadowTrader.tsx` page — real API calls, 15s poll, real
  Recharts equity curve, not a placeholder

Also done beyond what this sprint originally scoped: `PaperTrader`
(`aletheia/core/execution/paper_trader.py`) with real average-price/
position accounting, plus a frontend `PaperTrades.tsx` page and a
`FactorExplorer.tsx` page — none of these were in the original Sprint 3
plan but shipped alongside it (commit `c18ae0e`).

### 3D. Real Observability — 🟡 Partial
- [x] `LANGCHAIN_TRACING_V2`/LangSmith wiring is real and config-driven
  (`aletheia/core/config/settings.py:94-119` sets the env vars;
  `aletheia/core/agent/loop.py:12` decorates `ReActLoop.run` with
  `@traceable`, with a dummy fallback if langsmith isn't installed).
- [x] Structured tool-call events exist (`loop.py:87,100` emit
  `tool_call`/`tool_result` StreamEvents with tool name + args/result) —
  **gap**: no `latency_ms` or result-size field is captured.
- [x] Live per-agent status: functionally covered by
  `WS /api/v1/ws/runs/{run_id}` (`aletheia/core/api/routers/websocket.py`)
  plus `GET /runs/{run_id}/events` and `GET /runs/{run_id}/trace`
  (`aletheia/core/api/routers/runs.py:74-91`) — no dedicated `/progress`
  endpoint exists under that exact name, but the need it was meant to serve
  is met by what's there.

---

## Sprint 3.5 — Intelligence Upgrade ✅ Done

### Vector Memory (RAG)
- [x] Replace YAML semantic files with ChromaDB (local) or sqlite-vec
- [x] Embed every run result summary using `nomic-embed-text` via Ollama
- [x] Memory query: "what did I say about RELIANCE last quarter?"
- [x] Cross-run learning: Scribe references historical analyses in narrative

### Sage LLM Narrative Enrichment
- [x] Sage currently: Rust numbers only. Add: LLM generates scenario narrative on top of numbers
- [x] "Given your holding period and current Oracle signal, the tax-optimal exit window is..."

### Sentinel Natural Language Commentary
- [x] Sentinel currently: Rust numbers. Add: LLM generates plain-English risk brief
- [x] "Your portfolio has 45% IT concentration. VaR95 = ₹18,400 — elevated vs. NIFTY 500 baseline."

### LLM Token Streaming to Frontend
- [x] Token-by-token streaming from Ollama/OpenAI → SSE event per chunk → frontend render
- [x] "Thinking..." animation with live token display in RunDetail

### NSE/BSE Specific Intelligence
- [ ] FII/DII flow data (NSE India public API)
- [ ] SEBI circuit breaker awareness (upper/lower band data)
- [ ] F&O expiry calendar integration
- [ ] Promoter shareholding change detection (BSE filings)
- [ ] NIFTY/SENSEX regime detection for Sentinel (bullish/bearish/sideways macro)

---

## Sprint 4 — Production Hardening 🟡 Mostly Done

### 4A. PDF Report Generation — ✅ Done
- [x] WeasyPrint + Jinja2 templates (`aletheia/core/reporting/exporter.py`,
  `render_html()`/`export_pdf()` — falls back to raw HTML if WeasyPrint
  isn't installed; also `export_excel()`)
- [x] `GET /api/v1/runs/{run_id}/export?format=pdf|excel`
  (`aletheia/core/api/routers/runs.py:94-122`)
- [x] Executive summary + agent sections included

### 4B. Tauri Desktop Wire-up — 🟡 Partial
- [x] Auto-launch Python FastAPI backend (`spawn_api()`,
  `desktop/src-tauri/src/main.rs:90-115`)
- [x] Auto-launch Rust `aletheia-engine` sidecar (`spawn_engine()`,
  `main.rs:69-88`), with health-gated window reveal polling both services
  (`main.rs:255-278`). Note: this is manual `Command`-spawning of dev-tree
  binaries, not Tauri's `bundle.externalBin` mechanism
  (`tauri.conf.json:35-40` has empty `resources: []`) — fine for dev, needs
  real sidecar bundling before shipping an installer to a non-dev machine.
- [x] System tray integration (`TrayIconBuilder`, `main.rs:280-341`)
- [ ] Deep link: `aletheia://run/{id}` → open RunDetail page — **missing**,
  no `tauri-plugin-deep-link` dependency or scheme registered
- [ ] Native OS notifications when a run completes — **missing**, no
  `tauri-plugin-notification` dependency

### 4C. Docker & K8s Production — 🟡 Mostly Done
- [x] Liveness/readiness probes wired (`k8s/aletheia/templates/deployment.yaml:48-59`)
- [x] HPA (folded into `templates/service.yaml:74-101`, not a separate file,
  `autoscaling.enabled: true` in `values.yaml:71-77`)
- [x] Prometheus `/metrics` endpoint on FastAPI (routed in
  `aletheia/core/main.py`)
- [x] Grafana dashboard template
  (`monitoring/grafana/provisioning/dashboards/aletheia.json` + provisioning config)
- [ ] Helm `ConfigMap` — **missing**, env vars are inlined literally from
  `values.yaml` in `deployment.yaml:32-36` rather than templated
- [ ] Helm `Secret` — **partial**, `deployment.yaml:37-44` references a
  `aletheia-secrets` Secret via `secretKeyRef` but no
  `templates/secret.yaml` creates it; currently assumes external
  provisioning (fine if intentional, but undocumented as such)
- [ ] `docker-compose.yml` — has `backend`/`frontend`/`prometheus`/`grafana`,
  but **no Ollama service and no `aletheia-engine` Rust sidecar service** —
  incomplete relative to what running the full stack via compose needs

### 4D. Full MCP Server ✅
- [x] Expose all 13 registered tools as proper MCP tools via `aletheia mcp`
  (fixed: `fastmcp` was never an installed/pinned dependency and the
  dynamic `**kwargs` wrapper was rejected outright by FastMCP's schema
  builder — each tool now advertises its real `execute()` signature)
- [x] Support Claude Desktop, Cursor, and any MCP-compatible AI assistant —
  point its config `command` at `aletheia mcp` (stdio transport)
- [x] Tool discovery: `tools/list` verified end-to-end over a real stdio
  JSON-RPC handshake (`initialize` → `notifications/initialized` →
  `tools/list`), plus a live `market_data` tool call

---

## Sprint 5 — Moat 🔲

Reconfirmed 2026-09-03: none of this has been started — zero matches for
`swarm_preset`/`crypto_team`/`macro_team`/`smallcap_team` anywhere in the
codebase. Unchanged from the previous version of this doc.

### Multi-Swarm Specialist Teams
- [ ] `crypto_team`: Oracle/Sentinel tuned for crypto metrics (funding rate, open interest, liquidation levels)
- [ ] `macro_team`: macro factors (RBI policy, USD/INR, crude oil, FII flows impact)
- [ ] `smallcap_team`: adjusted thresholds for illiquid NSE/BSE smallcap stocks
- [ ] Teams selectable via `agent_config.swarm_preset` flag

### Domain Fine-tuning
- [ ] Collect BSE/NSE earnings call transcripts + SEBI filings corpus
- [ ] Fine-tune Llama-3 8B on this corpus (LoRA) → `aletheia-7b`
- [ ] Self-hosted on Ollama — better than generic models for Indian market queries
- [ ] This is the long-term technical moat

### Hypothesis Auto-Validation
- [ ] Hypothesis created → Backtest auto-runs → If Sharpe > threshold → auto-advance to validated
- [ ] Hypothesis tournament: N competing strategies, same date range, ranked output
- [ ] Report: winning strategy + loser analysis

The underlying registry this builds on is real: `HypothesisRegistry`
(`aletheia/extensions/hypotheses/registry.py`) has a working SQLite-backed
state machine (`propose`/`transition`/`link_to_backtest`), but `transition()`
is currently only ever called manually via
`POST /api/v1/hypotheses/{id}/transition`
(`aletheia/core/api/routers/hypotheses.py:74`) — nothing auto-runs a
backtest or checks a Sharpe threshold yet. Also has no frontend page at all
(see 3B).

### Live Broker Integration (Zerodha / Angel One)
- [ ] Complete Zerodha OAuth flow
- [ ] Order placement (paper mode first, then real)
- [ ] Position sync from broker → shadow account
- [ ] Automated alert: Oracle signal → SMS/email via broker notification

`aletheia/extensions/brokers/zerodha.py` is explicitly a "Blueprint
implementation" (line 2 docstring) — real method stubs
(`get_account_balance`/`place_order`/`cancel_order`) wrapping the
`kiteconnect` SDK if installed, but no `generate_session`/`request_token`
OAuth handling exists. This touches real money if completed — should be
staged carefully (paper mode first), not treated as a quick wire-up.

---

## Phase 3 — Rich Frontend & Live Streaming (Ongoing with Sprint 3B)

> Frontend is being rebuilt incrementally as backend APIs stabilize.

- [x] Design system — 🟡 partial: consistent CSS-variable token system
  (`frontend/src/styles/app.css`), but **dark-mode-only**
  (`color-scheme: dark` fixed, no light theme or toggle), no glassmorphism
  effects confirmed.
- [x] Agent reasoning visualization — real WebSocket-driven live status +
  token streaming exist for the 5 core agents, plus a static "Extended
  Signals" tab for Sentiment/Fundamental/OptionsFlow (RunDetail); see
  Sprint 3B/3D above for the remaining gap (no latency capture).
- [x] Portfolio editor — real CRUD (see 3B), not drag-and-drop specifically.
- [x] Equity curve chart component — Recharts (`recharts@3.8.1`), real,
  used in `ShadowTrader.tsx`/`PaperTrades.tsx`. **Not** used yet for the
  still-missing Backtest page (3B).
- [ ] Options pricing calculator widget — **missing**. Black-Scholes/Greeks
  are already computed server-side in Rust (`aletheia_rust/src/lib.rs`);
  nothing in the frontend exposes them.
- [ ] Mobile-responsive layout — **partial only**, two basic breakpoints
  (`1024px`/`640px`) in `app.css`, no dedicated mobile pass.

**Note**: no Tailwind, no shadcn/ui, no Victory installed — styling is
100% hand-rolled CSS + inline `style={{...}}` objects. `RunDetail.tsx` in
particular has heavy inline-style duplication instead of using the
CSS-variable system `app.css` already defines — worth cleaning up before
adding more features to that file.

---

## Architecture Evolution Notes

> Confidence Aggregation and Context Injection below weren't re-verified
> against code in the 2026-09-03 pass — everything above this section was.

### Event Bus (to add in Sprint 3D) — 🟡 Built, not wired in
`EventBus` is real (`aletheia/core/events/bus.py`, `get_event_bus()`),
exported from `aletheia/core/events/__init__.py`, with a full passing test
suite (`tests/unit/test_event_bus.py`). But nothing outside the `events/`
package actually imports or publishes to it yet — the WebSocket router,
logger, and audit log don't consume it, so agent events still flow through
the original SQLite-store-and-replay path this note describes replacing.
The building block exists; the integration doesn't.

### Confidence Aggregation (to add in Sprint 3.5)
Oracle emits `confidence: float`. Sentinel emits `risk_score: float`. These aren't systematically combined. Add formal confidence aggregation in `PortfolioManagerNode` — weighted combination of all analyst views → single portfolio-level conviction score.

### Context Injection (to add in Sprint 3.5)
Agents receive only the current run's data. Add pre-run context injection: each agent gets a "briefing" from episodic memory (last 3 analyses of the same symbols) injected into its system prompt automatically before the graph starts.
