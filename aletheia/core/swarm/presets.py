from typing import Callable, List
from aletheia.core.swarm.worker import SwarmWorker
from aletheia.core.llm.chat_llm import OllamaChatLLM
from aletheia.core.tools.registry import build_registry


def get_investment_team() -> List[SwarmWorker]:
    """Returns a pre-configured investment analysis swarm."""
    registry = build_registry()
    llm = OllamaChatLLM()

    return [
        SwarmWorker(
            name="Fundamental Analyst",
            role_description="an expert fundamental analyst focused on earnings, valuations, and balance sheets.",
            llm=llm,
            tool_registry=registry,
            allowed_tools=["fundamental_data", "sec_filings", "sector_peers"],
        ),
        SwarmWorker(
            name="Technical Analyst",
            role_description="a seasoned technical analyst focused on price action, momentum, and trends.",
            llm=llm,
            tool_registry=registry,
            allowed_tools=["market_data", "technical_analysis"],
        ),
        SwarmWorker(
            name="Risk Manager",
            role_description="a strict risk manager focused on downside protection, VaR, and correlations.",
            llm=llm,
            tool_registry=registry,
            allowed_tools=["portfolio_analytics", "backtest"],
        ),
    ]


def get_due_diligence_team() -> List[SwarmWorker]:
    """Returns a team focused on news and SEC filings."""
    registry = build_registry()
    llm = OllamaChatLLM()

    return [
        SwarmWorker(
            name="News Analyst",
            role_description="an investigative financial journalist tracking market sentiment and breaking news.",
            llm=llm,
            tool_registry=registry,
            allowed_tools=["news_search", "web_search", "web_reader"],
        ),
        SwarmWorker(
            name="SEC Analyst",
            role_description="a forensic accountant scouring EDGAR filings for red flags and forward-looking statements.",
            llm=llm,
            tool_registry=registry,
            allowed_tools=["sec_filings", "fundamental_data"],
        ),
    ]


# Preset registry: both presets above existed before this change but had
# zero callers anywhere in the codebase — no CLI command, no API route, no
# test. This registry plus aletheia/core/api/routers/swarm.py is what
# actually makes them runnable, and register_preset() lets a plugin add
# another without touching this file (mirrors the strategy/provider plugin
# registration pattern in aletheia/extensions/backtest/strategies.py and
# aletheia/extensions/data/registry.py).
_PRESET_REGISTRY: dict[str, Callable[[], List[SwarmWorker]]] = {
    "investment_team": get_investment_team,
    "due_diligence_team": get_due_diligence_team,
}


def register_preset(name: str, factory: Callable[[], List[SwarmWorker]]) -> None:
    _PRESET_REGISTRY[name] = factory


def available_presets() -> list[str]:
    return sorted(_PRESET_REGISTRY)


def get_preset(name: str) -> List[SwarmWorker]:
    factory = _PRESET_REGISTRY.get(name)
    if factory is None:
        raise ValueError(
            f"Unknown swarm preset '{name}'. Available: {', '.join(available_presets())}"
        )
    return factory()
