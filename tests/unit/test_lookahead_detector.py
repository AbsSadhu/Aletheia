from __future__ import annotations

import pandas as pd
import pytest

from aletheia.extensions.backtest.lookahead_detector import (
    LookAheadGuard,
    LookAheadViolation,
    assert_no_lookahead,
)


def _df(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"date": dates, "close": [100.0] * len(dates)})


class TestAssertNoLookahead:
    def test_clean_data_passes(self) -> None:
        df = _df(["2024-01-01", "2024-01-02", "2024-01-03"])
        assert_no_lookahead(df, decision_timestamp="2024-01-03")

    def test_data_after_decision_raises(self) -> None:
        df = _df(["2024-01-01", "2024-01-05"])
        with pytest.raises(LookAheadViolation):
            assert_no_lookahead(df, decision_timestamp="2024-01-03")

    def test_exact_boundary_is_not_a_violation(self) -> None:
        df = _df(["2024-01-01", "2024-01-03"])
        assert_no_lookahead(df, decision_timestamp="2024-01-03")

    def test_timestamp_objects_accepted(self) -> None:
        df = _df(["2024-01-01", "2024-01-02"])
        assert_no_lookahead(df, decision_timestamp=pd.Timestamp("2024-01-05"))

    def test_datetime_index_used_when_no_timestamp_column(self) -> None:
        df = pd.DataFrame(
            {"close": [1.0, 2.0]},
            index=pd.DatetimeIndex(["2024-01-01", "2024-01-10"]),
        )
        with pytest.raises(LookAheadViolation):
            assert_no_lookahead(df, decision_timestamp="2024-01-05", timestamp_col="date")

    def test_missing_timestamp_info_does_not_raise(self) -> None:
        df = pd.DataFrame({"close": [1.0, 2.0]})
        # No 'date' column and no DatetimeIndex -> can't verify, must not block.
        assert_no_lookahead(df, decision_timestamp="2024-01-05", timestamp_col="date") is None

    def test_incomparable_types_are_swallowed_not_raised(self) -> None:
        df = _df(["not-a-date"])
        # Malformed timestamps must not crash the backtest with an unrelated error.
        assert_no_lookahead(df, decision_timestamp="2024-01-05")


class TestLookAheadGuard:
    def test_no_decision_ts_set_is_always_clean(self) -> None:
        guard = LookAheadGuard()
        assert guard.validate_dataframe(_df(["2099-01-01"])) is True
        assert not guard.has_violations()

    def test_violation_recorded_and_raised_by_default(self) -> None:
        guard = LookAheadGuard(decision_timestamp="2024-01-01")
        with pytest.raises(LookAheadViolation):
            guard.validate_dataframe(_df(["2024-06-01"]))
        assert guard.has_violations()
        assert "2024-06-01" in guard.report() or "look-ahead" in guard.report().lower()

    def test_violation_suppressed_when_raise_on_violation_false(self) -> None:
        guard = LookAheadGuard(decision_timestamp="2024-01-01")
        result = guard.validate_dataframe(_df(["2024-06-01"]), raise_on_violation=False)
        assert result is False
        assert guard.has_violations()

    def test_set_decision_ts_updates_state(self) -> None:
        guard = LookAheadGuard()
        guard.set_decision_ts("2024-01-01")
        assert guard.decision_timestamp == "2024-01-01"

    def test_report_clean_state(self) -> None:
        guard = LookAheadGuard(decision_timestamp="2024-06-01")
        guard.validate_dataframe(_df(["2024-01-01"]))
        assert "no look-ahead" in guard.report().lower()
