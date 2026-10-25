import datetime as dt

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aletheia.core.signals.accuracy import MIN_SAMPLES, summarize


def _rec(signal: str, conf: float, ret: float, symbol: str = "INFY") -> dict:
    win = (ret > 0) if signal == "BUY" else (ret < 0) if signal == "REDUCE" else abs(ret) <= 2
    return {
        "symbol": symbol,
        "predicted_signal": signal,
        "predicted_confidence": conf,
        "actual_return_7d": ret,
        "actual_return_30d": None,
        "brier_score": round((conf - (1.0 if win else 0.0)) ** 2, 4),
        "recorded_at": dt.datetime.now(dt.UTC).isoformat(),
    }


def test_empty_state_is_honest() -> None:
    out = summarize([], pending=3)
    assert out["resolved"] == 0 and out["pending"] == 3 and not out["enough_data"]
    assert out["overall"] is None and "No resolved" in out["verdict"]


def test_small_sample_is_flagged_not_judged() -> None:
    out = summarize([_rec("BUY", 0.8, 3.0) for _ in range(5)])
    assert out["resolved"] == 5 and not out["enough_data"]
    assert "need" in out["verdict"].lower()


def test_hit_rates_by_signal_and_symbol() -> None:
    recs = [_rec("BUY", 0.7, 2.0), _rec("BUY", 0.7, -1.0), _rec("REDUCE", 0.6, -3.0, "TCS")]
    out = summarize(recs)
    assert out["by_signal"]["BUY"]["hit_rate_pct"] == 50.0
    assert out["by_signal"]["REDUCE"]["hit_rate_pct"] == 100.0
    assert {s["symbol"] for s in out["by_symbol"]} == {"INFY", "TCS"}


def test_calibration_buckets_compare_claimed_to_actual() -> None:
    recs = [_rec("BUY", 0.75, 1.0)] * 3 + [_rec("BUY", 0.75, -1.0)]
    (bucket,) = summarize(recs)["calibration"]
    assert bucket["range"] == "0.7-0.8" and bucket["n"] == 4
    assert bucket["claimed_pct"] == 75.0 and bucket["actual_hit_rate_pct"] == 75.0


def test_verdict_against_coin_flip_with_enough_data() -> None:
    good = summarize([_rec("BUY", 0.8, 2.0) for _ in range(MIN_SAMPLES)])
    assert good["enough_data"] and "better than a coin flip" in good["verdict"]
    bad = summarize([_rec("BUY", 0.9, -2.0) for _ in range(MIN_SAMPLES)])
    assert "Not better than a coin flip" in bad["verdict"]


def test_endpoint_reads_store(monkeypatch) -> None:
    from aletheia.core.api.routers import signals

    class _Store:
        def get_resolved_calibration(self, agent):
            return [_rec("BUY", 0.7, 1.0)]

        def count_unresolved_calibration(self, agent):
            return 2

    monkeypatch.setattr(
        signals, "get_run_service", lambda: type("S", (), {"sqlite_store": _Store()})()
    )
    app = FastAPI()
    app.include_router(signals.router)
    body = TestClient(app).get("/api/v1/signals/accuracy").json()
    assert body["resolved"] == 1 and body["pending"] == 2


def test_latest_backtest_endpoint_empty_then_present(monkeypatch, tmp_path) -> None:
    from aletheia.core.api.routers import signals

    monkeypatch.setattr(signals, "_latest_path", lambda: tmp_path / "latest.json")
    app = FastAPI()
    app.include_router(signals.router)
    c = TestClient(app)
    assert c.get("/api/v1/backtest/signal/latest").json() == {"result": None}
    (tmp_path / "latest.json").write_text('{"verdict": {"status": "FAIL"}}')
    assert c.get("/api/v1/backtest/signal/latest").json()["result"]["verdict"]["status"] == "FAIL"
