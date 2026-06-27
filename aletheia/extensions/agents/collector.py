from __future__ import annotations

import asyncio
import logging

from aletheia.extensions.data.normalizer import normalize_holding
from aletheia.extensions.data.provider_base import MarketDataProvider
from aletheia.core.models import CollectorOutput, Holding

logger = logging.getLogger(__name__)


class CollectorAgent:
    def __init__(self, providers: list[MarketDataProvider]) -> None:
        self.providers = providers

    async def collect_for_holding(self, holding: Holding) -> CollectorOutput:
        normalized = normalize_holding(holding)
        warnings: list[str] = []
        provenance: list[dict[str, str]] = []

        for provider in self.providers:
            attempts = 3
            timeout_secs = 5.0
            quotes = []
            success = False

            for attempt in range(1, attempts + 1):
                try:
                    logger.info(
                        "CollectorAgent: Fetching quote for %s from %s (attempt %d/%d)",
                        normalized.symbol,
                        provider.name,
                        attempt,
                        attempts,
                    )
                    # Enforce timeout per request
                    quotes = await asyncio.wait_for(
                        provider.get_quote(normalized.symbol, normalized.exchange),
                        timeout=timeout_secs,
                    )
                    success = True
                    break  # Succeeded, break the retry loop
                except asyncio.TimeoutError:
                    logger.warning(
                        "CollectorAgent: Timeout (%.1fs) fetching quote for %s from %s on attempt %d/%d",
                        timeout_secs,
                        normalized.symbol,
                        provider.name,
                        attempt,
                        attempts,
                    )
                    # continue retrying
                except Exception as exc:
                    logger.warning(
                        "CollectorAgent: Error fetching quote for %s from %s on attempt %d/%d: %s",
                        normalized.symbol,
                        provider.name,
                        attempt,
                        attempts,
                        exc,
                        exc_info=True,
                    )
                    # continue retrying

                if attempt < attempts:
                    await asyncio.sleep(0.5)

            if success:
                if quotes:
                    logger.info(
                        "CollectorAgent: Successfully retrieved data for %s from %s",
                        normalized.symbol,
                        provider.name,
                    )
                    provenance.append({"provider": provider.name, "symbol": normalized.symbol})
                    return CollectorOutput(
                        symbol=normalized.symbol,
                        provider_used=provider.name,
                        quotes=quotes,
                        warnings=warnings,
                        provenance=provenance,
                    )
                else:
                    logger.debug(
                        "CollectorAgent: Provider %s returned no data for %s",
                        provider.name,
                        normalized.symbol,
                    )
            else:
                msg = f"{provider.name}: Failed after {attempts} attempts"
                warnings.append(msg)
                provenance.append({"provider": provider.name, "error": "Max retries exceeded"})
                
                # Log the fallback if there's another provider in the list
                next_index = self.providers.index(provider) + 1
                if next_index < len(self.providers):
                    next_provider = self.providers[next_index]
                    logger.warning(
                        "CollectorAgent: Falling back from %s to %s for symbol %s",
                        provider.name,
                        next_provider.name,
                        normalized.symbol,
                    )

        return CollectorOutput(
            symbol=normalized.symbol,
            provider_used="unavailable",
            quotes=[],
            warnings=warnings or ["No provider could return quote data"],
            provenance=provenance,
        )

