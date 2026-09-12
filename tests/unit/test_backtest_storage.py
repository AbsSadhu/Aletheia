from aletheia.extensions.backtest.storage import BacktestResultStore
from aletheia.extensions.backtest.models import BacktestResult


def _result(run_id: str, sharpe: float) -> BacktestResult:
    return BacktestResult(
        run_id=run_id,
        strategy_name="sma_crossover",
        start_date="2024-01-01",
        end_date="2024-06-01",
        initial_capital=100_000.0,
        final_capital=110_000.0,
        total_return=0.10,
        metrics={"sharpe_ratio": sharpe, "max_drawdown": -0.05, "win_rate": 0.6, "profit_factor": 1.5, "total_trades": 4},
        orders=[],
        equity_curve=[],
    )


def test_save_and_get_roundtrip(tmp_path) -> None:
    store = BacktestResultStore(tmp_path / "backtests.db")
    result = _result("run-abc", sharpe=1.42)
    store.save(result)

    fetched = store.get("run-abc")
    assert fetched is not None
    assert fetched.run_id == "run-abc"
    assert fetched.metrics["sharpe_ratio"] == 1.42


def test_get_missing_run_id_returns_none(tmp_path) -> None:
    store = BacktestResultStore(tmp_path / "backtests.db")
    assert store.get("does-not-exist") is None


def test_save_overwrites_existing_run_id(tmp_path) -> None:
    store = BacktestResultStore(tmp_path / "backtests.db")
    store.save(_result("run-abc", sharpe=1.0))
    store.save(_result("run-abc", sharpe=2.0))

    fetched = store.get("run-abc")
    assert fetched.metrics["sharpe_ratio"] == 2.0
