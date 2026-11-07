import type { AgentEvent } from "./types";

export type StepStatus = "pending" | "active" | "completed" | "failed";

export type RunFrame =
  | { kind: "event"; event: AgentEvent }
  | { kind: "progress"; statuses: Record<string, string> }
  | { kind: "complete" }
  | { kind: "ignore" };

const STEP_ORDER = ["collector", "oracle", "sentinel", "sage", "scribe"];

export function isAgentEvent(v: unknown): v is AgentEvent {
  return !!v && typeof (v as AgentEvent).agent === "string" && typeof (v as AgentEvent).message === "string";
}

/**
 * The run socket carries three kinds of frame: agent events, `{type: "progress", agent_statuses}`
 * snapshots (no `agent` field) and the `stream_complete` marker. Only the first belongs in the
 * event log; treating every frame as an event used to crash the page mid-run.
 */
export function parseRunFrame(raw: string): RunFrame {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return { kind: "ignore" };
  }
  if (!data || typeof data !== "object") return { kind: "ignore" };
  const f = data as Record<string, unknown>;
  if (f.message === "stream_complete") return { kind: "complete" };
  if (f.type === "progress" && f.agent_statuses && typeof f.agent_statuses === "object") {
    return { kind: "progress", statuses: f.agent_statuses as Record<string, string> };
  }
  if (isAgentEvent(data)) return { kind: "event", event: data };
  return { kind: "ignore" };
}

export function stepStatusFor(
  stepKey: string,
  runStatus: string,
  agentStatuses: Record<string, string>,
  events: AgentEvent[],
): StepStatus {
  if (runStatus === "completed") return "completed";
  if (runStatus === "failed") return "failed";

  const reported = agentStatuses[stepKey];
  if (reported) {
    if (reported === "running") return "active";
    if (reported === "completed" || reported === "skipped") return "completed";
    if (reported === "failed") return "failed";
    return "pending";
  }

  const last = [...events].reverse().find(isAgentEvent);
  if (!last) return stepKey === "collector" ? "active" : "pending";
  const targetIdx = STEP_ORDER.indexOf(stepKey);
  const activeIdx = STEP_ORDER.indexOf(last.agent.toLowerCase());
  if (activeIdx === targetIdx) return "active";
  if (targetIdx < activeIdx) return "completed";
  return "pending";
}

/**
 * The run summary is fetched once when the page opens, so a background run that was still queued
 * then keeps saying "pending" while its agents are visibly working. Show what is actually going on.
 */
export function displayStatus(runStatus: string, events: AgentEvent[], agentStatuses: Record<string, string>): string {
  if (runStatus !== "pending") return runStatus;
  const started = events.some(isAgentEvent) || Object.values(agentStatuses).some((s) => s !== "pending");
  return started ? "running" : "pending";
}
