import { useState } from "react";
import TopBar from "../components/TopBar";
import { priceOption } from "../lib/api";
import type { OptionPrice } from "../lib/api";

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

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
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
          <div className="card">
            <div className="card-title" style={{ marginBottom: "var(--space-3)" }}>
              Black-Scholes · European {result.kind}
            </div>
            <table className="data-table">
              <tbody>
                {rows.map(([label, value]) => (
                  <tr key={label}>
                    <td>{label}</td>
                    <td style={{ fontFamily: "var(--font-mono)", textAlign: "right" }}>{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={{ color: "var(--text-muted)", fontSize: "var(--text-sm)", marginTop: "var(--space-3)" }}>
              Theoretical value for a European option with no dividends. NSE index options are
              European; stock options settle physically. Use the market-implied volatility, not a guess.
            </p>
          </div>
        )}
      </div>
    </>
  );
}
