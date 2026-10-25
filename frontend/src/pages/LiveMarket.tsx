import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import TopBar from "../components/TopBar";
import { getFeedStatus, getWatchlist, saveWatchlist } from "../lib/api";
import type { FeedStatus, LiveQuote, WatchItem } from "../lib/api";
import { quoteKey, useMarketFeed } from "../lib/useMarketFeed";
import { tradingViewUrl } from "../lib/tradingview";
import PriceChart from "../components/PriceChart";

const LAG_WARN_SECS = 180; // exchange data older than this during market hours is not 'live'

const fmt = (v?: number | null, d = 2) =>
  v == null ? "–" : v.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });

function ageSecs(q: LiveQuote | undefined, now: number): number | null {
  if (!q) return null;
  const t = Date.parse(q.as_of);
  return Number.isNaN(t) ? null : Math.max(0, Math.round((now - t) / 1000));
}

export default function LiveMarket() {
  const { quotes, moves, connection } = useMarketFeed();
  const [items, setItems] = useState<WatchItem[]>([]);
  const [status, setStatus] = useState<FeedStatus | null>(null);
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState("NSE");
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const refreshStatus = useCallback(() => {
    getFeedStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    getWatchlist().then((w) => setItems(w.items)).catch((e) => setError(String(e)));
    refreshStatus();
    const a = window.setInterval(refreshStatus, 5000);
    const b = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.clearInterval(a);
      window.clearInterval(b);
    };
  }, [refreshStatus]);

  async function persist(next: WatchItem[]) {
    setError(null);
    try {
      const saved = await saveWatchlist(next);
      setItems(saved.items);
      refreshStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the watchlist");
    }
  }

  function add(e: React.FormEvent) {
    e.preventDefault();
    const s = symbol.trim().toUpperCase();
    if (!s) return;
    setSymbol("");
    void persist([...items, { symbol: s, exchange }]);
  }

  const selectedItem = items.find((i) => quoteKey(i.symbol, i.exchange) === selected) ?? null;
  const selectedQuote = selectedItem ? quotes[quoteKey(selectedItem.symbol, selectedItem.exchange)] : undefined;

  const unresolved = useMemo(() => new Set(status?.unresolved_symbols ?? []), [status]);
  const live = status?.mode === "stream";
  const marketOpen = status?.market.is_open ?? false;

  const badge = (() => {
    if (connection !== "open") return { text: "Reconnecting to backend…", color: "var(--red)" };
    const cryptoLive = !!status?.crypto?.connected;
    if (live) {
      const extra = cryptoLive ? " · crypto live (Binance)" : "";
      return { text: `● LIVE · ${status?.source ?? "stream"}${extra}`, color: "var(--green)" };
    }
    // No broker stream, but crypto may still be live: say exactly which parts are which.
    if (cryptoLive) {
      return { text: "● Crypto LIVE (Binance, ~1s) · ◐ stocks delayed (Yahoo)", color: "var(--green)" };
    }
    return { text: `◐ ${status?.source ?? "Polling"}`, color: "var(--amber)" };
  })();

  return (
    <>
      <TopBar title="Live Market" />
      <div className="page-shell">
        <div
          className="card"
          style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-4)", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-4)" }}
        >
          <span role="status" style={{ color: badge.color, fontWeight: 600 }}>{badge.text}</span>
          <span style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
            {status ? `${status.market.label} · IST ${status.market.ist_time}` : ""}
          </span>
        </div>

        {status && !live && status.setup_hint && (
          <div className="card" style={{ borderLeft: "4px solid var(--amber)", marginBottom: "var(--space-4)" }}>
            <strong>Not streaming.</strong> {status.setup_hint} Prices below are delayed and refresh every
            few seconds. Setup guide: <code>{status.provider === "fyers" ? "docs/FYERS_SETUP.md" : "docs/ANGEL_ONE_SETUP.md"}</code>.
          </div>
        )}
        {status?.stream?.error && status.stream.error !== status.setup_hint && (
          <div className="card" role="alert" style={{ borderLeft: "4px solid var(--red)", marginBottom: "var(--space-4)" }}>
            Stream problem: {status.stream.error}
          </div>
        )}
        {status?.crypto?.error && !status.crypto.connected && (
          <div className="card" role="alert" style={{ borderLeft: "4px solid var(--amber)", marginBottom: "var(--space-4)" }}>
            Crypto stream problem: {status.crypto.error}. Crypto prices fall back to the delayed feed. Run <code>scripts/crypto_check.py</code> to diagnose; if Binance is blocked in your region, set <code>ALETHEIA_CRYPTO_STREAM_ENABLED=false</code>.
          </div>
        )}
        {live && status?.stream?.unofficial && (
          <div className="card" style={{ borderLeft: "4px solid var(--amber)", marginBottom: "var(--space-4)" }}>
            <strong>Unofficial free source.</strong> Prices are polled from BSE's public website every{" "}
            {status.stream.poll_secs ?? 2}s. They are BSE prices (large caps track NSE within paise), the site can
            change or block access, and its data is only as live as BSE makes it. Check the exchange-lag note on
            each row.
          </div>
        )}
        {live && status?.stream?.unofficial && marketOpen && (status.stream.data_lag_secs ?? 0) > LAG_WARN_SECS && (
          <div className="card" role="alert" style={{ borderLeft: "4px solid var(--red)", marginBottom: "var(--space-4)" }}>
            BSE's own timestamps trail your clock by about {Math.round((status.stream.data_lag_secs ?? 0) / 60)} minutes.
            Treat these prices as delayed, not live.
          </div>
        )}
        {live && status?.stream?.price_scale_verified === false && (
          <div className="card" role="alert" style={{ borderLeft: "4px solid var(--red)", marginBottom: "var(--space-4)" }}>
            Streamed prices could not be matched to the broker's own reference quote. Do not trade on them until this
            clears.
          </div>
        )}
        {live && !marketOpen && (
          <div className="card" style={{ marginBottom: "var(--space-4)", color: "var(--text-secondary)" }}>
            The market is closed, so prices are not moving. They will tick again at 09:15 IST on a trading day.
          </div>
        )}

        <form onSubmit={add} className="card" style={{ display: "flex", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
          <input
            className="form-control"
            aria-label="Symbol"
            placeholder="Add symbol, e.g. WIPRO"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            style={{ flex: 1, textTransform: "uppercase", fontFamily: "var(--font-mono)" }}
          />
          <select className="form-control" aria-label="Exchange" value={exchange} onChange={(e) => setExchange(e.target.value)}>
            <option>NSE</option>
            <option>BSE</option>
            <option>BINANCE</option>
          </select>
          <button className="btn btn-primary" type="submit">
            <Plus size={16} /> Add
          </button>
        </form>
        {error && <div className="card" role="alert" style={{ color: "var(--red)", marginBottom: "var(--space-4)" }}>{error}</div>}

        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th style={{ textAlign: "right" }}>Last</th>
                  <th style={{ textAlign: "right" }}>Change</th>
                  <th style={{ textAlign: "right" }}>Open</th>
                  <th style={{ textAlign: "right" }}>High</th>
                  <th style={{ textAlign: "right" }}>Low</th>
                  <th style={{ textAlign: "right" }}>Volume</th>
                  <th>Source</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((it) => {
                  const key = quoteKey(it.symbol, it.exchange);
                  const q = quotes[key];
                  const age = ageSecs(q, now);
                  // Crypto trades 24/7, so a quiet crypto row is stale at any hour; stocks only while the market is open.
                  const lagging = q?.data_lag_secs != null && q.data_lag_secs > LAG_WARN_SECS;
                  const stale = age != null && age > (q?.stream ? 10 : 60) && (it.exchange === "BINANCE" || marketOpen);
                  const move = moves[key];
                  const chg = q?.change_pct;
                  return (
                    <tr
                      key={key}
                      data-testid={`row-${it.symbol}`}
                      onClick={() => setSelected(key)}
                      style={{
                        cursor: "pointer",
                        background: key === selected ? "var(--accent-muted)" : undefined,
                      }}
                    >
                      <td>
                        <button
                          type="button"
                          className="btn btn-ghost"
                          aria-label={`Open chart for ${it.symbol}`}
                          aria-pressed={key === selected}
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelected(key === selected ? null : key);
                          }}
                          style={{ padding: 0, fontWeight: 700 }}
                        >
                          {it.symbol}
                        </button>{" "}
                        <span style={{ color: "var(--text-muted)", fontSize: "var(--text-xs)" }}>{it.exchange}</span>
                        {unresolved.has(`${it.symbol}:${it.exchange}`) && (
                          <span title="Your live-feed broker can't stream this symbol" style={{ color: "var(--amber)" }}> ⚠ unknown</span>
                        )}
                      </td>
                      <td
                        style={{
                          textAlign: "right",
                          fontFamily: "var(--font-mono)",
                          fontWeight: 600,
                          color: move === "up" ? "var(--green)" : move === "down" ? "var(--red)" : undefined,
                        }}
                      >
                        {fmt(q?.close)}
                      </td>
                      <td
                        style={{
                          textAlign: "right",
                          fontFamily: "var(--font-mono)",
                          color: chg == null ? undefined : chg >= 0 ? "var(--green)" : "var(--red)",
                        }}
                      >
                        {chg == null ? "–" : `${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%`}
                      </td>
                      <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{fmt(q?.open)}</td>
                      <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{fmt(q?.high)}</td>
                      <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{fmt(q?.low)}</td>
                      <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{fmt(q?.volume, 0)}</td>
                      <td style={{ fontSize: "var(--text-xs)", color: stale || lagging ? "var(--red)" : "var(--text-muted)" }}>
                        {q
                          ? `${q.stream ? "live" : "delayed"} · ${age ?? "?"}s ago${stale ? " · STALE" : ""}` +
                            (q.price_exchange && q.price_exchange !== q.exchange ? ` · ${q.price_exchange} price` : "") +
                            (lagging ? ` · exchange data ${Math.round((q.data_lag_secs ?? 0) / 60)} min old` : "")
                          : "waiting…"}
                      </td>
                      <td>
                        <button
                          className="btn btn-ghost"
                          aria-label={`Remove ${it.symbol}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (key === selected) setSelected(null);
                            void persist(items.filter((i) => quoteKey(i.symbol, i.exchange) !== key));
                          }}
                        >
                          <X size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {items.length === 0 && (
                  <tr>
                    <td colSpan={9} style={{ color: "var(--text-muted)" }}>
                      Your watchlist is empty. Add a symbol above.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {selectedItem && (
          <div className="card" style={{ marginTop: "var(--space-4)" }}>
            <div className="card-header">
              <span className="card-title">
                {selectedItem.symbol} · {selectedItem.exchange}
              </span>
              <span style={{ display: "flex", gap: "var(--space-4)", alignItems: "center" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>
                  {selectedQuote ? fmt(selectedQuote.close) : "–"}{" "}
                  <span style={{ color: "var(--text-muted)", fontSize: "var(--text-xs)", fontWeight: 400 }}>
                    {selectedQuote ? (selectedQuote.stream ? "your live feed" : "your feed (delayed)") : "waiting…"}
                  </span>
                </span>
                <button className="btn btn-ghost" onClick={() => setSelected(null)} aria-label="Close chart">
                  <X size={14} />
                </button>
              </span>
            </div>
            <PriceChart
              key={`${selectedItem.exchange}:${selectedItem.symbol}`}
              symbol={selectedItem.symbol}
              exchange={selectedItem.exchange}
              quote={selectedQuote}
            />
            <p style={{ color: "var(--text-muted)", fontSize: "var(--text-xs)", marginTop: "var(--space-2)" }}>
              Candles are history from Yahoo Finance; the last candle moves with your live feed.{" "}
              <a href={tradingViewUrl(selectedItem.symbol, selectedItem.exchange)} target="_blank" rel="noopener noreferrer">
                Open in TradingView ↗
              </a>
            </p>
          </div>
        )}
      </div>
    </>
  );
}
