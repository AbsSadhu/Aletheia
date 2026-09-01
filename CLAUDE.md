# Agent Instructions

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
