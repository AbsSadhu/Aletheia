"""
Long-Term Layered Memory Store.

Three tiers:
  L1 (Immediate)  — last 10 obs per agent/ticker, 14-day retention
  L2 (Recent)     — weekly rollups of best/worst calls, 180-day retention
  L3 (Historical) — monthly summaries of key patterns, 730-day retention

Automatic promotion happens when `promote()` is called (e.g., weekly cron).
"""

from __future__ import annotations

import sqlite3
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aletheia.memory.working_memory import WorkingMemory

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".aletheia" / "memory" / "long_term.db"


class LongTermMemory:
    """
    Tiered memory store that promotes short-term observations into
    summarised long-term records for efficient agent recall.
    """

    # Retention boundaries
    L1_DAYS = 14
    L2_DAYS = 180
    L3_DAYS = 730

    def __init__(
        self,
        db_path: str | Path = _DEFAULT_DB,
        working_memory: WorkingMemory | None = None,
    ) -> None:
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.wm = working_memory or WorkingMemory()
        self._init_db()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._conn() as conn:
            # L2 — weekly rollups
            conn.execute("""
                CREATE TABLE IF NOT EXISTS l2_weekly_rollups (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name  TEXT NOT NULL,
                    ticker      TEXT NOT NULL,
                    week_start  TEXT NOT NULL,
                    best_call   TEXT,
                    worst_call  TEXT,
                    avg_confidence REAL,
                    call_count  INTEGER DEFAULT 0,
                    created_at  TEXT NOT NULL,
                    UNIQUE(agent_name, ticker, week_start)
                )
            """)
            # L3 — monthly summaries
            conn.execute("""
                CREATE TABLE IF NOT EXISTS l3_monthly_summaries (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name  TEXT NOT NULL,
                    ticker      TEXT NOT NULL,
                    month       TEXT NOT NULL,
                    pattern_summary TEXT,
                    avg_confidence REAL,
                    call_count  INTEGER DEFAULT 0,
                    created_at  TEXT NOT NULL,
                    UNIQUE(agent_name, ticker, month)
                )
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------

    def promote_l1_to_l2(self, agent_name: str) -> int:
        """Roll up last week's L1 observations into L2 weekly records."""
        week_start = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        observations = self.wm.list_all_observations(agent_name=agent_name, limit=200)

        # Group by ticker
        by_ticker: dict[str, list[dict[str, Any]]] = {}
        for obs in observations:
            ts = obs.get("timestamp", "")
            if ts >= week_start:
                tk = obs["ticker"]
                by_ticker.setdefault(tk, []).append(obs)

        promoted = 0
        now = datetime.now(UTC).isoformat()
        for ticker, obs_list in by_ticker.items():
            if not obs_list:
                continue
            confidences = [o["confidence"] for o in obs_list]
            sorted_by_conf = sorted(obs_list, key=lambda x: x["confidence"], reverse=True)
            best = sorted_by_conf[0]["observation"] if sorted_by_conf else ""
            worst = sorted_by_conf[-1]["observation"] if len(sorted_by_conf) > 1 else ""

            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO l2_weekly_rollups
                        (agent_name, ticker, week_start, best_call, worst_call,
                         avg_confidence, call_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(agent_name, ticker, week_start)
                    DO UPDATE SET
                        best_call=excluded.best_call,
                        worst_call=excluded.worst_call,
                        avg_confidence=excluded.avg_confidence,
                        call_count=excluded.call_count
                """,
                    (
                        agent_name,
                        ticker,
                        week_start[:10],
                        best,
                        worst,
                        sum(confidences) / len(confidences) if confidences else 0.5,
                        len(obs_list),
                        now,
                    ),
                )
            promoted += 1
            logger.debug("Promoted %s/%s L1→L2 (%d obs)", agent_name, ticker, len(obs_list))

        return promoted

    def promote_l2_to_l3(self, agent_name: str) -> int:
        """Summarize last month's L2 rollups into L3 monthly summaries."""
        month = datetime.now(UTC).strftime("%Y-%m")
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM l2_weekly_rollups WHERE agent_name = ? AND week_start LIKE ?",
                (agent_name, f"{month}%"),
            ).fetchall()

        by_ticker: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            by_ticker.setdefault(row["ticker"], []).append(row)

        promoted = 0
        now = datetime.now(UTC).isoformat()
        for ticker, rollups in by_ticker.items():
            avg_conf = sum(r["avg_confidence"] for r in rollups) / len(rollups)
            total_calls = sum(r["call_count"] for r in rollups)
            best_calls = [r["best_call"] for r in rollups if r["best_call"]]
            pattern = (
                f"Monthly summary ({len(rollups)} weeks, {total_calls} calls). Top signals: "
                + " | ".join(best_calls[:3])
            )

            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO l3_monthly_summaries
                        (agent_name, ticker, month, pattern_summary, avg_confidence, call_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(agent_name, ticker, month)
                    DO UPDATE SET
                        pattern_summary=excluded.pattern_summary,
                        avg_confidence=excluded.avg_confidence,
                        call_count=excluded.call_count
                """,
                    (agent_name, ticker, month, pattern, avg_conf, total_calls, now),
                )
            promoted += 1

        return promoted

    def promote(self, agent_name: str) -> dict[str, int]:
        """Run both promotion passes for an agent."""
        l2 = self.promote_l1_to_l2(agent_name)
        l3 = self.promote_l2_to_l3(agent_name)
        return {"l2_promoted": l2, "l3_promoted": l3}

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve_l2(self, agent_name: str, ticker: str, limit: int = 4) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM l2_weekly_rollups
                WHERE agent_name = ? AND ticker = ?
                ORDER BY week_start DESC LIMIT ?
                """,
                (agent_name, ticker.upper(), limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def retrieve_l3(self, agent_name: str, ticker: str, limit: int = 3) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM l3_monthly_summaries
                WHERE agent_name = ? AND ticker = ?
                ORDER BY month DESC LIMIT ?
                """,
                (agent_name, ticker.upper(), limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def build_long_term_context(self, agent_name: str, ticker: str) -> str:
        """Format L2+L3 memory for injection into agent prompts."""
        l2 = self.retrieve_l2(agent_name, ticker)
        l3 = self.retrieve_l3(agent_name, ticker)

        parts: list[str] = []
        if l2:
            parts.append("WEEKLY MEMORY (L2):")
            for r in l2:
                parts.append(
                    f"  Week of {r['week_start']}: avg_conf={r['avg_confidence']:.2f}, "
                    f"calls={r['call_count']}. Best: {r['best_call'][:100] if r['best_call'] else 'N/A'}"
                )
        if l3:
            parts.append("MONTHLY PATTERNS (L3):")
            for r in l3:
                parts.append(
                    f"  {r['month']}: {r['pattern_summary'][:150] if r['pattern_summary'] else 'N/A'}"
                )

        return "\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def prune_expired(self) -> dict[str, int]:
        """Remove records beyond their retention window."""
        now = datetime.now(UTC)
        l2_cutoff = (now - timedelta(days=self.L2_DAYS)).strftime("%Y-%m-%d")
        l3_cutoff = (now - timedelta(days=self.L3_DAYS)).strftime("%Y-%m")

        with self._conn() as conn:
            l2_del = conn.execute(
                "DELETE FROM l2_weekly_rollups WHERE week_start < ?", (l2_cutoff,)
            ).rowcount
            l3_del = conn.execute(
                "DELETE FROM l3_monthly_summaries WHERE month < ?", (l3_cutoff,)
            ).rowcount

        return {"l2_deleted": l2_del, "l3_deleted": l3_del}
