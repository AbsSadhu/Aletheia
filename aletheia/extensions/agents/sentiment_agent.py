"""
SentimentAgent — AnalystContract agent that classifies news sentiment for a symbol.

Sources (in priority order, all best-effort):
1. NSE announcements JSON API (no auth required)
2. MoneyControl RSS feed (public)
3. Reddit r/IndiaInvestments via PRAW (optional — requires REDDIT_CLIENT_ID env var)

Timeout: 8 seconds total. Returns partial results on timeout.
Always produces a SentimentOutput — worst case is sentiment_score=0.0, confidence=0.2.
"""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from aletheia.core.models import SentimentOutput

logger = logging.getLogger(__name__)

_NSE_ANNOUNCEMENTS_URL = (
    "https://www.nseindia.com/api/corp-info?symbol={symbol}&corpType=announcements&market=equities"
)
_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}
_MONEYCONTROL_RSS = "https://www.moneycontrol.com/rss/companynews.xml"

# Simple keyword-based sentiment classifier (used as LLM fallback)
_BULLISH_WORDS = {
    "profit",
    "growth",
    "record",
    "acquisition",
    "expansion",
    "dividend",
    "buyback",
    "upgrade",
    "beat",
    "outperform",
    "positive",
    "strong",
    "surge",
    "rally",
    "gain",
}
_BEARISH_WORDS = {
    "loss",
    "decline",
    "down",
    "weak",
    "miss",
    "underperform",
    "cut",
    "reduce",
    "default",
    "fraud",
    "penalty",
    "sell",
    "crash",
    "fall",
    "concern",
    "risk",
}


