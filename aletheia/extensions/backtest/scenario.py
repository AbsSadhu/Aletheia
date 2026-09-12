from __future__ import annotations

from datetime import UTC

from aletheia.extensions.backtest.tax import build_tax_summary
from aletheia.core.models import Holding, MarketQuote, SageOutput, SageScenario


def build_scenario(holding: Holding, quote: MarketQuote, conviction: float) -> SageOutput:
    # Deliberately not delegated to aletheia_rust's build_scenario_rust: that
    # path's embedded tax summary predates holding-period-aware STCG/LTCG
    # logic (see aletheia/extensions/backtest/tax.py) and would silently
    # return the old flat-rate numbers even after this function learned to
    # tell short- and long-term gains apart.
    move_pct = (quote.close - holding.average_price) / max(holding.average_price, 1e-6)
    projected_return_pct = (move_pct * 100) + (conviction * 8.0)
    pre_tax_profit = holding.quantity * holding.average_price * (projected_return_pct / 100)

    holding_days: int | None = None
    if holding.acquisition_date is not None:
        acquisition = holding.acquisition_date
        if acquisition.tzinfo is None:
            acquisition = acquisition.replace(tzinfo=UTC)
        holding_days = max((quote.as_of - acquisition).days, 0)

    tax_summary = build_tax_summary(holding.tax_profile, pre_tax_profit, holding_days)
    projected_post_tax_return_pct = (
        tax_summary.post_tax_profit / max(holding.quantity * holding.average_price, 1e-6)
    ) * 100
    projected_sharpe = max(min((projected_return_pct / 12.0), 2.5), -1.0)

    rationale = [
        f"Projected pre-tax return is {projected_return_pct:.2f}% based on mark-to-market drift and conviction.",
        f"Estimated tax drag for {holding.tax_profile.value} is {tax_summary.tax_drag_pct:.2f}%.",
    ]

    return SageOutput(
        symbol=holding.symbol.upper(),
        scenario=SageScenario(
            scenario_name="base_tax_aware_projection",
            projected_return_pct=round(projected_return_pct, 2),
            projected_post_tax_return_pct=round(projected_post_tax_return_pct, 2),
            projected_sharpe=round(projected_sharpe, 2),
            tax_summary=tax_summary,
        ),
        confidence=round(max(min(0.45 + conviction * 0.4, 0.9), 0.2), 2),
        rationale=rationale,
    )
