from aletheia.extensions.agents.collector import CollectorAgent
from aletheia.extensions.data.providers.static_seed import StaticSeedProvider
from aletheia.core.models import AssetType, Holding, TaxProfile


async def test_collector_uses_seed_provider() -> None:
    agent = CollectorAgent([StaticSeedProvider()])
    output = await agent.collect_for_holding(
        Holding(
            symbol="RELIANCE",
            quantity=10,
            average_price=2500,
            asset_type=AssetType.EQUITY,
            tax_profile=TaxProfile.EQUITY,
        )
    )

    assert output.provider_used == "static_seed"
    assert output.quotes

