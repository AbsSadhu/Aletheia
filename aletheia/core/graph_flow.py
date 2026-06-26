from __future__ import annotations

from typing import Any, Dict, List, Optional
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
    Portfolio,
    MarketQuote,
)


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
    insights: List[str]
    error: Optional[str]


def create_agent_graph(run_service: Any) -> Any:
    """Creates and compiles a LangGraph StateGraph bound to the given RunService instance."""

    async def collect_node(state: AgentState) -> Dict[str, Any]:
        portfolio = state["portfolio"]
        run_id = state["run_id"]
        if not portfolio:
            return {}

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
                    payload=output.model_dump(),
                )
            )

        quotes_by_symbol = run_service._quotes_by_symbol(outputs)
        return {"collector_outputs": outputs, "quotes_by_symbol": quotes_by_symbol}

    async def oracle_node(state: AgentState) -> Dict[str, Any]:
        portfolio = state["portfolio"]
        quotes_by_symbol = state.get("quotes_by_symbol") or {}
        run_id = state["run_id"]
        if not portfolio or not quotes_by_symbol:
            return {}

        oracle_outputs = []
        for holding in portfolio.holdings:
            quote = quotes_by_symbol.get(holding.symbol.upper())
            if quote is None:
                continue
            oracle_output = await run_service.oracle.analyze(holding, quote)
            oracle_outputs.append(oracle_output)
            await run_service.record_event(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName.ORACLE,
                    message=f"{holding.symbol}: {oracle_output.signal} with confidence {oracle_output.confidence:.2f}",
                    payload=oracle_output.model_dump(),
                )
            )
        return {"oracle_outputs": oracle_outputs}

    async def sentinel_node(state: AgentState) -> Dict[str, Any]:
        portfolio = state["portfolio"]
        quotes_by_symbol = state.get("quotes_by_symbol") or {}
        run_id = state["run_id"]
        if not portfolio or not quotes_by_symbol:
            return {}

        sentinel_output = await run_service.sentinel.assess(portfolio, quotes_by_symbol)
        await run_service.record_event(
            AgentEvent(
                run_id=run_id,
                agent=AgentName.SENTINEL,
                message=(
                    f"Portfolio VaR95 {sentinel_output.portfolio_var_95:.2f}, "
                    f"max position {sentinel_output.max_single_position_pct:.2f}%"
                ),
                payload=sentinel_output.model_dump(),
            )
        )
        return {"sentinel_output": sentinel_output}

    async def sage_node(state: AgentState) -> Dict[str, Any]:
        portfolio = state["portfolio"]
        quotes_by_symbol = state.get("quotes_by_symbol") or {}
        oracle_outputs = state.get("oracle_outputs") or []
        run_id = state["run_id"]
        if not portfolio or not quotes_by_symbol:
            return {}

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
                    payload=sage_output.model_dump(),
                )
            )
        return {"sage_outputs": sage_outputs}

    async def scribe_node(state: AgentState) -> Dict[str, Any]:
        oracle_outputs = state.get("oracle_outputs") or []
        sentinel_output = state.get("sentinel_output")
        sage_outputs = state.get("sage_outputs") or []
        run_id = state["run_id"]
        portfolio = state["portfolio"]
        collector_outputs = state.get("collector_outputs") or []

        scribe_output = await run_service.scribe.synthesize(
            oracle_outputs, sentinel_output, sage_outputs
        )
        await run_service.record_event(
            AgentEvent(
                run_id=run_id,
                agent=AgentName.SCRIBE,
                message=f"Synthesis complete with {scribe_output.agreement_level} agreement.",
                payload=scribe_output.model_dump(),
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
        return {"scribe_output": scribe_output, "insights": insights}

    # Setup the StateGraph workflow
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("collect", collect_node)
    workflow.add_node("oracle", oracle_node)
    workflow.add_node("sentinel", sentinel_node)
    workflow.add_node("sage", sage_node)
    workflow.add_node("scribe", scribe_node)

    # Establish flow edges
    workflow.add_edge(START, "collect")

    # Fork from collect to oracle and sentinel concurrently
    workflow.add_edge("collect", "oracle")
    workflow.add_edge("collect", "sentinel")

    # Oracle output goes sequentially into Sage tax calculation
    workflow.add_edge("oracle", "sage")

    # Sage and Sentinel outputs join into Scribe narrative synthesis
    workflow.add_edge("sage", "scribe")
    workflow.add_edge("sentinel", "scribe")

    # End the graph run
    workflow.add_edge("scribe", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)
