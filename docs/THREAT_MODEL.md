# Threat Model: ALETHEIA Financial Intelligence Platform

This threat model outlines the security boundaries, assets, threats, and mitigations for the ALETHEIA platform.

## 1. System Boundaries & Assumptions

ALETHEIA is designed as a **local-first** application where domain logic, database storage, and agent reasoning run on the user's local machine.

### Core Assumptions:
- **Compromised Host**: We assume that if the host operating system or local machine is fully compromised (root/admin access), all stored databases, settings, and memory can be read. We do not attempt to protect against a compromised local machine.
- **Network Boundaries**: While local-first, the FastAPI backend exposes HTTP and WebSocket ports (`8899`/`8900`) which might be exposed to a Local Area Network (LAN) or bound to public interfaces.

---

## 2. Asset Classification

| Asset | Sensitivity | Location | Protection |
| --- | --- | --- | --- |
| **API Keys** (OpenAI, Anthropic) | High | `.env` file | OS file permissions |
| **Portfolio Holdings** | Medium | SQLite Database | Column-level AES-256 (Fernet) encryption |
| **Market Quotes & Cache** | Low | DuckDB Database | Native file encryption (AES-256-GCM) |
| **Agent Reasoning Traces** | Medium | SQLite Database | Column-level AES-256 (Fernet) encryption |

---

## 3. Threat Analysis & Mitigations

### 3.1. Unauthorized Local or Network API Access
- **Threat**: An attacker on the same LAN (or a remote client if port-forwarded) queries portfolio data or runs costly LLM prompts via the FastAPI endpoints.
- **Mitigation**:
  - Bound the FastAPI app to loopback (`127.0.0.1`) by default.
  - Implement request **rate limiting** (using a token-bucket algorithm) to prevent resource-exhaustion.
  - Enforce **X-API-Key** header validation on all endpoints.

### 3.2. Local Database Snooping (Data-at-Rest Leakage)
- **Threat**: Someone steals or reads the `aletheia.sqlite3` or `aletheia.duckdb` files from the filesystem.
- **Mitigation**:
  - Enable native transparent database encryption for DuckDB via `encryption_key`.
  - Implement column-level encryption (Fernet AES-256) for SQLite's sensitive JSON columns (`holdings_json`, `result_json`, `payload_json`).

### 3.3. Malicious Portfolio Data Injection (SQL / Command Injection)
- **Threat**: User-supplied portfolio names or ticker symbols contain special characters designed to inject SQL code or FTS5 query logic, or exhaust system memory.
- **Mitigation**:
  - Strict input validation using Pydantic regex constraints (limiting character sets to alphanumeric plus safe symbols).
  - Enforce strict range constraints on quantity and price fields.
  - Limit the maximum number of holdings per portfolio to 100.

### 3.4. Untrusted Code Execution (Agent-Generated Strategy Code)
- **Threat**: An LLM agent (Sage, Scribe, or the ReAct chat loop) autonomously
  writes and executes arbitrary Python — a "strategy" the model authors and
  runs without human review — which would be a remote-code-execution vector
  the moment any agent input is influenced by external/untrusted data (e.g.
  a scraped news article or a crafted portfolio field).
- **Audited, not assumed**: swept the codebase for `eval(`, `exec(`,
  `os.system`, `subprocess.*`, `pickle.loads`, `importlib.import_module`,
  and `spec.loader.exec_module` (2026-09-01). No code path constructs or
  executes agent/LLM-authored code strings anywhere — `hypotheses/registry.py`
  stores hypotheses as structured Pydantic data (never code), and
  `backtest/models.py`'s `strategy_name` is a plain string label matched
  against a fixed set of built-in strategies, not a code blob.
  The ReAct tool-calling loop (`core/tools/registry.py`) only ever invokes a
  fixed, typed Python method per tool the model can select by name — the
  model supplies structured arguments, never a code string to run.
  Two legitimate dynamic-module-loading mechanisms exist —
  `factors/registry.py`'s `_load_custom()` (`~/.aletheia/factors/custom/*.py`)
  and `core/infrastructure/plugins.py`'s `PluginManager`
  (`settings.plugin_dir`, default `./plugins`) — but both load only `.py`
  files the local user deliberately places on their own filesystem; no
  agent, LLM output, or network response writes to either directory
  anywhere in the codebase. This is the same trust boundary as any local
  tool's plugin folder, not an agent-controlled execution path.
- **Mitigation**: keep it that way — any future feature that has an agent
  *write* a file into `factors/custom/` or `plugin_dir` (not just read
  user-authored files there) would cross this boundary and needs its own
  sandboxing review before shipping.
