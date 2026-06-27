import pytest
from pydantic import ValidationError
from aletheia.core.models import (
    CollectorOutput,
    OracleOutput,
    SageOutput,
    SageScenario,
    TaxSummary,
    TaxProfile,
    Holding,
    Portfolio,
    AssetType,
    MarketQuote,
    RunRequest,
    AnalystContract,
    RiskConstraintContract,
    SynthesisContract,
)
from aletheia.core.services import RunService
from aletheia.core.config.settings import get_settings


def test_pydantic_org_chart_role_contracts():
    # 1. Analyst contract violation: collector/oracle/sentinel trying to output final decisions
    with pytest.raises(ValidationError) as excinfo:
        # CollectorOutput cannot have recommendations
        CollectorOutput(
            symbol="INFY",
            provider_used="yfinance",
            quotes=[],
            recommendations=[
                {"symbol": "INFY", "action": "BUY", "confidence": 1.0, "explanation": "forced"}
            ],
        )
    assert "Analyst contract violation" in str(excinfo.value)

    with pytest.raises(ValidationError) as excinfo:
        # OracleOutput cannot have executive_summary
        OracleOutput(
            symbol="INFY", signal="BUY", confidence=0.9, executive_summary="Highly bullish outlook"
        )
    assert "Analyst contract violation" in str(excinfo.value)

    # 2. Risk constraint contract violation: Sage outputting collector quotes or scribe summaries
    with pytest.raises(ValidationError) as excinfo:
        SageOutput(
            symbol="INFY",
            scenario=SageScenario(
                scenario_name="base",
                projected_return_pct=5.0,
                projected_post_tax_return_pct=4.0,
                projected_sharpe=1.2,
                tax_summary=TaxSummary(
                    tax_profile=TaxProfile.EQUITY,
                    pre_tax_profit=100.0,
                    tax_drag_pct=10.0,
                    estimated_tax_amount=10.0,
                    post_tax_profit=90.0,
                ),
            ),
            confidence=0.8,
            executive_summary="Synthesis",
        )
    # 3. Subclass contract violation: defining classes with forbidden fields raises TypeError
    with pytest.raises(TypeError) as excinfo:

        class BadAnalyst(AnalystContract):
            recommendations: list = []

    assert "Analyst contract violation" in str(excinfo.value)

    with pytest.raises(TypeError) as excinfo:

        class BadRisk(RiskConstraintContract):
            executive_summary: str = ""

    assert "RiskConstraint contract violation" in str(excinfo.value)

    with pytest.raises(TypeError) as excinfo:

        class BadSynthesis(SynthesisContract):
            quotes: list = []

    assert "Synthesis contract violation" in str(excinfo.value)


@pytest.mark.asyncio
async def test_oracle_sentinel_debate_node_convergence(run_service: RunService):
    # Setup portfolio and quotes to trigger disagreement: Oracle BUY, Sentinel Alerts present
    portfolio = Portfolio(
        name="TestPortfolio",
        holdings=[
            Holding(
                symbol="RELIANCE",
                quantity=10,
                average_price=2500,
                asset_type=AssetType.EQUITY,
                exchange="NSE",
                tax_profile=TaxProfile.EQUITY,
                sector="Energy",
            )
        ],
    )

    quote = MarketQuote(
        symbol="RELIANCE",
        exchange="NSE",
        close=2600.0,
        open=2550.0,
        provider="static",
    )
    run_service.duckdb_store.persist_quotes([quote])

    # Run execution with full agent workflow
    req = RunRequest(
        prompt="Test debate",
        portfolio=portfolio,
        selected_agents=["collector", "oracle", "sentinel", "sage", "scribe"],
    )

    # We will trigger the run. By default in conftest mock_generate, oracle debate returns HOLD, which is convergence!
    res = await run_service.create_run(req)

    assert res.summary.status == "completed"
    # Oracle output signal should have converged to HOLD
    assert len(res.oracle_output) > 0
    assert res.oracle_output[0].signal == "HOLD"
    # No debate disagreements should be registered since consensus was achieved
    # pyrefly: ignore [missing-attribute]
    assert len(res.scribe_output.notes) > 0
    # pyrefly: ignore [not-iterable]
    assert not any("[Debate Disagreement]" in note for note in res.scribe_output.notes)


