"""Semantic/episodic memory search and per-agent working-memory endpoints.

GET /memory/search
GET /memory/vector-search
GET /memory/{agent_name}
GET /memory/{agent_name}/critique
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from aletheia.core.config.settings import get_settings

router = APIRouter(prefix="/api/v1")


@router.get("/memory/search")
async def memory_search(q: str, limit: int = 8) -> dict:
    """
    Semantic search over episodic run history and semantic memory files.
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query 'q' is required")

    settings = get_settings()
    from aletheia.core.memory.persistent import PersistentMemory

    memory = PersistentMemory(memory_dir=settings.memory_dir)
    results = memory.search(q, limit=limit)
    return results


@router.get("/memory/vector-search")
async def vector_search(q: str, limit: int = 5) -> dict:
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query 'q' is required")
    try:
        from aletheia.core.memory.vector_store import VectorMemoryStore

        store = VectorMemoryStore()
        results = store.search(q, k=limit)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {e}")


@router.get("/memory/{agent_name}")
async def get_agent_memory(
    agent_name: str,
    ticker: str | None = None,
    limit: int = 20,
) -> dict:
    """Retrieve working memory observations for a given agent."""
    from aletheia.memory.working_memory import WorkingMemory

    wm = WorkingMemory()
    observations = wm.list_all_observations(
        agent_name=agent_name,
        ticker=ticker.upper() if ticker else None,
        limit=limit,
    )
    return {"agent": agent_name, "observations": observations}


@router.get("/memory/{agent_name}/critique")
async def get_agent_critique(agent_name: str) -> dict:
    """Retrieve latest self-critique for a given agent."""
    from aletheia.memory.working_memory import WorkingMemory

    wm = WorkingMemory()
    critique = wm.get_latest_critique(agent_name)
    critiques = wm.get_critiques(agent_name, limit=5)
    return {"agent": agent_name, "latest_critique": critique, "history": critiques}
