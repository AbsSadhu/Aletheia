import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import TopBar from "../components/TopBar";
import { listRuns, createDemoRun } from "../lib/api";
import type { RunSummary } from "../lib/types";

export default function RunsList() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setError(null);
      const data = await listRuns();
      setRuns(data.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }

  useEffect(() => {
    void refresh();
    const interval = setInterval(() => void refresh(), 15_000);
    return () => clearInterval(interval);
  }, []);

  async function handleNewRun() {
    try {
      setLoading(true);
      setError(null);
      const result = await createDemoRun();
      await refresh();
      navigate(`/runs/${result.summary.run_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <TopBar
        title="Runs"
        onNewRun={handleNewRun}
        onRefresh={() => void refresh()}
        loading={loading}
      />
      <div className="page-shell">
        {error && (
          <p style={{ color: "var(--red)", marginBottom: "var(--space-4)" }}>
            {error}
          </p>
        )}

        {runs.length > 0 ? (
          <div className="card">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Prompt</th>
                    <th>Created</th>
                    <th>Updated</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.run_id}>
                      <td>
                        <span className={`badge badge-${run.status}`}>
                          {run.status}
                        </span>
                      </td>
                      <td
                        style={{
                          maxWidth: 400,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {run.prompt}
                      </td>
                      <td
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "var(--text-xs)",
                        }}
                      >
                        {new Date(run.created_at).toLocaleString()}
                      </td>
                      <td
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "var(--text-xs)",
                        }}
                      >
                        {new Date(run.updated_at).toLocaleString()}
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
          </div>
        ) : (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon">📋</div>
              <div className="empty-state-title">No runs yet</div>
              <div className="empty-state-text">
                Click "New Analysis" to run your first portfolio analysis
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
