import asyncio
import logging
import operator
import time
from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from aletheia.core.models import (
    AgentName,
    AgentEvent,
    CollectorOutput,
    OracleOutput,
    SageOutput,
    SentinelOutput,
    ScribeOutput,
    SentimentOutput,
    FundamentalOutput,
    OptionsFlowOutput,
    CriticVerdict,
    Portfolio,
    MarketQuote,
    RunStatus,
)
from aletheia.core.llm.chat_llm import LLMRouter
from aletheia.core.llm.client import OllamaClient

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    run_id: str
    portfolio: Optional[Portfolio]
    prompt: str
    collector_outputs: List[CollectorOutput]
    quotes_by_symbol: Dict[str, MarketQuote]
    oracle_outputs: List[OracleOutput]
    sage_outputs: List[SageOutput]
    sentinel_output: Optional[SentinelOutput]
    scribe_output: Optional[ScribeOutput]
    sentiment_outputs: List[SentimentOutput]
    fundamental_outputs: List[FundamentalOutput]
    options_flow_outputs: List[OptionsFlowOutput]
    critic_verdict: Optional[CriticVerdict]
    macro_context_text: str
    insights: List[str]
    error: Optional[str]
    traces: Annotated[List[Dict[str, Any]], operator.add]
    agent_statuses: Dict[str, str]
    debate_disagreements: Annotated[List[str], operator.add]
    portfolio_manager_overrides: Annotated[List[str], operator.add]


def _get_new_llm_calls(start_time: float) -> list[dict[str, Any]]:
    calls = []
    for call in LLMRouter._call_history:
        if call["timestamp"] >= start_time:
            calls.append({
                "provider": call["provider"],
                "model": call["model"],
                "input_tokens": call["input_tokens"],
                "output_tokens": call["output_tokens"],
                "latency_secs": call["latency_secs"],
                "cost_usd": call["cost_usd"],
            })
    for call in OllamaClient._call_history:
        if call["timestamp"] >= start_time:
            calls.append({
                "provider": call["provider"],
                "model": call["model"],
                "input_tokens": call["input_tokens"],
                "output_tokens": call["output_tokens"],
                "latency_secs": call["latency_secs"],
                "cost_usd": call["cost_usd"],
            })
    return calls


