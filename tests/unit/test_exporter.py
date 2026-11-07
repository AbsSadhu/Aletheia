"""export_pdf had no coverage, and the API layer mislabeled its HTML
fallback as application/pdf when weasyprint isn't available — this file
guards both the exporter's honest (data, is_pdf) contract and the router's
use of it."""

import types
from unittest.mock import MagicMock, patch

from aletheia.core.reporting.exporter import export_excel, export_pdf

_RUN = {
    "run_id": "abc123",
    "status": "completed",
    "request": {"portfolio": {"name": "Test Portfolio", "holdings": []}},
    "result_json": {
        "recommendations": [],
        "executive_summary": "All clear.",
        "final_verdict": "HOLD",
        "confidence": 0.8,
    },
}


def _reportlab_broken():
    # Patch the function, not sys.modules: once any test has imported reportlab its submodules stay cached.
    return patch(
        "aletheia.core.reporting.exporter._reportlab_pdf", side_effect=RuntimeError("no reportlab")
    )


def _fake_weasyprint_module(html_factory) -> types.ModuleType:
    """Inject a fake `weasyprint` module rather than patching the real one —
    the real package fails to import at all in this environment (its native
    GTK/Pango/Cairo libraries aren't installed), so `patch("weasyprint.HTML")`
    can't even reach the attribute to mock."""
    module = types.ModuleType("weasyprint")
    module.HTML = html_factory  # type: ignore[attr-defined]
    return module


def test_export_pdf_returns_true_when_weasyprint_succeeds() -> None:
    fake_html_instance = MagicMock()
    fake_html_instance.write_pdf.return_value = b"%PDF-1.4 fake"
    fake_module = _fake_weasyprint_module(lambda string: fake_html_instance)

    with patch.dict("sys.modules", {"weasyprint": fake_module}):
        data, is_pdf = export_pdf(_RUN)

    assert is_pdf is True
    assert data == b"%PDF-1.4 fake"


def test_export_pdf_falls_back_to_html_when_weasyprint_raises() -> None:
    def _raise(string):
        raise OSError("cannot load libgobject-2.0-0")

    fake_module = _fake_weasyprint_module(_raise)

    with patch.dict("sys.modules", {"weasyprint": fake_module}), _reportlab_broken():
        data, is_pdf = export_pdf(_RUN)

    assert is_pdf is False
    assert b"<html" in data.lower()


def test_export_pdf_falls_back_to_html_when_weasyprint_not_installed() -> None:
    with patch.dict("sys.modules", {"weasyprint": None}), _reportlab_broken():
        data, is_pdf = export_pdf(_RUN)
    assert is_pdf is False
    assert b"<html" in data.lower()


def test_export_excel_produces_a_workbook() -> None:
    data = export_excel(_RUN)
    assert data[:2] == b"PK"  # xlsx is a zip archive


# The shape RunResult.model_dump() really produces (trimmed from a live run). The exporter used to
# read `result_json` / `request.portfolio`, which no run has, so every export came out empty.
_REAL_RUN = {
    "summary": {
        "run_id": "2851f524-9f3b-47e5",
        "status": "completed",
        "prompt": "Analyze portfolio demo",
    },
    "collector_output": [{"symbol": "ABC", "quotes": [{"close": 581.95, "currency": "INR"}]}],
    "oracle_output": [
        {
            "symbol": "ABC",
            "signal": "HOLD",
            "confidence": 0.5,
            "stop_loss_price": 528.43,
            "target_price": None,
            "rationale": ["Unrealised P&L vs average cost: -2.84%."],
        }
    ],
    "sentinel_output": {
        "portfolio_var_95": -6039.27,
        "concentration_risk": 1.0,
        "max_single_position_pct": 100.0,
        "market_regime": "bullish",
        "alerts": ["Single-position exposure is above 40%."],
    },
    "sage_output": [
        {
            "symbol": "ABC",
            "scenario": {
                "projected_post_tax_return_pct": 0.93,
                "tax_summary": {
                    "tax_profile": "equity",
                    "tax_drag_pct": 20.0,
                    "estimated_tax_amount": 417.48,
                    "post_tax_profit": 1669.92,
                    "term": "short",
                },
            },
        }
    ],
    "scribe_output": {
        "executive_summary": "Multi-agent review completed.",
        "overall_confidence": 0.53,
        "recommendations": [
            {
                "symbol": "ABC",
                "action": "HOLD",
                "confidence": 0.5,
                "explanation": "HOLD view.",
                "stop_loss": 528.43,
                "target_price": None,
            }
        ],
        "notes": ["note"],
        "sebi_disclaimer": "Informational only.",
    },
}


def test_flatten_reads_the_real_run_shape() -> None:
    from aletheia.core.reporting.exporter import _flatten_run_data

    ctx = _flatten_run_data(_REAL_RUN)
    assert ctx["run_id"] == "2851f524-9f3b-47e5"
    assert ctx["status"] == "COMPLETED"
    assert ctx["executive_summary"] == "Multi-agent review completed."
    assert ctx["confidence"] == 0.53
    assert ctx["recommendations"][0]["symbol"] == "ABC"
    assert ctx["recommendations"][0]["reasoning"] == "HOLD view."
    assert ctx["symbols"][0]["last_price"] == 581.95
    assert ctx["risk"]["var_95"] == -6039.27
    assert ctx["tax_scenarios"][0]["symbol"] == "ABC"
    assert ctx["tax_scenarios"][0]["estimated_tax"] == 417.48


def test_excel_for_a_real_run_has_the_run_data() -> None:
    import io

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(export_excel(_REAL_RUN)))
    cells = {
        str(c.value) for ws in wb for row in ws.iter_rows() for c in row if c.value is not None
    }
    assert {
        "2851f524-9f3b-47e5",
        "COMPLETED",
        "ABC",
        "HOLD",
        "Multi-agent review completed.",
    } <= cells
    assert "UNKNOWN" not in cells and "unknown" not in cells


def test_pdf_for_a_real_run_is_a_real_pdf_without_native_libraries() -> None:
    with patch.dict("sys.modules", {"weasyprint": None}):
        data, is_pdf = export_pdf(_REAL_RUN)
    assert is_pdf is True
    assert data.startswith(b"%PDF")
