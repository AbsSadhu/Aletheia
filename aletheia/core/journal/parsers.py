"""Broker export parsing: CSV or Excel to one standard trades table.

Standard columns: datetime, symbol, name, side ("buy"/"sell"), quantity, price, amount, fee,
segment. Zerodha's tradebook is recognised by name; anything else is matched by column aliases,
so Upstox, Groww, Angel One, ICICI Direct and hand-made sheets work if they carry a symbol, a
side, a quantity, a price and some form of date.

Adapted in part from Vibe-Trading's generic journal parser (MIT; see THIRD_PARTY_NOTICES.md).
"""

from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 100_000

STANDARD_COLUMNS = [
    "datetime",
    "symbol",
    "name",
    "side",
    "quantity",
    "price",
    "amount",
    "fee",
    "segment",
]

_BUY = {"buy", "b", "bought", "purchase", "long", "bto", "cover"}
_SELL = {"sell", "s", "sold", "sale", "short", "sto"}

# header (lower-cased, punctuation squashed) -> standard field
_ALIASES: dict[str, list[str]] = {
    "symbol": [
        "symbol",
        "tradingsymbol",
        "trading symbol",
        "scrip",
        "scrip name",
        "script",
        "stock",
        "stock name",
        "ticker",
        "instrument",
        "security",
        "code",
    ],
    "side": [
        "side",
        "trade type",
        "tradetype",
        "buy sell",
        "buy/sell",
        "buysell",
        "transaction type",
        "transaction",
        "action",
        "direction",
        "type",
        "b/s",
    ],
    "quantity": [
        "quantity",
        "qty",
        "traded qty",
        "traded quantity",
        "shares",
        "units",
        "size",
        "volume",
    ],
    "price": [
        "price",
        "trade price",
        "rate",
        "avg price",
        "average price",
        "net rate",
        "executed price",
        "traded price",
        "buy price/sell price",
    ],
    "amount": ["amount", "value", "trade value", "net amount", "turnover", "notional", "net total"],
    "fee": ["fee", "fees", "brokerage", "charges", "commission", "total charges"],
    "datetime": [
        "datetime",
        "date time",
        "order execution time",
        "order_execution_time",
        "executed at",
        "execution time",
        "trade time",
        "timestamp",
        "time",
    ],
    "date": ["trade date", "trade_date", "date", "order date", "execution date", "tradedate"],
    "segment": ["segment", "exchange segment", "series", "product", "market"],
    "name": ["name", "company", "company name", "security name", "description"],
}


class JournalFormatError(ValueError):
    """The file could not be read as a trade journal; the message says why, in plain words."""


def _norm(col: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_\-]+", " ", str(col)).strip().lower())


def load_table(content: bytes, filename: str) -> pd.DataFrame:
    """Bytes of a CSV or xlsx file to a raw DataFrame."""
    if len(content) > MAX_BYTES:
        raise JournalFormatError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    name = filename.lower()
    try:
        if name.endswith((".xlsx", ".xlsm")):
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
        elif name.endswith(".csv") or name.endswith(".txt"):
            text = content.decode("utf-8-sig", errors="replace")
            df = pd.read_csv(io.StringIO(text), sep=None, engine="python")
        else:
            raise JournalFormatError(
                "Upload a .csv or .xlsx file (an .xls sheet: save it as .xlsx first)."
            )
    except JournalFormatError:
        raise
    except Exception as exc:  # pandas/openpyxl raise many types for a bad file
        raise JournalFormatError(f"Could not read the file: {exc}") from exc
    df = df.dropna(how="all")
    if df.empty:
        raise JournalFormatError("The file has no rows.")
    if len(df) > MAX_ROWS:
        raise JournalFormatError(f"The file has more than {MAX_ROWS:,} rows.")
    return df


def _pick(columns: dict[str, str], field: str) -> str | None:
    for alias in _ALIASES[field]:
        if _norm(alias) in columns:
            return columns[_norm(alias)]
    return None


def _num(value: Any) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    text = re.sub(r"[₹$,\s]", "", str(value))
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return float(text)
    except ValueError:
        return 0.0


