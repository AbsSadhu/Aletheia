"""
Information Coefficient (IC) Scorer for factor evaluation.

IC measures the Spearman rank correlation between factor values and
forward returns. Higher IC = more predictive factor.
"""

from __future__ import annotations

import sqlite3
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from scipy import stats as _scipy_stats

    _HAS_SCIPY = True
except ImportError:
    _scipy_stats = None  # type: ignore
    _HAS_SCIPY = False


logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".aletheia" / "memory" / "factor_ic.db"


class ICResult:
    """IC score for a single factor."""

    def __init__(
        self,
        factor_name: str,
        ic: float,
        ic_std: float,
        icir: float,
        t_stat: float,
        p_value: float,
        n_observations: int,
        computed_at: datetime,
        status: str = "alive",
    ) -> None:
        self.factor_name = factor_name
        self.ic = ic
        self.ic_std = ic_std
        self.icir = icir  # IC Information Ratio = IC / IC_std
        self.t_stat = t_stat
        self.p_value = p_value
        self.n_observations = n_observations
        self.computed_at = computed_at
        self.status = status  # "alive", "reversed", "dead"

    @property
    def is_significant(self) -> bool:
        return self.p_value < 0.05 and abs(self.ic) > 0.02

    def __repr__(self) -> str:
        return (
            f"ICResult({self.factor_name}: IC={self.ic:.4f}, ICIR={self.icir:.2f}, "
            f"p={self.p_value:.3f}, status={self.status})"
        )


