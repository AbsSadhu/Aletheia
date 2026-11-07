/** The pipeline's agents in run order, as the dashboard and the run page show them. */
export const AGENT_STEPS = [
  { key: "collector", label: "Collector" },
  { key: "oracle", label: "Oracle" },
  { key: "sentinel", label: "Sentinel" },
  { key: "sage", label: "Sage" },
  { key: "scribe", label: "Scribe" },
] as const;
