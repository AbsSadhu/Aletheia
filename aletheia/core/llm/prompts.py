"""
Prompt templates for LLM generation.

All templates use JSON-mode: every prompt ends with an injected Pydantic JSON schema
and strict instruction to respond ONLY with valid JSON. This eliminates parse failures.

Usage:
    from aletheia.core.llm.prompts import build_oracle_prompt
    prompt = build_oracle_prompt(holding_data, quote_data, macro_context)
"""
from __future__ import annotations

import json


# ─────────────────────────────────────────────────────────────
# Schema injection helper
# ─────────────────────────────────────────────────────────────

def _json_schema_footer(schema: dict) -> str:
    return (
        "\n\nRespond ONLY with a single valid JSON object matching this schema exactly. "
        "No markdown, no prose, no explanation outside the JSON.\n\n"
        f"Schema:\n{json.dumps(schema, indent=2)}"
    )


# ─────────────────────────────────────────────────────────────
# Oracle
# ─────────────────────────────────────────────────────────────

ORACLE_SCHEMA = {
    "type": "object",
    "required": ["signal", "confidence", "rationale"],
    "properties": {
        "signal": {"type": "string", "enum": ["BUY", "HOLD", "REDUCE"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "rationale": {"type": "string"},
    },
}

ORACLE_SCHEMA_MULTITF = {
    "type": "object",
    "required": ["signal", "confidence", "rationale", "timeframe_agreement"],
    "properties": {
        "signal": {"type": "string", "enum": ["BUY", "HOLD", "REDUCE"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "rationale": {"type": "string"},
        "timeframe_agreement": {
            "type": "string",
            "enum": ["ALL_AGREE", "MAJORITY_AGREE", "SPLIT", "NO_AGREEMENT"],
        },
        "factor_commentary": {"type": "string"},
    },
}


def build_oracle_prompt(
    holding_data: dict,
    quote_data: dict,
    macro_context: str = "",
    multi_tf_data: dict | None = None,
    factor_exposures: dict | None = None,
) -> str:
    macro_section = f"\n\nMacro Context:\n{macro_context}" if macro_context else ""
    tf_section = ""
    if multi_tf_data:
        tf_section = f"\n\nMulti-Timeframe Signals:\n{json.dumps(multi_tf_data, indent=2)}"
    factor_section = ""
    if factor_exposures:
        factor_section = (
            f"\n\nFama-French Factor Exposures:\n{json.dumps(factor_exposures, indent=2)}"
        )

    schema = ORACLE_SCHEMA_MULTITF if multi_tf_data else ORACLE_SCHEMA
    schema_footer = _json_schema_footer(schema)

    return f"""You are an expert Indian equity analyst. Analyze this holding and current market data.
Consider: technical momentum, price vs. cost basis, intraday movement, and any macro context.
Only emit BUY if at least 2 of 3 timeframes (1D/1W/1M) agree — if timeframe data is provided.
Confidence must reflect genuine conviction, not optimism. 0.5 = uncertain, 0.85 = strong conviction.{macro_section}

Holding Data:
{json.dumps(holding_data, default=str, indent=2)}

Market Data (current quote):
{json.dumps(quote_data, default=str, indent=2)}{tf_section}{factor_section}{schema_footer}"""


# ─────────────────────────────────────────────────────────────
# Sentinel
# ─────────────────────────────────────────────────────────────

SENTINEL_SCHEMA = {
    "type": "object",
    "required": ["natural_language_brief"],
    "properties": {
        "natural_language_brief": {"type": "string"},
    },
}


def build_sentinel_commentary_prompt(sentinel_data: dict, macro_context: str = "") -> str:
    macro_section = f"\n\nMacro Context:\n{macro_context}" if macro_context else ""
    schema_footer = _json_schema_footer(SENTINEL_SCHEMA)
    return f"""You are Sentinel, a risk management agent for an Indian retail investor portfolio.
You have completed your quantitative risk assessment. Now write a plain-English risk brief.
Write for a non-technical investor. Be specific about numbers. Max 3 sentences.{macro_section}

Quantitative Risk Assessment:
{json.dumps(sentinel_data, indent=2)}{schema_footer}"""


def build_sentinel_debate_prompt(sentinel_output: dict, oracle_text: str) -> str:
    schema = {
        "type": "object",
        "required": ["portfolio_var_95", "concentration_risk", "max_single_position_pct",
                     "market_regime", "confidence", "alerts"],
        "properties": {
            "portfolio_var_95": {"type": "number"},
            "concentration_risk": {"type": "number"},
            "max_single_position_pct": {"type": "number"},
            "market_regime": {"type": "string"},
            "confidence": {"type": "number"},
            "alerts": {"type": "array", "items": {"type": "string"}},
        },
    }
    return f"""You are Sentinel (risk agent). Re-evaluate your risk assessment after reviewing Oracle's signals.
Either converge (reduce alerts if Oracle's reasoning is sound) or defend (maintain warnings with justification).

Your previous risk assessment:
{json.dumps(sentinel_output, indent=2)}

Oracle analyst signals:
{oracle_text}{_json_schema_footer(schema)}"""


# ─────────────────────────────────────────────────────────────
# Scribe
# ─────────────────────────────────────────────────────────────

SCRIBE_SCHEMA = {
    "type": "object",
    "required": ["executive_summary", "synthesized_recommendation", "market_regime",
                 "stop_loss_suggested", "target_allocation_shift"],
    "properties": {
        "executive_summary": {"type": "string"},
        "synthesized_recommendation": {"type": "string"},
        "market_regime": {"type": "string", "enum": ["BULLISH", "BEARISH", "VOLATILE", "NEUTRAL"]},
        "stop_loss_suggested": {"type": "boolean"},
        "target_allocation_shift": {"type": "string"},
    },
}


def build_scribe_prompt(
    oracle_signals: list,
    sentinel_risk: dict,
    sage_scenarios: list,
    sentiment_data: list | None = None,
    fundamental_data: list | None = None,
    options_flow_data: list | None = None,
    critic_notes: list[str] | None = None,
    macro_context: str = "",
) -> str:
    macro_section = f"\n\nMacro Context:\n{macro_context}" if macro_context else ""
    sentiment_section = (
        f"\n\nSentiment Analysis:\n{json.dumps(sentiment_data, indent=2)}"
        if sentiment_data else ""
    )
    fundamental_section = (
        f"\n\nFundamental Data:\n{json.dumps(fundamental_data, indent=2)}"
        if fundamental_data else ""
    )
    options_section = (
        f"\n\nOptions Flow:\n{json.dumps(options_flow_data, indent=2)}"
        if options_flow_data else ""
    )
    critic_section = (
        f"\n\nCritic Notes (address these in your summary):\n" + "\n".join(f"- {n}" for n in critic_notes)
        if critic_notes else ""
    )

    return f"""You are Scribe, the synthesis agent for an Indian multi-agent investment research system.
Synthesize ALL agent findings into a coherent narrative for a retail investor.
Explicitly surface: disagreements between agents, low-confidence signals, tax implications, missing data gaps.
Do NOT ignore conflicts — name them. Be specific, concise, and actionable.{macro_section}

Oracle Signals:
{json.dumps(oracle_signals, default=str, indent=2)}

Sentinel Risk Assessment:
{json.dumps(sentinel_risk, default=str, indent=2)}

Sage Tax & Scenarios:
{json.dumps(sage_scenarios, default=str, indent=2)}{sentiment_section}{fundamental_section}{options_section}{critic_section}{_json_schema_footer(SCRIBE_SCHEMA)}"""


# ─────────────────────────────────────────────────────────────
# Sentiment Agent
# ─────────────────────────────────────────────────────────────

SENTIMENT_SCHEMA = {
    "type": "object",
    "required": ["sentiment_score", "verdict", "key_themes"],
    "properties": {
        "sentiment_score": {"type": "number", "minimum": -1.0, "maximum": 1.0},
        "verdict": {"type": "string", "enum": ["STRONGLY_POSITIVE", "POSITIVE", "NEUTRAL",
                                                "NEGATIVE", "STRONGLY_NEGATIVE"]},
        "key_themes": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
    },
}


def build_sentiment_prompt(symbol: str, headlines: list[str]) -> str:
    headlines_text = "\n".join(f"- {h}" for h in headlines[:20])
    return f"""You are a financial sentiment analyst specializing in the Indian stock market.
Analyze these recent news headlines about {symbol} and return a sentiment assessment.
Score: -1.0 = extremely bearish, 0.0 = neutral, 1.0 = extremely bullish.
Focus on: earnings, management actions, regulatory news, sector tailwinds/headwinds.

Headlines:
{headlines_text}{_json_schema_footer(SENTIMENT_SCHEMA)}"""


# ─────────────────────────────────────────────────────────────
# Fundamental Agent
# ─────────────────────────────────────────────────────────────

FUNDAMENTAL_SCHEMA = {
    "type": "object",
    "required": ["valuation_verdict", "valuation_commentary"],
    "properties": {
        "valuation_verdict": {"type": "string", "enum": ["OVERVALUED", "FAIR", "UNDERVALUED"]},
        "valuation_commentary": {"type": "string"},
    },
}


def build_fundamental_prompt(symbol: str, fundamental_data: dict) -> str:
    return f"""You are a fundamental analyst covering Indian equities.
Assess the valuation of {symbol} based on the following data.
Compare stock P/E vs sector P/E. Consider promoter holding as a governance signal.

Fundamental Data:
{json.dumps(fundamental_data, indent=2)}{_json_schema_footer(FUNDAMENTAL_SCHEMA)}"""


# ─────────────────────────────────────────────────────────────
# Critic Agent
# ─────────────────────────────────────────────────────────────

CRITIC_SCHEMA = {
    "type": "object",
    "required": ["passed", "score", "notes"],
    "properties": {
        "passed": {"type": "boolean"},
        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}


def build_critic_prompt(scribe_output: dict, sentinel_output: dict, sage_outputs: list) -> str:
    return f"""You are the Critic agent — an independent auditor of the Scribe's recommendation.
Your job is to catch errors, inconsistencies, and omissions. Be rigorous.

Check:
1. Is the confidence level consistent with Sentinel's VaR and risk alerts?
2. Are Sage's tax implications correctly reflected in the recommendation?
3. If any agent failed/was missing, does the summary properly caveat this?
4. Is the recommendation actionable and specific (not vague platitudes)?
5. Does the executive summary address all material agent disagreements?

Score 0.0-1.0: 0.8+ = pass. Below 0.6 = fail (Scribe must revise).

Scribe Output:
{json.dumps(scribe_output, indent=2)}

Sentinel Risk Data:
{json.dumps(sentinel_output, indent=2)}

Sage Scenarios:
{json.dumps(sage_outputs, indent=2)}{_json_schema_footer(CRITIC_SCHEMA)}"""


# ─────────────────────────────────────────────────────────────
# Legacy aliases (kept for backwards compatibility)
# ─────────────────────────────────────────────────────────────

ORACLE_PROMPT_TEMPLATE = """{holding_data}\n{quote_data}"""  # replaced by build_oracle_prompt
SCRIBE_PROMPT_TEMPLATE = """{oracle_signals}\n{sentinel_risk}\n{sage_scenarios}"""  # replaced by build_scribe_prompt
