import json

import httpx
import pytest

from aletheia.extensions.data.providers.angel_one_provider import (
    LOGIN_PATH,
    QUOTE_PATH,
    AngelOneProvider,
    totp_now,
)

CREDS = {
    "api_key": "K",
    "client_code": "C1",
    "pin": "1234",
    "totp_secret": "JBSWY3DPEHPK3PXP",  # pragma: allowlist secret (well-known example key)
}


def test_totp_matches_rfc6238_vector() -> None:
    # RFC 6238 appendix B, SHA-1, secret "12345678901234567890", T=59 -> 94287082 (8 digits).
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # pragma: allowlist secret (RFC 6238 test key)
    assert totp_now(secret, at=59, digits=8) == "94287082"


def _provider(handler, tmp_path, creds=CREDS) -> AngelOneProvider:
    scrips = tmp_path / "scrips.json"
    scrips.write_text(
        json.dumps(
            [
                {"token": "2885", "symbol": "RELIANCE-EQ", "exch_seg": "NSE"},
                {"token": "500325", "symbol": "RELIANCE", "exch_seg": "BSE"},
            ]
        )
    )
    client = httpx.AsyncClient(
        base_url="https://apiconnect.angelone.in", transport=httpx.MockTransport(handler)
    )
    return AngelOneProvider(credentials=creds, client=client, scrip_master_path=scrips)


def _ok_handler(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, request.headers, json.loads(request.content)))
        if request.url.path == LOGIN_PATH:
            return httpx.Response(200, json={"status": True, "data": {"jwtToken": "JWT"}})
        assert request.url.path == QUOTE_PATH
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": {
                    "fetched": [
                        {"ltp": 1250.5, "open": 1240, "high": 1260, "low": 1235, "tradeVolume": 99}
                    ]
                },
            },
        )

    return handler


async def test_returns_live_quote_and_reuses_session(tmp_path) -> None:
    calls: list = []
    p = _provider(_ok_handler(calls), tmp_path)

    q = (await p.get_quote("RELIANCE", "NSE"))[0]
    await p.get_quote("RELIANCE", "NSE")

    assert (q.symbol, q.close, q.provider, q.volume) == ("RELIANCE", 1250.5, "angel_one", 99.0)
    paths = [c[0] for c in calls]
    assert paths.count(LOGIN_PATH) == 1  # second quote reused the JWT
    login_body = next(c[2] for c in calls if c[0] == LOGIN_PATH)
    assert login_body["clientcode"] == "C1" and len(login_body["totp"]) == 6
    quote_call = next(c for c in calls if c[0] == QUOTE_PATH)
    assert quote_call[1]["authorization"] == "Bearer JWT"
    assert quote_call[2] == {"mode": "FULL", "exchangeTokens": {"NSE": ["2885"]}}


async def test_failures_return_empty_so_collector_falls_through(tmp_path) -> None:
    def rejected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": False, "message": "Invalid TOTP"})

    assert await _provider(rejected, tmp_path).get_quote("RELIANCE", "NSE") == []
    assert await _provider(_ok_handler([]), tmp_path).get_quote("NOPE", "NSE") == []
    assert await _provider(_ok_handler([]), tmp_path).get_quote("RELIANCE", "NYSE") == []
    assert await _provider(_ok_handler([]), tmp_path, creds={}).get_quote("RELIANCE", "NSE") == []


async def test_expired_session_relogs_in_once(tmp_path) -> None:
    state = {"quotes": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == LOGIN_PATH:
            return httpx.Response(200, json={"status": True, "data": {"jwtToken": "JWT"}})
        state["quotes"] += 1
        if state["quotes"] == 1:
            return httpx.Response(200, json={"status": False, "message": "Invalid Token"})
        return httpx.Response(
            200, json={"status": True, "data": {"fetched": [{"ltp": 10, "open": 10}]}}
        )

    q = await _provider(handler, tmp_path).get_quote("RELIANCE", "NSE")
    assert q and q[0].close == 10.0


def test_gated_by_setting() -> None:
    class S:
        angel_one_enabled = False

    assert AngelOneProvider.check_available(S()) is False
    S.angel_one_enabled = True
    assert AngelOneProvider.check_available(S()) is True


@pytest.mark.parametrize("flag,expected", [(False, False), (True, True)])
def test_static_seed_is_opt_in(flag, expected) -> None:
    from aletheia.extensions.data.providers.static_seed import StaticSeedProvider

    class S:
        static_seed_enabled = flag

    assert StaticSeedProvider.check_available(S()) is expected
