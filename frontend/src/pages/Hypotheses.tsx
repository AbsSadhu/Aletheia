import { useEffect, useState } from "react";
import { FlaskConical } from "lucide-react";

import TopBar from "../components/TopBar";
import {
  listHypotheses,
  proposeHypothesis,
  transitionHypothesis,
  addHypothesisEvidence,
  linkHypothesisToBacktest,
} from "../lib/api";
import type { Hypothesis } from "../lib/api";

const STATUS_TRANSITIONS: Record<string, string[]> = {
  proposed: ["testing", "rejected"],
  testing: ["validated", "rejected", "proposed"],
  validated: ["rejected"],
  rejected: ["proposed"],
};

const STATUS_BADGE: Record<string, string> = {
  proposed: "badge-pending",
  testing: "badge-running",
  validated: "badge-completed",
  rejected: "badge-failed",
};

export default function Hypotheses() {
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Propose form
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [testCriteria, setTestCriteria] = useState("");

  // Evidence form
  const [evSource, setEvSource] = useState("");
  const [evSummary, setEvSummary] = useState("");
  const [evSupports, setEvSupports] = useState(true);

  // Backtest link form
  const [backtestRunId, setBacktestRunId] = useState("");

  async function refresh() {
    try {
      setError(null);
      const data = await listHypotheses(statusFilter || undefined);
      setHypotheses(data.hypotheses);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load hypotheses");
    }
  }

  useEffect(() => {
    void refresh();
  }, [statusFilter]);

  const selected = hypotheses.find((h) => h.id === selectedId) ?? null;

  async function handlePropose() {
    if (!title.trim() || !description.trim() || !testCriteria.trim()) {
      setError("Title, description, and test criteria are all required");
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const hypo = await proposeHypothesis(title.trim(), description.trim(), testCriteria.trim());
      setTitle("");
      setDescription("");
      setTestCriteria("");
      await refresh();
      setSelectedId(hypo.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to propose hypothesis");
    } finally {
      setLoading(false);
    }
  }

  async function handleTransition(newStatus: string) {
    if (!selected) return;
    try {
      setBusy(true);
      setError(null);
      await transitionHypothesis(selected.id, newStatus);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to transition hypothesis");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddEvidence() {
    if (!selected || !evSource.trim() || !evSummary.trim()) {
      setError("Evidence needs a source and a summary");
      return;
    }
    try {
      setBusy(true);
      setError(null);
      await addHypothesisEvidence(selected.id, evSource.trim(), evSummary.trim(), evSupports);
      setEvSource("");
      setEvSummary("");
      setEvSupports(true);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add evidence");
    } finally {
      setBusy(false);
    }
  }

  async function handleLinkBacktest() {
    if (!selected || !backtestRunId.trim()) {
      setError("Enter a backtest run ID to link");
      return;
    }
    try {
      setBusy(true);
      setError(null);
      await linkHypothesisToBacktest(selected.id, backtestRunId.trim());
      setBacktestRunId("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to link backtest");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <TopBar title="Hypotheses" onRefresh={() => void refresh()} loading={loading} />
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
            <span className="card-title">Propose a Hypothesis</span>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            <input
              className="form-control"
              style={{ width: 220 }}
              placeholder="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <input
              className="form-control"
              style={{ flex: 1, minWidth: 220 }}
              placeholder="Description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <input
              className="form-control"
              style={{ flex: 1, minWidth: 220 }}
              placeholder="Test criteria (how would this be validated?)"
              value={testCriteria}
              onChange={(e) => setTestCriteria(e.target.value)}
            />
            <button
              className="btn btn-primary"
              onClick={() => void handlePropose()}
              disabled={loading}
            >
              Propose
            </button>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: "var(--space-5)" }}>
          <div className="card">
            <div className="card-header" style={{ justifyContent: "space-between" }}>
              <span className="card-title">All Hypotheses ({hypotheses.length})</span>
              <select
                className="form-control"
                style={{ width: 130 }}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">All statuses</option>
                <option value="proposed">Proposed</option>
                <option value="testing">Testing</option>
                <option value="validated">Validated</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>

            {hypotheses.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">🧪</div>
                <div className="empty-state-title">No hypotheses yet</div>
                <div className="empty-state-text">Propose one above to start tracking it.</div>
              </div>
            ) : (
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {hypotheses.map((h) => (
                  <li key={h.id}>
                    <button
                      onClick={() => setSelectedId(h.id)}
                      style={{
                        width: "100%",
                        textAlign: "left",
                        display: "flex",
                        flexDirection: "column",
                        gap: 4,
                        padding: "10px 12px",
                        marginBottom: 6,
                        borderRadius: "var(--radius-sm)",
                        border:
                          h.id === selectedId
                            ? "1px solid var(--accent)"
                            : "1px solid var(--border)",
                        background: h.id === selectedId ? "var(--accent-muted)" : "transparent",
                        cursor: "pointer",
                      }}
                    >
                      <span style={{ fontWeight: 600 }}>{h.title}</span>
                      <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        <span className={`badge ${STATUS_BADGE[h.status] ?? "badge-pending"}`}>
                          {h.status}
                        </span>
                        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                          {h.evidence.length} evidence
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card">
            {!selected ? (
              <div className="empty-state">
                <div className="empty-state-icon">
                  <FlaskConical />
                </div>
                <div className="empty-state-title">Select a hypothesis</div>
                <div className="empty-state-text">
                  Pick one from the list to view detail, transition its status, add evidence, or
                  link it to a backtest run.
                </div>
              </div>
            ) : (
              <>
                <div className="card-header" style={{ justifyContent: "space-between" }}>
                  <span className="card-title">{selected.title}</span>
                  <span className={`badge ${STATUS_BADGE[selected.status] ?? "badge-pending"}`}>
                    {selected.status}
                  </span>
                </div>

                <p style={{ color: "var(--text-muted)" }}>{selected.description}</p>
                <p style={{ fontSize: "var(--text-sm)" }}>
                  <strong>Test criteria:</strong> {selected.test_criteria}
                </p>
                <p style={{ fontSize: "var(--text-sm)" }}>
                  <strong>Linked backtest:</strong>{" "}
                  {selected.backtest_run_id ?? (
                    <span style={{ color: "var(--text-muted)" }}>none</span>
                  )}
                </p>

                <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
                  {(STATUS_TRANSITIONS[selected.status] ?? []).map((next) => (
                    <button
                      key={next}
                      className="btn btn-secondary btn-sm"
                      disabled={busy}
                      onClick={() => void handleTransition(next)}
                    >
                      → {next}
                    </button>
                  ))}
                </div>

                <div
                  style={{
                    display: "flex",
                    gap: 8,
                    alignItems: "center",
                    marginBottom: 16,
                    flexWrap: "wrap",
                  }}
                >
                  <input
                    className="form-control"
                    style={{ width: 220 }}
                    placeholder="Backtest run ID"
                    value={backtestRunId}
                    onChange={(e) => setBacktestRunId(e.target.value)}
                  />
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={busy}
                    onClick={() => void handleLinkBacktest()}
                  >
                    Link Backtest
                  </button>
                </div>

                <div className="card-header">
                  <span className="card-title">Evidence ({selected.evidence.length})</span>
                </div>
                {selected.evidence.length === 0 ? (
                  <p style={{ color: "var(--text-muted)", fontSize: "var(--text-sm)" }}>
                    No evidence recorded yet.
                  </p>
                ) : (
                  <ul style={{ listStyle: "none", margin: 0, padding: 0, marginBottom: 12 }}>
                    {selected.evidence.map((ev, i) => (
                      <li
                        key={i}
                        style={{
                          padding: "8px 10px",
                          borderBottom: "1px solid var(--border)",
                          display: "flex",
                          gap: 8,
                          alignItems: "flex-start",
                        }}
                      >
                        <span
                          className={`badge ${ev.supports_hypothesis ? "badge-buy" : "badge-reduce"}`}
                        >
                          {ev.supports_hypothesis ? "Supports" : "Refutes"}
                        </span>
                        <span style={{ flex: 1 }}>
                          <strong>{ev.source}:</strong> {ev.description}
                        </span>
                        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                          {new Date(ev.date_added).toLocaleDateString("en-IN")}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}

                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <input
                    className="form-control"
                    style={{ width: 160 }}
                    placeholder="Source"
                    value={evSource}
                    onChange={(e) => setEvSource(e.target.value)}
                  />
                  <input
                    className="form-control"
                    style={{ flex: 1, minWidth: 220 }}
                    placeholder="Summary"
                    value={evSummary}
                    onChange={(e) => setEvSummary(e.target.value)}
                  />
                  <select
                    className="form-control"
                    style={{ width: 130 }}
                    value={evSupports ? "supports" : "refutes"}
                    onChange={(e) => setEvSupports(e.target.value === "supports")}
                  >
                    <option value="supports">Supports</option>
                    <option value="refutes">Refutes</option>
                  </select>
                  <button
                    className="btn btn-primary btn-sm"
                    disabled={busy}
                    onClick={() => void handleAddEvidence()}
                  >
                    Add Evidence
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
