"""
3-Tier Persistent Memory System.

Tiers:
    Working   — in-process dict; cleared between runs; fast
    Episodic  — SQLite FTS5; auto-ingested from run results; searchable by text
    Semantic  — YAML-frontmatter .md files; long-term facts, user preferences, references

Usage:
    memory = PersistentMemory()
    memory.store_semantic("user", "User prefers INR, India equity focus", "prefs")
    snippets = memory.search("RELIANCE signal")
    snapshot = memory.build_system_prompt_snippet("analyse RELIANCE portfolio")
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

from aletheia.core.memory.episodic import EpisodicMemory

logger = logging.getLogger(__name__)


class PersistentMemory:
    """
    Unified 3-tier memory.

    Tier 1 — Working  : dict[str, Any]  (in-process, cleared per-run)
    Tier 2 — Episodic : SQLite FTS5     (auto-populated from RunResult)
    Tier 3 — Semantic : YAML .md files  (hand-crafted / agent-authored facts)
    """

    def __init__(self, memory_dir: str = "~/.aletheia/memory"):
        self.memory_dir = Path(os.path.expanduser(memory_dir))
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.semantic_dir = self.memory_dir / "semantic"
        self.semantic_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.memory_dir / "MEMORY.md"

        # Tier 1
        self._working: dict[str, Any] = {}

        # Tier 2
        self.episodic = EpisodicMemory(db_path=self.memory_dir / "episodic.db")

    # ------------------------------------------------------------------
    # Tier 1 — Working Memory
    # ------------------------------------------------------------------

    def set_working(self, key: str, value: Any) -> None:
        """Store a value in working memory for the current session."""
        self._working[key] = value

    def get_working(self, key: str, default: Any = None) -> Any:
        return self._working.get(key, default)

    def clear_working(self) -> None:
        """Clear working memory (call at start of each run)."""
        self._working.clear()

    # ------------------------------------------------------------------
    # Tier 3 — Semantic Memory (.md files with YAML frontmatter)
    # ------------------------------------------------------------------

    def store_semantic(
        self,
        memory_type: str,
        content: str,
        memory_id: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """
        Store a semantic memory snippet.

        memory_type: one of 'user', 'feedback', 'project', 'reference', 'market'
        Returns the memory_id (can be used for recall/update).
        """
        if not memory_id:
            memory_id = str(uuid.uuid4())[:8]

        tags_line = ", ".join(tags or [])
        file_path = self.semantic_dir / f"{memory_type}_{memory_id}.md"
        frontmatter = f"---\ntype: {memory_type}\nid: {memory_id}\ntags: [{tags_line}]\n---\n\n"

        file_path.write_text(frontmatter + content + "\n", encoding="utf-8")
        self._rebuild_index()
        logger.info("PersistentMemory: stored semantic/%s/%s", memory_type, memory_id)
        return memory_id

    def recall_semantic(self, memory_type: str, memory_id: str) -> str | None:
        """Recall a specific semantic memory by type + id."""
        file_path = self.semantic_dir / f"{memory_type}_{memory_id}.md"
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return None

    def search_semantic(self, query: str) -> list[dict[str, str]]:
        """
        Keyword search over semantic .md files.
        Returns list of {file, snippet} dicts, sorted by relevance (basic BM25 via Rust if available).
        """
        query_lower = query.lower()
        candidates: list[tuple[str, str, int]] = []  # (file, snippet, hit_count)

        for fp in self.semantic_dir.glob("*.md"):
            text = fp.read_text(encoding="utf-8")
            hits = text.lower().count(query_lower)
            if hits > 0:
                candidates.append((fp.name, text[:300], hits))

        # Sort by hit count descending (poor-man's relevance)
        candidates.sort(key=lambda x: x[2], reverse=True)

        # Try Rust BM25 if available
        candidates = _rerank_with_rust_bm25(query, candidates)

        return [{"file": f, "content_snippet": s} for f, s, _ in candidates]

    # ------------------------------------------------------------------
    # Combined search across all tiers
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 8) -> dict[str, Any]:
        """
        Search across Episodic + Semantic tiers.
        Working memory is not searched (it's ephemeral).

        Returns:
            {
                "episodic": [...],   # from FTS5 run history
                "semantic": [...],   # from .md files
            }
        """
        episodic_results = self.episodic.search(query, limit=limit // 2 + 1)
        semantic_results = self.search_semantic(query)[: limit // 2 + 1]
        return {"episodic": episodic_results, "semantic": semantic_results}

    def build_system_prompt_snippet(self, query: str) -> str:
        """
        Build a compact memory block for injection into agent system prompts.
        Pulls from both episodic and semantic tiers.
        """
        blocks: list[str] = []

        # Episodic snapshot
        ep_snapshot = self.episodic.get_snapshot_for_prompt(query, max_episodes=3)
        if ep_snapshot:
            blocks.append(ep_snapshot)

        # Semantic facts relevant to query
        sem_results = self.search_semantic(query)[:2]
        if sem_results:
            blocks.append("## Relevant Facts\n")
            for r in sem_results:
                blocks.append(f"- {r['content_snippet'].strip()[:200]}")
            blocks.append("")

        return "\n".join(blocks) if blocks else ""

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def _rebuild_index(self) -> None:
        """Rebuild the human-readable MEMORY.md index."""
        semantic_entries = list(self.semantic_dir.glob("*.md"))
        episodic_count = self.episodic.count()

        lines = [
            "# Aletheia Memory Index\n",
            f"Episodic runs indexed: **{episodic_count}**\n",
            f"Semantic entries: **{len(semantic_entries)}**\n",
            "",
            "## Semantic Files",
        ]
        for fp in sorted(semantic_entries):
            lines.append(f"- `{fp.name}`")

        self.index_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # Legacy compatibility shim
    # ------------------------------------------------------------------

    def store(self, memory_type: str, content: str, memory_id: str | None = None) -> str:
        """Backward-compat: store semantic memory (previously was in root memory_dir)."""
        return self.store_semantic(memory_type, content, memory_id)

    def recall(self, memory_type: str, memory_id: str) -> str | None:
        """Backward-compat: recall semantic memory."""
        return self.recall_semantic(memory_type, memory_id)


def _rerank_with_rust_bm25(
    query: str,
    candidates: list[tuple[str, str, int]],
) -> list[tuple[str, str, int]]:
    """
    Rerank candidates using Rust BM25 if the module is compiled.
    Falls back to hit-count order gracefully.
    """
    if not candidates:
        return candidates
    try:
        from aletheia_rust import bm25_score_rust  # type: ignore[import]

        docs = [snippet for _, snippet, _ in candidates]
        scores = bm25_score_rust(query, docs, 1.5, 0.75)
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        return [item for item, _ in ranked]
    except ImportError:
        return candidates  # Rust module not compiled — fall back silently
    except Exception as exc:
        logger.debug("BM25 rerank skipped: %s", exc)
        return candidates
