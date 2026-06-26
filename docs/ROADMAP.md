# ALETHEIA Roadmap

Last updated: 2026-06-26

## Phase Overview

| Phase | Name | Status |
|-------|------|--------|
| 1 | Skeleton & Data Layer | ✅ Done |
| 2 | Engine Foundations | ✅ Done |
| 4 | LLM Integration & Smart Agents | ✅ Done (Basic) |
| 5 | Production Polish & Desktop | 🔲 Partial (Docker/K8s skeleton) |
| **A** | **Agentic Core — ReAct Loop, Tool Registry, Memory** | ✅ **Done (Scaffold)** |
| **Sprint 1** | **Make It Actually Work — LLM Router, Semantic Memory, Backtest Feed** | 🔴 **NEXT** |
| **Sprint 2** | **Rust Berserk Mode — Engine Sidecar, 30+ Compute Functions** | 🔲 Planned |
| **Sprint 3** | **Real Intelligence — Debate, Shadow Account, Frontend Wire-up** | 🔲 Planned |
| **Sprint 4** | **Production Hardening — Security, Reports, Docker** | 🔲 Planned |

---

## Completed Work (Phases 1, 2, 4, A)

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
- GitHub Actions CI (pytest + frontend build)

### Phase 2 — Engine Foundations ✅
- OracleAgent: heuristic signal generation (BUY / HOLD / REDUCE)
- SentinelAgent: portfolio risk assessment (VaR95, concentration risk, market regime)
- SageAgent: tax-aware scenario projection per holding (India tax drag)
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
- `PersistentMemory`: file-based storage (keyword search only — needs upgrade)
- `SwarmRuntime`: parallel worker orchestration scaffold
- Swarm presets: `investment_team`, `quant_team`
- Hypothesis models + registry (lifecycle incomplete)
- Backtest runner (event-driven, no real data feed yet)
- MCP server via FastMCP (dynamic tool wrapping)
- Rust PyO3 module: 6 functions — `assess_portfolio_risk_rust`, `build_tax_summary_rust`,
  `build_scenario_rust`, `options_pricing_rust`, `monte_carlo_var_rust`,
  `calculate_technical_indicators_rust`

---

## Sprint 1 — Make It Actually Work 🔴 NEXT

### 1A. Multi-Provider LLM Router
- [ ] `OpenAIChatLLM` implementation
- [ ] `AnthropicChatLLM` implementation
- [ ] `LLMRouter` with priority list, retry, circuit breaker
- [ ] Token usage + cost tracking per call
- [ ] `llm_provider_priority` setting

### 1B. Semantic Memory Upgrade
- [ ] `EpisodicMemory` — SQLite FTS5 over run history
- [ ] Rust `bm25_score_rust()` function for relevance ranking
- [ ] Working / Episodic / Semantic 3-tier architecture
- [ ] Auto-ingest run results into episodic store
- [ ] Snapshot injection into agent system prompts

### 1C. Historical Data Feed for Backtest
- [ ] `HistoricalDataFeed` — yfinance → DuckDB ingestion
- [ ] `BacktestRunner` wired to real data feed
- [ ] Lookahead bias guard (strict timestamp ordering)
- [ ] `POST /api/v1/backtest` endpoint

### 1D. Hypothesis Lifecycle
- [ ] State machine: proposed → testing → validated → rejected
- [ ] `link_to_backtest()` — connect hypothesis to backtest run
- [ ] CLI commands: `aletheia hypothesis propose/test/validate/reject`
- [ ] `GET /api/v1/hypotheses` endpoint

---

## Sprint 2 — Rust Berserk Mode 🔲

### 2A. Expanded `aletheia_rust` PyO3 Module (30+ functions)
- [ ] MACD: `calculate_macd_rust()`
- [ ] Bollinger Bands: `calculate_bollinger_bands_rust()`
- [ ] ATR: `calculate_atr_rust()`
- [ ] Stochastic: `calculate_stochastic_rust()`
- [ ] VWAP: `calculate_vwap_rust()`
- [ ] OBV: `calculate_obv_rust()`
- [ ] Portfolio optimization (mean-variance): `portfolio_optimization_rust()`
- [ ] Monte Carlo paths: `monte_carlo_portfolio_paths_rust()`
- [ ] Correlation matrix: `correlation_matrix_rust()`
- [ ] Rolling correlation: `rolling_correlation_rust()`
- [ ] Covariance matrix: `covariance_matrix_rust()`
- [ ] Sharpe: `calculate_sharpe_rust()`
- [ ] Sortino: `calculate_sortino_rust()`
- [ ] Calmar: `calculate_calmar_rust()`
- [ ] Enhanced max drawdown: `calculate_max_drawdown_rust()`
- [ ] BM25 scoring: `bm25_score_rust()`
- [ ] Rate limiter class: `RateLimiter` (token bucket, thread-safe)
- [ ] Cargo.toml upgrade: add `ndarray`, `statrs`

