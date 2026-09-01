"""
Reflection / Self-Critique Module.

Periodically compares each agent's past recommendations against actual
market outcomes (next-day close) and generates a self-critique that is
injected into future agent prompts.

Pattern inspired by FinMem / FinCon:
    past_calls + actual_outcomes → LLM critique → stored critique → injected next run
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def format_past_calls_with_outcomes(
    observations: list[dict[str, Any]],
    actual_outcomes: dict[str, float],
) -> str:
    """
    Build a human-readable table of past agent calls with their actual outcomes.

    observations: list of agent_observations rows
    actual_outcomes: {ticker: forward_return_pct} e.g. {"RELIANCE": 2.3}
    """
    if not observations:
        return "No past observations available."

    lines = ["Ticker | Timestamp | Confidence | Observation | Actual Outcome"]
    lines.append("-" * 80)
    for obs in observations:
        ticker = obs.get("ticker", "?")
        ts = obs.get("timestamp", "?")[:10]
        conf = f"{obs.get('confidence', 0):.2f}"
        text = obs.get("observation", "")[:80]
        outcome = actual_outcomes.get(ticker)
        outcome_str = f"{outcome:+.2f}%" if outcome is not None else "unknown"
        lines.append(f"{ticker:10} | {ts:10} | {conf:6} | {text:<80} | {outcome_str}")
    return "\n".join(lines)


def build_critique_prompt(agent_name: str, formatted_calls: str) -> str:
    return f"""You are {agent_name.upper()}, an AI financial analysis agent. 
Review your recent calls and their actual outcomes:

{formatted_calls}

Generate a concise self-critique (100-200 words) addressing:
1. What went well? (calls that were directionally correct)
2. What missed? (calls that were wrong or poorly calibrated)
3. Any systematic biases you notice (overconfidence, sector bias, etc.)?
4. How will you adjust your next analysis?

Be specific and actionable. Do not be vague.
"""


class ReflectionEngine:
    """
    Runs self-critique cycles for agents based on past observations
    and actual market outcomes.
    """

    def __init__(self, working_memory: Any, llm_router: Any | None = None) -> None:
        """
        working_memory: WorkingMemory instance
        llm_router: LLMRouter instance (optional; if None, critique is template-based)
        """
        self.wm = working_memory
        self.llm = llm_router

    async def run_critique(
        self,
        agent_name: str,
        lookback_days: int = 7,
        actual_outcomes: dict[str, float] | None = None,
    ) -> str:
        """
        Run a self-critique cycle for one agent.

        actual_outcomes: {ticker: forward_return_pct} — if None, uses placeholder text.
        Returns the critique string, which is also stored in working memory.
        """
        observations = self.wm.list_all_observations(agent_name=agent_name, limit=50)
        cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()
        recent_obs = [o for o in observations if o.get("timestamp", "") >= cutoff]

        if not recent_obs:
            critique = (
                f"No recent observations found for {agent_name} in the last "
                f"{lookback_days} days. Cannot generate self-critique."
            )
            self.wm.store_critique(agent_name, critique)
            return critique

        formatted = format_past_calls_with_outcomes(
            recent_obs,
            actual_outcomes or {},
        )
        prompt = build_critique_prompt(agent_name, formatted)

        if self.llm is not None:
            try:
                critique = await self.llm.generate(prompt, max_tokens=400)
            except Exception as exc:
                logger.warning("LLM critique failed for %s: %s", agent_name, exc)
                critique = self._template_critique(agent_name, recent_obs, actual_outcomes or {})
        else:
            critique = self._template_critique(agent_name, recent_obs, actual_outcomes or {})

        self.wm.store_critique(agent_name, critique)
        logger.info("Stored critique for %s (%d chars)", agent_name, len(critique))
        return critique

    def _template_critique(
        self,
        agent_name: str,
        observations: list[dict[str, Any]],
        outcomes: dict[str, float],
    ) -> str:
        """Fallback critique generation when LLM is unavailable."""
        total = len(observations)
        correct = sum(
            1 for obs in observations
            if self._is_directionally_correct(obs.get("observation", ""), outcomes.get(obs.get("ticker", ""), 0.0))
        )
        accuracy = correct / total if total > 0 else 0.0
        avg_conf = sum(o.get("confidence", 0.5) for o in observations) / total if total > 0 else 0.5

        bias = "overconfident" if avg_conf > 0.75 and accuracy < 0.5 else \
               "underconfident" if avg_conf < 0.4 and accuracy > 0.6 else "calibrated"

        return (
            f"Self-critique for {agent_name.upper()} (last {total} observations):\n"
            f"- Directional accuracy: {accuracy:.1%} ({correct}/{total} correct)\n"
            f"- Average confidence: {avg_conf:.2f} — appears {bias}\n"
            f"- Bias assessment: {'Need to calibrate confidence lower.' if bias == 'overconfident' else 'Confidence is well-calibrated.'}\n"
            f"- Next steps: {'Reduce overconfidence by widening uncertainty range.' if bias == 'overconfident' else 'Maintain current calibration approach.'}"
        )

    def _is_directionally_correct(self, observation: str, return_pct: float) -> bool:
        """Heuristic: observation contains BUY/bullish and return was positive, or SELL/bearish and negative."""
        obs_lower = observation.lower()
        is_bullish = any(w in obs_lower for w in ("buy", "bullish", "long", "increase", "upside"))
        is_bearish = any(w in obs_lower for w in ("sell", "bearish", "short", "decrease", "downside"))
        if is_bullish and return_pct > 0:
            return True
        if is_bearish and return_pct < 0:
            return True
        return False

    async def run_all_agents(
        self,
        agent_names: list[str],
        lookback_days: int = 7,
        actual_outcomes: dict[str, float] | None = None,
    ) -> dict[str, str]:
        """Run critique for multiple agents. Returns {agent_name: critique}."""
        results: dict[str, str] = {}
        for name in agent_names:
            results[name] = await self.run_critique(name, lookback_days, actual_outcomes)
        return results
