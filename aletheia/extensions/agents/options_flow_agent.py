"""
OptionsFlowAgent — AnalystContract agent that reads NSE options chain data.

Source: NSE options chain API (public, no auth, requires session cookie pattern).
Computes: PCR, IV Rank, max pain, OI concentration signal.
Delegates heavy computation to Rust sidecar (ComputeClient.options_flow()).

Only runs for NSE equity symbols. Skips crypto, cash, non-NSE holdings.
Timeout: 5 seconds hard cutoff.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from aletheia.core.models import OptionsFlowOutput

logger = logging.getLogger(__name__)

_NSE_OPTIONS_CHAIN_URL = "https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}

# NSE session establishment URL (needed to get cookies)
_NSE_HOME_URL = "https://www.nseindia.com"


class OptionsFlowAgent:
    """
    Analyst-contract agent. Emits OptionsFlowOutput — never recommendations.
    Only runs for NSE equity symbols.
    """

    def __init__(self, compute_client=None, timeout: float = 5.0) -> None:
        self._compute = compute_client
        self._timeout = timeout

    async def analyze(self, symbol: str) -> OptionsFlowOutput:
        """Main entry. Fetches options chain, computes flow metrics."""
        if not self._is_nse_equity(symbol):
            return OptionsFlowOutput(
                symbol=symbol,
                oi_concentration="NEUTRAL",
                signal_hint="SKIP",
                confidence=0.0,
            )

        try:
            chain_data = await asyncio.wait_for(
                self._fetch_options_chain(symbol),
                timeout=self._timeout,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("OptionsFlowAgent: chain fetch failed for %s: %s", symbol, exc)
            return self._empty_output(symbol)

        if not chain_data:
            return self._empty_output(symbol)

        return await self._compute_metrics(symbol, chain_data)

    async def _fetch_options_chain(self, symbol: str) -> dict[str, Any] | None:
        """Fetch NSE options chain. Returns parsed chain data."""
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                # Establish NSE session first (get cookies)
                try:
                    await client.get(_NSE_HOME_URL, headers=_NSE_HEADERS)
                except Exception:
                    pass  # Session establishment is best-effort

                url = _NSE_OPTIONS_CHAIN_URL.format(symbol=symbol.upper())
                resp = await client.get(url, headers=_NSE_HEADERS)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.debug("NSE options chain fetch error: %s", exc)
            return None

    async def _compute_metrics(self, symbol: str, chain_data: dict) -> OptionsFlowOutput:
        """Parse chain data and compute OI/IV metrics."""
        records = (
            chain_data.get("filtered", {}).get("data", []) or
            chain_data.get("records", {}).get("data", []) or
            []
        )

        calls_oi: list[float] = []
        puts_oi: list[float] = []
        calls_iv: list[float] = []
        puts_iv: list[float] = []

        for record in records:
            ce = record.get("CE", {})
            pe = record.get("PE", {})
            if ce:
                calls_oi.append(float(ce.get("openInterest", 0) or 0))
                calls_iv.append(float(ce.get("impliedVolatility", 20) or 20))
            if pe:
                puts_oi.append(float(pe.get("openInterest", 0) or 0))
                puts_iv.append(float(pe.get("impliedVolatility", 20) or 20))

        if not calls_oi or not puts_oi:
            return self._empty_output(symbol)

        # Try sidecar compute, fall back to Python
        try:
            metrics = await self._rust_compute(calls_oi, puts_oi, calls_iv, puts_iv)
        except Exception:
            metrics = self._python_compute(calls_oi, puts_oi, calls_iv, puts_iv)

        pcr = metrics.get("put_call_ratio", 1.0)
        iv_rank = metrics.get("iv_rank", 50.0)
        oi_conc = metrics.get("oi_concentration", "NEUTRAL")
        iv_sig = metrics.get("iv_signal", "NEUTRAL")

        # Combine OI + IV signals into a single hint
        if oi_conc == "BULLISH_OI" and iv_sig in ("NEUTRAL", "CONTRARIAN_BUY"):
            signal_hint = "BULLISH"
        elif oi_conc == "BEARISH_OI" and iv_sig in ("NEUTRAL", "CONTRARIAN_SELL"):
            signal_hint = "BEARISH"
        else:
            signal_hint = "NEUTRAL"

        return OptionsFlowOutput(
            symbol=symbol,
            put_call_ratio=round(pcr, 3),
            iv_rank=round(iv_rank, 1),
            max_pain_level=self._compute_max_pain(records),
            oi_concentration=oi_conc,
            signal_hint=signal_hint,
            confidence=0.7,
        )

    async def _rust_compute(
        self,
        calls_oi: list[float],
        puts_oi: list[float],
        calls_iv: list[float],
        puts_iv: list[float],
    ) -> dict:
        if self._compute is None:
            raise RuntimeError("No compute client")
        iv_all = calls_iv + puts_iv
        iv_52w_high = max(iv_all) if iv_all else 50.0
        iv_52w_low = min(iv_all) if iv_all else 10.0
        return await self._compute.options_flow(
            calls_oi=calls_oi,
            puts_oi=puts_oi,
            calls_iv=calls_iv,
            puts_iv=puts_iv,
            iv_52w_high=iv_52w_high,
            iv_52w_low=iv_52w_low,
        )

    def _python_compute(
        self,
        calls_oi: list[float],
        puts_oi: list[float],
        calls_iv: list[float],
        puts_iv: list[float],
    ) -> dict:
        tc = sum(calls_oi)
        tp = sum(puts_oi)
        pcr = tp / tc if tc > 0 else 1.0
        iv_all = calls_iv + puts_iv
        iv_52w_high = max(iv_all) if iv_all else 50.0
        iv_52w_low = min(iv_all) if iv_all else 10.0
        atm_iv = sum(iv_all) / len(iv_all) if iv_all else 20.0
        iv_range = iv_52w_high - iv_52w_low
        iv_rank = (atm_iv - iv_52w_low) / iv_range * 100 if iv_range > 0 else 50.0
        oi_conc = "BEARISH_OI" if pcr > 1.3 else ("BULLISH_OI" if pcr < 0.7 else "NEUTRAL")
        iv_sig = "CONTRARIAN_BUY" if iv_rank > 80 else ("CONTRARIAN_SELL" if iv_rank < 20 else "NEUTRAL")
        return {"put_call_ratio": pcr, "iv_rank": iv_rank, "oi_concentration": oi_conc, "iv_signal": iv_sig}

    def _compute_max_pain(self, records: list[dict]) -> float | None:
        """Max pain: strike where total OI loss (calls + puts) is minimized."""
        if not records:
            return None
        try:
            total_oi_by_strike: dict[float, float] = {}
            for rec in records:
                strike = float(rec.get("strikePrice", 0) or 0)
                if strike <= 0:
                    continue
                ce_oi = float((rec.get("CE") or {}).get("openInterest", 0) or 0)
                pe_oi = float((rec.get("PE") or {}).get("openInterest", 0) or 0)
                total_oi_by_strike[strike] = ce_oi + pe_oi
            if not total_oi_by_strike:
                return None
            # Strike with maximum total OI (simplistic max pain approximation)
            return min(total_oi_by_strike, key=lambda s: abs(total_oi_by_strike[s] - max(total_oi_by_strike.values())))
        except Exception:
            return None

    def _is_nse_equity(self, symbol: str) -> bool:
        s = symbol.upper()
        crypto_markers = {"BTC", "ETH", "USDT", "SOL", "ADA", "-USD", "-INR"}
        return not any(c in s for c in crypto_markers)

    def _empty_output(self, symbol: str) -> OptionsFlowOutput:
        return OptionsFlowOutput(
            symbol=symbol,
            put_call_ratio=1.0,
            iv_rank=50.0,
            oi_concentration="NEUTRAL",
            signal_hint="NEUTRAL",
            confidence=0.1,
        )