class ICScorer:
    """
    Computes and stores Information Coefficient scores for factors.

    Usage:
        scorer = ICScorer()
        result = scorer.compute_ic("rsi", factor_values, forward_returns)
        scores = scorer.get_all_scores()
    """

    def __init__(self, db_path: str | Path = _DEFAULT_DB) -> None:
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS factor_ic (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    factor_name  TEXT NOT NULL,
                    ic           REAL NOT NULL,
                    ic_std       REAL NOT NULL,
                    icir         REAL NOT NULL,
                    t_stat       REAL NOT NULL,
                    p_value      REAL NOT NULL,
                    n_obs        INTEGER NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'alive',
                    computed_at  TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_factor_ic_name_ts
                ON factor_ic (factor_name, computed_at DESC)
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def compute_ic(
        self,
        factor_name: str,
        factor_values: pd.Series,
        forward_returns: pd.Series,
    ) -> ICResult:
        """
        Compute Spearman IC between factor_values and forward_returns.

        Both series should share the same index (ticker, date, etc.).
        """
        # Align and drop NaN
        aligned = pd.concat([factor_values, forward_returns], axis=1).dropna()
        if len(aligned) < 10:
            logger.warning("Not enough observations for IC calculation: %d", len(aligned))
            result = ICResult(
                factor_name=factor_name,
                ic=0.0,
                ic_std=0.0,
                icir=0.0,
                t_stat=0.0,
                p_value=1.0,
                n_observations=len(aligned),
                computed_at=datetime.now(UTC),
                status="dead",
            )
            return result

        if not _HAS_SCIPY:
            raise ImportError(
                "scipy is required for IC computation. Install it with: pip install scipy"
            )
        col0, col1 = aligned.columns[0], aligned.columns[1]
        spearman_corr, p_val = _scipy_stats.spearmanr(aligned[col0], aligned[col1])  # type: ignore
        ic = float(spearman_corr)

        # Rolling IC to estimate IC_std and ICIR
        # For simplicity: use bootstrap std over 5-obs windows
        window_size = min(20, len(aligned) // 2)
        if window_size >= 5:
            window_ics = []
            for i in range(0, len(aligned) - window_size, window_size // 2):
                window = aligned.iloc[i : i + window_size]
                wic, _ = _scipy_stats.spearmanr(window[col0], window[col1])  # type: ignore
                if not np.isnan(wic):
                    window_ics.append(wic)
            ic_std = float(np.std(window_ics)) if window_ics else 0.01
        else:
            ic_std = 0.01

        icir = ic / ic_std if ic_std > 0 else 0.0

        # Analytical t-stat: t = IC * sqrt(N) / IC_std
        # More robust than ttest_1samp([ic]) which gives NaN for n=1
        n_windows = len(aligned)
        if ic_std > 0 and n_windows > 1:
            t_stat = ic * (n_windows**0.5) / ic_std
        else:
            t_stat = 0.0
        # Sanitize NaN/Inf that could arise from edge cases
        import math as _math

        if _math.isnan(t_stat) or _math.isinf(t_stat):
            t_stat = 0.0
        if _math.isnan(float(p_val)) or _math.isinf(float(p_val)):
            p_val = 1.0

        # Classify factor status
        if abs(ic) < 0.01 or float(p_val) > 0.2:
            status = "dead"
        elif ic < 0:
            status = "reversed"
        else:
            status = "alive"

        result = ICResult(
            factor_name=factor_name,
            ic=round(ic, 6),
            ic_std=round(ic_std, 6),
            icir=round(icir, 4),
            t_stat=round(float(t_stat), 4),
            p_value=round(float(p_val), 6),
            n_observations=len(aligned),
            computed_at=datetime.now(UTC),
            status=status,
        )
        self._store(result)
        return result

    def _store(self, result: ICResult) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO factor_ic
                    (factor_name, ic, ic_std, icir, t_stat, p_value, n_obs, status, computed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    result.factor_name,
                    result.ic,
                    result.ic_std,
                    result.icir,
                    result.t_stat,
                    result.p_value,
                    result.n_observations,
                    result.status,
                    result.computed_at.isoformat(),
                ),
            )

    def get_latest_score(self, factor_name: str) -> ICResult | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM factor_ic WHERE factor_name = ? ORDER BY computed_at DESC LIMIT 1",
                (factor_name,),
            ).fetchone()
        return self._row_to_result(row) if row else None

    def get_all_scores(self) -> dict[str, ICResult]:
        """Get the latest IC score per factor."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT DISTINCT factor_name, MAX(computed_at) as latest,
                    ic, ic_std, icir, t_stat, p_value, n_obs, status, computed_at
                FROM factor_ic GROUP BY factor_name
            """).fetchall()
        return {row["factor_name"]: self._row_to_result(row) for row in rows}

    def get_ic_weights(self, min_ic: float = 0.02) -> dict[str, float]:
        """
        Return factor weights based on IC magnitude.
        Dead/reversed factors get weight 0.

        Returns: {factor_name: weight}
        """
        scores = self.get_all_scores()
        weights: dict[str, float] = {}
        for name, score in scores.items():
            if score.status == "dead":
                weights[name] = 0.0
            elif score.status == "reversed":
                weights[name] = max(0.0, score.ic)  # use magnitude but limit to 0
            else:
                weights[name] = max(0.0, score.ic) if score.is_significant else min_ic / 2
        return weights

    def _row_to_result(self, row: sqlite3.Row) -> ICResult:
        return ICResult(
            factor_name=row["factor_name"],
            ic=row["ic"],
            ic_std=row["ic_std"],
            icir=row["icir"],
            t_stat=row["t_stat"],
            p_value=row["p_value"],
            n_observations=row["n_obs"],
            computed_at=datetime.fromisoformat(row["computed_at"]),
            status=row["status"],
        )

    def list_scores_as_dicts(self) -> list[dict[str, Any]]:
        scores = self.get_all_scores()
        return [
            {
                "factor_name": r.factor_name,
                "ic": r.ic,
                "ic_std": r.ic_std,
                "icir": r.icir,
                "t_stat": r.t_stat,
                "p_value": r.p_value,
                "n_observations": r.n_observations,
                "status": r.status,
                "significant": r.is_significant,
                "computed_at": r.computed_at.isoformat(),
            }
            for r in scores.values()
        ]

    def get_history(self, factor_name: str, limit: int = 10) -> list[ICResult]:
        """Return the most recent IC computations for a factor, newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM factor_ic
                WHERE factor_name = ?
                ORDER BY computed_at DESC
                LIMIT ?
                """,
                (factor_name, limit),
            ).fetchall()
        return [self._row_to_result(row) for row in rows]

    def get_factor_ranking(self, min_observations: int = 10) -> list[ICResult]:
        """
        Return all factors ranked by absolute IC descending.
        Dead factors appear last; reversed factors are included but flagged.
        """
        scores = self.get_all_scores()
        results = [r for r in scores.values() if r.n_observations >= min_observations]
        results.sort(key=lambda r: abs(r.ic) if r.status != "dead" else -1, reverse=True)
        return results
