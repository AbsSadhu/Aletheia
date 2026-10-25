"""Free, no-account quotes polled from BSE's public website API (UNOFFICIAL).

Endpoints (the same ones the open-source `bshada/nse-bse-api` library uses):
  GET https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w?scripcode=500325
      -> {"CurrRate": {"LTP", "Chg", "PcChg"}, "Header": {"LTP", "PrevClose", "Open", "High", "Low",
          "Ason": "23 Oct 26 | 16:00", ...}}
  GET https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?segment=Equity&status=Active
      -> every active equity with its numeric scrip code and `scrip_id` (usually the NSE ticker)

HONEST LIMITS
  - Unofficial. BSE can change or block it, and its terms may restrict automated access; this is
    rate-limited (<= 8 requests/s overall, the limit that library also uses) and backs off on
    errors, but it carries no guarantee.
  - It is a polling loop (default every 2 s), not a push stream. About 1-3 s freshness, never 'tick'.
  - Prices are BSE prices. For large caps they track NSE within paise; for thin stocks they can differ.
  - Whether BSE's public data is real-time or delayed during market hours is not guaranteed, so each
    quote carries the exchange's own 'as on' time and the lag against our clock, and the UI shows it.
  - Volume is not in this response.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from aletheia.core.events.bus import EventBus, Topics
from aletheia.core.marketdata.hours import market_status

logger = logging.getLogger(__name__)

API = "https://api.bseindia.com/BseIndiaAPI/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/118.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.bseindia.com/",
    "Referer": "https://www.bseindia.com/",
}
SCRIP_LIST_PATH = Path.home() / ".aletheia" / "bse_scrips.json"
SCRIP_LIST_MAX_AGE_SECS = 24 * 3600
_IST = timedelta(hours=5, minutes=30)
MAX_REQUESTS_PER_SEC = 8.0
CONCURRENCY = 4
# Anything older than this during market hours is reported as lagging data, not live data.
LAG_WARN_SECS = 180.0


def parse_ason(text: Any) -> datetime | None:
    """'23 Oct 26 | 16:00' (IST, minute resolution) -> aware UTC datetime."""
    if not isinstance(text, str):
        return None
    try:
        naive = datetime.strptime(text.strip(), "%d %b %y | %H:%M")
    except ValueError:
        return None
    return (naive - _IST).replace(tzinfo=UTC)


def _num(v: Any) -> float | None:
    try:
        f = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def parse_quote(
    payload: dict[str, Any],
    symbol: str,
    exchange: str,
    received: datetime,
    market_open: bool,
) -> dict[str, Any] | None:
    header = payload.get("Header") or {}
    curr = payload.get("CurrRate") or {}
    ltp = _num(header.get("LTP")) or _num(curr.get("LTP"))
    if ltp is None or ltp <= 0:
        return None
    prev = _num(header.get("PrevClose"))
    pct = _num(curr.get("PcChg"))
    exch_time = parse_ason(header.get("Ason"))
    lag = None
    if exch_time is not None and market_open:
        lag = max((received - exch_time).total_seconds(), 0.0)
    return {
        "symbol": symbol,
        "exchange": exchange,  # the row the user is watching
        "price_exchange": "BSE",  # but the price itself is BSE's
        "currency": "INR",
        "close": ltp,  # MarketQuote convention: `close` is the latest price
        "open": _num(header.get("Open")),
        "high": _num(header.get("High")),
        "low": _num(header.get("Low")),
        "volume": None,
        "prev_close": prev,
        "change_pct": round(pct, 2)
        if pct is not None
        else (round((ltp / prev - 1) * 100, 2) if prev else None),
        "as_of": received.isoformat(),  # when WE fetched it, so the UI's age shows feed liveness
        "exchange_time": exch_time.isoformat() if exch_time else None,
        "data_lag_secs": round(lag, 0) if lag is not None else None,
        "provider": "bse_web",
        "stream": True,
        "price_scale_verified": True,
    }


async def load_bse_scrips(
    path: Path = SCRIP_LIST_PATH, client: httpx.AsyncClient | None = None
) -> dict[str, str]:
    """{SCRIP_ID: scrip code} for all active BSE equities, cached for a day."""
    fresh = path.exists() and time.time() - path.stat().st_mtime < SCRIP_LIST_MAX_AGE_SECS
    if fresh:
        rows = json.loads(path.read_text(encoding="utf-8"))
    else:
        own = client is None
        http = client or httpx.AsyncClient(headers=HEADERS, timeout=30.0)
        try:
            resp = await http.get(
                f"{API}/ListofScripData/w",
                params={
                    "Group": "",
                    "Scripcode": "",
                    "industry": "",
                    "segment": "Equity",
                    "status": "Active",
                },
            )
            resp.raise_for_status()
            rows = resp.json()
        finally:
            if own:
                await http.aclose()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows), encoding="utf-8")
    out: dict[str, str] = {}
    for row in rows:
        sid, code = str(row.get("scrip_id", "")).upper(), str(row.get("SCRIP_CD", ""))
        if sid and code:
            out.setdefault(sid, code)  # first listing wins on a duplicate id
    return out


class BseWebStream:
    label = "BSE website"

    def __init__(
        self,
        bus: EventBus,
        poll_secs: float = 2.0,
        idle_poll_secs: float = 60.0,
        client: httpx.AsyncClient | None = None,
        clock: Any = None,
        max_rps: float = MAX_REQUESTS_PER_SEC,
    ) -> None:
        self.bus = bus
        self.poll_secs = max(poll_secs, 1.0)  # never hammer: 1 s is the floor
        self.idle_poll_secs = idle_poll_secs
        self._client = client
        self._clock = clock or (lambda: datetime.now(UTC))
        self._gap = 1.0 / max_rps

        self._wanted: dict[str, tuple[str, str]] = {}  # scrip code -> (SYMBOL, EXCHANGE of the row)
        self._stop = asyncio.Event()
        self._gate = asyncio.Lock()
        self._next_slot = 0.0
        self._failures = 0
        self._penalty = 0.0

        self.connected = False
        self.last_error: str | None = None
        self.last_tick_at: float | None = None
        self.ticks_total = 0
        self.reconnects = 0
        self.max_lag_secs: float | None = None
        self.last_quotes: dict[tuple[str, str], dict[str, Any]] = {}

    # -- public ---------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        age = None if self.last_tick_at is None else round(time.time() - self.last_tick_at, 1)
        return {
            "connected": self.connected,
            "symbols": len(self._wanted),
            "ticks": self.ticks_total,
            "last_tick_age_secs": age,
            "reconnects": self.reconnects,
            "price_scale_verified": True,
            "data_lag_secs": self.max_lag_secs,
            "poll_secs": self.poll_secs,
            "unofficial": True,
            "error": self.last_error,
        }

    def covers(self, symbol: str, exchange: str) -> bool:
        return any(
            sym == symbol.upper() and exch == exchange.upper()
            for sym, exch in self._wanted.values()
        )

    async def set_symbols(self, mapping: dict[tuple[str, str], str]) -> None:
        """mapping: {(EXCHANGE, SYMBOL): BSE scrip code}."""
        self._wanted = {code: (sym.upper(), exch.upper()) for (exch, sym), code in mapping.items()}

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            state = market_status()["state"]
            interval = self.poll_secs if state in ("open", "pre_open") else self.idle_poll_secs
            started = time.monotonic()
            with contextlib.suppress(Exception):
                await self.poll_once()
            wait = max(interval - (time.monotonic() - started), 0.0) + self._penalty
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=wait)

    # -- polling --------------------------------------------------------------------

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(headers=HEADERS, timeout=10.0)
        return self._client

    async def _throttle(self) -> None:
        """Global request spacing: no more than max_rps starts per second, whatever the symbol count."""
        async with self._gate:
            now = time.monotonic()
            wait = self._next_slot - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_slot = max(now, self._next_slot) + self._gap

    async def _fetch(self, code: str, symbol: str, exchange: str, sem: asyncio.Semaphore) -> bool:
        async with sem:
            await self._throttle()
            http = await self._http()
            try:
                resp = await http.get(f"{API}/getScripHeaderData/w", params={"scripcode": code})
            except httpx.HTTPError as exc:
                self.last_error = f"BSE request failed: {type(exc).__name__}"
                return False
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                self.last_error = (
                    f"BSE refused or limited the request (HTTP {resp.status_code}); backing off."
                )
                return False
            try:
                payload = resp.json()
            except ValueError:
                self.last_error = "BSE returned a non-JSON response."
                return False
        received = self._clock()
        quote = parse_quote(
            payload, symbol, exchange, received, bool(market_status(received)["is_open"])
        )
        if quote is None:
            return False
        self.ticks_total += 1
        self.last_tick_at = time.time()
        lag = quote["data_lag_secs"]
        if lag is not None:
            self.max_lag_secs = lag if self.max_lag_secs is None else max(lag, self.max_lag_secs)
        self.last_quotes[(symbol, exchange)] = quote
        await self.bus.emit(Topics.MARKET_QUOTE, quote, source="bse_web")
        return True

    async def poll_once(self) -> int:
        """One pass over the watchlist. Returns how many quotes were published."""
        targets = [(code, sym, exch) for code, (sym, exch) in self._wanted.items()]
        if not targets:
            return 0
        self.max_lag_secs = None
        sem = asyncio.Semaphore(CONCURRENCY)
        results = await asyncio.gather(*(self._fetch(c, s, e, sem) for c, s, e in targets))
        ok = sum(results)
        if ok:
            if self._failures:
                self.reconnects += 1  # recovered after failing
            self.connected = True
            self._failures = 0
            self._penalty = 0.0
            if ok == len(targets):
                self.last_error = None
        else:
            self._failures += 1
            self._penalty = min(2.0**self._failures, 60.0)  # exponential, capped at a minute
            if self._failures >= 3:
                self.connected = False  # the poller falls back to the delayed feed
        return ok
