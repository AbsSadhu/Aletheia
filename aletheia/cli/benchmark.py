"""
aletheia benchmark CLI — run and compare historical test scenarios.

Commands:
    aletheia benchmark run --scenario <name> --label <label>
    aletheia benchmark compare <label_a> <label_b>
    aletheia benchmark list
    aletheia benchmark scenarios
"""
from __future__ import annotations

import asyncio
import typer
from rich.console import Console
from rich.table import Table
from rich import box

app = typer.Typer(
    name="benchmark",
    help="Benchmark historical test scenarios and compare results.",
    no_args_is_help=True,
)
console = Console()


def _get_harness():
    from aletheia.extensions.backtest.benchmark import BenchmarkHarness
    return BenchmarkHarness()


@app.command(name="run")
def benchmark_run(
    scenario: str = typer.Option(
        ..., "--scenario", "-s", help="Scenario name (e.g. nse_starter_2024)"
    ),
    label: str = typer.Option(
        ..., "--label", "-l", help="Label for this run (e.g. before_memory_v1)"
    ),
):
    """Run a historical benchmark scenario and save results."""
    harness = _get_harness()
    try:
        cfg = harness.get_scenario(scenario)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold blue]Running benchmark: {scenario}[/bold blue]")
    console.print(f"  Symbols: {', '.join(cfg.symbols)}")
    console.print(f"  Period: {cfg.start_date} → {cfg.end_date}")
    console.print(f"  Label: [yellow]{label}[/yellow]")

    result = asyncio.run(harness.run_scenario(cfg, label))

    console.print(f"\n[bold green]✓ Benchmark complete in {result.runtime_seconds:.1f}s[/bold green]")

    # Print key metrics
    metrics = result.metrics
    if metrics:
        table = Table(title="Results", box=box.SIMPLE_HEAVY)
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        for k, v in metrics.items():
            if isinstance(v, float):
                table.add_row(k.replace("_", " ").title(), f"{v:.4f}")
            elif v is not None:
                table.add_row(k.replace("_", " ").title(), str(v))
        console.print(table)


@app.command(name="compare")
def benchmark_compare(
    label_a: str = typer.Argument(..., help="Label of first benchmark result"),
    label_b: str = typer.Argument(..., help="Label of second benchmark result"),
):
    """Compare two benchmark results — show metric diffs."""
    harness = _get_harness()
    try:
        comparison = harness.compare(label_a, label_b)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    table = Table(
        title=f"[bold]Benchmark Diff: {label_a} vs {label_b}[/bold]",
        box=box.ROUNDED,
        header_style="bold magenta",
    )
    table.add_column("Metric")
    table.add_column(label_a, justify="right")
    table.add_column(label_b, justify="right")
    table.add_column("Delta", justify="right")

    for metric, vals in comparison["diffs"].items():
        a_str = f"{vals['a']:.4f}" if isinstance(vals["a"], float) else str(vals["a"])
        b_str = f"{vals['b']:.4f}" if isinstance(vals["b"], float) else str(vals["b"])
        delta = vals["delta"]
        if delta is not None:
            d_str = (
                f"[green]+{delta:.4f}[/green]" if delta > 0 else
                f"[red]{delta:.4f}[/red]" if delta < 0 else "±0"
            )
        else:
            d_str = "—"
        table.add_row(metric.replace("_", " ").title(), a_str, b_str, d_str)

    console.print(table)


@app.command(name="list")
def benchmark_list():
    """List all saved benchmark results."""
    harness = _get_harness()
    results = harness.list_results()
    if not results:
        console.print("[yellow]No benchmark results saved yet.[/yellow]")
        return
    table = Table(title="Saved Benchmark Results", box=box.SIMPLE)
    table.add_column("Label")
    table.add_column("Scenario")
    table.add_column("Timestamp")
    for label in results:
        result = harness.load_result(label)
        scenario = result.scenario if result else "—"
        ts = str(result.timestamp) if result and getattr(result, "timestamp", None) else "—"
        table.add_row(label, scenario, ts)
    console.print(table)
    console.print(f"\n[dim]Total: {len(results)} result(s)[/dim]")


@app.command(name="scenarios")
def list_scenarios():
    """List all available built-in benchmark scenarios."""
    from aletheia.extensions.backtest.benchmark import BUILTIN_SCENARIOS
    table = Table(title="Built-in Benchmark Scenarios", box=box.SIMPLE)
    table.add_column("Name", style="bold white")
    table.add_column("Symbols")
    table.add_column("Period")
    table.add_column("Description")
    for name, cfg in BUILTIN_SCENARIOS.items():
        table.add_row(
            name,
            ", ".join(cfg.symbols),
            f"{cfg.start_date} → {cfg.end_date}",
            cfg.description,
        )
    console.print(table)
