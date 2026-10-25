# Angel One live feed: setup guide

Gives Aletheia a free, official NSE/BSE feed that updates **about once per second** per symbol
(WebSocket stream), instead of the 15-second delayed polling fallback.

You need an active Angel One trading account. Nothing here places orders; this is data only.

## 1. Enable TOTP on your Angel One account (one time)

SmartAPI logins need a time-based one-time password.

1. Go to <https://smartapi.angelone.in/enable-totp> (the same page is sometimes linked from
   `smartapi.angelbroking.com`; use whichever opens).
2. Enter your **client ID** and **PIN**, then the OTP sent to your registered phone/email.
3. A QR code appears. Scan it with Google Authenticator, Authy or similar, **and also copy the
   long text code (the "secret key", letters A-Z and digits 2-7) and keep it somewhere safe.**
   Aletheia needs that text. If you lose it you must re-enable TOTP to get a new one.

## 2. Create a SmartAPI app (one time)

1. Sign in at <https://smartapi.angelone.in> and open **My Apps** → **Create App**.
2. App type: **Trading APIs**. Redirect URL: `http://127.0.0.1` (not used by Aletheia, but the form
   requires one). Name it anything.
3. Copy the **API key**. You do not need the API secret.

If a later step reports a permissions error on quotes or the stream, create a second app of a
market-data type if Angel One offers one, and use that key instead.

## 3. Save your credentials in Aletheia

You need four values:

| Value | Where it comes from |
|---|---|
| API key | step 2 |
| Client code | your Angel One login ID (like `A123456`) |
| PIN | your 4-digit Angel One trading PIN |
| TOTP secret | the text code from step 1 (spaces are ignored) |

Easiest: run the wizard and answer **yes** to the Angel One question.

```powershell
.venv\Scripts\python.exe -m aletheia.cli.main config init
```

Or fill them in on the **Settings** page under *Broker Integrations*. They are stored encrypted and
in your OS keyring, never in plain text on disk, and are masked in the UI after saving.

## 4. Test it before turning it on

```powershell
.venv\Scripts\python.exe scripts\angel_check.py
```

It checks, in order: credentials saved, login, instrument lookup, a REST quote, then streams
RELIANCE for 12 seconds and confirms the streamed price matches the REST price. Each line says
`PASS` or `FAIL` with what to fix. Run it during market hours (Mon-Fri 09:15-15:30 IST) to see
ticks; outside hours it still verifies login and the connection and tells you no ticks is expected.

## 5. Turn it on

Settings → *Market Data Feeds* → switch on **Angel One Live Feed** → save. Or put this in `.env`:

```
ALETHEIA_ANGEL_ONE_ENABLED=true
```

Then **restart the backend**; it reads this at startup.

## 6. Watch it

Open **Live Market** in the sidebar. The badge should read **● LIVE · Angel One · ~1s**. Add symbols
with the box at the top (NSE or BSE ticker, e.g. `WIPRO`); the stream follows immediately. A symbol
Angel One doesn't list shows `⚠ unknown`. Crypto (BTC/USDT) is not on Angel One, so it keeps coming
from the slower polling feed.

## What to expect

- **Update rate:** each symbol is pushed at most once a second (`ALETHEIA_MARKET_FEED_EMIT_INTERVAL_SECS`,
  minimum 0.2). Liquid stocks change more often than that; the latest price wins.
- **Market closed:** prices simply don't move; the page says so. Exchange holidays are not known, so on a
  holiday it will say "open" with no ticks.
- **Automatic recovery:** if the connection drops it reconnects with backoff, and re-logs in when the
  daily session expires. If ticks stop during market hours for 60 seconds it reconnects.
- **Fallback:** while the stream is down, the 15-second poller covers everything and the badge shows
  *delayed*.
- **Price check:** the first streamed price is compared with a REST quote. If the stream's scaling is wrong
  the divisor self-corrects; if it can't be matched, the page shows a red warning and you should not trade
  on it.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `Login rejected: Invalid TOTP` | Wrong secret, or your PC clock is off. Sync the Windows clock (Settings → Time & language → Sync now). |
| `Login rejected: Invalid ... password` | The PIN is wrong. Use the 4-digit trading PIN, not your web password. |
| `Invalid API key` / `Invalid Token` on quotes | Key copied with a space, or from a different app. Re-copy it. |
| Connected, but no ticks during market hours | Check the symbol shows no `⚠ unknown`; run `angel_check.py`. |
| Badge says *delayed* though configured | The switch in step 5 is off, or the backend was not restarted. |
| `Reconnecting to backend…` | The Aletheia backend itself isn't running or reachable. |

## Verified vs not

The stream protocol (URL, headers, subscribe messages, binary layout) comes from Angel One's official
SDK source and is covered by tests with simulated frames. It has **not** been run against a live Angel
One account from this repository: `scripts/angel_check.py` is how you confirm that on your own account.
Rules for retail algorithmic access (for example static-IP registration) have been tightening; they
mainly apply to order APIs, but check Angel One's current notices if login or the stream is refused.
