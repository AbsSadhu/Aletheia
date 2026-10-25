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


def _team(specs: list[tuple[str, str, list[str]]]) -> List[SwarmWorker]:
    registry = build_registry()
    llm = OllamaChatLLM()
    return [
        SwarmWorker(
            name=name,
            role_description=role,
            llm=llm,
            tool_registry=registry,
            allowed_tools=tools,
        )
        for name, role, tools in specs
    ]


def get_quant_team() -> List[SwarmWorker]:
    """Systematic research: test an idea, size the risk, and refuse to trust a thin sample."""
    return _team(
        [
            (
                "Factor Researcher",
                "a quantitative researcher who evaluates momentum, mean-reversion and volume "
                "factors. Report the sample size behind every claim and say so when it is small.",
                ["market_data", "technical_analysis"],
            ),
            (
                "Backtest Engineer",
                "a backtest engineer who runs strategies with realistic costs and Indian tax "
                "treatment. Treat any Sharpe under 1.0 or fewer than 30 trades as inconclusive.",
                ["backtest", "market_data"],
            ),
            (
                "Risk Quant",
                "a risk quant focused on VaR, drawdown and correlation. Flag any position above "
                "20% of the portfolio.",
                ["portfolio_analytics", "backtest"],
            ),
        ]
    )


def get_crypto_team() -> List[SwarmWorker]:
    """24/7, high-volatility assets: wider ranges, no earnings, heavy on liquidity and news."""
    return _team(
        [
            (
                "Crypto Technical Analyst",
                "a crypto technical analyst. Markets trade 24/7 and are far more volatile than "
                "equities, so judge moves against realised volatility, not equity-style 2% bands. "
                "Quote prices in both USDT and INR where relevant.",
                ["market_data", "technical_analysis"],
            ),
            (
                "Crypto News Analyst",
                "a crypto news analyst tracking exchange listings, protocol upgrades, regulation "
                "and hacks. Distinguish confirmed reports from rumours.",
                ["news_search", "web_search", "web_reader"],
            ),
            (
                "Crypto Risk Manager",
                "a risk manager for crypto. Assume 30% drawdowns happen, check correlation to "
                "BTC, and remember Indian VDA tax: a flat 30% on gains with no loss set-off and "
                "1% TDS on transfers.",
                ["portfolio_analytics", "backtest"],
            ),
        ]
    )


def get_macro_team() -> List[SwarmWorker]:
    """Top-down view: rates, currency, flows and sector rotation before single stocks."""
    return _team(
        [
            (
                "Macro Economist",
                "a macro economist covering RBI policy, inflation, INR/USD, crude and FII/DII "
                "flows, and how each transmits to Indian equity sectors.",
                ["news_search", "web_search", "web_reader"],
            ),
            (
                "Sector Strategist",
                "a sector strategist deciding which NSE sectors benefit from the current macro "
                "regime, using peer comparisons rather than single-stock stories.",
                ["sector_peers", "fundamental_data", "market_data"],
            ),
            (
                "Portfolio Risk Manager",
                "a risk manager checking that the macro view does not concentrate the portfolio "
                "in one sector or one rate/currency bet.",
                ["portfolio_analytics"],
            ),
        ]
    )


def get_smallcap_team() -> List[SwarmWorker]:
    """Illiquid, under-covered names: governance and liquidity come before valuation."""
    return _team(
        [
            (
                "Forensic Accountant",
                "a forensic accountant for small caps. Look for promoter pledging, related-party "
                "transactions, auditor changes and cash flow that does not match profit. Any "
                "unexplained red flag outweighs a cheap valuation.",
                ["sec_filings", "fundamental_data", "web_reader"],
            ),
            (
                "Liquidity Analyst",
                "a liquidity analyst. Estimate days to exit at 10% of average daily volume and "
                "refuse to size a position that cannot be exited in a few sessions.",
                ["market_data", "technical_analysis"],
            ),
            (
                "Small-cap Risk Manager",
                "a risk manager who caps any single small-cap at a few percent of the portfolio "
                "and assumes wider spreads and gap risk than for large caps.",
                ["portfolio_analytics", "backtest"],
            ),
        ]
    )


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
    "quant_team": get_quant_team,
    "crypto_team": get_crypto_team,
    "macro_team": get_macro_team,
    "smallcap_team": get_smallcap_team,
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
