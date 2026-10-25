# Free live-data sources: what was evaluated and what works

Goal: live Indian stock prices with no broker account. Findings from testing each candidate against the
real services (not just reading READMEs). Dates are when it was tested: Sunday 25 Oct 2026, market closed.

## What works today

| Source | Cost / account | Cadence | Status |
|---|---|---|---|
| **Binance public WebSocket** (crypto) | free, none | ~1 s | Works. Verified live. Always on (`ALETHEIA_CRYPTO_STREAM_ENABLED`). |
| **BSE website API** (stocks) | free, none | poll, ~2 s | Works technically. **Unofficial.** Real-time-ness during market hours is unverified; each quote carries BSE's own timestamp so lag is shown on screen. |
| Yahoo Finance | free, none | delayed | Default fallback. |

### Turning on the BSE source

Settings → Market Data Feeds → **Per-second live feed from** → *BSE website*, save, restart the backend.
Or `ALETHEIA_LIVE_FEED_PROVIDER=bse_web`. Then, **on a trading day (Mon-Fri 09:15-15:30 IST)**:

```powershell
.venv\Scripts\python.exe scripts\bse_check.py
```

It compares BSE's 'as on' time with your clock. A lag of 0-1 minute means live; several minutes means delayed.
That result decides whether this is useful to you.

What to know before relying on it:
- **Unofficial.** It uses the same public endpoints as the open-source `bshada/nse-bse-api` library. BSE can
  change or block them, and its terms may restrict automated access. Aletheia limits itself to 8 requests per
  second overall, never polls faster than every 1 s, and backs off exponentially on 403/429/5xx.
- **BSE prices, not NSE.** For large caps they track NSE within paise; thin stocks can differ. Rows are labelled
  "BSE price".
- **No volume** in this response. Symbols are matched on BSE's ticker (`scrip_id`), usually the NSE ticker;
  unmatched ones show "unknown".
- **Polling, not a push stream.** About 1-3 s freshness at best. Practical rate with many symbols is limited by
  the 8 requests/s cap (100 symbols take about 12 s per pass).

## What does not work, and why

| Candidate | Result |
|---|---|
| NSE website (`nseindia.com/api/...`) | **Blocked.** HTTP 403 Access Denied even after cookie priming, using the same headers the `nse-bse-api` library uses. Getting past this would mean evading bot protection, so it is not attempted. |
| `bshada/nse-bse-api` NSE half | Same block as above. Its **BSE half is what Aletheia uses**. |
| `maanavshah/stock-market-india` | **Dead.** Every NSE endpoint it uses is on the legacy `www1.nseindia.com` host, which fails the TLS handshake; the repo has not been updated since December 2023. Its BSE endpoints are older HTML/ASPX pages superseded by the API above. |
| `0xramm/Indian-Stock-Market-API` | A Flask wrapper around Yahoo Finance, which Aletheia already uses. It adds no new data and Yahoo's NSE data is delayed. |
| RapidAPI "Indian Stock Exchange API" (linuz) | **Not evaluated.** It needs a RapidAPI account and key plus a subscription, the page content would not load here, and its data source and delay are undisclosed. Resellers of this kind typically repackage scraped or delayed data; it conflicts with the no-account goal. |
| Yahoo Finance at higher polling rates | Same delayed data, more likely to be throttled. |

## If you want guaranteed, licensed real-time

A broker account is the only legitimate route: Angel One ([ANGEL_ONE_SETUP.md](ANGEL_ONE_SETUP.md)) or Fyers
([FYERS_SETUP.md](FYERS_SETUP.md)). Both are built and documented but not yet run against a live account.
