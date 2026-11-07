import { useCallback, useMemo, useRef, useState } from "react";
import { AlertTriangle, FileSpreadsheet, FlaskConical, Upload } from "lucide-react";

import { Bars } from "../components/charts/Bars";
import { LineArea } from "../components/charts/kit";
import PageHero from "../components/PageHero";
import SafeLink from "../components/SafeLink";
import TopBar from "../components/TopBar";
import { analyzeJournal, analyzeSampleJournal } from "../lib/api";
import type { BehaviorCheck, JournalAnalysis, Severity } from "../lib/api";
import { symbolPath } from "../lib/symbols";

const inr = (v: number, digits = 0) => `${v < 0 ? "-" : ""}₹${Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
const signedInr = (v: number) => `${v >= 0 ? "+" : "-"}₹${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const pct = (v: number, d = 1) => `${(v * 100).toFixed(d)}%`;
const day = (iso: string) => iso.slice(0, 10);

const SEV_BADGE: Record<Severity, string> = { high: "badge-reduce", medium: "badge-hold", low: "badge-pending" };
const CHECKS: { key: keyof JournalAnalysis["behavior"]; title: string; question: string }[] = [
  { key: "disposition_effect", title: "Hold times", question: "Do you hold losing trades longer than winning ones?" },
  { key: "overtrading", title: "Busy days", question: "Do your most active days earn less than your quietest?" },
  { key: "chasing_momentum", title: "Run-ups", question: "Do you buy after a price has already climbed?" },
  { key: "anchoring", title: "Repeated prices", question: "Do you keep trading the same price area?" },
];
const CATEGORY: Record<string, { label: string; note: string }> = {
  intraday: { label: "Intraday", note: "bought and sold the same day" },
  short_term: { label: "Short-term", note: "held up to 12 months" },
  long_term: { label: "Long-term", note: "held over 12 months" },
};

function metricLine(c: BehaviorCheck): string | null {
  const pairs: [string, string][] = [];
  if (typeof c.ratio_loss_to_win_hold === "number") pairs.push(["loser/winner hold", `${c.ratio_loss_to_win_hold}x`]);
  if (typeof c.busy_day_avg_pnl === "number" && typeof c.quiet_day_avg_pnl === "number") pairs.push(["busy vs quiet day", `${signedInr(c.busy_day_avg_pnl)} vs ${signedInr(c.quiet_day_avg_pnl)}`]);
  if (typeof c.chase_ratio === "number") pairs.push(["buys after a run-up", pct(c.chase_ratio, 0)]);
  if (typeof c.anchored_symbol_ratio === "number") pairs.push(["symbols in a tight band", pct(c.anchored_symbol_ratio, 0)]);
  return pairs.length ? pairs.map(([k, v]) => `${k}: ${v}`).join(" · ") : null;
}

export default function Journal() {
  const [result, setResult] = useState<JournalAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const run = useCallback(async (work: () => Promise<JournalAnalysis>) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await work());
      setShowAll(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The journal could not be read.");
    } finally {
      setBusy(false);
    }
  }, []);

  const onFile = (file: File | undefined) => file && void run(() => analyzeJournal(file));

  const p = result?.profile;
  const curveX = useMemo(() => (p?.pnl_curve ?? []).map((c) => day(c.t)), [p]);
  const curveSeries = useMemo(() => [{ name: "Cumulative P&L", data: (p?.pnl_curve ?? []).map((c) => c.v), tone: "accent" as const, area: true }], [p]);
  const monthly = useMemo(() => (p?.monthly_pnl ?? []).map((m) => ({ label: m.month, value: m.pnl })), [p]);
  const hours = useMemo(
    () =>
      Object.entries(p?.entries_by_hour ?? {})
        .map(([h, c]) => ({ label: `${String(h).padStart(2, "0")}h`, value: c }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    [p],
  );

  return (
    <>
      <TopBar title="Trade Journal" />
      <div className="page-shell">
        <PageHero
          variant="wave"
          headline="See how you actually trade."
          sub="Drop a broker export and read your own habits: how long you hold losers, whether busy days cost you, whether you chase. It is read in memory and never stored."
        />

        <div className="card" style={{ marginBottom: "var(--space-5)" }}>
          <div
            className={`dropzone${drag ? " over" : ""}${busy ? " busy" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              onFile(e.dataTransfer.files?.[0]);
            }}
          >
            <Upload size={26} strokeWidth={1.5} aria-hidden="true" />
            <div className="dz-copy">
              <b>{busy ? "Reading your journal…" : "Drop your tradebook here"}</b>
              <span>Zerodha tradebook works as it is. For other brokers, a CSV or Excel sheet with symbol, buy/sell, quantity, price and a date.</span>
            </div>
            <div className="dz-actions">
              <input ref={input} type="file" accept=".csv,.xlsx,.xlsm,.txt" hidden onChange={(e) => onFile(e.target.files?.[0])} aria-label="Choose a tradebook file" />
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => input.current?.click()}>
                <FileSpreadsheet size={15} /> Choose file
              </button>
              <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => void run(analyzeSampleJournal)}>
                <FlaskConical size={15} /> Try sample data
              </button>
            </div>
          </div>
          {error && (
            <p className="journal-error" role="alert">
              <AlertTriangle size={14} aria-hidden="true" /> {error}
            </p>
          )}
        </div>

        {result && p && (
          <>
            <div className="journal-file">
              <span className="chip-static">{result.file.name}</span>
              <span>{result.file.format} format</span>
              <span>
                {result.file.rows_used.toLocaleString("en-IN")} trades{result.file.rows_skipped ? `, ${result.file.rows_skipped} rows skipped` : ""}
              </span>
              <span>
                {result.file.date_range[0]} to {result.file.date_range[1]}
              </span>
              {result.synthetic && <span className="badge badge-hold">synthetic sample, not your data</span>}
            </div>

            <div className="card" style={{ marginBottom: "var(--space-5)" }}>
              <div className="card-header">
                <div className="card-title">What stands out</div>
                <span className="pulse-window">checks on this file only</span>
              </div>
              {result.findings.length > 0 ? (
                <ul className="finding-list">
                  {result.findings.map((f) => (
                    <li key={f.key}>
                      <span className={`badge ${SEV_BADGE[f.severity]}`}>{f.severity}</span>
                      <div>
                        <b>{f.title}</b>
                        <p>{f.evidence}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="empty-state">
                  <div className="empty-state-title">Nothing stands out</div>
                  <div className="empty-state-text">None of the four checks reached medium on this file. That is a finding too.</div>
                </div>
              )}
            </div>

            {p.note && <div className="card note-card" style={{ marginBottom: "var(--space-4)" }}>{p.note}</div>}

            {p.total_pnl !== undefined && (
              <>
                <div className="grid-4" style={{ marginBottom: "var(--space-4)" }}>
                  <div className="card">
                    <span className="stat-label">Net P&L (closed trades)</span>
                    <span className={`stat-value ${p.total_pnl >= 0 ? "pos" : "neg"}`}>{signedInr(p.total_pnl)}</span>
                  </div>
                  <div className="card">
                    <span className="stat-label">Win rate</span>
                    <span className="stat-value">{pct(p.win_rate ?? 0)}</span>
                    <span className="sym-note">{p.closed_round_trips} round trips</span>
                  </div>
                  <div className="card">
                    <span className="stat-label">Profit factor</span>
                    <span className="stat-value">{p.profit_factor ?? "–"}</span>
                    <span className="sym-note">gross wins / gross losses</span>
                  </div>
                  <div className="card">
                    <span className="stat-label">Expectancy per trade</span>
                    <span className={`stat-value ${(p.expectancy ?? 0) >= 0 ? "pos" : "neg"}`}>{signedInr(p.expectancy ?? 0)}</span>
                  </div>
                </div>
                <div className="grid-4" style={{ marginBottom: "var(--space-5)" }}>
                  <div className="card">
                    <span className="stat-label">Average hold</span>
                    <span className="stat-value">{p.avg_hold_days}d</span>
                  </div>
                  <div className="card">
                    <span className="stat-label">Max drawdown</span>
                    <span className="stat-value neg">{inr(p.max_drawdown ?? 0)}</span>
                    <span className="sym-note">on cumulative P&L</span>
                  </div>
                  <div className="card">
                    <span className="stat-label">Fees paid</span>
                    <span className="stat-value">{inr(p.fees_paid ?? 0)}</span>
                  </div>
                  <div className="card">
                    <span className="stat-label">Realized XIRR</span>
                    <span className="stat-value">{p.xirr.value != null ? pct(p.xirr.value) : "–"}</span>
                    <span className="sym-note">{p.xirr.note}</span>
                  </div>
                </div>

                <div className="grid-2" style={{ marginBottom: "var(--space-5)" }}>
                  <div className="card">
                    <div className="card-header">
                      <div className="card-title">Cumulative P&L</div>
                      <span className="pulse-window">by exit date</span>
                    </div>
                    <LineArea x={curveX} series={curveSeries} format={(v) => inr(v)} height={260} zoom={false} label="Cumulative profit and loss of closed trades" />
                  </div>
                  <div className="card">
                    <div className="card-header">
                      <div className="card-title">P&L by month</div>
                    </div>
                    <Bars items={monthly} signed format={(v) => inr(v)} height={260} label="Profit and loss per month" />
                  </div>
                </div>
              </>
            )}

            <div className="behavior-grid" style={{ marginBottom: "var(--space-5)" }}>
              {CHECKS.map((c) => {
                const b = result.behavior[c.key];
                const line = metricLine(b);
                return (
                  <article className={`card behavior sev-${b.severity}`} key={c.key}>
                    <header>
                      <h3>{c.title}</h3>
                      <span className={`badge ${SEV_BADGE[b.severity]}`}>{b.severity}</span>
                    </header>
                    <p className="behavior-q">{c.question}</p>
                    <p className="behavior-ev">{b.evidence}</p>
                    {line && <p className="behavior-metric">{line}</p>}
                  </article>
                );
              })}
            </div>

            {p.by_category && (
              <div className="grid-2" style={{ marginBottom: "var(--space-5)" }}>
                <div className="card">
                  <div className="card-header">
                    <div className="card-title">By holding period</div>
                  </div>
                  <ul className="cat-list">
                    {Object.entries(p.by_category).map(([k, v]) => (
                      <li key={k}>
                        <span>
                          <b>{CATEGORY[k]?.label ?? k}</b>
                          <i>{CATEGORY[k]?.note}</i>
                        </span>
                        <span className="cat-num">{v.trips} trips</span>
                        <span className="cat-num">{pct(v.win_rate, 0)} won</span>
                        <span className={`cat-num ${v.pnl >= 0 ? "pos" : "neg"}`}>{signedInr(v.pnl)}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="pulse-note" style={{ marginTop: "var(--space-3)" }}>
                    Sorted by holding period only, to help you see where your gains came from. Tax treatment depends on current rules and your situation. This is not tax advice.
                  </p>
                </div>
                <div className="card">
                  <div className="card-header">
                    <div className="card-title">When you enter</div>
                    <span className="pulse-window">trades by hour, as stamped in the file</span>
                  </div>
                  <Bars items={hours} height={220} label="Number of entries by hour of day" />
                </div>
              </div>
            )}

            {p.by_symbol && p.by_symbol.length > 0 && (
              <div className="card" style={{ marginBottom: "var(--space-5)" }}>
                <div className="card-header">
                  <div className="card-title">By symbol</div>
                  <span className="pulse-window">best to worst</span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Symbol</th>
                        <th style={{ textAlign: "right" }}>Round trips</th>
                        <th style={{ textAlign: "right" }}>Win rate</th>
                        <th style={{ textAlign: "right" }}>P&L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {p.by_symbol.map((s) => (
                        <tr key={s.symbol}>
                          <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                            <SafeLink to={symbolPath(s.symbol, "NSE")} className="sym-link">
                              {s.symbol}
                            </SafeLink>
                          </td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{s.trips}</td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{pct(s.win_rate, 0)}</td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", color: s.pnl >= 0 ? "var(--green)" : "var(--red)" }}>{signedInr(s.pnl)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {p.open_positions.length > 0 && (
              <div className="card" style={{ marginBottom: "var(--space-5)" }}>
                <div className="card-header">
                  <div className="card-title">Still open in this file</div>
                  <span className="pulse-window">bought or sold short, not yet closed</span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Symbol</th>
                        <th>Side</th>
                        <th style={{ textAlign: "right" }}>Quantity</th>
                        <th style={{ textAlign: "right" }}>Average price</th>
                        <th>Since</th>
                      </tr>
                    </thead>
                    <tbody>
                      {p.open_positions.map((o) => (
                        <tr key={`${o.symbol}-${o.direction}`}>
                          <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{o.symbol}</td>
                          <td>{o.direction}</td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{o.quantity}</td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{inr(o.average_price, 2)}</td>
                          <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>{day(o.since)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {result.round_trips.length > 0 && (
              <div className="card" style={{ marginBottom: "var(--space-5)" }}>
                <div className="card-header">
                  <div className="card-title">Round trips</div>
                  <span className="pulse-window">most recent first</span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Symbol</th>
                        <th>Side</th>
                        <th>Opened</th>
                        <th>Closed</th>
                        <th style={{ textAlign: "right" }}>Qty</th>
                        <th style={{ textAlign: "right" }}>In</th>
                        <th style={{ textAlign: "right" }}>Out</th>
                        <th style={{ textAlign: "right" }}>Held</th>
                        <th style={{ textAlign: "right" }}>P&L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.round_trips.slice(0, showAll ? 200 : 25).map((t, i) => (
                        <tr key={`${t.symbol}-${t.exit_dt}-${i}`}>
                          <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{t.symbol}</td>
                          <td>{t.direction}</td>
                          <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>{day(t.entry_dt)}</td>
                          <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>{day(t.exit_dt)}</td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{t.qty}</td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{t.entry_price.toFixed(2)}</td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{t.exit_price.toFixed(2)}</td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{t.hold_days < 1 ? "same day" : `${t.hold_days.toFixed(1)}d`}</td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", color: t.pnl >= 0 ? "var(--green)" : "var(--red)" }}>{signedInr(t.pnl)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {result.round_trips.length > 25 && (
                  <button type="button" className="btn btn-secondary" style={{ marginTop: "var(--space-3)" }} onClick={() => setShowAll((v) => !v)}>
                    {showAll ? "Show fewer" : `Show up to ${Math.min(200, result.round_trips.length)}`}
                  </button>
                )}
              </div>
            )}

            <p className="pulse-note">{result.method}</p>
          </>
        )}
      </div>
    </>
  );
}
