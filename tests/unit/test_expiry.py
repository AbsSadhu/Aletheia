"""Pure calendar-math tests for the F&O expiry module — no network, fully verifiable."""

from datetime import date, timedelta

import pytest

from aletheia.core.marketdata.expiry import (
    get_expiry_rule,
    monthly_expiry,
    next_expiry,
    weekly_expiries,
)


def test_monthly_expiry_is_last_configured_weekday_of_month() -> None:
    # September 2026: last Tuesday is the 29th.
    result = monthly_expiry("NIFTY", 2026, 9)
    assert result == date(2026, 9, 29)
    assert result.weekday() == get_expiry_rule("NIFTY").weekday


def test_monthly_expiry_rolls_back_over_a_holiday() -> None:
    holidays = {date(2026, 9, 29)}
    result = monthly_expiry("NIFTY", 2026, 9, holidays=holidays)
    assert result == date(2026, 9, 28)


def test_monthly_expiry_rolls_back_over_weekend_if_last_weekday_lands_there() -> None:
    # BSE (Thursday) in September 2026: last Thursday is the 24th — no weekend
    # adjustment needed, but confirm a clean case still returns a weekday.
    result = monthly_expiry("SENSEX", 2026, 9)
    assert result.weekday() < 5


def test_weekly_expiries_returns_one_per_week_in_month() -> None:
    results = weekly_expiries("NIFTY", 2026, 9)
    assert len(results) in (4, 5)
    assert all(d.weekday() == get_expiry_rule("NIFTY").weekday for d in results)
    assert results == sorted(results)


def test_weekly_expiries_holiday_rollback_is_independent_per_week() -> None:
    all_expiries = weekly_expiries("NIFTY", 2026, 9)
    holiday = all_expiries[0]
    adjusted = weekly_expiries("NIFTY", 2026, 9, holidays={holiday})
    assert adjusted[0] == holiday - timedelta(days=1)
    assert adjusted[1:] == all_expiries[1:]


def test_next_expiry_finds_soonest_expiry_on_or_after_date() -> None:
    all_expiries = weekly_expiries("NIFTY", 2026, 9)
    mid_month = all_expiries[1] - timedelta(days=3)
    result = next_expiry("NIFTY", mid_month)
    assert result == all_expiries[1]


def test_next_expiry_rolls_into_next_month_if_needed() -> None:
    last_expiry_of_month = weekly_expiries("NIFTY", 2026, 9)[-1]
    day_after = last_expiry_of_month + timedelta(days=1)
    result = next_expiry("NIFTY", day_after)
    assert result.month == 10
    assert result == weekly_expiries("NIFTY", 2026, 10)[0]


def test_unknown_underlying_raises() -> None:
    with pytest.raises(ValueError, match="No expiry rule"):
        get_expiry_rule("DOGECOIN")


def test_all_configured_rules_are_marked_unverified() -> None:
    """Regression guard: don't silently flip a rule to verified without a real citation."""
    from aletheia.core.marketdata.expiry import EXPIRY_RULES

    for underlying, rule in EXPIRY_RULES.items():
        assert rule.verified is False, f"{underlying} marked verified with no source captured here"
        assert rule.note
