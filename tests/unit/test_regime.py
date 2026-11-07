"""Correlation regimes: edge density, the hysteresis state machine, episodes, and the endpoint."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aletheia.core.analytics import regime
from aletheia.core.analytics.regime import (
    aligned_returns,
    build,
    compute_edge_density,
    detect_regimes,
    fused_episodes,
)


def _returns(seed=0, n=300, assets=5, fused_from=None, fused_to=None):
    """Independent assets, with one common factor switched on between two bars."""
    rng = np.random.default_rng(seed)
    data = rng.normal(0, 0.01, (n, assets))
    if fused_from is not None:
        common = rng.normal(0, 0.02, n)
        data[fused_from:fused_to] = (
            0.15 * data[fused_from:fused_to] + common[fused_from:fused_to, None]
        )
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame(data, index=idx, columns=[f"A{i}" for i in range(assets)])


def test_edge_density_is_low_for_independent_assets_and_high_when_they_share_a_factor():
    r = _returns(fused_from=150, fused_to=250)
    d = compute_edge_density(r, corr_window=40, edge_threshold=0.5)
    assert d.iloc[:39].isna().all()  # warm-up
    assert d.iloc[100:140].max() < 0.3
    assert d.iloc[220:250].mean() > 0.8


def test_hysteresis_needs_the_enter_threshold_and_holds_until_the_exit_threshold():
    d = pd.Series(
        [0.2, 0.5, 0.7, 0.6, 0.5, 0.4, 0.2]
    )  # crosses 0.65 once, sits in the dead band, then drops below 0.45
    out = detect_regimes(d, smooth_window=1, enter_threshold=0.65, exit_threshold=0.45)
    assert out["fused"].tolist() == [0, 0, 1, 1, 1, 0, 0]


def test_the_dead_band_stops_chatter():
    d = pd.Series([0.7, 0.6, 0.7, 0.6, 0.7, 0.6])  # bounces between 0.6 and 0.7 but never to 0.45
    assert detect_regimes(d, smooth_window=1)["fused"].tolist() == [1] * 6


def test_thresholds_must_be_ordered():
    with pytest.raises(ValueError, match="below enter"):
        detect_regimes(pd.Series([0.1, 0.2]), enter_threshold=0.5, exit_threshold=0.5)


def test_smoothing_is_trailing_so_it_cannot_read_the_future():
    d = pd.Series([0.0, 0.0, 0.0, 1.0, 1.0])
    s = detect_regimes(d, smooth_window=3, enter_threshold=0.9, exit_threshold=0.1)["smoothed"]
    assert s.iloc[:3].tolist() == [0.0, 0.0, 0.0]  # nothing moves before the jump arrives


def test_episodes_close_and_stay_open_when_ongoing():
    dates = [f"d{i}" for i in range(6)]
    assert fused_episodes(dates, [0, 1, 1, 0, 1, 1]) == [
        {"start": "d1", "end": "d2"},
        {"start": "d4", "end": None},
    ]
    assert fused_episodes(dates, [0] * 6) == []


def test_aligned_returns_use_common_days_without_forward_filling():
    a = pd.Series(
        [100, 101, 102, 103],
        index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-06"]),
    )
    b = pd.Series(
        [50, 51, 52], index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-06"])
    )  # no 3 Jan
    out = aligned_returns({"A": a, "B": b})
    assert list(out.index) == [pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-06")]


def test_build_reports_state_pairs_and_trims_to_the_window():
    r = _returns(fused_from=180, fused_to=300)
    out = build(r, days=100, corr_window=40)
    assert len(out["dates"]) == 100 and out["current"]["state"] == "FUSED"
    assert out["most_correlated"][0]["corr"] >= out["least_correlated"][0]["corr"]
    assert np.array(out["matrix"]).shape == (5, 5) and out["matrix"][0][0] == 1.0
    with pytest.raises(ValueError, match="common trading days"):
        build(_returns(n=30), corr_window=60)


def _fake_candles(seed):
    rng = np.random.default_rng(seed)
    closes = 100 * np.cumprod(1 + rng.normal(0, 0.01, 200))
    days = pd.bdate_range("2025-06-02", periods=200)
    return {
        "candles": [{"time": int(d.timestamp()), "close": float(c)} for d, c in zip(days, closes)]
    }


def test_endpoint_with_stubbed_prices(monkeypatch):
    from fastapi.testclient import TestClient

    from aletheia.core.main import create_app

    seeds = {"INFY": 1, "TCS": 2, "SBIN": 3}

    def fake_fetch(symbol, exchange, interval):
        if symbol == "BROKEN":
            raise RuntimeError("no data")
        return _fake_candles(seeds[symbol])

    monkeypatch.setattr(regime.candle_source, "fetch_candles", fake_fetch)
    client = TestClient(create_app())
    ok = client.get(
        "/api/v1/analytics/correlation",
        params={"symbols": "NSE:INFY,TCS,NSE:SBIN,NSE:BROKEN", "days": 60, "corr_window": 40},
    )
    body = ok.json()
    assert ok.status_code == 200, body
    assert body["labels"] == ["INFY", "TCS", "SBIN"] and body["unavailable"] == ["BROKEN"]
    assert body["current"]["state"] in {"FUSED", "NORMAL"} and len(body["dates"]) == 60
    assert (
        client.get("/api/v1/analytics/correlation", params={"symbols": "NSE:INFY"}).status_code
        == 422
    )
    bad = client.get(
        "/api/v1/analytics/correlation",
        params={"symbols": "INFY,TCS", "enter_threshold": 0.4, "exit_threshold": 0.5},
    )
    assert bad.status_code == 422