@pytest.mark.asyncio
async def test_oracle_sentinel_debate_node_unresolved(run_service: RunService):
    # Setup portfolio with "DISAGREE" symbol to trigger mock disagreement flow in conftest
    portfolio = Portfolio(
        name="TestPortfolio",
        holdings=[
            Holding(
                symbol="DISAGREE",
                quantity=10,
                average_price=2500,
                asset_type=AssetType.EQUITY,
                exchange="NSE",
                tax_profile=TaxProfile.EQUITY,
                sector="Energy",
            )
        ],
    )

    quote = MarketQuote(
        symbol="DISAGREE",
        exchange="NSE",
        close=2600.0,
        open=2550.0,
        provider="static",
    )
    run_service.duckdb_store.persist_quotes([quote])

    req = RunRequest(
        prompt="Test debate unresolved",
        portfolio=portfolio,
        selected_agents=["collector", "oracle", "sentinel", "sage", "scribe"],
    )

    settings = get_settings()
    original_max_pos = settings.pm_max_position_size_pct
    original_max_sector = settings.pm_max_sector_concentration_pct
    original_max_var = settings.pm_max_portfolio_var_pct

    try:
        settings.pm_max_position_size_pct = 100.0
        settings.pm_max_sector_concentration_pct = 100.0
        settings.pm_max_portfolio_var_pct = 100.0

        res = await run_service.create_run(req)

        assert res.summary.status == "completed"
        # Oracle output signal should remain BUY (unresolved)
        assert len(res.oracle_output) > 0
        assert res.oracle_output[0].signal == "BUY"

        # Debate disagreement must be registered and surfaced by Scribe
        # pyrefly: ignore [missing-attribute]
        assert any("[Debate Disagreement]" in note for note in res.scribe_output.notes)
    finally:
        settings.pm_max_position_size_pct = original_max_pos
        settings.pm_max_sector_concentration_pct = original_max_sector
        settings.pm_max_portfolio_var_pct = original_max_var


@pytest.mark.asyncio
async def test_portfolio_manager_overrides(run_service: RunService):
    # Setup settings constraints to trigger PM overrides
    settings = get_settings()
    original_max_pos = settings.pm_max_position_size_pct
    original_max_sector = settings.pm_max_sector_concentration_pct
    original_max_var = settings.pm_max_portfolio_var_pct

    try:
        # Set very strict PM limits
        settings.pm_max_position_size_pct = 5.0
        settings.pm_max_sector_concentration_pct = 5.0
        settings.pm_max_portfolio_var_pct = 1.0

        portfolio = Portfolio(
            name="PMTestPortfolio",
            holdings=[
                Holding(
                    symbol="DISAGREE",
                    quantity=100,
                    average_price=3000,
                    asset_type=AssetType.EQUITY,
                    exchange="NSE",
                    tax_profile=TaxProfile.EQUITY,
                    sector="Technology",
                )
            ],
        )

        quote = MarketQuote(
            symbol="DISAGREE",
            exchange="NSE",
            close=3200.0,
            open=3100.0,
            provider="static",
        )
        run_service.duckdb_store.persist_quotes([quote])

        req = RunRequest(
            prompt="Test PM Override disagree",
            portfolio=portfolio,
            selected_agents=["collector", "oracle", "sentinel", "sage", "scribe"],
        )

        res = await run_service.create_run(req)

        assert res.summary.status == "completed"
        # The proposed BUY signal should be overridden to HOLD by PM due to position size (> 5%)
        assert len(res.oracle_output) > 0
        assert res.oracle_output[0].signal == "HOLD"

        # Override note must be present in Scribe notes
        # pyrefly: ignore [missing-attribute]
        pm_notes = [note for note in res.scribe_output.notes if "[PM Override]" in note]
        assert len(pm_notes) > 0
        assert any(
            "position size" in note.lower() or "var" in note.lower() or "sector" in note.lower()
            for note in pm_notes
        )

    finally:
        # Restore settings
        settings.pm_max_position_size_pct = original_max_pos
        settings.pm_max_sector_concentration_pct = original_max_sector
        settings.pm_max_portfolio_var_pct = original_max_var
