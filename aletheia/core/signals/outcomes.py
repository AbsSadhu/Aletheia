"""Close the calibration loop: score past Oracle predictions against what the price did.

Records are written at the end of every run (`RunService`), but nothing used to fill in the
outcomes, so `get_calibration_score` (and the PM's "poorly calibrated" haircut) never fired.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Awaitable, Callable

import pandas as pd

from aletheia.core.db.sqlite_store import SQLiteStore
from aletheia.core.signals.quant import normalize_ohlcv

logger = logging.getLogger(__name__)

HOLD_BAND_PCT = 2.0  # a HOLD "wins" if the price stayed within +/- this over the window
Loader = Callable[[str], Awaitable[pd.DataFrame | None]]


def _return_pct(closes: pd.Series, start: pd.Timestamp, days: int) -> float | None:
    """% change from the last close at/before `start` to the first close at/after start+days."""
    before = closes[closes.index <= start]
    after = closes[closes.index >= start + pd.Timedelta(days=days)]
    if before.empty or after.empty:
        return None
    return float((after.iloc[0] / before.iloc[-1] - 1.0) * 100)


def is_win(signal: str, ret_pct: float) -> bool:
    if signal == "BUY":
        return ret_pct > 0
    if signal == "REDUCE":
        return ret_pct < 0
    return abs(ret_pct) <= HOLD_BAND_PCT


def brier_for(signal: str, confidence: float, ret_pct: float) -> float:
    return round((confidence - (1.0 if is_win(signal, ret_pct) else 0.0)) ** 2, 4)


async def resolve_pending_outcomes(
    sqlite_store: SQLiteStore, loader: Loader, days_old: int = 7
) -> int:
    """Fill 7d/30d returns and Brier scores for Oracle records old enough. Returns count resolved."""
    resolved = 0
    for rec in sqlite_store.get_pending_calibration_records(days_old=days_old):
        if rec.get("agent", "oracle") != "oracle":
            continue
        df = normalize_ohlcv(await loader(rec["symbol"]))
        if df is None:
            continue
        closes = df["close"]
        if closes.index.tz is not None:
            closes = closes.tz_localize(None)
        start = pd.Timestamp(dt.datetime.fromisoformat(rec["recorded_at"])).tz_localize(None)
        r7 = _return_pct(closes, start, 7)
        if r7 is None:
            continue
        r30 = _return_pct(closes, start, 30)
        sqlite_store.update_calibration_outcome(
            record_id=rec["record_id"],
            actual_return_7d=round(r7, 4),
            actual_return_30d=None if r30 is None else round(r30, 4),
            brier_score=brier_for(rec["predicted_signal"], rec["predicted_confidence"], r7),
        )
        resolved += 1
    logger.info("Calibration: resolved %d pending Oracle outcomes.", resolved)
    return resolved
