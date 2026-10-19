"""Every manifest must carry the same version as ``aletheia.__version__``.

The version lives in several ecosystems (Poetry, npm, Cargo, Tauri), so it can't be
read from one file at build time. This test makes drift fail CI instead.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

from aletheia import __version__

ROOT = Path(__file__).resolve().parents[2]


def _toml_version(path: str, *keys: str) -> str:
    data = tomllib.loads((ROOT / path).read_text(encoding="utf-8"))
    for key in keys:
        data = data[key]
    return data  # type: ignore[return-value]


def _json_version(path: str) -> str:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))["version"]


@pytest.mark.parametrize(
    ("path", "read"),
    [
        ("pyproject.toml", lambda p: _toml_version(p, "tool", "poetry", "version")),
        ("aletheia_engine/Cargo.toml", lambda p: _toml_version(p, "package", "version")),
        ("desktop/src-tauri/Cargo.toml", lambda p: _toml_version(p, "package", "version")),
        ("frontend/package.json", _json_version),
        ("desktop/package.json", _json_version),
        ("desktop/src-tauri/tauri.conf.json", _json_version),
    ],
)
def test_manifest_version_matches_package(path: str, read) -> None:  # noqa: ANN001
    assert read(path) == __version__, f"{path} is out of sync with aletheia.__version__"


def test_changelog_has_an_entry_for_current_version() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(rf"^## \[{re.escape(__version__)}\]", changelog, re.MULTILINE)


def test_exported_report_shows_current_version() -> None:
    from aletheia.core.reporting.exporter import render_html

    html = render_html({"summary": {"run_id": "r", "prompt": "p", "status": "completed"}})
    assert f"ALETHEIA v{__version__}" in html
