import pytest
from unittest.mock import AsyncMock
from aletheia.core.models import (
    RunRequest,
    Portfolio,
    Holding,
    RunStatus,
)


@pytest.mark.asyncio
async def test_sentinel_partial_failure(run_service) -> None:
    # Ensure tax_jurisdiction is set so sage runs
    run_service.settings.tax_jurisdiction = "IN"

    # Arrange: mock sentinel to fail
    run_service.sentinel.assess = AsyncMock(side_effect=Exception("Sentinel API error"))

    # Run request
    portfolio = Portfolio(
        name="TestPortfolio",
        holdings=[
            Holding(
                symbol="RELIANCE",
                quantity=10,
                average_price=2500,
                asset_type="equity",
                exchange="NSE",
                tax_profile="equity",
            )
        ],
    )
    request = RunRequest(
        prompt="Analyze with failing sentinel",
        portfolio=portfolio,
    )

    # Act: create and run
    result = await run_service.create_run(request)

    # Assert
    assert result.summary.status == RunStatus.PARTIAL
    assert result.agent_statuses["sentinel"] == "failed"
    assert result.agent_statuses["collector"] == "completed"
    assert result.agent_statuses["oracle"] == "completed"
    assert result.agent_statuses["sage"] == "completed"
    assert result.agent_statuses["scribe"] == "completed"

    # Verify Scribe output has gap notes
    assert result.scribe_output is not None
    assert any("sentinel failed" in note.lower() for note in result.scribe_output.notes)


@pytest.mark.asyncio
async def test_sage_skipped_if_no_tax_jurisdiction(run_service) -> None:
    # Ensure tax_jurisdiction is None
    run_service.settings.tax_jurisdiction = None

    # Run request
    portfolio = Portfolio(
        name="TestPortfolio",
        holdings=[
            Holding(
                symbol="RELIANCE",
                quantity=10,
                average_price=2500,
                asset_type="equity",
                exchange="NSE",
                tax_profile="equity",
            )
        ],
    )
    request = RunRequest(
        prompt="Analyze without tax jurisdiction",
        portfolio=portfolio,
    )

    # Act: create and run
    result = await run_service.create_run(request)

    # Assert
    assert result.summary.status == RunStatus.COMPLETED
    assert result.agent_statuses["sage"] == "skipped"
    assert result.agent_statuses["collector"] == "completed"
    assert result.agent_statuses["oracle"] == "completed"
    assert result.agent_statuses["sentinel"] == "completed"
    assert result.agent_statuses["scribe"] == "completed"

    # Verify Scribe output has skip notes
    assert result.scribe_output is not None
    assert any("sage was skipped" in note.lower() for note in result.scribe_output.notes)


@pytest.mark.asyncio
async def test_sage_included_if_tax_jurisdiction_set(run_service) -> None:
    run_service.settings.tax_jurisdiction = "IN"

    portfolio = Portfolio(
        name="TestPortfolio",
        holdings=[
            Holding(
                symbol="RELIANCE",
                quantity=10,
                average_price=2500,
                asset_type="equity",
                exchange="NSE",
                tax_profile="equity",
            )
        ],
    )
    request = RunRequest(
        prompt="Analyze with tax jurisdiction",
        portfolio=portfolio,
    )

    result = await run_service.create_run(request)

    assert result.summary.status == RunStatus.COMPLETED
    assert result.agent_statuses["sage"] == "completed"
