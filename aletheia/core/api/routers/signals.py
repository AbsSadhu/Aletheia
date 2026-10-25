"""Signal validation: does acting on Oracle's signals actually work?

GET  /signals/accuracy              resolved-prediction hit rates, Brier score, calibration buckets
GET  /signals/shadow-vs-nifty       Shadow Trader equity curve against Nifty over the same dates
POST /backtest/signal               walk-forward backtest of the signal vs Nifty / equal-weight
GET  /backtest/signal/latest        the last completed signal backtest (it takes a minute to run)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aletheia.core.api.dependencies import get_run_service, get_shadow_account
from aletheia.core.config.settings import get_settings
from aletheia.core.signals.accuracy import summarize
from aletheia.extensions.backtest.signal_backtest import (
    DEFAULT_UNIVERSE,
    SignalBacktestConfig,
    run_signal_backtest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

_backtest_lock = asyncio.Lock()


def _fetch_history(symbol: str, years: int) -> pd.DataFrame | None:
    import yfinance as yf

    sym = symbol if symbol.startswith("^") else f"{symbol.upper().split('.')[0]}.NS"
    try:
        df = yf.Ticker(sym).history(period=f"{years}y", interval="1d", auto_adjust=True)
    except Exception as exc:
        logger.warning("History fetch for %s failed: %s", sym, exc)
        return None
    return df if df is not None and not df.empty else None


def _latest_path() -> Path:
    return Path(get_settings().data_dir) / "signal_backtest_latest.json"


@router.get("/signals/accuracy")
async def signal_accuracy() -> dict:
    store = get_run_service().sqlite_store
    return summarize(
        store.get_resolved_calibration("oracle"),
        pending=store.count_unresolved_calibration("oracle"),
    )


@router.get("/signals/shadow-vs-nifty")
async def shadow_vs_nifty() -> dict:
    curve = get_shadow_account().equity_curve(limit=2000)
    if len(curve) < 2:
        return {"points": [], "note": "Needs at least two shadow-account snapshots."}
    curve = sorted(curve, key=lambda s: s.timestamp)
    nifty = await asyncio.to_thread(_fetch_history, "^NSEI", 2)
    if nifty is None:
        raise HTTPException(status_code=502, detail="Could not fetch Nifty history.")
    closes = nifty["Close"]
    closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()

    def nifty_at(ts: datetime) -> float | None:
        day = pd.Timestamp(ts).tz_localize(None).normalize()
        prior = closes[closes.index <= day]
        return float(prior.iloc[-1]) if len(prior) else None

    base_equity = curve[0].total_equity
    base_nifty = nifty_at(curve[0].timestamp)
    if not base_nifty or base_equity <= 0:
        return {"points": [], "note": "No Nifty data for the shadow account's start date."}
    points: list[dict[str, Any]] = []
    for snap in curve:
        n = nifty_at(snap.timestamp)
        if n is None:
            continue
        points.append(
            {
                "date": snap.timestamp.isoformat(),
                "shadow_pct": round((snap.total_equity / base_equity - 1) * 100, 2),
                "nifty_pct": round((n / base_nifty - 1) * 100, 2),
            }
        )
    last: dict[str, Any] = points[-1]
    return {
        "points": points,
        "excess_pct": round(last["shadow_pct"] - last["nifty_pct"], 2),
        "days": (curve[-1].timestamp - curve[0].timestamp).days,
        "note": "Percent change since the first snapshot. Short windows are mostly noise.",
    }


class SignalBacktestRequest(BaseModel):
    symbols: list[str] | None = Field(default=None, description="Defaults to 25 Nifty large caps")
    years: int = Field(default=6, ge=2, le=10)
    max_positions: int = Field(default=10, ge=1, le=50)
    rebalance_days: int = Field(default=5, ge=1, le=60)
    initial_capital: float = Field(default=1_000_000.0, gt=0)
    apply_tax: bool = True


@router.post("/backtest/signal")
async def run_signal_backtest_endpoint(request: SignalBacktestRequest) -> dict:
    if _backtest_lock.locked():
        raise HTTPException(status_code=409, detail="A signal backtest is already running.")
    async with _backtest_lock:
        symbols = [s.upper() for s in (request.symbols or DEFAULT_UNIVERSE)]
        frames = await asyncio.gather(
            *[asyncio.to_thread(_fetch_history, s, request.years) for s in symbols]
        )
        data = {s: f for s, f in zip(symbols, frames, strict=True) if f is not None}
        bench = await asyncio.to_thread(_fetch_history, "^NSEI", request.years)
        if bench is None or not data:
            raise HTTPException(status_code=502, detail="Could not fetch price history.")
        cfg = SignalBacktestConfig(
            initial_capital=request.initial_capital,
            max_positions=request.max_positions,
            rebalance_days=request.rebalance_days,
            apply_tax=request.apply_tax,
        )
        try:
            result = await asyncio.to_thread(run_signal_backtest, data, bench, cfg)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        payload = result.to_dict()
        payload["missing_symbols"] = sorted(set(symbols) - set(data))
        payload["ran_at"] = datetime.now(UTC).isoformat()
        try:
            _latest_path().write_text(json.dumps(payload, default=str), encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not save signal backtest result: %s", exc)
        return payload


@router.get("/backtest/signal/latest")
async def latest_signal_backtest() -> dict:
    path = _latest_path()
    if not path.exists():
        return {"result": None}
    return {"result": json.loads(path.read_text(encoding="utf-8"))}
