import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { applyEvent } from "../../../lib/useChat";
import type { ChatMessage } from "../../../lib/useChat";
import type { LineDisplay, ProposalDisplay, TableDisplay } from "../../../lib/ohlcv";
import LineWidget from "./LineWidget";
import ProposalCard from "./ProposalCard";
import TableWidget from "./TableWidget";

const proposal: ProposalDisplay = {
  type: "proposal",
  proposal_id: "p1",
  symbol: "RELIANCE",
  exchange: "NSE",
  side: "BUY",
  quantity: 10,
  order_type: "MARKET",
  limit_price: null,
  reference_price: 1190,
  estimated_value: 11900,
  currency: "INR",
  rationale: "Pullback to the 20-day average.",
};

let calls: { url: string; method: string }[];
let handler: (url: string, method: string) => Response;

beforeEach(() => {
  calls = [];
  handler = () => Response.json({ id: "p1", status: "pending", outcome: null });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url: url.replace(/^.*\/api\/v1/, ""), method });
      return handler(url, method);
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ProposalCard", () => {
  it("shows the order as a request and places nothing until Confirm is pressed", async () => {
    render(<ProposalCard display={proposal} />);
    expect(await screen.findByText("Waiting for your confirmation")).toBeTruthy();
    expect(screen.getByText("simulated")).toBeTruthy();
    expect(screen.getByText("₹11,900.00")).toBeTruthy();
    expect(calls.map((c) => c.method)).toEqual(["GET"]); // only a status read so far
  });

  it("confirms once, shows the fill, and a second click cannot fire another request", async () => {
    handler = (_url, method) =>
      method === "POST"
        ? Response.json({ proposal: { id: "p1", status: "executed", outcome: null }, trade: { simulated_fill_price: 1190.5 } })
        : Response.json({ id: "p1", status: "pending", outcome: null });
    render(<ProposalCard display={proposal} />);
    const confirm = await screen.findByRole("button", { name: /Confirm/ });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(await screen.findByText(/Placed \(paper\)/)).toBeTruthy();
    expect(screen.getByText(/Filled at ₹1,190.50/)).toBeTruthy();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /Confirm/ })).toBeNull(); // buttons are gone
  });

  it("reports a refusal (e.g. a risk limit) and re-reads the real status", async () => {
    handler = (_url, method) =>
      method === "POST"
        ? new Response(JSON.stringify({ message: "Order too large; the most allowed right now is 4 shares." }), { status: 422 })
        : Response.json({ id: "p1", status: calls.length > 2 ? "failed" : "pending", outcome: null });
    render(<ProposalCard display={proposal} />);
    fireEvent.click(await screen.findByRole("button", { name: /Confirm/ }));
    await waitFor(() => expect(screen.getByText(/Not placed/)).toBeTruthy());
    expect(screen.getByText(/too large/)).toBeTruthy();
  });

  it("shows the true state when a reopened thread's order was already placed", async () => {
    handler = () => Response.json({ id: "p1", status: "executed", outcome: { trade: { simulated_fill_price: 1188 } } });
    render(<ProposalCard display={proposal} />);
    expect(await screen.findByText(/Placed \(paper\)/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Confirm/ })).toBeNull();
  });

  it("reject calls the reject endpoint", async () => {
    handler = (_url, method) =>
      method === "POST"
        ? Response.json({ id: "p1", status: "rejected", outcome: null })
        : Response.json({ id: "p1", status: "pending", outcome: null });
    render(<ProposalCard display={proposal} />);
    fireEvent.click(await screen.findByRole("button", { name: /Reject/ }));
    expect(await screen.findByText("Rejected")).toBeTruthy();
    expect(calls.some((c) => c.url.endsWith("/reject") && c.method === "POST")).toBe(true);
  });
});

describe("other widgets", () => {
  it("TableWidget lists label/value rows", () => {
    const d: TableDisplay = { type: "table", title: "TCS fundamentals", rows: [["P/E (trailing)", "17.73"]], note: "Source: Yahoo" };
    render(<TableWidget display={d} />);
    expect(screen.getByText("TCS fundamentals")).toBeTruthy();
    expect(screen.getByRole("row", { name: /P\/E \(trailing\)\s*17\.73/ })).toBeTruthy();
  });

  it("LineWidget reports the change from the first to the last point", () => {
    const d: LineDisplay = { type: "line", title: "sma_crossover equity (simulated)", baseline: 100000, points: [[0, 100000], [1, 101000], [2, 105000]] };
    render(<LineWidget display={d} />);
    expect(screen.getByText("sma_crossover equity (simulated)")).toBeTruthy();
    expect(screen.getByText(/1,05,000 \(\+5\.00%\)/)).toBeTruthy();
  });
});

describe("token streaming into a message", () => {
  const base: ChatMessage = { id: "a", role: "assistant", content: "", steps: [], pending: true };
  it("types text out, then re-files it as a thought when the turn continues into a tool call", () => {
    let m = applyEvent(base, { event: "token", data: { content: "Let me " } });
    m = applyEvent(m, { event: "token", data: { content: "check." } });
    expect(m.content).toBe("Let me check.");
    m = applyEvent(m, { event: "thought", data: { content: "Let me check." } });
    expect(m.content).toBe("");
    expect(m.steps[0]).toEqual({ type: "thought", content: "Let me check." });
  });

  it("the final answer replaces whatever was streamed, so the two never double up", () => {
    let m = applyEvent(base, { event: "token", data: { content: "All " } });
    m = applyEvent(m, { event: "token", data: { content: "done" } });
    m = applyEvent(m, { event: "final_answer", data: { content: "All done" } });
    expect(m.content).toBe("All done");
  });

  it("pairs a result with its own call id and keeps its chart payload out of the text", () => {
    let m = applyEvent(base, { event: "tool_call", data: { id: "x1", tool: "market_data", arguments: {} } });
    m = applyEvent(m, { event: "tool_call", data: { id: "x2", tool: "market_data", arguments: {} } });
    m = applyEvent(m, { event: "tool_result", data: { id: "x2", tool: "market_data", result: { ok: 2 }, display: { type: "table", title: "t", rows: [] } } });
    const [first, second] = m.steps as { result?: unknown; display?: unknown }[];
    expect(first.result).toBeUndefined();
    expect(second.result).toEqual({ ok: 2 });
    expect(second.display).toMatchObject({ type: "table" });
  });
});

