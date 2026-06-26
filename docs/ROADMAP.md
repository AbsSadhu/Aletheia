# ALETHEIA Roadmap

Last updated: 2026-06-18

## Phase Overview

| Phase | Name | Status |
|-------|------|--------|
| 1 | Skeleton & Data Layer | ✅ Done |
| 2 | Engine Foundations | ✅ Done |
| 3 | Rich Frontend & Live Streaming | 🔲 Deferred |
| 4 | LLM Integration & Smart Agents | ✅ Done (Basic) |
| 5 | Production Polish & Desktop | 🔲 Partial (Docker/K8s skeleton) |
| **A** | **Agentic Core — ReAct Loop, Tool Registry, Memory** | 🔴 **Next** |
| **B** | **Research & Backtesting Engine** | 🔲 Planned |
| **C** | **Advanced Agent Capabilities — Swarm, MCP, LangSmith** | 🔲 Planned |
| **D** | **Rust Performance Modules** | 🔲 Planned |
| **E** | **Security, Reports & Production Hardening** | 🔲 Planned |

---

## Phase 1 — Skeleton & Data Layer ✅

- Monorepo layout (backend / frontend / desktop / docs / scripts)
- Pydantic settings with ALETHEIA_ env prefix
- 20+ Pydantic data models covering all agent outputs
- Provider chain architecture: Static Seed → yfinance → CCXT
- CollectorAgent with provider fallback and provenance logging
- Data normalizer (NSE/BSE suffix stripping, asset type inference)
- SQLite run store (upsert, list, get by ID)
- DuckDB market quote store (analytical persistence)
- FastAPI app with CORS, health, runs, portfolio-analysis, WebSocket endpoints
- Frontend React 19 + Vite scaffold
- Tauri 2 desktop shell scaffold (compiles, `get_desktop_settings` Tauri command)
- Docker Compose (backend + frontend)
- GitHub Actions CI (pytest + frontend build)
- ADR-0001 (Python core authority), ADR-0002 (Tauri desktop shell)

## Phase 2 — Engine Foundations ✅

- OracleAgent: heuristic signal generation (BUY / HOLD / REDUCE)
- SentinelAgent: portfolio risk assessment (VaR95, concentration risk, market regime)
- SageAgent: tax-aware scenario projection per holding (India tax drag)
- ScribeAgent: cross-agent recommendation synthesis with disagreement detection
- RunService: full 5-agent orchestration via LangGraph StateGraph
- AgentEvent recording for WebSocket replay
- LangGraph MemorySaver checkpointer integration
- Rust PyO3 module: `assess_portfolio_risk_rust`, `build_tax_summary_rust`, `build_scenario_rust`

## Phase 4 — LLM Integration ✅ (Basic)

- Ollama async HTTP client (`aletheia/core/llm/client.py`)
- Prompt templates for Oracle and Scribe (`prompts.py`)
- Structured output parsers (`parsers.py`)
- Oracle and Scribe agents upgraded with LLM + heuristic fallback
- Interactive CLI setup wizard (`aletheia setup`)
- Placeholder tool stubs (web_search, sec_filings)
- K8s manifests: Deployment, Service, Ingress, PVC
- Multi-stage Dockerfile

---

## Phase A — Agentic Core 🔴 NEXT

### A1. Tool Registry & Base Tool Framework
- [ ] `BaseTool` abstract class with JSON Schema parameter definitions
- [ ] `ToolRegistry` with auto-discovery via `__subclasses__()`
- [ ] 12+ real financial tools: market_data, web_search, web_reader, sec_filings, technical_analysis, fundamental_data, options_pricing, sector_peers, portfolio_analytics, backtest, remember, hypothesis, report_generate
- [ ] Tool availability checks and graceful degradation

### A2. ReAct Agent Loop
- [ ] Core ReAct loop: prompt → LLM → tool calls → execute → feed back → repeat
- [ ] Multi-provider ChatLLM interface (Ollama, OpenAI, Anthropic)
- [ ] 5-layer context management (microcompact, collapse, auto-summary)
- [ ] SSE streaming of reasoning, tool calls, and final answers
- [ ] Thread-safe cancellation
- [ ] Token usage tracking per iteration
- [ ] Configurable max iterations with wrap-up nudge

