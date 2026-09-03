import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Shield,
  Eye,
  BookOpen,
  Cpu,
  PenTool,
  X,
  Play,
  Briefcase,
} from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

import TopBar from "../components/TopBar";
import { fetchHealth, listRuns, listPortfolios, createRun, getRun } from "../lib/api";
import type { RunResult, RunSummary, HealthData, PortfolioData } from "../lib/types";

const AGENT_META = [
  { key: "collector", label: "Collector", icon: Cpu, className: "collector" },
  { key: "oracle", label: "Oracle", icon: Eye, className: "oracle" },
  { key: "sentinel", label: "Sentinel", icon: Shield, className: "sentinel" },
  { key: "sage", label: "Sage", icon: BookOpen, className: "sage" },
  { key: "scribe", label: "Scribe", icon: PenTool, className: "scribe" },
];

const PIE_COLORS = ["#3b82f6", "#a855f7", "#22c55e", "#f59e0b", "#14b8a6", "#ef4444"];

function agentPipelineState(key: string, run: RunResult | null): { label: string; active: boolean } {
  if (!run) return { label: "Idle", active: false };

  const hasOutput = (() => {
    switch (key) {
      case "collector":
        return run.collector_output.length > 0;
      case "oracle":
        return run.oracle_output.length > 0;
      case "sentinel":
        return run.sentinel_output !== null;
      case "sage":
        return run.sage_output.length > 0;
      case "scribe":
        return run.scribe_output !== null;
      default:
        return false;
    }
  })();

  if (hasOutput) return { label: "Last run: completed", active: true };

  const status = run.summary.status;
  if (status === "running" || status === "pending") return { label: "Last run: in progress", active: true };
  if (status === "failed") return { label: "Last run: failed", active: false };
  // Overall run completed but this agent produced no output - e.g. Sage
  // skipped for a portfolio with no tax jurisdiction set.
  return { label: "Last run: skipped", active: false };
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [health, setHealth] = useState<HealthData | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [portfolios, setPortfolios] = useState<PortfolioData[]>([]);
  const [latestRun, setLatestRun] = useState<RunResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New Analysis Modal State
  const [showModal, setShowModal] = useState(false);
  const [selectedPortName, setSelectedPortName] = useState("");
  const [customPrompt, setCustomPrompt] = useState("");

  async function refresh() {
    try {
      setError(null);
      const [healthData, runsData, portData] = await Promise.all([
        fetchHealth(),
        listRuns(),
        listPortfolios(),
      ]);
      setHealth(healthData);
      setRuns(runsData.runs);
      setPortfolios(portData.portfolios);

      if (portData.portfolios.length > 0 && !selectedPortName) {
        setSelectedPortName(portData.portfolios[0].name);
        setCustomPrompt(`Analyze portfolio ${portData.portfolios[0].name}`);
      }

      // Load the latest completed run's full result
      if (runsData.runs.length > 0) {
        const latest = runsData.runs[0];
        try {
          setLatestRun(await getRun(latest.run_id));
        } catch {
          /* ignore – we still show the dashboard */
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }

  useEffect(() => {
    void refresh();
    const interval = setInterval(() => void refresh(), 15_000);
    return () => clearInterval(interval);
  }, []);

  const handlePortSelect = (name: string) => {
    setSelectedPortName(name);
    setCustomPrompt(`Analyze portfolio ${name}`);
  };

  async function handleStartAnalysis(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedPortName) {
      setError("Please select a portfolio or create one first.");
      return;
    }

    const matchedPort = portfolios.find((p) => p.name === selectedPortName);
    if (!matchedPort) return;

    try {
      setLoading(true);
      setError(null);
      // Create a background run
      const result = await createRun(
        customPrompt || `Analyze portfolio ${selectedPortName}`,
        matchedPort,
        true // background execution
      );
      setShowModal(false);
      // Navigate immediately to the run detail page to watch it live!
      navigate(`/runs/${result.summary.run_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger analysis run");
    } finally {
      setLoading(false);
    }
  }

  // Compute portfolio stats from latest run
  const holdings = latestRun?.collector_output ?? [];
  const totalValue = holdings.reduce((sum, h) => {
    const quote = h.quotes?.[0];
    return sum + (quote ? quote.close * (latestRun?.summary?.prompt ? 1 : 1) : 0);
  }, 0);

  const pieData = holdings.map((h) => ({
    name: h.symbol,
    value: h.quotes?.[0]?.close ?? 0,
  }));

  const recommendations = latestRun?.scribe_output?.recommendations ?? [];
  const sentinelData = latestRun?.sentinel_output;

  return (
    <>
      <TopBar
        title="Dashboard"
        onNewRun={() => setShowModal(true)}
        onRefresh={() => void refresh()}
        loading={loading}
      />
      <div className="page-shell">
        {error && <p style={{ color: "var(--red)", marginBottom: "var(--space-4)" }}>{error}</p>}

        {/* Stat Row */}
        <div className="grid-4" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card">
            <div className="card-subtitle">System Status</div>
            <div className="stat-value" style={{ color: health ? "var(--green)" : "var(--text-muted)" }}>
              {health ? "Online" : "—"}
            </div>
            <div className="stat-label">
              {health ? `v${health.version}` : "Connecting…"}
            </div>
          </div>

          <div className="card">
            <div className="card-subtitle">Total Runs</div>
            <div className="stat-value">{runs.length}</div>
            <div className="stat-label">portfolio analyses</div>
          </div>

          <div className="card">
            <div className="card-subtitle">Agreement Level</div>
            <div className="stat-value">
              {latestRun?.scribe_output?.agreement_level ?? "—"}
            </div>
            <div className="stat-label">latest cross-agent consensus</div>
          </div>

          <div className="card">
            <div className="card-subtitle">Confidence</div>
            <div className="stat-value">{latestRun?.scribe_output ? `${(latestRun.scribe_output.overall_confidence * 100).toFixed(0)}%` : "—"}</div>
            <div className="stat-label">overall score</div>
            {latestRun?.scribe_output && (
              <div className="confidence-bar" style={{ marginTop: 8 }}>
                <div
                  className={`confidence-bar-fill ${
                    latestRun.scribe_output.overall_confidence > 0.65
                      ? "high"
                      : latestRun.scribe_output.overall_confidence > 0.4
                        ? "medium"
                        : "low"
                  }`}
                  style={{ width: `${latestRun.scribe_output.overall_confidence * 100}%` }}
                />
              </div>
            )}
          </div>
        </div>

        <div className="grid-2" style={{ marginBottom: "var(--space-5)" }}>
          {/* Agent Status Cards */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">Agent Pipeline</div>
              {latestRun && (
                <span className={`badge badge-${latestRun.summary.status}`}>
                  {latestRun.summary.status}
                </span>
              )}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              {AGENT_META.map((agent) => {
                const { label, active } = agentPipelineState(agent.key, latestRun);
                return (
                  <div
                    key={agent.key}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-3)",
                      padding: "var(--space-2) var(--space-3)",
                      borderRadius: "var(--radius-md)",
                      background: "var(--bg-elevated)",
                    }}
                  >
                    <div className={`agent-icon ${agent.className}`}>
                      <agent.icon size={16} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
                        {agent.label}
                      </div>
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                        {label}
                      </div>
                    </div>
                    <div className="status-dot" style={{ opacity: active ? 1 : 0.3 }} />
                  </div>
                );
              })}
            </div>
          </div>

          {/* Portfolio Allocation */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">Portfolio Allocation</div>
            </div>
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={3}
                    dataKey="value"
                    stroke="none"
                  >
                    {pieData.map((_, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={PIE_COLORS[index % PIE_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: "var(--bg-elevated)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-md)",
                      fontSize: "var(--text-sm)",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state">
                <div className="empty-state-icon">📊</div>
                <div className="empty-state-title">No data yet</div>
                <div className="empty-state-text">
                  Run an analysis to see portfolio allocation
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Risk & Recommendations */}
        <div className="grid-2" style={{ marginBottom: "var(--space-5)" }}>
          {/* Risk Summary */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">Risk Assessment</div>
              {sentinelData && (
                <span className="badge badge-hold">{sentinelData.market_regime}</span>
              )}
            </div>
            {sentinelData ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                <div>
                  <div className="stat-label">VaR (95%)</div>
                  <div className="stat-value" style={{ fontSize: "var(--text-xl)" }}>
                    ₹{Math.abs(sentinelData.portfolio_var_95).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                  </div>
                </div>
                <div>
                  <div className="stat-label">Concentration Risk</div>
                  <div className="confidence-bar" style={{ marginTop: 4 }}>
                    <div
                      className={`confidence-bar-fill ${
                        sentinelData.concentration_risk > 0.4 ? "low" : sentinelData.concentration_risk > 0.25 ? "medium" : "high"
                      }`}
                      style={{ width: `${sentinelData.concentration_risk * 100}%` }}
                    />
                  </div>
                  <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 4 }}>
                    Max position: {sentinelData.max_single_position_pct.toFixed(1)}%
                  </div>
                </div>
                {sentinelData.alerts.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
                    {sentinelData.alerts.map((alert, i) => (
                      <div
                        key={i}
                        style={{
                          fontSize: "var(--text-xs)",
                          padding: "var(--space-2) var(--space-3)",
                          background: "var(--amber-muted)",
                          borderRadius: "var(--radius-sm)",
                          color: "var(--amber)",
                        }}
                      >
                        ⚠ {alert}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-state-title">No risk data</div>
                <div className="empty-state-text">Run an analysis first</div>
              </div>
            )}
          </div>

          {/* Recommendations */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">Recommendations</div>
            </div>
            {recommendations.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                {recommendations.map((rec) => (
                  <div className="rec-card" key={rec.symbol}>
                    <div className="rec-card-header">
                      <span className="rec-card-symbol">{rec.symbol}</span>
                      <span
                        className={`badge ${
                          rec.action === "BUY"
                            ? "badge-buy"
                            : rec.action === "REDUCE"
                              ? "badge-reduce"
                              : "badge-hold"
                        }`}
                      >
                        {rec.action === "BUY" && <TrendingUp size={12} />}
                        {rec.action === "REDUCE" && <TrendingDown size={12} />}
                        {rec.action === "HOLD" && <Minus size={12} />}
                        {rec.action}
                      </span>
                    </div>
                    <div className="rec-card-explanation">{rec.explanation}</div>
                    <div className="rec-card-metrics">
                      Confidence: <span>{(rec.confidence * 100).toFixed(0)}%</span>
                      {rec.stop_loss != null && (
                        <>
                          &nbsp;· Stop: <span>{rec.stop_loss}</span>
                        </>
                      )}
                      {rec.target_price != null && (
                        <>
                          &nbsp;· Target: <span>{rec.target_price}</span>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-state-title">No recommendations</div>
                <div className="empty-state-text">Run an analysis to see signals</div>
              </div>
            )}
          </div>
        </div>

        {/* Recent Runs */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">Recent Runs</div>
            <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
              {runs.length} total
            </span>
          </div>
          {runs.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Prompt</th>
                    <th>Created</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {runs.slice(0, 10).map((run) => (
                    <tr key={run.run_id}>
                      <td>
                        <span className={`badge badge-${run.status}`}>
                          {run.status}
                        </span>
                      </td>
                      <td style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {run.prompt}
                      </td>
                      <td style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}>
                        {new Date(run.created_at).toLocaleString()}
                      </td>
                      <td>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => navigate(`/runs/${run.run_id}`)}
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-state-icon">🔍</div>
              <div className="empty-state-title">No runs yet</div>
              <div className="empty-state-text">
                Click "New Analysis" to run your first portfolio analysis
              </div>
            </div>
          )}
        </div>
      </div>

      {/* New Run Modal Overlay */}
      {showModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(11, 14, 20, 0.8)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 999,
          }}
        >
          <div
            className="card"
            style={{
              width: "100%",
              maxWidth: 500,
              background: "var(--bg-surface)",
              boxShadow: "var(--shadow-lg)",
              border: "1px solid var(--border-medium)",
              padding: "var(--space-6)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "var(--space-5)",
              }}
            >
              <h3 style={{ fontSize: "var(--text-lg)", fontWeight: 700 }}>Run Multi-Agent Analysis</h3>
              <button className="btn btn-ghost" onClick={() => setShowModal(false)} style={{ padding: 4 }}>
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleStartAnalysis} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
                <label style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)" }}>
                  Select Portfolio
                </label>
                {portfolios.length > 0 ? (
                  <select
                    value={selectedPortName}
                    onChange={(e) => handlePortSelect(e.target.value)}
                    style={{
                      padding: "10px 14px",
                      background: "var(--bg-input)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-md)",
                      color: "var(--text-primary)",
                      fontSize: "var(--text-sm)",
                    }}
                  >
                    {portfolios.map((p) => (
                      <option key={p.name} value={p.name}>
                        {p.name} ({p.holdings.length} holdings)
                      </option>
                    ))}
                  </select>
                ) : (
                  <div
                    style={{
                      padding: "var(--space-3)",
                      background: "var(--bg-elevated)",
                      borderRadius: "var(--radius-md)",
                      border: "1px solid var(--border-subtle)",
                      fontSize: "var(--text-xs)",
                      color: "var(--amber)",
                      display: "flex",
                      flexDirection: "column",
                      gap: 8,
                    }}
                  >
                    <span>⚠️ No saved portfolios found. You must create a portfolio first.</span>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => {
                        setShowModal(false);
                        navigate("/portfolio");
                      }}
                      style={{ alignSelf: "flex-start" }}
                    >
                      Go to Portfolio Manager
                    </button>
                  </div>
                )}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
                <label style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)" }}>
                  Custom Analysis Prompt
                </label>
                <input
                  type="text"
                  placeholder="e.g. Analyze portfolio long term drift"
                  value={customPrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                  style={{
                    padding: "10px 14px",
                    background: "var(--bg-input)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "var(--radius-md)",
                    color: "var(--text-primary)",
                    fontSize: "var(--text-sm)",
                  }}
                />
              </div>

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: 12,
                  color: "var(--text-muted)",
                  background: "var(--accent-muted)",
                  padding: 8,
                  borderRadius: "var(--radius-sm)",
                }}
              >
                <span>ℹ️ Running this analysis will start the multi-agent pipeline asynchronously. You will be redirected to watch the live progress.</span>
              </div>

              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-end",
                  gap: "var(--space-3)",
                  marginTop: "var(--space-2)",
                }}
              >
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={loading || portfolios.length === 0}
                  style={{ display: "flex", alignItems: "center", gap: 6 }}
                >
                  <Play size={14} fill="white" />
                  Start Run
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
