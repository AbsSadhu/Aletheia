from aletheia.core.models import AssetType, Holding, MarketQuote, Portfolio, TaxProfile
from aletheia.core.risk.metrics import assess_portfolio_risk


def test_assess_portfolio_risk_concentrated() -> None:
    portfolio = Portfolio(
        name="Risk",
        holdings=[
            Holding(
                symbol="RELIANCE",
                quantity=20,
                average_price=2500,
                asset_type=AssetType.EQUITY,
                exchange="NSE",
                tax_profile=TaxProfile.EQUITY,
            ),
            Holding(
                symbol="TCS",
                quantity=1,
                average_price=3700,
                asset_type=AssetType.EQUITY,
                exchange="NSE",
                tax_profile=TaxProfile.EQUITY,
            ),
        ],
    )
    quotes = {
        "RELIANCE": MarketQuote(
            symbol="RELIANCE", exchange="NSE", close=3000, open=2900, provider="seed"
        ),
        "TCS": MarketQuote(symbol="TCS", exchange="NSE", close=3900, open=3890, provider="seed"),
    }
    output = assess_portfolio_risk(portfolio, quotes)
    assert output.max_single_position_pct > 40
    assert output.alerts
