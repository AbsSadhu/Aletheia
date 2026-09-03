import { useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

import TopBar from "../components/TopBar";
import { runBacktest } from "../lib/api";
import type { BacktestResult } from "../lib/types";

export default function Backtest() {
  const [symbols, setSymbols] = useState("RELIANCE,TCS");
  const [startDate, setStartDate] = useState("2025-01-01");
  const [endDate, setEndDate] = useState("2025-06-30");
  const [strategy, setStrategy] = useState("oracle_signals");
  const [initialCapital, setInitialCapital] = useState("100000");
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
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setRunning(false);
    }
  }

  const chartData = result?.equity_curve.map((p) => ({
    step: p.step,
    value: Math.round(p.value),
  })) ?? [];

  return (
    <>
      <TopBar title="Backtest" onRefresh={() => void handleRun()} loading={running} />
      <div className="page-shell">
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
            ❌ {error}
          </div>
        )}

        <div className="card" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card-header">
            <span className="card-title">Run a Backtest</span>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input
              className="form-control"
              style={{ width: 220 }}
              placeholder="Symbols (comma-separated)"
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
            />
            <input
              className="form-control"
              type="date"
              style={{ width: 160 }}
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
            <input
              className="form-control"
              type="date"
              style={{ width: 160 }}
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
            <input
              className="form-control"
              style={{ width: 160 }}
              placeholder="Strategy"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
            />
            <input
              className="form-control"
              type="number"
              style={{ width: 140 }}
              placeholder="Initial Capital"
              value={initialCapital}
              onChange={(e) => setInitialCapital(e.target.value)}
            />
            <button className="btn btn-primary" onClick={() => void handleRun()} disabled={running}>
              {running ? "Running..." : "Run Backtest"}
            </button>
          </div>
        </div>

        {!result && !running && (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon">📉</div>
              <div className="empty-state-title">No backtest run yet</div>
              <div className="empty-state-text">
                Configure the symbols, date range, and strategy above, then click "Run Backtest".
              </div>
            </div>
          </div>
        )}

        {result && (
          <>
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
                <span className="stat-value" style={{ color: "var(--accent)" }}>
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
                <span className="stat-value">{result.metrics.profit_factor.toFixed(2)}</span>
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

            <div className="card" style={{ marginBottom: "var(--space-5)" }}>
              <div className="card-header">
                <span className="card-title">Equity Curve</span>
              </div>
              <div style={{ width: "100%", height: 280 }}>
                <ResponsiveContainer>
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="backtestEquity" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="var(--accent)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="step" tick={{ fontSize: 11 }} />
                    <YAxis
                      tick={{ fontSize: 11 }}
                      domain={["auto", "auto"]}
                      tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`}
                    />
                    <Tooltip formatter={(v) => `₹${Number(v).toLocaleString("en-IN")}`} />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke="var(--accent)"
                      fill="url(#backtestEquity)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <span className="card-title">Orders ({result.orders.length})</span>
              </div>
              {result.orders.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-icon">📊</div>
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
