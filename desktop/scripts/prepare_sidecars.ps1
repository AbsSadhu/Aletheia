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
# (`.venv\Scripts\pip install pyinstaller`).

$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."
# Relative to tauri.conf.json (desktop/src-tauri/), not desktop/ itself —
# that's what `bundle.resources: ["resources"]` in tauri.conf.json points at.
$resourcesDir = Join-Path $root "desktop\src-tauri\resources"

New-Item -ItemType Directory -Force -Path $resourcesDir | Out-Null

# --- Rust engine sidecar ---
$engineExe = Join-Path $root "aletheia_engine\target\release\aletheia-engine.exe"
if (-not (Test-Path $engineExe)) {
    throw "aletheia-engine.exe not found at $engineExe -run 'cargo build --release' in aletheia_engine first."
}
Copy-Item $engineExe (Join-Path $resourcesDir "aletheia-engine.exe") -Force
Write-Host "Staged aletheia-engine.exe"

# --- Python backend sidecar (PyInstaller onedir build) ---
$backendDist = Join-Path $root "desktop\dist_backend\aletheia-backend"
if (-not (Test-Path $backendDist)) {
    throw "PyInstaller backend build not found at $backendDist -run:`n  .venv\Scripts\python.exe -m PyInstaller desktop\aletheia-backend.spec"
}
$backendDest = Join-Path $resourcesDir "aletheia-backend"
if (Test-Path $backendDest) {
    Remove-Item $backendDest -Recurse -Force
}
Copy-Item $backendDist $backendDest -Recurse -Force
Write-Host "Staged aletheia-backend/ (PyInstaller onedir output)"

Write-Host "Sidecars staged in $resourcesDir - ready for 'npm run tauri build'."
