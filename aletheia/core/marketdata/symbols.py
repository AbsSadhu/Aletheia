"""Turn a symbol as the user typed it into the one Yahoo Finance knows today."""

from __future__ import annotations

# Listings that changed ticker. Each pair was checked against live Yahoo data: the old symbol
# returns "no data / delisted" and the new one has current prices. Keep it short and verified.
RENAMED_TICKERS: dict[str, str] = {
    "ZOMATO": "ETERNAL",  # Zomato renamed itself Eternal
    # Tata Motors demerged; the listed passenger-vehicle company kept the old price history
    # (commercial vehicles trade separately as TMCV).
    "TATAMOTORS": "TMPV",
}

_NSE_BSE_SUFFIXES = (".NS", ".BO")

# Bare coin tickers someone might type without a quote currency. Matched whole, never as a substring:
# ADANIENT and ADANIPORTS are NSE stocks that merely contain "ADA".
_CRYPTO_BASES = frozenset({"BTC", "ETH", "SOL", "ADA", "BNB", "XRP", "DOGE", "DOT", "LTC", "MATIC"})
_CRYPTO_QUOTE_SUFFIXES = ("-USD", "-USDT", "-INR", "USDT")


def is_crypto(symbol: str) -> bool:
    """True for a coin pair (BTC/USDT), a Yahoo crypto symbol (SOL-USD), BTCUSDT or a bare coin ticker."""
    s = symbol.upper()
    return "/" in s or s.endswith(_CRYPTO_QUOTE_SUFFIXES) or s in _CRYPTO_BASES


def apply_rename(symbol: str) -> str:
    """Map an old ticker to its current one; any exchange suffix is kept."""
    s = symbol.upper()
    for suffix in (*_NSE_BSE_SUFFIXES, ""):
        if suffix and not s.endswith(suffix):
            continue
        base = s[: -len(suffix)] if suffix else s
        if base in RENAMED_TICKERS:
            return RENAMED_TICKERS[base] + suffix
    return s


def yahoo_symbol(symbol: str, exchange: str) -> str:
    s, e = symbol.upper(), exchange.upper()
    if "/" not in s and s.endswith(("-USD", "-USDT")):
        return s  # already a Yahoo crypto symbol such as SOL-USD
    if "/" in s or e == "BINANCE":
        base, _, quote = s.partition("/")
        return f"{base}-{'USD' if quote in ('USDT', 'USD', '') else quote}"
    if s.startswith("^"):
        return s
    s = apply_rename(s)
    if s.endswith(_NSE_BSE_SUFFIXES):
        return s
    return f"{s}.{'BO' if e == 'BSE' else 'NS'}"
