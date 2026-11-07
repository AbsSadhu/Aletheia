"""Discovery of the models the chat panel can use.

Ollama is the default provider, so the interesting part is asking the running Ollama server what
is on disk (`/api/tags`) and pulling new models into it (`/api/pull`).
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)


def normalize_ollama_name(name: str) -> str:
    """Ollama treats `qwen2.5` and `qwen2.5:latest` as the same model."""
    return name if ":" in name else f"{name}:latest"


async def list_ollama_models(base_url: str) -> tuple[list[dict[str, Any]], str | None]:
    """Return (models on disk, error). `error` is None when the server answered."""
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(f"{base_url.rstrip('/')}/api/tags")
            r.raise_for_status()
            raw = r.json().get("models", [])
    except Exception as exc:
        return [], f"Ollama not reachable at {base_url} ({type(exc).__name__})"

    models = []
    for m in raw:
        details = m.get("details") or {}
        models.append(
            {
                "model": m.get("name") or m.get("model", ""),
                "size_bytes": m.get("size", 0),
                "parameter_size": details.get("parameter_size"),
                "quantization": details.get("quantization_level"),
                "family": details.get("family"),
                "modified_at": m.get("modified_at"),
            }
        )
    models.sort(key=lambda x: x["model"])
    return models, None


async def pull_ollama_model(base_url: str, name: str) -> AsyncIterator[dict[str, Any]]:
    """Stream `ollama pull` progress as dicts: {status, completed?, total?} then {status:"success"}.

    Raises on connection failure; an error reported by Ollama mid-stream is yielded as
    {"error": "..."} so the caller can forward it.
    """
    url = f"{base_url.rstrip('/')}/api/pull"
    async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5.0)) as client:
        async with client.stream("POST", url, json={"model": name, "stream": True}) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode(errors="replace")[:300]
                yield {"error": f"Ollama returned {resp.status_code}: {body}"}
                return
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Skipping non-JSON pull line: %r", line[:80])
