from datetime import UTC, datetime, timedelta

from aletheia.extensions.backtest.scenario import build_scenario
from aletheia.core.models import AssetType, Holding, MarketQuote, TaxProfile


def _quote(as_of: datetime | None = None) -> MarketQuote:
    return MarketQuote(
        symbol="RELIANCE",
        exchange="NSE",
        close=2920.0,
        open=2890.0,
        high=2950.0,
        low=2880.0,
        volume=1000,
        as_of=as_of or datetime.now(UTC),
        provider="static_seed",
    )


def test_scenario_uses_long_term_rate_for_old_acquisition() -> None:
    now = datetime.now(UTC)
    holding = Holding(
        symbol="RELIANCE",
        quantity=5,
        average_price=2500,
        asset_type=AssetType.EQUITY,
        tax_profile=TaxProfile.EQUITY,
        acquisition_date=now - timedelta(days=400),
    )
    output = build_scenario(holding, _quote(now), conviction=0.5)
    assert output.scenario.tax_summary.term == "long"


def test_scenario_uses_short_term_rate_for_recent_acquisition() -> None:
    now = datetime.now(UTC)
    holding = Holding(
        symbol="RELIANCE",
        quantity=5,
        average_price=2500,
        asset_type=AssetType.EQUITY,
        tax_profile=TaxProfile.EQUITY,
        acquisition_date=now - timedelta(days=30),
    )
    output = build_scenario(holding, _quote(now), conviction=0.5)
    assert output.scenario.tax_summary.term == "short"


def test_scenario_without_acquisition_date_falls_back_to_short_term() -> None:
    holding = Holding(
        symbol="RELIANCE",
        quantity=5,
        average_price=2500,
        asset_type=AssetType.EQUITY,
        tax_profile=TaxProfile.EQUITY,
    )
    output = build_scenario(holding, _quote(), conviction=0.5)
    assert output.scenario.tax_summary.term == "short"
