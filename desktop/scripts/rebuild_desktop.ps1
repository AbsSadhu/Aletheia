# One command to bring the desktop app up to date with the source tree.
#
# The desktop build embeds TWO things that go stale independently: the frontend (frontend/dist)
# and a frozen PyInstaller copy of the Python backend. Rebuilding only one of them leaves the
# installed app running old code. This script rebuilds both and produces the NSIS installer.
#
#   powershell -ExecutionPolicy Bypass -File desktop\scripts\rebuild_desktop.ps1
#   ... -SkipBackend   (frontend-only change: reuse the last frozen backend)
#
# Output: desktop\src-tauri\target\release\bundle\nsis\ALETHEIA_<version>_x64-setup.exe
#         desktop\src-tauri\target\release\aletheia-desktop.exe (runs directly, sidecars alongside)
#
# Only the NSIS installer is built: the MSI step downloads WiX from GitHub and times out offline.

param([switch]$SkipBackend)

$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $root

# A running app locks its own exe and the sidecars; close it first.
Get-Process aletheia-desktop, aletheia-backend, aletheia-engine -ErrorAction SilentlyContinue |
    Stop-Process -Force

if (-not $SkipBackend) {
    Write-Host "== Freezing the Python backend (PyInstaller, a few minutes) =="
    & "$root\.venv\Scripts\python.exe" -m PyInstaller desktop\aletheia-backend.spec `
        --distpath desktop\dist_backend --workpath desktop\build_backend --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
}

Write-Host "== Staging sidecars =="
& "$PSScriptRoot\prepare_sidecars.ps1"

Write-Host "== Building the desktop app (frontend + Rust + NSIS installer) =="
Set-Location "$root\desktop"
# (npx, not `npm run ... --`: PowerShell swallows the `--` separator and Tauri then sees a stray arg)
npx tauri build --bundles nsis
if ($LASTEXITCODE -ne 0) { throw "tauri build failed" }

Write-Host "Done. Installer: desktop\src-tauri\target\release\bundle\nsis\"
