import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aletheia.core.api.routers import feed
from aletheia.core.marketdata import candles


def test_yahoo_symbol_mapping() -> None:
    assert candles.yahoo_symbol("RELIANCE", "NSE") == "RELIANCE.NS"
    assert candles.yahoo_symbol("RELIANCE", "BSE") == "RELIANCE.BO"
    assert candles.yahoo_symbol("BTC/USDT", "BINANCE") == "BTC-USD"
    assert candles.yahoo_symbol("^NSEI", "NSE") == "^NSEI"
    assert candles.yahoo_symbol("TCS.NS", "NSE") == "TCS.NS"


def _frame(tz: str | None, n: int = 3, freq: str = "5min") -> pd.DataFrame:
    idx = pd.date_range("2026-10-26 09:15", periods=n, freq=freq, tz=tz)
    return pd.DataFrame(
        {"Open": [100.0, 101, 102][:n], "High": [101.0, 102, 103][:n], "Low": [99.0, 100, 101][:n],
         "Close": [100.5, 101.5, 102.5][:n], "Volume": [10, 20, 30][:n]},
        index=idx,
    )  # fmt: skip


def test_intraday_frame_becomes_epoch_seconds_ascending() -> None:
    out = candles.frame_to_candles(_frame("Asia/Kolkata"), daily=False)
    assert [c["time"] for c in out] == sorted(c["time"] for c in out)
    # 09:15 IST == 03:45 UTC
    assert out[0]["time"] == int(pd.Timestamp("2026-10-26 03:45", tz="UTC").timestamp())
    assert out[0]["close"] == 100.5 and out[2]["volume"] == 30.0


def test_daily_frame_is_pinned_to_utc_midnight_not_shifted() -> None:
    df = _frame(None, freq="D")
    out = candles.frame_to_candles(df, daily=True)
    assert out[0]["time"] == int(pd.Timestamp("2026-10-26", tz="UTC").timestamp())


def test_nan_rows_and_empty_frames_are_handled() -> None:
    df = _frame("Asia/Kolkata")
    df.iloc[1, df.columns.get_loc("Close")] = float("nan")
    assert len(candles.frame_to_candles(df, daily=False)) == 2
    assert candles.frame_to_candles(pd.DataFrame(), daily=False) == []


def test_bad_interval_is_rejected() -> None:
    with pytest.raises(ValueError):
        candles.fetch_candles("TCS", "NSE", "3m")


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(feed.router)
    return TestClient(app)


def test_endpoint_returns_candles_with_ist_offset_for_indian_intraday(client, monkeypatch) -> None:
    def fake_fetch(symbol, exchange, interval):
        return {
            "symbol": symbol, "exchange": exchange, "interval": interval,
            "candles": [{"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 9}],
            "tz_offset_secs": 19800, "source": "Yahoo Finance", "note": "n",
        }  # fmt: skip

    monkeypatch.setattr(candles, "fetch_candles", fake_fetch)
    body = client.get(
        "/api/v1/marketdata/candles", params={"symbol": "tcs", "interval": "5m"}
    ).json()
    assert body["symbol"] == "TCS" and body["tz_offset_secs"] == 19800 and len(body["candles"]) == 1


def test_endpoint_error_mapping(client, monkeypatch) -> None:
    monkeypatch.setattr(candles, "fetch_candles", lambda s, e, i: {"candles": [], "symbol": s})
    assert client.get("/api/v1/marketdata/candles", params={"symbol": "ZZZ"}).status_code == 404
    assert client.get("/api/v1/marketdata/candles", params={"symbol": "bad sym"}).status_code == 422

    def boom(s, e, i):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(candles, "fetch_candles", boom)
    assert client.get("/api/v1/marketdata/candles", params={"symbol": "TCS"}).status_code == 502
    monkeypatch.setattr(
        candles,
        "fetch_candles",
        lambda s, e, i: (_ for _ in ()).throw(ValueError("interval must be")),
    )
    assert (
        client.get(
            "/api/v1/marketdata/candles", params={"symbol": "TCS", "interval": "7m"}
        ).status_code
        == 422
    )
