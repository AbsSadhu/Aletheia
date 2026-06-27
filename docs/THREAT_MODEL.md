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
