import pytest
from unittest.mock import AsyncMock
from datetime import UTC, datetime
from aletheia.core.context.macro_injector import MacroContext, MacroContextInjector


def test_macro_context_prompt_formatting():
    # Test formatting with all fields populated
    ctx = MacroContext(
        rbi_repo_rate_pct=6.5,
        usd_inr=83.45,
        nifty_50_momentum_pct=4.2,
        crude_oil_usd=82.5,
        fetched_at=datetime.now(UTC),
        notes=["USD/INR checked"],
    )
    prompt = ctx.as_prompt_text()
    assert "RBI repo rate: 6.50%" in prompt
    assert "USD/INR: ₹83.45" in prompt
    assert "Brent crude: $82.5/bbl" in prompt
    assert "NIFTY 50 50-day momentum: +4.2% (uptrend)" in prompt
    assert "USD/INR checked" in prompt

    # Test formatting with missing fields
    ctx_empty = MacroContext(
        rbi_repo_rate_pct=None,
        usd_inr=None,
        nifty_50_momentum_pct=None,
        crude_oil_usd=None,
    )
    assert (
        ctx_empty.as_prompt_text()
        == "Macro data unavailable — agents operating without macro context."
    )


@pytest.mark.asyncio
async def test_macro_injector_fetch_fallback():
    injector = MacroContextInjector(duckdb_path=None)

    # Mock usd_inr and crude_oil fetchers to raise errors or return specific values
    injector._fetch_usd_inr = AsyncMock(return_value=83.12)
    injector._fetch_crude_oil = AsyncMock(return_value=79.5)
    injector._fetch_nifty_momentum = AsyncMock(return_value=None)  # no DB

    ctx = await injector.get()
    assert ctx.rbi_repo_rate_pct == 6.50  # fallback RBI rate
    assert ctx.usd_inr == 83.12
    assert ctx.crude_oil_usd == 79.5
    assert ctx.nifty_50_momentum_pct is None
