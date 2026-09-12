from aletheia.extensions.backtest.tax import build_tax_summary, estimate_tax_drag
from aletheia.core.models import TaxProfile


def test_tax_drag_for_fno_is_flat_and_slab_dependent() -> None:
    assert estimate_tax_drag(TaxProfile.FNO) == 0.30


def test_tax_drag_for_crypto_is_flat_30_pct() -> None:
    assert estimate_tax_drag(TaxProfile.CRYPTO) == 0.30


def test_equity_short_term_holding_uses_short_term_rate() -> None:
    summary = build_tax_summary(TaxProfile.EQUITY, 100000, holding_days=100)
    assert summary.term == "short"
    assert summary.tax_drag_pct == 20.0
    assert summary.estimated_tax_amount == 20000.0
    assert summary.post_tax_profit == 80000.0


def test_equity_long_term_holding_uses_long_term_rate() -> None:
    summary = build_tax_summary(TaxProfile.EQUITY, 100000, holding_days=400)
    assert summary.term == "long"
    assert summary.tax_drag_pct == 12.5
    assert summary.estimated_tax_amount == 12500.0
    assert summary.post_tax_profit == 87500.0


def test_equity_at_exact_threshold_is_long_term() -> None:
    summary = build_tax_summary(TaxProfile.EQUITY, 100000, holding_days=365)
    assert summary.term == "long"


def test_unknown_holding_period_conservatively_assumes_short_term() -> None:
    summary = build_tax_summary(TaxProfile.EQUITY, 100000, holding_days=None)
    assert summary.term == "short"
    assert any("acquisition date" in note for note in summary.notes)


def test_crypto_and_fno_have_no_term_distinction() -> None:
    short_holding = build_tax_summary(TaxProfile.CRYPTO, 100000, holding_days=10)
    long_holding = build_tax_summary(TaxProfile.CRYPTO, 100000, holding_days=1000)
    assert short_holding.term == long_holding.term == "flat"
    assert short_holding.tax_drag_pct == long_holding.tax_drag_pct == 30.0


def test_rates_are_flagged_unverified() -> None:
    summary = build_tax_summary(TaxProfile.EQUITY, 100000, holding_days=400)
    assert summary.rates_verified is False
    assert any("unverified" in note.lower() for note in summary.notes)
