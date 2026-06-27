"""
FundamentalAgent — AnalystContract agent that fetches NSE equity fundamentals.

Data source: NSE India public equity quote API (no auth, browser User-Agent required).
Fallback: yfinance for P/E, EPS, promoter holding when NSE API is unreachable.
LLM enrichment: 1-sentence valuation commentary.

Always produces a FundamentalOutput — worst case is all None fields with confidence 0.2.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from aletheia.core.models import FundamentalOutput

logger = logging.getLogger(__name__)

_NSE_QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol={symbol}"
_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}


class FundamentalAgent:
    """Analyst-contract agent. Emits FundamentalOutput — never recommendations."""

    def __init__(self, llm_client=None, timeout: float = 10.0) -> None:
        self._llm = llm_client
        self._timeout = timeout

    async def analyze(self, symbol: str) -> FundamentalOutput:
        """Main entry point. Fetches fundamentals and generates verdict."""
        # Only applicable to NSE equity symbols
        if self._is_crypto_or_unknown(symbol):
            return self._empty_output(symbol, note="Non-NSE symbol — fundamentals unavailable")

        try:
            fundamentals = await asyncio.wait_for(
                self._fetch_fundamentals(symbol),
                timeout=self._timeout,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("FundamentalAgent: fetch failed for %s: %s", symbol, exc)
            fundamentals = {}

        if not fundamentals:
            return self._empty_output(symbol)

        # Determine valuation verdict
        pe = fundamentals.get("pe_ratio")
        sector_pe = fundamentals.get("sector_pe")
        verdict = self._compute_valuation_verdict(pe, sector_pe)

        # LLM commentary
        try:
            commentary = await self._generate_commentary(symbol, fundamentals, verdict)
        except Exception as exc:
            logger.debug("FundamentalAgent: LLM commentary failed: %s", exc)
            commentary = f"P/E {pe:.1f}x vs sector {sector_pe:.1f}x → {verdict}" if pe and sector_pe else "Valuation data incomplete."

        return FundamentalOutput(
            symbol=symbol,
            pe_ratio=pe,
            eps_growth_pct=fundamentals.get("eps_growth_pct"),
            revenue_growth_pct=fundamentals.get("revenue_growth_pct"),
            debt_to_equity=fundamentals.get("debt_to_equity"),
            promoter_holding_pct=fundamentals.get("promoter_holding_pct"),
            sector_pe=sector_pe,
            valuation_verdict=verdict,
            valuation_commentary=commentary,
            confidence=0.75 if pe is not None else 0.4,
        )

    async def _fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        """Try NSE API first, fall back to yfinance."""
        try:
            return await self._fetch_from_nse(symbol)
        except Exception as exc:
            logger.debug("NSE API failed for %s, falling back to yfinance: %s", symbol, exc)
            return await self._fetch_from_yfinance(symbol)

    async def _fetch_from_nse(self, symbol: str) -> dict[str, Any]:
        url = _NSE_QUOTE_URL.format(symbol=symbol.upper())
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=_NSE_HEADERS)
            resp.raise_for_status()
            data = resp.json()

        result: dict[str, Any] = {}

        # NSE quote-equity response structure
        metadata = data.get("metadata", {})
        info = data.get("securityInfo", {})
        pdSeries = data.get("priceInfo", {})

        # P/E ratio
        pe_raw = metadata.get("pdSymbolPe") or info.get("applicableMargin")
        if pe_raw:
            try:
                result["pe_ratio"] = float(str(pe_raw).replace(",", ""))
            except (ValueError, TypeError):
                pass

        # Sector P/E
        sector_pe_raw = metadata.get("pdSectorPe")
        if sector_pe_raw:
            try:
                result["sector_pe"] = float(str(sector_pe_raw).replace(",", ""))
            except (ValueError, TypeError):
                pass

        # Promoter holding
        shareholding = data.get("shareholdingPatterns", {})
        promoter_raw = shareholding.get("data", [{}])[0].get("promoterAndPromoterGroupTotal") if shareholding.get("data") else None
        if promoter_raw:
            try:
                result["promoter_holding_pct"] = float(str(promoter_raw).replace("%", "").strip())
            except (ValueError, TypeError):
                pass

        return result

    async def _fetch_from_yfinance(self, symbol: str) -> dict[str, Any]:
        """Fallback: yfinance (blocking, run in thread)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._yfinance_fundamentals, symbol)

    def _yfinance_fundamentals(self, symbol: str) -> dict[str, Any]:
        try:
            import yfinance as yf
            # NSE symbols need .NS suffix for yfinance
            ticker_sym = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
            ticker = yf.Ticker(ticker_sym)
            info = ticker.info
            result: dict[str, Any] = {}
            if info.get("trailingPE"):
                result["pe_ratio"] = float(info["trailingPE"])
            if info.get("sectorPE"):
                result["sector_pe"] = float(info["sectorPE"])
            if info.get("earningsGrowth"):
                result["eps_growth_pct"] = float(info["earningsGrowth"]) * 100
            if info.get("revenueGrowth"):
                result["revenue_growth_pct"] = float(info["revenueGrowth"]) * 100
            if info.get("debtToEquity"):
                result["debt_to_equity"] = float(info["debtToEquity"])
            return result
        except Exception as exc:
            logger.debug("yfinance fundamentals failed: %s", exc)
            return {}

    def _compute_valuation_verdict(
        self, pe: float | None, sector_pe: float | None
    ) -> str:
        if pe is None or sector_pe is None or sector_pe <= 0:
            return "FAIR"  # insufficient data — conservative default
        ratio = pe / sector_pe
        if ratio > 1.5:
            return "OVERVALUED"
        elif ratio < 0.7:
            return "UNDERVALUED"
        return "FAIR"

    async def _generate_commentary(
        self, symbol: str, fundamentals: dict, verdict: str
    ) -> str:
        from aletheia.core.llm.prompts import build_fundamental_prompt

        if self._llm is None:
            return ""
        prompt = build_fundamental_prompt(symbol, {**fundamentals, "valuation_verdict": verdict})
        resp = await self._llm.generate(prompt)
        text = str(resp)
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return str(data.get("valuation_commentary", ""))
        return text[:200]

    def _is_crypto_or_unknown(self, symbol: str) -> bool:
        crypto_suffixes = {"-USD", "-INR", "-USDT", "BTC", "ETH", "SOL", "ADA"}
        return any(c in symbol.upper() for c in crypto_suffixes)

    def _empty_output(self, symbol: str, note: str = "") -> FundamentalOutput:
        return FundamentalOutput(
            symbol=symbol,
            valuation_verdict="FAIR",
            valuation_commentary=note or "Fundamental data unavailable.",
            confidence=0.2,
        )
