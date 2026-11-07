"""SQLite persistence for sentiment-flip alerts and each symbol's last stable tone.

Without it every restart forgets the history, and the first reading after start would be silently
treated as a baseline even when the tone had flipped while the app was closed.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class NewsAlertStore:
    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS news_alerts ("
                "id TEXT PRIMARY KEY, t TEXT NOT NULL, symbol TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_news_alerts_t ON news_alerts (t DESC)")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS news_states (symbol TEXT PRIMARY KEY, state TEXT NOT NULL)"
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def add_alert(self, alert: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO news_alerts (id, t, symbol, payload) VALUES (?, ?, ?, ?)",
                (alert["id"], alert["t"], alert["symbol"], json.dumps(alert)),
            )

    def recent_alerts(self, limit: int = 100) -> list[dict[str, Any]]:
        """Newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM news_alerts ORDER BY t DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def save_state(self, symbol: str, state: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO news_states (symbol, state) VALUES (?, ?)", (symbol, state)
            )

    def states(self) -> dict[str, str]:
        with self._conn() as conn:
            return dict(conn.execute("SELECT symbol, state FROM news_states").fetchall())
