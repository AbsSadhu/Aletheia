# Aletheia Codebase Handoff & Technical Audit

Welcome to Aletheia! This document serves as a single-pass onboarding blueprint for **Claude Code** and developers. It details the system architecture, feature completion status, database models, dependencies, verification status, and the immediate development roadmap.

---

## 1. Project Overview

- **Project Name**: Aletheia
- **Purpose**: A local-first, multi-agent financial intelligence and recommendation engine for the Indian stock (NSE/BSE) and cryptocurrency markets.
- **Current Sprint**: **Sprint 3: Real Intelligence** — Shadow Account (paper trading) is done, including a frontend page; the live market feed (`aletheia-stream`) is the one genuinely unbuilt piece. Frontend is **not** fully wired to the backend yet — the Backtest and Hypotheses pages have real backends but zero frontend (see `docs/ROADMAP.md` §3B for the reconciled breakdown).
- **Current Status**: 219 tests collected across all suites; CI (`.github/workflows/ci.yml`) is green end-to-end as of this update — lint, format, mypy (baseline-gated), Python/frontend/Rust dependency audits, and all three Python test steps are real blocking gates, not `continue-on-error`.
- **Repository**: [github.com/AbsSadhu/Aletheia](https://github.com/AbsSadhu/Aletheia)
- **Last Updated**: 2026-09-03

---

## 2. Product Form Factors

- [x] **CLI Tool**: Typer-based interface located in [aletheia/cli/main.py](file:///c:/Aletheia/aletheia/cli/main.py). Fully working. Allows project setup, executing agent runs, viewing paper trades, running backtests, and comparing results.
- [x] **Python SDK**: Internal modules under [aletheia/core/](file:///c:/Aletheia/aletheia/core/) serve as the SDK. Easily imported (e.g. `from aletheia.core.compute.client import ComputeClient`).
- [🟡] **Desktop App**: Tauri 2 wrapper located in [desktop/](file:///c:/Aletheia/desktop/). Builds and embeds Vite static output. Sidecar auto-launch for both the Python FastAPI backend and the Rust `aletheia-engine` sidecar is real (`spawn_api()`/`spawn_engine()`, `desktop/src-tauri/src/main.rs`), with health-gated window reveal and a working system tray. What's still missing: real Tauri `bundle.externalBin` sidecar bundling for distribution (currently spawns dev-tree binaries directly), deep links, and native OS notifications.
- [x] **Docker Container**: [Dockerfile](file:///c:/Aletheia/Dockerfile) and [docker-compose.yml](file:///c:/Aletheia/docker-compose.yml) are fully operational for containerized deployments.

---

## 3. Architecture Snapshot

### 3.1 LangGraph Agent Pipeline
- **File**: [aletheia/core/graph_flow.py](file:///c:/Aletheia/aletheia/core/graph_flow.py)
- **Topology**:
  ```mermaid
  graph TD
      START --> Collector
      Collector --> Oracle
      Collector --> Sentinel
      Collector --> Sentiment
      Collector --> Fundamental
      Collector --> OptionsFlow
      Oracle --> Debate
      Sentinel --> Debate
      Debate -- Disagreement --> Re-Prompt
      Debate --> Sage
      Sage --> PortfolioManager
      PortfolioManager --> Scribe
      Sentiment --> Scribe
      Fundamental --> Scribe
      OptionsFlow --> Scribe
      Scribe --> END
  ```
- **Base Role Contracts**:
  - `AnalystContract` (Collector, Oracle, Sentiment, Fundamental, OptionsFlow): Prohibited from emitting final recommendations or decisions.
  - `RiskConstraintContract` (Sentinel, Sage): Prohibited from emitting final narrative synthesis.
  - `SynthesisContract` (Scribe): Prohibited from emitting raw metrics/quotes.
- **Node Controls**: Features Timeout handling, skipped nodes (e.g., skip tax-related Sage node if no tax profile), and deterministic PM node overrides.

### 3.2 FastAPI Backend
- **Core Files**: [aletheia/core/main.py](file:///c:/Aletheia/aletheia/core/main.py) and [aletheia/core/api/routes.py](file:///c:/Aletheia/aletheia/core/api/routes.py).
- **Core Endpoints**:
  - `GET /health` & `GET /health/ready`: System & DB availability check.
  - `GET/POST /api/v1/config`: Retrieve system config with masked secrets / Update settings.
  - `GET/POST /api/v1/portfolios`: Manage portfolios.
  - `POST /api/v1/portfolios/{name}/sync-zerodha`: Pull holdings from Zerodha Kite (with mock fallback).
  - `GET/POST /api/v1/runs`: List agent runs / Initiate a new multi-agent portfolio analysis.
  - `GET /api/v1/runs/{id}`: Detailed run results and inputs.
  - `WS /ws/runs/{id}`: Live stream agent thought logs, tools, and token stream.
  - `POST /api/v1/backtest`: Execute historical backtest over DuckDB/yfinance feed.
  - `GET/POST /api/v1/hypotheses`: Proposed strategy registry & outcome tracking.
  - `GET/POST /api/v1/execution/paper-trades`: Retrieve simulated executions.
  - `POST /api/v1/execution/paper-trades/{id}/settle`: Close paper trade with final price.

### 3.3 Data Layer
- **SQLite Database**: Transactional storage for runs, agent events, portfolios, and hypotheses. Uses [Alembic](file:///c:/Aletheia/alembic/) migrations (`c036e66a7d30_init_schema.py`).
- **DuckDB Database**: Analytical market quote engine storing historical price candles and tick details.
- **Vector Store / FTS5**: Layered memory system using SQLite Virtual FTS5 tables (`episodes_fts`) for semantic text search and `sqlite-vec` (with a BM25 tokenizer fallback) for vector embedding memory search.

### 3.4 Rust Extension (`aletheia_rust`) & Sidecar (`aletheia-engine`)
- **PyO3 Module**: [aletheia_rust/src/lib.rs](file:///c:/Aletheia/aletheia_rust/src/lib.rs) exports portfolio VaR95, tax computation, scenario-projector, Black-Scholes pricing, Fama-French loadings, technical indicators (SMA/EMA/RSI/MACD/BB/VWAP), and Brier calibration scores to Python.
- **Engine Sidecar**: AXUM-based HTTP server listening on port `18899`. `ComputeClient` automatically directs workloads to this sidecar to release the Python GIL, falling back to PyO3 automatically if the sidecar is offline.

---

## 4. Feature Completion Matrix

| Feature | Phase/Sprint | Files Involved | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **5-Agent Pipeline** | Phase 1/2 | `graph_flow.py`, `services.py` | **✅ Done** | Resilient node fallback, timeout & skipped nodes implemented. |
| **SQLite + DuckDB Storage** | Phase 1 | `duckdb_store.py`, `sqlite_store.py` | **✅ Done** | SQLite for transactions, DuckDB for analytical quotes. |
| **FastAPI Backend** | Phase 1 | `routes.py`, `main.py` | **✅ Done** | Full REST surface + WebSockets for thought streaming. |
| **Tauri Desktop Shell** | Phase 1 | `desktop/` | **✅ Done** | Frontend static embedding works. Python + Rust sidecar auto-launch and system tray are real; distribution-grade `externalBin` bundling is not. |
| **CLI & Setup Wizard** | Phase 1/4 | `cli/main.py`, `cli/config.py` | **✅ Done** | Wizard guides settings & API keys validation. |
| **Agent Role Contracts** | Phase 2.5 | `models.py` | **✅ Done** | Pydantic contracts validated at type & runtime. |
| **Debate & PM Node** | Phase 2.5 | `graph_flow.py` | **✅ Done** | Re-prompts Oracle/Sentinel; PM enforces size/exposure caps. |
| **Working & Episodic Memory** | Phase 3/3.5 | `episodic.py`, `working_memory.py` | **✅ Done** | 3-tier memory store with SQLite FTS5 index. |
| **Vector Memory (RAG)** | Phase 3.5 | `vector_store.py` | **✅ Done** | ChromaDB/sqlite-vec + nomic-embed-text via Ollama. |
| **Technical Indicators** | Sprint 2A/B | `lib.rs`, `main.rs` | **✅ Done** | Completed technical math library in Rust sidecar. |
| **Fama-French Model** | Sprint 2.5 | `lib.rs`, `main.rs` | **✅ Done** | 3-factor regression model executed in Rust. |
| **Interactive Paper Trading**| Sprint 3C | `paper_trader.py`, `storage.py` | **✅ Done** | Fully integrated in UI with manual close/settle action. |
| **Zerodha Portfolio Sync** | Sprint 2D | `zerodha.py`, `routes.py` | **✅ Done** | Syncs Indian equity holdings with mock fallback. |
| **Shadow Account (Paper Trading)** | Sprint 3C | `extensions/shadow_account/` | **✅ Done** | `EntryExitScanner` auto-generates trades from Oracle signals; SQLite persistence, equity curve, `ShadowTrader.tsx` frontend page all real. |
| **Live Market Feed** | Sprint 3A | `aletheia-stream` | 🔲 Planned | Confirmed absent — `aletheia_engine` has zero websocket deps; genuinely the biggest remaining backend gap. |
| **PDF/Excel Report Exporter** | Sprint 4A | `reporting/exporter.py` | **✅ Done** | Jinja2 + WeasyPrint (HTML fallback if not installed) + openpyxl, wired to `GET /runs/{id}/export?format=pdf\|excel`. |
| **Backtest Frontend Page** | Sprint 3B | `pages/Backtest.tsx` | **✅ Done** | Built 2026-09-04 — form, metrics, equity curve, orders table. |
| **Hypotheses Frontend Page** | Sprint 3B | `pages/Hypotheses.tsx` | **✅ Done** | Built 2026-09-04 alongside three backend bug fixes (`backtest_run_id` persistence, `Evidence` field-name mismatch, missing `link-backtest` endpoint — see `docs/ROADMAP.md` §1D). All five endpoints were curl-tested end-to-end against a running backend to confirm the request/response shapes the page uses; the page itself is typecheck/build-verified but not yet exercised in a browser (Chrome extension unavailable this session). |

---

## 5. Dependencies & Integrations

### Python Packages (`pyproject.toml`)
- **Core Frameworks**: `fastapi`, `uvicorn`, `langgraph`, `langchain`, `pydantic-settings`
- **Data & Computation**: `pandas`, `numpy`, `scipy`, `duckdb`
- **API Clients**: `yfinance`, `ccxt`
- **Security & Config**: `cryptography`, `keyring`, `python-dotenv`

### External Integrations
- **Local Models**: Ollama (`qwen3.5:9b` or `mistral:7b` for local ReAct execution).
- **Frontier LLMs**: OpenAI (GPT-4o), Anthropic (Claude 3.5), Google (Gemini 1.5).
- **Brokers**: Zerodha Kite API connector blueprint.
- **Signals**: TradingView webhook payload connector.

---

## 6. Database Schemas

### 6.1 SQLite (`aletheia.db` & `execution.sqlite3`)
```sql
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    prompt TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT,
    result_json TEXT
);

CREATE TABLE agent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL FOREIGN KEY REFERENCES runs(run_id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload_json TEXT
);

CREATE TABLE paper_trades (
    trade_id TEXT PRIMARY KEY,
    run_id TEXT,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    simulated_qty REAL NOT NULL,
    simulated_fill_price REAL NOT NULL,
    simulated_pnl REAL NOT NULL,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE paper_positions (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    quantity REAL NOT NULL,
    average_price REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (symbol, exchange)
);
```

### 6.2 DuckDB (`quotes.duckdb`)
```sql
CREATE TABLE market_quotes (
    symbol VARCHAR,
    exchange VARCHAR,
    currency VARCHAR,
    close DOUBLE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    volume DOUBLE,
    as_of TIMESTAMP,
    provider VARCHAR
);
```

---

## 7. Known Issues & Blockers

1. **Windows File Locks**: Windows Defender may lock `.rcgu.o` and `.rmeta` build files inside Rust target directories. Workaround: Exclude the project target folder from antivirus scans.
2. **PyO3 Stale Installations**: When using `maturin develop`, python processes may lock PyO3 libraries. Terminate python prior to maturin upgrades.
3. **Mypy Baseline Debt**: `mypy-baseline.txt` snapshots ~232 pre-existing errors (mostly missing return-type annotations, concentrated in `core/compute/client.py`, `cli/main.py`, `core/tools/remember_tool.py`). CI only fails on *new* errors not in that file — see `CONTRIBUTING.md` for how to re-sync it as errors get fixed for real.
4. ~~**pyo3 0.22**~~ — Done. Upgraded to `pyo3 = "0.29"` (was pinned to `0.22`, which had one live advisory, `RUSTSEC-2026-0177`). Breaking changes handled: `PyDict::new_bound()` → `PyDict::new()`, `.downcast_into()` → `.cast_into()`, and 18 `#[pyfunction]`s returning `PyResult<PyObject>` changed to `PyResult<Bound<'py, PyAny>>` (the old signature became ambiguous under 0.29's new `IntoPyObject` trait resolution). `RUSTSEC-2026-0177` is no longer in CI's ignore list — it's fixed for real now, not silenced.

---

## 8. Quick Start Guide (For Claude Code)

### Setup & Installation
```powershell
# 1. Activate Virtual Environment
.venv\Scripts\Activate.ps1

# 2. Build Rust Extension
cd aletheia_rust
.venv\Scripts\python.exe -m pip install maturin
.venv\Scripts\python.exe -m maturin develop
cd ..

# 3. Initialize Settings Wizard
.venv\Scripts\python.exe -m aletheia config init
```

### Running Backend Services
```powershell
# Start Rust Compute Sidecar (Port 18899)
.\aletheia_engine\target\release\aletheia-engine.exe

# Start Python FastAPI server (Port 8899)
.venv\Scripts\python.exe -m uvicorn aletheia.core.main:app --port 8899
```

### Running Frontend
```powershell
cd frontend
npm install
npm run dev
```

### Testing & Verification
```powershell
# Run the complete test suite
.venv\Scripts\pytest tests/ -v

# Run linting checks
.venv\Scripts\python.exe -m ruff check aletheia/
```

---

## 9. Annotated File Tree

```
Aletheia/
├── aletheia/
│   ├── cli/                    # CLI command implementations (typer)
│   │   ├── benchmark.py        # Benchmark runner & outputs
│   │   ├── compare.py          # Compare two agent run results
│   │   ├── main.py             # CLI entrypoint
│   │   └── paper_trades.py     # Paper trading CLI commands
│   ├── config/
│   │   └── config_manager.py   # Config loader/saver with key validation
│   ├── core/                   # Core business logic
│   │   ├── agent/              # ReActLoop, AgentContext, agent configurations
│   │   ├── api/                # FastAPI routes, dependencies, security middleware
│   │   ├── compute/            # ComputeClient (axum server client + PyO3 fallback)
│   │   ├── config/             # Pydantic Settings settings.py
│   │   ├── db/                 # DuckDB and SQLite stores
│   │   ├── execution/          # Position sizing, PM constraints override logic
│   │   └── memory/             # Episodic memory and ChromaDB vector store
│   ├── extensions/             # Extensions layer
│   │   ├── agents/             # Optional sentiment/fundamental agents
│   │   ├── brokers/            # Zerodha Kite and TradingView Webhooks
│   │   └── shadow_account/     # Shadow trading state machines
│   └── factors/                # Alpha factor calculation library
│       ├── ic_scorer.py        # Information Coefficient scorer
│       └── momentum.py         # Heuristic alpha signals
├── aletheia_engine/            # standalone Axum Rust Compute Sidecar (18899)
├── aletheia_rust/              # PyO3 Rust extension modules (VaR, Greeks, Technicals)
├── alembic/                    # SQLite database schema migrations
├── desktop/                    # Tauri desktop project config
└── frontend/                   # React 19 + Vite dashboard
```

---

## 10. Reference Section

- **To write new agents**: Ensure they inherit from the correct contract model in [aletheia/core/models.py](file:///c:/Aletheia/aletheia/core/models.py) to prevent class definition contract validation errors.
- **To modify compute calculations**: Edit [aletheia_rust/src/lib.rs](file:///c:/Aletheia/aletheia_rust/src/lib.rs) and re-run `maturin develop` inside your virtual environment.
- **Next High Priority Items** (reconciled against actual code 2026-09-03 —
  see `docs/ROADMAP.md` for full detail on each):
  1. Implement `aletheia-stream` in the Rust sidecar for WebSocket
     Binance/NSE live pricing — confirmed completely unbuilt, the biggest
     single remaining backend gap.
  2. Implement native Tauri desktop notifications and deep links
     (`aletheia://run/{id}`) — sidecar auto-launch and system tray are
     already done, these two are what's left in Sprint 4B.
  3. Hypothesis auto-validation (backtest auto-runs on propose, auto-advance
     on a Sharpe threshold) — the registry and Hypotheses page are both now
     real; `transition()` is still only ever called manually.

  (pyo3 `0.22` → `0.29` is done as of 2026-09-04, and the Backtest and
  Hypotheses frontend pages are done as of 2026-09-04 — neither is on this
  list anymore.)
