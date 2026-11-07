"""Correlation regimes: when does a group of assets start moving as one?

``compute_edge_density``, ``detect_regimes`` and ``fused_episodes`` are adapted from Vibe-Trading's
``backtest/regime.py`` (MIT; see THIRD_PARTY_NOTICES.md): rolling pairwise correlations are reduced to
an "edge density" (the share of pairs whose |correlation| clears a threshold), smoothed with a
trailing window, and run through a two-threshold hysteresis state machine that labels each bar FUSED
or NORMAL. The dead band between the thresholds is what stops it flickering.

This is descriptive risk context: it says diversification has thinned, not what will happen next.
Prices come from Aletheia's own daily candles.
"""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pandas as pd

from aletheia.core.marketdata import candles as candle_source

MAX_ASSETS = 20
MIN_ASSETS = 2


def compute_edge_density(
    returns: pd.DataFrame, corr_window: int = 60, edge_threshold: float = 0.5
) -> pd.Series:
    """Fraction of distinct pairs whose rolling |correlation| is at least ``edge_threshold``, per bar."""
    n_assets = returns.shape[1]
    n_pairs = n_assets * (n_assets - 1) // 2
    if n_pairs == 0:
        return pd.Series(np.nan, index=returns.index)
    upper = np.triu(np.ones((n_assets, n_assets), dtype=bool), k=1)
    density = pd.Series(np.nan, index=returns.index)
    for i in range(corr_window, len(returns) + 1):
        corr = returns.iloc[i - corr_window : i].corr().abs().to_numpy()
        density.iloc[i - 1] = float((corr[upper] >= edge_threshold).sum()) / n_pairs
    return density


def detect_regimes(
    density: pd.Series,
    smooth_window: int = 5,
    enter_threshold: float = 0.65,
    exit_threshold: float = 0.45,
) -> pd.DataFrame:
    """Schmitt-trigger state machine on the smoothed density: FUSED from ``enter`` until it falls to ``exit``."""
    if exit_threshold >= enter_threshold:
        raise ValueError("exit_threshold must be below enter_threshold")
    smoothed = density.rolling(
        smooth_window, min_periods=1
    ).mean()  # trailing, so it never reads the future
    fused = False
    states = np.zeros(len(smoothed), dtype=int)
    for i, value in enumerate(smoothed.to_numpy()):
        if np.isnan(value):
            states[i] = int(fused)
            continue
        if not fused and value >= enter_threshold:
            fused = True
        elif fused and value <= exit_threshold:
            fused = False
        states[i] = int(fused)
    return pd.DataFrame(
        {"density": density, "smoothed": smoothed, "fused": states}, index=density.index
    )


def fused_episodes(dates: list[str], fused: list[int]) -> list[dict[str, str | None]]:
    """Contiguous FUSED intervals. ``end`` is None while the last bar is still FUSED."""
    episodes: list[dict[str, str | None]] = []
    start: str | None = None
    last: str | None = None
    for date, state in zip(dates, fused):
        if state:
            start = start or date
            last = date
        elif start is not None:
            episodes.append({"start": start, "end": last})
            start = None
    if start is not None:
        episodes.append({"start": start, "end": None})
    return episodes


def _closes(payload: dict[str, Any]) -> pd.Series:
    rows = payload.get("candles", [])
    idx = (
        pd.to_datetime([r["time"] for r in rows], unit="s", utc=True).tz_localize(None).normalize()
    )
    return pd.Series([r["close"] for r in rows], index=idx)


def aligned_returns(prices: dict[str, pd.Series]) -> pd.DataFrame:
    """Daily returns, one column per asset, on the dates every asset traded. No forward-filling."""
    frames = []
    for label, series in prices.items():
        series = series[~series.index.duplicated(keep="last")]
        frames.append(series.pct_change(fill_method=None).dropna().rename(label))
    joined = pd.concat(frames, axis=1).dropna()
    if joined.empty:
        raise ValueError("These assets have no trading days in common.")
    return joined


def build(
    returns: pd.DataFrame,
    days: int = 180,
    corr_window: int = 60,
    edge_threshold: float = 0.5,
    smooth_window: int = 5,
    enter_threshold: float = 0.65,
    exit_threshold: float = 0.45,
) -> dict[str, Any]:
    if len(returns) < corr_window + 5:
        raise ValueError(
            f"Only {len(returns)} common trading days; a {corr_window}-day window needs at least {corr_window + 5}."
        )
    density = compute_edge_density(returns, corr_window, edge_threshold)
    regimes = detect_regimes(density, smooth_window, enter_threshold, exit_threshold)
    if (
        len(regimes) > days
    ):  # trim after the state machine has run, so the first bar reflects full history
        regimes = regimes.iloc[-days:]
    dates = [d.strftime("%Y-%m-%d") for d in regimes.index]
    opt = lambda s: [None if np.isnan(v) else round(float(v), 4) for v in s]  # noqa: E731
    fused = [int(v) for v in regimes["fused"]]
    latest = returns.iloc[-corr_window:].corr()
    labels = list(returns.columns)
    pairs = [
        {"a": labels[i], "b": labels[j], "corr": round(float(latest.iloc[i, j]), 3)}
        for i in range(len(labels))
        for j in range(i + 1, len(labels))
    ]
    pairs.sort(key=lambda p: p["corr"], reverse=True)
    last_smoothed = regimes["smoothed"].iloc[-1]
    return {
        "labels": labels,
        "matrix": [
            [None if np.isnan(v) else round(float(v), 3) for v in row] for row in latest.to_numpy()
        ],
        "dates": dates,
        "density": opt(regimes["density"]),
        "smoothed": opt(regimes["smoothed"]),
        "fused": fused,
        "episodes": fused_episodes(dates, fused),
        "current": {
            "state": "FUSED" if fused[-1] else "NORMAL",
            "smoothed_density": None if np.isnan(last_smoothed) else round(float(last_smoothed), 4),
            "average_correlation": round(float(np.mean([p["corr"] for p in pairs])), 3)
            if pairs
            else None,
        },
        "most_correlated": pairs[:3],
        "least_correlated": pairs[::-1][:3],
        "params": {
            "days": days,
            "corr_window": corr_window,
            "edge_threshold": edge_threshold,
            "smooth_window": smooth_window,
            "enter_threshold": enter_threshold,
            "exit_threshold": exit_threshold,
        },
    }


async def compute(items: list[tuple[str, str]], **params: Any) -> dict[str, Any]:
    """Fetch daily candles for (symbol, exchange) pairs and build the regime view."""
    items = items[:MAX_ASSETS]
    results = await asyncio.gather(
        *(asyncio.to_thread(candle_source.fetch_candles, s, e, "1d") for s, e in items),
        return_exceptions=True,
    )
    prices: dict[str, pd.Series] = {}
    missing: list[str] = []
    for (symbol, _exchange), res in zip(items, results):
        if isinstance(res, BaseException) or not res.get("candles"):
            missing.append(symbol)
        else:
            prices[symbol] = _closes(res)
    if len(prices) < MIN_ASSETS:
        raise ValueError(
            f"Need price history for at least {MIN_ASSETS} assets; got {len(prices)} ({', '.join(missing) or 'none'} unavailable)."
        )
    out = build(aligned_returns(prices), **params)
    out["unavailable"] = missing
    return out
