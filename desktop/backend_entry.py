"""
PyInstaller entry point for the ALETHEIA FastAPI backend.

`python -m uvicorn aletheia.core.main:app` (what the dev tree and Docker
image both use) isn't invokable from a frozen PyInstaller binary — there's
no `python` interpreter or `-m` module resolution once packaged, only this
process itself. This script is the thing PyInstaller actually freezes;
Tauri's sidecar spawns the resulting binary directly, with the same
ALETHEIA_* env vars it already sets today.
"""

import os

import uvicorn

from aletheia.core.main import app

if __name__ == "__main__":
    host = os.getenv("ALETHEIA_HOST", "127.0.0.1")
    port = int(os.getenv("ALETHEIA_PORT", "8899"))
    uvicorn.run(app, host=host, port=port, log_level="info")
