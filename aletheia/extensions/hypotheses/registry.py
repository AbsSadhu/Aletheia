import sqlite3
import json
import logging
import uuid
from typing import List, Optional
from datetime import datetime, UTC

from aletheia.extensions.hypotheses.models import Hypothesis, Evidence

logger = logging.getLogger(__name__)

class HypothesisRegistry:
    """SQLite-backed store for research hypotheses."""

    def __init__(self, db_path: str = "hypotheses.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS hypotheses (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    status TEXT,
                    test_criteria TEXT,
                    evidence TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            ''')
            conn.commit()

    def propose(self, title: str, description: str, test_criteria: str) -> Hypothesis:
        hypo = Hypothesis(
            id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            test_criteria=test_criteria
        )
        self.save(hypo)
        return hypo

    def save(self, hypo: Hypothesis):
        with sqlite3.connect(self.db_path) as conn:
            evidence_json = json.dumps([e.model_dump(mode='json') for e in hypo.evidence])
            conn.execute('''
                INSERT OR REPLACE INTO hypotheses 
                (id, title, description, status, test_criteria, evidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                hypo.id, hypo.title, hypo.description, hypo.status, 
                hypo.test_criteria, evidence_json, 
                hypo.created_at.isoformat(), hypo.updated_at.isoformat()
            ))
            conn.commit()

    def get(self, hypo_id: str) -> Optional[Hypothesis]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM hypotheses WHERE id = ?", (hypo_id,)).fetchone()
            if row:
                evidence_list = []
                for e_dict in json.loads(row['evidence']):
                    evidence_list.append(Evidence(**e_dict))
                
                return Hypothesis(
                    id=row['id'],
                    title=row['title'],
                    description=row['description'],
                    status=row['status'],
                    test_criteria=row['test_criteria'],
                    evidence=evidence_list,
                    created_at=datetime.fromisoformat(row['created_at']),
                    updated_at=datetime.fromisoformat(row['updated_at'])
                )
            return None

    def list_all(self, status: Optional[str] = None) -> List[Hypothesis]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute("SELECT * FROM hypotheses WHERE status = ? ORDER BY updated_at DESC", (status,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM hypotheses ORDER BY updated_at DESC").fetchall()
            
            results = []
            for row in rows:
                evidence_list = [Evidence(**e_dict) for e_dict in json.loads(row['evidence'])]
                results.append(Hypothesis(
                    id=row['id'],
                    title=row['title'],
                    description=row['description'],
                    status=row['status'],
                    test_criteria=row['test_criteria'],
                    evidence=evidence_list,
                    created_at=datetime.fromisoformat(row['created_at']),
                    updated_at=datetime.fromisoformat(row['updated_at'])
                ))
            return results
