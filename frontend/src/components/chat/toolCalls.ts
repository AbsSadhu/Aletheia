import type { ChatToolCallItem } from "@astryxdesign/core/Chat";

import type { Step } from "../../lib/chatApi";

type ToolStep = Extract<Step, { type: "tool" }>;

const TARGET_KEYS = ["symbol", "symbols", "query", "strategy_name", "url", "id", "action"];

/** A short "what did it act on" label for a tool call: `RELIANCE · 1y`, `TCS, INFY`, a search query. */
export function describeTarget(args: Record<string, unknown> | undefined): string | undefined {
  if (!args) return undefined;
  for (const key of TARGET_KEYS) {
    const v = args[key];
    if (v === undefined || v === null || v === "") continue;
    const main = Array.isArray(v) ? v.join(", ") : String(v);
    const extra = typeof args.period === "string" ? ` · ${args.period}` : "";
    return `${main}${extra}`.slice(0, 80);
  }
  return undefined;
}

export function formatDuration(ms: number | undefined): string | undefined {
  if (ms === undefined || ms === null || Number.isNaN(ms)) return undefined;
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;
}

/** A tool result that is an `{error: "..."}` object means the call failed. */
export function resultError(result: unknown): string | undefined {
  if (result && typeof result === "object" && "error" in result) {
    const e = (result as { error: unknown }).error;
    return typeof e === "string" ? e : "The tool reported an error";
  }
  return undefined;
}

export function toCallItem(
  step: ToolStep,
  index: number,
  isPending: boolean,
  detail?: ChatToolCallItem["resultDetail"],
): ChatToolCallItem {
  const err = resultError(step.result);
  const waiting = step.result === undefined;
  return {
    key: step.id ?? `${step.tool}-${index}`,
    name: step.tool,
    // A call that never got a result on a finished message was interrupted (Stop pressed).
    status: err ? "error" : waiting ? (isPending ? "running" : "error") : "complete",
    target: describeTarget(step.arguments),
    duration: formatDuration(step.latency_ms),
    errorMessage: err ?? (waiting && !isPending ? "Interrupted before it finished" : undefined),
    resultDetail: waiting ? undefined : detail,
  };
}