class SentimentAgent:
    """
    Analyst-contract agent. Emits SentimentOutput — never recommendations.
    """

    def __init__(
        self,
        llm_client=None,
        timeout: float = 8.0,
        enable_reddit: bool = False,
    ) -> None:
        self._llm = llm_client
        self._timeout = timeout
        self._enable_reddit = enable_reddit

    async def analyze(self, symbol: str) -> SentimentOutput:
        """Entry point. Fetches headlines and classifies sentiment."""
        try:
            headlines, source_breakdown = await asyncio.wait_for(
                self._fetch_headlines(symbol),
                timeout=self._timeout,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning(
                "SentimentAgent: headline fetch timed out/failed for %s: %s", symbol, exc
            )
            headlines, source_breakdown = [], {}

        if not headlines:
            return SentimentOutput(
                symbol=symbol,
                sentiment_score=0.0,
                headline_count=0,
                top_headlines=[],
                source_breakdown={},
                verdict="NEUTRAL",
                confidence=0.2,
            )

        # Try LLM classification first, fall back to keyword scoring
        try:
            score, verdict = await self._classify_with_llm(symbol, headlines)
            confidence = 0.75
        except Exception as exc:
            logger.debug(
                "SentimentAgent: LLM classification failed, using keyword fallback: %s", exc
            )
            score, verdict = self._keyword_classify(headlines)
            confidence = 0.5

        return SentimentOutput(
            symbol=symbol,
            sentiment_score=round(score, 3),
            headline_count=len(headlines),
            top_headlines=headlines[:5],
            source_breakdown=source_breakdown,
            verdict=verdict,
            confidence=confidence,
        )

    async def _fetch_headlines(self, symbol: str) -> tuple[list[str], dict[str, int]]:
        headlines: list[str] = []
        source_breakdown: dict[str, int] = {}

        tasks = [
            self._fetch_nse_announcements(symbol),
            self._fetch_moneycontrol_rss(symbol),
        ]
        if self._enable_reddit:
            tasks.append(self._fetch_reddit(symbol))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                continue
            src_name, src_headlines = result
            headlines.extend(src_headlines)
            if src_headlines:
                source_breakdown[src_name] = len(src_headlines)

        return headlines, source_breakdown

    async def _fetch_nse_announcements(self, symbol: str) -> tuple[str, list[str]]:
        url = _NSE_ANNOUNCEMENTS_URL.format(symbol=symbol.upper())
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=_NSE_HEADERS)
                resp.raise_for_status()
                data = resp.json()
                # NSE returns list under various keys depending on API version
                announcements = (
                    data.get("announcements")
                    or data.get("data")
                    or (data if isinstance(data, list) else [])
                )
                headlines = [
                    a.get("subject") or a.get("description") or a.get("headline") or ""
                    for a in announcements[:15]
                    if isinstance(a, dict)
                ]
                headlines = [h for h in headlines if h.strip()]
                return ("nse", headlines)
        except Exception as exc:
            logger.debug("NSE announcements fetch failed for %s: %s", symbol, exc)
            return ("nse", [])

    async def _fetch_moneycontrol_rss(self, symbol: str) -> tuple[str, list[str]]:
        """Fetch MoneyControl company news RSS and filter by symbol."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(_MONEYCONTROL_RSS, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                # Parse RSS — find <title> tags in items
                titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", resp.text)
                if not titles:
                    titles = re.findall(r"<title>(.*?)</title>", resp.text)
                # Filter by symbol mention
                symbol_lower = symbol.lower()
                filtered = [t for t in titles if symbol_lower in t.lower()][:10]
                return ("moneycontrol", filtered)
        except Exception as exc:
            logger.debug("MoneyControl RSS failed: %s", exc)
            return ("moneycontrol", [])

    async def _fetch_reddit(self, symbol: str) -> tuple[str, list[str]]:
        """Fetch Reddit posts (requires PRAW credentials in env)."""
        try:
            import os
            import asyncio

            client_id = os.environ.get("REDDIT_CLIENT_ID")
            client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
            if not client_id or not client_secret:
                return ("reddit", [])
            loop = asyncio.get_event_loop()
            posts = await loop.run_in_executor(
                None, self._praw_fetch, symbol, client_id, client_secret
            )
            return ("reddit", posts)
        except Exception as exc:
            logger.debug("Reddit fetch failed: %s", exc)
            return ("reddit", [])

    def _praw_fetch(self, symbol: str, client_id: str, client_secret: str) -> list[str]:
        try:
            import praw

            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent="Aletheia-SentimentAgent/1.0",
            )
            posts = []
            for sub in reddit.subreddit("IndiaInvestments+stocks").search(
                symbol, limit=10, time_filter="week"
            ):
                posts.append(sub.title)
            return posts
        except Exception:
            return []

    async def _classify_with_llm(self, symbol: str, headlines: list[str]) -> tuple[float, str]:
        """Use LLM to classify sentiment. Returns (score, verdict)."""
        from aletheia.core.llm.prompts import build_sentiment_prompt
        import json

        if self._llm is None:
            raise RuntimeError("No LLM client configured")

        prompt = build_sentiment_prompt(symbol, headlines)
        response_text = await self._llm.generate(prompt)
        # Parse JSON response
        text = str(response_text)
        # Extract JSON from possible markdown wrapping
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            score = float(data.get("sentiment_score", 0.0))
            verdict = str(data.get("verdict", "NEUTRAL"))
            return score, verdict
        raise ValueError(f"LLM returned non-JSON: {text[:200]}")

    def _keyword_classify(self, headlines: list[str]) -> tuple[float, str]:
        """Fallback keyword-based sentiment scoring."""
        total_score = 0.0
        for headline in headlines:
            words = set(re.findall(r"\b\w+\b", headline.lower()))
            bull = len(words & _BULLISH_WORDS)
            bear = len(words & _BEARISH_WORDS)
            if bull + bear > 0:
                total_score += (bull - bear) / (bull + bear)
        if not headlines:
            return 0.0, "NEUTRAL"
        avg = total_score / len(headlines)
        avg = max(-1.0, min(1.0, avg))
        if avg > 0.4:
            verdict = "STRONGLY_POSITIVE"
        elif avg > 0.1:
            verdict = "POSITIVE"
        elif avg < -0.4:
            verdict = "STRONGLY_NEGATIVE"
        elif avg < -0.1:
            verdict = "NEGATIVE"
        else:
            verdict = "NEUTRAL"
        return avg, verdict
