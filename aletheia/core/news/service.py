"""NewsService: keeps a rolling window of scored, symbol-tagged headlines and derives the
market mood, a per-symbol sentiment tracker, and the day's movers with the headlines that
were published around them.

A "driver" is a headline that mentions the symbol. It is reported next to the move, not proven
to have caused it; the API says so in its `note` field.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from aletheia.core.news.feeds import RawItem, fetch_all
from aletheia.core.news.sentiment import label_for, score_headline
from aletheia.core.news.store import NewsAlertStore

FetchFn = Callable[[], Awaitable[tuple[list[RawItem], dict[str, bool]]]]

KEEP_HOURS = 36
MOOD_WINDOW_HOURS = 6
MOOD_HALF_LIFE_HOURS = 3.0
DRIVER_WINDOW_HOURS = 24

# Sentiment-flip alerts for watched symbols. A symbol's state is the recency-weighted tone of its
# recent headlines; it changes only when the score crosses ENTER, and returns to neutral only when
# it falls inside EXIT, so a score hovering near a line does not flap.
FLIP_WINDOW_HOURS = 12
FLIP_ENTER = 0.2
FLIP_EXIT = 0.1
FLIP_MIN_MENTIONS = 2

# Company and index names as they appear in headlines. Watchlist symbols not listed here are
# matched by their own ticker.
ALIASES: dict[str, list[str]] = {
    "RELIANCE": ["reliance", "ril", "mukesh ambani"],
    "TCS": ["tcs", "tata consultancy"],
    "INFY": ["infosys", "infy"],
    "HDFCBANK": ["hdfc bank", "hdfcbank"],
    "ICICIBANK": ["icici bank", "icicibank"],
    "SBIN": ["sbi", "state bank of india"],
    "ITC": ["itc"],
    "WIPRO": ["wipro"],
    "LT": ["larsen", "l&t"],
    "BHARTIARTL": ["airtel", "bharti airtel"],
    "KOTAKBANK": ["kotak mahindra", "kotak bank"],
    "AXISBANK": ["axis bank"],
    "MARUTI": ["maruti"],
    "TATAMOTORS": ["tata motors"],
    "TATASTEEL": ["tata steel"],
    "ADANIENT": ["adani enterprises", "adani"],
    "SUNPHARMA": ["sun pharma"],
    "BAJFINANCE": ["bajaj finance"],
    "HINDUNILVR": ["hindustan unilever", "hul"],
    "ONGC": ["ongc"],
    "NTPC": ["ntpc"],
    "POWERGRID": ["power grid"],
    "COALINDIA": ["coal india"],
    "TITAN": ["titan"],
    "ASIANPAINT": ["asian paints"],
    "ULTRACEMCO": ["ultratech"],
    "HCLTECH": ["hcl tech", "hcltech"],
    "TECHM": ["tech mahindra"],
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "ether"],
    "NIFTY": ["nifty"],
    "SENSEX": ["sensex"],
    "BANKNIFTY": ["bank nifty"],
}


# Feeds that carry general news alongside markets. Their items must look market related to be kept.
GENERAL_SOURCES = {"NDTV Profit"}
_MARKET_TERMS = re.compile(
    r"(?<![a-z0-9])(stock|stocks|share|shares|sensex|nifty|market|markets|rupee|rbi|sebi|ipo|bank|banks|"
    r"profit|earnings|results|q[1-4]|dividend|buyback|crude|oil|gold|silver|fed|bitcoin|crypto|inflation|gdp|"
    r"economy|budget|gst|tax|bond|yield|fii|fpi|dii|etf|mutual fund|brokerage|target price|rally|selloff|"
    r"downgrade|upgrade|merger|acquisition|deal|order win|investors?|trading|trader|futures|options|rates?)(?![a-z0-9])"
)


def is_market_related(title: str, source: str, aliases: list[list[str]]) -> bool:
    """General-news feeds are filtered; market-specific feeds are trusted as they are."""
    if source not in GENERAL_SOURCES:
        return True
    lowered = title.lower()
    if _MARKET_TERMS.search(lowered):
        return True
    return any(_pattern(a).search(lowered) for names in aliases for a in names)


@dataclass
class Headline:
    id: str
    title: str
    source: str
    url: str
    published: str
    score: float
    label: str
    symbols: list[str]
    published_dt: datetime = field(repr=False, default_factory=lambda: datetime.now(timezone.utc))

    def public(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("published_dt")
        return d


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def _base_symbol(symbol: str) -> str:
    """BTC/USDT -> BTC, RELIANCE.NS -> RELIANCE."""
    return re.split(r"[/.\-:]", symbol.upper())[0]


def _pattern(alias: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])")


class NewsService:
    def __init__(
        self,
        fetch: FetchFn | None = None,
        ttl_seconds: float = 20.0,
        store: NewsAlertStore | None = None,
    ) -> None:
        self._fetch: FetchFn = fetch or fetch_all
        self._ttl = ttl_seconds
        self._items: dict[str, Headline] = {}
        self._last: datetime | None = None
        self._sources: dict[str, bool] = {}
        self._history: deque[tuple[str, float]] = deque(maxlen=360)
        self._lock = asyncio.Lock()
        self._patterns: dict[str, list[re.Pattern[str]]] = {}
        self._states: dict[str, str] = {}
        self._alerts: deque[dict[str, Any]] = deque(maxlen=100)
        self._store = store
        if store is not None:
            self._states = store.states()
            self._alerts.extend(store.recent_alerts(100))  # already newest first

    def _alias_patterns(self, symbols: list[str]) -> dict[str, list[re.Pattern[str]]]:
        for sym in {_base_symbol(s) for s in symbols} | set(ALIASES):
            if sym not in self._patterns:
                names = ALIASES.get(sym, [sym.lower()])
                self._patterns[sym] = [_pattern(n) for n in names]
        return self._patterns

    def tag(self, title: str, extra_symbols: list[str] | None = None) -> list[str]:
        lowered = title.lower()
        patterns = self._alias_patterns(extra_symbols or [])
        return sorted(sym for sym, pats in patterns.items() if any(p.search(lowered) for p in pats))

    async def ensure_fresh(self, extra_symbols: list[str] | None = None) -> None:
        now = datetime.now(timezone.utc)
        if self._last and (now - self._last).total_seconds() < self._ttl:
            return
        async with self._lock:
            if self._last and (datetime.now(timezone.utc) - self._last).total_seconds() < self._ttl:
                return
            await self.refresh(extra_symbols)

    async def refresh(self, extra_symbols: list[str] | None = None) -> None:
        raw, ok = await self._fetch()
        self._sources = ok
        now = datetime.now(timezone.utc)
        alias_lists = list(ALIASES.values())
        for item in raw:
            if not is_market_related(item.title, item.source, alias_lists):
                continue
            key = hashlib.sha1(_norm(item.title).encode()).hexdigest()[:16]
            if key in self._items:
                continue
            score = score_headline(item.title)
            self._items[key] = Headline(
                id=key,
                title=item.title,
                source=item.source,
                url=item.link,
                published=item.published.isoformat(),
                score=score,
                label=label_for(score),
                symbols=self.tag(item.title, extra_symbols),
                published_dt=item.published,
            )
        cutoff = now - timedelta(hours=KEEP_HOURS)
        self._items = {k: v for k, v in self._items.items() if v.published_dt >= cutoff}
        self._last = now
        self._detect_flips(extra_symbols or [], now)
        mood = self.mood()["value"]
        if self._items:
            self._history.append((now.isoformat(), mood))

    def _symbol_tone(self, symbol: str, now: datetime) -> tuple[float, int]:
        """Recency-weighted mean score and mention count for a symbol over the flip window."""
        window = now - timedelta(hours=FLIP_WINDOW_HOURS)
        num = den = 0.0
        n = 0
        for h in self._items.values():
            if symbol in h.symbols and h.published_dt >= window:
                age_h = max(0.0, (now - h.published_dt).total_seconds() / 3600)
                w = math.pow(0.5, age_h / MOOD_HALF_LIFE_HOURS)
                num += h.score * w
                den += w
                n += 1
        return (num / den if den else 0.0), n

    @staticmethod
    def _next_state(previous: str | None, score: float) -> str:
        if score >= FLIP_ENTER:
            return "bullish"
        if score <= -FLIP_ENTER:
            return "bearish"
        if abs(score) < FLIP_EXIT:
            return "neutral"
        return previous or "neutral"  # between the lines: hold what we had

    def _detect_flips(self, watch_symbols: list[str], now: datetime) -> None:
        """Record an alert when a watched symbol's stable tone changes. The first reading of a
        symbol only sets its baseline, so starting the app never raises a burst of alerts."""
        for sym in {_base_symbol(s) for s in watch_symbols}:
            score, n = self._symbol_tone(sym, now)
            if n < FLIP_MIN_MENTIONS:
                continue
            previous = self._states.get(sym)
            current = self._next_state(previous, score)
            if self._states.get(sym) != current and self._store is not None:
                self._store.save_state(sym, current)
            self._states[sym] = current
            if previous is None or current == previous:
                continue
            evidence = sorted(
                (h for h in self._items.values() if sym in h.symbols),
                key=lambda h: (h.label != current, -h.published_dt.timestamp()),
            )
            top = evidence[0] if evidence else None
            alert = {
                "id": hashlib.sha1(f"{sym}{current}{now.isoformat()}".encode()).hexdigest()[:16],
                "t": now.isoformat(),
                "symbol": sym,
                "from": previous,
                "to": current,
                "score": round(score, 3),
                "mentions": n,
                "headline": top.public() if top else None,
            }
            self._alerts.appendleft(alert)
            if self._store is not None:
                self._store.add_alert(alert)

    def alerts(self, limit: int = 30) -> list[dict[str, Any]]:
        return list(self._alerts)[:limit]

    def _sorted(self) -> list[Headline]:
        return sorted(self._items.values(), key=lambda h: h.published_dt, reverse=True)

    def headlines(
        self, limit: int = 60, symbol: str | None = None, label: str | None = None
    ) -> list[dict[str, Any]]:
        out = self._sorted()
        if symbol:
            base = _base_symbol(symbol)
            out = [h for h in out if base in h.symbols]
        if label:
            out = [h for h in out if h.label == label]
        return [h.public() for h in out[:limit]]

    def mood(self, now: datetime | None = None) -> dict[str, Any]:
        """Recency-weighted mean score of the last few hours, plus the raw counts."""
        now = now or datetime.now(timezone.utc)
        window = now - timedelta(hours=MOOD_WINDOW_HOURS)
        recent = [h for h in self._items.values() if h.published_dt >= window]
        num = den = 0.0
        counts = {"bullish": 0, "bearish": 0, "neutral": 0}
        for h in recent:
            age_h = max(0.0, (now - h.published_dt).total_seconds() / 3600)
            w = math.pow(0.5, age_h / MOOD_HALF_LIFE_HOURS)
            num += h.score * w
            den += w
            counts[h.label] += 1
        value = round(num / den, 3) if den else 0.0
        return {
            "value": value,
            "label": label_for(value),
            "window_hours": MOOD_WINDOW_HOURS,
            "counts": counts,
            "headlines": len(recent),
        }

    def tracker(self, watch_symbols: list[str], limit: int = 14) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        window = now - timedelta(hours=DRIVER_WINDOW_HOURS)
        by_sym: dict[str, list[Headline]] = {}
        for h in self._items.values():
            if h.published_dt >= window:
                for s in h.symbols:
                    by_sym.setdefault(s, []).append(h)
        watched = {_base_symbol(s) for s in watch_symbols}
        rows: list[dict[str, Any]] = []
        for sym in set(by_sym) | watched:
            hs = sorted(by_sym.get(sym, []), key=lambda h: h.published_dt, reverse=True)
            if not hs and sym not in watched:
                continue
            avg = round(sum(h.score for h in hs) / len(hs), 3) if hs else 0.0
            rows.append(
                {
                    "symbol": sym,
                    "watched": sym in watched,
                    "mentions": len(hs),
                    "score": avg,
                    "label": label_for(avg) if hs else "neutral",
                    "bullish": sum(1 for h in hs if h.label == "bullish"),
                    "bearish": sum(1 for h in hs if h.label == "bearish"),
                    "neutral": sum(1 for h in hs if h.label == "neutral"),
                    "latest": hs[0].public() if hs else None,
                }
            )
        rows.sort(
            key=lambda r: (
                not r["watched"] and r["mentions"] == 0,
                -r["mentions"],
                -abs(r["score"]),
            )
        )
        return rows[:limit]

    def movers(self, quotes: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        window = now - timedelta(hours=DRIVER_WINDOW_HOURS)
        usable = [q for q in quotes if q.get("change_pct") is not None and q.get("symbol")]
        usable.sort(key=lambda q: abs(q["change_pct"]), reverse=True)
        out = []
        for q in usable[:limit]:
            base = _base_symbol(str(q["symbol"]))
            move = float(q["change_pct"])
            hs = [h for h in self._items.values() if base in h.symbols and h.published_dt >= window]
            aligned = lambda h: (h.score > 0) == (move > 0) and h.label != "neutral"  # noqa: E731
            hs.sort(key=lambda h: (not aligned(h), -h.published_dt.timestamp()))
            drivers = [{**h.public(), "aligned": aligned(h)} for h in hs[:2]]
            out.append(
                {
                    "symbol": str(q["symbol"]),
                    "exchange": q.get("exchange"),
                    "close": q.get("close"),
                    "change_pct": round(move, 2),
                    "direction": "up" if move > 0 else "down" if move < 0 else "flat",
                    "drivers": drivers,
                    "reason": drivers[0]["title"] if drivers else None,
                    "note": "Headlines that mention this symbol around the move. Reported alongside it, not proof of cause.",
                }
            )
        return out

    def symbol_view(self, symbol: str, limit: int = 30) -> dict[str, Any]:
        """Everything the news side knows about one symbol: its headlines, 24h tone, current
        flip state, and the alerts raised for it."""
        base = _base_symbol(symbol)
        now = datetime.now(timezone.utc)
        window = now - timedelta(hours=DRIVER_WINDOW_HOURS)
        mine = sorted(
            (h for h in self._items.values() if base in h.symbols),
            key=lambda h: h.published_dt,
            reverse=True,
        )
        recent = [h for h in mine if h.published_dt >= window]
        avg = round(sum(h.score for h in recent) / len(recent), 3) if recent else 0.0
        return {
            "symbol": base,
            "headlines": [h.public() for h in mine[:limit]],
            "tone": {
                "score": avg,
                "label": label_for(avg) if recent else "neutral",
                "mentions": len(recent),
                "bullish": sum(1 for h in recent if h.label == "bullish"),
                "bearish": sum(1 for h in recent if h.label == "bearish"),
                "neutral": sum(1 for h in recent if h.label == "neutral"),
            },
            "state": self._states.get(base),
            "alerts": [a for a in self._alerts if a["symbol"] == base][:10],
        }

    def pulse(self, watch_symbols: list[str], quotes: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "mood": self.mood(),
            "history": [{"t": t, "v": v} for t, v in self._history],
            "tracker": self.tracker(watch_symbols),
            "movers": self.movers(quotes),
            "alerts": self.alerts(),
            "sources": self._sources,
            "updated_at": self._last.isoformat() if self._last else None,
            "method": "Lexicon-scored headlines (transparent word weights), not a language model.",
        }
