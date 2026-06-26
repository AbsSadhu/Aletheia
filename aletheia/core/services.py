from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aletheia.extensions.agents.collector import CollectorAgent
from aletheia.extensions.agents.oracle import OracleAgent
from aletheia.extensions.agents.sage import SageAgent
from aletheia.extensions.agents.scribe import ScribeAgent
from aletheia.extensions.agents.sentinel import SentinelAgent
from aletheia.core.db.duckdb_store import DuckDBStore
from aletheia.core.db.sqlite_store import SQLiteStore
from aletheia.core.models import (
    AgentEvent,
    AgentName,
    CollectorOutput,
    MarketQuote,
    Portfolio,
    RunRequest,
    RunResult,
    RunStatus,
    RunSummary,
)
from aletheia.core.graph_flow import create_agent_graph



class RunService:
    def __init__(
        self,
        collector: CollectorAgent,
        oracle: OracleAgent,
        sentinel: SentinelAgent,
        sage: SageAgent,
        scribe: ScribeAgent,
        sqlite_store: SQLiteStore,
        duckdb_store: DuckDBStore,
    ) -> None:
        self.collector = collector
        self.oracle = oracle
        self.sentinel = sentinel
        self.sage = sage
        self.scribe = scribe
        self.sqlite_store = sqlite_store
        self.duckdb_store = duckdb_store
        self._events: dict[str, list[AgentEvent]] = {}
        self._active_sockets: dict[str, list[Any]] = {}
        self.graph = create_agent_graph(self)

    def register_socket(self, run_id: str, websocket: Any) -> None:
        self._active_sockets.setdefault(run_id, []).append(websocket)

    def unregister_socket(self, run_id: str, websocket: Any) -> None:
        if run_id in self._active_sockets:
            if websocket in self._active_sockets[run_id]:
                self._active_sockets[run_id].remove(websocket)
            if not self._active_sockets[run_id]:
                del self._active_sockets[run_id]

    async def record_event(self, event: AgentEvent) -> None:
        self._events.setdefault(event.run_id, []).append(event)
        
        # Broadcast to active sockets
        sockets = self._active_sockets.get(event.run_id, [])
        if sockets:
            payload = event.model_dump(mode="json")
            for ws in list(sockets):
                try:
                    await ws.send_json(payload)
                except Exception:
                    pass

    def get_events(self, run_id: str) -> list[AgentEvent]:
        return self._events.get(run_id, [])

    def list_runs(self, limit: int = 20) -> list[RunSummary]:
        return self.sqlite_store.list_runs(limit=limit)

    def get_run(self, run_id: str) -> RunResult | None:
        return self.sqlite_store.get_run(run_id)

    async def create_run(self, request: RunRequest) -> RunResult:
        summary = RunSummary(prompt=request.prompt, status=RunStatus.RUNNING)
        self.sqlite_store.upsert_run(summary)
        return await self.execute_run(summary, request)

    async def execute_run(self, summary: RunSummary, request: RunRequest) -> RunResult:
        try:
            initial_state = {
                "run_id": summary.run_id,
                "portfolio": request.portfolio,
                "prompt": request.prompt,
                "collector_outputs": [],
                "quotes_by_symbol": {},
                "oracle_outputs": [],
                "sage_outputs": [],
                "sentinel_output": None,
                "scribe_output": None,
                "insights": [],
                "error": None,
            }

            config = {"configurable": {"thread_id": summary.run_id}}
            final_state = await self.graph.ainvoke(initial_state, config=config)

            outputs = final_state.get("collector_outputs") or []
            oracle_outputs = final_state.get("oracle_outputs") or []
            sage_outputs = final_state.get("sage_outputs") or []
            sentinel_output = final_state.get("sentinel_output")
            scribe_output = final_state.get("scribe_output")
            insight_lines = final_state.get("insights") or []

            confidence_score = scribe_output.overall_confidence if scribe_output else (0.35 if outputs else 0.0)
            result = RunResult(
                summary=summary.model_copy(
                    update={
                        "status": RunStatus.COMPLETED,
                        "updated_at": datetime.now(UTC),
                    }
                ),
                collector_output=outputs,
                oracle_output=oracle_outputs,
                sentinel_output=sentinel_output,
                sage_output=sage_outputs,
                scribe_output=scribe_output,
                insights=insight_lines,
                confidence_score=confidence_score,
            )
            self.sqlite_store.upsert_run(result.summary, result)
            
            # Broadcast completion message to active sockets
            sockets = self._active_sockets.get(summary.run_id, [])
            for ws in list(sockets):
                try:
                    await ws.send_json({"run_id": summary.run_id, "message": "stream_complete"})
                except Exception:
                    pass
            return result
        except Exception as e:
            failed_summary = summary.model_copy(
                update={
                    "status": RunStatus.FAILED,
                    "updated_at": datetime.now(UTC),
                    "error_message": str(e),
                }
            )
            self.sqlite_store.upsert_run(failed_summary)
            # Broadcast failure / stream completion to active sockets
            sockets = self._active_sockets.get(summary.run_id, [])
            for ws in list(sockets):
                try:
                    await ws.send_json({"run_id": summary.run_id, "message": "stream_complete"})
                except Exception:
                    pass
            raise e

    def _quotes_by_symbol(self, outputs: list[CollectorOutput]) -> dict[str, MarketQuote]:
        quotes: dict[str, MarketQuote] = {}
        for output in outputs:
            if output.quotes:
                quotes[output.symbol.upper()] = output.quotes[-1]
        return quotes

    def _build_initial_insights(
        self,
        portfolio: Portfolio | None,
        outputs: list[CollectorOutput],
        oracle_outputs: list,
        sentinel_output,
        sage_outputs: list,
        scribe_output,
    ) -> list[str]:
        if portfolio is None:
            return ["Run created without a portfolio. Provide holdings to activate the full engine."]

        holdings_with_quotes = sum(1 for output in outputs if output.quotes)
        insights = [
            f"Collector gathered market data for {holdings_with_quotes}/{len(portfolio.holdings)} holdings.",
            f"Oracle generated {len(oracle_outputs)} symbol-level views.",
            f"Sage completed {len(sage_outputs)} tax-aware scenario projections.",
        ]
        if sentinel_output is not None:
            insights.append(
                f"Sentinel estimates portfolio VaR95 at {sentinel_output.portfolio_var_95:.2f} {portfolio.base_currency}."
            )
        if scribe_output is not None:
            insights.append(
                f"Scribe reports {scribe_output.agreement_level} cross-agent agreement with confidence {scribe_output.overall_confidence:.2f}."
            )
        return insights

