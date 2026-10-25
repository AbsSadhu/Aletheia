# Fyers live feed: setup guide

Gives Aletheia a per-second NSE feed from Fyers' official data WebSocket. It is an alternative to
the Angel One feed; pick one in Settings.

You need an active Fyers trading account. This is data only; nothing here places orders.

## How it works (and why there is a helper environment)

Fyers' stream uses a binary protocol that their official `fyers-apiv3` SDK decodes. Rather than
re-implement that decoder without a live account to test against (a decoding mistake would mean
wrong prices), Aletheia runs the **official SDK** in a small helper process. That SDK pulls in
boto3 and AWS packages and pins older `requests`/`aiohttp`, which breaks Aletheia's own
environment (this was observed), so it lives in its own virtualenv at `~/.aletheia/fyers-venv`.
Aletheia's environment is not touched.

## 1. Create a Fyers API app (one time)

1. Sign in at <https://myapi.fyers.in/dashboard> and choose **Create App**.
2. **Redirect URL:** use exactly the one shown in Aletheia under Settings → Fyers. By default:
   `http://127.0.0.1:8899/api/v1/brokers/fyers/callback`. It must match character for character.
3. Create it, then copy the **App ID** (looks like `ABC123XYZ-100`) and the **Secret**.

Fyers' docs list plan limits for the data stream: the Standard plan allows up to **100 symbols**
in total, Prime up to 5,000. Aletheia's watchlist is capped at 100, so Standard is enough. Check
Fyers' current plan page for pricing.

## 2. Install the helper environment (one time)

```powershell
.venv\Scripts\python.exe scripts\fyers_setup.py
```

It creates `~/.aletheia/fyers-venv`, installs `fyers-apiv3==3.2.0` there, and checks it imports.

## 3. Save your app details and choose Fyers

Settings → *Broker Integrations* → **Fyers**: enter the App ID and Secret and save. Then under
*Market Data Feeds*, set **Per-second live feed from** to **Fyers** and save. (Or set
`ALETHEIA_LIVE_FEED_PROVIDER=fyers` in `.env`.) **Restart the backend.**

## 4. Log in (every trading day)

Settings → **Connect Fyers**. Log in on Fyers' site; it redirects back to Aletheia, which stores the
token (encrypted). Fyers access tokens **expire every day at 06:30 IST**, so repeat this each trading
day. No restart is needed: the running stream notices the new token within a few seconds.

## 5. Test it

```powershell
.venv\Scripts\python.exe scripts\fyers_check.py
```

It checks credentials, the helper environment, today's login, then streams RELIANCE and TCS for 15
seconds and compares the streamed prices with Yahoo's last close as a sanity check. Run it between
09:15 and 15:30 IST on a trading day to see ticks.

## 6. Watch it

Open **Live Market**. The badge should read **● LIVE · Fyers (live, ~1s)**.

## What to expect

- **NSE equities only.** Symbols stream as `NSE:SYMBOL-EQ`. BSE symbols and crypto are not streamed by
  Fyers here; they fall back to the slower delayed polling and show `⚠ unknown` for BSE. Indices are not in
  the watchlist.
- **Rate:** each symbol is pushed at most once a second (`ALETHEIA_MARKET_FEED_EMIT_INTERVAL_SECS`,
  minimum 0.2). Each tick carries the exchange's own trade time, so the "age" you see is real staleness.
- **Failures are loud.** An expired or invalid token shows "log in again" and stops retrying; a helper
  crash restarts automatically; ticks stopping for 60 seconds during market hours restarts the helper.
- **Packaged desktop app:** the helper environment is created from the source tree with the script above,
  so this feed is for source installs, not the frozen installer.

## Troubleshooting

| Symptom | Cause |
|---|---|
| "Fyers helper environment is missing" | Run `scripts/fyers_setup.py`, then restart the backend. |
| "Fyers login expired or invalid; log in again" | Tokens reset at 06:30 IST. Settings → Connect Fyers. Also shown for a bad or empty token. |
| Login page says redirect mismatch | The app's redirect URL differs from the one in Settings; edit the app on myapi.fyers.in. |
| "Login rejected: unknown or expired state" | You opened an old login link; click Connect Fyers again. |
| Connected, no ticks during market hours | Check the symbol is an NSE equity (e.g. `RELIANCE`); run `fyers_check.py`. |
| Symbol limit message | Standard plan is 100 symbols total across connections. |

## Verified vs not

Tested with the real SDK: installing it into an isolated environment, running the helper with it, and its
response to an invalid token (reported as "log in again" within about a second, no restart loop, clean
shutdown). Tested with a stand-in for the SDK: the full tick path (subscribe, ticks, coalescing, live watchlist
changes, restarts). **Not tested from this repository:** a successful login and live ticks, since that needs
your Fyers account. `scripts/fyers_check.py` is how you confirm it on yours; if it fails, send me the output.
