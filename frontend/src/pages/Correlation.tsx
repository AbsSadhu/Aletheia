import { useCallback, useEffect, useState } from "react";

import Flap from "../components/Flap";
import { CorrelationMatrix } from "../components/charts/Matrix";
import RegimeChart from "../components/charts/RegimeChart";
import PageHero from "../components/PageHero";
import TopBar from "../components/TopBar";
import { getCorrelationRegime } from "../lib/api";
import type { CorrelationRegime } from "../lib/api";

const HEAVYWEIGHTS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT", "BHARTIARTL", "KOTAKBANK"];
type Source = "basket" | "watchlist" | "custom";

/** "INFY, tcs, BTC/USDT" -> "NSE:INFY,NSE:TCS,BINANCE:BTC/USDT". */
function toQuery(raw: string): string {
  return raw
    .split(/[,\s]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
    .map((s) => (s.includes(":") ? s : s.includes("/") ? `BINANCE:${s}` : `NSE:${s}`))
    .join(",");
}

export default function Correlation() {
  const [source, setSource] = useState<Source>("basket");
  const [custom, setCustom] = useState("RELIANCE, TCS, INFY, ITC, SBIN, BTC/USDT");
  const [days, setDays] = useState(180);
  const [windowBars, setWindowBars] = useState(60);
  const [data, setData] = useState<CorrelationRegime | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const symbols = source === "basket" ? toQuery(HEAVYWEIGHTS.join(",")) : source === "custom" ? toQuery(custom) : undefined;
      setData(await getCorrelationRegime({ symbols, days, corrWindow: windowBars }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not compute correlations.");
    } finally {
      setLoading(false);
    }
    // the source/custom text are read when Run is pressed, not on every keystroke
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, days, windowBars]);

  useEffect(() => {
    void run();
    // first load only: the controls below re-run on demand
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cur = data?.current;
  const fused = cur?.state === "FUSED";

  return (
    <>
      <TopBar title="Correlation" onRefresh={() => void run()} loading={loading} />
      <div className="page-shell">
        <PageHero
          variant="ripple"
          headline="Know when your stocks start moving as one."
          sub="When most pairs of assets move together, diversification has thinned. This watches for that, with a regime that does not flicker."
        />

        <div className="card" style={{ marginBottom: "var(--space-5)" }}>
          <div className="corr-controls">
            <div className="chip-row" role="group" aria-label="Which symbols">
              {(
                [
                  ["basket", "Nifty heavyweights"],
                  ["watchlist", "My watchlist"],
                  ["custom", "Custom"],
                ] as [Source, string][]
              ).map(([id, label]) => (
                <button key={id} type="button" className={`chip${source === id ? " on" : ""}`} aria-pressed={source === id} onClick={() => setSource(id)}>
                  {label}
                </button>
              ))}
            </div>
            {source === "custom" && (
              <input className="form-control" style={{ flex: 1, minWidth: 260, fontFamily: "var(--font-mono)" }} aria-label="Symbols" value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="INFY, TCS, BTC/USDT" />
            )}
            <label className="console-field" style={{ width: 120 }}>
              <span className="stat-label">Timeline</span>
              <select className="form-control" value={days} onChange={(e) => setDays(Number(e.target.value))}>
                <option value={90}>90 days</option>
                <option value={180}>180 days</option>
                <option value={365}>1 year</option>
              </select>
            </label>
            <label className="console-field" style={{ width: 130 }}>
              <span className="stat-label">Window</span>
              <select className="form-control" value={windowBars} onChange={(e) => setWindowBars(Number(e.target.value))}>
                <option value={40}>40 days</option>
                <option value={60}>60 days</option>
                <option value={90}>90 days</option>
              </select>
            </label>
            <button type="button" className="btn btn-primary" onClick={() => void run()} disabled={loading}>
              {loading ? "Working…" : "Run"}
            </button>
          </div>
          {error && (
            <p className="journal-error" role="alert">
              {error}
            </p>
          )}
        </div>

        {loading && !data && <div className="skeleton" style={{ height: 320 }} aria-busy="true" />}

        {data && cur && (
          <>
            <div className="grid-3" style={{ marginBottom: "var(--space-5)" }}>
              <div className={`card regime-card ${fused ? "fused" : "normal"}`}>
                <span className="stat-label">Right now</span>
                <span className="regime-state">{cur.state}</span>
                <p className="regime-explain">
                  {fused
                    ? "Most pairs are moving together. Holdings that looked diversified are behaving like one bet."
                    : "Assets are mostly moving on their own. Diversification is doing its job."}
                </p>
              </div>
              <div className="card">
                <span className="stat-label">Pairs moving together</span>
                <span className="stat-value">
                  <Flap text={cur.smoothed_density != null ? `${Math.round(cur.smoothed_density * 100)}%` : "—"} hold={false} />
                </span>
                <span className="sym-note">share of pairs with |correlation| of {data.params.edge_threshold} or more, smoothed over {data.params.smooth_window} days</span>
              </div>
              <div className="card">
                <span className="stat-label">Average correlation</span>
                <span className="stat-value">{cur.average_correlation != null ? cur.average_correlation.toFixed(2) : "–"}</span>
                <span className="sym-note">
                  over the last {data.params.corr_window} days, {data.labels.length} assets
                </span>
              </div>
            </div>

            <div className="card" style={{ marginBottom: "var(--space-5)" }}>
              <div className="card-header">
                <div className="card-title">Regime over time</div>
                <span className="pulse-window">shaded = fused</span>
              </div>
              <RegimeChart dates={data.dates} smoothed={data.smoothed} fused={data.fused} enter={data.params.enter_threshold} exit={data.params.exit_threshold} />
              <p className="pulse-note" style={{ marginTop: "var(--space-2)" }}>
                A fused stretch begins when the smoothed share reaches {Math.round(data.params.enter_threshold * 100)}% and ends only when it falls to {Math.round(data.params.exit_threshold * 100)}%. The gap between the two stops it flickering.
              </p>
            </div>

            <div className="pulse-split" style={{ marginBottom: "var(--space-5)" }}>
              <div className="card">
                <div className="card-header">
                  <div className="card-title">Correlation matrix</div>
                  <span className="pulse-window">last {data.params.corr_window} days</span>
                </div>
                <CorrelationMatrix labels={data.labels} matrix={data.matrix} />
                <div className="legend-row" aria-hidden="true">
                  <span><i style={{ background: "var(--green)" }} /> moves apart</span>
                  <span><i style={{ background: "var(--border-medium)" }} /> unrelated</span>
                  <span><i style={{ background: "var(--amber)" }} /> some link</span>
                  <span><i style={{ background: "var(--accent-2)" }} /> strong</span>
                  <span><i style={{ background: "var(--accent)" }} /> near identical</span>
                </div>
              </div>
              <div className="card">
                <div className="card-header">
                  <div className="card-title">Pairs and episodes</div>
                </div>
                <h4 className="mini-h">Most alike</h4>
                <ul className="pair-list">
                  {data.most_correlated.map((p) => (
                    <li key={`${p.a}-${p.b}`}>
                      <span>{p.a} / {p.b}</span>
                      <b>{p.corr.toFixed(2)}</b>
                    </li>
                  ))}
                </ul>
                <h4 className="mini-h">Most independent</h4>
                <ul className="pair-list">
                  {data.least_correlated.map((p) => (
                    <li key={`${p.a}-${p.b}`}>
                      <span>{p.a} / {p.b}</span>
                      <b>{p.corr.toFixed(2)}</b>
                    </li>
                  ))}
                </ul>
                <h4 className="mini-h">Fused episodes in this window</h4>
                {data.episodes.length > 0 ? (
                  <ul className="pair-list">
                    {data.episodes.map((e) => (
                      <li key={e.start}>
                        <span>{e.start}</span>
                        <b>{e.end ? `to ${e.end}` : "ongoing"}</b>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="pulse-note">None in this window.</p>
                )}
                {data.unavailable.length > 0 && <p className="pulse-note" style={{ marginTop: "var(--space-3)" }}>No price history for: {data.unavailable.join(", ")}.</p>}
              </div>
            </div>
            <p className="pulse-note">Descriptive risk context from daily returns, not a signal. Correlations shift, and a calm stretch can end without warning.</p>
          </>
        )}
      </div>
    </>
  );
}
