"""
aletheia run compare <run_a_id> <run_b_id>

Side-by-side comparison of two analysis runs, including:
  - Oracle recommendation + confidence
  - Sentinel risk flags
  - Sage adjustments
  - Portfolio Manager decision
  - Scribe narrative summary
  - Final paper trade outcome (if settled)
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table
from rich.columns import Columns
from rich.panel import Panel
from rich import box

app = typer.Typer(
    name="compare",
    help="Compare two analysis runs side-by-side.",
    no_args_is_help=True,
)
console = Console()


def _get_service():
    from aletheia.core.api.dependencies import get_run_service

    return get_run_service()


def _build_run_panel(run_id: str, service, label: str) -> Panel:
    result = service.get_run(run_id)
    if result is None:
        return Panel(f"[red]Run {run_id[:12]}… not found[/red]", title=label)

    lines = []

    # Oracle
    oracle = getattr(result, "oracle_output", None)
    if oracle:
        lines.append("[bold cyan]Oracle[/bold cyan]")
        signal = getattr(oracle, "signal", "—")
        conf = getattr(oracle, "confidence", None)
        conf_str = f"{conf:.1%}" if conf is not None else "—"
        lines.append(f"  Signal: [bold]{signal}[/bold]  Confidence: {conf_str}")
        reasoning = getattr(oracle, "reasoning", None) or ""
        if reasoning:
            lines.append(f"  {reasoning[:200]}")

    # Sentinel
    sentinel = getattr(result, "sentinel_output", None)
    if sentinel:
        lines.append("\n[bold yellow]Sentinel[/bold yellow]")
        risk = getattr(sentinel, "risk_score", None)
        regime = getattr(sentinel, "regime", None)
        lines.append(f"  Risk score: {risk or '—'}  Regime: {regime or '—'}")
        flags = getattr(sentinel, "flagged_risks", []) or []
        for f in flags[:3]:
            lines.append(f"  ⚠ {f}")

    # Sage
    sage = getattr(result, "sage_output", None)
    if sage:
        lines.append("\n[bold blue]Sage[/bold blue]")
        tax_drag = getattr(sage, "tax_drag", None)
        lines.append(f"  Tax drag: {tax_drag or '—'}")

    # Scribe
    scribe = getattr(result, "scribe_output", None)
    if scribe:
        lines.append("\n[bold green]Scribe[/bold green]")
        agreement = getattr(scribe, "agreement_level", None)
        overall_conf = getattr(scribe, "overall_confidence", None)
        lines.append(
            f"  Agreement: {agreement or '—'}  Overall conf: {f'{overall_conf:.1%}' if overall_conf else '—'}"
        )
        recs = getattr(scribe, "recommendations", []) or []
        for rec in recs[:3]:
            action = getattr(rec, "action", "")
            sym = getattr(rec, "symbol", "")
            rat = getattr(rec, "rationale", "")
            lines.append(f"  → {action} {sym}: {rat[:80]}")

    # Status
    summary = getattr(result, "summary", None)
    if summary:
        lines.append(f"\n[dim]Status: {getattr(summary, 'status', '—')}[/dim]")

    return Panel(
        "\n".join(lines) if lines else "[dim]No data[/dim]",
        title=f"[bold]{label}[/bold] [dim]{run_id[:12]}…[/dim]",
        border_style="cyan" if "A" in label else "magenta",
        box=box.ROUNDED,
    )


@app.command(name="runs")
def compare_runs(
    run_a: str = typer.Argument(..., help="First run ID"),
    run_b: str = typer.Argument(..., help="Second run ID"),
):
    """Compare two analysis runs side-by-side."""
    service = _get_service()
    panel_a = _build_run_panel(run_a, service, "Run A")
    panel_b = _build_run_panel(run_b, service, "Run B")

    console.print(Columns([panel_a, panel_b], equal=True, expand=True))

    # Diff table for key metrics
    result_a = service.get_run(run_a)
    result_b = service.get_run(run_b)

    if result_a and result_b:
        table = Table(
            title="[bold]Key Metrics Diff[/bold]",
            box=box.SIMPLE_HEAVY,
            header_style="bold dim",
        )
        table.add_column("Metric")
        table.add_column("Run A", justify="center")
        table.add_column("Run B", justify="center")
        table.add_column("Delta", justify="center")

        def _conf(r):
            s = getattr(r, "scribe_output", None)
            return getattr(s, "overall_confidence", None) if s else None

        def _risk(r):
            s = getattr(r, "sentinel_output", None)
            return getattr(s, "risk_score", None) if s else None

        def _oracle_sig(r):
            o = getattr(r, "oracle_output", None)
            return getattr(o, "signal", "—") if o else "—"

        ca, cb = _conf(result_a), _conf(result_b)
        ra, rb = _risk(result_a), _risk(result_b)

        table.add_row(
            "Oracle Signal",
            _oracle_sig(result_a),
            _oracle_sig(result_b),
            "—",
        )
        table.add_row(
            "Overall Confidence",
            f"{ca:.1%}" if ca is not None else "—",
            f"{cb:.1%}" if cb is not None else "—",
            (
                f"[green]+{(cb - ca):.1%}[/green]"
                if cb and ca and cb > ca
                else f"[red]{(cb - ca):.1%}[/red]"
                if cb and ca and cb < ca
                else "—"
            ),
        )
        table.add_row(
            "Risk Score",
            str(ra) if ra is not None else "—",
            str(rb) if rb is not None else "—",
            "—",
        )

        console.print(table)
