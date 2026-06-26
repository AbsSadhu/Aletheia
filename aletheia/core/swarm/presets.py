from typing import List
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
