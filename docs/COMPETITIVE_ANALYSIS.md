# ALETHEIA — Competitive Analysis & Positioning

**Last updated: 2026-06-27**

---

## Peer Projects Analyzed

| Project | Org | Focus | Stars (~) |
|---|---|---|---|
| **Vibe-Trading** | HKUDS | 29-agent swarm, NL strategy generation, DAG orchestration | ~5k+ |
| **FinGPT** | AI4Finance | Domain-fine-tuned LLMs, LoRA, RAG on financial data | ~20k+ |
| **OpenBB** | OpenBB | Open data platform, 100+ data providers, MCP native, Workspace UI | ~35k+ |
| **PrimoAgent** | Community | 4-agent sequential LangGraph pipeline, daily signals | ~1k |
| **LangAlpha** | Ginlix AI | Persistent workspaces, PTC (code execution), iterative Bayesian research | N/A |
| **FinRobot** | AI4Finance | Financial CoT, multi-agent report generation | ~3k |

---

## Feature Comparison

| Capability | Vibe-Trading | FinGPT | OpenBB | PrimoAgent | **Aletheia (Now)** |
|---|:---:|:---:|:---:|:---:|:---:|
| Multi-agent orchestration | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Pydantic role contracts** | ❌ | ❌ | ❌ | ❌ | ✅ **Unique** |
| **Agent debate / disagreement node** | ✅ | ⚠️ | ❌ | ❌ | ✅ |
| **Portfolio Manager override layer** | ❌ | ❌ | ❌ | ⚠️ | ✅ **Unique** |
| **India STCG/LTCG tax engine (Rust)** | ❌ | ❌ | ❌ | ❌ | ✅ **Unique** |
| **Run-level partial-failure resilience** | ❌ | ❌ | ❌ | ❌ | ✅ **Unique** |
| **Configurable graph (node-skip)** | ✅ skill system | ❌ | ❌ | ❌ | ✅ |
| Rust performance core | ❌ | ❌ | ⚠️ Some | ❌ | ✅ 30+ functions |
| Rust sidecar (zero-GIL compute) | ❌ | ❌ | ❌ | ❌ | ✅ **Unique** |
| Live WebSocket market feed | ✅ | ⚠️ | ✅ | ❌ | ❌ Sprint 3A |
| Episodic memory (FTS) | ✅ | ⚠️ | ❌ | ❌ | ✅ |
| Vector / semantic memory | ✅ | ✅ | ❌ | ❌ | ❌ Sprint 3.5 |
| Paper trading / shadow account | ✅ | ⚠️ | ✅ | ❌ | ⚠️ Model only |
| LLM multi-provider router | ✅ | ✅ | ✅ | ❌ | ✅ |
| MCP native integration | ✅ 30+ tools | ❌ | ✅ Native | ❌ | ✅ 13 tools (`aletheia mcp`) |
| Backtest (real data) | ✅ | ⚠️ | ✅ | ❌ | ✅ |
| LangSmith / observability | ✅ | ⚠️ | ✅ | ❌ | ⚠️ Stub |
| PDF report generation | ⚠️ | ✅ | ✅ | ❌ | ❌ Sprint 4A |
| Frontend UI | ⚠️ | ❌ | ✅ Enterprise | ❌ | ⚠️ Scaffolded |
| Desktop app (Tauri) | ❌ | ❌ | ❌ | ❌ | ⚠️ Compiles, unwired |
| Options pricing (Black-Scholes, Greeks) | ❌ | ❌ | ✅ | ❌ | ✅ Rust |
| Broker connectors | ✅ | ❌ | ✅ 100+ | ❌ | ⚠️ Zerodha blueprint |
| Domain fine-tuned local LLM | ❌ | ✅ | ❌ | ❌ | ❌ Sprint 5 |
| NSE/BSE-specific signals | ❌ | ❌ | ⚠️ | ❌ | ❌ Sprint 3.5 |

