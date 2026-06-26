import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  TrendingUp,
  TrendingDown,
  Minus,
  Shield,
  Cpu,
  Eye,
  BookOpen,
  PenTool,
  AlertTriangle,
  Clock,
  CheckCircle2,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";

import TopBar from "../components/TopBar";
import { getRun, getRunEvents, getWebSocketUrl } from "../lib/api";
import type { RunResult, AgentEvent } from "../lib/types";

const TABS = ["Overview", "Oracle Signals", "Risk", "Tax Scenarios", "Recommendations", "Live Timeline"] as const;
type Tab = (typeof TABS)[number];

const AGENT_STEPS = [
  { key: "collector", label: "Collector", icon: Cpu, desc: "Market Data" },
  { key: "oracle", label: "Oracle", icon: Eye, desc: "Trend Analysis" },
  { key: "sentinel", label: "Sentinel", icon: Shield, desc: "Risk Check" },
  { key: "sage", label: "Sage", icon: BookOpen, desc: "Tax Scenario" },
  { key: "scribe", label: "Scribe", icon: PenTool, desc: "Synthesis" },
];

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [run, setRun] = useState<RunResult | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [tab, setTab] = useState<Tab>("Overview");
  const [error, setError] = useState<string | null>(null);
  const [expandedPayloadIndex, setExpandedPayloadIndex] = useState<number | null>(null);

  useEffect(() => {
    if (!runId) return;
    const id: string = runId;

    let socket: WebSocket | null = null;
    let fallbackTimer: number | null = null;

    async function loadRunAndConnect() {
      try {
        setError(null);
        const data = await getRun(id);
        setRun(data);

        // Fetch initial events
        try {
          const eventsRes = await getRunEvents(id);
          setEvents(eventsRes.events);
        } catch {
          // ignore if events fallback endpoint fails
        }

        // If run is running or pending, open WebSocket
        if (data.summary.status === "running" || data.summary.status === "pending") {
          setTab("Live Timeline"); // Switch to timeline automatically to watch it execute
          const wsUrl = getWebSocketUrl(id);
          socket = new WebSocket(wsUrl);

          socket.onmessage = (event) => {
            const parsed = JSON.parse(event.data);
            if (parsed.message === "stream_complete") {
              // Refresh run data to get the full final result
              getRun(id)
                .then((finalRun) => {
                  setRun(finalRun);
                  setTab("Overview"); // Go back to Overview when finished
                })
                .catch(() => {});
              socket?.close();
            } else {
              setEvents((prev) => {
                // Prevent duplicate events
                if (prev.some((e) => e.timestamp === parsed.timestamp && e.message === parsed.message)) {
                  return prev;
                }
                return [...prev, parsed];
              });
            }
          };

          socket.onclose = () => {
            getRun(id).then(setRun).catch(() => {});
          };

          socket.onerror = () => {
            console.warn("WebSocket error, falling back to HTTP polling...");
            // Polling fallback every 2 seconds
            fallbackTimer = window.setInterval(async () => {
              try {
                const refreshed = await getRun(id);
                setRun(refreshed);

                const eventsRes = await getRunEvents(id);
                setEvents(eventsRes.events);

                if (refreshed.summary.status === "completed" || refreshed.summary.status === "failed") {
                  if (fallbackTimer) clearInterval(fallbackTimer);
                  setTab("Overview");
                }
              } catch (err) {
                console.error("HTTP poll fallback error", err);
              }
            }, 2000);
          };
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      }
    }

    void loadRunAndConnect();

    return () => {
      if (socket) socket.close();
      if (fallbackTimer) clearInterval(fallbackTimer);
    };
  }, [runId]);

  if (error) {
    return (
      <>
        <TopBar title="Run Detail" />
        <div className="page-shell">
          <div className="card" style={{ textAlign: "center", padding: "var(--space-8)" }}>
            <p style={{ color: "var(--red)", marginBottom: "var(--space-4)", fontWeight: 600 }}>{error}</p>
            <button className="btn btn-secondary" onClick={() => navigate("/")} style={{ margin: "0 auto" }}>
              <ArrowLeft size={14} /> Back to Dashboard
            </button>
          </div>
        </div>
      </>
    );
  }

  if (!run) {
    return (
      <>
        <TopBar title="Run Detail" />
        <div className="page-shell">
          <div style={{ display: "flex", justifyContent: "center", padding: "var(--space-12)" }}>
            <div className="spinner" />
          </div>
        </div>
      </>
    );
  }

  const scribe = run.scribe_output;
  const sentinel = run.sentinel_output;
  const oracleOutputs = run.oracle_output;
  const sageOutputs = run.sage_output;
  const recs = scribe?.recommendations ?? [];

  // Determine active agent pipeline step
  const getStepStatus = (stepKey: string) => {
    const status = run.summary.status;
    if (status === "completed") return "completed";
    if (status === "failed") return "failed";

    // Trace active agent based on events
    if (events.length === 0) {
      return stepKey === "collector" ? "active" : "pending";
    }

    const lastEvent = events[events.length - 1];
    const activeAgent = lastEvent.agent.toLowerCase();

    // Map order
    const stepOrder = ["collector", "oracle", "sentinel", "sage", "scribe"];
    const targetIdx = stepOrder.indexOf(stepKey);
    const activeIdx = stepOrder.indexOf(activeAgent);

    if (activeIdx === targetIdx) return "active";
    if (targetIdx < activeIdx) return "completed";
    return "pending";
  };

  return (
    <>
      <TopBar title={`Run: ${run.summary.prompt}`} />
      <div className="page-shell">
        {/* Back + Header Bar */}
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginBottom: "var(--space-5)" }}>
          <button className="btn btn-ghost" onClick={() => navigate("/")} style={{ padding: "8px" }}>
            <ArrowLeft size={16} />
          </button>
          <span className={`badge badge-${run.summary.status}`}>{run.summary.status}</span>
          <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
            {new Date(run.summary.created_at).toLocaleString()}
          </span>
          {scribe && (
            <span style={{ marginLeft: "auto", fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
              Confidence: <strong>{(scribe.overall_confidence * 100).toFixed(0)}%</strong>
              &nbsp;· Agreement: <strong>{scribe.agreement_level}</strong>
            </span>
          )}
        </div>

        {/* Live Execution Steps Progress Bar */}
        {(run.summary.status === "running" || run.summary.status === "pending") && (
          <div className="card" style={{ marginBottom: "var(--space-5)", background: "var(--bg-surface)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: "var(--space-4)" }}>
              <div className="spinner" style={{ width: 14, height: 14 }} />
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--accent)" }}>
                Agent Orchestrator Pipeline Executing...
              </div>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(5, 1fr)",
                gap: "var(--space-2)",
                position: "relative",
              }}
            >
              {AGENT_STEPS.map((step, idx) => {
                const stepStatus = getStepStatus(step.key);
                return (
                  <div
                    key={step.key}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      padding: "var(--space-3)",
                      borderRadius: "var(--radius-md)",
                      background:
                        stepStatus === "active"
                          ? "var(--accent-muted)"
                          : stepStatus === "completed"
                            ? "var(--green-muted)"
                            : "var(--bg-elevated)",
                      border:
                        stepStatus === "active"
                          ? "1px solid var(--accent)"
                          : stepStatus === "completed"
                            ? "1px solid var(--green)"
                            : "1px solid var(--border-subtle)",
                      opacity: stepStatus === "pending" ? 0.5 : 1,
                      textAlign: "center",
                      transition: "all var(--transition-base)",
                    }}
                    className={stepStatus === "active" ? "pulse" : ""}
                  >
                    <div
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: "50%",
                        background:
                          stepStatus === "completed"
                            ? "var(--green)"
                            : stepStatus === "active"
                              ? "var(--accent)"
                              : "var(--bg-input)",
                        color: stepStatus === "completed" || stepStatus === "active" ? "white" : "var(--text-muted)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        marginBottom: 6,
                      }}
                    >
                      {stepStatus === "completed" ? <CheckCircle2 size={16} /> : <step.icon size={16} />}
                    </div>
                    <div style={{ fontSize: "var(--text-xs)", fontWeight: 600 }}>{step.label}</div>
                    <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{step.desc}</div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Executive Summary */}
        {scribe && (
          <div className="card" style={{ marginBottom: "var(--space-5)", borderLeft: "4px solid var(--accent)" }}>
            <div className="card-subtitle" style={{ marginBottom: "var(--space-2)" }}>Executive Summary</div>
            <p style={{ fontSize: "var(--text-base)", lineHeight: 1.6, color: "var(--text-primary)" }}>
              {scribe.executive_summary}
            </p>
            {scribe.notes.length > 0 && (
              <div style={{ marginTop: "var(--space-3)", display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
                {scribe.notes.map((note, i) => (
                  <div
                    key={i}
                    style={{
                      fontSize: "var(--text-xs)",
                      padding: "var(--space-2) var(--space-3)",
                      background: "var(--amber-muted)",
                      borderRadius: "var(--radius-sm)",
                      color: "var(--amber)",
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-2)",
                    }}
                  >
                    <AlertTriangle size={12} /> {note}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tabs */}
        <div className="tabs">
          {TABS.map((t) => (
            <button
              key={t}
              className={`tab${tab === t ? " active" : ""}`}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Overview Tab */}
        {tab === "Overview" && (
          <div>
            <div className="card-subtitle" style={{ marginBottom: "var(--space-3)" }}>Insights</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginBottom: "var(--space-5)" }}>
              {run.insights.map((insight, i) => (
                <div
                  key={i}
                  style={{
                    fontSize: "var(--text-sm)",
                    padding: "var(--space-3)",
                    background: "var(--bg-card)",
                    borderRadius: "var(--radius-md)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-secondary)",
                  }}
                >
                  {insight}
                </div>
              ))}
            </div>

            <div className="card-subtitle" style={{ marginBottom: "var(--space-3)" }}>Collector Summary</div>
            <div className="card">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Provider</th>
                      <th>Close</th>
                      <th>Open</th>
                      <th>High</th>
                      <th>Low</th>
                      <th>Volume</th>
                    </tr>
                  </thead>
                  <tbody>
                    {run.collector_output.map((co) => {
                      const q = co.quotes[co.quotes.length - 1];
                      return (
                        <tr key={co.symbol}>
                          <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{co.symbol}</td>
                          <td><span className="badge badge-running" style={{ fontSize: 10 }}>{co.provider_used}</span></td>
                          <td style={{ fontFamily: "var(--font-mono)" }}>₹{q?.close?.toLocaleString("en-IN") ?? "—"}</td>
                          <td style={{ fontFamily: "var(--font-mono)" }}>₹{q?.open?.toLocaleString("en-IN") ?? "—"}</td>
                          <td style={{ fontFamily: "var(--font-mono)" }}>₹{q?.high?.toLocaleString("en-IN") ?? "—"}</td>
                          <td style={{ fontFamily: "var(--font-mono)" }}>₹{q?.low?.toLocaleString("en-IN") ?? "—"}</td>
                          <td style={{ fontFamily: "var(--font-mono)" }}>{q?.volume?.toLocaleString("en-IN") ?? "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Oracle Signals Tab */}
        {tab === "Oracle Signals" && (
          <div className="grid-auto">
            {oracleOutputs.map((oracle) => (
              <div className="card" key={oracle.symbol}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-3)" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "var(--text-lg)" }}>
                    {oracle.symbol}
                  </span>
                  <span
                    className={`badge ${
                      oracle.signal === "BUY" ? "badge-buy" : oracle.signal === "REDUCE" ? "badge-reduce" : "badge-hold"
                    }`}
                  >
                    {oracle.signal === "BUY" && <TrendingUp size={12} />}
                    {oracle.signal === "REDUCE" && <TrendingDown size={12} />}
                    {oracle.signal === "HOLD" && <Minus size={12} />}
                    {oracle.signal}
                  </span>
                </div>
                <div style={{ marginBottom: "var(--space-3)" }}>
                  <div className="stat-label">Confidence</div>
                  <div className="confidence-bar" style={{ marginTop: 4 }}>
                    <div
                      className={`confidence-bar-fill ${oracle.confidence > 0.65 ? "high" : oracle.confidence > 0.4 ? "medium" : "low"}`}
                      style={{ width: `${oracle.confidence * 100}%` }}
                    />
                  </div>
                  <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 4 }}>
                    {(oracle.confidence * 100).toFixed(0)}%
                  </div>
                </div>
                <div style={{ display: "flex", gap: "var(--space-4)", marginBottom: "var(--space-3)" }}>
                  <div>
                    <div className="stat-label">Fair Value Gap</div>
                    <div className={`stat-change ${oracle.fair_value_gap_pct > 0 ? "positive" : oracle.fair_value_gap_pct < 0 ? "negative" : "neutral"}`}>
                      {oracle.fair_value_gap_pct > 0 ? "+" : ""}{oracle.fair_value_gap_pct.toFixed(2)}%
                    </div>
                  </div>
                  <div>
                    <div className="stat-label">Momentum</div>
                    <div className={`stat-change ${oracle.momentum_pct > 0 ? "positive" : oracle.momentum_pct < 0 ? "negative" : "neutral"}`}>
                      {oracle.momentum_pct > 0 ? "+" : ""}{oracle.momentum_pct.toFixed(2)}%
                    </div>
                  </div>
                </div>
                <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
                  {oracle.rationale.map((r, i) => (
                    <span key={i}>• {r}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Risk Tab */}
        {tab === "Risk" && sentinel && (
          <div className="grid-2">
            <div className="card">
              <div className="card-title" style={{ marginBottom: "var(--space-4)" }}>Portfolio Risk Metrics</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
                <div>
                  <div className="stat-label">Value at Risk (95%)</div>
                  <div className="stat-value" style={{ color: "var(--red)" }}>
                    ₹{Math.abs(sentinel.portfolio_var_95).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                  </div>
                </div>
                <div>
                  <div className="stat-label">Market Regime</div>
                  <div className="stat-value" style={{ fontSize: "var(--text-xl)", textTransform: "capitalize" }}>
                    {sentinel.market_regime}
                  </div>
                </div>
                <div>
                  <div className="stat-label">Concentration Risk</div>
                  <div className="stat-value" style={{ fontSize: "var(--text-xl)" }}>
                    {(sentinel.concentration_risk * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="stat-label">Max Position %</div>
                  <div className="stat-value" style={{ fontSize: "var(--text-xl)" }}>
                    {sentinel.max_single_position_pct.toFixed(1)}%
                  </div>
                </div>
              </div>
              <div style={{ marginTop: "var(--space-4)" }}>
                <div className="stat-label">Sentinel Confidence</div>
                <div className="confidence-bar" style={{ marginTop: 6 }}>
                  <div
                    className={`confidence-bar-fill ${sentinel.confidence > 0.5 ? "medium" : "low"}`}
                    style={{ width: `${sentinel.confidence * 100}%` }}
                  />
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card-title" style={{ marginBottom: "var(--space-4)" }}>Risk Alerts</div>
              {sentinel.alerts.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                  {sentinel.alerts.map((alert, i) => (
                    <div
                      key={i}
                      style={{
                        padding: "var(--space-3) var(--space-4)",
                        background: "var(--amber-muted)",
                        borderRadius: "var(--radius-md)",
                        color: "var(--amber)",
                        fontSize: "var(--text-sm)",
                        display: "flex",
                        alignItems: "center",
                        gap: "var(--space-3)",
                      }}
                    >
                      <AlertTriangle size={16} />
                      {alert}
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>
                  No risk alerts for this analysis.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tax Scenarios Tab */}
        {tab === "Tax Scenarios" && (
          <div>
            {sageOutputs.length > 0 && (
              <div className="card" style={{ marginBottom: "var(--space-5)" }}>
                <div className="card-title" style={{ marginBottom: "var(--space-4)" }}>Projected Returns (Pre vs Post-Tax)</div>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={sageOutputs.map((s) => ({
                    symbol: s.symbol,
                    preTax: s.scenario.projected_return_pct,
                    postTax: s.scenario.projected_post_tax_return_pct,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="symbol" tick={{ fill: "#8b95a8", fontSize: 12 }} />
                    <YAxis tick={{ fill: "#8b95a8", fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{
                        background: "var(--bg-elevated)",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: "var(--radius-md)",
                        fontSize: 13,
                      }}
                      formatter={(value) => `${Number(value).toFixed(2)}%`}
                    />
                    <Bar dataKey="preTax" name="Pre-Tax Return" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="postTax" name="Post-Tax Return" fill="#14b8a6" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            <div className="grid-auto">
              {sageOutputs.map((sage) => (
                <div className="card" key={sage.symbol}>
                  <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "var(--text-lg)", marginBottom: "var(--space-3)" }}>
                    {sage.symbol}
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)", marginBottom: "var(--space-3)" }}>
                    <div>
                      <div className="stat-label">Pre-Tax Return</div>
                      <div className={`stat-change ${sage.scenario.projected_return_pct > 0 ? "positive" : "negative"}`}>
                        {sage.scenario.projected_return_pct > 0 ? "+" : ""}{sage.scenario.projected_return_pct.toFixed(2)}%
                      </div>
                    </div>
                    <div>
                      <div className="stat-label">Post-Tax Return</div>
                      <div className={`stat-change ${sage.scenario.projected_post_tax_return_pct > 0 ? "positive" : "negative"}`}>
                        {sage.scenario.projected_post_tax_return_pct > 0 ? "+" : ""}{sage.scenario.projected_post_tax_return_pct.toFixed(2)}%
                      </div>
                    </div>
                    <div>
                      <div className="stat-label">Sharpe Ratio</div>
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)" }}>
                        {sage.scenario.projected_sharpe.toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <div className="stat-label">Tax Drag</div>
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--red)" }}>
                        {sage.scenario.tax_summary.tax_drag_pct.toFixed(1)}%
                      </div>
                    </div>
                  </div>
                  <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                    Tax: ₹{sage.scenario.tax_summary.estimated_tax_amount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                    &nbsp;· Post-tax profit: ₹{sage.scenario.tax_summary.post_tax_profit.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recommendations Tab */}
        {tab === "Recommendations" && (
          <div className="grid-auto">
            {recs.map((rec) => (
              <div className="rec-card" key={rec.symbol}>
                <div className="rec-card-header">
                  <span className="rec-card-symbol">{rec.symbol}</span>
                  <span
                    className={`badge ${
                      rec.action === "BUY" ? "badge-buy" : rec.action === "REDUCE" ? "badge-reduce" : "badge-hold"
                    }`}
                  >
                    {rec.action === "BUY" && <TrendingUp size={12} />}
                    {rec.action === "REDUCE" && <TrendingDown size={12} />}
                    {rec.action === "HOLD" && <Minus size={12} />}
                    {rec.action}
                  </span>
                </div>
                <div className="rec-card-explanation">{rec.explanation}</div>
                <div>
                  <div className="stat-label">Confidence</div>
                  <div className="confidence-bar" style={{ marginTop: 4, marginBottom: 4 }}>
                    <div
                      className={`confidence-bar-fill ${rec.confidence > 0.65 ? "high" : rec.confidence > 0.4 ? "medium" : "low"}`}
                      style={{ width: `${rec.confidence * 100}%` }}
                    />
                  </div>
                  <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                    {(rec.confidence * 100).toFixed(0)}%
                  </div>
                </div>
                <div className="rec-card-metrics">
                  {rec.stop_loss != null && <>Stop Loss: <span>{rec.stop_loss}</span></>}
                  {rec.target_price != null && <>&nbsp;· Target: <span>{rec.target_price}</span></>}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Live Timeline Tab */}
        {tab === "Live Timeline" && (
          <div className="card">
            <div className="card-header" style={{ marginBottom: "var(--space-4)" }}>
              <div className="card-title">Orchestration Logs</div>
              <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 4 }}>
                <Clock size={12} /> {events.length} logs captured
              </span>
            </div>
            <div className="event-timeline">
              {events.length > 0 ? (
                events.map((evt, idx) => (
                  <div className="event-item" key={idx}>
                    <div
                      className="badge"
                      style={{
                        padding: "4px 8px",
                        fontSize: 10,
                        background:
                          evt.agent === "collector"
                            ? "var(--accent-muted)"
                            : evt.agent === "oracle"
                              ? "var(--purple-muted)"
                              : evt.agent === "sentinel"
                                ? "var(--red-muted)"
                                : evt.agent === "sage"
                                  ? "var(--teal-muted)"
                                  : "var(--amber-muted)",
                        color:
                          evt.agent === "collector"
                            ? "var(--accent)"
                            : evt.agent === "oracle"
                              ? "var(--purple)"
                              : evt.agent === "sentinel"
                                ? "var(--red)"
                                : evt.agent === "sage"
                                  ? "var(--teal)"
                                  : "var(--amber)",
                        textTransform: "capitalize",
                        width: 75,
                        justifyContent: "center",
                      }}
                    >
                      {evt.agent}
                    </div>
                    <div className="event-item-body">
                      <div className="event-item-message">{evt.message}</div>
                      <div className="event-item-time">
                        {new Date(evt.timestamp).toLocaleTimeString()}
                      </div>
                      
                      {/* Optional Expandable payload details */}
                      {evt.payload && (
                        <div style={{ marginTop: 8 }}>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => setExpandedPayloadIndex(expandedPayloadIndex === idx ? null : idx)}
                            style={{ fontSize: 10, padding: "2px 6px" }}
                          >
                            {expandedPayloadIndex === idx ? "Hide Payload" : "Show Payload"}
                          </button>
                          {expandedPayloadIndex === idx && (
                            <pre
                              style={{
                                background: "var(--bg-input)",
                                padding: "var(--space-3)",
                                borderRadius: "var(--radius-sm)",
                                fontSize: 11,
                                fontFamily: "var(--font-mono)",
                                overflowX: "auto",
                                color: "var(--text-secondary)",
                                marginTop: 6,
                                border: "1px solid var(--border-subtle)",
                              }}
                            >
                              {JSON.stringify(evt.payload, null, 2)}
                            </pre>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div style={{ padding: "var(--space-6)", textAlign: "center", color: "var(--text-muted)" }}>
                  Waiting for agent events to stream...
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
