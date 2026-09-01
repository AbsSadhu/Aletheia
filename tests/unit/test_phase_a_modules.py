"""
Unit tests for Phase A modules:
  - Alpha factor computation (momentum, mean reversion, volume, technicals)
  - Factor registry composite signal
  - Portfolio Manager constraint checker
  - Risk metrics computation
  - Position sizing (Kelly, fractional)
  - Working memory storage
"""
from __future__ import annotations

import math
import pandas as pd
import numpy as np
import pytest
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ohlcv_df():
    """100-bar synthetic OHLCV DataFrame."""
    rng = np.random.default_rng(42)
    n = 100
    closes = 100 + np.cumsum(rng.normal(0, 1, n))
    opens = closes * (1 + rng.normal(0, 0.002, n))
    highs = np.maximum(opens, closes) * (1 + rng.uniform(0, 0.01, n))
    lows = np.minimum(opens, closes) * (1 - rng.uniform(0, 0.01, n))
    volumes = rng.integers(100_000, 1_000_000, n).astype(float)
    dates = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(n)]
    return pd.DataFrame(
        {"date": dates, "open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes}
    )


# ---------------------------------------------------------------------------
# Factor tests
# ---------------------------------------------------------------------------

class TestMomentumFactors:
    def test_rsi_returns_valid_signal(self, ohlcv_df):
        from aletheia.factors.momentum import RSIFactor
        f = RSIFactor()
        out = f.compute(ohlcv_df)
        assert out.signal in ("BUY", "HOLD", "SELL")
        assert 0.0 <= out.confidence <= 1.0
        assert not math.isnan(out.value)

    def test_macd_returns_valid_signal(self, ohlcv_df):
        from aletheia.factors.momentum import MACDFactor
        f = MACDFactor()
        out = f.compute(ohlcv_df)
        assert out.signal in ("BUY", "HOLD", "SELL")
        assert 0.0 <= out.confidence <= 1.0

    def test_momentum_score(self, ohlcv_df):
        from aletheia.factors.momentum import MomentumScoreFactor
        f = MomentumScoreFactor()
        out = f.compute(ohlcv_df)
        assert out.signal in ("BUY", "HOLD", "SELL")


class TestMeanReversionFactors:
    def test_bollinger_valid_signal(self, ohlcv_df):
        from aletheia.factors.mean_reversion import BollingerBandFactor
        f = BollingerBandFactor()
        out = f.compute(ohlcv_df)
        assert out.signal in ("BUY", "HOLD", "SELL")

    def test_zscore_valid(self, ohlcv_df):
        from aletheia.factors.mean_reversion import ZScoreFactor
        f = ZScoreFactor()
        out = f.compute(ohlcv_df)
        assert out.signal in ("BUY", "HOLD", "SELL")


class TestVolumeFactors:
    def test_vwap_factor(self, ohlcv_df):
        from aletheia.factors.volume import VWAPDeviationFactor
        f = VWAPDeviationFactor()
        out = f.compute(ohlcv_df)
        assert out.signal in ("BUY", "HOLD", "SELL")

    def test_obv_factor(self, ohlcv_df):
        from aletheia.factors.volume import OBVTrendFactor
        f = OBVTrendFactor()
        out = f.compute(ohlcv_df)
        assert out.signal in ("BUY", "HOLD", "SELL")


class TestTechnicalFactors:
    def test_ma_crossover(self, ohlcv_df):
        from aletheia.factors.technicals import MACrossFactor
        f = MACrossFactor()
        out = f.compute(ohlcv_df)
        assert out.signal in ("BUY", "HOLD", "SELL")


class TestFactorRegistry:
    def test_compute_all_returns_all_factors(self, ohlcv_df):
        from aletheia.factors.registry import get_registry
        reg = get_registry()
        results = reg.compute_all(ohlcv_df)
        assert len(results) >= 5, f"Expected ≥5 factors, got {len(results)}"
        for name, out in results.items():
            assert out.signal in ("BUY", "HOLD", "SELL"), f"{name} returned invalid signal"

    def test_composite_signal(self, ohlcv_df):
        from aletheia.factors.registry import get_registry
        reg = get_registry()
        results = reg.compute_all(ohlcv_df)
        composite = reg.composite_signal(results)
        assert composite["signal"] in ("BUY", "HOLD", "SELL")
        assert 0.0 <= composite["confidence"] <= 1.0
        assert -1.0 <= composite["composite_score"] <= 1.0

    def test_registry_is_singleton(self):
        from aletheia.factors.registry import get_registry
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2


# ---------------------------------------------------------------------------
# Portfolio Manager Constraint Checker tests
# ---------------------------------------------------------------------------

class TestPortfolioConstraints:
    def _make_checker(self, **kwargs):
        from aletheia.core.execution.portfolio_constraints import (
            PortfolioConstraints,
            PortfolioManagerConstraintChecker,
        )
        return PortfolioManagerConstraintChecker(PortfolioConstraints(**kwargs))

    def test_normal_buy_executes(self):
        checker = self._make_checker(max_position_size_pct=20.0, min_cash_reserve_pct=5.0)
        decision = checker.check(
            symbol="RELIANCE",
            action="BUY",
            quantity=10,
            price=2500.0,
            portfolio_value=500_000,
            current_position_value=0,
            current_cash=100_000,
        )
        assert decision.decision == "EXECUTE"
        assert not decision.violations

    def test_oversized_position_skips(self):
        checker = self._make_checker(max_position_size_pct=5.0, min_cash_reserve_pct=0.0)
        decision = checker.check(
            symbol="RELIANCE",
            action="BUY",
            quantity=100,
            price=2500.0,             # ₹2,50,000 = 50% of ₹5,00,000
            portfolio_value=500_000,
            current_position_value=0,
            current_cash=500_000,
        )
        assert decision.decision in ("SKIP", "REDUCE")

    def test_hold_always_executes(self):
        checker = self._make_checker()
        decision = checker.check(
            symbol="INFY", action="HOLD", quantity=0, price=1500, portfolio_value=100_000,
        )
        assert decision.decision == "EXECUTE"

    def test_insufficient_cash_blocks_buy(self):
        checker = self._make_checker(min_cash_reserve_pct=50.0)
        decision = checker.check(
            symbol="TCS",
            action="BUY",
            quantity=5,
            price=3500.0,               # ₹17,500 buy
            portfolio_value=100_000,
            current_cash=20_000,         # after buy: ₹2,500 < 50% min ₹50,000
        )
        assert decision.decision in ("SKIP", "REDUCE")
        assert len(decision.violations) > 0

    def test_sell_bypasses_cash_check(self):
        checker = self._make_checker(min_cash_reserve_pct=99.0)
        decision = checker.check(
            symbol="HDFCBANK",
            action="SELL",
            quantity=5,
            price=1650.0,
            portfolio_value=50_000,
            current_cash=0,
        )
        # SELL doesn't consume cash — should pass other checks
        # may still fail on position-size; just verify it's not blocked by cash
        assert "cash" not in " ".join(decision.violations).lower()

    def test_bulk_check_reduces_cash_greedy(self):
        from aletheia.core.execution.portfolio_constraints import (
            PortfolioConstraints,
            PortfolioManagerConstraintChecker,
        )
        checker = PortfolioManagerConstraintChecker(
            PortfolioConstraints(max_position_size_pct=30.0, min_cash_reserve_pct=5.0)
        )
        candidates = [
            {"symbol": "A", "action": "BUY", "quantity": 10, "price": 1000.0,
             "current_position_value": 0, "sector": "tech", "sector_exposure": 0.0,
             "portfolio_var_95": 0.02, "current_leverage": 1.0},
            {"symbol": "B", "action": "BUY", "quantity": 10, "price": 1000.0,
             "current_position_value": 0, "sector": "tech", "sector_exposure": 0.0,
             "portfolio_var_95": 0.02, "current_leverage": 1.0},
        ]
        results = checker.bulk_check(candidates, portfolio_value=100_000, current_cash=50_000)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Risk Metrics tests
# ---------------------------------------------------------------------------

class TestRiskMetrics:
    def _sample_returns(self, n=252, seed=42):
        rng = np.random.default_rng(seed)
        return pd.Series(rng.normal(0.0005, 0.015, n))

    def test_sharpe_computed(self):
        from aletheia.core.risk.metrics import compute_full_risk_metrics
        returns = self._sample_returns()
        metrics = compute_full_risk_metrics(returns)
        assert hasattr(metrics, "sharpe")
        assert not math.isnan(metrics.sharpe)

    def test_sortino_computed(self):
        from aletheia.core.risk.metrics import compute_full_risk_metrics
        returns = self._sample_returns()
        metrics = compute_full_risk_metrics(returns)
        assert hasattr(metrics, "sortino")
        assert not math.isnan(metrics.sortino)

    def test_max_drawdown_non_negative(self):
        from aletheia.core.risk.metrics import compute_full_risk_metrics
        returns = self._sample_returns()
        metrics = compute_full_risk_metrics(returns)
        # max_drawdown is expressed as positive magnitude (0 = no drawdown)
        assert metrics.max_drawdown >= 0.0

    def test_var_non_negative(self):
        from aletheia.core.risk.metrics import compute_full_risk_metrics
        returns = self._sample_returns()
        metrics = compute_full_risk_metrics(returns)
        # var_95 is the loss expressed as positive (loss at 5th percentile)
        assert metrics.var_95 >= 0.0

    def test_comment_populated(self):
        from aletheia.core.risk.metrics import compute_full_risk_metrics
        returns = self._sample_returns()
        metrics = compute_full_risk_metrics(returns)
        assert isinstance(metrics.comment, str)
        assert len(metrics.comment) > 0


# ---------------------------------------------------------------------------
# Position Sizing tests
# ---------------------------------------------------------------------------

class TestPositionSizing:
    def test_fixed_fractional(self):
        from aletheia.core.execution.position_sizing import PositionSizer
        result = PositionSizer.fixed_fractional(portfolio_value=100_000, pct=2.0)
        assert abs(result - 2_000) < 1.0

    def test_half_kelly_positive_edge(self):
        from aletheia.core.execution.position_sizing import PositionSizer
        result = PositionSizer.half_kelly(
            win_rate=0.6,
            avg_win=1500,
            avg_loss=1000,
            portfolio_value=100_000,
        )
        assert result > 0

    def test_half_kelly_negative_edge_zero(self):
        from aletheia.core.execution.position_sizing import PositionSizer
        result = PositionSizer.half_kelly(
            win_rate=0.3,
            avg_win=100,
            avg_loss=1000,
            portfolio_value=100_000,
        )
        assert result == 0.0  # negative Kelly → zero position

    def test_position_in_shares(self):
        from aletheia.core.execution.position_sizing import PositionSizer
        shares = PositionSizer.compute_shares(
            capital=10_000, price=500.0, pct=5.0, portfolio_value=200_000
        )
        assert isinstance(shares, int)
        assert shares >= 0


# ---------------------------------------------------------------------------
# Working Memory tests
# ---------------------------------------------------------------------------

class TestWorkingMemory:
    @pytest.fixture
    def wm(self, tmp_path):
        from aletheia.memory.working_memory import WorkingMemory
        return WorkingMemory(db_path=str(tmp_path / "wm_test.db"))

    def test_store_and_retrieve(self, wm):
        wm.store_observation(
            agent_name="oracle",
            ticker="RELIANCE",
            observation="Strong momentum breakout above 50-day MA",
            confidence=0.85,
        )
        obs = wm.list_all_observations("oracle", ticker="RELIANCE", limit=10)
        assert len(obs) >= 1
        assert obs[0]["ticker"] == "RELIANCE"
        assert abs(obs[0]["confidence"] - 0.85) < 0.01

    def test_store_and_retrieve_critique(self, wm):
        wm.store_critique("sentinel", "Consistently underestimated volatility in small-caps.")
        critique = wm.get_latest_critique("sentinel")
        assert critique is not None
        assert "small-caps" in critique

    def test_no_observations_returns_empty(self, wm):
        obs = wm.list_all_observations("sage", limit=5)
        assert obs == []

    def test_multiple_agents_separated(self, wm):
        wm.store_observation("oracle", "TCS", "BUY signal", 0.7)
        wm.store_observation("sentinel", "TCS", "Risk warning", 0.4)
        oracle_obs = wm.list_all_observations("oracle", limit=10)
        sentinel_obs = wm.list_all_observations("sentinel", limit=10)
        assert all(o["agent_name"] == "oracle" for o in oracle_obs)
        assert all(o["agent_name"] == "sentinel" for o in sentinel_obs)
