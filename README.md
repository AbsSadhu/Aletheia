# <p align="center"><img src="docs/images/banner.png" alt="Aletheia Banner" width="100%"></p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/Project%20Status-Active%20%2F%20In%20Development-orange.svg" alt="Project Status"></a>
  <a href="#"><img src="https://img.shields.io/badge/Python-3.11%2B-blue.svg?logo=python&logoColor=white" alt="Python"></a>
  <a href="#"><img src="https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="#"><img src="https://img.shields.io/badge/React-19-20232A?style=flat&logo=react&logoColor=61DAFB" alt="React"></a>
  <a href="#"><img src="https://img.shields.io/badge/Tauri-2.0-FFC131?style=flat&logo=tauri&logoColor=white" alt="Tauri"></a>
  <a href="#"><img src="https://img.shields.io/badge/Rust-2021-000000?style=flat&logo=rust&logoColor=white" alt="Rust"></a>
  <a href="#"><img src="https://img.shields.io/badge/Orchestration-LangGraph-darkgreen" alt="LangGraph"></a>
  <a href="#"><img src="https://img.shields.io/badge/Analytics-DuckDB-yellow" alt="DuckDB"></a>
</p>

---

## 🔮 Overview

**Aletheia** is a local-first, open-source, multi-agent financial intelligence platform specifically tailored for the **Indian stock and crypto markets**. It runs local LLMs (via Ollama) alongside heuristic mathematical engines to gather data, assess risk, calculate tax drag, and synthesize actionable market insights—all while maintaining complete data privacy on your local machine.

The architecture separates the authoritative **Python/FastAPI** agentic core, high-performance calculations written in **Rust/PyO3**, and a beautiful **React/Vite** frontend packaged inside a **Tauri desktop shell**.

---

## 🚧 Project Status & Roadmap

> [!IMPORTANT]
> **Aletheia is currently under active development.**
> The multi-agent orchestration engine, the React/Tauri desktop app, and a terminal dashboard (`aletheia tui`) are all functional and verified running end-to-end locally, backed by 138 Python unit tests, 32 Rust tests, and 8 frontend tests.

### Development Progress: Sprint 2.5 & Sprint 3.5 Completed ✅

All nine intelligence agents, structured debate loops, deterministic Portfolio Manager limits, vector memories, and SEBI compliance logs are fully implemented and running locally.

| Phase | Component | Focus | Status |
| :---: | :--- | :--- | :---: |
| **1** | **Skeleton & Data Layer** | Monorepo layout, Pydantic schema validation, Data providers (yfinance/CCXT) | ✅ Done |
| **2** | **Engine Foundations** | LangGraph orchestration, heuristic agents, Rust/PyO3 math backend | ✅ Done |
| **2.5** | **Resilience & Org-Chart** | Per-node timeouts, partial-failure tolerance, Pydantic role contracts, Debate/PM node | ✅ Done |
| **3** | **Rich Frontend & Live Streaming** | React UI, WebSocket agent reasoning stream visualization, desktop (Tauri) app | ✅ Done |
| **3.5** | **Intelligence Upgrade** | sqlite-vec RAG vector memory, news sentiment classifier, options chain metrics, Scribe-Critic loop | ✅ Done |
| **4** | **LLM Integration** | Ollama local model support, prompt synthesis, CLI wizard | ✅ Done (Basic) |
| **4.5** | **Terminal Dashboard** | `aletheia tui` — portfolio, live run streaming, paper trades, recent runs | ✅ Done |
| **5** | **Production Hardening** | Encryption at rest, PDF reports, Docker build fixed, CI test coverage | 🟡 Partial — K8s deployment untested, dependency version bumps pending |

---

## 🖥️ Preview

The React/Tauri desktop app and terminal dashboard are both functional today — the mockup below predates them; run `aletheia tui` or the desktop app to see the real thing. It shows portfolio composition, capital gains tax drag projection, risk profile gauges, and real-time agent output streaming.

<p align="center">
  <img src="docs/images/dashboard_mockup.png" alt="Aletheia Dashboard Preview" width="90%">
</p>

---

## 📐 Multi-Agent Orchestration Flow

Aletheia uses a concurrent/sequential pipeline built on **LangGraph** where agents collaborate to analyze a portfolio:

```mermaid
graph TD
    UI["Frontend / Desktop Shell"] -->|REST / WS| API["FastAPI Gateway"]
    API -->|Orchestrate| Engine["RunService (LangGraph StateGraph)"]

    subgraph Multi-Agent Intelligence Core & Org-Chart
        Engine --> Collector["Collector Agent (Data Normalization & Sourcing)"]

        Collector -->|Parallel Fan-Out| Oracle["Oracle Agent (Trend & Signals)"]
        Collector -->|Parallel Fan-Out| Sentinel["Sentinel Agent (Portfolio VaR & Regimes)"]
        Collector -->|Parallel Fan-Out| Sentiment["Sentiment Agent (News Classifier)"]
        Collector -->|Parallel Fan-Out| Fundamental["Fundamental Agent (Valuation Multiples)"]
        Collector -->|Parallel Fan-Out| OptionsFlow["Options Flow Agent (PCR, IV Rank, Max Pain)"]

        Oracle -.->|Disagreement Dialog Loop| DebateNode{"Debate Node"}
        Sentinel -.->|Disagreement Dialog Loop| DebateNode

        DebateNode -->|Consensus or Registered Disagreement| PMNode["Portfolio Manager Node (Deterministic Rules & Limits)"]
        Sentiment --> PMNode
        Fundamental --> PMNode
        OptionsFlow --> PMNode

        PMNode --> Sage["Sage Agent (Tax-Aware Indian Market Projections)"]

        Sage -->|Fan-In / Join| Scribe["Scribe Agent (Narrative Synthesis)"]
        Scribe --> Critic["Critic Agent (Reflexion Auditor - Max 2 Runs)"]

        Critic -->|Failed / Revise| Scribe
        Critic -->|Passed / Complete| FinalOutput["Final Scribe Output"]
    end

    subgraph Data & Storage Layer
        Collector --> DuckDB[("DuckDB (Quotes & Analytical OHLCV)")]
        Engine --> SQLite[("SQLite (Transactional Runs, Agent Status, SEBI Logs)")]
        Engine --> VecStore[("sqlite-vec (Vector RAG Memory)")]
    end

    FinalOutput --> API
```

