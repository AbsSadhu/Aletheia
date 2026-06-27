"""
CriticAgent — independent auditor of the Scribe's recommendation.

Pattern: Reflexion / self-critique loop (max 2 iterations).
- Reads ScribeOutput + Sentinel + Sage outputs
- Scores the recommendation on 5 criteria (confidence consistency, tax reflection,
  data-gap disclosure, actionability, disagreement surfacing)
- If score >= 0.8 → passes (critic_passed=True)
- If score < 0.6 → sends CriticVerdict(passed=False) back → Scribe must revise once
- Max 2 iterations to avoid infinite loop (after 2nd attempt, passes regardless with critic_notes)
"""

from __future__ import annotations

import logging

from aletheia.core.models import CriticVerdict, ScribeOutput

logger = logging.getLogger(__name__)

_PASS_THRESHOLD = 0.8
_FAIL_THRESHOLD = 0.6
_MAX_ITERATIONS = 2


class CriticAgent:
    """
    Not bound by AnalystContract — it is an auditor, not an analyst.
    Does not emit signals or recommendations itself.
    """

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client

    async def audit(
        self,
        scribe_output: ScribeOutput,
        sentinel_output: dict | None = None,
        sage_outputs: list | None = None,
        iteration: int = 1,
    ) -> CriticVerdict:
        """
        Audit the Scribe's recommendation.
        Returns CriticVerdict(passed, score, notes).
        """
        if self._llm is None:
            # No LLM — auto-pass with caveat
            return CriticVerdict(
                passed=True,
                score=1.0,
                notes=["CriticAgent: no LLM configured — auto-passed."],
                iteration=iteration,
            )

        # After max iterations, force pass
        if iteration > _MAX_ITERATIONS:
            return CriticVerdict(
                passed=True,
                score=0.6,
                notes=["CriticAgent: max iterations reached — passing with caveats."],
                iteration=iteration,
            )

        try:
            return await self._llm_audit(
                scribe_output, sentinel_output or {}, sage_outputs or [], iteration
            )
        except Exception as exc:
            logger.warning("CriticAgent: LLM audit failed: %s", exc)
            return self._rule_based_audit(scribe_output, sentinel_output or {}, iteration)

    async def _llm_audit(
        self,
        scribe_output: ScribeOutput,
        sentinel_output: dict,
        sage_outputs: list,
        iteration: int,
    ) -> CriticVerdict:
        from aletheia.core.llm.prompts import build_critic_prompt

        scribe_dict = scribe_output.model_dump(mode="json")
        prompt = build_critic_prompt(scribe_dict, sentinel_output, sage_outputs)

        data = await self._llm.generate_structured(prompt=prompt)
        if not data:
            raise ValueError("CriticAgent: LLM returned empty response")

        passed = bool(data.get("passed", True))
        score = float(data.get("score", 0.8))
        notes = list(data.get("notes", []))

        # Apply thresholds
        if score >= _PASS_THRESHOLD:
            passed = True
        elif score < _FAIL_THRESHOLD and iteration <= _MAX_ITERATIONS:
            passed = False
        else:
            passed = True  # soft pass between thresholds

        return CriticVerdict(passed=passed, score=score, notes=notes, iteration=iteration)

    def _rule_based_audit(
        self,
        scribe_output: ScribeOutput,
        sentinel_output: dict,
        iteration: int,
    ) -> CriticVerdict:
        """
        Deterministic rule-based audit (no LLM).
        Checks a subset of criteria that can be verified without LLM.
        """
        notes: list[str] = []
        score = 1.0

        # Check: does summary mention risk if Sentinel has high VaR?
        var_95 = sentinel_output.get("portfolio_var_95", 0)
        summary = scribe_output.executive_summary.lower()
        if var_95 > 0.05 and "risk" not in summary and "var" not in summary:
            notes.append(f"High portfolio VaR ({var_95:.1%}) not mentioned in summary.")
            score -= 0.15

        # Check: are there recommendations?
        if not scribe_output.recommendations:
            notes.append("No specific recommendations emitted — summary is non-actionable.")
            score -= 0.2

        # Check: is overall confidence too high without supporting data?
        if scribe_output.overall_confidence > 0.85 and sentinel_output.get("alerts"):
            notes.append("High confidence despite active risk alerts from Sentinel.")
            score -= 0.1

        # Check: summary length (too short = non-substantive)
        if len(scribe_output.executive_summary) < 100:
            notes.append(
                "Executive summary is too brief — insufficient detail for a retail investor."
            )
            score -= 0.1

        score = max(0.0, min(1.0, score))
        passed = score >= _PASS_THRESHOLD
        return CriticVerdict(passed=passed, score=score, notes=notes, iteration=iteration)
