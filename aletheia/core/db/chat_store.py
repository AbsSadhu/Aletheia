"""SQLite storage for the chat panel: threads, messages and user-added custom models.

Kept in its own file (`<data_dir>/chat.sqlite3`) so chat history never touches the run/execution
databases. Connections are opened per call; the chat volume is tiny.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    steps TEXT,
    provider TEXT,
    model TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, id);
CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    order_json TEXT NOT NULL,
    display TEXT NOT NULL,
    status TEXT NOT NULL,
    outcome TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE TABLE IF NOT EXISTS custom_models (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    label TEXT NOT NULL,
    base_url TEXT,
    api_key TEXT,
    created_at TEXT NOT NULL
);
"""

# Tool results can be huge (price histories, filings); keep what's stored per step bounded.
_MAX_STEP_RESULT_CHARS = 8000
# A step's `display` payload (chart bars) must stay whole to be re-renderable, so it is kept
# intact up to this size and dropped, not cut, beyond it.
_MAX_STEP_DISPLAY_CHARS = 400_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_thread(self, title: str, provider: str | None, model: str | None) -> str:
        thread_id = uuid.uuid4().hex
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO threads (id, title, provider, model, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (thread_id, title[:80] or "New chat", provider, model, now, now),
            )
        return thread_id

    def list_threads(self, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, title, provider, model, created_at, updated_at FROM threads "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, title, provider, model, created_at, updated_at FROM threads "
                "WHERE id = ?",
                (thread_id,),
            ).fetchone()
            if row is None:
                return None
            msgs = conn.execute(
                "SELECT id, role, content, steps, provider, model, created_at FROM messages "
                "WHERE thread_id = ? ORDER BY id",
                (thread_id,),
            ).fetchall()
        thread = dict(row)
        thread["messages"] = [
            {**dict(m), "steps": json.loads(m["steps"]) if m["steps"] else []} for m in msgs
        ]
        return thread

    def rename_thread(self, thread_id: str, title: str) -> bool:
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE threads SET title = ? WHERE id = ?", (title[:80] or "New chat", thread_id)
            )
        return cur.rowcount > 0

    def delete_thread(self, thread_id: str) -> bool:
        with closing(self._connect()) as conn, conn:
            cur = conn.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
        return cur.rowcount > 0

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        *,
        steps: list[dict[str, Any]] | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        stored_steps = None
        if steps:
            stored_steps = json.dumps(
                [_truncate_step(s) for s in steps], default=str, ensure_ascii=False
            )
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO messages (thread_id, role, content, steps, provider, model, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (thread_id, role, content, stored_steps, provider, model, now),
            )
            conn.execute(
                "UPDATE threads SET updated_at = ?, provider = COALESCE(?, provider), "
                "model = COALESCE(?, model) WHERE id = ?",
                (now, provider, model, thread_id),
            )

    def history(self, thread_id: str, limit: int = 20) -> list[dict[str, str]]:
        """The last `limit` user/assistant turns as plain {role, content}, oldest first."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE thread_id = ? AND content != '' "
                "ORDER BY id DESC LIMIT ?",
                (thread_id, limit),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # A proposal is only ever a request for the user to confirm. `claim_proposal` flips
    # pending -> executing in one UPDATE, so a double-click or a reopened thread can't run it twice.

    def create_proposal(
        self, thread_id: str, order: dict[str, Any], display: dict[str, Any]
    ) -> str:
        proposal_id = uuid.uuid4().hex
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO proposals (id, thread_id, order_json, display, status, created_at) "
                "VALUES (?, ?, ?, ?, 'pending', ?)",
                (proposal_id, thread_id, json.dumps(order), json.dumps(display), _now()),
            )
        return proposal_id

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["order"] = json.loads(out.pop("order_json"))
        out["display"] = json.loads(out["display"])
        out["outcome"] = json.loads(out["outcome"]) if out["outcome"] else None
        return out

    def claim_proposal(self, proposal_id: str, max_age_secs: float) -> str:
        """Atomically take a pending proposal for execution.

        Returns "claimed", or the status that prevented it ("executed", "rejected", "expired",
        "executing", "failed", "missing").
        """
        found = self.get_proposal(proposal_id)
        if found is None:
            return "missing"
        age = (
            datetime.now(timezone.utc) - datetime.fromisoformat(found["created_at"])
        ).total_seconds()
        with closing(self._connect()) as conn, conn:
            if found["status"] == "pending" and age > max_age_secs:
                conn.execute(
                    "UPDATE proposals SET status = 'expired', decided_at = ? "
                    "WHERE id = ? AND status = 'pending'",
                    (_now(), proposal_id),
                )
                return "expired"
            cur = conn.execute(
                "UPDATE proposals SET status = 'executing', decided_at = ? "
                "WHERE id = ? AND status = 'pending'",
                (_now(), proposal_id),
            )
        if cur.rowcount == 1:
            return "claimed"
        latest = self.get_proposal(proposal_id)
        return latest["status"] if latest else "missing"

    def finish_proposal(self, proposal_id: str, status: str, outcome: dict[str, Any]) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE proposals SET status = ?, outcome = ?, decided_at = ? WHERE id = ?",
                (status, json.dumps(outcome, default=str), _now(), proposal_id),
            )

    def reject_proposal(self, proposal_id: str) -> bool:
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE proposals SET status = 'rejected', decided_at = ? "
                "WHERE id = ? AND status = 'pending'",
                (_now(), proposal_id),
            )
        return cur.rowcount == 1

    def add_custom_model(
        self,
        provider: str,
        model: str,
        label: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Idempotent on (provider, model, base_url): re-adding returns the existing entry."""
        existing = self._find_custom(provider, model, base_url)
        if existing:
            return existing
        model_id = uuid.uuid4().hex
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO custom_models (id, provider, model, label, base_url, api_key, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (model_id, provider, model, label or model, base_url, api_key, _now()),
            )
        found = self.get_custom_model(model_id)
        assert found is not None
        return found

    def _find_custom(
        self, provider: str, model: str, base_url: str | None
    ) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM custom_models WHERE provider = ? AND model = ? "
                "AND COALESCE(base_url, '') = ?",
                (provider, model, base_url or ""),
            ).fetchone()
        return dict(row) if row else None

    def get_custom_model(self, model_id: str) -> dict[str, Any] | None:
        """Includes `api_key` — callers building an LLM need it; never return it to clients."""
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM custom_models WHERE id = ?", (model_id,)).fetchone()
        return dict(row) if row else None

    def list_custom_models(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM custom_models ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def delete_custom_model(self, model_id: str) -> bool:
        with closing(self._connect()) as conn, conn:
            cur = conn.execute("DELETE FROM custom_models WHERE id = ?", (model_id,))
        return cur.rowcount > 0


def _truncate_step(step: dict[str, Any]) -> dict[str, Any]:
    display = step.get("display")
    if display is not None and len(json.dumps(display, default=str)) > _MAX_STEP_DISPLAY_CHARS:
        step = {k: v for k, v in step.items() if k != "display"}
        step["display_dropped"] = True
    result = step.get("result")
    if isinstance(result, str) and len(result) > _MAX_STEP_RESULT_CHARS:
        return {**step, "result": result[:_MAX_STEP_RESULT_CHARS], "truncated": True}
    if result is not None and not isinstance(result, str):
        text = json.dumps(result, default=str, ensure_ascii=False)
        if len(text) > _MAX_STEP_RESULT_CHARS:
            return {**step, "result": text[:_MAX_STEP_RESULT_CHARS], "truncated": True}
    return step
