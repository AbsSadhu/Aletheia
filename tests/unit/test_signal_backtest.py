import numpy as np
import pandas as pd
import pytest

from aletheia.extensions.backtest.signal_backtest import (
    SignalBacktestConfig,
    Trade,
    run_signal_backtest,
    tax_on_trades,
)


def _walk(n: int, seed: int, drift: float = 0.0004) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + drift + rng.normal(0, 0.012, n))
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame(
        {
            "Open": close * (1 + rng.normal(0, 0.002, n)),
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": 1e6,
        },
        index=idx,
    )


def _universe(n: int = 700):
    return {f"S{i}": _walk(n, seed=i) for i in range(4)}, _walk(n, seed=99)


CFG = SignalBacktestConfig(max_positions=3, rebalance_days=5)


def test_result_shape_and_benchmarks_present() -> None:
    data, bench = _universe()
    res = run_signal_backtest(data, bench, CFG)

    assert res.verdict["status"] in {"PASS", "FAIL", "INCONCLUSIVE"}
    for block in (res.strategy, res.strategy_post_tax, res.nifty, res.equal_weight):
        assert {"cagr_pct", "sharpe", "max_drawdown_pct"} <= set(block)
    assert res.out_of_sample["start"] > res.period["start"]
    assert res.caveats and any("Survivorship" in c for c in res.caveats)
    assert res.equity_curve[0]["strategy"] > 0


def test_decisions_never_depend_on_future_bars() -> None:
    """Rewrite every bar after day K with garbage: equity up to K must be unchanged."""
    data, bench = _universe()
    base = run_signal_backtest(data, bench, CFG)

    cut = pd.Timestamp(base.equity_curve[len(base.equity_curve) // 2]["date"])
    poisoned = {}
    for sym, df in data.items():
        p = df.copy()
        later = p.index > cut
        p.loc[later, ["Open", "High", "Low", "Close"]] = np.random.default_rng(5).uniform(
            1, 1000, (later.sum(), 4)
        )
        poisoned[sym] = p
    pb = bench.copy()
    pb.loc[pb.index > cut, ["Open", "High", "Low", "Close"]] = 123.0
    other = run_signal_backtest(poisoned, pb, CFG)

    a = {r["date"]: r["strategy"] for r in base.equity_curve if pd.Timestamp(r["date"]) <= cut}
    b = {r["date"]: r["strategy"] for r in other.equity_curve if pd.Timestamp(r["date"]) <= cut}
    assert a and a == b


def test_costs_reduce_returns() -> None:
    data, bench = _universe()
    free = run_signal_backtest(
        data,
        bench,
        SignalBacktestConfig(
            max_positions=3,
            commission_bps=0,
            spread_bps=0,
            slippage_bps=0,
            stt_bps=0,
            apply_tax=False,
        ),
    )
    costly = run_signal_backtest(
        data,
        bench,
        SignalBacktestConfig(max_positions=3, slippage_bps=50, apply_tax=False),
    )
    if free.trading["trades"] > 0:
        assert costly.trading["gross_final_equity"] < free.trading["gross_final_equity"]
        assert costly.trading["trading_costs_inr"] > free.trading["trading_costs_inr"]


def test_tax_applied_only_when_enabled() -> None:
    data, bench = _universe()
    taxed = run_signal_backtest(data, bench, CFG)
    untaxed = run_signal_backtest(
        data, bench, SignalBacktestConfig(max_positions=3, apply_tax=False)
    )
    assert untaxed.trading["tax_paid_inr"] == 0
    assert taxed.trading["tax_paid_inr"] >= 0
    assert taxed.trading["gross_final_equity"] == untaxed.trading["gross_final_equity"]


def test_too_little_history_is_an_error_not_a_guess() -> None:
    with pytest.raises(ValueError):
        run_signal_backtest({"S": _walk(100, 1)}, _walk(100, 2), CFG)


def _trade(entry: str, exit_: str, pnl: float) -> Trade:
    t = Trade("X", pd.Timestamp(entry), 100.0, 1)
    t.exit_date, t.pnl = pd.Timestamp(exit_), pnl
    return t


def test_tax_short_term_rate_and_loss_setoff() -> None:
    assert tax_on_trades([_trade("2024-05-01", "2024-08-01", 100_000)]) == pytest.approx(20_000)
    # a short-term loss in the same FY reduces the taxable gain
    both = [
        _trade("2024-05-01", "2024-08-01", 100_000),
        _trade("2024-06-01", "2024-09-01", -40_000),
    ]
    assert tax_on_trades(both) == pytest.approx(12_000)
    assert tax_on_trades([_trade("2024-05-01", "2024-08-01", -5_000)]) == 0


def test_long_term_exemption_and_rate() -> None:
    gain = 225_000  # 1.25L exempt -> 100k taxed at 12.5%
    assert tax_on_trades([_trade("2022-05-01", "2024-08-01", gain)]) == pytest.approx(12_500)
    assert tax_on_trades([_trade("2022-05-01", "2024-08-01", 100_000)]) == 0


def test_financial_years_are_taxed_separately() -> None:
    # exits in different FYs: each FY gets its own exemption
    t = [_trade("2021-05-01", "2024-02-01", 125_000), _trade("2021-05-01", "2024-05-01", 125_000)]
    assert tax_on_trades(t) == 0
