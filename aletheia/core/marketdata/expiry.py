"""
F&O expiry-date calendar math for NSE/BSE index derivatives.

Deterministic date arithmetic only — no network calls, so unlike the NSE
quote/shareholding endpoints elsewhere in this codebase, every function here
is fully testable and verifiable in any environment.

The one thing that ISN'T pure math is *which weekday* an index expires on.
SEBI/exchange circulars have changed this more than once (e.g. Bank Nifty
moved from Thursday to Wednesday in 2023; a 2024 SEBI circular pushed
exchanges toward a single weekly expiry day each — NSE settled on Tuesday,
BSE on Thursday, from January 2025). Treat `EXPIRY_WEEKDAY` as a
best-effort default, not ground truth: confirm against the exchange's
current circular before relying on it for anything real-money.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)


@dataclass(frozen=True)
class ExpiryRule:
    weekday: int
    verified: bool
    note: str


# Unverified as of this session — confirm against a live NSE/BSE circular
# before trusting these for real trading.
EXPIRY_RULES: dict[str, ExpiryRule] = {
    "NIFTY": ExpiryRule(TUESDAY, verified=False, note="NSE consolidated to a single weekly expiry day (Tuesday) from Jan 2025 per SEBI circular."),
    "BANKNIFTY": ExpiryRule(TUESDAY, verified=False, note="Same NSE consolidation as NIFTY; BANKNIFTY weekly contracts were discontinued in 2024, monthly only."),
    "FINNIFTY": ExpiryRule(TUESDAY, verified=False, note="Same NSE consolidation as NIFTY."),
    "SENSEX": ExpiryRule(THURSDAY, verified=False, note="BSE settled on Thursday as its single weekly expiry day."),
    "BANKEX": ExpiryRule(THURSDAY, verified=False, note="Same BSE consolidation as SENSEX."),
}


def get_expiry_rule(underlying: str) -> ExpiryRule:
    rule = EXPIRY_RULES.get(underlying.upper())
    if rule is None:
        raise ValueError(f"No expiry rule configured for '{underlying}'")
    return rule


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Last occurrence of `weekday` (Mon=0..Sun=6) in the given month."""
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day = next_month_first - timedelta(days=1)
    offset = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=offset)


def _weekday_occurrences_in_month(year: int, month: int, weekday: int) -> list[date]:
    """All occurrences of `weekday` in the given month, in order."""
    first_of_month = date(year, month, 1)
    offset = (weekday - first_of_month.weekday()) % 7
    d = first_of_month + timedelta(days=offset)
    occurrences = []
    while d.month == month:
        occurrences.append(d)
        d += timedelta(days=7)
    return occurrences


def _roll_back_to_trading_day(d: date, holidays: set[date] | None) -> date:
    """If `d` is a weekend or a configured holiday, step back to the prior trading day."""
    holidays = holidays or set()
    while d.weekday() >= SATURDAY or d in holidays:
        d -= timedelta(days=1)
    return d


def monthly_expiry(underlying: str, year: int, month: int, holidays: set[date] | None = None) -> date:
    """Last `expiry weekday` of the month, rolled back over holidays/weekends."""
    rule = get_expiry_rule(underlying)
    raw = _last_weekday_of_month(year, month, rule.weekday)
    return _roll_back_to_trading_day(raw, holidays)


def weekly_expiries(underlying: str, year: int, month: int, holidays: set[date] | None = None) -> list[date]:
    """Every weekly expiry in the month, each independently rolled back over holidays."""
    rule = get_expiry_rule(underlying)
    raw_dates = _weekday_occurrences_in_month(year, month, rule.weekday)
    return [_roll_back_to_trading_day(d, holidays) for d in raw_dates]


def next_expiry(underlying: str, on_date: date, holidays: set[date] | None = None) -> date:
    """The next weekly expiry on or after `on_date`."""
    year, month = on_date.year, on_date.month
    for _ in range(3):
        for expiry in weekly_expiries(underlying, year, month, holidays):
            if expiry >= on_date:
                return expiry
        month += 1
        if month > 12:
            month = 1
            year += 1
    raise RuntimeError(f"Could not resolve next expiry for {underlying} from {on_date}")
