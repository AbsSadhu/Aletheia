from __future__ import annotations

from aletheia.core.models import TaxProfile, TaxSummary
from aletheia.extensions.backtest.tax_rates import determine_term, get_rate_entry


def estimate_tax_drag(tax_profile: TaxProfile, holding_days: int | None = None) -> float:
    """Returns the rate as a fraction (0.20 = 20%), not a percentage."""
    return get_rate_entry(tax_profile, holding_days).rate_pct / 100.0


def build_tax_summary(
    tax_profile: TaxProfile, pre_tax_profit: float, holding_days: int | None = None
) -> TaxSummary:
    """Single source of truth for tax-drag estimation — deliberately pure
    Python, not delegated to aletheia_rust. The old Rust path
    (`build_tax_summary_rust`) has no concept of holding period, so calling
    it here would silently produce STCG/LTCG-blind results even after this
    function learned to tell the two apart; keeping one implementation of a
    domain-sensitive rate table beats keeping two in sync. See
    `aletheia/extensions/backtest/tax_rates.py` for the rate table itself
    and its verification status.
    """
    term = determine_term(tax_profile, holding_days)
    entry = get_rate_entry(tax_profile, holding_days)
    tax_drag_pct = entry.rate_pct / 100.0

    estimated_tax_amount = max(pre_tax_profit, 0.0) * tax_drag_pct
    post_tax_profit = pre_tax_profit - estimated_tax_amount

    notes = list(entry.notes)
    if holding_days is None and term == "short":
        notes.append(
            "No acquisition date on this holding — assumed short-term (higher rate)."
        )
    if not entry.verified:
        notes.append(f"Rate unverified against a primary source (as of {entry.assessment_year}).")

    return TaxSummary(
        tax_profile=tax_profile,
        pre_tax_profit=round(pre_tax_profit, 2),
        tax_drag_pct=round(tax_drag_pct * 100, 2),
        estimated_tax_amount=round(estimated_tax_amount, 2),
        post_tax_profit=round(post_tax_profit, 2),
        term=term,
        rates_verified=entry.verified,
        notes=notes,
    )
