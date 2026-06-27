# ALETHEIA Roadmap

**Last updated: 2026-06-27**

---

## Phase Overview

| Phase | Name | Status |
|-------|------|--------|
| 1 | Skeleton & Data Layer | ✅ Done |
| 2 | Engine Foundations | ✅ Done |
| 4 | LLM Integration & Smart Agents | ✅ Done (Basic) |
| 5 | Production Polish & Desktop | 🔲 Partial (Docker/K8s skeleton) |
| **A** | **Agentic Core — ReAct Loop, Tool Registry, Memory** | ✅ **Done (Scaffold)** |
| **Sprint 1** | **Make It Actually Work — LLM Router, Semantic Memory, Backtest Feed** | ✅ **Done** |
| **Sprint 2** | **Rust Berserk Mode — Engine Sidecar, Custom Ingestion, Broker Blueprints** | ✅ **Done** (Streaming ❌) |
| **Sprint 2.5** | **Resilience & Org-Chart — State Machine, Timeout, Debate, PM Node, Contracts** | ✅ **Done** |
| **Sprint 3** | **Real Intelligence — Live Feed, Shadow Account, Frontend Wire-up** | 🔴 **NEXT** |
| **Sprint 3.5** | **Intelligence Upgrade — Vector Memory, Sage/Sentinel LLM Enrichment** | ✅ **Done** |
| **Sprint 4** | **Production Hardening — PDF Reports, LangSmith, Tauri, Prometheus** | 🔲 Planned |
| **Sprint 5** | **Moat — Full MCP, Multi-Swarm, Domain Fine-tuning** | 🔲 Future |

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
- [x] `link_to_backtest()` — connect hypothesis to backtest run
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

## Sprint 3 — Real Intelligence 🔴 NEXT

### 3A. Live Market Feed (Highest Impact)
- [ ] `aletheia-stream` in engine sidecar: Tokio Tungstenite → Binance WebSocket
- [ ] Yahoo Finance polling fallback with configurable interval
- [ ] Python `start_market_stream()` / `stop_market_stream()` interface
- [ ] NSE/BSE live feed (jugaad-trader or Angel One SmartAPI — India-specific)
- [ ] Live quote injection into Collector's provider chain (streaming overrides static/yfinance)

### 3B. Frontend Real Wire-up
- [ ] Dashboard: real WebSocket stream during run execution (agent thought bubbles live)
- [ ] RunDetail: all 5 agent outputs rendered from real API + per-agent status
- [ ] Portfolio page: real CRUD (add/edit/delete holdings) wired to `/api/v1/portfolios`
- [ ] Backtest page: form → POST /backtest → equity curve chart (Recharts)
- [ ] Hypotheses page: list / create / link-to-backtest
- [ ] RunsList: real-time status polling / WebSocket update

### 3C. Shadow Account (Paper Trading)
- [ ] `ShadowAccount` — VirtualPosition + VirtualOrder management
- [ ] `EntryExitScanner` — auto-generate virtual trades from Oracle signals
- [ ] SQLite persistence for positions, orders, and P&L
- [ ] Equity curve tracking
- [ ] `GET /api/v1/shadow/positions`
- [ ] `POST /api/v1/shadow/trade`
- [ ] Frontend Shadow Account page

### 3D. Real Observability
- [ ] Wire `LANGCHAIN_TRACING_V2` properly to LangSmith
- [ ] Tag every LangGraph node with `run_id`, `agent_name`, `token_count`
- [ ] Add structured logging to every tool call (name, args summary, result size, latency_ms)
- [ ] Emit `agent_progress` events via WebSocket per-agent (frontend renders real-time progress)
- [ ] `GET /api/v1/runs/{run_id}/progress` endpoint returning per-agent status

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

## Sprint 4 — Production Hardening 🔲

### 4A. PDF Report Generation
- [ ] WeasyPrint + Jinja2 templates
- [ ] `GET /api/v1/runs/{id}/export?format=pdf|json|csv`
- [ ] Include: executive summary, all 5 agent sections, charts (matplotlib), tax table

### 4B. Tauri Desktop Wire-up
- [ ] Auto-launch Python FastAPI backend as Tauri sidecar (no separate terminal needed)
- [ ] Auto-launch Rust `aletheia-engine` sidecar from Tauri
- [ ] Deep link: `aletheia://run/{id}` → open RunDetail page
- [ ] Native OS notifications when a run completes
- [ ] System tray integration

### 4C. Docker & K8s Production
- [ ] `docker-compose.yml` — Ollama sidecar, `aletheia-engine` Rust sidecar, Prometheus scrape
- [ ] Helm chart with ConfigMap, Secrets, HPA
- [ ] Liveness/readiness probes wired
- [ ] Prometheus `/metrics` endpoint on FastAPI
- [ ] Grafana dashboard template

### 4D. Full MCP Server
- [ ] Expose all 15 tools as proper MCP tools (not just FastMCP stub)
- [ ] Support Claude Desktop, Cursor, and any MCP-compatible AI assistant
- [ ] Tool discovery: `tools/list` → dynamic tool manifest

---

## Sprint 5 — Moat 🔲

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

### Live Broker Integration (Zerodha / Angel One)
- [ ] Complete Zerodha OAuth flow
- [ ] Order placement (paper mode first, then real)
- [ ] Position sync from broker → shadow account
- [ ] Automated alert: Oracle signal → SMS/email via broker notification

---

## Phase 3 — Rich Frontend & Live Streaming (Ongoing with Sprint 3B)

> Frontend is being rebuilt incrementally as backend APIs stabilize.

- [ ] Design system (dark mode, glassmorphism, micro-animations)
- [ ] Agent reasoning visualization (thought → tool call → result → next thought) — live token stream
- [ ] Portfolio editor with drag-and-drop CRUD operations
- [ ] Equity curve chart component (Recharts or Victory)
- [ ] Options pricing calculator widget (using existing Rust Greeks)
- [ ] Mobile-responsive layout

---

## Architecture Evolution Notes

### Event Bus (to add in Sprint 3D)
Currently agent events are stored in SQLite and replayed. Add an in-process `asyncio.Queue` event bus so agents publish events and multiple consumers (WebSocket, logger, audit log) subscribe without tight coupling.

### Confidence Aggregation (to add in Sprint 3.5)
Oracle emits `confidence: float`. Sentinel emits `risk_score: float`. These aren't systematically combined. Add formal confidence aggregation in `PortfolioManagerNode` — weighted combination of all analyst views → single portfolio-level conviction score.

### Context Injection (to add in Sprint 3.5)
Agents receive only the current run's data. Add pre-run context injection: each agent gets a "briefing" from episodic memory (last 3 analyses of the same symbols) injected into its system prompt automatically before the graph starts.
