from __future__ import annotations

from aletheia.extensions.data.normalizer import normalize_holding
from aletheia.extensions.data.provider_base import MarketDataProvider
from aletheia.core.models import CollectorOutput, Holding


class CollectorAgent:
    def __init__(self, providers: list[MarketDataProvider]) -> None:
        self.providers = providers

    async def collect_for_holding(self, holding: Holding) -> CollectorOutput:
        normalized = normalize_holding(holding)
        warnings: list[str] = []
        provenance: list[dict[str, str]] = []

        for provider in self.providers:
            try:
                quotes = await provider.get_quote(normalized.symbol, normalized.exchange)
                provenance.append({"provider": provider.name, "symbol": normalized.symbol})
                if quotes:
                    return CollectorOutput(
                        symbol=normalized.symbol,
                        provider_used=provider.name,
                        quotes=quotes,
                        warnings=warnings,
                        provenance=provenance,
                    )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{provider.name}: {exc}")
                provenance.append({"provider": provider.name, "error": str(exc)})

        return CollectorOutput(
            symbol=normalized.symbol,
            provider_used="unavailable",
            quotes=[],
            warnings=warnings or ["No provider could return quote data"],
            provenance=provenance,
        )