### 2B. `aletheia-engine` — Standalone Rust HTTP Sidecar
- [ ] New crate `aletheia_engine/` at workspace root
- [ ] Tokio + Hyper HTTP server on `127.0.0.1:18899`
- [ ] DuckDB connection pool (Rust-owned, no Python GIL)
- [ ] `POST /compute/indicators` — full indicator suite
- [ ] `POST /compute/portfolio-optimization`
- [ ] `POST /compute/monte-carlo`
- [ ] `POST /ingest/quotes` — bulk DuckDB insert
- [ ] `GET /query/quotes` — time-range query
- [ ] Python `ComputeClient` (thin async HTTP wrapper)
- [ ] Cargo workspace setup (`Cargo.toml` at root)

### 2C. `aletheia-stream` — Tokio WebSocket Ingestion (in engine)
- [ ] Binance WebSocket feed integration
- [ ] OHLCV normalization → DuckDB insert pipeline
- [ ] Yahoo Finance polling fallback
- [ ] Python `start_market_stream()` / `stop_market_stream()` interface

---

## Sprint 3 — Real Intelligence 🔲

### 3A. Agent Debate System
- [ ] `DebateOrchestrator` — Bull / Bear / Arbiter pattern
- [ ] 3 specialized system prompts (bullish, bearish, neutral)
- [ ] `debate_node` in LangGraph StateGraph
- [ ] `DebateResult` model + API response integration
- [ ] Opt-in `deep_analysis` flag (avoids 3× LLM cost by default)

### 3B. LangSmith Observability
- [ ] Token count + tool name tags per ReAct iteration
- [ ] `run_id` + `agent_name` LangSmith metadata
- [ ] LangGraph node tracing
- [ ] `langchain_tracing_v2` setting wired to CI/CD

### 3C. Shadow Account (Paper Trading)
- [ ] `ShadowAccount` — VirtualPosition + VirtualOrder management
- [ ] `EntryExitScanner` — auto-trade on Oracle signals
- [ ] SQLite persistence for positions and P&L
- [ ] Equity curve tracking
- [ ] `GET /api/v1/shadow/positions`
- [ ] `POST /api/v1/shadow/trade`

### 3D. Frontend Wire-up
- [ ] Dashboard: real WebSocket stream during run execution
- [ ] RunDetail: all 5 agent outputs from real API
- [ ] Backtest page: form → API → equity curve chart
- [ ] Hypotheses page: list / create / link to backtest
- [ ] Portfolio page: portfolio CRUD + trigger run

---

## Sprint 4 — Production Hardening 🔲

### 4A. Security & Trust Layer
- [ ] API key encryption at rest (Fernet)
- [ ] Rate limiting middleware (Rust token bucket via PyO3)
- [ ] Audit log table: every LLM call, tool execution, agent decision
- [ ] Input sanitization for all endpoints
- [ ] CSP headers

### 4B. Report Generation
- [ ] PDF reports (WeasyPrint + Jinja2 templates)
- [ ] JSON and CSV export
- [ ] `GET /api/v1/runs/{id}/export?format=pdf|json|csv`

### 4C. Docker & K8s Production
- [ ] `docker-compose.yml` — Ollama sidecar, `aletheia-engine` Rust sidecar, Prometheus
- [ ] Helm chart with ConfigMap, Secrets, HPA
- [ ] Liveness/readiness probes wired
- [ ] CI/CD pipeline for container builds

---

## Phase 3 — Rich Frontend & Live Streaming (Ongoing with Sprint 3D)

> Frontend is being rebuilt incrementally as backend APIs stabilize.

- [ ] Design system (dark mode, glassmorphism, micro-animations)
- [ ] Agent reasoning visualization (thought → tool call → result → next thought)
- [ ] Portfolio editor with drag-and-drop CRUD operations
