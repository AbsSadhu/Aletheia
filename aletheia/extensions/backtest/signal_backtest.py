"""Walk-forward backtest of the Oracle signal (the factor composite), judged against benchmarks.

Question it answers: *would acting on these signals have beaten simply holding Nifty, after
costs and tax?* It is deliberately strict about the ways backtests flatter themselves:

  - No look-ahead: a decision on day t sees bars <= t only, and fills at the NEXT bar's open.
  - Real frictions: commission + spread + slippage on both sides, plus India's delivery STT.
  - Tax: realised gains are taxed per financial year (STCG/LTCG rates from `tax_rates`, LTCG
    exemption applied, short-term losses set off). Benchmarks are shown pre-tax, which is
    *generous to them* only in that buy-and-hold defers tax; the comparison is still reported
    after-tax for the strategy so the cost of turnover is visible.
  - Benchmarks: Nifty 50 buy-and-hold AND an equal-weight buy-and-hold of the same universe, so
    "the strategy beat the index" can't just mean "the universe beat the index".
  - Out-of-sample split: results are also reported for the last 40% of the period.

What it cannot fix is listed in `caveats` and returned with every result (survivorship bias in
the universe being the big one).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from aletheia.core.models import TaxProfile
from aletheia.core.signals.quant import MIN_BARS, compute_atr, normalize_ohlcv
from aletheia.extensions.backtest.tax_rates import TAX_RATE_TABLE
from aletheia.factors.registry import FactorRegistry, get_registry

TRADING_DAYS = 252
LTCG_EXEMPTION_INR = (
    125_000.0  # per FY, equity (assumed; see tax_rates for the verification caveat)
)
MIN_TRADES_FOR_VERDICT = 30

# Current Nifty large caps. NOTE: today's constituents -> survivorship bias (see caveats).
DEFAULT_UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", "SBIN",
    "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA",
    "TITAN", "BAJFINANCE", "NESTLEIND", "ULTRACEMCO", "WIPRO", "HCLTECH", "POWERGRID",
    "NTPC", "TATAMOTORS", "TATASTEEL",
]  # fmt: skip

CAVEATS = [
    "Survivorship bias: the universe is today's large caps, so names that fell out of the index "
    "(or were delisted) are missing. This flatters every stock-picking result.",
    "Daily bars only: stops are checked against the daily low, so intraday sequencing is unknown.",
    "Prices are yfinance split/dividend-adjusted closes; they can differ slightly from exchange data.",
    "Tax is a simplified per-financial-year model (no loss carry-forward, surcharge or cess); "
    "the tax rate table is itself marked unverified.",
    "Past performance of a fixed rule over one period is not a forecast.",
]


@dataclass
class SignalBacktestConfig:
    initial_capital: float = 1_000_000.0
    rebalance_days: int = 5
    max_positions: int = 10
    stop_atr_mult: float = 2.0
    commission_bps: float = 2.0
    spread_bps: float = 1.0
    slippage_bps: float = 3.0
    stt_bps: float = 10.0  # delivery STT, charged on both buy and sell
    risk_free_pct: float = 6.5
    oos_fraction: float = 0.4
    window_bars: int = 300  # bars of history shown to the factors at each decision
    apply_tax: bool = True

    @property
    def one_way_bps(self) -> float:
        return self.commission_bps + self.spread_bps + self.slippage_bps + self.stt_bps


@dataclass
class Trade:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    qty: int
    exit_date: pd.Timestamp | None = None
    exit_price: float | None = None
    exit_reason: str = ""
    stop: float | None = None
    pnl: float = 0.0  # net of costs, before tax

    @property
    def holding_days(self) -> int:
        return int(((self.exit_date or self.entry_date) - self.entry_date).days)


def _clean(df: pd.DataFrame | None) -> pd.DataFrame | None:
    out = normalize_ohlcv(df)
    if out is None:
        return None
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    out.index = out.index.normalize()
    return out[~out.index.duplicated(keep="last")]


def _fy(ts: pd.Timestamp) -> int:
    """Indian financial year label: Apr 2023 - Mar 2024 -> 2023."""
    return int(ts.year if ts.month >= 4 else ts.year - 1)


def tax_on_trades(trades: list[Trade]) -> float:
    """Per-FY capital-gains tax. Short-term losses offset short- then long-term gains;
    long-term losses offset long-term gains only; LTCG exemption applies before the rate."""
    rates = TAX_RATE_TABLE[TaxProfile.EQUITY]
    stcg_rate, ltcg_rate = rates["short"].rate_pct / 100, rates["long"].rate_pct / 100
    by_fy: dict[int, dict[str, float]] = {}
    for t in trades:
        if t.exit_date is None:
            continue
        bucket = by_fy.setdefault(_fy(t.exit_date), {"st": 0.0, "lt": 0.0})
        bucket["lt" if t.holding_days >= 365 else "st"] += t.pnl
    total = 0.0
    for b in by_fy.values():
        st, lt = b["st"], b["lt"]
        if st < 0:  # set the short-term loss off against long-term gains
            lt += st
            st = 0.0
        lt = max(lt, 0.0)
        total += max(st, 0.0) * stcg_rate + max(lt - LTCG_EXEMPTION_INR, 0.0) * ltcg_rate
    return total


def _metrics(equity: pd.Series, bench: pd.Series | None, rf_pct: float) -> dict[str, float]:
    equity = equity.dropna()
    if len(equity) < 3 or equity.iloc[0] <= 0:
        return {}
    rets = equity.pct_change().dropna()
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    total = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if equity.iloc[-1] > 0 else -1.0
    vol = float(rets.std() * math.sqrt(TRADING_DAYS))
    rf_daily = (1 + rf_pct / 100) ** (1 / TRADING_DAYS) - 1
    sd = float(rets.std())
    sharpe = float((rets.mean() - rf_daily) / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else 0.0
    dd = float(((equity.cummax() - equity) / equity.cummax()).max())
    out = {
        "total_return_pct": round(total * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "volatility_pct": round(vol * 100, 2),
        "sharpe": round(sharpe, 3),
        "max_drawdown_pct": round(dd * 100, 2),
    }
    if bench is not None:
        b = bench.reindex(equity.index).ffill().pct_change().dropna()
        r = rets.reindex(b.index).dropna()
        b = b.reindex(r.index)
        if len(r) > 10 and b.var() > 0:
            beta = float(np.cov(r, b)[0, 1] / b.var())
            alpha = float((r.mean() - beta * b.mean()) * TRADING_DAYS)
            active = r - b
            ir = (
                float(active.mean() / active.std() * math.sqrt(TRADING_DAYS))
                if active.std() > 0
                else 0.0
            )
            out.update(
                beta=round(beta, 3), alpha_pct=round(alpha * 100, 2), information_ratio=round(ir, 3)
            )
    return out


def _buy_and_hold(
    prices: pd.DataFrame, calendar: pd.DatetimeIndex, capital: float, cost_bps: float
) -> pd.Series:
    """Equal-weight at the first date, never rebalanced; one entry cost, no exit."""
    px = prices.reindex(calendar).ffill()
    first = px.iloc[0].dropna()
    if first.empty:
        return pd.Series(dtype=float)
    per = capital * (1 - cost_bps / 10_000) / len(first)
    units = per / first
    return (px[first.index] * units).sum(axis=1)


@dataclass
class SignalBacktestResult:
    config: dict[str, Any]
    period: dict[str, Any]
    strategy: dict[str, Any]
    strategy_post_tax: dict[str, Any]
    nifty: dict[str, Any]
    equal_weight: dict[str, Any]
    out_of_sample: dict[str, Any]
    trading: dict[str, Any]
    verdict: dict[str, Any]
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    caveats: list[str] = field(default_factory=lambda: list(CAVEATS))

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def run_signal_backtest(
    data: dict[str, pd.DataFrame],
    benchmark: pd.DataFrame,
    config: SignalBacktestConfig | None = None,
    registry: FactorRegistry | None = None,
    start: str | None = None,
    end: str | None = None,
) -> SignalBacktestResult:
    cfg = config or SignalBacktestConfig()
    registry = registry or get_registry()
    bench_df = _clean(benchmark)
    if bench_df is None:
        raise ValueError("Benchmark (Nifty) history is required.")
    frames = {s: f for s, f in ((s, _clean(d)) for s, d in data.items()) if f is not None}
    frames = {s: f for s, f in frames.items() if len(f) >= MIN_BARS + 30}
    if not frames:
        raise ValueError(f"No symbol has at least {MIN_BARS + 30} bars of history.")

    calendar = bench_df.index
    if start:
        calendar = calendar[calendar >= pd.Timestamp(start)]
    if end:
        calendar = calendar[calendar <= pd.Timestamp(end)]
    if len(calendar) < MIN_BARS + 30:
        raise ValueError("Benchmark calendar too short for the requested period.")

    closes = pd.DataFrame({s: f["close"] for s, f in frames.items()}).reindex(calendar).ffill()
    cost = cfg.one_way_bps / 10_000

    cash = cfg.initial_capital
    open_pos: dict[str, Trade] = {}
    closed: list[Trade] = []
    equity: list[float] = []
    equity_dates: list[pd.Timestamp] = []
    invested: list[float] = []
    costs_paid = 0.0
    pending: dict[str, str] = {}  # symbol -> "buy"/"sell", decided yesterday, fills at today's open
    warmup = MIN_BARS

    def bar(sym: str, ts: pd.Timestamp) -> pd.Series | None:
        f = frames[sym]
        return f.loc[ts] if ts in f.index else None

    for i, ts in enumerate(calendar):
        # 1) Fill yesterday's decisions at today's open.
        buys = [s for s, a in pending.items() if a == "buy"]
        for sym, action in list(pending.items()):
            b = bar(sym, ts)
            if b is None:
                continue  # can't trade today; try again next bar
            px = float(b["open"])
            if action == "sell":
                pending.pop(sym)
                if sym in open_pos:
                    t = open_pos.pop(sym)
                    fill = px * (1 - cost)
                    cash += fill * t.qty
                    costs_paid += px * cost * t.qty
                    t.exit_date, t.exit_price, t.exit_reason = ts, fill, "signal"
                    t.pnl = (fill - t.entry_price) * t.qty
                    closed.append(t)
        if buys:
            equity_now = cash + sum(
                t.qty * float(closes[s].iloc[max(i - 1, 0)]) for s, t in open_pos.items()
            )
            slot_value = equity_now / cfg.max_positions
            for sym in buys:
                pending.pop(sym, None)
                b = bar(sym, ts)
                if b is None or sym in open_pos or len(open_pos) >= cfg.max_positions:
                    continue
                fill = float(b["open"]) * (1 + cost)
                qty = int(min(slot_value, cash) // fill)
                if qty < 1:
                    continue
                hist = frames[sym].loc[:ts].iloc[:-1]  # up to yesterday: ATR known at decision time
                atr = compute_atr(hist)
                stop = fill - cfg.stop_atr_mult * atr if atr else None
                cash -= fill * qty
                costs_paid += float(b["open"]) * cost * qty
                open_pos[sym] = Trade(sym, ts, fill, qty, stop=stop)

        # 2) Intraday-ish stop check on daily bars (gap-aware).
        for sym, t in list(open_pos.items()):
            b = bar(sym, ts)
            if b is None or t.stop is None or ts == t.entry_date:
                continue
            if float(b["low"]) <= t.stop:
                raw = min(float(b["open"]), t.stop)
                px = raw * (1 - cost)
                cash += px * t.qty
                costs_paid += raw * cost * t.qty
                t.exit_date, t.exit_price, t.exit_reason = ts, px, "stop"
                t.pnl = (px - t.entry_price) * t.qty
                closed.append(t)
                del open_pos[sym]

        # 3) Mark to market at the close.
        mtm = cash + sum(t.qty * float(closes[s].iloc[i]) for s, t in open_pos.items())
        equity.append(mtm)
        invested.append(1 - cash / mtm if mtm > 0 else 0.0)
        equity_dates.append(ts)

        # 4) Decide for tomorrow (uses bars <= today only).
        if i >= warmup and (i - warmup) % cfg.rebalance_days == 0 and i < len(calendar) - 1:
            ranked: list[tuple[float, str]] = []
            for sym, f in frames.items():
                window = f.loc[:ts].tail(cfg.window_bars)
                if len(window) < MIN_BARS or window.index[-1] < ts - pd.Timedelta(days=7):
                    continue
                comp = registry.composite_signal(registry.compute_all(window))
                sig = "REDUCE" if comp["signal"] == "SELL" else comp["signal"]
                if sym in open_pos and sig == "REDUCE":
                    pending[sym] = "sell"
                elif sym not in open_pos and sig == "BUY":
                    ranked.append((comp["composite_score"], sym))
            free = cfg.max_positions - len(open_pos)
            for _, sym in sorted(ranked, reverse=True)[: max(free, 0)]:
                pending[sym] = "buy"

    # Close what's still open at the last close so P&L and tax are complete.
    last = calendar[-1]
    for sym, t in list(open_pos.items()):
        raw = float(closes[sym].iloc[-1])
        px = raw * (1 - cost)
        costs_paid += raw * cost * t.qty
        t.exit_date, t.exit_price, t.exit_reason = last, px, "end_of_test"
        t.pnl = (px - t.entry_price) * t.qty
        closed.append(t)
    gross_final = equity[-1]

    eq = pd.Series(equity, index=equity_dates)
    test_idx = eq.index[warmup:]  # the first `warmup` bars are only data-gathering
    eq = eq.loc[test_idx]
    nifty = bench_df["close"].reindex(calendar).ffill().loc[test_idx]
    nifty_bh = nifty / nifty.iloc[0] * cfg.initial_capital * (1 - cost)
    ew = _buy_and_hold(closes.loc[test_idx], test_idx, cfg.initial_capital, cfg.one_way_bps)

    tax = tax_on_trades(closed) if cfg.apply_tax else 0.0
    post_tax_final = gross_final - tax
    eq_post = eq.copy()
    eq_post.iloc[-1] = post_tax_final  # tax is paid once, at the end of the test

    split = int(len(test_idx) * (1 - cfg.oos_fraction))
    oos_idx = test_idx[split:]

    def block(series: pd.Series, bench: pd.Series | None = None) -> dict[str, Any]:
        return _metrics(series, bench if bench is not None else nifty_bh, cfg.risk_free_pct)

    strat = block(eq)
    strat_pt = block(eq_post)
    nif = _metrics(nifty_bh, None, cfg.risk_free_pct)
    ewm = block(ew) if len(ew) else {}
    oos = {
        "start": str(oos_idx[0].date()) if len(oos_idx) else None,
        "strategy_post_tax": _metrics(eq_post.loc[oos_idx], nifty_bh, cfg.risk_free_pct),
        "nifty": _metrics(nifty_bh.loc[oos_idx], None, cfg.risk_free_pct),
        "note": "Last 40% of the period. The rule has fixed parameters (nothing was fitted), "
        "so this checks stability across regimes rather than curing overfitting.",
    }

    n = len(closed)
    wins = sum(1 for t in closed if t.pnl > 0)
    avg_invested = float(np.mean(invested[warmup:])) if invested[warmup:] else 0.0
    trading = {
        "trades": n,
        "win_rate_pct": round(wins / n * 100, 1) if n else 0.0,
        "avg_holding_days": round(float(np.mean([t.holding_days for t in closed])), 1) if n else 0,
        "stopped_out_pct": round(sum(t.exit_reason == "stop" for t in closed) / n * 100, 1)
        if n
        else 0.0,
        "trading_costs_inr": round(costs_paid, 2),
        "tax_paid_inr": round(tax, 2),
        "gross_final_equity": round(gross_final, 2),
        "post_tax_final_equity": round(post_tax_final, 2),
        "avg_invested_pct": round(avg_invested * 100, 1),
    }

    reasons: list[str] = []
    s_cagr, n_cagr = strat_pt.get("cagr_pct", -999), nif.get("cagr_pct", 999)
    if s_cagr <= n_cagr:
        reasons.append(f"Post-tax CAGR {s_cagr}% does not beat Nifty buy-and-hold {n_cagr}%.")
    if strat_pt.get("sharpe", -9) <= nif.get("sharpe", 9):
        reasons.append("Post-tax Sharpe is not above Nifty's.")
    oos_s = _metrics(eq_post.loc[oos_idx], nifty_bh, cfg.risk_free_pct).get("cagr_pct", -999)
    oos_n = _metrics(nifty_bh.loc[oos_idx], None, cfg.risk_free_pct).get("cagr_pct", 999)
    if oos_s <= oos_n:
        reasons.append(f"Out-of-sample CAGR {oos_s}% does not beat Nifty {oos_n}%.")
    ew_cagr = ewm.get("cagr_pct")
    if ew_cagr is not None and s_cagr <= ew_cagr:
        reasons.append(
            f"Does not beat equal-weight buy-and-hold of the same stocks ({ew_cagr}%): "
            "any outperformance of Nifty is the universe, not the signal."
        )
    if n < MIN_TRADES_FOR_VERDICT:
        status = "INCONCLUSIVE"
        reasons.append(f"Only {n} trades (< {MIN_TRADES_FOR_VERDICT}); too few to judge.")
    elif reasons:
        status = "FAIL"
    else:
        status = "PASS"
    headline = {
        "PASS": "Beat Nifty and equal-weight after costs and tax, in-sample and out-of-sample.",
        "FAIL": "Did not clear the bar. Do not rely on these signals for real money.",
        "INCONCLUSIVE": "Not enough trades to say either way.",
    }[status]

    step = max(len(eq) // 400, 1)
    curve = [
        {
            "date": str(d.date()),
            "strategy": round(float(eq.iloc[k]), 2),
            "nifty": round(float(nifty_bh.iloc[k]), 2),
            "equal_weight": round(float(ew.iloc[k]), 2) if len(ew) else None,
        }
        for k, d in enumerate(eq.index)
        if k % step == 0 or k == len(eq) - 1
    ]
    return SignalBacktestResult(
        config={k: v for k, v in cfg.__dict__.items()}
        | {"universe_size": len(frames), "symbols": sorted(frames)},
        period={"start": str(test_idx[0].date()), "end": str(test_idx[-1].date())},
        strategy=strat,
        strategy_post_tax=strat_pt,
        nifty=nif,
        equal_weight=ewm,
        out_of_sample=oos,
        trading=trading,
        verdict={"status": status, "headline": headline, "reasons": reasons},
        equity_curve=curve,
    )
