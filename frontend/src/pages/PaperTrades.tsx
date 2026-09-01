import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, Minus, Cpu } from "lucide-react";
import TopBar from "../components/TopBar";
import { listPaperTrades, getPaperPositions, settlePaperTrade } from "../lib/api";
import type { PaperTrade, PaperPosition } from "../lib/api";

export default function PaperTrades() {
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"history" | "positions">("history");
  
  // Settle form state
  const [settlePriceInput, setSettlePriceInput] = useState<Record<string, string>>({});
  const [settlingId, setSettlingId] = useState<string | null>(null);

  async function loadData() {
    try {
      const [tradesData, positionsData] = await Promise.all([
        listPaperTrades(100),
        getPaperPositions(),
      ]);
      setTrades(tradesData.trades);
      setPositions(positionsData.positions);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load paper trading data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
    const interval = setInterval(() => void loadData(), 15_000);
    return () => clearInterval(interval);
  }, []);

  const handleSettle = async (tradeId: string) => {
    const priceStr = settlePriceInput[tradeId];
    if (!priceStr) return;
    const price = parseFloat(priceStr);
    if (isNaN(price) || price <= 0) {
      alert("Please enter a valid actual close price.");
      return;
    }

    try {
      setSettlingId(tradeId);
      await settlePaperTrade(tradeId, price);
      // Clear input
      setSettlePriceInput((prev) => {
        const copy = { ...prev };
        delete copy[tradeId];
        return copy;
      });
      await loadData();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to settle trade");
    } finally {
      setSettlingId(null);
    }
  };

  const totalPnL = trades.filter(t => t.side === "SELL").reduce((s, t) => s + t.simulated_pnl, 0);
  const wins = trades.filter(t => t.side === "SELL" && t.simulated_pnl > 0).length;
  const losses = trades.filter(t => t.side === "SELL" && t.simulated_pnl < 0).length;
  const winRate = wins + losses > 0 ? (wins / (wins + losses)) * 100 : 0;

  return (
    <>
      <TopBar title="Paper Trading Dashboard" onRefresh={() => void loadData()} loading={loading} />
      <div className="page-shell">
        {error && (
          <div className="card" style={{ background: "var(--red-muted)", color: "var(--red)", borderColor: "var(--red)", marginBottom: "var(--space-5)" }}>
            ❌ {error}
          </div>
        )}

        {/* Summary Stats Grid */}
        <div className="grid-4" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="stat-label">Total Realized P&L</span>
            <span className="stat-value" style={{ color: totalPnL >= 0 ? "var(--green)" : "var(--red)" }}>
              ₹{totalPnL >= 0 ? "+" : ""}{totalPnL.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="stat-label">Total Trade Executions</span>
            <span className="stat-value" style={{ color: "var(--accent)" }}>{trades.length}</span>
          </div>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="stat-label">Win Rate</span>
            <span className="stat-value" style={{ color: winRate >= 50 ? "var(--green)" : "var(--amber)" }}>
              {winRate.toFixed(1)}%
            </span>
            <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 4 }}>
              {wins} Wins / {losses} Losses
            </span>
          </div>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="stat-label">Open Positions</span>
            <span className="stat-value" style={{ color: "var(--teal)" }}>{positions.length}</span>
          </div>
        </div>

        {/* Tabs */}
        <div className="tabs">
          <button
            className={`tab ${activeTab === "history" ? "active" : ""}`}
            onClick={() => setActiveTab("history")}
          >
            Trade History ({trades.length})
          </button>
          <button
            className={`tab ${activeTab === "positions" ? "active" : ""}`}
            onClick={() => setActiveTab("positions")}
          >
            Open Positions ({positions.length})
          </button>
        </div>

        {/* Trade History */}
        {activeTab === "history" && (
          <div className="card">
            {trades.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">📊</div>
                <div className="empty-state-title">No paper trades recorded</div>
                <div className="empty-state-text">
                  Trade signals will populate here automatically once you run portfolio analyses and Sage issues tax-aware recommendations.
                </div>
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th style={{ textAlign: "right" }}>Quantity</th>
                      <th style={{ textAlign: "right" }}>Fill Price</th>
                      <th style={{ textAlign: "right" }}>Actual Close</th>
                      <th style={{ textAlign: "right" }}>P&L</th>
                      <th>Status</th>
                      <th>Time</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((trade) => {
                      const pnl = trade.simulated_pnl;
                      const isPending = trade.status === "pending";
                      return (
                        <tr key={trade.trade_id}>
                          <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text-primary)" }}>
                            {trade.symbol}
                          </td>
                          <td>
                            <span className={`badge ${trade.side === "BUY" ? "badge-buy" : "badge-reduce"}`}>
                              {trade.side}
                            </span>
                          </td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                            {trade.simulated_qty}
                          </td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                            ₹{trade.simulated_fill_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                            {trade.actual_close != null ? `₹${trade.actual_close.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "—"}
                          </td>
                          <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 600, color: pnl > 0 ? "var(--green)" : pnl < 0 ? "var(--red)" : "var(--text-muted)" }}>
                            {pnl !== 0 ? `${pnl > 0 ? "+" : ""}₹${pnl.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "—"}
                          </td>
                          <td>
                            <span className={`badge ${trade.status === "settled" ? "badge-completed" : "badge-running"}`}>
                              {trade.status}
                            </span>
                          </td>
                          <td style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                            {new Date(trade.timestamp).toLocaleString("en-IN")}
                          </td>
                          <td>
                            {isPending && (
                              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                                <input
                                  type="number"
                                  placeholder="Close Price"
                                  value={settlePriceInput[trade.trade_id] || ""}
                                  onChange={(e) => setSettlePriceInput(prev => ({ ...prev, [trade.trade_id]: e.target.value }))}
                                  className="form-control"
                                  style={{
                                    width: 100,
                                    padding: "4px 8px",
                                    fontSize: 12,
                                    height: 28
                                  }}
                                />
                                <button
                                  className="btn btn-primary btn-sm"
                                  onClick={() => void handleSettle(trade.trade_id)}
                                  disabled={settlingId === trade.trade_id}
                                  style={{ fontSize: 11, padding: "4px 8px" }}
                                >
                                  {settlingId === trade.trade_id ? "..." : "Settle"}
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Open Positions */}
        {activeTab === "positions" && (
          <div className="card">
            {positions.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">📂</div>
                <div className="empty-state-title">No open positions</div>
                <div className="empty-state-text">
                  Any filled paper buy orders will display here as active open positions until settled with a sell/closing trade.
                </div>
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Exchange</th>
                      <th style={{ textAlign: "right" }}>Quantity</th>
                      <th style={{ textAlign: "right" }}>Avg Price</th>
                      <th style={{ textAlign: "right" }}>Realized P&L</th>
                      <th>Last Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((pos) => (
                      <tr key={`${pos.symbol}-${pos.exchange}`}>
                        <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text-primary)" }}>
                          {pos.symbol}
                        </td>
                        <td>
                          <span className="badge badge-pending" style={{ fontSize: 10 }}>{pos.exchange}</span>
                        </td>
                        <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                          {pos.quantity}
                        </td>
                        <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                          ₹{pos.average_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 600, color: pos.realized_pnl > 0 ? "var(--green)" : pos.realized_pnl < 0 ? "var(--red)" : "var(--text-muted)" }}>
                          {pos.realized_pnl > 0 ? "+" : ""}₹{pos.realized_pnl.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                          {new Date(pos.updated_at).toLocaleDateString("en-IN")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
