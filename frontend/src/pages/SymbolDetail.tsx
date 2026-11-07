import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { ArrowDownRight, ArrowUpRight, Check, ExternalLink, Minus, Plus } from "lucide-react";

import FactorRadar from "../components/charts/FactorRadar";
import Flap from "../components/Flap";
import Gauge3D from "../components/Gauge3D";
import { NewsList, BADGE } from "../components/NewsList";
import PriceChart from "../components/PriceChart";
import SafeLink from "../components/SafeLink";
import TopBar from "../components/TopBar";
import { toneBadge } from "../lib/tone";
import { computeFactors, getSymbolNews, getWatchlist, listPortfolios, saveWatchlist } from "../lib/api";
import type { FactorResult, SymbolNews, WatchItem } from "../lib/api";
import type { PortfolioData } from "../lib/types";
import { ago } from "../lib/newsStore";
import { baseSymbol, factorExchange, factorTicker } from "../lib/symbols";
import { tradingViewUrl } from "../lib/tradingview";
import { quoteKey, useMarketFeed } from "../lib/useMarketFeed";

/** A short human reason; the backend's own wording is kept unless it is about a missing market. */
function plain(e: unknown, missing: string): string {
  const m = e instanceof Error ? e.message : "";
  return /does not have market|no .*data|not found/i.test(m) ? missing : m || missing;
}

const money = (v: number, d = 2) => v.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
const signed = (v: number, d = 2) => `${v >= 0 ? "+" : ""}${v.toFixed(d)}`;

interface Position {
  portfolio: string;
  quantity: number;
  average: number;
}

/**
 * One symbol, everything in one place: the live chart, factor read, the news and its tone, and
 * what you hold. Nothing here is new data; it is the rest of the app, pivoted on a symbol.
 */
