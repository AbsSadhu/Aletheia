import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { LineArea } from "../components/charts/kit";
import TopBar from "../components/TopBar";
import PageHero from "../components/PageHero";
import { getOptionSurface, priceOption } from "../lib/api";
import { payoffCurve } from "../lib/bs";
import { METRICS } from "../lib/surface";
import "../styles/chart.css";
import type { SurfaceData, SurfaceMetric } from "../lib/surface";
import type { OptionPrice } from "../lib/api";

// three.js is heavy; the 3D view loads only once there is a price to show.
const Surface3D = lazy(() => import("../components/Surface3D"));

export default function Options() {
  const [form, setForm] = useState({
    spot: "100",
    strike: "100",
    days: "30",
    vol_pct: "25",
    rate_pct: "7",
    kind: "call" as "call" | "put",
  });
  const [result, setResult] = useState<OptionPrice | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<SurfaceMetric>("price");
  const [surface, setSurface] = useState<SurfaceData | null>(null);
  const [surfaceError, setSurfaceError] = useState<string | null>(null);
  // The inputs the current result was priced with, so the 3D view and its marker stay in step.
  const [priced, setPriced] = useState<typeof form | null>(null);

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setPriced(form);
      setResult(
        await priceOption({
          spot: Number(form.spot),
          strike: Number(form.strike),
          days: Number(form.days),
          vol_pct: Number(form.vol_pct),
          rate_pct: Number(form.rate_pct),
          kind: form.kind,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pricing failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  // Refresh the 3D surface whenever a price is computed or the metric changes.
  useEffect(() => {
    if (!priced) return;
    let live = true;
    setSurfaceError(null);
    getOptionSurface({
      spot: Number(priced.spot),
      strike: Number(priced.strike),
      vol_pct: Number(priced.vol_pct),
      rate_pct: Number(priced.rate_pct),
      kind: priced.kind,
      metric,
      max_days: Math.max(30, Math.ceil(Number(priced.days) * 1.5)),
    })
      .then((s) => live && setSurface(s))
      .catch((e: unknown) => live && setSurfaceError(e instanceof Error ? e.message : "Surface failed"));
    return () => {
      live = false;
    };
  }, [priced, metric]);

  const field = (label: string, key: keyof typeof form, step = "any") => (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
      <label className="stat-label" htmlFor={`opt-${key}`}>{label}</label>
      <input
        id={`opt-${key}`}
        className="form-control"
        type="number"
        step={step}
        value={form[key]}
        onChange={set(key)}
        style={{ fontFamily: "var(--font-mono)" }}
      />
    </div>
  );

  // Profit and loss of the option across spot: at expiry, and priced today by the same closed form.
  const payoff = useMemo(
    () =>
      result && priced
        ? payoffCurve({
            strike: Number(priced.strike),
            days: Number(priced.days),
            volPct: Number(priced.vol_pct),
            ratePct: Number(priced.rate_pct),
            kind: priced.kind,
            premium: result.price,
          })
        : [],
    [result, priced],
  );
  const payoffX = useMemo(() => payoff.map((p) => p.spot.toFixed(0)), [payoff]);
  const payoffSeries = useMemo(
    () => [
      { name: "At expiry", data: payoff.map((p) => Number(p.expiry.toFixed(2))), tone: "accent" as const, area: true },
      { name: "Today (theory)", data: payoff.map((p) => Number(p.today.toFixed(2))), tone: "orange" as const },
    ],
    [payoff],
  );
  const breakeven =
    result && priced ? (priced.kind === "call" ? Number(priced.strike) + result.price : Number(priced.strike) - result.price) : null;

  const rows: [string, string | undefined][] = result
    ? [
        ["Premium (₹)", result.price.toFixed(2)],
        ["Intrinsic (₹)", result.intrinsic.toFixed(2)],
        ["Delta", result.delta.toFixed(4)],
        ["Gamma", result.gamma.toFixed(6)],
        ["Theta / day (₹)", result.theta_per_day.toFixed(4)],
        ["Vega / vol point (₹)", result.vega_per_vol_point.toFixed(4)],
      ]
    : [];

  return (
    <>
      <TopBar title="Options Pricing" />
      <div className="page-shell">
        <PageHero variant="ripple" headline="See how an option moves before you place it." sub="Price it, read the Greeks, then watch the payoff and the 3D surface respond." />
        <form
          onSubmit={handleSubmit}
          className="card"
          style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "var(--space-4)", alignItems: "end", marginBottom: "var(--space-5)" }}
        >
          {field("Spot (₹)", "spot")}
          {field("Strike (₹)", "strike")}
          {field("Days to expiry", "days", "1")}
          {field("Implied vol (%)", "vol_pct")}
          {field("Risk-free rate (%)", "rate_pct")}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
            <label className="stat-label" htmlFor="opt-kind">Type</label>
            <select id="opt-kind" className="form-control" value={form.kind} onChange={set("kind")}>
              <option value="call">Call</option>
              <option value="put">Put</option>
            </select>
          </div>
          <button className="btn btn-primary" type="submit" disabled={loading}>
            {loading ? "Pricing…" : "Price"}
          </button>
        </form>

        {error && <div className="card" role="alert" style={{ color: "var(--red)" }}>{error}</div>}

        {result && (
          <>
            <div className="card-title" style={{ marginBottom: "var(--space-3)" }}>
              Black-Scholes · European {result.kind}
            </div>
            <div className="grid-3" style={{ marginBottom: "var(--space-3)" }}>
              {rows.map(([label, value]) => (
                <div className="card" key={label}>
                  <div className="stat-label" style={{ marginTop: 0 }}>{label}</div>
                  <div className="stat-value">{value}</div>
                </div>
              ))}
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "var(--text-sm)", marginBottom: "var(--space-5)" }}>
              Theoretical value for a European option with no dividends. NSE index options are
              European; stock options settle physically. Use the market-implied volatility, not a guess.
            </p>

            {payoff.length > 0 && (
              <div className="card" style={{ marginBottom: "var(--space-5)" }}>
                <div className="card-header">
                  <div className="card-title">Payoff · long {result.kind}</div>
                  {breakeven != null && (
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
                      break-even at expiry ₹{breakeven.toFixed(2)}
                    </span>
                  )}
                </div>
                <LineArea
                  x={payoffX}
                  series={payoffSeries}
                  format={(v) => `₹${v.toFixed(0)}`}
                  height={280}
                  zoom={false}
                  label="Profit and loss of the option across spot prices, at expiry and today"
                />
              </div>
            )}
          </>
        )}

        {result && priced && (
          <div className="card" style={{ marginTop: "var(--space-5)" }}>
            <div className="card-header">
              <div className="card-title">Surface · {metric} across spot and expiry</div>
              <div role="group" aria-label="Surface metric" className="pc-intervals">
                {METRICS.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    title={m.hint}
                    className={m.id === metric ? "active" : ""}
                    aria-pressed={m.id === metric}
                    onClick={() => setMetric(m.id)}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
            {surfaceError && <p role="alert" style={{ color: "var(--red)" }}>{surfaceError}</p>}
            {surface && !surfaceError && (
              <Suspense fallback={<div className="surface3d-fallback">Loading 3D view…</div>}>
                <Surface3D data={surface} marker={{ spot: Number(priced.spot), days: Number(priced.days) }} />
              </Suspense>
            )}
            <p style={{ color: "var(--text-muted)", fontSize: "var(--text-sm)", marginTop: "var(--space-3)" }}>
              The marker is the option you just priced; the faint plane is the strike. Same
              Black-Scholes pricer as the numbers above, sampled across a grid.
            </p>
          </div>
        )}
      </div>
    </>
  );
}
