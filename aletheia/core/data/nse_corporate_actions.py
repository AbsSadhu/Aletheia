"""
NSE Corporate Actions Fetcher.

Source: NSE India corporate actions API (public JSON, no auth).
Caches per symbol per day to avoid hammering the endpoint.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

_NSE_CORP_ACTIONS_URL = (
    "https://www.nseindia.com/api/corporates-corporateActions"
    "?index=equities&symbol={symbol}"
)
_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}


@dataclass
class CorporateAction:
    symbol: str
    action_type: str          # "DIVIDEND" | "BONUS" | "SPLIT" | "RIGHTS" | "OTHER"
    ex_date: date | None
    description: str
    impact_pct_estimate: float | None = None  # estimated % impact on stock price


@dataclass
class _CacheEntry:
    actions: list[CorporateAction]
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_stale(self) -> bool:
        return datetime.now(UTC) - self.fetched_at > timedelta(hours=12)


_CACHE: dict[str, _CacheEntry] = {}


class NSECorporateActionsFetcher:
    """Fetch and parse corporate actions for an NSE equity symbol."""

    async def fetch(self, symbol: str) -> list[CorporateAction]:
        """Return cached or freshly fetched corporate actions."""
        symbol = symbol.upper()
        if symbol in _CACHE and not _CACHE[symbol].is_stale():
            return _CACHE[symbol].actions

        actions = await self._fetch_from_nse(symbol)
        _CACHE[symbol] = _CacheEntry(actions=actions)
        return actions

    async def _fetch_from_nse(self, symbol: str) -> list[CorporateAction]:
        url = _NSE_CORP_ACTIONS_URL.format(symbol=symbol)
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=_NSE_HEADERS)
                resp.raise_for_status()
                data = resp.json()

            raw_actions = data if isinstance(data, list) else data.get("data", [])
            actions: list[CorporateAction] = []

            for item in raw_actions[:20]:
                action = self._parse_action(symbol, item)
                if action:
                    actions.append(action)
            return actions

        except Exception as exc:
            logger.warning("NSECorporateActionsFetcher: fetch failed for %s: %s", symbol, exc)
            return []

    def _parse_action(self, symbol: str, item: dict) -> CorporateAction | None:
        try:
            desc = item.get("subject") or item.get("corporateActionDesc") or ""
            ex_date_str = item.get("exDate") or item.get("exDt") or ""
            action_type = self._classify_action(desc)
            ex_date = None
            if ex_date_str:
                for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                    try:
                        ex_date = datetime.strptime(ex_date_str, fmt).date()
                        break
                    except ValueError:
                        continue
            return CorporateAction(
                symbol=symbol,
                action_type=action_type,
                ex_date=ex_date,
                description=desc[:200],
                impact_pct_estimate=self._estimate_impact(action_type, desc),
            )
        except Exception:
            return None

    def _classify_action(self, desc: str) -> str:
        d = desc.lower()
        if "dividend" in d or "div" in d:
            return "DIVIDEND"
        if "bonus" in d:
            return "BONUS"
        if "split" in d or "sub-division" in d:
            return "SPLIT"
        if "rights" in d or "right issue" in d:
            return "RIGHTS"
        return "OTHER"

    def _estimate_impact(self, action_type: str, desc: str) -> float | None:
        """Rough heuristic for price impact estimation."""
        if action_type == "SPLIT":
            # Split is neutral theoretically, minor short-term positive
            return 0.0
        if action_type == "DIVIDEND":
            # On ex-date, stock drops ~= dividend amount — hard to estimate without amount
            return None
        if action_type == "BONUS":
            return 0.0  # Bonus is net neutral (proportional)
        return None