export default function SymbolDetail() {
  const { exchange = "NSE", symbol = "" } = useParams<{ exchange: string; symbol: string }>();
  const ticker = symbol.toUpperCase();
  const base = baseSymbol(ticker);

  const { quotes } = useMarketFeed();
  const quote = quotes[quoteKey(ticker, exchange)] ?? quotes[quoteKey(ticker, exchange.toUpperCase())];

  const [watch, setWatch] = useState<WatchItem[] | null>(null);
  const [factors, setFactors] = useState<FactorResult | null>(null);
  const [factorErr, setFactorErr] = useState<string | null>(null);
  const [news, setNews] = useState<SymbolNews | null>(null);
  const [newsErr, setNewsErr] = useState<string | null>(null);
  const [portfolios, setPortfolios] = useState<PortfolioData[]>([]);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  // Reload everything when the symbol changes; each part fails on its own, never the whole page.
  useEffect(() => {
    let live = true;
    setFactors(null);
    setFactorErr(null);
    setNews(null);
    setNewsErr(null);
    computeFactors(factorTicker(ticker, exchange), factorExchange(exchange))
      .then((f) => live && setFactors(f))
      .catch((e: unknown) => live && setFactorErr(plain(e, `No market data to read factors for ${ticker}.`)));
    const loadNews = () =>
      getSymbolNews(ticker)
        .then((n) => live && (setNews(n), setNewsErr(null)))
        .catch((e: unknown) => live && setNewsErr(e instanceof Error ? e.message : "News unavailable"));
    void loadNews();
    getWatchlist().then((w) => live && setWatch(w.items)).catch(() => live && setWatch(null));
    listPortfolios().then((p) => live && setPortfolios(p.portfolios)).catch(() => undefined);
    const poll = window.setInterval(() => {
      void loadNews();
      setNow(Date.now());
    }, 30_000);
    return () => {
      live = false;
      window.clearInterval(poll);
    };
  }, [ticker, exchange]);

  const onWatchlist = !!watch?.some((w) => w.symbol.toUpperCase() === ticker && w.exchange.toUpperCase() === exchange.toUpperCase());

  async function toggleWatch() {
    if (!watch) return;
    setBusy(true);
    try {
      const next = onWatchlist
        ? watch.filter((w) => !(w.symbol.toUpperCase() === ticker && w.exchange.toUpperCase() === exchange.toUpperCase()))
        : [...watch, { symbol: ticker, exchange: exchange.toUpperCase() }];
      const saved = await saveWatchlist(next);
      setWatch(saved.items);
    } finally {
      setBusy(false);
    }
  }

  const positions: Position[] = useMemo(
    () =>
      portfolios.flatMap((p) =>
        p.holdings.filter((h) => baseSymbol(h.symbol) === base).map((h) => ({ portfolio: p.name, quantity: h.quantity, average: h.average_price })),
      ),
    [portfolios, base],
  );

  const price = quote?.close ?? null;
  const move = quote?.change_pct ?? (quote?.close != null && quote?.open ? ((quote.close - quote.open) / quote.open) * 100 : null);
  const composite = factors?.composite;
  const totalQty = positions.reduce((s, p) => s + p.quantity, 0);
  const invested = positions.reduce((s, p) => s + p.quantity * p.average, 0);
  const value = price != null ? totalQty * price : null;
  const pnl = value != null ? value - invested : null;

  const radar = useMemo(
    () => Object.entries(factors?.factors ?? {}).map(([name, f]) => ({ name, normalized: Number.isFinite(f.normalized) ? f.normalized : 0 })),
    [factors],
  );

  return (
    <>
      <TopBar title={ticker} />
      <div className="page-shell">
        <section className="sym-head card">
          <div className="sym-id">
            <h2 className="sym-name">{ticker}</h2>
            <span className="chip-static">{exchange.toUpperCase()}</span>
            {news?.state && <span className={`badge ${BADGE[news.state]}`}>{news.state}</span>}
          </div>
          <div className="sym-price">
            <span className="sym-last">{price != null ? <Flap text={money(price)} /> : "–"}</span>
            {move != null && (
              <span className={`sym-move ${move >= 0 ? "up" : "down"}`}>
                {move > 0 ? <ArrowUpRight size={18} /> : move < 0 ? <ArrowDownRight size={18} /> : <Minus size={18} />}
                {signed(move)}%
              </span>
            )}
            {price == null && <span className="sym-note">Not on your live feed yet. Add it to the watchlist to stream it.</span>}
          </div>
          <div className="sym-actions">
            <button type="button" className={`btn ${onWatchlist ? "btn-secondary" : "btn-primary"}`} onClick={() => void toggleWatch()} disabled={busy || watch === null}>
              {onWatchlist ? <Check size={15} /> : <Plus size={15} />}
              {onWatchlist ? "On watchlist" : "Add to watchlist"}
            </button>
            <a className="btn btn-secondary" href={tradingViewUrl(ticker, exchange)} target="_blank" rel="noopener noreferrer">
              TradingView <ExternalLink size={13} />
            </a>
          </div>
        </section>

        <div className="card" style={{ marginBottom: "var(--space-5)" }}>
          <PriceChart key={`${exchange}:${ticker}`} symbol={ticker} exchange={exchange.toUpperCase()} quote={quote} height={400} />
        </div>

        <div className="grid-3" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card">
            <div className="card-header">
              <div className="card-title">Factor read</div>
              {composite && <span className={`badge ${toneBadge(composite.signal)}`}>{composite.signal}</span>}
            </div>
            {factors ? (
              <FactorRadar factors={radar} height={250} />
            ) : factorErr ? (
              <p className="sym-note">{factorErr}</p>
            ) : (
              <div className="skeleton" style={{ height: 250 }} aria-busy="true" />
            )}
            {composite && (
              <p className="sym-note" style={{ marginTop: "var(--space-2)" }}>
                Composite {composite.composite_score.toFixed(3)} · {composite.factor_count} factors · research signal, not advice
              </p>
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <div className="card-title">News tone</div>
              <span className="pulse-window">last 24h</span>
            </div>
            {news ? (
              <>
                <Gauge3D value={news.tone.mentions ? (news.tone.score + 1) / 2 : null} />
                <div className="gauge-read">
                  <span className={`mood-word ${news.tone.label}`}>{news.tone.mentions ? news.tone.label : "no news"}</span>
                  <span className="departure-value">
                    <Flap text={news.tone.mentions ? signed(news.tone.score) : "—"} />
                  </span>
                </div>
                <p className="sym-note" style={{ textAlign: "center" }}>
                  {news.tone.bullish}↑ {news.tone.bearish}↓ {news.tone.neutral}· across {news.tone.mentions} headlines
                </p>
              </>
            ) : newsErr ? (
              <p className="sym-note">{newsErr}</p>
            ) : (
              <div className="skeleton" style={{ height: 250 }} aria-busy="true" />
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <div className="card-title">Your position</div>
              {positions.length > 0 && <span className="pulse-window">{positions.length} portfolio{positions.length > 1 ? "s" : ""}</span>}
            </div>
            {positions.length > 0 ? (
              <>
                <div className="sym-pos-total">
                  <span className="stat-label" style={{ marginTop: 0 }}>Unrealized P&L</span>
                  <span className={`stat-value ${pnl != null ? (pnl >= 0 ? "pos" : "neg") : ""}`}>
                    {pnl != null ? `${pnl >= 0 ? "+" : "-"}₹${money(Math.abs(pnl), 0)}` : "–"}
                  </span>
                  {pnl != null && invested > 0 && <span className="sym-note">{signed((pnl / invested) * 100)}% on ₹{money(invested, 0)} invested</span>}
                </div>
                <ul className="sym-pos-list">
                  {positions.map((p) => (
                    <li key={p.portfolio}>
                      <span>{p.portfolio}</span>
                      <span>
                        {p.quantity} @ ₹{money(p.average)}
                      </span>
                    </li>
                  ))}
                </ul>
                {price == null && <p className="sym-note">Add it to the watchlist to price this position live.</p>}
              </>
            ) : (
              <div className="empty-state">
                <div className="empty-state-title">Not held</div>
                <div className="empty-state-text">
                  {ticker} is not in any saved portfolio. <SafeLink to="/portfolio">Open Portfolio</SafeLink> to add it.
                </div>
              </div>
            )}
          </div>
        </div>

        {news && news.alerts.length > 0 && (
          <div className="card" style={{ marginBottom: "var(--space-5)" }}>
            <div className="card-header">
              <div className="card-title">Sentiment flips</div>
            </div>
            <ul className="flip-list">
              {news.alerts.map((a) => (
                <li key={a.id} className={`flip-row ${a.to}`}>
                  <span className="flip-path">
                    <span className={`badge ${BADGE[a.from]}`}>{a.from}</span>
                    <span aria-hidden="true">→</span>
                    <span className={`badge ${BADGE[a.to]}`}>{a.to}</span>
                  </span>
                  <span className="flip-score">{signed(a.score)}</span>
                  <span className="flip-why">{a.headline?.title ?? ""}</span>
                  <span className="flip-when">{ago(a.t, now)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="card">
          <div className="card-header">
            <div className="card-title">Headlines mentioning {base}</div>
            <span className="pulse-window">from public market feeds</span>
          </div>
          {news ? (
            <NewsList items={news.headlines} now={now} empty={`No recent headlines mention ${base}.`} />
          ) : newsErr ? (
            <p className="sym-note">{newsErr}</p>
          ) : (
            <div className="skeleton" style={{ height: 120 }} aria-busy="true" />
          )}
        </div>
      </div>
    </>
  );
}
