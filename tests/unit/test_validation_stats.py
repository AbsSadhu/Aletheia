"""Sharpe significance statistics (PSR, DSR, BH) and the one-call assessment."""

from __future__ import annotations

import numpy as np
import pytest

from aletheia.core.validation.stats import (
    assess,
    benjamini_hochberg,
    deflated_sharpe_ratio,
    expected_maximum_sharpe,
    max_drawdown,
    min_track_record_length,
    probabilistic_sharpe_ratio,
    sharpe_ratio,
)


def test_psr_is_one_half_when_the_sharpe_equals_the_benchmark_and_grows_with_history():
    assert probabilistic_sharpe_ratio(0.1, 500, benchmark_sharpe=0.1) == pytest.approx(0.5)
    assert probabilistic_sharpe_ratio(0.1, 1000) > probabilistic_sharpe_ratio(0.1, 100) > 0.5


def test_negative_skew_and_fat_tails_make_the_same_sharpe_less_trustworthy():
    plain = probabilistic_sharpe_ratio(0.15, 250)
    assert probabilistic_sharpe_ratio(0.15, 250, skew=-1.5) < plain
    assert probabilistic_sharpe_ratio(0.15, 250, kurtosis=9.0) < plain


def test_psr_rejects_the_conventions_that_silently_break_it():
    with pytest.raises(ValueError, match="at least 30"):
        probabilistic_sharpe_ratio(0.1, 10)
    with pytest.raises(ValueError, match="non-excess"):
        probabilistic_sharpe_ratio(0.1, 250, kurtosis=0.0)  # excess kurtosis passed by mistake


def test_expected_maximum_sharpe_matches_the_known_value_for_100_trials():
    assert expected_maximum_sharpe(100, 1.0) == pytest.approx(2.534, abs=0.01)
    assert expected_maximum_sharpe(1, 1.0) == 0.0 and expected_maximum_sharpe(50, 0.0) == 0.0


def test_deflating_for_more_trials_lowers_confidence():
    psr = probabilistic_sharpe_ratio(0.2, 750)
    few, bar_few = deflated_sharpe_ratio(0.2, 10, 750, 0.05)
    many, bar_many = deflated_sharpe_ratio(0.2, 10_000, 750, 0.05)
    assert psr > few > many and bar_many > bar_few > 0


def test_minimum_track_record_is_shorter_for_a_higher_sharpe():
    assert min_track_record_length(0.2) < min_track_record_length(0.1)
    assert min_track_record_length(-0.1) is None


def test_benjamini_hochberg_known_case():
    r = benjamini_hochberg([0.01, 0.02, 0.03, 0.5], fdr=0.05)
    assert r.rejected.tolist() == [True, True, True, False] and r.n_rejected == 3
    assert r.adjusted_p_values.tolist() == pytest.approx([0.04, 0.04, 0.04, 0.5])


def test_benjamini_hochberg_keeps_the_callers_order_and_validates_input():
    r = benjamini_hochberg([0.5, 0.01, 0.03, 0.02], fdr=0.05)
    assert r.rejected.tolist() == [False, True, True, True]
    with pytest.raises(ValueError):
        benjamini_hochberg([0.2, 1.5])
    with pytest.raises(ValueError):
        benjamini_hochberg([])


def test_sharpe_and_drawdown_basics():
    assert sharpe_ratio([0.01, 0.01, 0.01]) != sharpe_ratio(
        [0.01, 0.02, 0.0]
    )  # no dispersion is NaN, not inf
    assert np.isnan(sharpe_ratio([0.01, 0.01, 0.01]))
    assert max_drawdown(np.array([0.1, -0.2, 0.05])) == pytest.approx(-0.2)


def _noise(seed=1, n=250, drift=0.0):
    return np.random.default_rng(seed).normal(drift, 0.01, n)


def test_assess_calls_pure_noise_indistinguishable_from_luck():
    r = assess(_noise(), kind="returns")
    assert r["verdict"] in {"indistinguishable", "suggestive"} and r["verdict"] != "likely_real"
    assert r["observations"] == 250 and r["psr"] is not None


def test_assess_recognises_a_strong_edge_and_deflation_weakens_it():
    returns = _noise(seed=3, n=750, drift=0.002)
    alone = assess(returns, kind="returns")
    searched = assess(returns, kind="returns", n_trials=100_000)
    assert alone["verdict"] == "likely_real"
    assert (
        searched["dsr"] < alone["psr"]
        and searched["bar_annualized"] > 0
        and searched["trial_std_assumed"] is True
    )


def test_assess_accepts_an_equity_curve_and_reports_risk_stats():
    equity = 100_000 * np.cumprod(1 + _noise(seed=5, n=300, drift=0.001))
    r = assess(equity, kind="equity")
    assert (
        r["max_drawdown"] < 0
        and r["sortino_annualized"] is not None
        and r["annualized_return"] is not None
    )
    assert r["calmar"] is not None


def test_assess_refuses_too_little_data_and_flat_curves():
    with pytest.raises(ValueError, match="at least 30"):
        assess(_noise(n=20), kind="returns")
    with pytest.raises(ValueError, match="no variation"):
        assess([0.001] * 60, kind="returns")
    with pytest.raises(ValueError, match="positive"):
        assess([100, 90, 0, 80], kind="equity")


def test_validation_api():
    from fastapi.testclient import TestClient

    from aletheia.core.main import create_app

    client = TestClient(create_app())
    ok = client.post(
        "/api/v1/validation/sharpe",
        json={
            "values": list(_noise(seed=3, n=400, drift=0.002)),
            "kind": "returns",
            "n_trials": 20,
        },
    )
    assert ok.status_code == 200 and ok.json()["n_trials"] == 20 and "verdict_text" in ok.json()
    short = client.post(
        "/api/v1/validation/sharpe", json={"values": [0.01] * 10, "kind": "returns"}
    )
    assert short.status_code == 422 and "at least 30" in short.json()["message"]
    fdr = client.post("/api/v1/validation/fdr", json={"p_values": [0.01, 0.02, 0.03, 0.5]})
    assert fdr.status_code == 200 and fdr.json()["n_rejected"] == 3
