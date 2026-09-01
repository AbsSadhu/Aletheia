from __future__ import annotations

import asyncio

import httpx

from aletheia.integrations.validators import validate_local_model


def test_validate_local_model_success(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "models": [
                    {"name": "mistral:7b", "details": {"context_length": 8192}},
                    {"name": "llama3", "details": {"context_length": 4096}},
                ]
            }

    class FakeClient:
        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=10.0: FakeClient())
    result = asyncio.run(validate_local_model("http://localhost:11434", "mistral:7b"))
    assert result.is_valid is True
    assert result.model_downloaded is True
    assert result.context_length == 8192


def test_validate_local_model_failure(monkeypatch) -> None:
    class FakeClient:
        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str) -> None:
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=10.0: FakeClient())
    result = asyncio.run(validate_local_model("http://localhost:11434", "mistral:7b"))
    assert result.is_valid is False
    assert result.is_running is False
