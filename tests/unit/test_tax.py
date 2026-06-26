from aletheia.extensions.backtest.tax import build_tax_summary, estimate_tax_drag
from aletheia.core.models import TaxProfile


def test_tax_drag_for_fno() -> None:
    assert estimate_tax_drag(TaxProfile.FNO) == 0.175


def test_build_tax_summary_reduces_post_tax_profit() -> None:
    summary = build_tax_summary(TaxProfile.EQUITY, 100000)
    assert summary.estimated_tax_amount == 15000.0
    assert summary.post_tax_profit == 85000.0