def _side(value: Any) -> str | None:
    token = str(value).strip().lower()
    if token in _BUY:
        return "buy"
    if token in _SELL:
        return "sell"
    if token.startswith("buy") or token.startswith("purchase"):
        return "buy"
    if token.startswith("sell") or token.startswith("sale"):
        return "sell"
    return None


def _stamp(value: Any) -> pd.Timestamp:
    """Cell to Timestamp. Day-first dates are the norm in Indian exports."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NaT
    if isinstance(value, (int, float)) and 1.0 <= float(value) < 100_000.0:  # Excel serial
        return pd.to_datetime(float(value), unit="D", origin="1899-12-30", errors="coerce")
    text = str(value).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return pd.to_datetime(text, errors="coerce")
    return pd.to_datetime(text, dayfirst=True, errors="coerce")


def clean_symbol(raw: Any) -> str:
    text = str(raw).strip().upper()
    text = re.sub(r"^(NSE|BSE|NFO|MCX)[:\-]", "", text)
    text = re.sub(r"[-.](EQ|BE|N1|NS|BO)$", "", text)
    return text


def detect_format(columns: list[str]) -> str:
    cols = {_norm(c) for c in columns}
    if {"trade type", "symbol", "trade date"} <= cols or {
        "trade type",
        "symbol",
        "order execution time",
    } <= cols:
        return "zerodha"
    return "generic"


def parse(df: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    """Returns (format name, standard trades table sorted by time)."""
    columns = {_norm(c): str(c) for c in df.columns}
    fmt = detect_format(list(df.columns))
    sym, side, qty, price = (_pick(columns, f) for f in ("symbol", "side", "quantity", "price"))
    missing = [
        label
        for label, col in (
            ("symbol", sym),
            ("buy/sell side", side),
            ("quantity", qty),
            ("price", price),
        )
        if col is None
    ]
    if missing:
        raise JournalFormatError(
            f"Could not find the {', '.join(missing)} column. Columns in the file: {', '.join(map(str, df.columns))[:300]}."
        )
    dt_col, date_col = _pick(columns, "datetime"), _pick(columns, "date")
    if dt_col is None and date_col is None:
        raise JournalFormatError("Could not find a date or time column.")
    amount_col, fee_col, seg_col, name_col = (
        _pick(columns, f) for f in ("amount", "fee", "segment", "name")
    )

    rows: list[dict[str, Any]] = []
    skipped = 0
    for _, r in df.iterrows():
        s = _side(r[side])
        q = _num(r[qty])
        p = _num(r[price])
        ts = _stamp(r[dt_col]) if dt_col else pd.NaT
        if pd.isna(ts) and date_col:
            ts = _stamp(r[date_col])
        elif date_col and dt_col and ts is not pd.NaT and ts.hour == 0 and ts.minute == 0:
            day = _stamp(r[date_col])  # a time-only cell next to a date cell
            if pd.notna(day):
                ts = day
        if (
            s is None
            or q <= 0
            or p <= 0
            or pd.isna(ts)
            or not str(r[sym]).strip()
            or str(r[sym]).strip().lower() == "nan"
        ):
            skipped += 1
            continue
        rows.append(
            {
                "datetime": ts,
                "symbol": clean_symbol(r[sym]),
                "name": str(r[name_col]).strip() if name_col else "",
                "side": s,
                "quantity": q,
                "price": p,
                "amount": abs(_num(r[amount_col])) if amount_col and _num(r[amount_col]) else q * p,
                "fee": abs(_num(r[fee_col])) if fee_col else 0.0,
                "segment": str(r[seg_col]).strip().upper() if seg_col else "",
            }
        )
    if not rows:
        raise JournalFormatError(
            "No usable trades were found. Rows need a symbol, buy/sell, quantity, price and a date."
        )
    out = (
        pd.DataFrame(rows, columns=STANDARD_COLUMNS)
        .sort_values("datetime", kind="stable")
        .reset_index(drop=True)
    )
    out.attrs["skipped_rows"] = skipped
    return fmt, out
