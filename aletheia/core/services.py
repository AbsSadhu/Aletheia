from __future__ import annotations

import logging
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
    CollectorOutput,
    MarketQuote,
    Portfolio,
    RunRequest,
    RunResult,
    RunStatus,
    RunSummary,
)
from aletheia.core.graph_flow import create_agent_graph
from aletheia.core.config.settings import get_settings

logger = logging.getLogger(__name__)


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
        self.settings = get_settings()
        self._events: dict[str, list[AgentEvent]] = {}
        self._active_sockets: dict[str, list[Any]] = {}

        # Instantiate new agents and compute client
        from aletheia.extensions.agents.sentiment_agent import SentimentAgent
        from aletheia.extensions.agents.fundamental_agent import FundamentalAgent
        from aletheia.extensions.agents.options_flow_agent import OptionsFlowAgent
        from aletheia.extensions.agents.critic_agent import CriticAgent
        from aletheia.core.compute.client import ComputeClient

        self.compute_client = ComputeClient()
        self.sentiment = SentimentAgent(llm_client=self.scribe.llm_client)
        self.fundamental = FundamentalAgent(llm_client=self.scribe.llm_client)
        self.options_flow = OptionsFlowAgent(compute_client=self.compute_client)
        self.critic = CriticAgent(llm_client=self.scribe.llm_client)

        # Wire up stores to agents
        self.oracle.duckdb_store = duckdb_store
        self.oracle.compute_client = self.compute_client
        self.sentinel.duckdb_store = duckdb_store
        self.sentinel.compute_client = self.compute_client

        self.graph = create_agent_graph(self, self.settings.enabled_agents)

    def register_socket(self, run_id: str, websocket: Any) -> None:
        self._active_sockets.setdefault(run_id, []).append(websocket)

    def unregister_socket(self, run_id: str, websocket: Any) -> None:
        if run_id in self._active_sockets:
            if websocket in self._active_sockets[run_id]:
                self._active_sockets[run_id].remove(websocket)
            if not self._active_sockets[run_id]:
                del self._active_sockets[run_id]

    async def record_event(self, event: AgentEvent) -> None:
        # Persist event to SQLite for run tracing
        try:
            self.sqlite_store.save_agent_event(event)
        except Exception as db_exc:
            logger.warning("RunService: Failed to save agent event to DB: %s", db_exc)

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
        # Retrieve events from SQLite DB
        try:
            return self.sqlite_store.get_agent_events(run_id)
        except Exception as db_exc:
            logger.warning("RunService: Failed to fetch agent events from DB: %s", db_exc)
            return []

    def list_runs(self, limit: int = 20) -> list[RunSummary]:
        return self.sqlite_store.list_runs(limit=limit)

    def get_run(self, run_id: str) -> RunResult | None:
        return self.sqlite_store.get_run(run_id)

    async def update_run_progress(
        self,
        run_id: str,
        state: dict[str, Any],
        status: RunStatus = RunStatus.RUNNING,
    ) -> None:
        try:
            summary = RunSummary(
                run_id=run_id,
                status=status,
                prompt=state.get("prompt", ""),
                agent_statuses=state.get("agent_statuses", {}),
                error_message=state.get("error"),
            )

            collector_output = state.get("collector_outputs") or []
            oracle_output = state.get("oracle_outputs") or []
            sentinel_output = state.get("sentinel_output")
            sage_output = state.get("sage_outputs") or []
            scribe_output = state.get("scribe_output")
            insights = state.get("insights") or []
            traces = state.get("traces") or []

            result = RunResult(
                summary=summary,
                collector_output=collector_output,
                oracle_output=oracle_output,
                sentinel_output=sentinel_output,
                sage_output=sage_output,
                scribe_output=scribe_output,
                sentiment_outputs=state.get("sentiment_outputs") or [],
                fundamental_outputs=state.get("fundamental_outputs") or [],
                options_flow_outputs=state.get("options_flow_outputs") or [],
                critic_verdict=state.get("critic_verdict"),
                macro_context_text=state.get("macro_context_text", ""),
                insights=insights,
                agent_statuses=state.get("agent_statuses", {}),
                traces=traces,
            )
            self.sqlite_store.upsert_run(summary, result)
        except Exception as exc:
            logger.warning("RunService: Failed to save progress to DB: %s", exc)

        # Broadcast progress updates to active WebSocket sockets
        sockets = self._active_sockets.get(run_id, [])
        if sockets:
            payload = {
                "run_id": run_id,
                "type": "progress",
                "agent_statuses": state.get("agent_statuses", {}),
            }
            for ws in list(sockets):
                try:
                    await ws.send_json(payload)
                except Exception:
                    pass

    async def create_run(self, request: RunRequest) -> RunResult:
        summary = RunSummary(prompt=request.prompt, status=RunStatus.RUNNING)
        self.sqlite_store.upsert_run(summary)
        return await self.execute_run(summary, request)

    async def execute_run(self, summary: RunSummary, request: RunRequest) -> RunResult:
        try:
            # H5. Macro context pre-injection step
            macro_context_text = ""
            try:
                from aletheia.core.context.macro_injector import get_macro_injector

                macro_injector = get_macro_injector(duckdb_path=str(self.duckdb_store.db_path))
                macro_ctx = await macro_injector.get()
                macro_context_text = macro_ctx.as_prompt_text()
            except Exception as macro_exc:
                logger.warning("RunService: failed to fetch macro context: %s", macro_exc)

            # Determine active agents dynamically
            selected = [a.value for a in request.selected_agents]
            enabled = self.settings.enabled_agents
            active_agent_names = [a for a in selected if a in enabled]
            if "sage" in active_agent_names and not self.settings.tax_jurisdiction:
                active_agent_names.remove("sage")

            # Initialize agent statuses
            all_agent_names = [
                "collector",
                "oracle",
                "sentinel",
                "sage",
                "scribe",
                "sentiment",
                "fundamental",
                "options_flow",
                "critic",
            ]
            agent_statuses = {}
            for name in all_agent_names:
                if name in active_agent_names:
                    agent_statuses[name] = "pending"
                else:
                    agent_statuses[name] = "skipped"

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
                "sentiment_outputs": [],
                "fundamental_outputs": [],
                "options_flow_outputs": [],
                "critic_verdict": None,
                "macro_context_text": macro_context_text,
                "insights": [],
                "error": None,
                "traces": [],
                "agent_statuses": agent_statuses,
                "debate_disagreements": [],
                "portfolio_manager_overrides": [],
            }

            # Save initial progress
            await self.update_run_progress(summary.run_id, initial_state, status=RunStatus.RUNNING)

            # Compile dynamic graph
            graph = create_agent_graph(self, enabled_agents=active_agent_names)

            config = {"configurable": {"thread_id": summary.run_id}}
            final_state = await graph.ainvoke(initial_state, config=config)

            outputs = final_state.get("collector_outputs") or []
            oracle_outputs = final_state.get("oracle_outputs") or []
            sage_outputs = final_state.get("sage_outputs") or []
            sentinel_output = final_state.get("sentinel_output")
            scribe_output = final_state.get("scribe_output")
            sentiment_outputs = final_state.get("sentiment_outputs") or []
            fundamental_outputs = final_state.get("fundamental_outputs") or []
            options_flow_outputs = final_state.get("options_flow_outputs") or []
            critic_verdict = final_state.get("critic_verdict")
            insight_lines = final_state.get("insights") or []
            traces = final_state.get("traces") or []
            final_agent_statuses = final_state.get("agent_statuses") or agent_statuses

            # Check if any active agent failed
            any_failed = any(
                status == "failed"
                for name, status in final_agent_statuses.items()
                if name in active_agent_names
            )
            final_status = RunStatus.PARTIAL if any_failed else RunStatus.COMPLETED

            confidence_score = (
                scribe_output.overall_confidence if scribe_output else (0.35 if outputs else 0.0)
            )
            result = RunResult(
                summary=summary.model_copy(
                    update={
                        "status": final_status,
                        "updated_at": datetime.now(UTC),
                        "agent_statuses": final_agent_statuses,
                    }
                ),
                collector_output=outputs,
                oracle_output=oracle_outputs,
                sentinel_output=sentinel_output,
                sage_output=sage_outputs,
                scribe_output=scribe_output,
                sentiment_outputs=sentiment_outputs,
                fundamental_outputs=fundamental_outputs,
                options_flow_outputs=options_flow_outputs,
                critic_verdict=critic_verdict,
                macro_context_text=macro_context_text,
                insights=insight_lines,
                confidence_score=confidence_score,
                traces=traces,
                agent_statuses=final_agent_statuses,
            )
            self.sqlite_store.upsert_run(result.summary, result)

            # H7. ComplianceLogger call after each run
            if (
                result.summary.status in (RunStatus.COMPLETED, RunStatus.PARTIAL)
                and result.scribe_output
            ):
                try:
                    from aletheia.core.compliance.sebi_logger import SEBIComplianceLogger

                    sebi_logger = SEBIComplianceLogger(self.sqlite_store)
                    sebi_logger.log_run(
                        run_id=summary.run_id,
                        recommendations=result.scribe_output.recommendations,
                        executive_summary=result.scribe_output.executive_summary,
                    )
                except Exception as compliance_exc:
                    logger.warning("RunService: SEBI compliance logging failed: %s", compliance_exc)

            # Record confidence predictions to ConfidenceCalibrationStore after run
            if result.summary.status in (RunStatus.COMPLETED, RunStatus.PARTIAL):
                try:
                    # For Oracle
                    for o in oracle_outputs:
                        self.sqlite_store.record_confidence(
                            run_id=summary.run_id,
                            symbol=o.symbol,
                            agent="oracle",
                            predicted_signal=o.signal,
                            predicted_confidence=o.confidence,
                        )
                    # For Sentiment
                    for s in sentiment_outputs:
                        self.sqlite_store.record_confidence(
                            run_id=summary.run_id,
                            symbol=s.symbol,
                            agent="sentiment",
                            predicted_signal=s.verdict,
                            predicted_confidence=s.confidence,
                        )
                    # For Fundamental
                    for f in fundamental_outputs:
                        self.sqlite_store.record_confidence(
                            run_id=summary.run_id,
                            symbol=f.symbol,
                            agent="fundamental",
                            predicted_signal=f.valuation_verdict,
                            predicted_confidence=f.confidence,
                        )
                except Exception as cal_exc:
                    logger.warning(
                        "RunService: Confidence calibration recording failed: %s", cal_exc
                    )

            # Auto-ingest into episodic memory for future recall
            try:
                from aletheia.core.memory.episodic import EpisodicMemory
                import os

                mem_dir = os.path.expanduser(self.settings.memory_dir)
                episodic = EpisodicMemory(db_path=os.path.join(mem_dir, "episodic.db"))
                episodic.ingest_run_result(result)
            except Exception as mem_exc:
                logger.warning("Episodic memory ingest failed: %s", mem_exc)

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
            return [
                "Run created without a portfolio. Provide holdings to activate the full engine."
            ]

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
