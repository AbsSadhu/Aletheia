import { useEffect, useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Minus, RefreshCw } from "lucide-react";

import { LineArea } from "../components/charts/kit";
import Flap from "../components/Flap";
import Gauge3D from "../components/Gauge3D";
import { BADGE, NewsItem } from "../components/NewsList";
import PageHero from "../components/PageHero";
import SafeLink from "../components/SafeLink";
import TopBar from "../components/TopBar";
import { ago, markAlertsRead, refreshNews, useNews } from "../lib/newsStore";
import { resolveTag, symbolPath } from "../lib/symbols";
import type { SentimentLabel } from "../lib/api";

const FILTERS: { id: "all" | SentimentLabel; label: string }[] = [
  { id: "all", label: "All" },
  { id: "bullish", label: "Bullish" },
  { id: "bearish", label: "Bearish" },
  { id: "neutral", label: "Neutral" },
];

const signed = (v: number, d = 2) => `${v >= 0 ? "+" : ""}${v.toFixed(d)}`;

export default function Pulse() {
  const { pulse, headlines, fresh, error, loaded } = useNews();
  const [filter, setFilter] = useState<"all" | SentimentLabel>("all");
  const [now, setNow] = useState(() => Date.now());
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    markAlertsRead();
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 10_000);
    return () => window.clearInterval(id);
  }, []);

  const mood = pulse?.mood;
  const shown = useMemo(() => (filter === "all" ? headlines : headlines.filter((h) => h.label === filter)), [headlines, filter]);

  const histX = useMemo(
    () => (pulse?.history ?? []).map((p) => new Date(p.t).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })),
    [pulse],
  );
  const histSeries = useMemo(() => [{ name: "Mood", data: (pulse?.history ?? []).map((p) => p.v), tone: "accent" as const, area: true }], [pulse]);

  const sourcesUp = pulse ? Object.values(pulse.sources).filter(Boolean).length : 0;
  const sourcesAll = pulse ? Object.keys(pulse.sources).length : 0;

  async function manualRefresh() {
    setRefreshing(true);
    await refreshNews();
    setRefreshing(false);
  }

  return (
    <>
      <TopBar title="Market Pulse" onRefresh={() => void manualRefresh()} loading={refreshing} />
      <div className="page-shell">
        <PageHero
          variant="bars"
          headline="What the market is saying, and why it moved."
          sub="Headlines from public Indian market feeds, scored for tone and matched to your movers. Refreshes on its own."
        />

        {error && !pulse && (
          <div className="card note-card" role="alert" style={{ marginBottom: "var(--space-4)" }}>
            News is unavailable right now: {error}. Check your connection; the rest of the app is unaffected.
          </div>
        )}

        <div className="grid-3" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card">
            <div className="card-header">
              <div className="card-title">Market mood</div>
              <span className="pulse-window">last {mood?.window_hours ?? 6}h</span>
            </div>
            <Gauge3D value={mood ? (mood.value + 1) / 2 : null} warnBelow={0.4} />
            <div className="gauge-read">
              <span className={`mood-word ${mood?.label ?? "neutral"}`}>{mood ? mood.label : "waiting"}</span>
              <span className="departure-value">
                <Flap text={mood ? signed(mood.value) : "—"} />
              </span>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <div className="card-title">Mood over time</div>
              <span className="pulse-window">builds while the app runs</span>
            </div>
            {pulse && pulse.history.length >= 2 ? (
              <LineArea x={histX} series={histSeries} format={(v) => signed(v)} height={210} zoom={false} label="Market mood over time" />
            ) : (
              <div className="empty-state">
                <div className="empty-state-title">Collecting</div>
                <div className="empty-state-text">A line appears after a couple of refreshes.</div>
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <div className="card-title">Tone of the last {mood?.window_hours ?? 6}h</div>
              <button type="button" className="btn btn-ghost" onClick={() => void manualRefresh()} aria-label="Refresh news" disabled={refreshing}>
                <RefreshCw size={14} className={refreshing ? "pulse" : ""} />
              </button>
            </div>
            <div className="tone-split">
              {(["bullish", "neutral", "bearish"] as SentimentLabel[]).map((l) => (
                <div key={l} className={`tone-cell ${l}`}>
                  <span className="stat-label" style={{ marginTop: 0 }}>{l}</span>
                  <span className="tone-n">
                    <Flap text={String(mood?.counts[l] ?? 0)} hold={false} />
                  </span>
                </div>
              ))}
            </div>
            <div className="pulse-sources">
              {pulse &&
                Object.entries(pulse.sources).map(([name, ok]) => (
                  <span key={name} className={`src ${ok ? "up" : "down"}`} title={ok ? "reachable" : "not reachable"}>
                    {name}
                  </span>
                ))}
            </div>
            <p className="pulse-note">
              {sourcesAll > 0 ? `${sourcesUp} of ${sourcesAll} sources answering. ` : ""}
              {pulse?.updated_at ? `Updated ${ago(pulse.updated_at, now)} ago.` : loaded ? "" : "Loading…"}
            </p>
          </div>
        </div>

        <div className="card" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card-header">
            <div className="card-title">Sentiment flips</div>
            <span className="pulse-window">your watchlist · alerts when a symbol&apos;s tone changes</span>
          </div>
          {pulse && pulse.alerts.length > 0 ? (
            <ul className="flip-list">
              {pulse.alerts.map((a) => (
                <li key={a.id} className={`flip-row ${a.to}`}>
                  <span className="flip-sym">{a.symbol}</span>
                  <span className="flip-path">
                    <span className={`badge ${BADGE[a.from]}`}>{a.from}</span>
                    <span aria-hidden="true">→</span>
                    <span className={`badge ${BADGE[a.to]}`}>{a.to}</span>
                  </span>
                  <span className="flip-score">{signed(a.score)}</span>
                  {a.headline ? (
                    <a className="flip-why" href={a.headline.url} target="_blank" rel="noopener noreferrer">
                      {a.headline.title}
                    </a>
                  ) : (
                    <span className="flip-why" />
                  )}
                  <span className="flip-when">{ago(a.t, now)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">
              <div className="empty-state-title">No flips yet</div>
              <div className="empty-state-text">
                You are alerted when a watchlist symbol turns bullish, bearish or neutral, with at least two headlines behind it.
                Add symbols on Live Market. Alerts reset when the app restarts.
              </div>
            </div>
          )}
        </div>

        <div className="card" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card-header">
            <div className="card-title">Movers and what was reported</div>
            <span className="pulse-window">from your live quotes</span>
          </div>
          {pulse && pulse.movers.length > 0 ? (
            <div className="mover-grid">
              {pulse.movers.map((m) => {
                const top = m.drivers[0];
                return (
                  <article className={`mover ${m.direction}`} key={`${m.symbol}-${m.exchange}`}>
                    <header>
                      <SafeLink to={symbolPath(m.symbol, m.exchange ?? "NSE")} className="mover-sym">{m.symbol}</SafeLink>
                      <span className="mover-chg">
                        {m.direction === "up" ? <ArrowUpRight size={18} /> : m.direction === "down" ? <ArrowDownRight size={18} /> : <Minus size={18} />}
                        {signed(m.change_pct)}%
                      </span>
                    </header>
                    {top ? (
                      <>
                        <a className="mover-reason" href={top.url} target="_blank" rel="noopener noreferrer">
                          {top.title}
                        </a>
                        <div className="mover-foot">
                          <span className={`badge ${BADGE[top.label]}`}>{top.label}</span>
                          <span>{top.source} · {ago(top.published, now)}</span>
                          <span className={`aligned ${top.aligned ? "yes" : "no"}`}>{top.aligned ? "tone matches the move" : "tone differs from the move"}</span>
                        </div>
                      </>
                    ) : (
                      <p className="mover-none">No headline mentioning {m.symbol} yet.</p>
                    )}
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-state-title">No quotes to match yet</div>
              <div className="empty-state-text">Add symbols on Live Market. Movers appear here with the headlines published about them.</div>
            </div>
          )}
          <p className="pulse-note" style={{ marginTop: "var(--space-3)" }}>
            Headlines are shown alongside a move, not as proof of what caused it.
          </p>
        </div>

        <div className="pulse-split">
          <div className="card">
            <div className="card-header">
              <div className="card-title">Sentiment tracker</div>
              <span className="pulse-window">last 24h · tone per symbol</span>
            </div>
            {pulse && pulse.tracker.length > 0 ? (
              <ul className="tracker">
                {pulse.tracker.map((r) => (
                  <li key={r.symbol} className="track-row">
                    <span className="track-sym">
                      <SafeLink to={symbolPath(resolveTag(r.symbol).symbol, resolveTag(r.symbol).exchange)}>{r.symbol}</SafeLink>
                      {r.watched && <i className="track-watch" title="on your watchlist" />}
                    </span>
                    <span className="track-bar" role="img" aria-label={`${r.label}, score ${signed(r.score)}`}>
                      <i className="track-mid" />
                      <i
                        className={`track-fill ${r.score >= 0 ? "up" : "down"}`}
                        style={{ width: `${Math.min(50, Math.abs(r.score) * 50)}%`, [r.score >= 0 ? "left" : "right"]: "50%" }}
                      />
                    </span>
                    <span className="track-score">{r.mentions ? signed(r.score) : "–"}</span>
                    <span className="track-count" title="bullish / bearish / neutral headlines">
                      {r.mentions ? `${r.bullish}↑ ${r.bearish}↓ ${r.neutral}·` : "no news"}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="empty-state">
                <div className="empty-state-title">Nothing tracked yet</div>
                <div className="empty-state-text">Symbols from your watchlist and in the headlines show up here.</div>
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <div className="card-title">Headline stream</div>
              <div className="chip-row" role="group" aria-label="Filter by tone">
                {FILTERS.map((f) => (
                  <button key={f.id} type="button" className={`chip${filter === f.id ? " on" : ""}`} aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
            {shown.length > 0 ? (
              <ul className="news-list">
                {shown.slice(0, 50).map((h) => (
                  <NewsItem key={h.id} h={h} fresh={fresh.has(h.id)} now={now} />
                ))}
              </ul>
            ) : (
              <div className="empty-state">
                <div className="empty-state-title">{loaded ? "No headlines" : "Loading headlines"}</div>
                <div className="empty-state-text">{loaded ? "Nothing matches this filter right now." : "Reaching the news feeds."}</div>
              </div>
            )}
          </div>
        </div>

        <p className="pulse-note" style={{ marginTop: "var(--space-4)" }}>
          {pulse?.method ?? "Lexicon-scored headlines."} Not financial advice.
        </p>
      </div>
    </>
  );
}
