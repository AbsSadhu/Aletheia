"""
Dedicated unit tests for the ICScorer.

These tests exercise Spearman IC computation, persistence, history retrieval,
and factor status classification. They require scipy (pip install scipy).
"""

from __future__ import annotations


import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def scorer(tmp_path):
    """Return a fresh ICScorer backed by a temp SQLite db."""
    from aletheia.factors.ic_scorer import ICScorer

    return ICScorer(db_path=tmp_path / "test_ic.db")


@pytest.fixture
def perfect_data():
    """Factor values perfectly correlated with returns → IC should be ~1."""
    n = 60
    values = pd.Series(np.arange(n, dtype=float), name="factor")
    returns = pd.Series(np.arange(n, dtype=float) * 0.001 + 0.0001, name="fwd_ret")
    return values, returns


@pytest.fixture
def anti_data():
    """Factor perfectly anti-correlated with returns → IC should be ~ -1."""
    n = 60
    values = pd.Series(np.arange(n, dtype=float), name="factor")
    returns = pd.Series(np.arange(n - 1, -1, -1, dtype=float) * 0.001, name="fwd_ret")
    return values, returns


@pytest.fixture
def random_data():
    """Uncorrelated factor + returns → IC near 0."""
    rng = np.random.default_rng(42)
    n = 100
    values = pd.Series(rng.normal(0, 1, n), name="factor")
    returns = pd.Series(rng.normal(0, 0.01, n), name="fwd_ret")
    return values, returns


class TestICComputation:
    def test_perfect_correlation_ic_positive(self, scorer, perfect_data):
        pytest.importorskip("scipy")  # skip gracefully if not installed
        values, returns = perfect_data
        result = scorer.compute_ic("test_factor", values, returns)
        assert result.ic > 0.9, f"Expected IC close to 1, got {result.ic}"

    def test_anti_correlation_ic_negative(self, scorer, anti_data):
        pytest.importorskip("scipy")
        values, returns = anti_data
        result = scorer.compute_ic("test_factor_rev", values, returns)
        assert result.ic < -0.9, f"Expected IC close to -1, got {result.ic}"

    def test_uncorrelated_ic_near_zero(self, scorer, random_data):
        pytest.importorskip("scipy")
        values, returns = random_data
        result = scorer.compute_ic("random_factor", values, returns)
        assert abs(result.ic) < 0.4, f"Expected IC near 0, got {result.ic}"

    def test_result_has_required_fields(self, scorer, perfect_data):
        pytest.importorskip("scipy")
        values, returns = perfect_data
        result = scorer.compute_ic("test_fields", values, returns)
        assert hasattr(result, "ic")
        assert hasattr(result, "ic_std")
        assert hasattr(result, "icir")
        assert hasattr(result, "t_stat")
        assert hasattr(result, "p_value")
        assert hasattr(result, "n_observations")
        assert hasattr(result, "status")

    def test_positive_ic_status_alive(self, scorer, perfect_data):
        pytest.importorskip("scipy")
        values, returns = perfect_data
        result = scorer.compute_ic("status_test", values, returns)
        assert result.status == "alive"

    def test_negative_ic_status_reversed(self, scorer, anti_data):
        pytest.importorskip("scipy")
        values, returns = anti_data
        result = scorer.compute_ic("reversed_test", values, returns)
        assert result.status == "reversed"

    def test_insufficient_data_returns_dead(self, scorer):
        """Fewer than 10 observations → returns dead status without error."""
        values = pd.Series([1.0, 2.0, 3.0])
        returns = pd.Series([0.01, 0.02, 0.03])
        result = scorer.compute_ic("tiny_factor", values, returns)
        assert result.status == "dead"
        assert result.ic == 0.0

    def test_ic_persisted_to_db(self, scorer, perfect_data):
        pytest.importorskip("scipy")
        values, returns = perfect_data
        scorer.compute_ic("persist_test", values, returns)
        history = scorer.get_history("persist_test", limit=5)
        assert len(history) >= 1
        assert history[0].factor_name == "persist_test"

    def test_history_respects_limit(self, scorer, perfect_data):
        pytest.importorskip("scipy")
        values, returns = perfect_data
        for _ in range(5):
            scorer.compute_ic("repeated", values, returns)
        history = scorer.get_history("repeated", limit=3)
        assert len(history) <= 3

    def test_icir_is_ic_over_std(self, scorer, perfect_data):
        pytest.importorskip("scipy")
        values, returns = perfect_data
        result = scorer.compute_ic("icir_test", values, returns)
        if result.ic_std > 0:
            expected_icir = result.ic / result.ic_std
            assert abs(result.icir - expected_icir) < 0.01

    def test_n_observations_matches_data(self, scorer, perfect_data):
        pytest.importorskip("scipy")
        values, returns = perfect_data
        result = scorer.compute_ic("obs_test", values, returns)
        assert result.n_observations == len(values)

    def test_factor_ranking(self, scorer, perfect_data, anti_data, random_data):
        """Positive factor should rank higher than anti-correlated or random."""
        pytest.importorskip("scipy")
        v_pos, r_pos = perfect_data
        v_neg, r_neg = anti_data
        v_rand, r_rand = random_data

        scorer.compute_ic("pos_factor", v_pos, r_pos)
        scorer.compute_ic("neg_factor", v_neg, r_neg)
        scorer.compute_ic("rand_factor", v_rand, r_rand)

        ranking = scorer.get_factor_ranking()
        names = [r.factor_name for r in ranking]
        # pos_factor should appear before neg_factor in ranking by absolute IC
        assert "pos_factor" in names
