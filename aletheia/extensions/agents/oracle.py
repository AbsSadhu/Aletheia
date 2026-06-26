from __future__ import annotations

import json
from aletheia.core.models import Holding, MarketQuote, OracleOutput
from aletheia.core.llm.client import OllamaClient
from aletheia.core.llm.prompts import ORACLE_PROMPT_TEMPLATE
from aletheia.core.llm.parsers import OracleLLMOutput
from aletheia.core.config.settings import get_settings

class OracleAgent:
    def __init__(self):
        self.settings = get_settings()
        self.llm_client = OllamaClient(base_url=self.settings.ollama_base_url)

    async def analyze(self, holding: Holding, quote: MarketQuote) -> OracleOutput:
        momentum_pct = ((quote.close - (quote.open or quote.close)) / max((quote.open or quote.close), 1e-6)) * 100
        fair_value_gap_pct = ((quote.close - holding.average_price) / max(holding.average_price, 1e-6)) * 100

        signal = "HOLD"
        confidence = 0.5
        rationale = [
            f"Current price is {fair_value_gap_pct:.2f}% versus average cost.",
            f"Intraday momentum is {momentum_pct:.2f}%.",
        ]

        if self.settings.default_llm_provider == "ollama":
            prompt = ORACLE_PROMPT_TEMPLATE.format(
                holding_data=json.dumps(holding.model_dump(), default=str),
                quote_data=json.dumps(quote.model_dump(), default=str)
            )
            llm_result = await self.llm_client.generate_structured(
                prompt=prompt, 
                model=self.settings.default_llm_model
            )
            if llm_result and "signal" in llm_result:
                try:
                    parsed = OracleLLMOutput(**llm_result)
                    signal = parsed.signal.upper()
                    if signal not in ["BUY", "HOLD", "REDUCE"]:
                        signal = "HOLD"
                    confidence = parsed.confidence
                    rationale.append(f"[LLM Insights] {parsed.rationale}")
                    
                    return OracleOutput(
                        symbol=holding.symbol.upper(),
                        signal=signal,
                        confidence=confidence,
                        rationale=rationale,
                        fair_value_gap_pct=round(fair_value_gap_pct, 2),
                        momentum_pct=round(momentum_pct, 2),
                    )
                except Exception as e:
                    rationale.append(f"[LLM Fallback] Parse error: {e}")

        # Heuristic fallback
        if fair_value_gap_pct > 8 and momentum_pct > 0:
            signal = "BUY"
            confidence = 0.74
            rationale.append("Price strength and positive momentum support accumulation.")
        elif fair_value_gap_pct < -8 and momentum_pct < 0:
            signal = "REDUCE"
            confidence = 0.71
            rationale.append("Weak mark-to-market position and fading momentum suggest caution.")
        else:
            rationale.append("Signal remains neutral pending stronger confirmation.")

        return OracleOutput(
            symbol=holding.symbol.upper(),
            signal=signal,
            confidence=confidence,
            rationale=rationale,
            fair_value_gap_pct=round(fair_value_gap_pct, 2),
            momentum_pct=round(momentum_pct, 2),
        )
