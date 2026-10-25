"""Summarise how Oracle's past predictions actually turned out.

Input rows are resolved `confidence_calibration` records (see `outcomes.resolve_pending_outcomes`).
A prediction "wins" when the 7-day return went the way the signal said (BUY up, REDUCE down,
HOLD within +/-2%). The reference line is a coin flip: always saying 50% confidence scores a
Brier of 0.25, so a calibrated model must come in below that.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from aletheia.core.signals.outcomes import is_win

COIN_FLIP_BRIER = 0.25
MIN_SAMPLES = 30  # below this the numbers are anecdotes, and the response says so
_BUCKETS = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)]


def _rate(wins: int, n: int) -> float | None:
    return round(wins / n * 100, 1) if n else None


def summarize(records: list[dict[str, Any]], pending: int = 0) -> dict[str, Any]:
    rows = [r for r in records if r.get("actual_return_7d") is not None]
    n = len(rows)
    for r in rows:
        r["_win"] = is_win(r["predicted_signal"], r["actual_return_7d"])

    by_signal: dict[str, list[dict]] = defaultdict(list)
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_signal[r["predicted_signal"]].append(r)
        by_symbol[r["symbol"]].append(r)

    def block(group: list[dict]) -> dict[str, Any]:
        wins = sum(r["_win"] for r in group)
        briers = [r["brier_score"] for r in group if r.get("brier_score") is not None]
        return {
            "n": len(group),
            "hit_rate_pct": _rate(wins, len(group)),
            "avg_confidence": round(sum(r["predicted_confidence"] for r in group) / len(group), 3),
            "avg_return_7d_pct": round(sum(r["actual_return_7d"] for r in group) / len(group), 2),
            "brier": round(sum(briers) / len(briers), 4) if briers else None,
        }

    buckets = []
    for lo, hi in _BUCKETS:
        grp = [r for r in rows if lo <= r["predicted_confidence"] < hi]
        if grp:
            wins = sum(r["_win"] for r in grp)
            buckets.append(
                {
                    "range": f"{lo:.1f}-{min(hi, 1.0):.1f}",
                    "n": len(grp),
                    "claimed_pct": round(
                        sum(r["predicted_confidence"] for r in grp) / len(grp) * 100, 1
                    ),
                    "actual_hit_rate_pct": _rate(wins, len(grp)),
                }
            )

    overall = block(rows) if rows else None
    if n == 0:
        verdict = "No resolved predictions yet. Outcomes are scored 7 days after each run."
    elif n < MIN_SAMPLES:
        verdict = f"Only {n} resolved predictions; need {MIN_SAMPLES}+ before drawing conclusions."
    elif overall and overall["brier"] is not None and overall["brier"] < COIN_FLIP_BRIER:
        verdict = "Calibrated better than a coin flip so far."
    else:
        verdict = "Not better than a coin flip. Treat confidence numbers with suspicion."

    return {
        "resolved": n,
        "pending": pending,
        "enough_data": n >= MIN_SAMPLES,
        "coin_flip_brier": COIN_FLIP_BRIER,
        "overall": overall,
        "by_signal": {k: block(v) for k, v in sorted(by_signal.items())},
        "calibration": buckets,
        "by_symbol": sorted(
            ({"symbol": k, **block(v)} for k, v in by_symbol.items()), key=lambda x: -x["n"]
        ),
        "verdict": verdict,
    }
