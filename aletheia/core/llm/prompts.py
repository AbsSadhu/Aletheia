"""
Prompt templates for LLM generation
"""

ORACLE_PROMPT_TEMPLATE = """
You are an expert financial analyst. Analyze the following portfolio holding and market conditions.
Output your analysis strictly in JSON format.

Holding Data:
{holding_data}

Market Data:
{quote_data}

Based on technical momentum, recent price changes, and drift from target allocation, determine the signal (BUY, HOLD, or REDUCE).
Also provide a confidence score (0 to 1) and a short rationale.

Required JSON Structure:
{{
  "signal": "BUY", // or HOLD or REDUCE
  "confidence": 0.85,
  "rationale": "Brief explanation"
}}
"""

SCRIBE_PROMPT_TEMPLATE = """
You are a senior wealth manager. Synthesize the findings from the Oracle, Sentinel, and Sage agents into a cohesive summary.
Output your analysis strictly in JSON format.

Oracle Signals:
{oracle_signals}

Sentinel Risk Assessment:
{sentinel_risk}

Sage Tax & Scenarios:
{sage_scenarios}

Create an executive summary, identify the overall market regime, and synthesize a clear recommendation.

Required JSON Structure:
{{
  "executive_summary": "Overall summary of the portfolio health and actions.",
  "synthesized_recommendation": "Specific actionable advice.",
  "market_regime": "BULLISH", // or BEARISH, VOLATILE, NEUTRAL
  "stop_loss_suggested": true,
  "target_allocation_shift": "Shift 5% from Equity to Fixed Income"
}}
"""
