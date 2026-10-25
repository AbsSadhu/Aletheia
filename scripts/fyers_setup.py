"""One-time setup: create the isolated Python environment that runs Fyers' official SDK.

    .venv\\Scripts\\python.exe scripts\\fyers_setup.py

Why a separate environment: `fyers-apiv3` depends on boto3 and AWS libraries and pins older
`requests`/`aiohttp`. Installed into Aletheia's own environment it breaks `ccxt` and other
packages (this was observed). So it goes in ~/.aletheia/fyers-venv, used only by the helper
process in aletheia/extensions/data/fyers_bridge.py. Nothing in Aletheia's environment changes.
"""

from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

SDK_VERSION = "3.2.0"  # the version the bridge was written against
VENV = Path.home() / ".aletheia" / "fyers-venv"


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(*args: str) -> None:
    print("  $", " ".join(args))
    subprocess.run(args, check=True)


def main() -> int:
    py = venv_python()
    if not py.exists():
        print(f"Creating isolated environment at {VENV} ...")
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV)
    else:
        print(f"Using existing environment at {VENV}")

    print(f"Installing fyers-apiv3=={SDK_VERSION} (this takes a minute) ...")
    run(
        str(py),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-q",
        f"fyers-apiv3=={SDK_VERSION}",
    )
    # The SDK imports pkg_resources, which newer setuptools releases no longer ship.
    run(str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q", "setuptools<81")

    print("Verifying the SDK imports ...")
    check = subprocess.run(
        [str(py), "-c", "from fyers_apiv3.FyersWebsocket import data_ws; print('ok')"],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0 or "ok" not in check.stdout:
        print("FAIL: the SDK did not import.\n", check.stderr[-800:])
        return 1
    print(f"PASS: Fyers helper environment is ready at {VENV}")
    print("Next: Settings -> Fyers (app ID + secret) -> Connect Fyers, then:")
    print("      .venv\\Scripts\\python.exe scripts\\fyers_check.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
