"""Backtests must charge costs, refuse to run on missing data, and say what they could not see."""

from __future__ import annotations

import pytest

from aletheia.core.api.routers.backtest import coverage_warnings, pick_costs, split_missing
from aletheia.extensions.backtest.data_feed import OHLCV, is_bare_symbol
from aletheia.extensions.backtest.execution_costs import ExecutionCosts
from aletheia.extensions.backtest.metrics import split_segments
from aletheia.extensions.backtest.runner import BacktestRunner


def _round_trip(runner: BacktestRunner, buy: float, sell: float, qty: float = 100) -> None:
    runner.submit_order("AAA", "market", "buy", qty, price=buy)
    runner.execute_orders({"AAA": {"close": buy}})
    runner.update_equity({"AAA": {"close": buy}})
    runner.submit_order("AAA", "market", "sell", qty, price=sell)
    runner.execute_orders({"AAA": {"close": sell}})
    runner.update_equity({"AAA": {"close": sell}})


class TestCostsAreCharged:
    def test_flat_round_trip_without_costs_loses_nothing(self) -> None:
        runner = BacktestRunner(initial_capital=100_000.0)
        _round_trip(runner, 100.0, 100.0)
        assert runner.current_capital == pytest.approx(100_000.0)
        assert runner.total_costs_paid == 0.0

    def test_flat_round_trip_with_costs_loses_the_round_trip_cost(self) -> None:
        costs = ExecutionCosts.for_asset_class("equity_nse")
        runner = BacktestRunner(initial_capital=100_000.0, costs=costs)
        _round_trip(runner, 100.0, 100.0)
        expected_loss = 100 * 100.0 * costs.total_round_trip_cost_bps() / 10_000
        assert 100_000.0 - runner.current_capital == pytest.approx(expected_loss, rel=1e-3)
        assert runner.total_costs_paid == pytest.approx(expected_loss, rel=1e-3)
        assert runner.trades_pnl[0] < 0  # a flat trade is a loser once costs count

    def test_report_names_the_cost_model(self) -> None:
        runner = BacktestRunner(costs=ExecutionCosts.for_asset_class("crypto"))
        assert runner.generate_report("s", "2024-01-01", "2024-02-01").cost_model == "crypto"
        assert BacktestRunner().generate_report("s", "a", "b").cost_model is None

    def test_nse_delivery_round_trip_includes_statutory_charges(self) -> None:
        nse = ExecutionCosts.for_asset_class("equity_nse")
        assert nse.statutory_buy_bps > 0 and nse.statutory_sell_bps > 0
        assert ExecutionCosts.for_asset_class("crypto").statutory_buy_bps == 0


class TestRejectedOrders:
    def test_unaffordable_buy_is_rejected_not_filled(self) -> None:
        runner = BacktestRunner(initial_capital=1_000.0)
        order = runner.submit_order("AAA", "market", "buy", 100, price=100.0)
        runner.execute_orders({"AAA": {"close": 100.0}})
        assert order.status == "rejected"
        assert order.filled_price is None
        assert runner.positions == {}

    def test_sell_without_a_position_is_rejected(self) -> None:
        runner = BacktestRunner()
        order = runner.submit_order("AAA", "market", "sell", 5, price=10.0)
        runner.execute_orders({"AAA": {"close": 10.0}})
        assert order.status == "rejected"


class TestCostPicking:
    @pytest.mark.parametrize(
        ("symbols", "expected"),
        [
            (["RELIANCE.NS"], "equity_nse"),
            (["RELIANCE"], "equity_nse"),
            (["TCS.BO"], "equity_bse"),
            (["BTC-USD"], "crypto"),
            (["BTC/USDT"], "crypto"),
        ],
    )
    def test_auto_picks_by_symbol(self, symbols: list[str], expected: str) -> None:
        costs = pick_costs("auto", symbols)
        assert costs is not None and costs.asset_class == expected

    def test_none_means_no_costs(self) -> None:
        assert pick_costs("none", ["RELIANCE.NS"]) is None

    def test_explicit_class_is_honoured(self) -> None:
        costs = pick_costs("fno", ["RELIANCE.NS"])
        assert costs is not None and costs.asset_class == "fno"


class TestBareSymbols:
    @pytest.mark.parametrize("sym", ["RELIANCE", "TCS", "M&M"])
    def test_plain_tickers_are_bare(self, sym: str) -> None:
        assert is_bare_symbol(sym)

    @pytest.mark.parametrize(
        "sym", ["RELIANCE.NS", "BTC-USD", "BTC/USDT", "^NSEI", "LOCAL:ABC", "INR=X"]
    )
    def test_qualified_symbols_are_not(self, sym: str) -> None:
        assert not is_bare_symbol(sym)


def _candles(sym: str, first: str, last: str) -> list[OHLCV]:
    return [OHLCV(sym, d, 1, 1, 1, 1, 1) for d in (first, last)]


class TestCoverageWarnings:
    def test_full_coverage_is_silent(self) -> None:
        data = {"AAA": _candles("AAA", "2024-01-02", "2024-06-28")}
        assert coverage_warnings(["AAA"], data, "2024-01-01", "2024-06-30") == []

    def test_late_start_and_early_end_are_reported(self) -> None:
        data = {"AAA": _candles("AAA", "2024-03-01", "2024-05-01")}
        notes = coverage_warnings(["AAA"], data, "2024-01-01", "2024-06-30")
        assert len(notes) == 2
        assert "2024-03-01" in notes[0] and "2024-05-01" in notes[1]

    def test_bad_dates_do_not_raise(self) -> None:
        data = {"AAA": _candles("AAA", "2024-01-02", "2024-06-28")}
        assert coverage_warnings(["AAA"], data, "not-a-date", "2024-06-30") == []


class TestSegments:
    def test_short_curves_get_no_split(self) -> None:
        assert split_segments([100.0] * 10) == []

    def test_a_strategy_that_only_worked_early_shows_it(self) -> None:
        up = [100.0 + i for i in range(60)]
        down = [up[-1] - i * 0.5 for i in range(1, 41)]
        segs = split_segments(up + down)
        assert [s["label"] for s in segs] == ["earlier", "later"]
        assert segs[0]["total_return"] > 0 > segs[1]["total_return"]
        assert segs[0]["bars"] + segs[1]["bars"] == len(up + down) - 1


class TestJsonSafety:
    def test_all_winning_trades_serialise(self) -> None:
        import json

        runner = BacktestRunner()
        runner.trades_pnl = [5.0, 3.0]
        data = runner.generate_report("s", "a", "b").model_dump(mode="json")
        assert data["metrics"]["profit_factor"] is None
        json.dumps(data, allow_nan=False)


class TestSplitMissing:
    def test_symbols_without_prices_are_dropped_not_fatal(self) -> None:
        data = {
            "AAA.NS": _candles("AAA.NS", "2024-01-02", "2024-06-28"),
            "GONE.NS": [],
            "ONEBAR.NS": _candles("ONEBAR.NS", "2024-01-02", "2024-01-02")[:1],
        }
        usable, missing = split_missing(data)
        assert list(usable) == ["AAA.NS"]
        assert missing == ["GONE.NS", "ONEBAR.NS"]

    def test_all_missing_leaves_nothing_usable(self) -> None:
        usable, missing = split_missing({"GONE.NS": []})
        assert usable == {} and missing == ["GONE.NS"]
