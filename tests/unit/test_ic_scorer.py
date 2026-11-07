"""
Dedicated unit tests for the ICScorer.

These tests exercise Spearman IC computation, persistence, history retrieval,
and factor status classification. scipy is a declared dependency of the project.
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
        values, returns = perfect_data
        result = scorer.compute_ic("test_factor", values, returns)
        assert result.ic > 0.9, f"Expected IC close to 1, got {result.ic}"

    def test_anti_correlation_ic_negative(self, scorer, anti_data):
        values, returns = anti_data
        result = scorer.compute_ic("test_factor_rev", values, returns)
        assert result.ic < -0.9, f"Expected IC close to -1, got {result.ic}"

    def test_uncorrelated_ic_near_zero(self, scorer, random_data):
        values, returns = random_data
        result = scorer.compute_ic("random_factor", values, returns)
        assert abs(result.ic) < 0.2, f"Expected IC near 0, got {result.ic}"
        assert result.p_value > 0.05  # indistinguishable from noise

    def test_result_reports_the_sample_and_a_valid_p_value(self, scorer, perfect_data):
        values, returns = perfect_data
        result = scorer.compute_ic("test_fields", values, returns)
        assert result.n_observations == 60
        assert 0.0 <= result.p_value <= 1.0
        assert result.p_value < 0.01  # a perfect rank correlation over 60 points is not luck
        assert result.ic_std >= 0.0

    def test_positive_ic_status_alive(self, scorer, perfect_data):
        values, returns = perfect_data
        result = scorer.compute_ic("status_test", values, returns)
        assert result.status == "alive"

    def test_negative_ic_status_reversed(self, scorer, anti_data):
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
        values, returns = perfect_data
        stored = scorer.compute_ic("persist_test", values, returns)
        history = scorer.get_history("persist_test", limit=5)
        assert len(history) == 1
        assert history[0].factor_name == "persist_test"
        assert history[0].ic == pytest.approx(stored.ic)

    def test_history_respects_limit(self, scorer, perfect_data):
        values, returns = perfect_data
        for _ in range(5):
            scorer.compute_ic("repeated", values, returns)
        history = scorer.get_history("repeated", limit=3)
        assert len(history) == 3

    def test_icir_has_the_sign_of_the_ic_when_the_ic_varies(self, scorer):
        # Perfect rank correlation has zero IC spread, so ICIR is undefined there; add noise.
        rng = np.random.default_rng(7)
        n = 100
        signal = np.arange(n, dtype=float)
        values = pd.Series(signal + rng.normal(0, 20, n))
        up = pd.Series(signal * 0.001 + rng.normal(0, 0.03, n))
        down = pd.Series(-signal * 0.001 + rng.normal(0, 0.03, n))

        pos = scorer.compute_ic("icir_pos", values, up)
        neg = scorer.compute_ic("icir_neg", values, down)

        assert pos.ic_std > 0 and neg.ic_std > 0
        assert pos.icir > 0 > neg.icir

    def test_n_observations_matches_data(self, scorer, perfect_data):
        values, returns = perfect_data
        result = scorer.compute_ic("obs_test", values, returns)
        assert result.n_observations == len(values)

    def test_factor_ranking(self, scorer, perfect_data, anti_data, random_data):
        """Positive factor should rank higher than anti-correlated or random."""
        v_pos, r_pos = perfect_data
        v_neg, r_neg = anti_data
        v_rand, r_rand = random_data

        scorer.compute_ic("pos_factor", v_pos, r_pos)
        scorer.compute_ic("neg_factor", v_neg, r_neg)
        scorer.compute_ic("rand_factor", v_rand, r_rand)

        ranking = scorer.get_factor_ranking()
        names = [r.factor_name for r in ranking]
        # Ranked by absolute IC: the two near-perfect factors come before pure noise.
        assert set(names[:2]) == {"pos_factor", "neg_factor"}
        assert names[-1] == "rand_factor"
