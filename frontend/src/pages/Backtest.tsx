import { TrendingDown, BarChart3 } from "lucide-react";
import { useMemo, useState } from "react";
import { XCircle } from "lucide-react";
import { Drawdown, LineArea, ReturnsHistogram } from "../components/charts/kit";
import SharpeCheck from "../components/SharpeCheck";

import TopBar from "../components/TopBar";
import PageHero from "../components/PageHero";
import { runBacktest } from "../lib/api";
import type { BacktestResult } from "../lib/types";

export default function Backtest() {
  const [symbols, setSymbols] = useState("RELIANCE.NS,TCS.NS");
  const [startDate, setStartDate] = useState("2023-01-01");
  const [endDate, setEndDate] = useState("2025-06-30");
  const [strategy, setStrategy] = useState("sma_crossover");
  const [initialCapital, setInitialCapital] = useState("100000");
  const [withCosts, setWithCosts] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);

  async function handleRun() {
    const symbolList = symbols
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    const capital = parseFloat(initialCapital);

    if (symbolList.length === 0) {
      setError("Enter at least one symbol");
      return;
    }
    if (!startDate || !endDate) {
      setError("Enter a start and end date");
      return;
    }
    if (isNaN(capital) || capital <= 0) {
      setError("Enter a valid initial capital");
      return;
    }

    try {
      setRunning(true);
      setError(null);
      const data = await runBacktest({
        symbols: symbolList,
        start_date: startDate,
        end_date: endDate,
        strategy: strategy.trim() || undefined,
        initial_capital: capital,
        cost_model: withCosts ? "auto" : "none",
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setRunning(false);
    }
  }

  const steps = useMemo(() => result?.equity_curve.map((p) => String(p.step)) ?? [], [result]);
  const values = useMemo(() => result?.equity_curve.map((p) => Math.round(p.value)) ?? [], [result]);
  const inr = useMemo(() => (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`, []);
  const series = useMemo(() => [{ name: "Equity", data: values, tone: "accent" as const, area: true }], [values]);

  return (
    <>
      <TopBar title="Backtest" onRefresh={() => void handleRun()} loading={running} />
      <div className="page-shell">
        <PageHero variant="steps" headline="Test an idea against history." sub="Pick symbols, dates and a strategy, then read the equity curve, drawdown and every order." />
        {error && (
          <div
            className="card"
            style={{
              background: "var(--red-muted)",
              color: "var(--red)",
              borderColor: "var(--red)",
              marginBottom: "var(--space-5)",
            }}
          >
            <XCircle size={14} style={{ verticalAlign: "-2px", marginRight: 6 }} />{error}
          </div>
        )}

        <div className="card" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card-header">
            <span className="card-title">Run a Backtest</span>
          </div>
          <div className="console-grid">
            <label className="console-field">
              <span className="stat-label">Symbols</span>
              <input className="form-control" placeholder="RELIANCE, TCS" value={symbols} onChange={(e) => setSymbols(e.target.value)} />
            </label>
            <label className="console-field">
              <span className="stat-label">From</span>
              <input className="form-control" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </label>
            <label className="console-field">
              <span className="stat-label">To</span>
              <input className="form-control" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </label>
            <label className="console-field">
              <span className="stat-label">Strategy</span>
              <input className="form-control" placeholder="sma_crossover" value={strategy} onChange={(e) => setStrategy(e.target.value)} />
            </label>
            <label className="console-field">
              <span className="stat-label">Capital (₹)</span>
              <input className="form-control" type="number" placeholder="100000" value={initialCapital} onChange={(e) => setInitialCapital(e.target.value)} />
            </label>
            <label className="console-field costs-toggle">
              <span className="stat-label">Trading costs</span>
              <span className="costs-check">
                <input type="checkbox" checked={withCosts} onChange={(e) => setWithCosts(e.target.checked)} />
                brokerage, taxes, slippage
              </span>
            </label>
            <button className="btn btn-primary console-run" onClick={() => void handleRun()} disabled={running}>
              {running ? "Running..." : "Run Backtest"}
            </button>
          </div>
        </div>

        {!result && !running && (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon"><TrendingDown size={26} strokeWidth={1.5} /></div>
              <div className="empty-state-title">No backtest run yet</div>
              <div className="empty-state-text">
                Configure the symbols, date range, and strategy above, then click "Run Backtest".
              </div>
            </div>
          </div>
        )}

        {result && (
          <>
            {result.metrics.total_trades === 0 && (
              <div className="card note-card" role="status" style={{ marginBottom: "var(--space-4)" }}>
                No trades fired in this window, so capital stayed flat. Try a longer date range, more symbols, or another strategy.
              </div>
            )}
            <div className="grid-4" style={{ marginBottom: "var(--space-5)" }}>
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="stat-label">Total Return</span>
                <span
                  className="stat-value"
                  style={{ color: result.total_return >= 0 ? "var(--green)" : "var(--red)" }}
                >
                  {result.total_return >= 0 ? "+" : ""}
                  {(result.total_return * 100).toFixed(2)}%
                </span>
              </div>
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="stat-label">Final Capital</span>
                <span className="stat-value">
                  ₹{result.final_capital.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                </span>
              </div>
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="stat-label">Sharpe Ratio</span>
                <span className="stat-value" style={{ color: "var(--teal)" }}>
                  {result.metrics.sharpe_ratio.toFixed(2)}
                </span>
              </div>
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="stat-label">Max Drawdown</span>
                <span className="stat-value" style={{ color: "var(--red)" }}>
                  {(result.metrics.max_drawdown * 100).toFixed(2)}%
                </span>
              </div>
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="stat-label">Win Rate</span>
                <span className="stat-value">{(result.metrics.win_rate * 100).toFixed(1)}%</span>
              </div>
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="stat-label">Profit Factor</span>
                <span className="stat-value">{result.metrics.profit_factor == null ? "no losses" : result.metrics.profit_factor.toFixed(2)}</span>
              </div>
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="stat-label">Total Trades</span>
                <span className="stat-value">{result.metrics.total_trades}</span>
              </div>
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="stat-label">Strategy</span>
                <span className="stat-value" style={{ fontSize: "var(--text-lg)" }}>
                  {result.strategy_name}
                </span>
              </div>
            </div>

            <div className="card assumptions" style={{ marginBottom: "var(--space-5)" }}>
              <div className="card-header">
                <span className="card-title">What this run assumed</span>
                {result.data_as_of && <span className="pulse-window">prices through {result.data_as_of}</span>}
              </div>
              <p className="assume-line">
                {result.cost_model
                  ? `Fills include ${result.cost_model.replace("_", " ")} costs (slippage, spread, brokerage and statutory charges, approximate). They took ${inr(result.costs_paid ?? 0)} of ${inr(result.initial_capital)}.`
                  : "No trading costs were applied, so this result is better than a real account would see."}
              </p>
              {(result.warnings ?? []).map((w) => (
                <p key={w} className="assume-warn" role="status">{w}</p>
              ))}
              {(result.segments ?? []).length === 2 && (
                <div className="segment-grid">
                  {result.segments!.map((g) => (
                    <div key={g.label}>
                      <span className="stat-label">{g.label === "earlier" ? "Earlier part" : "Later part"} · {g.bars} bars</span>
                      <b className={g.total_return >= 0 ? "pos" : "neg"}>
                        {g.total_return >= 0 ? "+" : ""}
                        {(g.total_return * 100).toFixed(2)}%
                      </b>
                      <i>
                        drawdown {(g.max_drawdown * 100).toFixed(1)}% · Sharpe {g.sharpe_ratio.toFixed(2)}
                      </i>
                    </div>
                  ))}
                </div>
              )}
              <p className="pulse-note">A strategy that earns in one stretch and gives it back in the other has not shown it works. Past results do not predict future ones.</p>
            </div>

            <div className="card" style={{ marginBottom: "var(--space-5)" }}>
              <div className="card-header">
                <span className="card-title">Equity Curve</span>
              </div>
              <LineArea x={steps} series={series} format={inr} height={320} label="Backtest equity curve" />
            </div>

            {values.length >= 30 && <SharpeCheck equity={values} />}

            <div className="grid-2" style={{ marginBottom: "var(--space-5)" }}>
              <div className="card">
                <div className="card-header">
                  <span className="card-title">Drawdown</span>
                </div>
                <Drawdown x={steps} values={values} label="Backtest drawdown" />
              </div>
              <div className="card">
                <div className="card-header">
                  <span className="card-title">Return distribution</span>
                </div>
                <ReturnsHistogram values={values} label="Distribution of period returns" />
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <span className="card-title">Orders ({result.orders.length})</span>
              </div>
              {result.orders.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-icon"><BarChart3 size={26} strokeWidth={1.5} /></div>
                  <div className="empty-state-title">No orders generated</div>
                </div>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Symbol</th>
                        <th>Type</th>
                        <th>Action</th>
                        <th style={{ textAlign: "right" }}>Quantity</th>
                        <th style={{ textAlign: "right" }}>Filled Price</th>
                        <th>Status</th>
                        <th>Filled At</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.orders.map((o) => (
                        <tr key={o.id}>
                          <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                            {o.symbol}
                          </td>
                          <td>{o.order_type}</td>
                          <td>
                            <span
                              className={`badge ${o.action === "buy" ? "badge-buy" : "badge-reduce"}`}
                            >
                              {o.action.toUpperCase()}
                            </span>
                          </td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                            {o.quantity}
                          </td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                            {o.filled_price != null
                              ? `₹${o.filled_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`
                              : "—"}
                          </td>
                          <td>
                            <span
                              className={`badge ${o.status === "filled" ? "badge-completed" : "badge-pending"}`}
                            >
                              {o.status}
                            </span>
                          </td>
                          <td
                            style={{
                              fontSize: "var(--text-xs)",
                              color: "var(--text-muted)",
                              fontFamily: "var(--font-mono)",
                            }}
                          >
                            {o.filled_at ? new Date(o.filled_at).toLocaleString("en-IN") : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
