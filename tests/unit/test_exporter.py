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

    with patch.dict("sys.modules", {"weasyprint": fake_module}):
        data, is_pdf = export_pdf(_RUN)

    assert is_pdf is False
    assert b"<html" in data.lower()


def test_export_pdf_falls_back_to_html_when_weasyprint_not_installed() -> None:
    with patch.dict("sys.modules", {"weasyprint": None}):
        data, is_pdf = export_pdf(_RUN)
    assert is_pdf is False
    assert b"<html" in data.lower()


def test_export_excel_produces_a_workbook() -> None:
    data = export_excel(_RUN)
    assert data[:2] == b"PK"  # xlsx is a zip archive
