# ADR-0002: Tauri Desktop Shell

## Status

Accepted

## Decision

ALETHEIA includes a Tauri shell as a first-class local delivery surface for:

- secure desktop packaging
- OS-native credential handling
- backend lifecycle management
- export permissions and local notifications

## Consequences

- The same React frontend can be hosted in browser or desktop contexts.
- The desktop app owns local shell concerns, not domain logic.
