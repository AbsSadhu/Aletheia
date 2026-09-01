"""
Working Memory Module — per-agent, per-ticker observation store.

Implements the FinMem pattern: agents summarize current data, retrieve
relevant past observations for the same ticker, and store their outputs
for future recall.
"""

from __future__ import annotations

import json
import sqlite3
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".aletheia" / "memory" / "working_memory.db"


class AgentObservation:
    """A single agent observation for a ticker at a point in time."""

    def __init__(
        self,
        agent_name: str,
        ticker: str,
        observation: str,
        confidence: float,
        timestamp: datetime,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        id: int | None = None,
    ) -> None:
        self.id = id
        self.agent_name = agent_name
        self.ticker = ticker
        self.observation = observation
        self.confidence = confidence
        self.timestamp = timestamp
        self.run_id = run_id
        self.metadata = metadata or {}

    def as_prompt_text(self) -> str:
        age_hours = (datetime.now(UTC) - self.timestamp.replace(tzinfo=UTC)).total_seconds() / 3600
        return (
            f"[{self.agent_name.upper()} | {self.ticker} | {age_hours:.0f}h ago | "
            f"confidence={self.confidence:.2f}]\n{self.observation}"
        )


class WorkingMemory:
    """
    Per-agent, per-ticker short-term observation store.

    Schema:
        agent_observations(
            id          INTEGER PRIMARY KEY,
            agent_name  TEXT NOT NULL,
            ticker      TEXT NOT NULL,
            observation TEXT NOT NULL,
            confidence  REAL NOT NULL DEFAULT 0.5,
            timestamp   TEXT NOT NULL,
            run_id      TEXT,
            metadata    TEXT DEFAULT '{}'
        )
    """

    def __init__(self, db_path: str | Path = _DEFAULT_DB) -> None:
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_observations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name  TEXT    NOT NULL,
                    ticker      TEXT    NOT NULL,
                    observation TEXT    NOT NULL,
                    confidence  REAL    NOT NULL DEFAULT 0.5,
                    timestamp   TEXT    NOT NULL,
                    run_id      TEXT,
                    metadata    TEXT    DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_ticker_ts
                ON agent_observations (agent_name, ticker, timestamp DESC)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_critiques (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name  TEXT NOT NULL,
                    critique    TEXT NOT NULL,
                    timestamp   TEXT NOT NULL
                )
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store_observation(
        self,
        agent_name: str,
        ticker: str,
        observation: str,
        confidence: float = 0.5,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Store one agent observation. Returns the row id."""
        ts = datetime.now(UTC).isoformat()
        meta_str = json.dumps(metadata or {})
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO agent_observations
                    (agent_name, ticker, observation, confidence, timestamp, run_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (agent_name, ticker.upper(), observation, confidence, ts, run_id, meta_str),
            )
            return cur.lastrowid or 0

    def store_critique(self, agent_name: str, critique: str) -> int:
        ts = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO agent_critiques (agent_name, critique, timestamp) VALUES (?, ?, ?)",
                (agent_name, critique, ts),
            )
            return cur.lastrowid or 0

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def retrieve_for_ticker(
        self,
        agent_name: str,
        ticker: str,
        limit: int = 5,
        max_age_days: int = 14,
    ) -> list[AgentObservation]:
        """Retrieve recent observations by this agent for a ticker."""
        cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM agent_observations
                WHERE agent_name = ? AND ticker = ? AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (agent_name, ticker.upper(), cutoff, limit),
            ).fetchall()
        return [self._row_to_obs(r) for r in rows]

    def retrieve_recent(self, agent_name: str, limit: int = 10) -> list[AgentObservation]:
        """Retrieve latest N observations across all tickers for an agent."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM agent_observations
                WHERE agent_name = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (agent_name, limit),
            ).fetchall()
        return [self._row_to_obs(r) for r in rows]

    def get_latest_critique(self, agent_name: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT critique FROM agent_critiques WHERE agent_name = ? ORDER BY timestamp DESC LIMIT 1",
                (agent_name,),
            ).fetchone()
        return row["critique"] if row else None

    def get_critiques(self, agent_name: str, limit: int = 5) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_critiques WHERE agent_name = ? ORDER BY timestamp DESC LIMIT ?",
                (agent_name, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all_observations(
        self,
        agent_name: str | None = None,
        ticker: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List observations with optional filters."""
        query = "SELECT * FROM agent_observations WHERE 1=1"
        params: list[Any] = []
        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)
        if ticker:
            query += " AND ticker = ?"
            params.append(ticker.upper())
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Inject memory into agent prompt
    # ------------------------------------------------------------------

    def build_memory_context(
        self,
        agent_name: str,
        ticker: str,
        limit: int = 5,
    ) -> str:
        """Build a formatted string for injection into agent prompts."""
        observations = self.retrieve_for_ticker(agent_name, ticker, limit=limit)
        critique = self.get_latest_critique(agent_name)

        parts: list[str] = []

        if observations:
            parts.append("RELEVANT PAST OBSERVATIONS (same ticker):")
            for obs in observations:
                parts.append(obs.as_prompt_text())

        if critique:
            parts.append(f"\nYOUR RECENT SELF-CRITIQUE:\n{critique}")
            parts.append("Apply these insights to your current analysis.")

        return "\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _row_to_obs(self, row: sqlite3.Row) -> AgentObservation:
        ts_str = row["timestamp"]
        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            ts = datetime.now(UTC)

        meta: dict[str, Any] = {}
        try:
            meta = json.loads(row["metadata"] or "{}")
        except (json.JSONDecodeError, TypeError):
            pass

        return AgentObservation(
            id=row["id"],
            agent_name=row["agent_name"],
            ticker=row["ticker"],
            observation=row["observation"],
            confidence=float(row["confidence"]),
            timestamp=ts,
            run_id=row["run_id"],
            metadata=meta,
        )
