from __future__ import annotations

from aletheia.core.models import TaxProfile, TaxSummary

try:
    import aletheia_rust
except ImportError:
    aletheia_rust = None


def estimate_tax_drag(tax_profile: TaxProfile) -> float:
    if tax_profile == TaxProfile.EQUITY:
        return 0.15
    if tax_profile == TaxProfile.FNO:
        return 0.175
    if tax_profile == TaxProfile.CRYPTO:
        return 0.15
    if tax_profile == TaxProfile.MUTUAL_FUND:
        return 0.20
    return 0.15


def build_tax_summary(tax_profile: TaxProfile, pre_tax_profit: float) -> TaxSummary:
    if aletheia_rust is not None:
        try:
            profile_str = tax_profile.value if hasattr(tax_profile, "value") else str(tax_profile)
            res = aletheia_rust.build_tax_summary_rust(profile_str, float(pre_tax_profit))
            return TaxSummary(
                tax_profile=tax_profile,
                pre_tax_profit=res["pre_tax_profit"],
                tax_drag_pct=res["tax_drag_pct"],
                estimated_tax_amount=res["estimated_tax_amount"],
                post_tax_profit=res["post_tax_profit"],
            )
        except Exception:
            pass

    tax_drag_pct = estimate_tax_drag(tax_profile)
    estimated_tax_amount = max(pre_tax_profit, 0.0) * tax_drag_pct
    post_tax_profit = pre_tax_profit - estimated_tax_amount
    return TaxSummary(
        tax_profile=tax_profile,
        pre_tax_profit=round(pre_tax_profit, 2),
        tax_drag_pct=round(tax_drag_pct * 100, 2),
        estimated_tax_amount=round(estimated_tax_amount, 2),
        post_tax_profit=round(post_tax_profit, 2),
    )
