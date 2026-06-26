from __future__ import annotations

from aletheia.core.models import Portfolio


class AgentContext:
    """Manages the context and system prompt for the ReAct loop."""

    def __init__(
        self,
        portfolio: Portfolio | None = None,
        memory_snapshots: list[str] | None = None,
    ):
        self.portfolio = portfolio
        self.memory_snapshots = memory_snapshots or []

    @classmethod
    def from_query(cls, query: str, portfolio: Portfolio | None = None) -> "AgentContext":
        """
        Build context with automatic memory recall for the given query.
        Injects relevant episodic + semantic memory into the system prompt.
        """
        snapshots: list[str] = []
        try:
            from aletheia.core.config.settings import get_settings
            from aletheia.core.memory.persistent import PersistentMemory

            settings = get_settings()
            memory = PersistentMemory(memory_dir=settings.memory_dir)
            snippet = memory.build_system_prompt_snippet(query)
            if snippet:
                snapshots.append(snippet)
        except Exception:
            pass  # Memory unavailable — degrade gracefully

        return cls(portfolio=portfolio, memory_snapshots=snapshots)

    def build_system_prompt(self) -> str:
        prompt = (
            "You are an expert AI financial agent, part of the Aletheia intelligence system. "
            "Your objective is to analyze financial data, run backtests, and provide actionable insights. "
            "You have access to a set of specialized tools. "
            "Use them iteratively to gather information before giving a final answer.\n\n"
        )

        if self.portfolio and self.portfolio.holdings:
            prompt += "CURRENT PORTFOLIO STATE:\n"
            for holding in self.portfolio.holdings:
                prompt += (
                    f"- {holding.symbol}: {holding.quantity} units "
                    f"@ avg price {holding.average_price} "
                    f"({holding.asset_type.value}, {holding.tax_profile.value})\n"
                )
            prompt += "\n"

        if self.memory_snapshots:
            prompt += "PERSISTENT MEMORY CONTEXT:\n"
            for mem in self.memory_snapshots:
                prompt += f"{mem}\n"
            prompt += "\n"

        prompt += (
            "INSTRUCTIONS:\n"
            "1. Read the user's request carefully.\n"
            "2. Think step-by-step about what tools you need to answer the request.\n"
            "3. Call the necessary tools. Wait for their results.\n"
            "4. Once you have all the information, provide a final, comprehensive answer.\n"
            "5. If a tool returns an error, try an alternative approach or inform the user.\n"
            "6. Be specific with numbers, percentages, and dates in your final answer.\n"
        )
        return prompt
