from __future__ import annotations

from aletheia.core.models import Holding, MarketQuote, Portfolio, SentinelOutput

try:
    import aletheia_rust
except ImportError:
    aletheia_rust = None


def portfolio_market_values(portfolio: Portfolio, quotes_by_symbol: dict[str, MarketQuote]) -> dict[str, float]:
    values: dict[str, float] = {}
    for holding in portfolio.holdings:
        quote = quotes_by_symbol.get(holding.symbol.upper())
        if quote is None:
            continue
        values[holding.symbol.upper()] = holding.quantity * quote.close
    return values


def assess_portfolio_risk(portfolio: Portfolio, quotes_by_symbol: dict[str, MarketQuote]) -> SentinelOutput:
    if aletheia_rust is not None:
        try:
            res = aletheia_rust.assess_portfolio_risk_rust(portfolio, quotes_by_symbol)
            return SentinelOutput(
                portfolio_var_95=res["portfolio_var_95"],
                concentration_risk=res["concentration_risk"],
                max_single_position_pct=res["max_single_position_pct"],
                market_regime=res["market_regime"],
                confidence=res["confidence"],
                alerts=res["alerts"],
            )
        except Exception:
            pass

    values = portfolio_market_values(portfolio, quotes_by_symbol)
    total_value = sum(values.values()) or 1.0
    weights = {symbol: value / total_value for symbol, value in values.items()}
    max_weight = max(weights.values(), default=0.0)

    daily_move_estimate = 0.0
    for holding in portfolio.holdings:
        quote = quotes_by_symbol.get(holding.symbol.upper())
        if quote is None or quote.open in (None, 0):
            continue
        daily_move_estimate += abs((quote.close - quote.open) / quote.open) * weights.get(
            holding.symbol.upper(), 0.0
        )

    portfolio_var_95 = -(total_value * max(daily_move_estimate * 1.65, 0.01))
    concentration_risk = round(max_weight, 4)
    regime = "balanced"
    alerts: list[str] = []

    if max_weight > 0.4:
        regime = "concentrated"
        alerts.append("Single-position exposure is above 40% of portfolio market value.")
    if daily_move_estimate > 0.04:
        regime = "volatile"
        alerts.append("Observed mark-to-market volatility is elevated for the sampled holdings.")

    confidence = 0.55
    if not values:
        alerts.append("Risk metrics are estimated with incomplete market data.")
        confidence = 0.2

    return SentinelOutput(
        portfolio_var_95=round(portfolio_var_95, 2),
        concentration_risk=concentration_risk,
        max_single_position_pct=round(max_weight * 100, 2),
        market_regime=regime,
        confidence=confidence,
        alerts=alerts,
    )



