from __future__ import annotations

from aletheia.extensions.backtest.tax import build_tax_summary
from aletheia.core.models import Holding, MarketQuote, SageOutput, SageScenario, TaxSummary

try:
    import aletheia_rust
except ImportError:
    aletheia_rust = None


def build_scenario(holding: Holding, quote: MarketQuote, conviction: float) -> SageOutput:
    if aletheia_rust is not None:
        try:
            res = aletheia_rust.build_scenario_rust(holding, quote, float(conviction))
            tax_data = res["scenario"]["tax_summary"]
            return SageOutput(
                symbol=res["symbol"],
                scenario=SageScenario(
                    scenario_name=res["scenario"]["scenario_name"],
                    projected_return_pct=res["scenario"]["projected_return_pct"],
                    projected_post_tax_return_pct=res["scenario"]["projected_post_tax_return_pct"],
                    projected_sharpe=res["scenario"]["projected_sharpe"],
                    tax_summary=TaxSummary(
                        tax_profile=holding.tax_profile,
                        pre_tax_profit=tax_data["pre_tax_profit"],
                        tax_drag_pct=tax_data["tax_drag_pct"],
                        estimated_tax_amount=tax_data["estimated_tax_amount"],
                        post_tax_profit=tax_data["post_tax_profit"],
                    ),
                ),
                confidence=res["confidence"],
                rationale=res["rationale"],
            )
        except Exception:
            pass

    move_pct = (quote.close - holding.average_price) / max(holding.average_price, 1e-6)
    projected_return_pct = (move_pct * 100) + (conviction * 8.0)
    pre_tax_profit = holding.quantity * holding.average_price * (projected_return_pct / 100)
    tax_summary = build_tax_summary(holding.tax_profile, pre_tax_profit)
    projected_post_tax_return_pct = (
        (tax_summary.post_tax_profit / max(holding.quantity * holding.average_price, 1e-6)) * 100
    )
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



