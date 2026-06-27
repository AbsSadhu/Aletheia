from __future__ import annotations

import json
import logging
from aletheia.core.models import MarketQuote, Portfolio, SentinelOutput, OracleOutput
from aletheia.core.risk.metrics import assess_portfolio_risk
from aletheia.core.llm.client import OllamaClient
from aletheia.core.llm.prompts import build_sentinel_commentary_prompt, build_sentinel_debate_prompt
from aletheia.core.config.settings import get_settings

logger = logging.getLogger(__name__)

class SentinelAgent:
    def __init__(self, duckdb_store=None, compute_client=None) -> None:
        self.settings = get_settings()
        self.llm_client = OllamaClient(base_url=self.settings.ollama_base_url)
        self.duckdb_store = duckdb_store
        self.compute_client = compute_client

    async def assess(
        self,
        portfolio: Portfolio,
        quotes_by_symbol: dict[str, MarketQuote],
        macro_context_text: str = "",
    ) -> SentinelOutput:
        # Base quantitative risk assessment
        base_output = assess_portfolio_risk(portfolio, quotes_by_symbol)

        # F3. HMM Regime detection from DuckDB/yfinance NIFTY returns
        regime_detail = "unknown"
        regime = base_output.market_regime

        nifty_closes = []
        if self.duckdb_store:
            try:
                conn = self.duckdb_store._connect()
                rows = conn.execute(
                    "SELECT close FROM market_quotes WHERE symbol = '^NSEI' ORDER BY as_of DESC LIMIT 100"
                ).fetchall()
                conn.close()
                nifty_closes = [r[0] for r in rows]
            except Exception:
                pass
        if len(nifty_closes) < 30:
            try:
                import yfinance as yf
                ticker = yf.Ticker("^NSEI")
                hist = ticker.history(period="3mo")
                if not hist.empty:
                    nifty_closes = list(hist["Close"].values)[::-1]
            except Exception:
                pass
        if len(nifty_closes) < 10:
            nifty_closes = [22000.0 * (1.0 + (i * 0.001)) for i in range(60)]

        nifty_returns = [(nifty_closes[i] - nifty_closes[i+1]) / nifty_closes[i+1] for i in range(len(nifty_closes) - 1)][::-1]
        
        if self.compute_client and nifty_returns:
            try:
                res = await self.compute_client.regime_detection(nifty_returns)
                regime_detail = res.get("current_regime", "unknown")
                if regime_detail in ("bearish", "crash"):
                    regime = "bearish"
                elif regime_detail in ("bull", "high_vol_bull", "low_vol_bull"):
                    regime = "bullish"
                else:
                    regime = "balanced"
            except Exception as exc:
                logger.debug("SentinelAgent: regime detection failed: %s", exc)

        # Update market_regime and regime_detail
        base_output.market_regime = regime
        base_output.regime_detail = regime_detail

        # F4. Natural Language commentary brief via LLM
        natural_language_brief = ""
        if self.settings.default_llm_provider == "ollama":
            try:
                prompt = build_sentinel_commentary_prompt(
                    sentinel_data={
                        "portfolio_var_95": base_output.portfolio_var_95,
                        "concentration_risk": base_output.concentration_risk,
                        "max_single_position_pct": base_output.max_single_position_pct,
                        "market_regime": base_output.market_regime,
                        "regime_detail": base_output.regime_detail,
                        "alerts": base_output.alerts,
                    },
                    macro_context=macro_context_text,
                )
                llm_res = await self.llm_client.generate_structured(
                    prompt=prompt, model=self.settings.default_llm_model
                )
                if llm_res and "natural_language_brief" in llm_res:
                    natural_language_brief = llm_res["natural_language_brief"]
                elif llm_res and isinstance(llm_res, dict):
                    # Fallback if structure keys differ
                    natural_language_brief = next(iter(llm_res.values())) if llm_res else ""
            except Exception as exc:
                logger.debug("SentinelAgent: LLM commentary brief failed: %s", exc)

        if not natural_language_brief:
            natural_language_brief = f"Portfolio VaR is {base_output.portfolio_var_95:.2f}. " + (
                "Concentrated risk detected." if base_output.concentration_risk > 0.4 else "Portfolio concentration is balanced."
            )

        base_output.natural_language_brief = natural_language_brief
        return base_output

    async def debate(self, sentinel_output: SentinelOutput, oracle_outputs: list[OracleOutput]) -> SentinelOutput:
        if self.settings.default_llm_provider != "ollama":
            return sentinel_output

        oracle_details = []
        for o in oracle_outputs:
            oracle_details.append(f"Holding: {o.symbol}, Signal: {o.signal}, Confidence: {o.confidence}, Rationale: {o.rationale}")
        oracle_text = "\n".join(oracle_details)

        prompt = build_sentinel_debate_prompt(
            sentinel_output={
                "portfolio_var_95": sentinel_output.portfolio_var_95,
                "concentration_risk": sentinel_output.concentration_risk,
                "max_single_position_pct": sentinel_output.max_single_position_pct,
                "market_regime": sentinel_output.market_regime,
                "regime_detail": sentinel_output.regime_detail,
                "alerts": sentinel_output.alerts,
                "confidence": sentinel_output.confidence,
            },
            oracle_text=oracle_text,
        )
        llm_result = await self.llm_client.generate_structured(
            prompt=prompt, model=self.settings.default_llm_model
        )
        if llm_result and "confidence" in llm_result:
            try:
                return SentinelOutput(
                    portfolio_var_95=llm_result.get("portfolio_var_95", sentinel_output.portfolio_var_95),
                    concentration_risk=llm_result.get("concentration_risk", sentinel_output.concentration_risk),
                    max_single_position_pct=llm_result.get("max_single_position_pct", sentinel_output.max_single_position_pct),
                    market_regime=llm_result.get("market_regime", sentinel_output.market_regime),
                    confidence=llm_result.get("confidence", sentinel_output.confidence),
                    alerts=llm_result.get("alerts", sentinel_output.alerts),
                    regime_detail=sentinel_output.regime_detail,
                    natural_language_brief=sentinel_output.natural_language_brief,
                )
            except Exception:
                pass
        return sentinel_output
