"""
Episodic Memory Store — SQLite FTS5 backed.

Automatically ingests Aletheia run results so agents can recall past analyses,
signals, and insights via full-text search.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """
    Full-text searchable store of agent run history.

    Schema:
        episodes(
            id          TEXT PRIMARY KEY,
            run_id      TEXT,
            created_at  TEXT,
            symbols     TEXT,   -- comma-separated
            prompt      TEXT,
            insights    TEXT,   -- newline-separated
            signals     TEXT,   -- JSON blob
            full_text   TEXT    -- FTS5 indexed column
        )
    """

    def __init__(self, db_path: str | Path = "~/.aletheia/memory/episodic.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id         TEXT PRIMARY KEY,
                    run_id     TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    symbols    TEXT DEFAULT '',
                    prompt     TEXT DEFAULT '',
                    insights   TEXT DEFAULT '',
                    signals    TEXT DEFAULT '{}',
                    full_text  TEXT DEFAULT ''
                )
            """)
            # FTS5 virtual table that shadows episodes
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts
                USING fts5(
                    run_id,
                    prompt,
                    insights,
                    signals,
                    symbols,
                    content='episodes',
                    content_rowid='rowid'
                )
            """)
            # Triggers to keep FTS in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS episodes_ai
                AFTER INSERT ON episodes BEGIN
                    INSERT INTO episodes_fts(rowid, run_id, prompt, insights, signals, symbols)
                    VALUES (new.rowid, new.run_id, new.prompt, new.insights, new.signals, new.symbols);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS episodes_ad
                AFTER DELETE ON episodes BEGIN
                    INSERT INTO episodes_fts(episodes_fts, rowid, run_id, prompt, insights, signals, symbols)
                    VALUES('delete', old.rowid, old.run_id, old.prompt, old.insights, old.signals, old.symbols);
                END
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    def ingest_run_result(self, run_result: Any) -> str:
        """
        Ingest a completed RunResult into episodic memory.
        `run_result` is the Pydantic RunResult model.
        """
        run_id = run_result.summary.run_id
        prompt = run_result.summary.prompt
        created_at = run_result.summary.created_at.isoformat()
        insights = "\n".join(run_result.insights or [])

        # Extract symbols from collector output
        symbols_list = [o.symbol for o in (run_result.collector_output or [])]
        symbols = ",".join(symbols_list)

        # Flatten oracle signals to JSON
        signals: dict[str, str] = {}
        for o in (run_result.oracle_output or []):
            signals[o.symbol] = o.signal

        # Scribe summary
        scribe_summary = ""
        if run_result.scribe_output:
            scribe_summary = run_result.scribe_output.executive_summary

        full_text = " ".join([prompt, insights, scribe_summary, symbols, json.dumps(signals)])

        episode_id = f"ep_{run_id[:8]}"

        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO episodes
                    (id, run_id, created_at, symbols, prompt, insights, signals, full_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode_id,
                    run_id,
                    created_at,
                    symbols,
                    prompt,
                    insights,
                    json.dumps(signals),
                    full_text,
                ),
            )

        logger.info("EpisodicMemory: ingested run %s (symbols: %s)", run_id, symbols)
        return episode_id

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        FTS5 full-text search over run history.
        Returns list of matching episode dicts, ranked by relevance (BM25 default).
        """
        if not query.strip():
            return []

        # Sanitize query for FTS5 (remove special chars that break FTS5 syntax)
        safe_query = _sanitize_fts_query(query)

        try:
            with self._conn() as conn:
                rows = conn.execute(
                    """
                    SELECT e.id, e.run_id, e.created_at, e.symbols,
                           e.prompt, e.insights, e.signals,
                           rank
                    FROM episodes_fts
                    JOIN episodes e ON e.rowid = episodes_fts.rowid
                    WHERE episodes_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (safe_query, limit),
                ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("EpisodicMemory FTS error for query '%s': %s", query, exc)
            return []

        results = []
        for row in rows:
            results.append({
                "id": row["id"],
                "run_id": row["run_id"],
                "created_at": row["created_at"],
                "symbols": row["symbols"].split(",") if row["symbols"] else [],
                "prompt": row["prompt"],
                "insights": row["insights"].split("\n") if row["insights"] else [],
                "signals": json.loads(row["signals"] or "{}"),
                "fts_rank": row["rank"],
            })
        return results

    def get_snapshot_for_prompt(self, query: str, max_episodes: int = 3) -> str:
        """
        Returns a concise text block suitable for injection into an agent system prompt.
        Contains the most relevant past analyses for the given query.
        """
        episodes = self.search(query, limit=max_episodes)
        if not episodes:
            return ""

        lines = ["## Relevant Past Analyses\n"]
        for ep in episodes:
            lines.append(f"**Run {ep['run_id'][:8]}** ({ep['created_at'][:10]})")
            if ep["symbols"]:
                lines.append(f"Symbols: {', '.join(ep['symbols'])}")
            if ep["signals"]:
                sig_str = ", ".join(f"{k}:{v}" for k, v in ep["signals"].items())
                lines.append(f"Signals: {sig_str}")
            if ep["insights"]:
                lines.append(ep["insights"][0])  # Top insight only
            lines.append("")

        return "\n".join(lines)

    def list_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return most recent episodes, no text search."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, run_id, created_at, symbols, prompt FROM episodes ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]


def _sanitize_fts_query(query: str) -> str:
    """Strip FTS5-special characters to prevent query parse errors."""
    # Keep alphanumerics, spaces, dots — remove FTS5 operators
    safe = "".join(c if c.isalnum() or c in " .-_" else " " for c in query)
    # Collapse whitespace
    parts = safe.split()
    if not parts:
        return '""'
    # Join with implicit AND
    return " ".join(parts)
