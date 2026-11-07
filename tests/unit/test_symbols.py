"""Symbol resolution: renamed tickers and crypto pairs must reach Yahoo in a form it knows."""

from __future__ import annotations

import pandas as pd
import pytest

from aletheia.core.marketdata.symbols import yahoo_symbol


class TestYahooSymbol:
    @pytest.mark.parametrize(
        ("symbol", "exchange", "expected"),
        [
            ("RELIANCE", "NSE", "RELIANCE.NS"),
            ("RELIANCE.NS", "NSE", "RELIANCE.NS"),
            ("RELIANCE", "BSE", "RELIANCE.BO"),
            ("^NSEI", "NSE", "^NSEI"),
            ("BTC/USDT", "BINANCE", "BTC-USD"),
            ("eth/usdt", "BINANCE", "ETH-USD"),
            ("BTC/USDT", "NSE", "BTC-USD"),  # a pair is crypto whatever exchange it was filed under
            ("SOL-USD", "BINANCE", "SOL-USD"),
            ("BAJAJ-AUTO", "NSE", "BAJAJ-AUTO.NS"),  # hyphenated NSE tickers are not crypto
        ],
    )
    def test_ordinary_symbols(self, symbol: str, exchange: str, expected: str) -> None:
        assert yahoo_symbol(symbol, exchange) == expected

    @pytest.mark.parametrize(
        ("symbol", "expected"),
        [
            ("ZOMATO", "ETERNAL.NS"),
            ("zomato.ns", "ETERNAL.NS"),
            ("TATAMOTORS", "TMPV.NS"),
            ("TATAMOTORS.NS", "TMPV.NS"),
        ],
    )
    def test_renamed_tickers_follow_the_new_name(self, symbol: str, expected: str) -> None:
        assert yahoo_symbol(symbol, "NSE") == expected

    def test_a_rename_never_touches_crypto_or_indices(self) -> None:
        assert yahoo_symbol("^ZOMATO", "NSE") == "^ZOMATO"


@pytest.fixture(autouse=True)
def offline_price_history():
    """Overrides the conftest stub: these tests need the real loader (with yfinance faked)."""


class TestOracleHistoryLoader:
    async def test_crypto_pair_is_fetched_as_a_yahoo_crypto_symbol(self, monkeypatch) -> None:
        import yfinance as yf

        from aletheia.extensions.agents.oracle import OracleAgent

        seen: list[str] = []

        class FakeTicker:
            def __init__(self, sym: str) -> None:
                seen.append(sym)

            def history(self, **_: object) -> pd.DataFrame:
                return pd.DataFrame()

        monkeypatch.setattr(yf, "Ticker", FakeTicker)
        await OracleAgent._yfinance_ohlcv("BTC/USDT")
        await OracleAgent._yfinance_ohlcv("ZOMATO")
        assert seen == ["BTC-USD", "ETERNAL.NS"]


class TestIsCrypto:
    @pytest.mark.parametrize(
        "symbol", ["BTC/USDT", "BTCUSDT", "SOL-USD", "ETH-INR", "btc", "ADA", "eth/usdt"]
    )
    def test_crypto(self, symbol: str) -> None:
        from aletheia.core.marketdata.symbols import is_crypto

        assert is_crypto(symbol) is True

    # ADANIENT and ADANIPORTS contain "ADA", BETA contains "ETA" ... a substring is not a ticker.
    @pytest.mark.parametrize(
        "symbol", ["ADANIENT", "ADANIPORTS.NS", "RELIANCE", "BAJAJ-AUTO", "ETHOSLTD", "^NSEI"]
    )
    def test_not_crypto(self, symbol: str) -> None:
        from aletheia.core.marketdata.symbols import is_crypto

        assert is_crypto(symbol) is False


class TestOtherEntryPointsAgreeWithYahooSymbol:
    """The backtest tool and the signal-history route used to guess their own Yahoo symbols."""

    @pytest.mark.parametrize(
        ("symbol", "expected"),
        [
            ("RELIANCE", "RELIANCE.NS"),
            ("ZOMATO", "ETERNAL.NS"),
            ("RELIANCE.BO", "RELIANCE.BO"),
            ("^NSEI", "^NSEI"),
            ("BTC/USDT", "BTC-USD"),
            ("BAJAJ-AUTO", "BAJAJ-AUTO.NS"),
        ],
    )
    def test_backtest_tool(self, symbol: str, expected: str) -> None:
        from aletheia.core.tools.backtest_tool import _yahoo

        assert _yahoo(symbol) == expected
