"""
aletheia/core/reporting/exporter.py

Generates PDF and Excel exports of agent run results.

PDF:  Jinja2 → HTML → WeasyPrint (if available) or raw HTML fallback
Excel: openpyxl workbook with multiple sheets
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from aletheia import __version__

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def _build_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def _flatten_run_data(run: dict[str, Any]) -> dict[str, Any]:
    """Map a `RunResult.model_dump()` onto the flat fields the report and workbook use."""
    summary = run.get("summary") or {}
    scribe = run.get("scribe_output") or {}
    sentinel = run.get("sentinel_output") or {}

    last_price: dict[str, float | None] = {}
    for item in run.get("collector_output") or []:
        quotes = item.get("quotes") or []
        last_price[item.get("symbol", "")] = quotes[-1].get("close") if quotes else None

    symbols = [
        {
            "symbol": o.get("symbol"),
            "last_price": last_price.get(o.get("symbol", "")),
            "signal": o.get("signal"),
            "confidence": float(o.get("confidence") or 0),
            "stop_loss": o.get("stop_loss_price"),
            "target_price": o.get("target_price"),
            "rationale": "; ".join(o.get("rationale") or []),
        }
        for o in run.get("oracle_output") or []
    ]

    recommendations = [
        {
            "symbol": r.get("symbol"),
            "action": r.get("action") or "",
            "target_price": r.get("target_price"),
            "stop_loss": r.get("stop_loss"),
            "confidence": float(r.get("confidence") or 0),
            "reasoning": r.get("explanation") or "",
        }
        for r in scribe.get("recommendations") or []
    ]

    risk = None
    if sentinel:
        risk = {
            "var_95": sentinel.get("portfolio_var_95"),
            "concentration_risk": sentinel.get("concentration_risk"),
            "max_single_position_pct": sentinel.get("max_single_position_pct"),
            "market_regime": sentinel.get("market_regime"),
            "alerts": sentinel.get("alerts") or [],
            "brief": sentinel.get("natural_language_brief") or "",
        }

    tax_scenarios = []
    for item in run.get("sage_output") or []:
        scenario = item.get("scenario") or {}
        tax = scenario.get("tax_summary") or {}
        tax_scenarios.append(
            {
                "symbol": item.get("symbol"),
                "term": tax.get("term"),
                "tax_profile": tax.get("tax_profile"),
                "tax_rate": tax.get("tax_drag_pct"),
                "estimated_tax": tax.get("estimated_tax_amount"),
                "post_tax_profit": tax.get("post_tax_profit"),
                "post_tax_return_pct": scenario.get("projected_post_tax_return_pct"),
            }
        )

    actions = {r["action"] for r in recommendations if r["action"]}
    overall_verdict = actions.pop() if len(actions) == 1 else ("Mixed" if actions else "—")

    return {
        "run_id": summary.get("run_id") or "unknown",
        "status": str(summary.get("status") or "unknown").upper(),
        "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "prompt": summary.get("prompt") or "",
        "num_symbols": len(symbols),
        "symbols": symbols,
        "recommendations": recommendations,
        "executive_summary": scribe.get("executive_summary") or "",
        "notes": scribe.get("notes") or [],
        "disclaimer": scribe.get("sebi_disclaimer") or "",
        "risk": risk,
        "tax_scenarios": tax_scenarios,
        "confidence": float(scribe.get("overall_confidence") or 0),
        "overall_verdict": overall_verdict,
    }


def render_html(run: dict[str, Any]) -> str:
    """Render the report as an HTML string."""
    env = _build_jinja_env()
    template = env.get_template("report.html")
    ctx = _flatten_run_data(run)
    return template.render(app_version=__version__, **ctx)


def _reportlab_pdf(ctx: dict[str, Any]) -> bytes:
    """Pure-Python PDF, used where WeasyPrint's native GTK/Pango libraries are missing (Windows)."""
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    body, h2 = styles["BodyText"], styles["Heading2"]
    small = styles["BodyText"].clone("small", fontSize=8, leading=10)

    def para(text: Any, style: Any = body) -> Paragraph:
        return Paragraph(escape(str(text)), style)

    def money(v: Any) -> str:
        return "—" if v is None else f"{float(v):,.2f}"

    def table(header: list[str], rows: list[list[Any]]) -> Table:
        data = [header] + [[para(c, small) for c in r] for r in rows]
        t = Table(data, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E1B4B")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return t

    story: list[Any] = [
        para("ALETHEIA — Investment Intelligence Report", styles["Title"]),
        para(f"Run {ctx['run_id']} · {ctx['status']} · {ctx['generated_at']}", small),
        Spacer(1, 6 * mm),
        para(f"Confidence {ctx['confidence'] * 100:.0f}% · Verdict {ctx['overall_verdict']}"),
        para("Executive summary", h2),
        para(ctx["executive_summary"] or "No executive summary generated."),
    ]
    if ctx["recommendations"]:
        story += [
            para("Recommendations", h2),
            table(
                ["Symbol", "Action", "Target", "Stop loss", "Conf.", "Reasoning"],
                [
                    [
                        r["symbol"],
                        r["action"],
                        money(r["target_price"]),
                        money(r["stop_loss"]),
                        f"{r['confidence'] * 100:.0f}%",
                        r["reasoning"],
                    ]
                    for r in ctx["recommendations"]
                ],
            ),
        ]
    if ctx["symbols"]:
        story += [
            para("Oracle signals", h2),
            table(
                ["Symbol", "Last price", "Signal", "Conf.", "Rationale"],
                [
                    [
                        s["symbol"],
                        money(s["last_price"]),
                        s["signal"],
                        f"{s['confidence'] * 100:.0f}%",
                        s["rationale"],
                    ]
                    for s in ctx["symbols"]
                ],
            ),
        ]
    if ctx["risk"]:
        r = ctx["risk"]
        story += [
            para("Risk (Sentinel)", h2),
            para(
                f"VaR 95%: {money(r['var_95'])} · Concentration: {r['concentration_risk']} · "
                f"Largest position: {r['max_single_position_pct']}% · Regime: {r['market_regime']}"
            ),
        ]
        story += [para(f"• {a}", small) for a in r["alerts"]]
    if ctx["tax_scenarios"]:
        story += [
            para("Tax projections (Sage)", h2),
            table(
                ["Symbol", "Term", "Profile", "Tax rate %", "Est. tax", "Post-tax profit"],
                [
                    [
                        x["symbol"],
                        x["term"],
                        x["tax_profile"],
                        x["tax_rate"],
                        money(x["estimated_tax"]),
                        money(x["post_tax_profit"]),
                    ]
                    for x in ctx["tax_scenarios"]
                ],
            ),
        ]
    story += [
        Spacer(1, 6 * mm),
        para(
            ctx["disclaimer"]
            or "Informational only; not financial advice. Consult a SEBI-registered investment advisor.",
            small,
        ),
    ]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title="ALETHEIA report").build(story)
    return buf.getvalue()


