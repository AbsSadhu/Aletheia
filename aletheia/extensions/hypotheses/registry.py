import sqlite3
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import List, Optional

from aletheia.extensions.hypotheses.models import Hypothesis, Evidence

logger = logging.getLogger(__name__)

# Valid state machine transitions
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "proposed": {"testing", "rejected"},
    "testing": {"validated", "rejected", "proposed"},
    "validated": {"rejected"},
    "rejected": {"proposed"},
}


class HypothesisRegistry:
    """SQLite-backed store for research hypotheses."""

    def __init__(self, db_path: str = "hypotheses.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hypotheses (
                    id           TEXT PRIMARY KEY,
                    title        TEXT,
                    description  TEXT,
                    status       TEXT,
                    test_criteria TEXT,
                    evidence     TEXT,
                    backtest_run_id TEXT DEFAULT NULL,
                    created_at   TIMESTAMP,
                    updated_at   TIMESTAMP
                )
            """)
            # Migration: add backtest_run_id column if missing
            try:
                conn.execute("ALTER TABLE hypotheses ADD COLUMN backtest_run_id TEXT DEFAULT NULL")
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.commit()

    def propose(self, title: str, description: str, test_criteria: str) -> Hypothesis:
        hypo = Hypothesis(
            id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            test_criteria=test_criteria,
        )
        self.save(hypo)
        return hypo

    def save(self, hypo: Hypothesis):
        with sqlite3.connect(self.db_path) as conn:
            evidence_json = json.dumps([e.model_dump(mode="json") for e in hypo.evidence])
            conn.execute(
                """
                INSERT OR REPLACE INTO hypotheses
                (id, title, description, status, test_criteria, evidence, backtest_run_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    hypo.id,
                    hypo.title,
                    hypo.description,
                    hypo.status,
                    hypo.test_criteria,
                    evidence_json,
                    hypo.backtest_run_id,
                    hypo.created_at.isoformat(),
                    hypo.updated_at.isoformat(),
                ),
            )
            conn.commit()

    def get(self, hypo_id: str) -> Optional[Hypothesis]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM hypotheses WHERE id = ?", (hypo_id,)).fetchone()
            if row:
                evidence_list = []
                for e_dict in json.loads(row["evidence"]):
                    evidence_list.append(Evidence(**e_dict))

                return Hypothesis(
                    id=row["id"],
                    title=row["title"],
                    description=row["description"],
                    status=row["status"],
                    test_criteria=row["test_criteria"],
                    evidence=evidence_list,
                    backtest_run_id=row["backtest_run_id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
            return None

    def list_all(self, status: Optional[str] = None) -> List[Hypothesis]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM hypotheses WHERE status = ? ORDER BY updated_at DESC", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM hypotheses ORDER BY updated_at DESC").fetchall()

            results = []
            for row in rows:
                evidence_list = [Evidence(**e_dict) for e_dict in json.loads(row["evidence"])]
                results.append(
                    Hypothesis(
                        id=row["id"],
                        title=row["title"],
                        description=row["description"],
                        status=row["status"],
                        test_criteria=row["test_criteria"],
                        evidence=evidence_list,
                        backtest_run_id=row["backtest_run_id"],
                        created_at=datetime.fromisoformat(row["created_at"]),
                        updated_at=datetime.fromisoformat(row["updated_at"]),
                    )
                )
            return results

    def transition(self, hypo_id: str, new_status: str) -> Hypothesis:
        """
        Transition a hypothesis to a new status.
        Raises ValueError for invalid transitions or missing hypothesis.
        """
        hypo = self.get(hypo_id)
        if hypo is None:
            raise ValueError(f"Hypothesis '{hypo_id}' not found")

        allowed = _VALID_TRANSITIONS.get(hypo.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: '{hypo.status}' → '{new_status}'. "
                f"Allowed: {allowed or {'none'}}"
            )

        hypo.status = new_status
        hypo.updated_at = datetime.now(UTC)
        self.save(hypo)
        logger.info("Hypothesis %s transitioned to '%s'", hypo_id, new_status)
        return hypo

    def link_to_backtest(self, hypo_id: str, backtest_run_id: str) -> Hypothesis:
        """Link a hypothesis to a backtest run for validation tracking."""
        hypo = self.get(hypo_id)
        if hypo is None:
            raise ValueError(f"Hypothesis '{hypo_id}' not found")

        hypo.backtest_run_id = backtest_run_id
        hypo.updated_at = datetime.now(UTC)
        self.save(hypo)
        logger.info("Hypothesis %s linked to backtest %s", hypo_id, backtest_run_id)
        return hypo

    def add_evidence(self, hypo_id: str, source: str, summary: str, supports: bool) -> Hypothesis:
        """Append a new evidence entry to a hypothesis."""
        hypo = self.get(hypo_id)
        if hypo is None:
            raise ValueError(f"Hypothesis '{hypo_id}' not found")

        hypo.evidence.append(
            Evidence(source=source, description=summary, supports_hypothesis=supports)
        )
        hypo.updated_at = datetime.now(UTC)
        self.save(hypo)
        return hypo

    def list_by_status(self, status: str) -> List[Hypothesis]:
        """Return hypotheses filtered by status."""
        return self.list_all(status=status)
