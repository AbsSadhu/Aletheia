# Windows Rust/Python Hybrid Development Guidelines

1. **Target Folder Exclusions**:
   - In hybrid Rust/Python codebases on Windows, Windows Defender may lock `.rcgu.o` and `.rmeta` files in cargo target directories.
   - If a build fails with `os error 32 (access denied/file in use)`, run `Remove-Item -Recurse -Force "path/to/target"` and advise the user to exclude the cargo `target/` directory in Windows Security settings.

2. **PyO3 Extension Upgrades & Maturin**:
   - If `maturin develop` fails with "cannot overwrite the installed extension module", stop all python processes (`Get-Process | Where-Object {$_.Name -match 'python|cargo'} | Stop-Process -Force`) and remove the stale directory `C:\Aletheia\.venv\Lib\site-packages\~letheia_rust` before retrying.

3. **Windows Python Execution**:
   - Never run raw `python` or `pytest` in terminal commands on Windows workspaces. Always run using `.venv\Scripts\python.exe` or `.venv\Scripts\pytest` explicitly to prevent escaping the virtual environment.

---

# Aletheia Agent Context — READ THIS FIRST

## What This Project Is

Aletheia is a **local-first, multi-agent financial intelligence platform** for the **Indian stock and crypto markets**. It is NOT a trading bot — it is an analysis and recommendation engine. All decisions stay with the user.

## Current Sprint: Sprint 3 — "Real Intelligence"

**The engine is complete. The experience layer is what's missing.**

Sprints 1, 2, and 2.5 are fully done. The next work is:
1. **Live market feed** (`aletheia-stream` Rust Tokio WebSocket — Binance + NSE/BSE)
2. **Frontend wire-up** (React pages are scaffolded but all data is mocked — connect to real API)
3. **Shadow account** (paper trading — model exists, API not wired)
4. **Real observability** (LangSmith tracing — currently a stub)

See `docs/ROADMAP.md` for the full checklist. See `docs/KNOWLEDGE_GRAPH.md` for the full architecture and gap map.

## Key Architecture Facts

- **5 agents**: Collector → (Oracle ‖ Sentinel) → Debate → PortfolioManager → Sage → Scribe
- **LangGraph StateGraph** orchestrates the pipeline
- **Rust sidecar** (`aletheia-engine` on :18899) handles all heavy compute — ZERO Python GIL blocking
- **PyO3 module** (`aletheia_rust`) is the fallback when the sidecar is not running
- **SQLite** = transactional data (runs, agent status, episodic memory, hypotheses)
- **DuckDB** = analytical data (market quotes, historical OHLCV)
- **Run state machine**: `pending → running → partial → complete → failed` — persisted per agent
- **Pydantic role contracts** enforce agent mandates at type-system level — unique vs. all peers

## Agent Role Contracts (DO NOT VIOLATE)

| Agent | Base Contract | Can Emit | Cannot Emit |
|---|---|---|---|
| Collector | `AnalystContract` | data, quotes, provenance | recommendations, final_decision |
| Oracle | `AnalystContract` | signal, confidence, reasoning | recommendations, final_decision |
| Sentinel | `RiskConstraintContract` | risk_score, var95, regime | quotes, recommendations |
| Sage | `RiskConstraintContract` | tax_drag, scenarios, projections | quotes, recommendations |
| Scribe | `SynthesisContract` | recommendations, executive_summary | raw quotes |

Violations at class-definition time → `TypeError`. Violations at runtime → `ValueError`. Do NOT add fields that violate these contracts.

## What's Unique About Aletheia (vs. Vibe-Trading, OpenBB, FinGPT)

1. **Pydantic role enforcement** — no other financial agent project has this
2. **India STCG/LTCG Rust tax engine** — completely absent from all Western peers
3. **Partial-failure resilience** — Scribe produces gap-noting reports even when agents fail
4. **Portfolio Manager override layer** — deterministic rule enforcement that LLMs cannot bypass
5. **Zero-GIL Rust sidecar** with its own DuckDB pool

## Files to Read Before Coding

| File | Why |
|---|---|
| `docs/KNOWLEDGE_GRAPH.md` | Full architecture graph, implemented vs. gap nodes, API surface |
| `docs/ROADMAP.md` | Sprint-by-sprint checklist of what's done and what's next |
| `docs/COMPETITIVE_ANALYSIS.md` | Why we made each technical decision |
| `docs/THREAT_MODEL.md` | Security boundaries and mitigations |
| `aletheia/core/models.py` | All Pydantic models + role contracts — read before touching agent outputs |
| `aletheia/core/api/routes.py` | Full API surface |
| `aletheia/core/db/sqlite_store.py` | Run state machine, agent status, all DB operations |
| `aletheia/core/llm/chat_llm.py` | LLM router — Ollama + OpenAI + Anthropic + circuit breaker |
| `aletheia/core/compute/client.py` | ComputeClient — always use this, never call Rust PyO3 directly from agents |
| `tests/integration/test_agent_org_chart.py` | 60-test suite for role contracts — run before any agent changes |

## Environment Setup

```powershell
# Activate venv (ALWAYS use explicit path on Windows)
.venv\Scripts\python.exe -m pip install -e .

# Run tests
.venv\Scripts\pytest tests/ -v

# Start Rust sidecar (optional, Python falls back to PyO3 if not running)
.\aletheia_engine\target\release\aletheia-engine.exe

# Start FastAPI
.venv\Scripts\python.exe -m uvicorn aletheia.main:app --port 8899
```

## DO NOT

- Run raw `python` or `pytest` — always use `.venv\Scripts\python.exe` / `.venv\Scripts\pytest`
- Add fields to agent output models without checking the role contract base class
- Call Rust PyO3 functions directly from agent code — always go through `ComputeClient`
- Commit `.env` — it is gitignored; use `.env.example` as the template
- Touch `aletheia_engine/target/` or `aletheia_rust/target/` — Windows Defender may lock files
