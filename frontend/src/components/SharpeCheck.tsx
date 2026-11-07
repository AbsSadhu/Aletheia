import { useEffect, useState } from "react";

import { assessSharpe } from "../lib/api";
import type { SharpeAssessment } from "../lib/api";

const fmt = (v: number | null | undefined, d = 2) => (v == null ? "–" : v.toFixed(d));
const pct = (v: number | null | undefined, d = 0) => (v == null ? "–" : `${(v * 100).toFixed(d)}%`);

/**
 * "Is this result real?" for a backtest equity curve: the probability its Sharpe beats zero, and the
 * same after allowing for how many strategies you tried to find it. The trial count is yours to set;
 * nothing else makes a best-of-many result honest.
 */
export default function SharpeCheck({ equity }: { equity: number[] }) {
  const [trials, setTrials] = useState(1);
  const [result, setResult] = useState<SharpeAssessment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    setLoading(true);
    const t = window.setTimeout(() => {
      assessSharpe(equity, Math.max(1, Math.round(trials)))
        .then((r) => live && (setResult(r), setError(null)))
        .catch((e: unknown) => live && (setResult(null), setError(e instanceof Error ? e.message : "Could not assess this curve.")))
        .finally(() => live && setLoading(false));
    }, 350);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [equity, trials]);

  const verdict = result?.verdict;
  return (
    <div className="card sharpe-check" style={{ marginBottom: "var(--space-5)" }}>
      <div className="card-header">
        <div className="card-title">Is this result real?</div>
        <label className="trials-field">
          <span>Strategies tried to find this</span>
          <input className="form-control" type="number" min={1} max={100000} value={trials} onChange={(e) => setTrials(Number(e.target.value) || 1)} aria-label="Strategies tried" />
        </label>
      </div>

      {error && <p className="journal-error" role="status">{error}</p>}
      {result && (
        <>
          {result.verdict_text && <p className={`verdict ${verdict}`}>{result.verdict_text}</p>}
          <div className="sharpe-grid">
            <div>
              <span className="stat-label">Sharpe (annual)</span>
              <b>{fmt(result.sharpe_annualized)}</b>
            </div>
            <div>
              <span className="stat-label">Chance it beats zero</span>
              <b>{pct(result.psr)}</b>
            </div>
            {result.dsr != null && (
              <div>
                <span className="stat-label">After {result.n_trials} tries</span>
                <b>{pct(result.dsr)}</b>
              </div>
            )}
            {result.bar_annualized != null && (
              <div>
                <span className="stat-label">Luck alone reaches</span>
                <b>{fmt(result.bar_annualized)}</b>
              </div>
            )}
            <div>
              <span className="stat-label">Sortino</span>
              <b>{fmt(result.sortino_annualized)}</b>
            </div>
            <div>
              <span className="stat-label">Calmar</span>
              <b>{fmt(result.calmar)}</b>
            </div>
            <div>
              <span className="stat-label">Skew / tails</span>
              <b>
                {fmt(result.skew)} / {fmt(result.kurtosis, 1)}
              </b>
            </div>
            <div>
              <span className="stat-label">History needed</span>
              <b>{result.min_track_record ? (result.min_track_record > 20000 ? "20,000+ bars" : `${result.min_track_record.toLocaleString("en-IN")} bars`) : "–"}</b>
            </div>
          </div>
          <p className="pulse-note">
            {result.observations} bars read as {result.periods_per_year} per year. {result.trial_std_assumed ? "The spread of the other tries is assumed from sampling error, not measured. " : ""}
            Chances are confidence levels from the probabilistic and deflated Sharpe ratio (Bailey and Lopez de Prado), not predictions.
          </p>
        </>
      )}
      {loading && !result && <div className="skeleton" style={{ height: 90 }} aria-busy="true" />}
    </div>
  );
}
