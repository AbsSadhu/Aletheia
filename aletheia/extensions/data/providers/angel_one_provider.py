"""Angel One SmartAPI REST quotes (free with an Angel One account).

REST is the fallback and the one-off path used by analysis runs; the per-second live feed is
`aletheia.extensions.data.angel_stream`. Both share one login (`angel_session`).

  - POST /rest/secure/angelbroking/market/v1/quote   (mode FULL, exchangeTokens)
Symbol -> instrument token comes from Angel One's public scrip master, cached on disk.

Enable with ALETHEIA_ANGEL_ONE_ENABLED=true. A failed login or quote returns [] so the collector
falls through to the next provider (yfinance) rather than failing the run.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from aletheia.core.models import MarketQuote
from aletheia.extensions.data.angel_session import (
    LOGIN_PATH,
    AngelOneSession,
    totp_now,
)
from aletheia.extensions.data.provider_base import MarketDataProvider

logger = logging.getLogger(__name__)

__all__ = ["AngelOneProvider", "LOGIN_PATH", "QUOTE_PATH", "totp_now", "load_scrip_tokens"]

QUOTE_PATH = "/rest/secure/angelbroking/market/v1/quote"
SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)
SCRIP_MASTER_MAX_AGE_SECS = 24 * 3600
_EXCHANGE_SEGMENTS = {"NSE": "NSE", "BSE": "BSE"}
DEFAULT_SCRIP_PATH = Path.home() / ".aletheia" / "angel_scrips.json"


async def load_scrip_tokens(path: Path = DEFAULT_SCRIP_PATH) -> dict[tuple[str, str], str]:
    """{(exchange, SYMBOL): instrument token} for NSE/BSE cash equities, cached for a day."""
    fresh = path.exists() and time.time() - path.stat().st_mtime < SCRIP_MASTER_MAX_AGE_SECS
    if fresh:
        rows = json.loads(path.read_text(encoding="utf-8"))
    else:
        async with httpx.AsyncClient(timeout=60.0) as dl:
            resp = await dl.get(SCRIP_MASTER_URL)
            resp.raise_for_status()
            rows = resp.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows), encoding="utf-8")
    tokens: dict[tuple[str, str], str] = {}
    for row in rows:
        sym, seg = str(row.get("symbol", "")), row.get("exch_seg")
        if seg in _EXCHANGE_SEGMENTS and sym.endswith("-EQ"):
            tokens[(seg, sym.removesuffix("-EQ").upper())] = str(row["token"])
    return tokens


class AngelOneProvider(MarketDataProvider):
    name = "angel_one"

    def __init__(
        self,
        credentials: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        scrip_master_path: Path | None = None,
        session: AngelOneSession | None = None,
    ) -> None:
        self.session = session or AngelOneSession(credentials, client)
        self._scrip_path = scrip_master_path or DEFAULT_SCRIP_PATH
        self._tokens: dict[tuple[str, str], str] | None = None

    @classmethod
    def check_available(cls, settings: Any) -> bool:
        return bool(getattr(settings, "angel_one_enabled", False))

    async def _load_scrips(self) -> dict[tuple[str, str], str]:
        if self._tokens is None:
            self._tokens = await load_scrip_tokens(self._scrip_path)
        return self._tokens

    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        exch = exchange.upper()
        if exch not in _EXCHANGE_SEGMENTS:
            return []
        creds = self.session.credentials()
        if creds is None:
            logger.debug("AngelOneProvider: credentials not configured.")
            return []
        base = symbol.upper().split(".")[0]
        try:
            token = (await self._load_scrips()).get((exch, base))
            if token is None:
                return []
            body: dict[str, Any] = {}
            for attempt in (1, 2):
                if not await self.session.ensure():
                    return []
                http = await self.session.http()
                resp = await http.post(
                    QUOTE_PATH,
                    headers=self.session.headers(creds["api_key"], self.session.jwt),
                    json={"mode": "FULL", "exchangeTokens": {exch: [token]}},
                )
                body = resp.json()
                if body.get("status"):
                    break
                self.session.invalidate()  # expired/invalid session: log in again once
                if attempt == 2:
                    logger.warning("AngelOneProvider: quote failed: %s", body.get("message"))
                    return []
            fetched = (body.get("data") or {}).get("fetched") or []
            if not fetched:
                return []
            q = fetched[0]
            ltp = float(q["ltp"])
            return [
                MarketQuote(
                    symbol=base,
                    exchange=exch,
                    close=ltp,
                    open=float(q.get("open") or ltp),
                    high=float(q.get("high") or ltp),
                    low=float(q.get("low") or ltp),
                    volume=float(q.get("tradeVolume") or 0.0),
                    as_of=datetime.now(UTC),
                    provider=self.name,
                )
            ]
        except Exception as exc:
            logger.warning("AngelOneProvider: %s/%s failed: %s", exch, base, exc)
            return []
