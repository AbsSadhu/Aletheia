from __future__ import annotations

import pytest

from aletheia.extensions.backtest.execution_costs import ExecutionCosts


class TestPresets:
    @pytest.mark.parametrize(
        "asset_class",
        ["equity_nse", "equity_bse", "fno", "crypto", "us_equity"],
    )
    def test_known_asset_classes_return_matching_preset(self, asset_class: str) -> None:
        costs = ExecutionCosts.for_asset_class(asset_class)
        assert costs.asset_class == asset_class

    def test_unknown_asset_class_falls_back_to_equity_nse(self) -> None:
        costs = ExecutionCosts.for_asset_class("does_not_exist")
        assert costs.asset_class == "equity_nse"

    def test_crypto_has_highest_costs(self) -> None:
        # Crypto should be the most expensive preset — sanity check the data,
        # not just that presets exist.
        crypto = ExecutionCosts.for_asset_class("crypto")
        nse = ExecutionCosts.for_asset_class("equity_nse")
        us = ExecutionCosts.for_asset_class("us_equity")
        assert crypto.total_round_trip_cost_bps() > nse.total_round_trip_cost_bps()
        assert crypto.total_round_trip_cost_bps() > us.total_round_trip_cost_bps()


class TestFillMath:
    def test_buy_fill_is_worse_than_close(self) -> None:
        costs = ExecutionCosts(slippage_bps=10, bid_ask_spread_bps=5, commission_bps=5)
        fill = costs.apply_to_buy(100.0)
        assert fill > 100.0
        assert fill == pytest.approx(100.0 * 1.0020)

    def test_sell_fill_is_worse_than_close(self) -> None:
        costs = ExecutionCosts(slippage_bps=10, bid_ask_spread_bps=5, commission_bps=5)
        fill = costs.apply_to_sell(100.0)
        assert fill < 100.0
        assert fill == pytest.approx(100.0 * 0.9980)

    def test_zero_cost_model_leaves_price_unchanged(self) -> None:
        costs = ExecutionCosts(slippage_bps=0, bid_ask_spread_bps=0, commission_bps=0)
        assert costs.apply_to_buy(100.0) == pytest.approx(100.0)
        assert costs.apply_to_sell(100.0) == pytest.approx(100.0)

    def test_round_trip_cost_is_double_one_way(self) -> None:
        costs = ExecutionCosts(slippage_bps=3, bid_ask_spread_bps=1, commission_bps=2)
        assert costs.total_round_trip_cost_bps() == pytest.approx(12.0)

    def test_negative_inputs_rejected(self) -> None:
        with pytest.raises(Exception):
            ExecutionCosts(slippage_bps=-1.0)


class TestLatencyBarsDelay:
    def test_sub_bar_latency_means_zero_delay(self) -> None:
        costs = ExecutionCosts(latency_ms=50.0)
        assert costs.latency_bars_delay(bar_duration_seconds=86400.0) == 0

    def test_latency_longer_than_bar_adds_delay(self) -> None:
        # 2 days of latency on 1-day bars -> should delay at least 2 bars.
        costs = ExecutionCosts(latency_ms=2 * 86400 * 1000.0)
        assert costs.latency_bars_delay(bar_duration_seconds=86400.0) == 2
