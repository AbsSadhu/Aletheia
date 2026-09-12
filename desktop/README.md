# Aletheia Desktop

Tauri 2 native shell that wraps the `../frontend/` production build and supervises two local sidecars: the Python FastAPI backend and the Rust `aletheia-engine` compute sidecar.

## What it does

On launch (`desktop/src-tauri/src/main.rs`), the app spawns two sidecars and resolves each one the same way:
1. **Packaged first** — check `resources/aletheia-engine[.exe]` and `resources/aletheia-backend/aletheia-backend[.exe]` inside the app's bundled resource dir (populated by `scripts/prepare_sidecars.*` before `tauri build` — see [Packaging a real installer](#packaging-a-real-installer) below).
2. **Dev tree fallback** — if the packaged binaries aren't there, fall back to `aletheia_engine/target/release/aletheia-engine[.exe]` and `.venv/{Scripts,bin}/python -m uvicorn aletheia.core.main:app`, exactly as before. This is what `npm run tauri dev` uses day to day — you don't need to run the packaging step for normal development.

Then it:
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

## Packaging a real installer

`npm run tauri build` alone produces an installer that can't run anywhere but this dev machine — a real user's machine has no `.venv`, no compiled `aletheia_engine` binary, and no `pyproject.toml` nearby for the dev-tree fallback to find. To ship a genuinely self-contained installer:

```bash
# 1. Build the Rust engine sidecar (if not already built)
cd aletheia_engine && cargo build --release && cd ..

# 2. Freeze the Python backend into a single sidecar binary (no interpreter needed at runtime)
.venv/Scripts/pip install pyinstaller   # one-time
.venv/Scripts/python.exe -m PyInstaller desktop/aletheia-backend.spec \
    --distpath desktop/dist_backend --workpath desktop/build_backend

# 3. Stage both sidecars where tauri.conf.json's bundle.resources expects them
desktop/scripts/prepare_sidecars.ps1   # or prepare_sidecars.sh on macOS/Linux

# 4. Build the installer — it now bundles both sidecars as resources
npm run tauri build
```

Verified empirically on Windows, in this order: (1) the frozen `aletheia-backend.exe` standalone answers `/api/v1/health` and completes a full multi-agent `/api/v1/runs` pipeline with no Python interpreter present; (2) `npm run tauri build` successfully bundles both staged sidecars via `bundle.resources` — cargo's build script copies `resources/` to `target/<profile>/resources/` at build time, which is what let this be checked without an installed copy; (3) running the built `target/release/aletheia-desktop.exe` directly resolves `resource_dir()` to the exe's own directory (not `.../resources` itself — join `"resources"` onto it, which is what `main.rs` does), spawns `aletheia-engine.exe` and `aletheia-backend.exe` from that packaged path (confirmed via process inspection, not just absence of errors), and completes a full `/api/v1/runs` call end to end. Not yet verified: the actual NSIS installer's silent install completed in this environment — `ALETHEIA_0.1.0_x64-setup.exe /S` produced no installed copy and no error, most likely because Tauri's default per-machine install mode needs an admin UAC prompt this non-interactive environment can't answer (same blocker as Docker Desktop's installer, below). The install-time resource layout should be identical to what step 3 already confirmed, since Tauri resolves `resource_dir()` relative to whatever directory the running exe is actually in — but that's inference from step 3, not a from-a-real-installer observation. If you have desktop access, running the installer normally (double-click, accept the UAC prompt) and confirming the app starts is the one remaining check. Also not yet verified: the equivalent macOS/Linux PyInstaller builds (the heavy dependency tree here — langchain, langgraph, duckdb, pandas/numpy/scipy — is exactly the kind PyInstaller's static analysis can miss hidden imports for; if a packaged build fails at runtime with a `ModuleNotFoundError` that doesn't reproduce from `.venv`, add that module to the `collect_all(...)` loop in `aletheia-backend.spec`).

Known limitation carried over from the dev tree: `weasyprint` (PDF export) needs native GTK/Pango/Cairo libraries that pip doesn't install and PyInstaller can't bundle from a Windows `.venv` that doesn't have them either — a packaged build has the same PDF-export-falls-back-to-HTML behavior as an unpackaged one, not a new regression.

## Platform notes

- Windows: process supervision additionally uses a Job Object (`win32job`, Windows-only dependency) so a hard kill of the Tauri process cannot leave orphaned sidecar processes running.
- Icons live in `src-tauri/icons/` (ico, icns, and png variants) — regenerate the full set from a single source image with `npx tauri icon <path-to-image>` if the app icon changes.
