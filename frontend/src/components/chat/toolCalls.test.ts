import { describe, expect, it } from "vitest";

import { describeTarget, formatDuration, resultError, toCallItem } from "./toolCalls";

const step = (over: Record<string, unknown> = {}) =>
  ({ type: "tool", id: "c1", tool: "market_data", arguments: { symbol: "RELIANCE", period: "1y" }, ...over }) as Parameters<
    typeof toCallItem
  >[0];

describe("tool call rows", () => {
  it("summarises what a call acted on", () => {
    expect(describeTarget({ symbol: "RELIANCE", period: "1y" })).toBe("RELIANCE · 1y");
    expect(describeTarget({ symbols: ["TCS", "INFY"] })).toBe("TCS, INFY");
    expect(describeTarget({ query: "hdfc bank news" })).toBe("hdfc bank news");
    expect(describeTarget({ unrelated: 1 })).toBeUndefined();
    expect(describeTarget(undefined)).toBeUndefined();
  });

  it("formats durations", () => {
    expect(formatDuration(392.4)).toBe("392ms");
    expect(formatDuration(2329)).toBe("2.3s");
    expect(formatDuration(undefined)).toBeUndefined();
  });

  it("recognises an error result", () => {
    expect(resultError({ error: "No data" })).toBe("No data");
    expect(resultError({ ok: 1 })).toBeUndefined();
    expect(resultError("plain")).toBeUndefined();
  });

  it("maps a step to running / complete / error", () => {
    expect(toCallItem(step(), 0, true).status).toBe("running");
    const done = toCallItem(step({ result: { ok: 1 }, latency_ms: 392 }), 0, false, "detail");
    expect(done).toMatchObject({ status: "complete", duration: "392ms", target: "RELIANCE · 1y", key: "c1", resultDetail: "detail" });
    const failed = toCallItem(step({ result: { error: "boom" } }), 0, false);
    expect(failed).toMatchObject({ status: "error", errorMessage: "boom" });
  });

  it("treats a call with no result on a finished message as interrupted, not still running", () => {
    const stopped = toCallItem(step(), 0, false);
    expect(stopped.status).toBe("error");
    expect(stopped.errorMessage).toMatch(/Interrupted/);
    expect(stopped.resultDetail).toBeUndefined();
  });
});