### A3. Persistent Memory System
- [ ] File-based cross-session memory (`~/.aletheia/memory/`)
- [ ] YAML frontmatter `.md` entries with keyword recall
- [ ] `MEMORY.md` auto-rebuilt index
- [ ] Memory types: user, feedback, project, reference
- [ ] Snapshot injection into agent system prompts
- [ ] DuckDB-backed analytical memory for run history search

## Phase B — Research & Backtesting Engine 🔲

### B1. Hypothesis-Driven Research
- [ ] `Hypothesis` model with lifecycle: proposed → testing → validated → rejected
- [ ] SQLite-backed hypothesis registry
- [ ] CLI commands: `aletheia hypothesis propose/list/test/validate`
- [ ] Link hypotheses to backtest run cards

### B2. Proper Backtest Engine
- [ ] Event-driven backtest runner with order book simulation
- [ ] Validation: lookahead bias detection, data snooping checks
- [ ] Metrics: Sharpe, Sortino, Calmar, max drawdown, win rate, profit factor
- [ ] Benchmark comparison: NIFTY 50, S&P 500, BTC
- [ ] Structured run cards (JSON artifacts)

### B3. Shadow Account (Paper Trading)
- [ ] Virtual position tracking with P&L
- [ ] Entry/exit signal scanning
- [ ] Equity curve and performance reports
- [ ] SQLite persistence

## Phase C — Advanced Agent Capabilities 🔲

### C1. Agent Swarm Orchestration
- [ ] Worker agents with scoped tool subsets and LLM context
- [ ] Swarm coordinator: spawn, collect, merge
- [ ] Preset teams: `investment_team`, `quant_team`, `due_diligence`
- [ ] Task storage and status tracking

### C2. MCP Server
- [ ] Expose Aletheia as MCP tool server
- [ ] Tools: run_analysis, execute_backtest, query_market_data, search_history, propose_hypothesis
- [ ] External AI agent integration (Claude, ChatGPT)

### C3. LangSmith Observability
- [ ] Wire `LANGCHAIN_TRACING_V2` to all LLM calls
- [ ] Add run metadata as LangSmith tags
- [ ] Token cost tracking per run

## Phase D — Rust Performance Modules 🔲

- [ ] `calculate_technical_indicators_rust()` — RSI, MACD, Bollinger Bands
- [ ] `options_pricing_rust()` — Black-Scholes, Greeks
- [ ] `portfolio_optimization_rust()` — mean-variance, efficient frontier
- [ ] `monte_carlo_var_rust()` — proper Monte Carlo VaR (10K+ simulations)
- [ ] `correlation_matrix_rust()` — fast pairwise correlation

## Phase E — Security, Reports & Production Hardening 🔲

### E1. Security & Trust Layer
- [ ] API key encryption at rest (Fernet)
- [ ] Rate limiting middleware (token bucket)
- [ ] Audit log table: every agent decision, LLM call, tool execution
- [ ] Input sanitization for all endpoints
- [ ] CSP headers

### E2. Report Generation
- [ ] PDF reports (WeasyPrint + Jinja2)
- [ ] JSON and CSV export
- [ ] Report download endpoint

### E3. Docker & K8s Production
- [ ] docker-compose with Ollama sidecar, Redis cache, Prometheus metrics
- [ ] Helm chart with ConfigMap, Secrets, HPA
- [ ] Liveness/readiness probes
- [ ] CI/CD pipeline for container builds

## Phase 3 — Rich Frontend & Live Streaming 🔲 (Deferred)

> This phase is intentionally deferred. The current frontend is a placeholder.
> The frontend will be rebuilt from scratch once the agentic backend is solid.

- [ ] Design system (dark mode, glassmorphism, micro-animations)
- [ ] Dashboard, Run Detail, Portfolio Editor, Settings pages
- [ ] WebSocket live streaming of ReAct loop progress
- [ ] Agent reasoning visualization (thinking → tool call → result → next thought)
