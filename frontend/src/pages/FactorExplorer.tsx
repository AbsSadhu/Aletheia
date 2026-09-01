import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, Minus, Cpu } from "lucide-react";
import TopBar from "../components/TopBar";
import { computeFactors } from "../lib/api";
import type { FactorResult, FactorOutput } from "../lib/api";

const CATEGORY_LABELS: Record<string, string> = {
  momentum: "📈 Momentum Factors",
  mean_reversion: "🔄 Mean Reversion Factors",
  volume: "📊 Volume Factors",
  technicals: "📐 Technical Indicators",
};

export default function FactorExplorer() {
  const [ticker, setTicker] = useState("RELIANCE");
  const [exchange, setExchange] = useState("NSE");
  const [result, setResult] = useState<FactorResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!ticker.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await computeFactors(ticker.trim().toUpperCase(), exchange);
      setResult(data);
      setSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to compute factors");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  // Group factors by category
  const byCategory = result
    ? Object.entries(result.factors).reduce(
        (acc, [name, factor]) => {
          const cat = factor.category;
          if (!acc[cat]) acc[cat] = [];
          acc[cat].push({ ...factor, name });
          return acc;
        },
        {} as Record<string, (FactorOutput & { name: string })[]>
      )
    : {};

  const composite = result?.composite;

  return (
    <>
      <TopBar title="Factor Explorer" />
      <div className="page-shell">
        <form onSubmit={handleSearch} className="card" style={{ display: "flex", gap: "var(--space-4)", alignItems: "flex-end", marginBottom: "var(--space-5)" }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
            <label className="stat-label">Ticker Symbol</label>
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="e.g. RELIANCE, AAPL, BTC-USD"
              className="form-control"
              style={{ width: "100%", textTransform: "uppercase", fontFamily: "var(--font-mono)" }}
            />
          </div>
          <div style={{ width: 150, display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
            <label className="stat-label">Exchange</label>
            <select
              value={exchange}
              onChange={(e) => setExchange(e.target.value)}
              className="form-control"
              style={{ width: "100%" }}
            >
              <option value="NSE">NSE</option>
              <option value="BSE">BSE</option>
              <option value="crypto">Crypto</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary"
            style={{ height: 38, padding: "0 var(--space-5)" }}
          >
            {loading ? (
              <>
                <div className="spinner" style={{ width: 14, height: 14, marginRight: 6 }} />
                Analyzing...
              </>
            ) : (
              "Compute Factors"
            )}
          </button>
        </form>

        {error && (
          <div className="card" style={{ background: "var(--red-muted)", color: "var(--red)", borderColor: "var(--red)", marginBottom: "var(--space-5)" }}>
            ❌ {error}
          </div>
        )}

        {!searched && !loading && (
          <div className="card" style={{ textAlign: "center", padding: "var(--space-12) var(--space-6)" }}>
            <p style={{ fontSize: "var(--text-3xl)", marginBottom: "var(--space-3)" }}>🔬</p>
            <h3 style={{ fontSize: "var(--text-lg)", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "var(--space-2)" }}>
              Alpha Factor Intelligence
            </h3>
            <p style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)", maxWidth: "450px", margin: "0 auto" }}>
              Enter a stock symbol to compute real-time alpha factors including RSI, MACD crossovers, Bollinger Bands, and volume anomalies. Supports both Indian equities and global crypto assets.
            </p>
          </div>
        )}

        {result && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
            {/* Composite Signal Banner */}
            {composite && (
              <div className="card" style={{ borderLeft: `4px solid ${composite.signal === "BUY" ? "var(--green)" : composite.signal === "SELL" ? "var(--red)" : "var(--amber)"}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div className="stat-label">COMPOSITE ANALYSIS</div>
                  <h2 style={{ fontSize: "var(--text-xl)", fontWeight: 700, display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                    {result.ticker} <span style={{ fontSize: "var(--text-sm)", fontWeight: 400, color: "var(--text-muted)" }}>({result.exchange})</span>
                  </h2>
                  <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 4 }}>
                    Based on past {result.bars} daily bars · {new Date(result.from).toLocaleDateString()} to {new Date(result.to).toLocaleDateString()}
                  </div>
                </div>

                <div style={{ textAlign: "right" }}>
                  <span className={`badge ${composite.signal === "BUY" ? "badge-buy" : composite.signal === "SELL" ? "badge-reduce" : "badge-hold"}`} style={{ fontSize: "var(--text-sm)", padding: "6px 16px", fontWeight: 700 }}>
                    {composite.signal === "BUY" && <TrendingUp size={14} style={{ marginRight: 6 }} />}
                    {composite.signal === "SELL" && <TrendingDown size={14} style={{ marginRight: 6 }} />}
                    {composite.signal === "HOLD" && <Minus size={14} style={{ marginRight: 6 }} />}
                    {composite.signal}
                  </span>
                  <div style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginTop: 6 }}>
                    Composite Score: <strong style={{ fontFamily: "var(--font-mono)" }}>{composite.composite_score.toFixed(3)}</strong>
                  </div>
                  <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                    Confidence: <strong>{((composite.confidence ?? 0) * 100).toFixed(0)}%</strong>
                  </div>
                </div>
              </div>
            )}

            {/* Factor Cards by Category */}
            {Object.entries(byCategory).map(([category, factors]) => (
              <div key={category} style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                <h3 className="card-subtitle">{CATEGORY_LABELS[category] ?? category}</h3>
                <div className="grid-3">
                  {factors.map((factor) => {
                    return (
                      <div key={factor.name} className="card" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", fontWeight: 600, textTransform: "uppercase", color: "var(--text-secondary)" }}>
                            {factor.name.replace(/_/g, " ")}
                          </span>
                          <span className={`badge ${factor.signal === "BUY" ? "badge-buy" : factor.signal === "SELL" ? "badge-reduce" : "badge-hold"}`}>
                            {factor.signal}
                          </span>
                        </div>

                        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                          <div style={{ fontSize: "var(--text-2xl)", fontWeight: 700, fontFamily: "var(--font-mono)", color: factor.signal === "BUY" ? "var(--green)" : factor.signal === "SELL" ? "var(--red)" : "var(--text-primary)" }}>
                            {isNaN(factor.value) ? "N/A" : factor.value.toFixed(2)}
                          </div>
                          <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                            conf {Math.round(factor.confidence * 100)}%
                          </div>
                        </div>

                        {/* Normalized bar indicator */}
                        <div>
                          <div className="confidence-bar">
                            <div
                              className="confidence-bar-fill"
                              style={{
                                width: `${Math.min(100, factor.normalized * 100)}%`,
                                background: factor.signal === "BUY" ? "var(--green)" : factor.signal === "SELL" ? "var(--red)" : "var(--text-secondary)",
                              }}
                            />
                          </div>
                        </div>

                        <p style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                          {factor.description}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
