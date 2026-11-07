"""Public RSS sources for Indian market news, fetched and parsed with the standard library."""

from __future__ import annotations

import asyncio
import html
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

# (label, url). Google News is a search over many publishers; its titles end in " - Publisher".
FEEDS: list[tuple[str, str]] = [
    (
        "Google News",
        "https://news.google.com/rss/search?q=Sensex+OR+Nifty+OR+%22stock+market%22+India+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    ),
    ("Economic Times", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("Mint", "https://www.livemint.com/rss/markets"),
    ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/marketreports.xml"),
    ("NDTV Profit", "https://feeds.feedburner.com/ndtvprofit-latest"),
]

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Aletheia/0.1; local market reader)"}
_TAGS = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class RawItem:
    title: str
    link: str
    source: str
    published: datetime


def _clean(text: str | None) -> str:
    return html.unescape(_TAGS.sub("", text or "")).strip()


def _parse_date(value: str | None) -> datetime:
    if value:
        try:
            dt = parsedate_to_datetime(value)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc)


def parse_rss(body: bytes, label: str) -> list[RawItem]:
    """Parse one RSS document into items. Malformed documents yield an empty list."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    items: list[RawItem] = []
    for node in root.iter("item"):
        title = _clean(node.findtext("title"))
        if not title:
            continue
        source = label
        if label == "Google News" and " - " in title:
            title, source = title.rsplit(" - ", 1)
        items.append(
            RawItem(
                title=title.strip(),
                link=_clean(node.findtext("link")),
                source=source.strip(),
                published=_parse_date(node.findtext("pubDate")),
            )
        )
    return items


async def _fetch_one(
    client: httpx.AsyncClient, label: str, url: str
) -> tuple[str, list[RawItem] | None]:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return label, parse_rss(resp.content, label)
    except Exception as exc:  # a dead feed must never take the others down
        logger.info("news feed %s unavailable: %s", label, exc)
        return label, None


async def fetch_all(timeout: float = 8.0) -> tuple[list[RawItem], dict[str, bool]]:
    """Fetch every feed concurrently. Returns the items and which sources answered."""
    async with httpx.AsyncClient(
        timeout=timeout, headers=_HEADERS, follow_redirects=True
    ) as client:
        results = await asyncio.gather(*(_fetch_one(client, label, url) for label, url in FEEDS))
    items: list[RawItem] = []
    ok: dict[str, bool] = {}
    for label, got in results:
        ok[label] = got is not None
        items.extend(got or [])
    return items, ok
