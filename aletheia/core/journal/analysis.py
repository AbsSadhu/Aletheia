"""Pair trades into round trips, profile the trader, and test for four behavioural patterns.

The diagnostics are adapted from Vibe-Trading's trade-journal analyzer (MIT; see
THIRD_PARTY_NOTICES.md): disposition effect, overtrading, momentum chasing and anchoring, each
with a severity and the numbers behind it. Differences from the original: pairing is signed FIFO
(a sell that opens a position is a short and is matched against the later buy, which matters for
intraday traders), every round trip is classed intraday / short-term / long-term, and a realized
XIRR is reported.

Nothing here predicts anything. It describes what the journal shows and says how strongly.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import brentq

EPS = 1e-9
#: Held strictly longer than this many days is long-term for listed Indian equity.
LONG_TERM_DAYS = 365
#: A realized XIRR beyond this is an artefact of very short holds, not a rate anyone earned.
XIRR_SANE_LIMIT = 10.0


def _rupees(value: float) -> str:
    return f"{'-' if value < 0 else '+'}₹{abs(value):,.0f}"


def pair_trades(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Signed FIFO. Returns (closed round trips, still-open positions)."""
    lots: dict[str, deque] = defaultdict(deque)
    trips: list[dict[str, Any]] = []
    for row in df.itertuples(index=False):
        sign = 1 if row.side == "buy" else -1
        remaining = float(row.quantity)
        queue = lots[row.symbol]
        while remaining > EPS and queue and queue[0]["dir"] == -sign:
            lot = queue[0]
            take = min(lot["qty"], remaining)
            entry_fee = lot["fee"] * (take / lot["qty"]) if lot["qty"] else 0.0
            exit_fee = row.fee * (take / row.quantity) if row.quantity else 0.0
            gross = (row.price - lot["price"]) * take * lot["dir"]
            pnl = gross - entry_fee - exit_fee
            cost = lot["price"] * take
            entry_dt, exit_dt = pd.Timestamp(lot["dt"]), pd.Timestamp(row.datetime)
            hold = max(0.0, (exit_dt - entry_dt).total_seconds() / 86400.0)
            if exit_dt.date() == entry_dt.date():
                category = "intraday"
            elif (exit_dt.date() - entry_dt.date()).days > LONG_TERM_DAYS:
                category = "long_term"
            else:
                category = "short_term"
            trips.append(
                {
                    "symbol": row.symbol,
                    "direction": "long" if lot["dir"] == 1 else "short",
                    "entry_dt": entry_dt,
                    "exit_dt": exit_dt,
                    "qty": take,
                    "entry_price": lot["price"],
                    "exit_price": float(row.price),
                    "hold_days": round(hold, 3),
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl / cost, 5) if cost else 0.0,
                    "fees": round(entry_fee + exit_fee, 2),
                    "category": category,
                }
            )
            lot["fee"] -= entry_fee
            lot["qty"] -= take
            remaining -= take
            if lot["qty"] <= EPS:
                queue.popleft()
        if remaining > EPS:
            queue.append(
                {
                    "dt": row.datetime,
                    "qty": remaining,
                    "price": float(row.price),
                    "fee": row.fee * (remaining / row.quantity) if row.quantity else 0.0,
                    "dir": sign,
                }
            )
    open_positions = [
        {
            "symbol": sym,
            "direction": "long" if q[0]["dir"] == 1 else "short",
            "quantity": round(sum(lot["qty"] for lot in q), 4),
            "average_price": round(
                sum(lot["qty"] * lot["price"] for lot in q) / sum(lot["qty"] for lot in q), 4
            ),
            "since": pd.Timestamp(q[0]["dt"]).isoformat(),
        }
        for sym, q in lots.items()
        if q and sum(lot["qty"] for lot in q) > EPS
    ]
    return trips, open_positions


def xirr(flows: list[tuple[pd.Timestamp, float]]) -> float | None:
    """Annualized internal rate of return for dated cash flows, or None when it is not defined."""
    flows = [(pd.Timestamp(t), float(v)) for t, v in flows if v]
    if len(flows) < 2:
        return None
    if not (any(v < 0 for _, v in flows) and any(v > 0 for _, v in flows)):
        return None
    t0 = min(t for t, _ in flows)
    years = np.array([(t - t0).total_seconds() / (365.0 * 86400) for t, _ in flows])
    amounts = np.array([v for _, v in flows])
    if years.max() < 30 / 365:
        return None

    def npv(rate: float) -> float:
        return float(np.sum(amounts / np.power(1.0 + rate, years)))

    try:
        return float(brentq(npv, -0.999, 1000.0, maxiter=200))
    except ValueError:
        return None


