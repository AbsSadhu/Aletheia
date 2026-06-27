from pathlib import Path

import pytest

from aletheia.extensions.agents.oracle import OracleAgent
from aletheia.extensions.agents.sage import SageAgent
from aletheia.extensions.agents.scribe import ScribeAgent
from aletheia.extensions.agents.sentinel import SentinelAgent
from aletheia.extensions.agents.collector import CollectorAgent
from aletheia.extensions.data.providers.static_seed import StaticSeedProvider
from aletheia.core.db.duckdb_store import DuckDBStore
from aletheia.core.db.sqlite_store import SQLiteStore
from aletheia.core.services import RunService


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def run_service(temp_data_dir: Path) -> RunService:
    sqlite_store = SQLiteStore(temp_data_dir / "test.sqlite3")
    duckdb_store = DuckDBStore(temp_data_dir / "test.duckdb")
    collector = CollectorAgent([StaticSeedProvider()])
    return RunService(
        collector,
        OracleAgent(),
        SentinelAgent(),
        SageAgent(),
        ScribeAgent(),
        sqlite_store,
        duckdb_store,
    )


@pytest.fixture(autouse=True)
def configure_test_settings():
    from aletheia.core.config.settings import get_settings

    settings = get_settings()
    settings.tax_jurisdiction = "IN"

    from unittest.mock import AsyncMock, patch

    async def mock_generate(prompt, model=None, format=None):
        p_lower = prompt.lower()
        print(f"\n[TEST_MOCK_PROMPT] {p_lower}\n")
        if "you are a risk management agent" in p_lower or "re-evaluate your risk" in p_lower:
            return {
                "portfolio_var_95": -100.0,
                "concentration_risk": 0.1,
                "max_single_position_pct": 10.0,
                "market_regime": "balanced",
                "confidence": 0.8,
                "alerts": ["Reduced risk after debate"],
            }
        elif (
            "you are an expert financial analyst. you previously proposed" in p_lower
            or "re-evaluate your signal" in p_lower
        ):
            if "disagree" in p_lower:
                return {
                    "signal": "BUY",
                    "confidence": 0.95,
                    "rationale": "Insistent buy despite sentinel warning",
                }
            return {
                "signal": "HOLD",
                "confidence": 0.6,
                "rationale": "Oracle agreed to lower signal to HOLD after Sentinel warnings",
            }
        elif (
            "determine the signal" in p_lower
            or "you are an expert indian equity analyst" in p_lower
        ):
            return {"signal": "BUY", "confidence": 0.9, "rationale": "High volume support"}
        elif "wealth manager" in p_lower or "you are scribe" in p_lower:
            return {
                "executive_summary": "Overall market looks positive",
                "synthesized_recommendation": "BUY",
                "market_regime": "bullish",
                "stop_loss_suggested": True,
                "target_allocation_shift": "none",
            }
        elif "critic agent" in p_lower or "independent auditor" in p_lower:
            return {
                "passed": True,
                "score": 0.9,
                "notes": ["Audited and approved scribe recommendations."],
            }
        return {}

    with patch(
        "aletheia.core.llm.client.OllamaClient.generate_structured",
        new=AsyncMock(side_effect=mock_generate),
    ):
        yield
