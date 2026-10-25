# Agent Instructions

## Start Here
- **Read `docs/PROJECT_STATE.md` first.** It is the single source of truth for current status: what works, what is verified (and how) versus unverified, the runbook, decisions, and prioritized open items. Update it when you finish significant work. (`CLAUDE_CODE_HANDOFF.md` and `docs/KNOWLEDGE_GRAPH.md` are older.)
- **Do not commit until the user says so.** They commit everything at once at the end.
- **Never `pip install` a vendor SDK into `.venv`** (it broke `requests`/`aiohttp`/`ccxt` once). Use an isolated venv, and run `pip check` after any install.
- **Report verification honestly.** Prefer testing against the real service or a real browser over mocks, and label anything not run on a real account as unverified.
- Tests must stay isolated from `./data` (see `tests/conftest.py`); never let a test write to the developer's real databases.
- Signals: the Oracle signal failed its backtest vs Nifty. Do not present BUY/REDUCE as reliable.

## Environment Setup & Package Manager
- Python: Use `.venv\Scripts\python.exe` and `.venv\Scripts\pytest` explicitly on Windows.
- Rust: Cargo inside `aletheia_rust/` and `aletheia_engine/`.
- Frontend: Use **npm** inside `frontend/`.

## File-Scoped Commands
| Task | Command |
| :--- | :--- |
| Test Python | `.venv\Scripts\pytest <file_path>` |
| Test Rust | `cargo test -p aletheia_rust` |
| Lint Python | `.venv\Scripts\python.exe -m ruff check <file_path>` |
| Format Python | `.venv\Scripts\python.exe -m ruff format <file_path>` |
| Build Frontend | `npm run build` inside `frontend/` |

## Commit Attribution
No `Co-Authored-By` trailer or other AI attribution on commits. The repo owner is the sole author; commits use their own configured git identity only.

## Key Conventions
- **Base Role Contracts**: All agents must inherit from the correct base class in `aletheia/core/models.py`.
- **Rust Sidecar Fallback**: Do not call `aletheia_rust` directly from agent code; go through `ComputeClient` to ensure fallback works.
- **SQLite & DuckDB**: Keep transactions in SQLite and OHLCV time-series analytics in DuckDB.
