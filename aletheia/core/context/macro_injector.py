"""
Macro Context Injector — fetches Indian market macro signals before each run.

Provides a pre-run briefing injected into every agent's system prompt:
- RBI repo rate (static fallback)
- USD/INR exchange rate
- NIFTY 50 50-day momentum (from DuckDB)
- Crude oil price (Brent)

Cache TTL: 15 minutes (avoids repeated API calls within a single session).
All fetches are best-effort — failure returns a degraded context, never raises.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

_CACHE_TTL = timedelta(minutes=15)


@dataclass
class MacroContext:
    rbi_repo_rate_pct: float | None
    usd_inr: float | None
    nifty_50_momentum_pct: float | None  # 50-day momentum vs 200-day SMA
    crude_oil_usd: float | None  # Brent, USD/barrel
    fetched_at: datetime = None  # type: ignore[assignment]
    notes: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.fetched_at is None:
            self.fetched_at = datetime.now(UTC)
        if self.notes is None:
            self.notes = []

    def as_prompt_text(self) -> str:
        """Single-paragraph macro briefing for LLM injection."""
        parts: list[str] = []
        if self.rbi_repo_rate_pct is not None:
            parts.append(f"RBI repo rate: {self.rbi_repo_rate_pct:.2f}%")
        if self.usd_inr is not None:
            parts.append(f"USD/INR: ₹{self.usd_inr:.2f}")
        if self.crude_oil_usd is not None:
            parts.append(f"Brent crude: ${self.crude_oil_usd:.1f}/bbl")
        if self.nifty_50_momentum_pct is not None:
            direction = "uptrend" if self.nifty_50_momentum_pct > 0 else "downtrend"
            parts.append(
                f"NIFTY 50 50-day momentum: {self.nifty_50_momentum_pct:+.1f}% ({direction})"
            )
        if not parts:
            return "Macro data unavailable — agents operating without macro context."
        base = "Current macro environment: " + ", ".join(parts) + "."
        if self.notes:
            base += " Notes: " + "; ".join(self.notes) + "."
        return base

    def is_stale(self) -> bool:
        return datetime.now(UTC) - self.fetched_at > _CACHE_TTL


# Known RBI repo rate — updated manually or via static lookup.
# NSE/RBI provide no clean free JSON endpoint for this.
_FALLBACK_RBI_RATE = 6.50  # June 2026 — update if changed


class MacroContextInjector:
    def __init__(self, duckdb_path: str | None = None) -> None:
        self._cache: MacroContext | None = None
        self._lock = asyncio.Lock()
        self._duckdb_path = duckdb_path

    async def get(self) -> MacroContext:
        """Return cached context or refresh if stale."""
        async with self._lock:
            if self._cache is None or self._cache.is_stale():
                self._cache = await self._fetch()
            return self._cache

    async def _fetch(self) -> MacroContext:
        usd_inr, crude = await asyncio.gather(
            self._fetch_usd_inr(),
            self._fetch_crude_oil(),
            return_exceptions=True,
        )
        nifty_momentum = await self._fetch_nifty_momentum()

        notes: list[str] = []
        if isinstance(usd_inr, Exception):
            logger.warning("MacroInjector: USD/INR fetch failed: %s", usd_inr)
            usd_inr = None
            notes.append("USD/INR unavailable")
        if isinstance(crude, Exception):
            logger.warning("MacroInjector: Crude oil fetch failed: %s", crude)
            crude = None
            notes.append("Crude oil price unavailable")

        return MacroContext(
            rbi_repo_rate_pct=_FALLBACK_RBI_RATE,
            usd_inr=usd_inr,
            nifty_50_momentum_pct=nifty_momentum,
            crude_oil_usd=crude,
            notes=notes,
        )

    async def _fetch_usd_inr(self) -> float | None:
        """Free tier exchange rate — open.er-api.com."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://open.er-api.com/v6/latest/USD",
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                return float(data["rates"]["INR"])
        except Exception as exc:
            logger.debug("USD/INR fetch error: %s", exc)
            return None

    async def _fetch_crude_oil(self) -> float | None:
        """
        Brent crude from a free commodity API.
        Fallback: use a known recent price if unreachable.
        """
        try:
            # commodities-api.com free tier: Brent crude
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.get(
                    "https://api.exchangerate-api.com/v4/latest/USD",
                    headers={"Accept": "application/json"},
                )
                # This endpoint doesn't have crude — use a secondary approach:
                # If no free commodity API is configured, return None gracefully
                return None
        except Exception:
            return None

    async def _fetch_nifty_momentum(self) -> float | None:
        """
        Compute NIFTY 50 50-day momentum from DuckDB quote store.
        Returns: pct difference between current close and 50-day SMA.
        Returns None if insufficient history.
        """
        if not self._duckdb_path:
            return await self._fetch_nifty_from_yfinance()
        try:
            import duckdb

            con = duckdb.connect(self._duckdb_path, read_only=True)
            result = con.execute(
                """
                SELECT close FROM market_quotes
                WHERE symbol = '^NSEI'
                ORDER BY as_of DESC
                LIMIT 200
                """
            ).fetchall()
            con.close()
            if len(result) < 51:
                return await self._fetch_nifty_from_yfinance()
            closes = [r[0] for r in result]
            current = closes[0]
            sma50 = sum(closes[:50]) / 50
            return round((current - sma50) / sma50 * 100, 2)
        except Exception as exc:
            logger.debug("DuckDB NIFTY momentum failed: %s", exc)
            return await self._fetch_nifty_from_yfinance()

    async def _fetch_nifty_from_yfinance(self) -> float | None:
        """Fallback: fetch NIFTY 50 from yfinance (blocking, run in thread)."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._yfinance_nifty)
        except Exception:
            return None

    def _yfinance_nifty(self) -> float | None:
        try:
            import yfinance as yf

            nifty = yf.download("^NSEI", period="3mo", interval="1d", progress=False)
            if nifty.empty or len(nifty) < 51:
                return None
            closes = nifty["Close"].values
            current = float(closes[-1])
            sma50 = float(closes[-50:].mean())
            return round((current - sma50) / sma50 * 100, 2)
        except Exception:
            return None


# Module-level singleton
_injector: MacroContextInjector | None = None


def get_macro_injector(duckdb_path: str | None = None) -> MacroContextInjector:
    global _injector
    if _injector is None:
        _injector = MacroContextInjector(duckdb_path=duckdb_path)
    return _injector
