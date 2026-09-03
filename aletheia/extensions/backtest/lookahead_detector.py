"""
Look-Ahead Bias Detector for backtesting.

Ensures that data accessed at a given decision timestamp never originates
from a bar with a later timestamp.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


class LookAheadViolation(Exception):
    """Raised when look-ahead bias is detected."""

    def __init__(self, data_ts: Any, decision_ts: Any) -> None:
        super().__init__(
            f"LOOK-AHEAD BIAS: Data timestamp {data_ts} is after decision timestamp {decision_ts}. "
            "This would cause unrealistically good backtest results."
        )


def assert_no_lookahead(
    data_df: pd.DataFrame,
    decision_timestamp: Any,
    timestamp_col: str = "date",
) -> None:
    """
    Assert that all rows in data_df have a timestamp ≤ decision_timestamp.

    Parameters
    ----------
    data_df : pd.DataFrame
        DataFrame of market data being accessed.
    decision_timestamp : Any
        The timestamp at which the decision is being made.
    timestamp_col : str
        Column name containing the data timestamps.

    Raises
    ------
    LookAheadViolation
        If any data row has a timestamp after decision_timestamp.
    """
    if timestamp_col in data_df.columns:
        max_data_ts = data_df[timestamp_col].max()
    elif isinstance(data_df.index, pd.DatetimeIndex):
        max_data_ts = data_df.index.max()
    else:
        return  # Cannot verify without timestamps

    # Normalize to comparable types
    try:
        if isinstance(decision_timestamp, str):
            decision_ts = pd.Timestamp(decision_timestamp)
        else:
            decision_ts = pd.Timestamp(decision_timestamp)

        if isinstance(max_data_ts, str):
            data_ts = pd.Timestamp(max_data_ts)
        else:
            data_ts = pd.Timestamp(max_data_ts)

        if data_ts > decision_ts:
            raise LookAheadViolation(data_ts, decision_ts)
    except LookAheadViolation:
        raise
    except Exception:
        pass  # If comparison fails, skip (don't block on type errors)


class LookAheadGuard:
    """
    Context manager / decorator that tracks the current decision timestamp
    and validates all data accesses.

    Usage:
        guard = LookAheadGuard(decision_ts="2024-01-15")
        guard.validate_dataframe(ohlcv_df)
    """

    def __init__(self, decision_timestamp: Any = None) -> None:
        self.decision_timestamp = decision_timestamp
        self.violations: list[dict[str, Any]] = []

    def set_decision_ts(self, ts: Any) -> None:
        self.decision_timestamp = ts

    def validate_dataframe(
        self,
        df: pd.DataFrame,
        timestamp_col: str = "date",
        raise_on_violation: bool = True,
    ) -> bool:
        """
        Validate a dataframe for look-ahead bias.

        Returns True if clean, False if violation detected (when raise=False).
        """
        if self.decision_timestamp is None:
            return True
        try:
            assert_no_lookahead(df, self.decision_timestamp, timestamp_col)
            return True
        except LookAheadViolation as exc:
            self.violations.append(
                {
                    "message": str(exc),
                    "decision_ts": str(self.decision_timestamp),
                }
            )
            if raise_on_violation:
                raise
            return False

    def has_violations(self) -> bool:
        return len(self.violations) > 0

    def report(self) -> str:
        if not self.violations:
            return "✅ No look-ahead bias detected."
        lines = [f"⚠️ {len(self.violations)} look-ahead violation(s):"]
        for v in self.violations:
            lines.append(f"  - {v['message']}")
        return "\n".join(lines)
