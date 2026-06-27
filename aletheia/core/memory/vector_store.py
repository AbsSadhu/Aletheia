"""
Vector Memory Store — semantic search over episodic memory.

Backend: sqlite-vec (pip install sqlite-vec) with Ollama nomic-embed-text embeddings.
Fallback: BM25 keyword search (using existing bm25_score_rust from PyO3).

Usage:
    store = VectorMemoryStore(db_path="data/memory.db")
    await store.store("RELIANCE: Oracle emitted BUY signal on 2025-01-15", {"run_id": "abc"})
    results = await store.search("RELIANCE momentum signal", k=5)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EMBEDDING_DIM = 768  # nomic-embed-text dimension


@dataclass
class MemoryResult:
    text: str
    metadata: dict[str, Any]
    score: float
    row_id: int


class VectorMemoryStore:
    """
    Semantic vector store backed by sqlite-vec.
    Falls back to BM25 if sqlite-vec extension is unavailable.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._use_vector = False
        self._conn: sqlite3.Connection | None = None
        self._embedding_model = "nomic-embed-text"
        self._ollama_url = "http://localhost:11434/api/embeddings"
        self._init()

    def _init(self) -> None:
        """Initialize the store. Try sqlite-vec first, fall back to BM25."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row

        try:
            import sqlite_vec  # type: ignore[import]

            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            # Create vector table
            conn.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec
                USING vec0(
                    embedding FLOAT[{_EMBEDDING_DIM}]
                )
                """
            )
            self._use_vector = True
            logger.info("VectorMemoryStore: sqlite-vec enabled.")
        except (ImportError, Exception) as exc:
            logger.info(
                "VectorMemoryStore: sqlite-vec unavailable (%s) — using BM25 fallback.", exc
            )
            self._use_vector = False

        # Always create text + metadata table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                text_tokens TEXT  -- space-separated lowercase tokens for BM25
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at)")
        conn.commit()
        self._conn = conn

    async def store(self, text: str, metadata: dict[str, Any] | None = None) -> int:
        """Store a memory. Returns row_id."""
        metadata = metadata or {}
        tokens = self._tokenize(text)

        assert self._conn is not None
        cursor = self._conn.execute(
            "INSERT INTO memories (text, metadata_json, text_tokens) VALUES (?, ?, ?)",
            (text, json.dumps(metadata), tokens),
        )
        row_id = cursor.lastrowid
        self._conn.commit()

        if self._use_vector:
            try:
                embedding = await self._embed(text)
                if embedding:
                    self._conn.execute(
                        "INSERT INTO memory_vec (rowid, embedding) VALUES (?, vec_f32(?))",
                        (row_id, json.dumps(embedding)),
                    )
                    self._conn.commit()
            except Exception as exc:
                logger.debug("VectorMemoryStore: embedding failed for row %d: %s", row_id, exc)

        return row_id

    async def search(self, query: str, k: int = 5) -> list[MemoryResult]:
        """Semantic search. Falls back to BM25 if embeddings unavailable."""
        if self._use_vector:
            try:
                return await self._vector_search(query, k)
            except Exception as exc:
                logger.debug("Vector search failed, falling back to BM25: %s", exc)

        return self._bm25_search(query, k)

    async def _vector_search(self, query: str, k: int) -> list[MemoryResult]:
        embedding = await self._embed(query)
        if not embedding:
            return self._bm25_search(query, k)

        assert self._conn is not None
        rows = self._conn.execute(
            """
            SELECT m.id, m.text, m.metadata_json, v.distance
            FROM memory_vec v
            JOIN memories m ON m.id = v.rowid
            WHERE v.embedding MATCH vec_f32(?)
            ORDER BY v.distance ASC
            LIMIT ?
            """,
            (json.dumps(embedding), k),
        ).fetchall()

        return [
            MemoryResult(
                text=row["text"],
                metadata=json.loads(row["metadata_json"] or "{}"),
                score=1.0 / (1.0 + float(row["distance"])),
                row_id=row["id"],
            )
            for row in rows
        ]

    def _bm25_search(self, query: str, k: int) -> list[MemoryResult]:
        """BM25 keyword search using Rust bm25_score_rust PyO3 function."""
        assert self._conn is not None
        query_tokens = set(self._tokenize(query).split())

        rows = self._conn.execute(
            "SELECT id, text, metadata_json, text_tokens FROM memories ORDER BY created_at DESC LIMIT 500"
        ).fetchall()

        if not rows:
            return []

        # Score with Rust BM25 if available, else simple overlap
        try:
            import aletheia_rust

            scored = []
            corpus = [row["text_tokens"] for row in rows]
            for i, row in enumerate(rows):
                score = aletheia_rust.bm25_score_rust(row["text_tokens"], corpus, query)
                scored.append((score, row))
        except Exception:
            # Simple TF overlap fallback
            scored = []
            for row in rows:
                doc_tokens = set((row["text_tokens"] or "").split())
                score = len(query_tokens & doc_tokens) / max(1, len(query_tokens))
                scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            MemoryResult(
                text=row["text"],
                metadata=json.loads(row["metadata_json"] or "{}"),
                score=score,
                row_id=row["id"],
            )
            for score, row in scored[:k]
        ]

    async def _embed(self, text: str) -> list[float] | None:
        """Call Ollama nomic-embed-text for embeddings."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self._ollama_url,
                    json={"model": self._embedding_model, "prompt": text},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("embedding")
        except Exception as exc:
            logger.debug("Embedding failed: %s", exc)
            return None

    @staticmethod
    def _tokenize(text: str) -> str:
        """Lowercase, split on non-alphanumeric, return space-joined tokens."""
        import re

        tokens = re.findall(r"\b[a-z0-9]{2,}\b", text.lower())
        return " ".join(tokens)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
