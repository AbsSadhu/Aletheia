"""Read-only view of the hypothesis registry (the chat agent cannot create or change entries)."""

from typing import Any, ClassVar

from aletheia.core.tools.registry import BaseTool


class HypothesisTool(BaseTool):
    """Look up tracked research hypotheses."""

    name: ClassVar[str] = "hypothesis"
    description: ClassVar[str] = (
        "List or fetch the user's tracked research hypotheses (title, status, test criteria, "
        "evidence, linked backtest). Read-only."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "get"], "description": "Default list."},
            "status": {
                "type": "string",
                "enum": ["proposed", "testing", "validated", "rejected"],
                "description": "Only for list: filter by status.",
            },
            "id": {"type": "string", "description": "Only for get: the hypothesis id."},
        },
    }

    async def execute(
        self,
        action: str = "list",
        status: str | None = None,
        id: str | None = None,  # noqa: A002 - matches the tool schema the model sees
        **kwargs: Any,
    ) -> Any:
        from aletheia.core.api.routers.hypotheses import _get_hypothesis_registry

        registry = _get_hypothesis_registry()
        if action == "get":
            if not id:
                return {"error": "Pass the hypothesis id."}
            hypo = registry.get(id)
            if hypo is None:
                return {"error": f"No hypothesis with id {id}."}
            return hypo.model_dump(mode="json")
        items = registry.list_all(status=status)
        return {
            "count": len(items),
            "hypotheses": [
                {
                    "id": h.id,
                    "title": h.title,
                    "status": h.status,
                    "evidence_items": len(h.evidence),
                    "backtest_run_id": h.backtest_run_id,
                }
                for h in items
            ],
        }
