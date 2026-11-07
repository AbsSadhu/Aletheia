"""Trade journal: parsing Indian broker exports, round-trip pairing, XIRR, and the behaviour checks."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from aletheia.core.journal.analysis import (
    analyze,
    anchoring,
    chasing_momentum,
    disposition_effect,
    pair_trades,
    xirr,
)
from aletheia.core.journal.parsers import JournalFormatError, load_table, parse
from aletheia.core.journal.sample import sample_tradebook_csv

ZERODHA = """symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,trade_id,order_id,order_execution_time
RELIANCE,INE002A01018,2026-05-04,NSE,EQ,EQ,buy,false,10,1250.50,1,11,2026-05-04T09:41:00
RELIANCE,INE002A01018,2026-05-11,NSE,EQ,EQ,sell,false,10,1300.00,2,12,2026-05-11T14:02:00
"""


def _df(rows: list[tuple]) -> pd.DataFrame:
    cols = ["datetime", "symbol", "side", "quantity", "price", "fee"]
    out = pd.DataFrame(rows, columns=cols)
    out["datetime"] = pd.to_datetime(out["datetime"])
    out["name"], out["amount"], out["segment"] = "", out["quantity"] * out["price"], ""
    return out.sort_values("datetime").reset_index(drop=True)


# ------------------------------------------------------------------ parsing
def test_zerodha_tradebook_is_recognised_and_parsed():
    fmt, df = parse(load_table(ZERODHA.encode(), "tradebook.csv"))
    assert fmt == "zerodha"
    assert list(df["side"]) == ["buy", "sell"] and df["symbol"].iloc[0] == "RELIANCE"
    assert df["datetime"].iloc[0] == pd.Timestamp("2026-05-04 09:41:00")


def test_generic_headers_dayfirst_dates_and_rupee_strings():
    csv = 'Scrip Name,Buy/Sell,Qty,Rate,Trade Date,Brokerage\nINFY-EQ,B,5,"₹1,500.00",03/05/2026,20\nINFY-EQ,S,5,1550,10/05/2026,20\n'
    fmt, df = parse(load_table(csv.encode(), "x.csv"))
    assert fmt == "generic"
    assert df["symbol"].tolist() == ["INFY", "INFY"] and df["price"].tolist() == [1500.0, 1550.0]
    assert df["datetime"].iloc[0] == pd.Timestamp("2026-05-03")  # 3 May, not 5 March


def test_excel_files_are_read():
    buf = io.BytesIO()
    pd.read_csv(io.StringIO(ZERODHA)).to_excel(buf, index=False)
    fmt, df = parse(load_table(buf.getvalue(), "tradebook.xlsx"))
    assert fmt == "zerodha" and len(df) == 2


def test_unusable_files_fail_with_a_reason():
    with pytest.raises(JournalFormatError, match="quantity"):
        parse(load_table(b"symbol,side,price,date\nA,buy,1,2026-01-01\n", "x.csv"))
    with pytest.raises(JournalFormatError, match="csv or .xlsx"):
        load_table(b"x", "journal.pdf")
    with pytest.raises(JournalFormatError, match="No usable trades"):
        parse(load_table(b"symbol,side,qty,price,date\nA,hold,0,0,2026-01-01\n", "x.csv"))


# ------------------------------------------------------------------ pairing
def test_long_round_trip_pnl_includes_fees():
    trips, opens = pair_trades(
        _df(
            [
                ("2026-05-04 10:00", "A", "buy", 10, 100.0, 5.0),
                ("2026-05-08 10:00", "A", "sell", 10, 110.0, 5.0),
            ]
        )
    )
    assert opens == [] and len(trips) == 1
    assert (
        trips[0]["pnl"] == 90.0
        and trips[0]["direction"] == "long"
        and trips[0]["category"] == "short_term"
    )


def test_sell_first_is_a_short_and_profits_when_price_falls():
    trips, _ = pair_trades(
        _df(
            [
                ("2026-05-04 10:00", "A", "sell", 10, 100.0, 0),
                ("2026-05-04 14:00", "A", "buy", 10, 90.0, 0),
            ]
        )
    )
    assert (
        trips[0]["direction"] == "short"
        and trips[0]["pnl"] == 100.0
        and trips[0]["category"] == "intraday"
    )


def test_partial_fills_pair_first_in_first_out_and_leave_the_rest_open():
    trips, opens = pair_trades(
        _df(
            [
                ("2026-05-01 10:00", "A", "buy", 10, 100.0, 0),
                ("2026-05-02 10:00", "A", "buy", 10, 120.0, 0),
                ("2026-05-05 10:00", "A", "sell", 15, 130.0, 0),
            ]
        )
    )
    assert [(t["qty"], t["entry_price"]) for t in trips] == [(10, 100.0), (5, 120.0)]
    assert opens == [
        {
            "symbol": "A",
            "direction": "long",
            "quantity": 5.0,
            "average_price": 120.0,
            "since": "2026-05-02T10:00:00",
        }
    ]


def test_holding_period_classes():
    trips, _ = pair_trades(
        _df(
            [
                ("2025-01-01 10:00", "A", "buy", 1, 100.0, 0),
                ("2026-01-02 10:00", "A", "sell", 1, 120.0, 0),
            ]
        )
    )
    assert trips[0]["category"] == "long_term"  # more than 365 days
    trips, _ = pair_trades(
        _df(
            [
                ("2025-01-01 10:00", "A", "buy", 1, 100.0, 0),
                ("2026-01-01 10:00", "A", "sell", 1, 120.0, 0),
            ]
        )
    )
    assert trips[0]["category"] == "short_term"  # exactly 365 days is not long-term


# ------------------------------------------------------------------ XIRR
def test_xirr_matches_a_known_rate():
    rate = xirr([(pd.Timestamp("2025-01-01"), -100.0), (pd.Timestamp("2026-01-01"), 110.0)])
    assert rate == pytest.approx(0.10, abs=1e-3)


def test_xirr_is_undefined_without_both_signs_or_over_a_few_days():
    assert xirr([(pd.Timestamp("2025-01-01"), -100.0)]) is None
    assert xirr([(pd.Timestamp("2025-01-01"), -100.0), (pd.Timestamp("2025-01-03"), 101.0)]) is None


def test_intraday_only_journals_do_not_report_a_silly_annualized_rate():
    rows = []
    for d in range(1, 29):
        rows += [
            (f"2026-04-{d:02d} 10:00", "A", "buy", 10, 100.0, 0),
            (f"2026-04-{d:02d} 15:00", "A", "sell", 10, 101.0, 0),
        ]
    result = analyze(_df(rows))
    assert result["profile"]["xirr"]["value"] is None


# ------------------------------------------------------------------ behaviour
def _trips(rows):
    return pd.DataFrame(rows, columns=["pnl", "hold_days"])


def test_disposition_effect_is_high_when_losers_are_held_much_longer():
    t = _trips([(100, 2), (120, 3), (-80, 20), (-90, 25)])
    r = disposition_effect(t)
    assert r["severity"] == "high" and r["ratio_loss_to_win_hold"] > 5


def test_disposition_effect_needs_both_winners_and_losers():
    assert disposition_effect(_trips([(100, 2), (50, 3)]))["severity"] == "low"


def test_chasing_momentum_counts_buys_after_a_runup():
    prices = [
        100,
        100,
        100,
        110,
        120,
        130,
        140,
    ]  # each buy after the 4th is >3% above the buy three earlier
    df = _df([(f"2026-05-{i + 1:02d} 10:00", "A", "buy", 1, p, 0) for i, p in enumerate(prices)])
    r = chasing_momentum(df)
    assert r["buys_evaluated"] == 4 and r["chase_ratio"] == 1.0 and r["severity"] == "high"


def test_anchoring_flags_symbols_traded_in_a_tight_band():
    df = _df(
        [(f"2026-05-{i + 1:02d} 10:00", "A", "buy", 1, 100.0 + (i % 2) * 0.5, 0) for i in range(6)]
    )
    assert anchoring(df)["severity"] == "high"


# ------------------------------------------------------------------ end to end
def test_sample_journal_runs_end_to_end_and_shows_the_planted_habits():
    fmt, df = parse(load_table(sample_tradebook_csv().encode(), "sample.csv"))
    assert fmt == "zerodha" and len(df) > 100
    result = analyze(df)
    p = result["profile"]
    assert p["closed_round_trips"] > 50 and set(p["by_category"]) >= {"intraday", "short_term"}
    assert result["behavior"]["disposition_effect"]["severity"] in {"medium", "high"}
    assert result["findings"] and result["findings"][0]["severity"] in {"high", "medium"}
    assert result["round_trips"] and "entry_dt" in result["round_trips"][0]


def test_api_upload_and_error_paths():
    from fastapi.testclient import TestClient

    from aletheia.core.main import create_app

    client = TestClient(create_app())
    ok = client.post("/api/v1/journal/analyze", files={"file": ("tb.csv", ZERODHA, "text/csv")})
    assert ok.status_code == 200 and ok.json()["file"]["format"] == "zerodha"
    assert ok.json()["profile"]["total_pnl"] == 495.0  # (1300 - 1250.50) x 10
    bad = client.post(
        "/api/v1/journal/analyze", files={"file": ("tb.pdf", b"%PDF", "application/pdf")}
    )
    assert bad.status_code == 422 and "csv or .xlsx" in bad.json()["message"]
    sample = client.post("/api/v1/journal/analyze-sample")
    assert sample.status_code == 200 and sample.json()["synthetic"] is True
