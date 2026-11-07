import { describe, expect, it } from "vitest";

import { displayStatus, isAgentEvent, parseRunFrame, stepStatusFor } from "./runProgress";

const ev = (agent: string, message = "m") => ({ run_id: "r", agent, message, timestamp: "2026-10-29T00:00:00Z", payload: null });

describe("parseRunFrame", () => {
  it("returns an event for a normal agent event frame", () => {
    expect(parseRunFrame(JSON.stringify(ev("collector")))).toEqual({ kind: "event", event: ev("collector") });
  });

  it("returns agent statuses for the progress frame the server pushes (it has no agent field)", () => {
    const frame = { run_id: "r", type: "progress", agent_statuses: { collector: "completed", oracle: "running" } };
    expect(parseRunFrame(JSON.stringify(frame))).toEqual({ kind: "progress", statuses: { collector: "completed", oracle: "running" } });
  });

  it("recognises the end-of-stream marker", () => {
    expect(parseRunFrame(JSON.stringify({ run_id: "r", message: "stream_complete" }))).toEqual({ kind: "complete" });
  });

  it("ignores garbage and shapes it does not know instead of throwing", () => {
    expect(parseRunFrame("not json")).toEqual({ kind: "ignore" });
    expect(parseRunFrame(JSON.stringify({ hello: 1 }))).toEqual({ kind: "ignore" });
    expect(parseRunFrame("null")).toEqual({ kind: "ignore" });
  });
});

describe("isAgentEvent", () => {
  it("needs a string agent and message", () => {
    expect(isAgentEvent(ev("oracle"))).toBe(true);
    expect(isAgentEvent({ type: "progress" })).toBe(false);
    expect(isAgentEvent({ agent: 3, message: "x" })).toBe(false);
    expect(isAgentEvent(null)).toBe(false);
  });
});

describe("stepStatusFor", () => {
  it("uses the server's per-agent statuses when present", () => {
    const statuses = { collector: "completed", oracle: "running", sentinel: "pending", sage: "pending", scribe: "pending" };
    expect(stepStatusFor("collector", "running", statuses, [])).toBe("completed");
    expect(stepStatusFor("oracle", "running", statuses, [])).toBe("active");
    expect(stepStatusFor("sage", "running", statuses, [])).toBe("pending");
  });

  it("maps failed and skipped", () => {
    expect(stepStatusFor("sage", "running", { sage: "failed" }, [])).toBe("failed");
    expect(stepStatusFor("sage", "running", { sage: "skipped" }, [])).toBe("completed");
  });

  it("everything is completed or failed once the run is over", () => {
    expect(stepStatusFor("scribe", "completed", {}, [])).toBe("completed");
    expect(stepStatusFor("scribe", "failed", {}, [])).toBe("failed");
  });

  it("falls back to the newest event when there are no statuses, and never throws on an odd last event", () => {
    expect(stepStatusFor("collector", "running", {}, [])).toBe("active");
    expect(stepStatusFor("oracle", "running", {}, [])).toBe("pending");
    expect(stepStatusFor("collector", "running", {}, [ev("oracle")])).toBe("completed");
    expect(stepStatusFor("oracle", "running", {}, [ev("oracle")])).toBe("active");
    // an event with no agent (what used to blank the whole app)
    const odd = { run_id: "r", type: "progress" } as unknown as ReturnType<typeof ev>;
    expect(() => stepStatusFor("oracle", "running", {}, [ev("collector"), odd])).not.toThrow();
  });
});

describe("displayStatus", () => {
  it("a run that has started producing work is running, even if the page loaded while it was pending", () => {
    expect(displayStatus("pending", [ev("collector")], {})).toBe("running");
    expect(displayStatus("pending", [], { collector: "running" })).toBe("running");
  });

  it("stays pending until something has actually happened", () => {
    expect(displayStatus("pending", [], {})).toBe("pending");
    expect(displayStatus("pending", [], { collector: "pending", oracle: "pending" })).toBe("pending");
  });

  it("never overrides a final or running status", () => {
    expect(displayStatus("completed", [ev("collector")], {})).toBe("completed");
    expect(displayStatus("failed", [], { collector: "running" })).toBe("failed");
    expect(displayStatus("running", [], {})).toBe("running");
  });
});
