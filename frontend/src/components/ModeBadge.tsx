import { useEffect, useState } from "react";
import { Badge } from "@astryxdesign/core/Badge";

import { getExecutionState } from "../lib/api";
import type { ExecutionState } from "../lib/api";

const POLL_MS = 20_000;

/**
 * Always-visible answer to "is this real money?". Simulation is calm, paper is amber, and live
 * pulses, so nobody confuses a simulated order with a real one. Hidden until the backend answers
 * (an unreachable backend is already shown in the sidebar footer).
 */
export default function ModeBadge() {
  const [state, setState] = useState<ExecutionState | null>(null);

  useEffect(() => {
    let live = true;
    const load = () =>
      getExecutionState()
        .then((r) => live && setState(r.state))
        .catch(() => live && setState(null));
    void load();
    const t = setInterval(load, POLL_MS);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, []);

  if (!state) return null;
  if (state.paused) {
    return (
      <span className="mode-badge" title="Order execution is paused">
        <Badge label="PAUSED" variant="neutral" />
      </span>
    );
  }
  const label = { simulation: "SIMULATION", paper: "PAPER", live: "LIVE · REAL MONEY" }[state.mode];
  const variant = { simulation: "neutral", paper: "warning", live: "error" }[state.mode] as
    | "neutral"
    | "warning"
    | "error";
  const title = {
    simulation: "Simulation: no orders are placed anywhere",
    paper: "Paper trading: simulated orders on live prices",
    live: "LIVE: orders go to your real broker account",
  }[state.mode];
  return (
    <span className={`mode-badge ${state.mode}`} title={title} data-mode={state.mode}>
      <Badge label={label} variant={variant} />
    </span>
  );
}
