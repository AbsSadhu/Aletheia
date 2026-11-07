"""Sharpe significance: the probabilistic and deflated Sharpe ratios, plus basic risk-adjusted stats.

Ported from Vibe-Trading's quantlib.multipletesting (MIT; see THIRD_PARTY_NOTICES.md):
``sharpe_ratio``, ``probabilistic_sharpe_ratio``, ``expected_maximum_sharpe``,
``deflated_sharpe_ratio`` and ``benjamini_hochberg`` keep that module's formulas and its two
conventions, which silently break the maths if ignored:

* Sharpe is **per observation**, never annualised, because every formula pairs it with the number
  of observations T. Annualising first inflates the statistic by about sqrt(252).
* Kurtosis is **non-excess** (3 for a normal distribution). scipy and pandas return the excess
  form by default.

Added here: Sortino, Calmar, drawdown, minimum track-record length, and ``assess`` which turns an
equity curve into one plain-language verdict.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats as sps
from scipy.stats import norm

EULER_MASCHERONI = 0.5772156649015329
GAUSSIAN_KURTOSIS = 3.0
#: Fewest observations for which skew and kurtosis estimates mean anything.
MIN_OBSERVATIONS = 30


@dataclass(frozen=True)
class FDRResult:
    rejected: np.ndarray
    adjusted_p_values: np.ndarray
    n_rejected: int
    threshold: float
    fdr: float


def sharpe_ratio(
    returns: Sequence[float] | np.ndarray, risk_free: float = 0.0, ddof: int = 1
) -> float:
    """Per-observation Sharpe ratio. NaN when the returns have no dispersion."""
    values = np.asarray(returns, dtype=float).ravel()
    values = values[np.isfinite(values)]
    if values.size < 2:
        raise ValueError(f"sharpe_ratio needs at least 2 observations, got {values.size}")
    excess = values - risk_free
    spread = float(excess.std(ddof=ddof))
    if not np.isfinite(spread) or spread <= 0.0:
        return float("nan")
    return float(excess.mean() / spread)


def probabilistic_sharpe_ratio(
    observed_sharpe: float,
    n_observations: int,
    benchmark_sharpe: float = 0.0,
    skew: float = 0.0,
    kurtosis: float = GAUSSIAN_KURTOSIS,
) -> float:
    """Confidence that the true Sharpe exceeds a benchmark, allowing for skew and fat tails."""
    if n_observations < MIN_OBSERVATIONS:
        raise ValueError(f"need at least {MIN_OBSERVATIONS} observations, got {n_observations}")
    if kurtosis < 1.0:
        raise ValueError(
            f"kurtosis must be the non-excess fourth moment (>= 1; 3 for a normal), got {kurtosis}"
        )
    if not np.isfinite(observed_sharpe):
        raise ValueError("observed_sharpe must be finite")
    variance_term = 1.0 - skew * observed_sharpe + (kurtosis - 1.0) / 4.0 * observed_sharpe**2
    if variance_term <= 0.0:
        raise ValueError("the supplied skew and kurtosis are inconsistent with this Sharpe")
    statistic = (
        (observed_sharpe - benchmark_sharpe)
        * math.sqrt(n_observations - 1)
        / math.sqrt(variance_term)
    )
    return float(norm.cdf(statistic))


def expected_maximum_sharpe(n_trials: int, trial_sharpe_std: float) -> float:
    """The Sharpe the best of ``n_trials`` reaches by luck alone: the bar a real edge must clear."""
    if n_trials < 1:
        raise ValueError(f"n_trials must be at least 1, got {n_trials}")
    if trial_sharpe_std < 0.0:
        raise ValueError(f"trial_sharpe_std must be >= 0, got {trial_sharpe_std}")
    if n_trials == 1 or trial_sharpe_std == 0.0:
        return 0.0
    a = norm.ppf(1.0 - 1.0 / n_trials)
    b = norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(trial_sharpe_std * ((1.0 - EULER_MASCHERONI) * a + EULER_MASCHERONI * b))


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_trials: int,
    n_observations: int,
    trial_sharpe_std: float,
    skew: float = 0.0,
    kurtosis: float = GAUSSIAN_KURTOSIS,
) -> tuple[float, float]:
    """(deflated Sharpe, the bar it was measured against): PSR with the benchmark raised to best-of-N."""
    bar = expected_maximum_sharpe(n_trials, trial_sharpe_std)
    return probabilistic_sharpe_ratio(observed_sharpe, n_observations, bar, skew, kurtosis), bar


def min_track_record_length(
    observed_sharpe: float,
    benchmark_sharpe: float = 0.0,
    skew: float = 0.0,
    kurtosis: float = GAUSSIAN_KURTOSIS,
    confidence: float = 0.95,
) -> float | None:
    """Observations needed before the observed Sharpe beats the benchmark at the given confidence."""
    if observed_sharpe <= benchmark_sharpe:
        return None
    variance_term = 1.0 - skew * observed_sharpe + (kurtosis - 1.0) / 4.0 * observed_sharpe**2
    if variance_term <= 0.0:
        return None
    z = norm.ppf(confidence)
    return float(1.0 + variance_term * (z / (observed_sharpe - benchmark_sharpe)) ** 2)


def benjamini_hochberg(p_values: Sequence[float] | np.ndarray, fdr: float = 0.05) -> FDRResult:
    """Control the false discovery rate across many simultaneous tests."""
    if not 0.0 < fdr < 1.0:
        raise ValueError(f"fdr must be in (0, 1), got {fdr}")
    values = np.asarray(p_values, dtype=float).ravel()
    if values.size == 0:
        raise ValueError("p_values is empty")
    if not np.isfinite(values).all() or ((values < 0.0) | (values > 1.0)).any():
        raise ValueError("every p-value must be a number in [0, 1]")
    n = values.size
    order = np.argsort(values, kind="stable")
    sorted_p = values[order]
    ranks = np.arange(1, n + 1)
    below = sorted_p <= (ranks / n) * fdr
    cutoff = int(ranks[below].max()) if below.any() else 0
    threshold = float(sorted_p[cutoff - 1]) if cutoff else 0.0
    adjusted_sorted = np.clip(np.minimum.accumulate((n / ranks * sorted_p)[::-1])[::-1], 0.0, 1.0)
    rejected, adjusted = np.empty(n, dtype=bool), np.empty(n, dtype=float)
    rejected[order] = ranks <= cutoff
    adjusted[order] = adjusted_sorted
    return FDRResult(rejected, adjusted, int(rejected.sum()), threshold, fdr)


def returns_from_equity(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2 or (arr <= 0).any():
        raise ValueError("an equity curve needs at least two positive values")
    returns: np.ndarray = arr[1:] / arr[:-1] - 1.0
    return returns


def max_drawdown(returns: np.ndarray) -> float:
    equity = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(np.concatenate([[1.0], equity]))[1:]
    return float(((equity - peak) / peak).min())


def sortino_ratio(returns: np.ndarray, target: float = 0.0) -> float | None:
    downside = np.minimum(returns - target, 0.0)
    dd = float(np.sqrt(np.mean(downside**2)))
    return float((returns.mean() - target) / dd) if dd > 0 else None


def _finite(x: float | None, digits: int = 4) -> float | None:
    return None if x is None or not np.isfinite(x) else round(float(x), digits)


def assess(
    values: Sequence[float],
    kind: str = "equity",
    n_trials: int = 1,
    trial_sharpe_std: float | None = None,
    periods_per_year: int = 252,
    confidence: float = 0.95,
) -> dict:
    """One equity curve (or return series) in, one plain-language reading of how real its Sharpe is out."""
    returns = returns_from_equity(values) if kind == "equity" else np.asarray(values, dtype=float)
    returns = returns[np.isfinite(returns)]
    t = int(returns.size)
    if t < MIN_OBSERVATIONS:
        raise ValueError(
            f"Need at least {MIN_OBSERVATIONS} observations to say anything about significance; this has {t}."
        )
    if n_trials < 1:
        raise ValueError("n_trials must be at least 1")
    sr = sharpe_ratio(returns)
    if not np.isfinite(sr):
        raise ValueError("The returns have no variation, so there is no Sharpe ratio.")
    skew = float(sps.skew(returns, bias=True))
    kurt = float(sps.kurtosis(returns, fisher=False, bias=True))  # non-excess, see module docstring
    ann = math.sqrt(periods_per_year)
    total_growth = float(np.prod(1.0 + returns))
    years = t / periods_per_year
    ann_return = total_growth ** (1.0 / years) - 1.0 if total_growth > 0 and years > 0 else None
    mdd = max_drawdown(returns)

    out: dict = {
        "observations": t,
        "periods_per_year": periods_per_year,
        "sharpe_per_period": _finite(sr, 5),
        "sharpe_annualized": _finite(sr * ann, 3),
        "skew": _finite(skew, 3),
        "kurtosis": _finite(kurt, 3),
        "annualized_return": _finite(ann_return, 4),
        "max_drawdown": _finite(mdd, 4),
        "sortino_annualized": _finite((sortino_ratio(returns) or float("nan")) * ann, 3),
        "calmar": _finite(ann_return / abs(mdd), 3) if ann_return is not None and mdd < 0 else None,
        "confidence_level": confidence,
    }
    try:
        psr = probabilistic_sharpe_ratio(sr, t, 0.0, skew, kurt)
    except ValueError as exc:
        out["error"] = str(exc)
        return out
    out["psr"] = _finite(psr, 4)
    mtrl = min_track_record_length(sr, 0.0, skew, kurt, confidence)
    out["min_track_record"] = None if mtrl is None else int(math.ceil(mtrl))

    n_trials = int(n_trials)
    out["n_trials"] = n_trials
    if n_trials > 1:
        # Without the real dispersion of the trials' Sharpes, use the sampling error of one Sharpe
        # estimate (Lo, 2002): how far apart honest trials of a zero-edge idea would land.
        std = (
            trial_sharpe_std
            if trial_sharpe_std is not None
            else math.sqrt((1.0 + 0.5 * sr * sr) / (t - 1))
        )
        dsr, bar = deflated_sharpe_ratio(sr, n_trials, t, std, skew, kurt)
        out.update(
            {
                "trial_sharpe_std": _finite(std, 5),
                "trial_std_assumed": trial_sharpe_std is None,
                "bar_per_period": _finite(bar, 5),
                "bar_annualized": _finite(bar * ann, 3),
                "dsr": _finite(dsr, 4),
            }
        )
        score, label = dsr, f"after allowing for {n_trials} strategies tried"
    else:
        score, label = psr, "against doing nothing"

    pct = f"{score:.0%}"
    if score >= confidence:
        out["verdict"] = "likely_real"
        out["verdict_text"] = (
            f"The Sharpe holds up {label}: {pct} confidence it is a real edge, not luck."
        )
    elif score >= 0.75:
        out["verdict"] = "suggestive"
        out["verdict_text"] = (
            f"Suggestive but not proven: {pct} confidence {label}. It would need more history or fewer tries to clear {confidence:.0%}."
        )
    else:
        out["verdict"] = "indistinguishable"
        out["verdict_text"] = f"Cannot be told apart from luck {label}: only {pct} confidence."
    return out
