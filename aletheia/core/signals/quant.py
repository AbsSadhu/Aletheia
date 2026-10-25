"""Deterministic quant signal: factor composite, walk-forward calibrated confidence,
ATR-based stop/target prices.

Confidence is the shrunk historical directional hit rate of this same composite on
this same symbol, measured with no look-ahead (the composite at bar t sees only bars
<= t, and is scored against the return over bars t..t+horizon). It is an empirical
frequency, not a model's self-reported certainty.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from aletheia.factors.registry import FactorRegistry, get_registry

logger = logging.getLogger(__name__)

MIN_BARS = 120  # enough for the 50-bar factors plus a calibration window
MAX_STALENESS_DAYS = 7
HORIZON = 10  # trading days a signal is scored over
STEP = 3  # bars between calibration samples
PRIOR_STRENGTH = 10  # pseudo-observations pulling hit rate toward 0.5
MIN_SAMPLES = 20  # below this, confidence is capped
LOW_SAMPLE_CAP = 0.55
ATR_PERIOD = 14
STOP_ATR_MULT = 2.0
TARGET_ATR_MULT = 3.0


@dataclass
class QuantSignal:
    signal: str  # BUY | HOLD | REDUCE
    confidence: float
    composite_score: float
    data_quality: str = "ok"
    hit_rate: float | None = None
    samples: int = 0
    atr: float | None = None
    stop_loss_price: float | None = None
    target_price: float | None = None
    notes: list[str] = field(default_factory=list)


def _to_oracle_signal(factor_signal: str) -> str:
    return "REDUCE" if factor_signal == "SELL" else factor_signal


def normalize_ohlcv(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Lower-case columns, drop NaN closes, sort ascending by index."""
    if df is None or df.empty:
        return None
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    if "close" not in out.columns:
        return None
    for col in ("open", "high", "low"):
        if col not in out.columns:
            out[col] = out["close"]
    if "volume" not in out.columns:
        out["volume"] = 0.0
    out = out.dropna(subset=["close"]).sort_index()
    return out


def check_data_quality(df: pd.DataFrame | None, today: pd.Timestamp | None = None) -> str:
    if df is None or len(df) < MIN_BARS:
        return "insufficient_history"
    last = df.index[-1]
    if not isinstance(last, pd.Timestamp):
        return "ok"
    now = today or pd.Timestamp.now(tz=last.tz)
    if (now - last).days > MAX_STALENESS_DAYS:
        return "stale"
    return "ok"


def compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float | None:
    if len(df) < period + 1:
        return None
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = float(tr.iloc[-period:].mean())
    return atr if atr == atr and atr > 0 else None


def _composite(registry: FactorRegistry, df: pd.DataFrame) -> tuple[str, float]:
    comp = registry.composite_signal(registry.compute_all(df))
    return _to_oracle_signal(comp["signal"]), float(comp["composite_score"])


def walk_forward_hit_rates(
    df: pd.DataFrame, registry: FactorRegistry
) -> dict[str, tuple[int, int]]:
    """Return {signal: (hits, total)} for BUY and REDUCE over the history.

    A BUY hits when the close HORIZON bars later is higher; a REDUCE hits when lower.
    """
    stats = {"BUY": [0, 0], "REDUCE": [0, 0]}
    closes = df["close"].to_numpy()
    last_t = len(df) - HORIZON - 1
    for t in range(MIN_BARS - 1, last_t + 1, STEP):
        sig, _ = _composite(registry, df.iloc[: t + 1])
        if sig not in stats:
            continue
        fwd = closes[t + HORIZON] - closes[t]
        stats[sig][1] += 1
        if (sig == "BUY" and fwd > 0) or (sig == "REDUCE" and fwd < 0):
            stats[sig][0] += 1
    return {k: (v[0], v[1]) for k, v in stats.items()}


def calibrated_confidence(hits: int, total: int) -> float:
    rate = (hits + 0.5 * PRIOR_STRENGTH) / (total + PRIOR_STRENGTH)
    conf = min(0.9, max(0.1, rate))
    if total < MIN_SAMPLES:
        conf = min(conf, LOW_SAMPLE_CAP)
    return round(conf, 4)


def compute_quant_signal(
    ohlcv: pd.DataFrame | None, registry: FactorRegistry | None = None
) -> QuantSignal:
    df = normalize_ohlcv(ohlcv)
    quality = check_data_quality(df)
    if quality != "ok" or df is None:
        return QuantSignal(
            signal="HOLD",
            confidence=0.0,
            composite_score=0.0,
            data_quality=quality,
            notes=[f"No signal: price history unusable ({quality})."],
        )

    registry = registry or get_registry()
    signal, score = _composite(registry, df)
    close = float(df["close"].iloc[-1])
    atr = compute_atr(df)

    out = QuantSignal(signal=signal, confidence=0.5, composite_score=score, atr=atr)

    if signal in ("BUY", "REDUCE"):
        hits, total = walk_forward_hit_rates(df, registry)[signal]
        out.samples = total
        out.hit_rate = round(hits / total, 4) if total else None
        out.confidence = calibrated_confidence(hits, total)
        out.notes.append(
            f"Walk-forward {signal} hit rate {hits}/{total} over {HORIZON}-day horizon."
        )
        if total < MIN_SAMPLES:
            out.notes.append(f"Only {total} historical samples — confidence capped.")

    if atr is not None and signal in ("BUY", "HOLD"):
        out.stop_loss_price = round(close - STOP_ATR_MULT * atr, 2)
        if signal == "BUY":
            out.target_price = round(close + TARGET_ATR_MULT * atr, 2)
    return out
