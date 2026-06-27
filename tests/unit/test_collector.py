from aletheia.extensions.agents.collector import CollectorAgent
from aletheia.extensions.data.providers.static_seed import StaticSeedProvider
from aletheia.core.models import AssetType, Holding, TaxProfile
from aletheia.extensions.data.provider_base import MarketDataProvider
from aletheia.core.models import MarketQuote
import pytest
import asyncio


class DummyFailingProvider(MarketDataProvider):
    name = "dummy_failing"

    def __init__(self, raises_timeout: bool = False):
        self.raises_timeout = raises_timeout
        self.call_count = 0

    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        self.call_count += 1
        if self.raises_timeout:
            raise asyncio.TimeoutError()
        raise ValueError("Connection failed")


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


async def test_collector_fallback_on_failure() -> None:
    failing_provider = DummyFailingProvider(raises_timeout=False)
    success_provider = StaticSeedProvider()

    agent = CollectorAgent([failing_provider, success_provider])
    output = await agent.collect_for_holding(
        Holding(
            symbol="RELIANCE",
            quantity=10,
            average_price=2500,
            asset_type=AssetType.EQUITY,
            tax_profile=TaxProfile.EQUITY,
        )
    )

    assert failing_provider.call_count == 3
    assert output.provider_used == "static_seed"
    assert output.quotes
    assert any(p.get("provider") == "dummy_failing" and "error" in p for p in output.provenance)


async def test_collector_fallback_on_timeout() -> None:
    timeout_provider = DummyFailingProvider(raises_timeout=True)
    success_provider = StaticSeedProvider()

    agent = CollectorAgent([timeout_provider, success_provider])
    output = await agent.collect_for_holding(
        Holding(
            symbol="RELIANCE",
            quantity=10,
            average_price=2500,
            asset_type=AssetType.EQUITY,
            tax_profile=TaxProfile.EQUITY,
        )
    )

    assert timeout_provider.call_count == 3
    assert output.provider_used == "static_seed"
    assert output.quotes

