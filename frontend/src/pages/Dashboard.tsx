import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Table } from "@astryxdesign/core/Table";

import CountUp from "../components/CountUp";
import DataWarnings from "../components/DataWarnings";
import Flap from "../components/Flap";
import Gauge3D from "../components/Gauge3D";
import HoldingsObject3D from "../components/HoldingsObject3D";
import TopBar from "../components/TopBar";
import { toneBadge } from "../lib/tone";
import { AGENT_STEPS } from "../lib/agents";
import { fetchHealth, listRuns, listPortfolios, createRun, getRun } from "../lib/api";
import type { RunResult, RunSummary, HealthData, PortfolioData } from "../lib/types";

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

/** Ten flat cells, lit in proportion: the board's scannable block. */
function Cells({ value, warn }: { value: number; warn?: boolean }) {
  const on = Math.max(0, Math.min(10, Math.round(value * 10)));
  return (
    <span className={`cells${warn ? " warn" : ""}`} aria-hidden="true">
      {Array.from({ length: 10 }, (_, i) => (
        <i key={i} className={i < on ? "on" : ""} style={{ ["--n" as string]: i } as React.CSSProperties} />
      ))}
    </span>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [health, setHealth] = useState<HealthData | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [portfolios, setPortfolios] = useState<PortfolioData[]>([]);
  const [fetchedRun, setLatestRun] = useState<RunResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const failedOnce = useRef(false);
  const seededSelection = useRef(false);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

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

      // Pick a default once. `refresh` is captured by the polling interval, so it can't see the
      // user's later choice in state.
      if (portData.portfolios.length > 0 && !seededSelection.current) {
        seededSelection.current = true;
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
      failedOnce.current = false;
    } catch (err) {
      // The desktop backend takes a few seconds to start; stay quiet on the first miss and retry soon.
      if (!failedOnce.current) {
        failedOnce.current = true;
        retryTimer.current = setTimeout(() => void refresh(), 3000);
        return;
      }
      setError(err instanceof Error ? err.message : "Unknown error");
    }
    setLoaded(true);
  }

  useEffect(() => {
    void refresh();
    const interval = setInterval(() => void refresh(), 15_000);
    return () => {
      clearInterval(interval);
      clearTimeout(retryTimer.current);
    };
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
  // A run priced from the built-in sample prices is not real market data: say so and keep its numbers out.
  const sampleRun = !!fetchedRun?.warnings?.some((w) => /sample data/i.test(w));
  const latestRun = sampleRun ? null : fetchedRun;
  const holdings = latestRun?.collector_output ?? [];
  // Allocation by market value: the saved portfolio that best matches the run's symbols, at the run's prices.
  const priceBySymbol = new Map(holdings.map((h) => [h.symbol.toUpperCase(), h.quotes?.[0]?.close ?? 0]));
  const matched = portfolios
    .map((p) => ({ p, hits: p.holdings.filter((h) => priceBySymbol.has(h.symbol.toUpperCase())).length }))
    .sort((a, b) => b.hits - a.hits)[0];
  const pieData =
    matched && matched.hits > 0
      ? matched.p.holdings
          .filter((h) => priceBySymbol.has(h.symbol.toUpperCase()))
          .map((h) => ({ name: h.symbol, value: h.quantity * (priceBySymbol.get(h.symbol.toUpperCase()) ?? 0) }))
      : [];

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
        {sampleRun && (
          <DataWarnings
            warnings={[
              "The latest run was priced from built-in sample data, not live market prices, so its results are hidden here. Click New Analysis to run on live prices.",
            ]}
          />
        )}
        <DataWarnings warnings={latestRun?.warnings} />

        <div className="board-hero">
          <div className="card hero-3d">
            <div className="hero-3d-title">
              <b>Your book</b>
              <span>{matched && matched.hits > 0 ? matched.p.name : "No analysis yet"}</span>
            </div>
            <HoldingsObject3D slices={pieData} />
          </div>

          <div className="card departures">
            <div className="departures-head">
              <span>Status board</span>
              <span>Now</span>
            </div>
            <div className="departure-row" style={{ ["--row" as string]: 0 } as React.CSSProperties}>
              <span className="departure-label">
                System
                <span className="departure-note">{health ? `v${health.version}` : "Connecting…"}</span>
              </span>
              <span className="departure-value">
                <Flap text={!loaded ? "···" : health ? "ONLINE" : "OFFLINE"} />
              </span>
            </div>
            <div className="departure-row" style={{ ["--row" as string]: 1 } as React.CSSProperties}>
              <span className="departure-label">
                Analyses run
                <span className="departure-note">portfolio analyses</span>
              </span>
              <span className="departure-value">
                <Flap text={loaded ? String(runs.length) : "·"} />
              </span>
            </div>
            <div className="departure-row" style={{ ["--row" as string]: 2 } as React.CSSProperties}>
              <span className="departure-label">
                Agent agreement
                <span className="departure-note">latest cross-agent consensus</span>
              </span>
              <span className="departure-value">
                <Flap text={loaded ? String(latestRun?.scribe_output?.agreement_level ?? "—").toUpperCase() : "···"} />
              </span>
            </div>
            <div className="departure-row" style={{ ["--row" as string]: 3 } as React.CSSProperties}>
              <span className="departure-label">
                Confidence
                <span className="departure-note">
                  {latestRun?.scribe_output ? (
                    <Cells
                      value={latestRun.scribe_output.overall_confidence}
                      warn={latestRun.scribe_output.overall_confidence < 0.4}
                    />
                  ) : (
                    "overall score"
                  )}
                </span>
              </span>
              <span className="departure-value">
                <Flap
                  text={
                    !loaded
                      ? "··"
                      : latestRun?.scribe_output
                        ? `${(latestRun.scribe_output.overall_confidence * 100).toFixed(0)}%`
                        : "—"
                  }
                />
              </span>
            </div>
          </div>
        </div>

        <div className="grid-3" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card">
            <div className="card-header">
              <div className="card-title">Agent gates</div>
              {latestRun && (
                <span className={`badge badge-${latestRun.summary.status}`}>
                  {latestRun.summary.status}
                </span>
              )}
            </div>
            <div>
              {AGENT_STEPS.map((agent, i) => {
                const { label } = agentPipelineState(agent.key, latestRun);
                const running = label.includes("in progress");
                const done = label.includes("completed");
                return (
                  <div className="gate" key={agent.key}>
                    <span className="gate-no">GATE {i + 1}</span>
                    <div>
                      <div className="gate-name">{agent.label}</div>
                      <div className="gate-state" style={{ color: "var(--text-muted)" }}>
                        {label}
                      </div>
                    </div>
                    <span className={`gate-lamp${running ? " on" : done ? " done" : ""}`} />
                  </div>
                );
              })}
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <div className="card-title">Conviction</div>
              <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>overall confidence</span>
            </div>
            <Gauge3D value={latestRun?.scribe_output ? latestRun.scribe_output.overall_confidence : null} />
            <div className="gauge-read">
              <span className="departure-value">
                <Flap
                  text={latestRun?.scribe_output ? `${(latestRun.scribe_output.overall_confidence * 100).toFixed(0)}%` : "—"}
                />
              </span>
            </div>
          </div>

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
                    <CountUp
                      value={Math.abs(sentinelData.portfolio_var_95)}
                      format={(n) => `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
                    />
                  </div>
                </div>
                <div>
                  <div className="stat-label">Concentration Risk</div>
                  <div style={{ marginTop: 4 }}>
                    <ProgressBar
                      label="Concentration risk"
                      isLabelHidden
                      value={sentinelData.concentration_risk * 100}
                      variant={
                        sentinelData.concentration_risk > 0.4
                          ? "error"
                          : sentinelData.concentration_risk > 0.25
                            ? "warning"
                            : "success"
                      }
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
                          display: "flex",
                          gap: "var(--space-2)",
                          alignItems: "flex-start",
                          fontSize: "var(--text-xs)",
                          padding: "var(--space-2) var(--space-3)",
                          background: "var(--amber-muted)",
                          borderRadius: "var(--radius-sm)",
                          color: "var(--amber)",
                        }}
                      >
                        <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
                        {alert}
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
        </div>

        <div className="card" style={{ marginBottom: "var(--space-5)" }}>
          <div className="card-header">
            <div className="card-title">Recommendations</div>
            <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
              Research output, not financial advice. Signals are not validated against Nifty.
            </span>
          </div>
          {recommendations.length > 0 ? (
            <>
            <div className="pass-grid">
              {recommendations.map((rec, i) => (
                <article className="pass" key={rec.symbol} style={{ ["--n" as string]: i } as React.CSSProperties}>
                  <div className="pass-main">
                    <div className="pass-top">
                      <span className="pass-symbol">{rec.symbol}</span>
                      <span
                        className={`badge ${toneBadge(rec.action)}`}
                      >
                        {rec.action === "BUY" && <TrendingUp size={12} />}
                        {rec.action === "REDUCE" && <TrendingDown size={12} />}
                        {rec.action === "HOLD" && <Minus size={12} />}
                        {rec.action}
                      </span>
                    </div>
                    <p className="pass-why">{rec.explanation}</p>
                  </div>
                  <div className="pass-stub">
                    <div className="pass-field">
                      <span>Confidence</span>
                      <b>{(rec.confidence * 100).toFixed(0)}%</b>
                      <div style={{ marginTop: 6 }}>
                        <Cells value={rec.confidence} warn={rec.confidence < 0.4} />
                      </div>
                    </div>
                    {rec.stop_loss != null && (
                      <div className="pass-field">
                        <span>Stop</span>
                        <b>{rec.stop_loss}</b>
                      </div>
                    )}
                    {rec.target_price != null && (
                      <div className="pass-field">
                        <span>Target</span>
                        <b>{rec.target_price}</b>
                      </div>
                    )}
                  </div>
                </article>
              ))}
            </div>
            <p className="pulse-note" style={{ marginTop: "var(--space-4)" }}>
              Confidence is a rough score averaged from the agents, not a calibrated chance of profit. Treat each pass as a hypothesis to check, and see how past signals held up in{" "}
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => navigate("/validation")}>Signal Validation</button> and{" "}
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => navigate("/shadow-trader")}>Shadow Trader</button>.
            </p>
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-state-title">No recommendations</div>
              <div className="empty-state-text">Run an analysis to see signals</div>
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-header">
            <div className="card-title">Recent Runs</div>
            <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
              {runs.length} total
            </span>
          </div>
          {runs.length > 0 ? (
            <Table
              data={runs.slice(0, 10).map((r) => ({ ...r }))}
              columns={[
                {
                  key: "status",
                  header: "Status",
                  renderCell: (r) => <span className={`badge badge-${String(r.status)}`}>{String(r.status)}</span>,
                },
                {
                  key: "prompt",
                  header: "Prompt",
                  renderCell: (r) => <span className="runs-prompt">{String(r.prompt)}</span>,
                },
                {
                  key: "created_at",
                  header: "Created",
                  renderCell: (r) => (
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}>
                      {new Date(String(r.created_at)).toLocaleString()}
                    </span>
                  ),
                },
                {
                  key: "run_id",
                  header: "",
                  renderCell: (r) => (
                    <Button label="View" variant="secondary" size="sm" onClick={() => navigate(`/runs/${String(r.run_id)}`)} />
                  ),
                },
              ]}
            />
          ) : (
            <div className="empty-state">
              <div className="empty-state-title">No runs yet</div>
              <div className="empty-state-text">
                Click "New Analysis" to run your first portfolio analysis
              </div>
            </div>
          )}
        </div>
      </div>

      <Dialog
        isOpen={showModal}
        onOpenChange={setShowModal}
        width={500}
      >
        <div style={{ padding: "var(--space-5)" }}>
        <DialogHeader title="Run multi-agent analysis" onOpenChange={setShowModal} />
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
                    <span>No saved portfolios found. Create a portfolio first.</span>
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
                <span>Running this analysis will start the multi-agent pipeline asynchronously. You will be redirected to watch the live progress.</span>
              </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-3)" }}>
            <Button type="button" label="Cancel" variant="secondary" onClick={() => setShowModal(false)} />
            <Button type="submit" label="Start run" variant="primary" isDisabled={loading || portfolios.length === 0} />
          </div>
        </form>
        </div>
      </Dialog>
    </>
  );
}
