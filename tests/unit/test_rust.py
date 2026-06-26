from aletheia.core.models import AssetType, Holding, MarketQuote, Portfolio, TaxProfile
import aletheia_rust


def test_rust_portfolio_risk() -> None:
    portfolio = Portfolio(
        name="Rust Test Port",
        holdings=[
            Holding(
                symbol="RELIANCE",
                quantity=10,
                average_price=2500,
                asset_type=AssetType.EQUITY,
                exchange="NSE",
                tax_profile=TaxProfile.EQUITY,
            ),
            Holding(
                symbol="TCS",
                quantity=5,
                average_price=3700,
                asset_type=AssetType.EQUITY,
                exchange="NSE",
                tax_profile=TaxProfile.EQUITY,
            ),
        ],
    )
    quotes = {
        "RELIANCE": MarketQuote(symbol="RELIANCE", exchange="NSE", close=3000, open=2900, provider="seed"),
        "TCS": MarketQuote(symbol="TCS", exchange="NSE", close=3900, open=3800, provider="seed"),
    }

    res = aletheia_rust.assess_portfolio_risk_rust(portfolio, quotes)
    
    # Assert correct keys in returned dictionary
    assert "portfolio_var_95" in res
    assert "concentration_risk" in res
    assert "max_single_position_pct" in res
    assert "market_regime" in res
    assert "confidence" in res
    assert "alerts" in res

    # Check approximate outputs
    assert res["max_single_position_pct"] > 0.0
    assert res["portfolio_var_95"] < 0.0


def test_rust_tax_summary() -> None:
    res = aletheia_rust.build_tax_summary_rust("fno", 100000.0)
    assert res["tax_profile"] == "fno"
    assert res["pre_tax_profit"] == 100000.0
    assert res["tax_drag_pct"] == 17.5
    assert res["estimated_tax_amount"] == 17500.0
    assert res["post_tax_profit"] == 82500.0


def test_rust_scenario() -> None:
    holding = Holding(
        symbol="INFY",
        quantity=8,
        average_price=1500,
        asset_type=AssetType.EQUITY,
        exchange="NSE",
        tax_profile=TaxProfile.EQUITY,
    )
    quote = MarketQuote(symbol="INFY", exchange="NSE", close=1600, open=1580, provider="seed")
    conviction = 0.8

    res = aletheia_rust.build_scenario_rust(holding, quote, conviction)
    assert res["symbol"] == "INFY"
    assert "scenario" in res
    scenario = res["scenario"]
    assert "projected_return_pct" in scenario
    assert "projected_post_tax_return_pct" in scenario
    assert "projected_sharpe" in scenario
    assert "tax_summary" in scenario