def export_pdf(run: dict[str, Any]) -> tuple[bytes, bool]:
    """
    Export run result as a PDF binary.

    Tries WeasyPrint (best layout, needs native GTK libraries), then ReportLab (pure Python, works
    on Windows), and only then returns the raw HTML. Returns (data, is_pdf) so callers can label
    the response correctly instead of serving HTML mislabeled as `application/pdf`.
    """
    html_str = render_html(run)
    try:
        from weasyprint import HTML  # type: ignore[import-untyped]

        pdf_bytes: bytes = HTML(string=html_str).write_pdf()
        return pdf_bytes, True
    except Exception as exc:  # ImportError, or OSError when GTK/Pango/Cairo are not installed
        logger.warning("WeasyPrint unavailable (%s) — trying ReportLab", exc)
    try:
        return _reportlab_pdf(_flatten_run_data(run)), True
    except Exception as exc:
        logger.error("ReportLab PDF rendering failed: %s — returning HTML", exc)
        return html_str.encode("utf-8"), False


def export_excel(run: dict[str, Any]) -> bytes:
    """Export run result as an Excel (.xlsx) binary."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise RuntimeError("openpyxl is required for Excel export: pip install openpyxl") from exc

    ctx = _flatten_run_data(run)
    wb = openpyxl.Workbook()

    ws_summary = wb.active
    ws_summary.title = "Summary"  # type: ignore[attr-defined]

    PURPLE = "7C3AED"
    DARK = "1E1B4B"

    def header_row(ws, values: list[str], row: int) -> None:
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.font = Font(bold=True, color="FFFFFF", size=10)
            cell.fill = PatternFill("solid", fgColor=DARK)
            cell.alignment = Alignment(horizontal="center")

    def title_row(ws, text: str, row: int, ncols: int = 5) -> None:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
        cell = ws.cell(row=row, column=1, value=text)
        cell.font = Font(bold=True, color="FFFFFF", size=12)
        cell.fill = PatternFill("solid", fgColor=PURPLE)
        cell.alignment = Alignment(horizontal="left")

    title_row(ws_summary, "ALETHEIA — Investment Intelligence Report", 1)

    summary_data = [
        ("Run ID", ctx["run_id"]),
        ("Status", ctx["status"]),
        ("Generated At", ctx["generated_at"]),
        ("Request", ctx["prompt"]),
        ("Symbols analysed", str(ctx["num_symbols"])),
        ("Confidence", f"{ctx['confidence'] * 100:.0f}%"),
        ("Verdict", ctx["overall_verdict"]),
    ]
    ws_summary.append([])  # blank row
    for label, value in summary_data:
        row_idx = ws_summary.max_row + 1
        ws_summary.append([label, value])
        ws_summary.cell(row=row_idx, column=1).font = Font(bold=True, color=PURPLE)

    ws_summary.append([])
    ws_summary.append(["Executive Summary"])
    ws_summary.cell(row=ws_summary.max_row, column=1).font = Font(bold=True, size=11)
    ws_summary.append([ctx["executive_summary"] or "N/A"])
    if ctx["notes"]:
        ws_summary.append([])
        ws_summary.append(["Notes"])
        ws_summary.cell(row=ws_summary.max_row, column=1).font = Font(bold=True, size=11)
        for note in ctx["notes"]:
            ws_summary.append([note])
    ws_summary.column_dimensions["A"].width = 25
    ws_summary.column_dimensions["B"].width = 80

    ws_h = wb.create_sheet("Signals")
    title_row(ws_h, "Oracle Signals", 1, 7)
    ws_h.append([])
    header_row(
        ws_h,
        ["Symbol", "Last Price", "Signal", "Confidence", "Stop Loss", "Target", "Rationale"],
        3,
    )
    for sym in ctx["symbols"]:
        ws_h.append(
            [
                sym["symbol"],
                sym["last_price"],
                sym["signal"],
                f"{sym['confidence'] * 100:.0f}%",
                sym["stop_loss"],
                sym["target_price"],
                sym["rationale"],
            ]
        )
    for col in range(1, 7):
        ws_h.column_dimensions[get_column_letter(col)].width = 16
    ws_h.column_dimensions["G"].width = 70

    ws_r = wb.create_sheet("Recommendations")
    title_row(ws_r, "Agent Recommendations", 1, 6)
    ws_r.append([])
    header_row(
        ws_r, ["Symbol", "Action", "Target Price", "Stop Loss", "Confidence", "Reasoning"], 3
    )
    for rec in ctx["recommendations"]:
        ws_r.append(
            [
                rec["symbol"],
                rec["action"],
                rec["target_price"],
                rec["stop_loss"],
                f"{rec['confidence'] * 100:.0f}%",
                rec["reasoning"][:500],
            ]
        )
    ws_r.column_dimensions["F"].width = 60

    ws_k = wb.create_sheet("Risk")
    title_row(ws_k, "Sentinel Risk Brief", 1, 2)
    ws_k.append([])
    risk = ctx["risk"]
    if risk:
        for label, key in (
            ("VaR 95%", "var_95"),
            ("Concentration", "concentration_risk"),
            ("Largest position %", "max_single_position_pct"),
            ("Market regime", "market_regime"),
        ):
            ws_k.append([label, risk[key]])
        for alert in risk["alerts"]:
            ws_k.append(["Alert", alert])
    ws_k.column_dimensions["A"].width = 24
    ws_k.column_dimensions["B"].width = 80

    ws_t = wb.create_sheet("Tax Scenarios")
    title_row(ws_t, "Sage Tax Projections", 1, 7)
    ws_t.append([])
    header_row(
        ws_t,
        [
            "Symbol",
            "Term",
            "Profile",
            "Tax Rate (%)",
            "Est. Tax (₹)",
            "Post-tax Profit (₹)",
            "Post-tax Return (%)",
        ],
        3,
    )
    for item in ctx["tax_scenarios"]:
        ws_t.append(
            [
                item["symbol"],
                item["term"],
                item["tax_profile"],
                item["tax_rate"],
                item["estimated_tax"],
                item["post_tax_profit"],
                item["post_tax_return_pct"],
            ]
        )
    for col in range(1, 8):
        ws_t.column_dimensions[get_column_letter(col)].width = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
