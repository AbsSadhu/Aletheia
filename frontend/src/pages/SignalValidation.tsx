import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import TopBar from "../components/TopBar";
import {
  getLatestSignalBacktest,
  getShadowVsNifty,
  getSignalAccuracy,
  runSignalBacktest,
} from "../lib/api";
import type { PerfBlock, SignalAccuracy, SignalBacktest } from "../lib/api";

const STATUS_COLOR = { PASS: "var(--green)", FAIL: "var(--red)", INCONCLUSIVE: "var(--amber)" };

const pct = (v?: number | null) => (v == null ? "–" : `${v.toFixed(2)}%`);
const num = (v?: number | null, d = 2) => (v == null ? "–" : v.toFixed(d));
const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

function PerfRow({ label, p }: { label: string; p: PerfBlock }) {
  return (
    <tr>
      <td>{label}</td>
      <td>{pct(p.cagr_pct)}</td>
      <td>{pct(p.total_return_pct)}</td>
      <td>{num(p.sharpe)}</td>
      <td>{pct(p.max_drawdown_pct)}</td>
      <td>{pct(p.volatility_pct)}</td>
    </tr>
  );
}

function BacktestSection() {
  const [result, setResult] = useState<SignalBacktest | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [years, setYears] = useState(6);

  useEffect(() => {
    getLatestSignalBacktest()
      .then((r) => setResult(r.result))
      .catch(() => {});
  }, []);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      setResult(await runSignalBacktest({ years }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="card" style={{ marginBottom: "var(--space-5)" }}>
      <div className="card-header">
        <span className="card-title">Does the signal beat just holding Nifty?</span>
        <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center" }}>
          <select
            className="form-control"
            aria-label="Years of history"
            value={years}
            onChange={(e) => setYears(Number(e.target.value))}
          >
            {[3, 5, 6, 8, 10].map((y) => (
              <option key={y} value={y}>
                {y} years
              </option>
            ))}
          </select>
          <button className="btn btn-primary" onClick={() => void run()} disabled={running}>
            {running ? "Running (about a minute)…" : "Run validation"}
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" style={{ color: "var(--red)", marginBottom: "var(--space-3)" }}>
          {error}
        </div>
      )}

      {!result ? (
        <p style={{ color: "var(--text-muted)" }}>
          Walks 25 Nifty large caps forward day by day, acting on the Oracle signal with next-day fills,
          real trading costs and Indian capital-gains tax, and compares the result with holding the
          index and with an equal-weight basket of the same stocks.
        </p>
      ) : (
        <>
          <div
            role="status"
            style={{
              borderLeft: `4px solid ${STATUS_COLOR[result.verdict.status]}`,
              padding: "var(--space-3) var(--space-4)",
              background: "var(--bg-elevated)",
              marginBottom: "var(--space-4)",
            }}
          >
            <strong style={{ color: STATUS_COLOR[result.verdict.status] }}>
              {result.verdict.status}
            </strong>{" "}
            — {result.verdict.headline}
            <ul style={{ margin: "var(--space-2) 0 0 var(--space-4)", color: "var(--text-secondary)" }}>
              {result.verdict.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>
                    {result.period.start} → {result.period.end}
                  </th>
                  <th>CAGR</th>
                  <th>Total</th>
                  <th>Sharpe</th>
                  <th>Max drawdown</th>
                  <th>Volatility</th>
                </tr>
              </thead>
              <tbody>
                <PerfRow label="Signal, after costs & tax" p={result.strategy_post_tax} />
                <PerfRow label="Signal, after costs, before tax" p={result.strategy} />
                <PerfRow label="Nifty 50, buy & hold" p={result.nifty} />
                <PerfRow label="Same stocks, equal-weight buy & hold" p={result.equal_weight} />
                <PerfRow
                  label={`Signal, last 40% (from ${result.out_of_sample.start})`}
                  p={result.out_of_sample.strategy_post_tax}
                />
                <PerfRow label="Nifty, same last 40%" p={result.out_of_sample.nifty} />
              </tbody>
            </table>
          </div>

          <p style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)", margin: "var(--space-3) 0" }}>
            {result.trading.trades} trades · {result.trading.win_rate_pct}% winners · held{" "}
            {result.trading.avg_holding_days} days on average · {result.trading.stopped_out_pct}% stopped
            out · invested {result.trading.avg_invested_pct}% of the time. Trading costs{" "}
            {inr(result.trading.trading_costs_inr)}, tax {inr(result.trading.tax_paid_inr)}. Ended at{" "}
            {inr(result.trading.post_tax_final_equity)} after tax.
          </p>

          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <LineChart data={result.equity_curve}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
                <YAxis
                  tick={{ fontSize: 11 }}
                  domain={["auto", "auto"]}
                  tickFormatter={(v: number) => `₹${(v / 100000).toFixed(0)}L`}
                />
                <Tooltip formatter={(v) => inr(Number(v))} />
                <Legend />
                <Line dataKey="strategy" name="Signal" stroke="var(--accent)" dot={false} strokeWidth={2} />
                <Line dataKey="nifty" name="Nifty" stroke="var(--amber)" dot={false} />
                <Line dataKey="equal_weight" name="Equal-weight" stroke="var(--teal)" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <details style={{ marginTop: "var(--space-3)" }}>
            <summary style={{ cursor: "pointer" }}>What this test can't tell you</summary>
            <ul style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
              {result.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </div>
  );
}

function AccuracySection() {
  const [acc, setAcc] = useState<SignalAccuracy | null>(null);
  const [shadow, setShadow] = useState<Awaited<ReturnType<typeof getShadowVsNifty>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getSignalAccuracy()
      .then(setAcc)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load accuracy"));
    getShadowVsNifty()
      .then(setShadow)
      .catch(() => setShadow(null));
  }, []);
  useEffect(load, [load]);

  if (error) return <div className="card" role="alert" style={{ color: "var(--red)" }}>{error}</div>;
  if (!acc) return <div className="card">Loading…</div>;

  return (
    <>
      <div className="card" style={{ marginBottom: "var(--space-5)" }}>
        <div className="card-header">
          <span className="card-title">Live track record</span>
          <span style={{ color: "var(--text-muted)", fontSize: "var(--text-sm)" }}>
            {acc.resolved} scored · {acc.pending} waiting for their 7-day result
          </span>
        </div>
        <p style={{ color: "var(--text-secondary)" }}>{acc.verdict}</p>

        {acc.overall && (
          <div className="grid-4" style={{ margin: "var(--space-4) 0" }}>
            {[
              ["Hit rate", pct(acc.overall.hit_rate_pct)],
              ["Avg confidence claimed", pct(acc.overall.avg_confidence * 100)],
              ["Brier (coin flip = 0.25)", num(acc.overall.brier, 3)],
              ["Avg 7-day return", pct(acc.overall.avg_return_7d_pct)],
            ].map(([label, value]) => (
              <div key={label} className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="stat-label">{label}</span>
                <span className="stat-value">{value}</span>
              </div>
            ))}
          </div>
        )}

        {acc.calibration.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Confidence band</th>
                  <th>Predictions</th>
                  <th>Claimed</th>
                  <th>Actually right</th>
                </tr>
              </thead>
              <tbody>
                {acc.calibration.map((b) => (
                  <tr key={b.range}>
                    <td>{b.range}</td>
                    <td>{b.n}</td>
                    <td>{pct(b.claimed_pct)}</td>
                    <td>{pct(b.actual_hit_rate_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {Object.keys(acc.by_signal).length > 0 && (
          <div className="table-wrap" style={{ marginTop: "var(--space-4)" }}>
            <table>
              <thead>
                <tr>
                  <th>Signal</th>
                  <th>n</th>
                  <th>Hit rate</th>
                  <th>Avg 7d return</th>
                  <th>Brier</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(acc.by_signal).map(([sig, b]) => (
                  <tr key={sig}>
                    <td>
                      <span className={`badge badge-${sig.toLowerCase()}`}>{sig}</span>
                    </td>
                    <td>{b.n}</td>
                    <td>{pct(b.hit_rate_pct)}</td>
                    <td>{pct(b.avg_return_7d_pct)}</td>
                    <td>{num(b.brier, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Shadow Trader vs Nifty</span>
          {shadow?.excess_pct != null && (
            <span style={{ color: shadow.excess_pct >= 0 ? "var(--green)" : "var(--red)" }}>
              {shadow.excess_pct >= 0 ? "+" : ""}
              {shadow.excess_pct}% vs Nifty over {shadow.days} days
            </span>
          )}
        </div>
        {!shadow || shadow.points.length < 2 ? (
          <p style={{ color: "var(--text-muted)" }}>
            {shadow?.note ?? "Run analyses and let the Shadow Trader trade to build a curve."}
          </p>
        ) : (
          <div style={{ width: "100%", height: 260 }}>
            <ResponsiveContainer>
              <LineChart data={shadow.points}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d: string) => d.slice(0, 10)} minTickGap={40} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `${v}%`} />
                <Tooltip formatter={(v) => `${Number(v).toFixed(2)}%`} />
                <Legend />
                <Line dataKey="shadow_pct" name="Shadow Trader" stroke="var(--accent)" dot={false} strokeWidth={2} />
                <Line dataKey="nifty_pct" name="Nifty" stroke="var(--amber)" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </>
  );
}

export default function SignalValidation() {
  return (
    <>
      <TopBar title="Signal Validation" />
      <div className="page-shell">
        <BacktestSection />
        <AccuracySection />
      </div>
    </>
  );
}
