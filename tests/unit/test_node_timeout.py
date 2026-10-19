"""The per-node timeout default must suit local LLMs, and stay configurable."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aletheia.core.config.settings import Settings


def test_default_node_timeout_allows_slow_local_models(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ignore any developer .env / shell override: this checks the built-in default.
    monkeypatch.delenv("ALETHEIA_NODE_TIMEOUT_SECS", raising=False)
    assert Settings(_env_file=None).node_timeout_secs == 120


def test_node_timeout_is_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALETHEIA_NODE_TIMEOUT_SECS", "300")
    assert Settings(_env_file=None).node_timeout_secs == 300


def test_node_timeout_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALETHEIA_NODE_TIMEOUT_SECS", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
