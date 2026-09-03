# Contributing to Aletheia

Thanks for considering a contribution. This guide covers setup, testing, and
PR expectations for human contributors. If you're an AI coding agent working
in this repo, read [`AGENTS.md`](AGENTS.md) / [`CLAUDE.md`](CLAUDE.md)
instead — they cover the same ground plus agent-specific conventions
(base role contracts, commit attribution, the `ComputeClient` fallback rule)
that don't need repeating here.

## Prerequisites

- **Python 3.11+** and [Poetry](https://python-poetry.org/)
- **Rust** (stable toolchain) — needed to build `aletheia_rust` (PyO3
  extension) and `aletheia_engine` (compute sidecar); required even for the
  Docker image now, since the build stage compiles the Rust extension there
- **Node 20+** and npm — for the React frontend
- **[Ollama](https://ollama.com/)** running locally if you want to exercise
  the LLM-backed agents without cloud API keys (the default provider)

## Setup

```powershell
git clone <this-repo>
cd Aletheia

# Python
poetry install
cd aletheia_rust && maturin develop && cd ..

# Frontend
cd frontend && npm install && cd ..

# Config
copy .env.example .env
# Edit .env: at minimum nothing is required to run locally — the app
# defaults to open (no API key) auth and Ollama for LLM calls. See
# SECURITY.md before exposing the API beyond 127.0.0.1.
```

## Running it

| What | Command |
| :--- | :--- |
| Backend only | `.venv\Scripts\aletheia.cmd serve` (or `poetry run aletheia serve`) |
| Frontend dev server | `npm run dev` inside `frontend/` |
| Desktop app | `cd desktop/src-tauri && cargo run` (needs the Rust binaries and `.venv` in place — see `main.rs` for how it locates them) |
| Terminal dashboard | `.venv\Scripts\aletheia.cmd tui` (needs a backend already running) |
| MCP server (stdio) | `.venv\Scripts\aletheia.cmd mcp` — point an MCP client (Claude Desktop, Cursor) at this command to expose the tool registry (market data, backtests, fundamentals, news, portfolio analytics, etc.) as MCP tools |

## Running the tests

This project has three independent test suites — a PR touching more than one
language should pass all of the relevant ones, not just the Python suite.

| Suite | Command |
| :--- | :--- |
| Python (unit) | `.venv\Scripts\pytest tests\unit -q` |
| Python (single file) | `.venv\Scripts\pytest <file_path>` |
| Rust — `aletheia_rust` | `cargo test --lib` inside `aletheia_rust/` |
| Rust — `aletheia_engine` | `cargo test` inside `aletheia_engine/` |
| Frontend | `npm run test` inside `frontend/` |
| Frontend build/typecheck | `npm run build` inside `frontend/` |

All of the above run in CI (`.github/workflows/ci.yml`) on every PR and are
blocking merge gates — including `tests/integration` and the Rust dependency
audits (`aletheia_rust`, `aletheia_engine`), which used to be
`continue-on-error` but no longer are. Unit-test coverage is also gated
(`--cov-fail-under=35`, see the comment in `ci.yml` for the honest-floor
rationale) — don't drop coverage below that on a PR.

## Before opening a PR

- Run `pre-commit run --all-files` — this repo uses `ruff` (lint + format)
  and `detect-secrets` (with a committed `.secrets.baseline`; if a hook flags
  a genuine new false positive, update the baseline with
  `detect-secrets scan --exclude-files '\.env\.example$' --exclude-files '\.env\.test$' --exclude-files '^tests/' > .secrets.baseline`
  rather than disabling the hook). The `don't commit to branch` hook will
  always report "Failed" when you run it standalone like this on `main` —
  that's expected, it only actually blocks a real `git commit` on `main`.
- `.venv\Scripts\python.exe -m mypy aletheia` **is** a merge gate, but only
  against a baseline: `mypy-baseline.txt` snapshots ~232 pre-existing errors
  (mostly missing return-type annotations), and CI only fails on errors *not*
  already in that file — i.e. new type errors in new/changed code. Run
  `poetry run mypy aletheia | poetry run mypy-baseline filter` locally to see
  what CI sees. New code should still be typed; don't feel obligated to fix
  unrelated pre-existing errors in files you're just passing through, but if
  you do fix some for real, re-sync the baseline
  (`poetry run mypy aletheia | poetry run mypy-baseline sync`) in the same PR.
- If you touched anything under `aletheia/core/api/` or `aletheia/core/api/routers/`,
  sanity-check the route list didn't change unexpectedly: hit `/docs` on a
  running backend and eyeball the endpoint list, or diff `app.openapi()`'s
  `paths` before/after.
- Never commit `.env` (it's gitignored) or hardcode credentials — see
  [`SECURITY.md`](SECURITY.md) for the actual auth/encryption model.

## Where things live

The architecture is documented in the README's Mermaid diagram and in
[`docs/`](docs/) (`KNOWLEDGE_GRAPH.md`, `THREAT_MODEL.md`, `ROADMAP.md`,
ADRs). If you're about to add a new API endpoint, put it in the router file
matching its domain under `aletheia/core/api/routers/` rather than growing
a new god-file — see that directory's existing modules for the pattern.