---

## 🏛️ Agent Org-Chart Discipline

To enforce institutional-grade risk management and prevent LLM hallucinations from bypassing guidelines, Aletheia implements a strict Pydantic role contract layout using class-level `__init_subclass__` and runtime `model_validator` methods:

| Role Contract | Base Class | Enabled Agents | Mandate Rules |
| :--- | :--- | :--- | :--- |
| **Analyst** | `AnalystContract` | Collector, Oracle, Sentiment, Fundamental, OptionsFlow | May only emit raw quotes, signals, and confidence scores. **Forbidden from generating recommendations or decisions.** |
| **Risk / Constraint** | `RiskConstraintContract` | Sentinel, Sage | Applies exposure, VaR, and tax drag constraints. **Forbidden from producing recommendations or final synthesis.** |
| **Synthesis** | `SynthesisContract` | Scribe | Consolidates all inputs into final narrative and flags unresolved disagreements. **Forbidden from introducing raw, unvalidated market data.** |

---

## 🧠 Meet the Agents

1. **📥 The Collector Agent** (Analyst)
   Normalizes tickers (NSE/BSE formats), fetches market quotes via a provider chain fallback, and logs provenance.
2. **📈 The Oracle Agent** (Analyst)
   Analyzes market momentum across multiple timeframes (1D, 1W, 1M) and computes trend signals.
3. **📰 The Sentiment Agent** (Analyst)
   Scrapes NSE corporate announcements and MoneyControl RSS news feeds to classify sentiment (bullish/bearish).
4. **📊 The Fundamental Agent** (Analyst)
   Fetches financial multiples (P/E ratios, promoter holdings) from Yahoo Finance and public NSE indices to flags valuations.
5. **⛓️ The Options Flow Agent** (Analyst)
   Parses public NSE option chains, computing Put-Call Ratio (PCR), IV Rank, and option pain levels.
6. **🛡️ The Sentinel Agent** (Risk)
   Evaluates portfolio Value-at-Risk (VaR95) and market regimes (using high-performance PyO3 hidden Markov models).
7. **🌾 The Sage Agent** (Risk)
   Runs India-specific tax projections (STCG/LTCG rules) to calculate tax drag on future gains.
8. **✍️ The Scribe Agent** (Synthesis)
   Synthesizes agent outputs, notes gaps, and drafts reports.
9. **🕵️ The Critic Agent** (Auditor)
   Performs reflexion self-audits on the Scribe report, checking criteria alignment and requesting revisions if criteria fail.

---

## 🛡️ Resilience & Production Hardening

- **Per-Node Timeouts:** Nodes are executed within `asyncio.wait_for` wrappers to prevent network hanging.
- **Partial-Failure Handling:** Scribe produces report summaries even when individual non-critical agents fail, noting data gaps in warning headers.
- **Rate Limiting:** Protects API endpoints with token bucket rate limiters.
- **Append-Only SEBI Log:** All emitted recommendations are stored in an append-only, immutable SQLite database with triggers preventing deletions or updates, plus a SHA-256 hash chain (each entry links to the previous one's hash) so tampering that bypasses the triggers via raw file access is still detectable — see `GET /api/v1/compliance/verify`.
- **AES-256 Encryption:** Encrypts API payloads and intermediate run states stored in SQLite at rest.

---

## 🛠️ Architecture & Tech Stack

- **Backend:** Python 3.11+, FastAPI, LangGraph, Pydantic v2
- **Performance:** Rust, PyO3 bindings (for portfolio optimization, HMM regimes, and tax math)
- **Database:** SQLite (system state/runs/SEBI logs), DuckDB (analytical market data), `sqlite-vec` (vector RAG memories)
- **Frontend:** React 19, TypeScript, Vite
- **Desktop Wrapper:** Tauri v2
- **Local LLM:** Ollama (defaulting to Llama-3/Qwen)

---

## 📋 Developer CLI Quick Look

For developers looking to inspect the engine locally, the API provides full endpoint access:

```bash
# Analyze a portfolio
POST /api/v1/runs
{
  "prompt": "Analyze an India-first starter portfolio",
  "portfolio": {
    "name": "Starter",
    "holdings": [
      { "symbol": "RELIANCE", "quantity": 5, "average_price": 2500, "asset_type": "equity", "exchange": "NSE", "tax_profile": "equity" }
    ]
  }
}

# Query SEBI Compliance Logs
GET /api/v1/compliance/log?limit=20

# Search Vector Memory RAG
GET /api/v1/memory/vector-search?q=Reliance
```

Detailed onboarding docs, threat models, and architectural guides are located in the [docs/](docs/) directory.

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, how to run the Python/Rust/frontend test suites, and PR expectations.

---

## ⚖️ License

Aletheia is open-source software licensed under the MIT License. See [LICENSE](LICENSE) for details.
