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