def realized_xirr(trips: list[dict[str, Any]]) -> dict[str, Any]:
    flows: list[tuple[pd.Timestamp, float]] = []
    for t in trips:
        cost = t["entry_price"] * t["qty"]
        proceeds = t["exit_price"] * t["qty"]
        if t["direction"] == "long":
            flows += [(t["entry_dt"], -cost), (t["exit_dt"], proceeds - t["fees"])]
        else:
            flows += [(t["entry_dt"], cost), (t["exit_dt"], -proceeds - t["fees"])]
    rate = xirr(flows)
    if rate is None:
        return {
            "value": None,
            "note": "Needs closed trades spanning at least a month with both gains and outlays.",
        }
    if abs(rate) > XIRR_SANE_LIMIT:
        return {
            "value": None,
            "note": "Not meaningful here: holding periods are too short for an annualized rate to say anything.",
        }
    return {
        "value": round(rate, 4),
        "note": "Annualized return on the money deployed in closed trades, weighted by when it was out.",
    }


def _safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b else 0.0


def build_profile(
    df: pd.DataFrame, trips: list[dict[str, Any]], opens: list[dict[str, Any]]
) -> dict[str, Any]:
    t = pd.DataFrame(trips)
    span_days = max(1, (df["datetime"].max() - df["datetime"].min()).days)
    base: dict[str, Any] = {
        "total_trades": int(len(df)),
        "symbols": int(df["symbol"].nunique()),
        "first_trade": df["datetime"].min().isoformat(),
        "last_trade": df["datetime"].max().isoformat(),
        "trades_per_week": round(len(df) / span_days * 7, 2),
        "closed_round_trips": int(len(t)),
        "open_positions": opens,
        "xirr": realized_xirr(trips),
    }
    if t.empty:
        return {
            **base,
            "note": "No round trips closed in this file yet (every position is still open).",
        }
    wins, losses = t[t["pnl"] > 0], t[t["pnl"] < 0]
    avg_win = float(wins["pnl"].mean()) if len(wins) else 0.0
    avg_loss = float(losses["pnl"].mean()) if len(losses) else 0.0
    ordered = t.sort_values("exit_dt")
    cum = ordered["pnl"].cumsum()
    drawdown = float((cum - cum.cummax()).min()) if len(cum) else 0.0
    gross_wins, gross_losses = float(wins["pnl"].sum()), float(-losses["pnl"].sum())

    by_cat = {}
    for cat, sub in t.groupby("category"):
        by_cat[cat] = {
            "trips": int(len(sub)),
            "pnl": round(float(sub["pnl"].sum()), 2),
            "win_rate": round(float((sub["pnl"] > 0).mean()), 4),
        }

    by_symbol = (
        t.groupby("symbol")
        .agg(
            trips=("pnl", "size"),
            pnl=("pnl", "sum"),
            win_rate=("pnl", lambda s: float((s > 0).mean())),
        )
        .sort_values("pnl", ascending=False)
        .reset_index()
    )
    by_symbol["pnl"] = by_symbol["pnl"].round(2)
    by_symbol["win_rate"] = by_symbol["win_rate"].round(4)

    monthly = ordered.groupby(ordered["exit_dt"].dt.strftime("%Y-%m"))["pnl"].sum().round(2)
    entries = t["entry_dt"]
    curve = ordered.assign(cum=cum.round(2))[["exit_dt", "cum"]]
    return {
        **base,
        "win_rate": round(len(wins) / len(t), 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_loss_ratio": round(_safe_div(avg_win, abs(avg_loss)), 2) if avg_loss else None,
        "profit_factor": round(_safe_div(gross_wins, gross_losses), 2) if gross_losses else None,
        "expectancy": round(float(t["pnl"].mean()), 2),
        "total_pnl": round(float(t["pnl"].sum()), 2),
        "fees_paid": round(float(t["fees"].sum()), 2),
        "max_drawdown": round(drawdown, 2),
        "avg_hold_days": round(float(t["hold_days"].mean()), 2),
        "best_trip": _trip_out(t.loc[t["pnl"].idxmax()]),
        "worst_trip": _trip_out(t.loc[t["pnl"].idxmin()]),
        "by_category": by_cat,
        "by_symbol": by_symbol.head(12).to_dict(orient="records"),
        "monthly_pnl": [{"month": m, "pnl": float(v)} for m, v in monthly.items()],
        "pnl_curve": [
            {"t": r.exit_dt.isoformat(), "v": float(r.cum)} for r in curve.itertuples(index=False)
        ],
        "entries_by_hour": {
            int(h): int(c) for h, c in entries.dt.hour.value_counts().sort_index().items()
        },
        "entries_by_weekday": {
            int(d): int(c) for d, c in entries.dt.dayofweek.value_counts().sort_index().items()
        },
    }


def _trip_out(row: pd.Series) -> dict[str, Any]:
    return {
        "symbol": row["symbol"],
        "direction": row["direction"],
        "pnl": float(row["pnl"]),
        "entry": pd.Timestamp(row["entry_dt"]).isoformat(),
        "exit": pd.Timestamp(row["exit_dt"]).isoformat(),
    }


def trips_for_output(trips: list[dict[str, Any]], limit: int = 200) -> list[dict[str, Any]]:
    out = []
    for t in sorted(trips, key=lambda x: x["exit_dt"], reverse=True)[:limit]:
        out.append(
            {**t, "entry_dt": t["entry_dt"].isoformat(), "exit_dt": t["exit_dt"].isoformat()}
        )
    return out


def _severity(score: float, thresholds: tuple[float, float]) -> str:
    med, high = thresholds
    return "high" if score >= high else "medium" if score >= med else "low"


def disposition_effect(t: pd.DataFrame) -> dict[str, Any]:
    """Holding losers longer than winners. Metric: average loser hold / average winner hold."""
    if t.empty:
        return {"severity": "low", "evidence": "No closed round trips yet."}
    wins, losses = t[t["pnl"] > 0], t[t["pnl"] < 0]
    if wins.empty or losses.empty:
        return {
            "severity": "low",
            "evidence": "Needs both winning and losing trades to compare how long each was held.",
        }
    win_hold, loss_hold = float(wins["hold_days"].mean()), float(losses["hold_days"].mean())
    if win_hold <= 0:
        # winners all closed within the same instant: compare against a one-minute floor
        win_hold = 1 / 1440
    ratio = loss_hold / win_hold
    sev = _severity(ratio, (1.2, 1.5))
    verdict = (
        "Losers are held far longer than winners."
        if sev == "high"
        else "Losers are held somewhat longer than winners."
        if sev == "medium"
        else "Hold times for winners and losers are about even."
    )
    return {
        "severity": sev,
        "ratio_loss_to_win_hold": round(ratio, 2),
        "avg_winner_hold_days": round(win_hold, 2),
        "avg_loser_hold_days": round(loss_hold, 2),
        "evidence": f"Losing trades were held {loss_hold:.1f} days against {win_hold:.1f} for winners (ratio {ratio:.2f}). {verdict}",
    }


def overtrading(df: pd.DataFrame, t: pd.DataFrame) -> dict[str, Any]:
    """Do the busiest days earn less than the quietest? Compares realised P&L by trade-count quartile."""
    if df.empty or t.empty:
        return {"severity": "low", "evidence": "Not enough data."}
    daily = df.groupby(df["datetime"].dt.date).size()
    if len(daily) < 4:
        return {"severity": "low", "evidence": "Needs at least four trading days."}
    busy_cut, quiet_cut = daily.quantile(0.75), daily.quantile(0.25)
    busy_days = set(daily[daily >= busy_cut].index)
    quiet_days = set(daily[daily <= quiet_cut].index)
    exit_dates = t["exit_dt"].dt.date
    busy, quiet = t[exit_dates.isin(busy_days)]["pnl"], t[exit_dates.isin(quiet_days)]["pnl"]
    if busy.empty or quiet.empty:
        return {
            "severity": "low",
            "evidence": "Round trips are not spread across both busy and quiet days.",
        }
    busy_avg, quiet_avg = float(busy.mean()), float(quiet.mean())
    gap = quiet_avg - busy_avg
    base = abs(quiet_avg) if quiet_avg else 1.0
    sev = _severity(gap / base, (0.3, 1.0)) if busy_avg < quiet_avg else "low"
    verdict = (
        "Heavy trading days earn clearly less."
        if sev == "high"
        else "Some drag from heavy trading days."
        if sev == "medium"
        else "Trading volume does not visibly hurt results."
    )
    return {
        "severity": sev,
        "busy_day_avg_pnl": round(busy_avg, 2),
        "quiet_day_avg_pnl": round(quiet_avg, 2),
        "busy_day_trade_threshold": round(float(busy_cut), 1),
        "evidence": f"On busy days (at least {busy_cut:.0f} trades) the average trade made {_rupees(busy_avg)}; on quiet days (at most {quiet_cut:.0f}) {_rupees(quiet_avg)}. {verdict}",
    }


def chasing_momentum(df: pd.DataFrame) -> dict[str, Any]:
    """Buying after a run-up: a buy is a chase if its price is over 3% above your own price three buys earlier."""
    buys = df[df["side"] == "buy"].sort_values(["symbol", "datetime"]).copy()
    if buys.empty:
        return {"severity": "low", "evidence": "No buys in this file."}
    buys["prev3"] = buys.groupby("symbol")["price"].shift(3)
    matured = buys.dropna(subset=["prev3"])
    if matured.empty:
        return {
            "severity": "low",
            "evidence": "Needs at least four buys of the same symbol to compare.",
        }
    chased = matured[matured["price"] > matured["prev3"] * 1.03]
    ratio = len(chased) / len(matured)
    sev = _severity(ratio, (0.4, 0.6))
    verdict = (
        "A strong tendency to buy after a run-up."
        if sev == "high"
        else "Some tendency to buy after a run-up."
        if sev == "medium"
        else "No clear habit of chasing."
    )
    return {
        "severity": sev,
        "chase_ratio": round(ratio, 3),
        "buys_evaluated": int(len(matured)),
        "evidence": f"{len(chased)} of {len(matured)} buys ({ratio:.0%}) came after the price had risen over 3% from your earlier buy in the same symbol. {verdict}",
    }


def anchoring(df: pd.DataFrame) -> dict[str, Any]:
    """Trading the same price area again and again. Per symbol with 5 or more trades: spread of price / mean price."""
    rows = []
    for sym, sub in df.groupby("symbol"):
        if len(sub) < 5:
            continue
        mean, std = float(sub["price"].mean()), float(sub["price"].std())
        if mean == 0 or math.isnan(std):
            continue
        rows.append(
            {
                "symbol": sym,
                "trades": int(len(sub)),
                "mean_price": round(mean, 2),
                "cv": round(std / mean, 4),
            }
        )
    if not rows:
        return {"severity": "low", "evidence": "Needs a symbol traded at least five times."}
    anchored = [r for r in rows if r["cv"] < 0.05]
    ratio = len(anchored) / len(rows)
    sev = _severity(ratio, (0.33, 0.66))
    verdict = (
        "Repeated trades cluster at the same prices."
        if sev == "high"
        else "Some symbols are traded at the same prices again and again."
        if sev == "medium"
        else "Prices vary naturally across repeat trades."
    )
    return {
        "severity": sev,
        "anchored_symbol_ratio": round(ratio, 3),
        "symbols_evaluated": len(rows),
        "anchored_symbols": anchored[:5],
        "evidence": f"{len(anchored)} of {len(rows)} frequently traded symbols stayed within a 5% price band. {verdict}",
    }


def build_behavior(df: pd.DataFrame, trips: list[dict[str, Any]]) -> dict[str, Any]:
    t = pd.DataFrame(trips)
    return {
        "disposition_effect": disposition_effect(t),
        "overtrading": overtrading(df, t),
        "chasing_momentum": chasing_momentum(df),
        "anchoring": anchoring(df),
    }


_TITLES = {
    "disposition_effect": "Holding losers longer than winners",
    "overtrading": "Trading more on days that pay less",
    "chasing_momentum": "Buying after run-ups",
    "anchoring": "Returning to the same prices",
}


def findings(behavior: dict[str, Any]) -> list[dict[str, str]]:
    """The patterns worth a look, strongest first."""
    order = {"high": 0, "medium": 1}
    out = [
        {"key": k, "title": _TITLES[k], "severity": v["severity"], "evidence": v["evidence"]}
        for k, v in behavior.items()
        if v.get("severity") in order
    ]
    return sorted(out, key=lambda f: order[f["severity"]])


def analyze(df: pd.DataFrame) -> dict[str, Any]:
    trips, opens = pair_trades(df)
    behavior = build_behavior(df, trips)
    return {
        "profile": build_profile(df, trips, opens),
        "behavior": behavior,
        "findings": findings(behavior),
        "round_trips": trips_for_output(trips),
        "method": (
            "Trades are matched first-in first-out per symbol; a sell that opens a position is treated as a short. "
            "The four behaviour checks use fixed thresholds and describe patterns in this file only. They are not advice."
        ),
    }
