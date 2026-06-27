# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅ Yes     |
| < 0.1.0 | ❌ No      |

## Reporting a Vulnerability

Do **NOT** open a public issue for security vulnerabilities. Email `security@aletheia.local` with:
- A detailed description of the vulnerability
- Steps to reproduce (PoC code or requests)
- Impact assessment

We will acknowledge within 48 hours and coordinate a patched release.

---

## Implemented Security Controls

### Authentication & Rate Limiting
- All API endpoints require `X-API-Key` header (configured via `ALETHEIA_API_KEY` env var)
- Rate limiting via Rust token-bucket algorithm (PyO3 `RateLimiter`) — per-endpoint limits
- FastAPI dependency injection enforces auth on every route

### Encryption at Rest
- **SQLite**: Sensitive columns (`holdings_json`, `result_json`, `payload_json`) encrypted with Fernet AES-256
  - Key derived from `ALETHEIA_ENCRYPTION_KEY` env var
  - See `aletheia/core/security/encryption.py`
- **DuckDB**: File-level AES-256-GCM encryption via `encryption_key` setting

### Input Validation
- All user-supplied portfolio data validated via Pydantic with strict regex constraints
- Ticker symbols: `[A-Z0-9.-]{1,20}` — no special characters
- Quantity: `> 0`, Price: `> 0`, Holdings per portfolio: max 100
- Input sanitization on all FTS5 query paths to prevent injection

### Secret Management
- `.env` is gitignored; `.env.example` contains only placeholder values
- CI enforces: `.env` must not be tracked in git
- CI scans every commit diff for high-entropy API key patterns (`sk-*`, `sk-ant-*`, `xoxb-*`)

### Dependency Auditing (CI)
- `pip-audit` — Python dependencies, fails on medium+ severity
- `cargo audit` — Rust dependencies, via `actions-rust-lang/audit@v1`
- `npm audit --audit-level=high` — frontend dependencies

### Network
- FastAPI binds to `127.0.0.1` by default (loopback only)
- CORS configured to localhost origins only by default
- Rust sidecar (`aletheia-engine`) binds to `127.0.0.1:18899` only

---

## Threat Model

Full threat model: [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)

Key threat boundaries:
- **Compromised host**: Not in scope — local-first assumption
- **LAN exposure**: Mitigated by loopback binding + API key + rate limiting
- **Data-at-rest leakage**: Mitigated by Fernet + DuckDB encryption
- **Injection attacks**: Mitigated by Pydantic validation + parameterized queries

