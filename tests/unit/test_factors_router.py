"""Regression test: /factors/{ticker} must build its OHLCV frame from Candle.ts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

import pytest

from aletheia.core.api.routers import factors
from aletheia.core.marketdata.models import Candle


class _FakeEngine:
    async def get_historical(self, request, start, end, interval):  # noqa: ANN001, ANN201
        base = datetime(2026, 1, 1, tzinfo=UTC)
        return [
            Candle(
                symbol=request.symbol,
                exchange=request.exchange,
                timeframe=interval,
                ts=base + timedelta(days=i),
                open=100 + i,
                high=101 + i,
                low=99 + i,
                close=100.5 + i,
                volume=1000 + i,
                provider="test",
            )
            for i in range(120)
        ]


def test_compute_factors_accepts_real_candles(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(factors.router)
    monkeypatch.setattr(factors, "get_market_data_engine", lambda: _FakeEngine())

    resp = TestClient(app).get("/api/v1/factors/RELIANCE")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bars"] == 120
    assert "composite" in body


class _FailingEngine:
    """What the real engine does for an unknown NSE ticker: every provider fails, and the last one
    tried is Binance, so the raw error talks about a Binance market symbol."""

    async def get_historical(self, request, start, end, interval):  # noqa: ANN001, ANN201
        raise RuntimeError(f"binance does not have market symbol {request.symbol}")


class _EmptyEngine:
    async def get_historical(self, request, start, end, interval):  # noqa: ANN001, ANN201
        return []


def _get(monkeypatch: pytest.MonkeyPatch, engine: object, url: str):  # noqa: ANN202
    app = FastAPI()
    app.include_router(factors.router)
    monkeypatch.setattr(factors, "get_market_data_engine", lambda: engine)
    return TestClient(app, raise_server_exceptions=False).get(url)


def test_unknown_indian_symbol_is_a_plain_404_not_a_binance_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = _get(monkeypatch, _FailingEngine(), "/api/v1/factors/NOSUCHCO")
    assert resp.status_code == 404
    text = resp.text.lower()
    assert "nosuchco" in text and "nse" in text
    assert "binance" not in text


def test_empty_history_is_also_a_plain_404(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _get(monkeypatch, _EmptyEngine(), "/api/v1/factors/NOSUCHCO")
    assert resp.status_code == 404
    assert "no price data" in resp.text.lower()


def test_a_crypto_pair_keeps_the_raw_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _get(monkeypatch, _FailingEngine(), "/api/v1/factors/FAKE-USD?exchange=BINANCE")
    assert resp.status_code == 502
