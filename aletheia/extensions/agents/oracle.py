from __future__ import annotations

import asyncio
import logging

import pandas as pd

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
from aletheia.core.signals.quant import compute_quant_signal, normalize_ohlcv

logger = logging.getLogger(__name__)


class OracleAgent:
    """Signal = deterministic factor composite (see `aletheia.core.signals.quant`).

    The LLM only explains the signal; it never sets or upgrades it. With no
    trustworthy price history the signal is HOLD at confidence 0.
    """

    def __init__(self, duckdb_store=None, compute_client=None, ohlcv_loader=None):
        self.settings = get_settings()
        self.llm_client = OllamaClient(base_url=self.settings.ollama_base_url)
        self.duckdb_store = duckdb_store
        self.compute_client = compute_client
        self._ohlcv_loader = ohlcv_loader or self._yfinance_ohlcv

    @staticmethod
    async def _yfinance_ohlcv(symbol: str) -> pd.DataFrame | None:
        def _fetch() -> pd.DataFrame | None:
            import yfinance as yf

            sym = symbol.upper()
            if not sym.startswith("^") and not sym.endswith((".NS", ".BO")):
                sym = f"{sym}.NS"
            # auto_adjust folds splits/dividends into OHLC so factors see a clean series.
            return yf.Ticker(sym).history(period="2y", interval="1d", auto_adjust=True)

        try:
            return await asyncio.to_thread(_fetch)
        except Exception as exc:
            logger.warning("OracleAgent: price history fetch for %s failed: %s", symbol, exc)
            return None

    async def analyze(
        self,
        holding: Holding,
        quote: MarketQuote,
        macro_context_text: str = "",
    ) -> OracleOutput:
        momentum_pct = (
            (quote.close - (quote.open or quote.close)) / max((quote.open or quote.close), 1e-6)
        ) * 100
        # Unrealised P&L versus the user's cost basis. Informational only: it plays no
        # part in the signal (a stock bought cheaply is not thereby a BUY).
        fair_value_gap_pct = (
            (quote.close - holding.average_price) / max(holding.average_price, 1e-6)
        ) * 100

        ohlcv = normalize_ohlcv(await self._ohlcv_loader(holding.symbol))
        quant = compute_quant_signal(ohlcv)
        multi_tf_data = self._multi_timeframe(ohlcv) if quant.data_quality == "ok" else {}

        sig_list = [multi_tf_data.get(tf, {}).get("signal", "HOLD") for tf in ("1D", "1W", "1M")]
        buy_count = sig_list.count("BUY")
        reduce_count = sig_list.count("REDUCE")
        hold_count = sig_list.count("HOLD")
        if 3 in (buy_count, reduce_count, hold_count):
            tf_agreement = "ALL_AGREE"
        elif 2 in (buy_count, reduce_count, hold_count):
            tf_agreement = "MAJORITY_AGREE"
        elif buy_count == 1 and reduce_count == 1 and hold_count == 1:
            tf_agreement = "SPLIT"
        else:
            tf_agreement = "NO_AGREEMENT"

        signal, confidence = quant.signal, quant.confidence
        rationale = [
            f"Unrealised P&L vs average cost: {fair_value_gap_pct:.2f}%.",
            f"Intraday move: {momentum_pct:.2f}%.",
            f"Factor composite {quant.composite_score:+.2f} -> {signal}.",
            f"Timeframe agreement: {tf_agreement}.",
            *quant.notes,
        ]

        # Trend-alignment gate: a high-confidence BUY needs at least two timeframes agreeing.
        if signal == "BUY" and confidence > 0.7 and buy_count < 2:
            confidence = 0.7
            rationale.append(
                "[High Confidence Gate] BUY confidence capped at 0.7 due to lack of multi-timeframe alignment."
            )

        factor_exposures = (
            await self._compute_factor_exposures(ohlcv) if quant.data_quality == "ok" else None
        )

        if quant.data_quality == "ok":
            rationale.extend(
                await self._llm_explanation(
                    holding, quote, macro_context_text, multi_tf_data, factor_exposures, signal
                )
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
            data_quality=quant.data_quality,
            composite_score=quant.composite_score,
            hit_rate=quant.hit_rate,
            hit_rate_samples=quant.samples,
            stop_loss_price=quant.stop_loss_price,
            target_price=quant.target_price,
        )

    async def _llm_explanation(
        self,
        holding: Holding,
        quote: MarketQuote,
        macro_context_text: str,
        multi_tf_data: dict[str, dict],
        factor_exposures: dict[str, float] | None,
        quant_signal: str,
    ) -> list[str]:
        """Ask the LLM for commentary. Its signal/confidence are discarded; disagreement
        with the quant signal is surfaced, not acted on."""
        if self.settings.default_llm_provider != "ollama":
            return []
        prompt = build_oracle_prompt(
            holding_data=holding.model_dump(),
            quote_data=quote.model_dump(),
            macro_context=macro_context_text,
            multi_tf_data=multi_tf_data,
            factor_exposures=factor_exposures,
        )
        llm_result = await self.llm_client.generate_structured(
            prompt=prompt, model=self.settings.default_llm_model
        )
        if not llm_result or "signal" not in llm_result:
            return []
        try:
            parsed = OracleLLMOutput(**llm_result)
        except Exception as exc:
            return [f"[LLM Fallback] Parse error: {exc}"]
        notes = [f"[LLM Insights] {parsed.rationale}"]
        llm_signal = parsed.signal.upper()
        if llm_signal in ("BUY", "HOLD", "REDUCE") and llm_signal != quant_signal:
            notes.append(
                f"[LLM Dissent] LLM leaned {llm_signal}; quant signal {quant_signal} stands."
            )
        return notes

    @staticmethod
    def _multi_timeframe(ohlcv: pd.DataFrame) -> dict[str, dict]:
        """Close vs its own SMA on daily / weekly / monthly bars (trend strength, not probability)."""
        closes = ohlcv["close"].astype(float)

        def _tf(series: pd.Series, window: int, key: str) -> dict:
            if len(series) < window:
                return {"signal": "HOLD", "confidence": 0.0, "indicators": {}}
            sma = float(series.iloc[-window:].mean())
            last = float(series.iloc[-1])
            dev = last / sma - 1.0
            sig = "BUY" if dev > 0.01 else ("REDUCE" if dev < -0.01 else "HOLD")
            return {
                "signal": sig,
                "confidence": round(min(1.0, abs(dev) * 10), 2),
                "indicators": {key: round(sma, 2)},
            }

        weekly = closes.resample("W").last().dropna()
        monthly = closes.resample("MS").last().dropna()
        return {
            "1D": _tf(closes, 20, "sma20"),
            "1W": _tf(weekly, 10, "sma10_w"),
            "1M": _tf(monthly, 3, "sma3_m"),
        }

    async def _compute_factor_exposures(self, ohlcv: pd.DataFrame) -> dict[str, float] | None:
        if not self.compute_client:
            return None
        try:
            bench = normalize_ohlcv(await self._ohlcv_loader("^NSEI"))
            if bench is None:
                logger.info("OracleAgent: no NIFTY history — factor exposures skipped.")
                return None
            rets = pd.concat(
                [
                    ohlcv["close"].pct_change().rename("s"),
                    bench["close"].pct_change().rename("b"),
                ],
                axis=1,
                join="inner",
            ).dropna()
            if len(rets) < 30:
                return None
            res = await self.compute_client.factor_model(rets["s"].tolist(), rets["b"].tolist())
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
                    # Debate may de-risk (lower the signal or confidence), never upgrade.
                    rank = {"REDUCE": 0, "HOLD": 1, "BUY": 2}
                    if rank[signal] > rank.get(oracle_output.signal, 1):
                        signal = oracle_output.signal
                    return oracle_output.model_copy(
                        update={
                            "signal": signal,
                            "confidence": min(parsed.confidence, oracle_output.confidence),
                            "rationale": oracle_output.rationale
                            + [f"[Debate Node Update] {parsed.rationale}"],
                        }
                    )
                except Exception as exc:
                    logger.debug("OracleAgent: debate-node LLM response parse failed: %s", exc)
        return oracle_output
