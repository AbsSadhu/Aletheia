import { describe, expect, it, vi } from "vitest";

import { takePendingPrompt } from "../lib/chatPanelStore";
import { buildCommands, buildSource } from "./CommandMenu";

describe("command menu", () => {
  const navigate = vi.fn();
  const commands = buildCommands(navigate);
  const source = buildSource(commands);

  it("lists every page plus the actions, grouped", async () => {
    const all = await source.bootstrap?.();
    const groups = new Set((all ?? []).map((c) => (c.auxiliaryData as { group: string }).group));
    expect(groups).toEqual(new Set(["Pages", "Actions"]));
    expect((all ?? []).some((c) => c.label === "Live Market")).toBe(true);
  });

  it("filters by what is typed and navigates when a page command runs", async () => {
    const found = await source.search("backt");
    expect(found.map((c) => c.label)).toContain("Backtest");
    (found.find((c) => c.label === "Backtest")!.auxiliaryData as { run: () => void }).run();
    expect(navigate).toHaveBeenCalledWith("/backtest");
  });

  it("offers to ask the assistant for longer text, and queues that exact prompt", async () => {
    expect((await source.search("hi")).some((c) => c.id.startsWith("ask:"))).toBe(false); // too short
    const found = await source.search("what is the price of TCS");
    const ask = found.find((c) => c.id.startsWith("ask:"))!;
    expect(ask.label).toBe("Ask the assistant: what is the price of TCS");
    (ask.auxiliaryData as { run: () => void }).run();
    expect(takePendingPrompt()).toBe("what is the price of TCS");
    expect(takePendingPrompt()).toBeNull(); // consumed once
  });
});
