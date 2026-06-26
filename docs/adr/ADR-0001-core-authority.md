# ADR-0001: Python Core Authority

## Status

Accepted

## Decision

The Python backend is the authoritative implementation of ALETHEIA core logic:

- data providers and normalization
- agent orchestration
- memory and persistence
- risk and backtesting engines
- HTTP and WebSocket interfaces

## Consequences

- Tauri does not replace the backend.
- Desktop features integrate through typed contracts and local process management.
- Rust additions must strengthen safety or UX without fragmenting core behavior.

