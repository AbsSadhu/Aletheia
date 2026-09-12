# Aletheia Desktop

Tauri 2 native shell that wraps the `../frontend/` production build and supervises two local sidecars: the Python FastAPI backend and the Rust `aletheia-engine` compute sidecar.

## What it does

On launch (`desktop/src-tauri/src/main.rs`), the app:
1. Locates the workspace root by walking up from its resource dir until it finds `pyproject.toml`.
2. Spawns `aletheia_engine/target/release/aletheia-engine[.exe]` and, half a second later, `.venv/{Scripts,bin}/python -m uvicorn aletheia.core.main:app` — both sidecars must already be built (`cargo build --release` in `aletheia_engine/`, and a `.venv` with the project installed) before running this.
3. Keeps the window hidden until both sidecars answer their health checks (or 30s elapses), so you never see a blank/connection-refused screen.
4. Runs a system tray (Open / Restart Services / Stop Services / Quit) and kills both sidecar processes when the window closes.

The backend no longer requires Ollama to be running to start — it boots with a warning and only agent runs that need the LLM will fail until Ollama is reachable.

## Getting started

```bash
npm install
npm run tauri dev     # requires ../frontend deps installed too, and both sidecars built
npm run tauri build   # produces a platform installer/bundle
```

Run this from `desktop/` — the `beforeDevCommand`/`beforeBuildCommand` in `src-tauri/tauri.conf.json` assume that working directory.

## Platform notes

- Windows: process supervision additionally uses a Job Object (`win32job`, Windows-only dependency) so a hard kill of the Tauri process cannot leave orphaned sidecar processes running.
- Icons live in `src-tauri/icons/` (ico, icns, and png variants) — regenerate the full set from a single source image with `npx tauri icon <path-to-image>` if the app icon changes.