### Overall Parity Score
| vs. | Parity |
|---|---|
| Vibe-Trading (best-in-class for agents) | **~60%** |
| OpenBB (best-in-class for data infra) | **~45%** (not the right comparison — different layer) |
| FinGPT (best-in-class for LLM) | **~50%** |

> **Note**: Aletheia's architecture quality (contracts, resilience, Rust core) exceeds all peers in several specific dimensions. The gap is in experience-layer features (live feed, frontend, paper trading).

---

## Aletheia's Genuine Moats (no peer has these combined)

### 1. Type-Safe Agent Role Enforcement
Pydantic contracts enforced at class-definition time (`__init_subclass__`) and at runtime (`model_validator`) prevent any agent from emitting output outside its defined mandate. This is unique across all open-source financial agent projects. The architecture ensures LLM hallucinations that violate role boundaries are caught structurally, not just by prompt engineering.

### 2. India-Specific Financial Intelligence
The Rust tax engine (`build_tax_summary_rust`, `build_scenario_rust`) implements SEBI-compliant STCG/LTCG rules for Indian equities. This is not available in any Western-focused peer. Combined with NSE/BSE ticker normalization and the Zerodha broker blueprint, this positions Aletheia as the only open-source platform built specifically for Indian retail investors.

### 3. Partial-Failure Resilience with Gap-Noting
The run-level state machine persists `partial` state when one or more agents fail. Scribe always produces a narrative even in degraded mode, explicitly noting what data is missing. This is production-grade resilience no peer implements.

### 4. Zero-GIL Compute Path (Rust Sidecar)
The `aletheia-engine` sidecar offloads all heavy compute (indicators, VaR, portfolio optimization, Monte Carlo) to Rust with its own DuckDB connection pool. Python never blocks on compute. No peer has a dedicated Rust compute sidecar.

### 5. Configurable Graph Without Code Changes
The LangGraph topology is configurable via `agent_config` flags — skip Sage if no tax jurisdiction is set, skip Sentinel for quick-mode runs. This enables different "preset" run configurations without changing the graph code, similar to Vibe-Trading's skill system but implemented within LangGraph's native paradigm.

---

## Competitive Strategy

### Short-Term (Sprint 3): Close the Experience Gap
The engine is already ahead in design. The live feed, frontend wire-up, and paper trading are what make peers feel more "real" to users. Sprint 3 is entirely focused on closing this gap.

### Medium-Term (Sprint 3.5–4): Double Down on Differentiation
Vector memory + domain fine-tuning + NSE/BSE specific data creates a moat that Western-focused peers (Vibe-Trading, OpenBB) structurally cannot replicate without significant market-specific work.

### Long-Term (Sprint 5+): Become the OpenBB for India
OpenBB is the "data infrastructure" layer for the Western market. Aletheia can become the equivalent for the Indian market — a local-first, privacy-preserving financial intelligence platform that speaks NSE/BSE natively, implements SEBI compliance rules, and integrates with Indian brokers (Zerodha, Angel One, Upstox).

---

## Technology Choices — Rationale vs. Peers

| Decision | Aletheia Choice | Peer Alternative | Rationale |
|---|---|---|---|
| Orchestration | LangGraph | CrewAI (Vibe-Trading uses DAG) | LangGraph has better state management and partial-failure handling |
| Performance | Rust + PyO3 + sidecar | Pure Python (most peers) | Zero-GIL compute for real-time VaR, portfolio optimization |
| Storage | SQLite + DuckDB | PostgreSQL (OpenBB), plain files | Local-first, zero-ops for single-user deployment |
| Memory | FTS5 + BM25 | ChromaDB (vector) — most peers | BM25 is fast, explainable, offline. Vector upgrade planned. |
| Desktop | Tauri (Rust) | Electron (most desktop tools) | ~10x smaller binary, Rust native, no Chromium bundle |
| Tax | Custom Rust engine | Ignored (all peers) | India-specific — not replicable from generic tools |
| Frontend | React 19 + Vite | Next.js (most full-stack) | Simpler for the scope, works as Tauri webview |
