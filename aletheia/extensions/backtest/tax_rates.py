"""India capital-gains tax rate table for tax-drag estimation.

**UNVERIFIED.** Seeded from public reporting on the Finance Act 2024 (July
2024 budget) capital-gains changes at the time this table was written — not
confirmed against a primary source (the Income Tax Act text, a CBDT
circular, or a CA) as part of adding this structure. Every `TaxRateEntry`
below carries `verified=False` for that reason, and `build_tax_summary()`
propagates it into `TaxSummary.rates_verified` so callers and the frontend
can surface it rather than presenting a number with false confidence.
Confirm against a current source before relying on this for real decisions,
and update `assessment_year`/`source`/`verified` on the entries you confirm.

F&O is a distinct problem, not just an unverified number: as non-speculative
business income it's taxed at the individual's income-tax slab rate, which
this table has no way to know. The F&O entry is explicitly flagged
`slab_dependent=True` and its rate is a top-slab approximation, not a claim
of accuracy for any specific user.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aletheia.core.models import TaxProfile

# Holding period (days) at or above which a position is long-term, per
# profile. Crypto and F&O don't have a term distinction (see determine_term).
LONG_TERM_THRESHOLD_DAYS: dict[TaxProfile, int] = {
    TaxProfile.EQUITY: 365,
    TaxProfile.MUTUAL_FUND: 365,
}


@dataclass(frozen=True)
class TaxRateEntry:
    rate_pct: float
    assessment_year: str
    source: str
    verified: bool = False
    slab_dependent: bool = False
    notes: list[str] = field(default_factory=list)


# profile -> term ("short" | "long" | "flat") -> entry
TAX_RATE_TABLE: dict[TaxProfile, dict[str, TaxRateEntry]] = {
    TaxProfile.EQUITY: {
        "short": TaxRateEntry(
            20.0, "FY2024-25", "Finance Act 2024 capital-gains changes (public reporting)"
        ),
        "long": TaxRateEntry(
            12.5,
            "FY2024-25",
            "Finance Act 2024 capital-gains changes (public reporting)",
            notes=["Ignores the ₹1.25L LTCG exemption threshold — applied to full gain."],
        ),
    },
    TaxProfile.MUTUAL_FUND: {
        "short": TaxRateEntry(
            20.0, "FY2024-25", "Finance Act 2024 capital-gains changes (public reporting)"
        ),
        "long": TaxRateEntry(
            12.5,
            "FY2024-25",
            "Finance Act 2024 capital-gains changes (public reporting)",
            notes=["Assumes an equity-oriented fund; debt fund taxation differs."],
        ),
    },
    TaxProfile.CRYPTO: {
        "flat": TaxRateEntry(
            30.0,
            "FY2022-23+",
            "Income Tax Act Section 115BBH (public reporting)",
            notes=["No loss set-off or deduction beyond cost of acquisition under 115BBH."],
        ),
    },
    TaxProfile.FNO: {
        "flat": TaxRateEntry(
            30.0,
            "n/a",
            "Approximation only",
            slab_dependent=True,
            notes=[
                "F&O is non-speculative business income taxed at the individual's "
                "slab rate, not a fixed percentage. This uses a top-slab "
                "approximation — actual liability depends on total income."
            ],
        ),
    },
}


def determine_term(tax_profile: TaxProfile, holding_days: int | None) -> str:
    """Which rate-table bucket applies. Crypto and F&O are always "flat" —
    holding period doesn't change their tax treatment. For equity/mutual
    fund, an unknown holding period conservatively resolves to "short" (the
    higher rate) rather than assuming a favorable long-term rate.
    """
    if tax_profile not in LONG_TERM_THRESHOLD_DAYS:
        return "flat"
    if holding_days is None:
        return "short"
    threshold = LONG_TERM_THRESHOLD_DAYS[tax_profile]
    return "long" if holding_days >= threshold else "short"


def get_rate_entry(tax_profile: TaxProfile, holding_days: int | None) -> TaxRateEntry:
    term = determine_term(tax_profile, holding_days)
    table = TAX_RATE_TABLE.get(tax_profile, TAX_RATE_TABLE[TaxProfile.EQUITY])
    return table.get(term) or next(iter(table.values()))
