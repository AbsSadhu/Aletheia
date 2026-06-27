from __future__ import annotations

import logging
from aletheia.core.models import (
    Holding,
    MarketQuote,
    OracleOutput,
    SentinelOutput,
    MultiTimeframeSignal,
)
from aletheia.core.llm.client import OllamaClient
from aletheia.core.llm.prompts import build_oracle_prompt
from aletheia.core.llm.parsers import OracleLLMOutput
from aletheia.core.config.settings import get_settings

logger = logging.getLogger(__name__)


class OracleAgent:
    def __init__(self, duckdb_store=None, compute_client=None):
        self.settings = get_settings()
        self.llm_client = OllamaClient(base_url=self.settings.ollama_base_url)
        self.duckdb_store = duckdb_store
        self.compute_client = compute_client

    async def analyze(
        self,
        holding: Holding,
        quote: MarketQuote,
        macro_context_text: str = "",
    ) -> OracleOutput:
        momentum_pct = (
            (quote.close - (quote.open or quote.close)) / max((quote.open or quote.close), 1e-6)
        ) * 100
        fair_value_gap_pct = (
            (quote.close - holding.average_price) / max(holding.average_price, 1e-6)
        ) * 100

        # F1. Multi-timeframe signals (1D / 1W / 1M)
        multi_tf_data, closes = await self._compute_multi_timeframe(holding.symbol, quote)

        # Determine timeframe agreement
        sig1d = multi_tf_data.get("1D", {}).get("signal", "HOLD")
        sig1w = multi_tf_data.get("1W", {}).get("signal", "HOLD")
        sig1m = multi_tf_data.get("1M", {}).get("signal", "HOLD")
        signals_list = [sig1d, sig1w, sig1m]

        buy_count = signals_list.count("BUY")
        reduce_count = signals_list.count("REDUCE")
        hold_count = signals_list.count("HOLD")

        if buy_count == 3 or reduce_count == 3 or hold_count == 3:
            tf_agreement = "ALL_AGREE"
        elif buy_count == 2 or reduce_count == 2 or hold_count == 2:
            tf_agreement = "MAJORITY_AGREE"
        elif buy_count == 1 and reduce_count == 1 and hold_count == 1:
            tf_agreement = "SPLIT"
        else:
            tf_agreement = "NO_AGREEMENT"

        # F2. Fama-French exposures
        factor_exposures = await self._compute_factor_exposures(holding.symbol, closes)

        signal = "HOLD"
        confidence = 0.5
        rationale = [
            f"Current price is {fair_value_gap_pct:.2f}% versus average cost.",
            f"Intraday momentum is {momentum_pct:.2f}%.",
            f"Timeframe agreement: {tf_agreement}.",
        ]

        # Call LLM using JSON-mode build_oracle_prompt
        if self.settings.default_llm_provider == "ollama":
            tf_dict = {
                tf: {
                    "signal": val["signal"],
                    "confidence": val["confidence"],
                    "indicators": val["indicators"],
                }
                for tf, val in multi_tf_data.items()
            }
            prompt = build_oracle_prompt(
                holding_data=holding.model_dump(),
                quote_data=quote.model_dump(),
                macro_context=macro_context_text,
                multi_tf_data=tf_dict,
                factor_exposures=factor_exposures,
            )
            llm_result = await self.llm_client.generate_structured(
                prompt=prompt, model=self.settings.default_llm_model
            )
            if llm_result and "signal" in llm_result:
                try:
                    parsed = OracleLLMOutput(**llm_result)
                    signal = parsed.signal.upper()
                    if signal not in ["BUY", "HOLD", "REDUCE"]:
                        signal = "HOLD"
                    confidence = parsed.confidence
                    rationale.append(f"[LLM Insights] {parsed.rationale}")
                except Exception as e:
                    rationale.append(f"[LLM Fallback] Parse error: {e}")
                    signal, confidence = self._heuristic_fallback(
                        fair_value_gap_pct, momentum_pct, rationale
                    )
            else:
                signal, confidence = self._heuristic_fallback(
                    fair_value_gap_pct, momentum_pct, rationale
                )
        else:
            signal, confidence = self._heuristic_fallback(
                fair_value_gap_pct, momentum_pct, rationale
            )

        # F5. High confidence gate
        if signal == "BUY" and confidence > 0.7:
            if buy_count < 2:
                confidence = 0.7
                rationale.append(
                    "[High Confidence Gate] BUY confidence capped at 0.7 due to lack of multi-timeframe alignment."
                )

        tf_models = [
            MultiTimeframeSignal(
                timeframe=tf,
                signal=val["signal"],
                confidence=val["confidence"],
                indicators=val["indicators"],
            )
            for tf, val in multi_tf_data.items()
        ]

        return OracleOutput(
            symbol=holding.symbol.upper(),
            signal=signal,
            confidence=confidence,
            rationale=rationale,
            fair_value_gap_pct=round(fair_value_gap_pct, 2),
            momentum_pct=round(momentum_pct, 2),
            multi_timeframe_signals=tf_models,
            factor_exposures=factor_exposures,
            timeframe_agreement=tf_agreement,
        )

    def _heuristic_fallback(
        self, fair_value_gap_pct: float, momentum_pct: float, rationale: list[str]
    ) -> tuple[str, float]:
        if fair_value_gap_pct > 8 and momentum_pct > 0:
            rationale.append("Price strength and positive momentum support accumulation.")
            return "BUY", 0.74
        elif fair_value_gap_pct < -8 and momentum_pct < 0:
            rationale.append("Weak mark-to-market position and fading momentum suggest caution.")
            return "REDUCE", 0.71
        else:
            rationale.append("Signal remains neutral pending stronger confirmation.")
            return "HOLD", 0.5

    async def _compute_multi_timeframe(
        self, symbol: str, quote: MarketQuote
    ) -> tuple[dict[str, dict], list[float]]:
        closes = []
        if self.duckdb_store:
            try:
                conn = self.duckdb_store._connect()
                rows = conn.execute(
                    "SELECT close FROM market_quotes WHERE symbol = ? ORDER BY as_of DESC LIMIT 150",
                    (symbol.upper(),),
                ).fetchall()
                conn.close()
                closes = [r[0] for r in rows]
            except Exception:
                pass

        if len(closes) < 50:
            try:
                import yfinance as yf

                ticker_sym = (
                    f"{symbol.upper()}.NS" if not symbol.upper().endswith(".NS") else symbol.upper()
                )
                ticker = yf.Ticker(ticker_sym)
                hist = ticker.history(period="6mo")
                if not hist.empty:
                    closes = list(hist["Close"].values)[::-1]
            except Exception:
                pass

        if len(closes) < 10:
            import random

            closes = [quote.close * (1.0 + (random.random() - 0.5) * 0.05) for _ in range(60)]
            closes[0] = quote.close

        sma20 = sum(closes[:20]) / 20 if len(closes) >= 20 else closes[0]
        sig1d = (
            "BUY"
            if closes[0] > sma20 * 1.01
            else ("REDUCE" if closes[0] < sma20 * 0.99 else "HOLD")
        )

        weekly_closes = closes[::5]
        sma10_w = sum(weekly_closes[:10]) / 10 if len(weekly_closes) >= 10 else weekly_closes[0]
        sig1w = (
            "BUY"
            if weekly_closes[0] > sma10_w * 1.01
            else ("REDUCE" if weekly_closes[0] < sma10_w * 0.99 else "HOLD")
        )

        monthly_closes = closes[::20]
        sma3_m = sum(monthly_closes[:3]) / 3 if len(monthly_closes) >= 3 else monthly_closes[0]
        sig1m = (
            "BUY"
            if monthly_closes[0] > sma3_m * 1.01
            else ("REDUCE" if monthly_closes[0] < sma3_m * 0.99 else "HOLD")
        )

        return {
            "1D": {"signal": sig1d, "confidence": 0.7, "indicators": {"sma20": round(sma20, 2)}},
            "1W": {
                "signal": sig1w,
                "confidence": 0.7,
                "indicators": {"sma10_w": round(sma10_w, 2)},
            },
            "1M": {"signal": sig1m, "confidence": 0.7, "indicators": {"sma3_m": round(sma3_m, 2)}},
        }, closes

    async def _compute_factor_exposures(
        self, symbol: str, closes: list[float]
    ) -> dict[str, float] | None:
        if not self.compute_client or len(closes) < 10:
            return None
        try:
            nifty_closes = []
            if self.duckdb_store:
                try:
                    conn = self.duckdb_store._connect()
                    rows = conn.execute(
                        "SELECT close FROM market_quotes WHERE symbol = '^NSEI' ORDER BY as_of DESC LIMIT 150"
                    ).fetchall()
                    conn.close()
                    nifty_closes = [r[0] for r in rows]
                except Exception:
                    pass

            if len(nifty_closes) < 50:
                try:
                    import yfinance as yf

                    ticker = yf.Ticker("^NSEI")
                    hist = ticker.history(period="6mo")
                    if not hist.empty:
                        nifty_closes = list(hist["Close"].values)[::-1]
                except Exception:
                    pass

            if len(nifty_closes) < 10:
                nifty_closes = [22000.0 * (1.0 + (i * 0.001)) for i in range(len(closes))]

            min_len = min(len(closes), len(nifty_closes))
            sub_closes = closes[:min_len]
            sub_nifty = nifty_closes[:min_len]

            symbol_returns = [
                (sub_closes[i] - sub_closes[i + 1]) / sub_closes[i + 1] for i in range(min_len - 1)
            ]
            nifty_returns = [
                (sub_nifty[i] - sub_nifty[i + 1]) / sub_nifty[i + 1] for i in range(min_len - 1)
            ]

            symbol_returns = symbol_returns[::-1]
            nifty_returns = nifty_returns[::-1]

            res = await self.compute_client.factor_model(symbol_returns, nifty_returns)
            return {
                "alpha": res.get("alpha", 0.0),
                "beta": res.get("beta", 1.0),
                "smb_loading": res.get("smb_loading", 0.0),
                "hml_loading": res.get("hml_loading", 0.0),
                "r_squared": res.get("r_squared", 0.0),
            }
        except Exception as exc:
            logger.debug("OracleAgent: factor exposures computation failed: %s", exc)
            return None

    async def debate(
        self, oracle_output: OracleOutput, sentinel_output: SentinelOutput
    ) -> OracleOutput:
        prompt = f"""You are an expert financial analyst. You previously proposed the following signal for a holding:
Symbol: {oracle_output.symbol}
Proposed Signal: {oracle_output.signal}
Confidence: {oracle_output.confidence}
Rationale: {oracle_output.rationale}

However, the Sentinel risk agent has raised the following portfolio risk concerns:
Concentration Risk: {sentinel_output.concentration_risk}
Max Single Position %: {sentinel_output.max_single_position_pct}
Portfolio VaR (95%): {sentinel_output.portfolio_var_95}
Sentinel Alerts: {", ".join(sentinel_output.alerts)}

Please re-evaluate your signal. You can either:
1. Converge: Adjust your signal to HOLD or REDUCE if you agree the risk is too high.
2. Defend: Maintain your BUY signal, but you must lower your confidence score if appropriate or provide a defense.

Output your response strictly in JSON format.
Required JSON Structure:
{{
  "signal": "BUY", // or HOLD or REDUCE
  "confidence": 0.65,
  "rationale": "Updated explanation addressing the Sentinel's risk warnings"
}}"""
        if self.settings.default_llm_provider == "ollama":
            llm_result = await self.llm_client.generate_structured(
                prompt=prompt, model=self.settings.default_llm_model
            )
            if llm_result and "signal" in llm_result:
                try:
                    parsed = OracleLLMOutput(**llm_result)
                    signal = parsed.signal.upper()
                    if signal not in ["BUY", "HOLD", "REDUCE"]:
                        signal = "HOLD"
                    return OracleOutput(
                        symbol=oracle_output.symbol,
                        signal=signal,
                        confidence=parsed.confidence,
                        rationale=oracle_output.rationale
                        + [f"[Debate Node Update] {parsed.rationale}"],
                        fair_value_gap_pct=oracle_output.fair_value_gap_pct,
                        momentum_pct=oracle_output.momentum_pct,
                        multi_timeframe_signals=oracle_output.multi_timeframe_signals,
                        factor_exposures=oracle_output.factor_exposures,
                        timeframe_agreement=oracle_output.timeframe_agreement,
                    )
                except Exception:
                    pass
        return oracle_output
