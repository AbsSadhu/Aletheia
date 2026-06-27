from __future__ import annotations
import logging

from aletheia.core.models import Recommendation, SageOutput, ScribeOutput, SentinelOutput
from aletheia.core.models import OracleOutput, SentimentOutput, FundamentalOutput, OptionsFlowOutput
from aletheia.core.llm.client import OllamaClient
from aletheia.core.llm.prompts import build_scribe_prompt
from aletheia.core.llm.parsers import ScribeLLMOutput
from aletheia.core.config.settings import get_settings

logger = logging.getLogger(__name__)


class ScribeAgent:
    def __init__(self):
        self.settings = get_settings()
        self.llm_client = OllamaClient(base_url=self.settings.ollama_base_url)

    async def synthesize(
        self,
        oracle_outputs: list[OracleOutput],
        sentinel_output: SentinelOutput | None,
        sage_outputs: list[SageOutput],
        agent_statuses: dict[str, str] | None = None,
        portfolio_manager_overrides: list[str] | None = None,
        debate_disagreements: list[str] | None = None,
        sentiment_outputs: list[SentimentOutput] | None = None,
        fundamental_outputs: list[FundamentalOutput] | None = None,
        options_flow_outputs: list[OptionsFlowOutput] | None = None,
        critic_notes: list[str] | None = None,
        critic_passed: bool = True,
        macro_context_text: str = "",
    ) -> ScribeOutput:
        recommendations: list[Recommendation] = []
        notes: list[str] = []
        disagreements = 0

        if agent_statuses:
            for agent, status in agent_statuses.items():
                if status == "failed":
                    notes.append(f"Agent {agent} failed during execution.")
                elif status == "skipped":
                    notes.append(f"Agent {agent} was skipped.")

        if debate_disagreements:
            for d in debate_disagreements:
                notes.append(f"[Debate Disagreement] {d}")

        if portfolio_manager_overrides:
            for o in portfolio_manager_overrides:
                notes.append(f"[PM Override] {o}")

        sage_by_symbol = {item.symbol: item for item in sage_outputs}
        for oracle in oracle_outputs:
            sage = sage_by_symbol.get(oracle.symbol)
            action = oracle.signal
            confidence = oracle.confidence

            if sage and oracle.signal == "BUY" and sage.scenario.projected_post_tax_return_pct < 2:
                action = "HOLD"
                disagreements += 1
                notes.append(
                    f"{oracle.symbol}: Oracle is constructive but tax-aware scenario is muted."
                )
            elif (
                sage
                and oracle.signal == "REDUCE"
                and sage.scenario.projected_post_tax_return_pct > 6
            ):
                disagreements += 1
                notes.append(
                    f"{oracle.symbol}: Oracle is defensive but backtest scenario remains favorable."
                )

            explanation = oracle.rationale[0] if oracle.rationale else f"{oracle.signal} signal."
            target_price = None
            stop_loss = None
            if sage:
                explanation = (
                    f"{oracle.signal} view with {sage.scenario.projected_post_tax_return_pct:.2f}% projected "
                    f"post-tax return."
                )
                target_price = round(sage.scenario.projected_return_pct, 2)
                # Compute stop loss relative to average cost basis
                stop_loss = round(max(oracle.fair_value_gap_pct - 5, -25), 2)

            recommendations.append(
                Recommendation(
                    symbol=oracle.symbol,
                    action=action,
                    confidence=round(confidence, 2),
                    explanation=explanation,
                    stop_loss=stop_loss,
                    target_price=target_price,
                )
            )

        agreement_level = "high"
        if disagreements > 1:
            agreement_level = "mixed"
        elif disagreements == 1:
            agreement_level = "moderate"

        overall_confidence = 0.0
        if recommendations:
            overall_confidence = sum(item.confidence for item in recommendations) / len(
                recommendations
            )
        if sentinel_output is not None:
            overall_confidence = (
                (overall_confidence + sentinel_output.confidence) / 2
                if overall_confidence
                else sentinel_output.confidence
            )
            if sentinel_output.alerts:
                notes.extend(sentinel_output.alerts)

        executive_summary = "Multi-agent review completed with India-first market data, risk context, and tax-aware scenarios."

        if self.settings.default_llm_provider == "ollama":
            prompt = build_scribe_prompt(
                oracle_signals=[o.model_dump() for o in oracle_outputs],
                sentinel_risk=sentinel_output.model_dump() if sentinel_output else {},
                sage_scenarios=[s.model_dump() for s in sage_outputs],
                sentiment_data=[s.model_dump() for s in sentiment_outputs]
                if sentiment_outputs
                else None,
                fundamental_data=[f.model_dump() for f in fundamental_outputs]
                if fundamental_outputs
                else None,
                options_flow_data=[o.model_dump() for o in options_flow_outputs]
                if options_flow_outputs
                else None,
                critic_notes=critic_notes,
                macro_context=macro_context_text,
            )

            llm_result = await self.llm_client.generate_structured(
                prompt=prompt, model=self.settings.default_llm_model
            )

            if llm_result and "executive_summary" in llm_result:
                try:
                    parsed = ScribeLLMOutput(**llm_result)
                    executive_summary = f"[LLM Insights]\n{parsed.executive_summary}\n\nRecommendation: {parsed.synthesized_recommendation}"
                    notes.append(f"Market Regime: {parsed.market_regime}")
                    if parsed.stop_loss_suggested:
                        notes.append("System suggests tight stop losses.")
                    if parsed.target_allocation_shift:
                        notes.append(f"Allocation shift: {parsed.target_allocation_shift}")
                except Exception as e:
                    notes.append(f"[LLM Fallback] Parse error: {e}")

        return ScribeOutput(
            executive_summary=executive_summary,
            overall_confidence=round(overall_confidence, 2),
            agreement_level=agreement_level,
            recommendations=recommendations,
            notes=notes,
            critic_passed=critic_passed,
            critic_notes=critic_notes or [],
        )
