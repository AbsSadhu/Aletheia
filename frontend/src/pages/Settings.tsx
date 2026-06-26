import { useEffect, useState } from "react";
import TopBar from "../components/TopBar";
import { fetchHealth } from "../lib/api";
import type { HealthData } from "../lib/types";

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthData | null>(null);

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => {});
  }, []);

  return (
    <>
      <TopBar title="Settings" />
      <div className="page-shell">
        <div className="grid-2">
          <div className="card">
            <div className="card-title" style={{ marginBottom: "var(--space-4)" }}>
              System Information
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <div>
                <div className="stat-label">Service</div>
                <div style={{ fontSize: "var(--text-sm)" }}>{health?.service ?? "—"}</div>
              </div>
              <div>
                <div className="stat-label">Version</div>
                <div style={{ fontSize: "var(--text-sm)", fontFamily: "var(--font-mono)" }}>
                  {health?.version ?? "—"}
                </div>
              </div>
              <div>
                <div className="stat-label">Status</div>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                  <span className={`status-dot${health ? "" : " offline"}`} />
                  <span style={{ fontSize: "var(--text-sm)" }}>
                    {health ? "Online" : "Offline"}
                  </span>
                </div>
              </div>
              <div>
                <div className="stat-label">SQLite Path</div>
                <div style={{ fontSize: "var(--text-xs)", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                  {health?.sqlite_path ?? "—"}
                </div>
              </div>
              <div>
                <div className="stat-label">DuckDB Path</div>
                <div style={{ fontSize: "var(--text-xs)", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                  {health?.duckdb_path ?? "—"}
                </div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-title" style={{ marginBottom: "var(--space-4)" }}>
              Configuration
            </div>
            <div style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", lineHeight: 1.6 }}>
              <p>Backend: <code style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}>http://127.0.0.1:8899</code></p>
              <p style={{ marginTop: "var(--space-2)" }}>LLM: <code style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}>Ollama (not connected)</code></p>
              <p style={{ marginTop: "var(--space-2)" }}>Mode: <code style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}>Local-first / Offline</code></p>
            </div>
            <div style={{ marginTop: "var(--space-6)", padding: "var(--space-3)", background: "var(--accent-muted)", borderRadius: "var(--radius-md)", fontSize: "var(--text-xs)", color: "var(--accent)" }}>
              ℹ Advanced settings and LLM configuration will be available in Phase 4.
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