def create_agent_graph(run_service: Any, enabled_agents: List[str] | None = None) -> Any:
    """Creates and compiles a LangGraph StateGraph bound to the given RunService instance."""

    def make_resilient_node(agent_name: str, node_func: Any, fallback_updates: Dict[str, Any]) -> Any:
        async def wrapped_node(state: AgentState) -> Dict[str, Any]:
            run_id = state["run_id"]
            start_time = time.time()
            
            state["agent_statuses"][agent_name] = "running"
            await run_service.update_run_progress(run_id, state, status=RunStatus.RUNNING)
            
            timeout = getattr(run_service.settings, "node_timeout_secs", 30)
            
            try:
                updates = await asyncio.wait_for(node_func(state), timeout=timeout)
                state["agent_statuses"][agent_name] = "completed"
                
                merged_state = {**state, **updates}
                await run_service.update_run_progress(run_id, merged_state, status=RunStatus.RUNNING)
                return updates
            except Exception as exc:
                logger.error("Node %s failed: %r", agent_name, exc, exc_info=True)
                state["agent_statuses"][agent_name] = "failed"
                
                duration = time.time() - start_time
                span = {
                    "node": agent_name,
                    "start_time": start_time,
                    "end_time": time.time(),
                    "duration": duration,
                    "llm_calls": [],
                    "error": str(exc),
                }
                
                merged_fallback = dict(fallback_updates)
                if "traces" in merged_fallback:
                    merged_fallback["traces"].append(span)
                else:
                    merged_fallback["traces"] = [span]
                
                try:
                    await run_service.record_event(
                        AgentEvent(
                            run_id=run_id,
                            agent=AgentName(agent_name),
                            message=f"Node execution failed or timed out: {exc}",
                        )
                    )
                except Exception:
                    pass
                
                merged_state = {**state, **merged_fallback}
                await run_service.update_run_progress(run_id, merged_state, status=RunStatus.PARTIAL)
                return merged_fallback

        return wrapped_node

    async def collect_node(state: AgentState) -> Dict[str, Any]:
        start_time = time.time()
        portfolio = state["portfolio"]
        run_id = state["run_id"]
        if not portfolio:
            return {"traces": [{
                "node": "collect",
                "start_time": start_time,
                "end_time": time.time(),
                "duration": time.time() - start_time,
                "llm_calls": [],
            }]}

        outputs = []
        for holding in portfolio.holdings:
            await run_service.record_event(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName.COLLECTOR,
                    message=f"Fetching market data for {holding.symbol}",
                )
            )
            output = await run_service.collector.collect_for_holding(holding)
            outputs.append(output)
            run_service.duckdb_store.persist_quotes(output.quotes)
            await run_service.record_event(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName.COLLECTOR,
                    message=f"Completed collection using {output.provider_used}",
                    payload=output.model_dump(mode="json"),
                )
            )

        quotes_by_symbol = run_service._quotes_by_symbol(outputs)
        end_time = time.time()
        span = {
            "node": "collect",
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "llm_calls": _get_new_llm_calls(start_time),
        }
        return {"collector_outputs": outputs, "quotes_by_symbol": quotes_by_symbol, "traces": [span]}

    async def oracle_node(state: AgentState) -> Dict[str, Any]:
        start_time = time.time()
        portfolio = state["portfolio"]
        quotes_by_symbol = state.get("quotes_by_symbol") or {}
        run_id = state["run_id"]
        if not portfolio or not quotes_by_symbol:
            return {"traces": [{
                "node": "oracle",
                "start_time": start_time,
                "end_time": time.time(),
                "duration": time.time() - start_time,
                "llm_calls": [],
            }]}

        oracle_outputs = []
        for holding in portfolio.holdings:
            quote = quotes_by_symbol.get(holding.symbol.upper())
            if quote is None:
                continue
            oracle_output = await run_service.oracle.analyze(
                holding, quote, macro_context_text=state.get("macro_context_text", "")
            )
            oracle_outputs.append(oracle_output)
            await run_service.record_event(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName.ORACLE,
                    message=f"{holding.symbol}: {oracle_output.signal} with confidence {oracle_output.confidence:.2f}",
                    payload=oracle_output.model_dump(mode="json"),
                )
            )
        end_time = time.time()
        span = {
            "node": "oracle",
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "llm_calls": _get_new_llm_calls(start_time),
        }
        return {"oracle_outputs": oracle_outputs, "traces": [span]}

    async def sentinel_node(state: AgentState) -> Dict[str, Any]:
        start_time = time.time()
        portfolio = state["portfolio"]
        quotes_by_symbol = state.get("quotes_by_symbol") or {}
        run_id = state["run_id"]
        if not portfolio or not quotes_by_symbol:
            return {"traces": [{
                "node": "sentinel",
                "start_time": start_time,
                "end_time": time.time(),
                "duration": time.time() - start_time,
                "llm_calls": [],
            }]}

        sentinel_output = await run_service.sentinel.assess(
            portfolio, quotes_by_symbol, macro_context_text=state.get("macro_context_text", "")
        )
        await run_service.record_event(
            AgentEvent(
                run_id=run_id,
                agent=AgentName.SENTINEL,
                message=(
                    f"Portfolio VaR95 {sentinel_output.portfolio_var_95:.2f}, "
                    f"max position {sentinel_output.max_single_position_pct:.2f}%"
                ),
                payload=sentinel_output.model_dump(mode="json"),
            )
        )
        end_time = time.time()
        span = {
            "node": "sentinel",
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "llm_calls": _get_new_llm_calls(start_time),
        }
        return {"sentinel_output": sentinel_output, "traces": [span]}

    async def sentiment_node(state: AgentState) -> Dict[str, Any]:
        start_time = time.time()
        portfolio = state["portfolio"]
        run_id = state["run_id"]
        if not portfolio:
            return {"traces": [{
                "node": "sentiment",
                "start_time": start_time,
                "end_time": time.time(),
                "duration": 0.0,
                "llm_calls": [],
            }]}
        
        sentiment_outputs = []
        for holding in portfolio.holdings:
            await run_service.record_event(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName.SENTIMENT,
                    message=f"Analyzing sentiment for {holding.symbol}",
                )
            )
            output = await run_service.sentiment.analyze(holding.symbol)
            sentiment_outputs.append(output)
            await run_service.record_event(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName.SENTIMENT,
                    message=f"{holding.symbol}: sentiment score {output.sentiment_score} ({output.verdict})",
                    payload=output.model_dump(mode="json"),
                )
            )
        
        end_time = time.time()
        span = {
            "node": "sentiment",
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "llm_calls": _get_new_llm_calls(start_time),
        }
        return {"sentiment_outputs": sentiment_outputs, "traces": [span]}

    async def fundamental_node(state: AgentState) -> Dict[str, Any]:
        start_time = time.time()
        portfolio = state["portfolio"]
        run_id = state["run_id"]
        if not portfolio:
            return {"traces": [{
                "node": "fundamental",
                "start_time": start_time,
                "end_time": time.time(),
                "duration": 0.0,
                "llm_calls": [],
            }]}
        
        fundamental_outputs = []
        for holding in portfolio.holdings:
            await run_service.record_event(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName.FUNDAMENTAL,
                    message=f"Analyzing fundamentals for {holding.symbol}",
                )
            )
            output = await run_service.fundamental.analyze(holding.symbol)
            fundamental_outputs.append(output)
            await run_service.record_event(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName.FUNDAMENTAL,
                    message=f"{holding.symbol}: P/E={output.pe_ratio or 'N/A'}, valuation={output.valuation_verdict}",
                    payload=output.model_dump(mode="json"),
                )
            )
        
        end_time = time.time()
        span = {
            "node": "fundamental",
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "llm_calls": _get_new_llm_calls(start_time),
        }
        return {"fundamental_outputs": fundamental_outputs, "traces": [span]}

    async def options_flow_node(state: AgentState) -> Dict[str, Any]:
        start_time = time.time()
        portfolio = state["portfolio"]
        run_id = state["run_id"]
        if not portfolio:
            return {"traces": [{
                "node": "options_flow",
                "start_time": start_time,
                "end_time": time.time(),
                "duration": 0.0,
                "llm_calls": [],
            }]}
        
        options_flow_outputs = []
        for holding in portfolio.holdings:
            await run_service.record_event(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName.OPTIONS_FLOW,
                    message=f"Analyzing options flow for {holding.symbol}",
                )
            )
            output = await run_service.options_flow.analyze(holding.symbol)
            options_flow_outputs.append(output)
            await run_service.record_event(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName.OPTIONS_FLOW,
                    message=f"{holding.symbol}: PCR={output.put_call_ratio:.2f}, IV rank={output.iv_rank:.1f}",
                    payload=output.model_dump(mode="json"),
                )
            )
        
        end_time = time.time()
        span = {
            "node": "options_flow",
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "llm_calls": _get_new_llm_calls(start_time),
        }
        return {"options_flow_outputs": options_flow_outputs, "traces": [span]}

    async def sage_node(state: AgentState) -> Dict[str, Any]:
        start_time = time.time()
        portfolio = state["portfolio"]
        quotes_by_symbol = state.get("quotes_by_symbol") or {}
        oracle_outputs = state.get("oracle_outputs") or []
        run_id = state["run_id"]
        if not portfolio or not quotes_by_symbol:
            return {"traces": [{
                "node": "sage",
                "start_time": start_time,
                "end_time": time.time(),
                "duration": time.time() - start_time,
                "llm_calls": [],
            }]}

        oracle_by_symbol = {o.symbol: o for o in oracle_outputs}
        sage_outputs = []
        for holding in portfolio.holdings:
            quote = quotes_by_symbol.get(holding.symbol.upper())
            oracle_output = oracle_by_symbol.get(holding.symbol.upper())
            if quote is None or oracle_output is None:
                continue
            sage_output = await run_service.sage.backtest(holding, quote, oracle_output)
            sage_outputs.append(sage_output)
            await run_service.record_event(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName.SAGE,
                    message=(
                        f"{holding.symbol}: projected post-tax return "
                        f"{sage_output.scenario.projected_post_tax_return_pct:.2f}%"
                    ),
                    payload=sage_output.model_dump(mode="json"),
                )
            )
        end_time = time.time()
        span = {
            "node": "sage",
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "llm_calls": _get_new_llm_calls(start_time),
        }
        return {"sage_outputs": sage_outputs, "traces": [span]}

    async def debate_node(state: AgentState) -> Dict[str, Any]:
        start_time = time.time()
        oracle_outputs = state.get("oracle_outputs") or []
        sentinel_output = state.get("sentinel_output")
        run_id = state["run_id"]

        if not oracle_outputs or not sentinel_output:
            return {"traces": [{
                "node": "debate",
                "start_time": start_time,
                "end_time": time.time(),
                "duration": time.time() - start_time,
                "llm_calls": [],
            }]}

        has_confident_buy = any(o.signal == "BUY" and o.confidence >= 0.7 for o in oracle_outputs)
        has_sentinel_risk = (
            sentinel_output.concentration_risk >= 0.4
            or sentinel_output.max_single_position_pct >= 40.0
            or len(sentinel_output.alerts) > 0
        )
        disagree = has_confident_buy and has_sentinel_risk

        new_oracle_outputs = list(oracle_outputs)
        new_sentinel_output = sentinel_output
        debate_disagreements = []

        if disagree:
            await run_service.record_event(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName.DEBATE,
                    message="Material disagreement detected between Oracle and Sentinel. Starting debate.",
                )
            )
            debated_oracles = []
            for o in oracle_outputs:
                if o.signal == "BUY" and o.confidence >= 0.7:
                    updated_oracle = await run_service.oracle.debate(o, sentinel_output)
                    debated_oracles.append(updated_oracle)
                else:
                    debated_oracles.append(o)
            new_oracle_outputs = debated_oracles

            new_sentinel_output = await run_service.sentinel.debate(sentinel_output, oracle_outputs)

            any_buy_left = any(o.signal == "BUY" for o in new_oracle_outputs)
            any_alerts_left = len(new_sentinel_output.alerts) > 0

            if any_buy_left and any_alerts_left:
                msg = "Oracle maintains BUY signal despite Sentinel risk warnings."
                debate_disagreements.append(msg)
                await run_service.record_event(
                    AgentEvent(
                        run_id=run_id,
                        agent=AgentName.DEBATE,
                        message="Debate completed: unresolved disagreement registered.",
                    )
                )
            else:
                await run_service.record_event(
                    AgentEvent(
                        run_id=run_id,
                        agent=AgentName.DEBATE,
                        message="Debate completed: consensus achieved.",
                    )
                )

        end_time = time.time()
        span = {
            "node": "debate",
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "llm_calls": _get_new_llm_calls(start_time),
        }
        return {
            "oracle_outputs": new_oracle_outputs,
            "sentinel_output": new_sentinel_output,
            "debate_disagreements": debate_disagreements,
            "traces": [span],
        }

    async def portfolio_manager_node(state: AgentState) -> Dict[str, Any]:
        start_time = time.time()
        portfolio = state["portfolio"]
        quotes_by_symbol = state.get("quotes_by_symbol") or {}
        oracle_outputs = state.get("oracle_outputs") or []
        sentinel_output = state.get("sentinel_output")
        run_id = state["run_id"]

        if not portfolio:
            return {"traces": [{
                "node": "portfolio_manager",
                "start_time": start_time,
                "end_time": time.time(),
                "duration": time.time() - start_time,
                "llm_calls": [],
            }]}

        from aletheia.core.risk.metrics import portfolio_market_values
        mkt_values = portfolio_market_values(portfolio, quotes_by_symbol)
        total_value = sum(mkt_values.values()) or 1.0

        max_pos_limit = run_service.settings.pm_max_position_size_pct
        max_sector_limit = run_service.settings.pm_max_sector_concentration_pct
        max_var_limit = run_service.settings.pm_max_portfolio_var_pct

        pm_overrides = []
        new_oracle_outputs = []
        for o in oracle_outputs:
            o_copy = o.model_copy()
            try:
                score = run_service.sqlite_store.get_calibration_score(o.symbol, "oracle")
                if score is not None and score > 0.25:
                    logger.warning(
                        "PM: Symbol %s Oracle is poorly calibrated (Brier score = %.2f > 0.25). Reducing confidence.",
                        o.symbol, score
                    )
                    o_copy.confidence = round(o_copy.confidence * 0.7, 2)
                    o_copy.rationale.append(
                        f"[PM Calibration Warning] Oracle confidence reduced by 30% due to poor historical calibration (Brier score = {score:.2f})."
                    )
            except Exception as e:
                logger.debug("PM: Failed to query calibration: %s", e)
            new_oracle_outputs.append(o_copy)

        # 1. VaR limit check
        var_pct = 0.0
        if sentinel_output:
            var_pct = abs(sentinel_output.portfolio_var_95) / total_value * 100
            if var_pct > max_var_limit:
                for idx, o in enumerate(new_oracle_outputs):
                    if o.signal == "BUY":
                        msg = (
                            f"[PM OVERRIDE] Portfolio VaR ({var_pct:.2f}%) exceeds max limit ({max_var_limit}%). "
                            f"BUY for {o.symbol} overridden to HOLD."
                        )
                        pm_overrides.append(msg)
                        await run_service.record_event(
                            AgentEvent(
                                run_id=run_id,
                                agent=AgentName.PORTFOLIO_MANAGER,
                                message=msg,
                            )
                        )
                        new_oracle_outputs[idx] = OracleOutput(
                            symbol=o.symbol,
                            signal="HOLD",
                            confidence=o.confidence,
                            rationale=o.rationale + [f"[PM Override] {msg}"],
                            fair_value_gap_pct=o.fair_value_gap_pct,
                            momentum_pct=o.momentum_pct,
                        )

        # 2. Sector concentration check
        sector_values = {}
        for holding in portfolio.holdings:
            symbol = holding.symbol.upper()
            if symbol not in mkt_values:
                continue
            sector = getattr(holding, "sector", "Technology")
            sector_values[sector] = sector_values.get(sector, 0.0) + mkt_values[symbol]

        for idx, o in enumerate(new_oracle_outputs):
            if o.signal != "BUY":
                continue
            holding = next((h for h in portfolio.holdings if h.symbol.upper() == o.symbol), None)
            if not holding:
                continue
            sector = getattr(holding, "sector", "Technology")
            sector_val = sector_values.get(sector, 0.0)
            sector_pct = sector_val / total_value * 100
            if sector_pct > max_sector_limit:
                msg = (
                    f"[PM OVERRIDE] Sector '{sector}' concentration ({sector_pct:.2f}%) exceeds max limit ({max_sector_limit}%). "
                    f"BUY for {o.symbol} overridden to HOLD."
                )
                pm_overrides.append(msg)
                await run_service.record_event(
                    AgentEvent(
                        run_id=run_id,
                        agent=AgentName.PORTFOLIO_MANAGER,
                        message=msg,
                    )
                )
                new_oracle_outputs[idx] = OracleOutput(
                    symbol=o.symbol,
                    signal="HOLD",
                    confidence=o.confidence,
                    rationale=o.rationale + [f"[PM Override] {msg}"],
                    fair_value_gap_pct=o.fair_value_gap_pct,
                    momentum_pct=o.momentum_pct,
                )

        # 3. Max position size check
        for idx, o in enumerate(new_oracle_outputs):
            if o.signal != "BUY":
                continue
            val = mkt_values.get(o.symbol, 0.0)
            pos_pct = val / total_value * 100
            if pos_pct > max_pos_limit:
                msg = (
                    f"[PM OVERRIDE] Position size for {o.symbol} ({pos_pct:.2f}%) exceeds max limit ({max_pos_limit}%). "
                    f"BUY overridden to HOLD."
                )
                pm_overrides.append(msg)
                await run_service.record_event(
                    AgentEvent(
                        run_id=run_id,
                        agent=AgentName.PORTFOLIO_MANAGER,
                        message=msg,
                    )
                )
                new_oracle_outputs[idx] = OracleOutput(
                    symbol=o.symbol,
                    signal="HOLD",
                    confidence=o.confidence,
                    rationale=o.rationale + [f"[PM Override] {msg}"],
                    fair_value_gap_pct=o.fair_value_gap_pct,
                    momentum_pct=o.momentum_pct,
                )

        end_time = time.time()
        span = {
            "node": "portfolio_manager",
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "llm_calls": [],
        }
        return {
            "oracle_outputs": new_oracle_outputs,
            "portfolio_manager_overrides": pm_overrides,
            "traces": [span],
        }

    async def scribe_node(state: AgentState) -> Dict[str, Any]:
        start_time = time.time()
        oracle_outputs = state.get("oracle_outputs") or []
        sentinel_output = state.get("sentinel_output")
        sage_outputs = state.get("sage_outputs") or []
        run_id = state["run_id"]
        portfolio = state["portfolio"]
        collector_outputs = state.get("collector_outputs") or []

        sentiment_outputs = state.get("sentiment_outputs") or []
        fundamental_outputs = state.get("fundamental_outputs") or []
        options_flow_outputs = state.get("options_flow_outputs") or []
        critic_verdict = state.get("critic_verdict")
        
        critic_notes = critic_verdict.notes if critic_verdict else []
        critic_passed = critic_verdict.passed if critic_verdict else True
        macro_context_text = state.get("macro_context_text", "")

        scribe_output = await run_service.scribe.synthesize(
            oracle_outputs,
            sentinel_output,
            sage_outputs,
            agent_statuses=state.get("agent_statuses"),
            portfolio_manager_overrides=state.get("portfolio_manager_overrides"),
            debate_disagreements=state.get("debate_disagreements"),
            sentiment_outputs=sentiment_outputs,
            fundamental_outputs=fundamental_outputs,
            options_flow_outputs=options_flow_outputs,
            critic_notes=critic_notes,
            critic_passed=critic_passed,
            macro_context_text=macro_context_text,
        )
        await run_service.record_event(
            AgentEvent(
                run_id=run_id,
                agent=AgentName.SCRIBE,
                message=f"Synthesis complete with {scribe_output.agreement_level} agreement.",
                payload=scribe_output.model_dump(mode="json"),
            )
        )

        insights = run_service._build_initial_insights(
            portfolio,
            collector_outputs,
            oracle_outputs,
            sentinel_output,
            sage_outputs,
            scribe_output,
        )
        end_time = time.time()
        span = {
            "node": "scribe",
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "llm_calls": _get_new_llm_calls(start_time),
        }
        return {"scribe_output": scribe_output, "insights": insights, "traces": [span]}

    async def critic_node(state: AgentState) -> Dict[str, Any]:
        start_time = time.monotonic()
        scribe_output = state.get("scribe_output")
        sentinel_output = state.get("sentinel_output")
        sage_outputs = state.get("sage_outputs") or []
        run_id = state["run_id"]
        
        if not scribe_output:
            return {"traces": [{
                "node": "critic",
                "start_time": start_time,
                "end_time": time.monotonic(),
                "duration": 0.0,
                "llm_calls": [],
            }]}
            
        previous_verdict = state.get("critic_verdict")
        iteration = (previous_verdict.iteration + 1) if previous_verdict else 1
        
        await run_service.record_event(
            AgentEvent(
                run_id=run_id,
                agent=AgentName.CRITIC,
                message=f"Auditing Scribe output (iteration {iteration})",
            )
        )
        
        verdict = await run_service.critic.audit(
            scribe_output=scribe_output,
            sentinel_output=sentinel_output.model_dump() if sentinel_output else None,
            sage_outputs=[s.model_dump() for s in sage_outputs],
            iteration=iteration,
        )
        
        await run_service.record_event(
            AgentEvent(
                run_id=run_id,
                agent=AgentName.CRITIC,
                message=f"Audit complete: passed={verdict.passed}, score={verdict.score:.2f}",
                payload=verdict.model_dump(mode="json"),
            )
        )
        
        end_time = time.monotonic()
        span = {
            "node": "critic",
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "llm_calls": _get_new_llm_calls(start_time),
        }
        return {"critic_verdict": verdict, "traces": [span]}

    node_map = {
        "collector": ("collect", collect_node, {"collector_outputs": [], "quotes_by_symbol": {}}),
        "oracle": ("oracle", oracle_node, {"oracle_outputs": []}),
        "sentinel": ("sentinel", sentinel_node, {"sentinel_output": None}),
        "debate": ("debate", debate_node, {"oracle_outputs": [], "debate_disagreements": []}),
        "sage": ("sage", sage_node, {"sage_outputs": []}),
        "portfolio_manager": ("portfolio_manager", portfolio_manager_node, {"oracle_outputs": [], "portfolio_manager_overrides": []}),
        "scribe": ("scribe", scribe_node, {"scribe_output": None, "insights": []}),
        "sentiment": ("sentiment", sentiment_node, {"sentiment_outputs": []}),
        "fundamental": ("fundamental", fundamental_node, {"fundamental_outputs": []}),
        "options_flow": ("options_flow", options_flow_node, {"options_flow_outputs": []}),
        "critic": ("critic", critic_node, {"critic_verdict": None}),
    }

    if enabled_agents is None:
        enabled_agents = getattr(run_service.settings, "enabled_agents", ["collector", "oracle", "sentinel", "sage", "scribe", "sentiment", "fundamental", "options_flow", "critic"])

    agents_list = list(enabled_agents)
    if "oracle" in agents_list and "sentinel" in agents_list and "debate" not in agents_list:
        agents_list.append("debate")
    if "sage" in agents_list and "portfolio_manager" not in agents_list:
        agents_list.append("portfolio_manager")

    active_agent_names = [a for a in agents_list if a in node_map]

    # Setup the StateGraph workflow
    workflow = StateGraph(AgentState)

    # Register active nodes in workflow
    for agent_name in active_agent_names:
        node_name, node_func, fallback = node_map[agent_name]
        resilient_func = make_resilient_node(agent_name, node_func, fallback)
        workflow.add_node(node_name, resilient_func)

    active_node_names = {node_map[a][0] for a in active_agent_names}

    # Connect START to collect
    if "collect" in active_node_names:
        workflow.add_edge(START, "collect")
    else:
        workflow.add_edge(START, "oracle" if "oracle" in active_node_names else "scribe")

    # Connect collect to parallel analysts
    for node in ["oracle", "sentinel", "sentiment", "fundamental", "options_flow"]:
        if "collect" in active_node_names and node in active_node_names:
            workflow.add_edge("collect", node)

    # Connect parallel sentiment/fundamental/options_flow to scribe
    for node in ["sentiment", "fundamental", "options_flow"]:
        if node in active_node_names and "scribe" in active_node_names:
            workflow.add_edge(node, "scribe")

    # Handle debate/PM flow routing
    if "debate" in active_node_names:
        if "oracle" in active_node_names:
            workflow.add_edge("oracle", "debate")
        if "sentinel" in active_node_names:
            workflow.add_edge("sentinel", "debate")
        
        if "sage" in active_node_names:
            workflow.add_edge("debate", "sage")
            if "portfolio_manager" in active_node_names:
                workflow.add_edge("sage", "portfolio_manager")
        else:
            if "portfolio_manager" in active_node_names:
                workflow.add_edge("debate", "portfolio_manager")
    else:
        if "oracle" in active_node_names:
            if "sage" in active_node_names:
                workflow.add_edge("oracle", "sage")
                if "portfolio_manager" in active_node_names:
                    workflow.add_edge("sage", "portfolio_manager")
            else:
                if "portfolio_manager" in active_node_names:
                    workflow.add_edge("oracle", "portfolio_manager")
        if "sentinel" in active_node_names:
            if "portfolio_manager" in active_node_names:
                workflow.add_edge("sentinel", "portfolio_manager")

    # Connect last step of risk/PM path to scribe
    if "portfolio_manager" in active_node_names:
        if "scribe" in active_node_names:
            workflow.add_edge("portfolio_manager", "scribe")
    elif "sage" in active_node_names:
        if "scribe" in active_node_names:
            workflow.add_edge("sage", "scribe")
    elif "debate" in active_node_names:
        if "scribe" in active_node_names:
            workflow.add_edge("debate", "scribe")
    elif "oracle" in active_node_names or "sentinel" in active_node_names:
        if "oracle" in active_node_names and "scribe" in active_node_names:
            workflow.add_edge("oracle", "scribe")
        if "sentinel" in active_node_names and "scribe" in active_node_names:
            workflow.add_edge("sentinel", "scribe")

    # Scribe -> Critic -> Scribe loop or END
    def route_critic(state: AgentState):
        verdict = state.get("critic_verdict")
        if verdict and not verdict.passed and verdict.iteration < 2:
            return "scribe"
        return "__end__"

    if "critic" in active_node_names and "scribe" in active_node_names:
        workflow.add_edge("scribe", "critic")
        workflow.add_conditional_edges(
            "critic",
            route_critic,
            {
                "scribe": "scribe",
                "__end__": END
            }
        )
    else:
        if "scribe" in active_node_names:
            workflow.add_edge("scribe", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)
