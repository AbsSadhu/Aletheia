import { useEffect, useState } from "react";
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
import {
  getShadowPositions,
  getShadowOrders,
  getShadowPerformance,
  submitShadowOrder,
} from "../lib/api";
import type { VirtualPosition, ShadowOrder, ShadowSnapshot } from "../lib/api";

export default function ShadowTrader() {
  const [positions, setPositions] = useState<VirtualPosition[]>([]);
  const [orders, setOrders] = useState<ShadowOrder[]>([]);
  const [curve, setCurve] = useState<ShadowSnapshot[]>([]);
  const [latest, setLatest] = useState<ShadowSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [symbol, setSymbol] = useState("RELIANCE");
  const [exchange, setExchange] = useState("NSE");
  const [action, setAction] = useState<"buy" | "sell">("buy");
  const [quantity, setQuantity] = useState("1");

  async function loadData() {
    try {
      const [posData, orderData, perfData] = await Promise.all([
        getShadowPositions(),
        getShadowOrders(100),
        getShadowPerformance(200),
      ]);
      setPositions(posData.positions);
      setOrders(orderData.orders);
      setCurve(perfData.equity_curve);
      setLatest(perfData.latest);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load shadow account data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
    const interval = setInterval(() => void loadData(), 15_000);
    return () => clearInterval(interval);
  }, []);

  const handleSubmit = async () => {
    const qty = parseFloat(quantity);
    if (isNaN(qty) || qty <= 0) {
      alert("Enter a valid quantity");
      return;
    }
    try {
      setSubmitting(true);
      await submitShadowOrder(symbol.trim().toUpperCase(), exchange, action, qty);
      await loadData();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to submit virtual order");
    } finally {
      setSubmitting(false);
    }
  };

  const chartData = curve.map((s) => ({
    time: new Date(s.timestamp).toLocaleTimeString("en-IN"),
    equity: Math.round(s.total_equity),
  }));

  const totalUnrealized = positions.reduce((sum, p) => sum + p.unrealized_pnl, 0);

  return (
    <>
      <TopBar title="Shadow Trader" onRefresh={() => void loadData()} loading={loading} />
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

        <div className="grid-4" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="stat-label">Total Equity</span>
            <span className="stat-value" style={{ color: "var(--accent)" }}>
              ₹{(latest?.total_equity ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
            </span>
          </div>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="stat-label">Cash Balance</span>
            <span className="stat-value" style={{ color: "var(--teal)" }}>
              ₹{(latest?.cash_balance ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
            </span>
          </div>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="stat-label">Unrealized P&L</span>
            <span
              className="stat-value"
              style={{ color: totalUnrealized >= 0 ? "var(--green)" : "var(--red)" }}
            >
              {totalUnrealized >= 0 ? "+" : ""}₹
              {totalUnrealized.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
            </span>
          </div>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="stat-label">Open Positions</span>
            <span className="stat-value" style={{ color: "var(--accent)" }}>
              {positions.length}
            </span>
          </div>
        </div>

        <div className="card" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card-header">
            <span className="card-title">Virtual Equity Curve</span>
          </div>
          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="shadowEquity" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="var(--accent)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                <YAxis
                  tick={{ fontSize: 11 }}
                  domain={["auto", "auto"]}
                  tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip formatter={(v) => `₹${Number(v).toLocaleString("en-IN")}`} />
                <Area
                  type="monotone"
                  dataKey="equity"
                  stroke="var(--accent)"
                  fill="url(#shadowEquity)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          {chartData.length === 0 && (
            <div className="empty-state">
              <div className="empty-state-icon">📈</div>
              <div className="empty-state-title">No equity history yet</div>
              <div className="empty-state-text">
                Submit a virtual order below to start tracking equity.
              </div>
            </div>
          )}
        </div>

        <div className="card" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card-header">
            <span className="card-title">Submit Virtual Order</span>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input
              className="form-control"
              style={{ width: 140 }}
              placeholder="Symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
            />
            <select
              className="form-control"
              style={{ width: 150 }}
              value={exchange}
              onChange={(e) => setExchange(e.target.value)}
            >
              <option value="NSE">NSE (India)</option>
              <option value="BSE">BSE (India)</option>
              <option value="NASDAQ">NASDAQ (US)</option>
              <option value="NYSE">NYSE (US)</option>
              <option value="BINANCE">Binance (Crypto)</option>
            </select>
            <select
              className="form-control"
              style={{ width: 100 }}
              value={action}
              onChange={(e) => setAction(e.target.value as "buy" | "sell")}
            >
              <option value="buy">BUY</option>
              <option value="sell">SELL</option>
            </select>
            <input
              className="form-control"
              type="number"
              style={{ width: 100 }}
              placeholder="Qty"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
            <button className="btn btn-primary" onClick={() => void handleSubmit()} disabled={submitting}>
              {submitting ? "..." : "Execute"}
            </button>
          </div>
        </div>

        <div className="card" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card-header">
            <span className="card-title">Open Positions ({positions.length})</span>
          </div>
          {positions.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📂</div>
              <div className="empty-state-title">No open virtual positions</div>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th style={{ textAlign: "right" }}>Quantity</th>
                    <th style={{ textAlign: "right" }}>Avg Price</th>
                    <th style={{ textAlign: "right" }}>Current Price</th>
                    <th style={{ textAlign: "right" }}>Unrealized P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.symbol}>
                      <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{p.symbol}</td>
                      <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{p.quantity}</td>
                      <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                        ₹{p.average_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </td>
                      <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                        ₹{p.current_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </td>
                      <td
                        style={{
                          textAlign: "right",
                          fontFamily: "var(--font-mono)",
                          fontWeight: 600,
                          color:
                            p.unrealized_pnl > 0
                              ? "var(--green)"
                              : p.unrealized_pnl < 0
                                ? "var(--red)"
                                : "var(--text-muted)",
                        }}
                      >
                        {p.unrealized_pnl > 0 ? "+" : ""}₹
                        {p.unrealized_pnl.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Virtual Order History ({orders.length})</span>
          </div>
          {orders.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📊</div>
              <div className="empty-state-title">No virtual orders yet</div>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Action</th>
                    <th style={{ textAlign: "right" }}>Quantity</th>
                    <th style={{ textAlign: "right" }}>Price</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => (
                    <tr key={o.id}>
                      <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{o.symbol}</td>
                      <td>
                        <span className={`badge ${o.action === "buy" ? "badge-buy" : "badge-reduce"}`}>
                          {o.action.toUpperCase()}
                        </span>
                      </td>
                      <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{o.quantity}</td>
                      <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                        ₹{o.price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </td>
                      <td style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        {new Date(o.timestamp).toLocaleString("en-IN")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
