#!/usr/bin/env bash
# Stages both backend sidecars into desktop/resources/ so `tauri build`
# can bundle them via tauri.conf.json's `bundle.resources`.
#
# A packaged installer has no .venv, no cargo target dir, and no
# pyproject.toml nearby for the old dev-tree path-walking logic to find —
# this script produces the two artifacts that make the packaged app
# self-contained instead.
#
# Run this before `npm run tauri build`. Requires: a `cargo build --release`
# of aletheia_engine already done, and PyInstaller installed in .venv
# (`.venv/bin/pip install pyinstaller`).

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# Relative to tauri.conf.json (desktop/src-tauri/), not desktop/ itself —
# that's what `bundle.resources: ["resources"]` in tauri.conf.json points at.
RESOURCES_DIR="$ROOT/desktop/src-tauri/resources"

mkdir -p "$RESOURCES_DIR"

# --- Rust engine sidecar ---
ENGINE_BIN="$ROOT/aletheia_engine/target/release/aletheia-engine"
if [ ! -f "$ENGINE_BIN" ]; then
    echo "aletheia-engine not found at $ENGINE_BIN — run 'cargo build --release' in aletheia_engine first." >&2
    exit 1
fi
cp "$ENGINE_BIN" "$RESOURCES_DIR/aletheia-engine"
chmod +x "$RESOURCES_DIR/aletheia-engine"
echo "Staged aletheia-engine"

# --- Python backend sidecar (PyInstaller onedir build) ---
BACKEND_DIST="$ROOT/desktop/dist_backend/aletheia-backend"
if [ ! -d "$BACKEND_DIST" ]; then
    echo "PyInstaller backend build not found at $BACKEND_DIST — run:" >&2
    echo "  .venv/bin/python -m PyInstaller desktop/aletheia-backend.spec" >&2
    exit 1
fi
BACKEND_DEST="$RESOURCES_DIR/aletheia-backend"
rm -rf "$BACKEND_DEST"
cp -r "$BACKEND_DIST" "$BACKEND_DEST"
echo "Staged aletheia-backend/ (PyInstaller onedir output)"

echo "Sidecars staged in $RESOURCES_DIR — ready for 'npm run tauri build'."
