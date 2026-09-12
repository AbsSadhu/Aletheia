# -*- mode: python ; coding: utf-8 -*-
#
# Builds the frozen backend sidecar that a packaged Tauri app spawns
# directly — no .venv, no `python -m`, no dev-tree path lookup. Run from
# the repo root:
#
#   .venv\Scripts\python.exe -m PyInstaller desktop\aletheia-backend.spec ^
#       --distpath desktop\dist_backend --workpath desktop\build_backend
#
# then desktop\scripts\prepare_sidecars.ps1 (or .sh) to stage the result
# for `npm run tauri build`.
#
# Verified empirically (this file's build was smoke-tested, not just
# assumed to work): the resulting aletheia-backend.exe answers
# /api/v1/health and completes a full multi-agent /api/v1/runs pipeline
# with zero Python interpreter on the host.
import os

from PyInstaller.utils.hooks import collect_all

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

datas = [(os.path.join(REPO_ROOT, "aletheia", "core", "templates"), "aletheia/core/templates")]
binaries = []
hiddenimports = []

# These packages rely heavily on dynamic imports/plugin discovery that
# PyInstaller's static analysis misses on its own.
for pkg in ("duckdb", "langchain", "langgraph", "langsmith", "fastmcp", "pydantic", "yfinance", "ccxt"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    [os.path.join(REPO_ROOT, "desktop", "backend_entry.py")],
    pathex=[REPO_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="aletheia-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="aletheia-backend",
)
