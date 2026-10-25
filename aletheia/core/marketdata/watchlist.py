"""The user's saved watchlist: which symbols the live feed follows.

Plain JSON on disk (small, human-editable, survives a database reset).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

MAX_ITEMS = 100
VALID_EXCHANGES = {"NSE", "BSE", "BINANCE"}
_SYMBOL = re.compile(r"^[A-Z0-9&\-./]{1,20}$")

DEFAULT_ITEMS: list[tuple[str, str]] = [
    ("RELIANCE", "NSE"),
    ("TCS", "NSE"),
    ("INFY", "NSE"),
    ("HDFCBANK", "NSE"),
    ("ICICIBANK", "NSE"),
    ("SBIN", "NSE"),
    ("BTC/USDT", "BINANCE"),
]


class WatchItem(BaseModel):
    symbol: str
    exchange: str = "NSE"

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, v: str) -> str:
        v = v.strip().upper()
        if not _SYMBOL.match(v):
            raise ValueError(f"Invalid symbol {v!r}")
        return v

    @field_validator("exchange")
    @classmethod
    def _exchange(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in VALID_EXCHANGES:
            raise ValueError(f"Exchange must be one of {sorted(VALID_EXCHANGES)}")
        return v


class WatchlistStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def items(self) -> list[tuple[str, str]]:
        if not self.path.exists():
            return list(DEFAULT_ITEMS)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return [(i.symbol, i.exchange) for i in (WatchItem(**r) for r in raw)]
        except (ValueError, KeyError, TypeError, OSError) as exc:
            logger.warning("Watchlist file unreadable (%s); using defaults.", exc)
            return list(DEFAULT_ITEMS)

    def save(self, items: list[WatchItem]) -> list[tuple[str, str]]:
        seen: set[tuple[str, str]] = set()
        unique = []
        for it in items:
            key = (it.symbol, it.exchange)
            if key not in seen:
                seen.add(key)
                unique.append(it)
        if len(unique) > MAX_ITEMS:
            raise ValueError(f"A watchlist holds at most {MAX_ITEMS} symbols.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([i.model_dump() for i in unique], indent=1), encoding="utf-8"
        )
        return [(i.symbol, i.exchange) for i in unique]
