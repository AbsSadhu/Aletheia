import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { readSSE } from "../../lib/chatApi";
import type { ProvidersResponse } from "../../lib/chatApi";
import { setChatOpen } from "../../lib/chatPanelStore";
import { applyEvent } from "../../lib/useChat";
import type { ChatMessage } from "../../lib/useChat";
import ChatPanel from "./ChatPanel";

const enc = new TextEncoder();

// Astryx's composer input is a contenteditable element, not a textarea.
async function findComposer(): Promise<HTMLElement> {
  return waitFor(() => {
    const el = document.querySelector<HTMLElement>('[contenteditable="true"]');
    if (!el) throw new Error("composer not rendered yet");
    return el;
  });
}
function typeInto(el: HTMLElement, text: string): void {
  el.textContent = text;
  fireEvent.input(el);
}

function sseResponse(chunks: string[], status = 200): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      chunks.forEach((x) => c.enqueue(enc.encode(x)));
      c.close();
    },
  });
  return new Response(stream, { status, headers: { "Content-Type": "text/event-stream" } });
}

const ev = (event: string, data: object) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

const PROVIDERS: ProvidersResponse = {
  default: { provider: "ollama", model: "mistral:7b" },
  providers: [
    {
      id: "ollama",
      label: "Ollama (local)",
      configured: true,
      available: true,
      error: null,
      models: [
        { model: "mistral:7b", label: "mistral:7b", installed: true, custom_id: null, parameter_size: "7B", size_bytes: 4_100_000_000 },
        { model: "qwen2.5:7b", label: "qwen2.5:7b", installed: true, custom_id: null, parameter_size: "7.6B", size_bytes: 4_700_000_000 },
      ],
    },
    { id: "openai", label: "OpenAI", configured: false, available: false, error: "Add an OpenAI API key in Settings", models: [] },
  ],
};

describe("readSSE", () => {
  it("reassembles events split across chunks and ignores garbage", async () => {
    const full = ev("thread", { thread_id: "t1" }) + ev("final_answer", { content: "hi" });
    const cut = 20; // splits inside the first event
    const seen: string[] = [];
    await readSSE(sseResponse([full.slice(0, cut), full.slice(cut), "event: x\ndata: {bad\n\n"]), (e) =>
      seen.push(e.event),
    );
    expect(seen).toEqual(["thread", "final_answer"]);
  });
});

describe("applyEvent", () => {
  const base: ChatMessage = { id: "a", role: "assistant", content: "", steps: [] };
  it("pairs a tool result with its call and records the answer", () => {
    let m = applyEvent(base, { event: "tool_call", data: { tool: "market_data", arguments: { symbol: "X" } } });
    m = applyEvent(m, { event: "tool_result", data: { tool: "market_data", result: { p: 1 }, latency_ms: 12 } });
    m = applyEvent(m, { event: "final_answer", data: { content: "done" } });
    expect(m.content).toBe("done");
    expect(m.steps[0]).toMatchObject({ type: "tool", result: { p: 1 }, latency_ms: 12 });
  });
});

describe("ChatPanel", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let bodies: Record<string, unknown>[];

  beforeEach(() => {
    localStorage.clear();
    bodies = [];
    fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/chat/providers")) return Response.json(PROVIDERS);
      if (url.endsWith("/chat/stream")) {
        bodies.push(JSON.parse(String(init?.body)));
        return sseResponse([
          ev("thread", { thread_id: "t1", provider: "ollama", model: "qwen2.5:7b" }),
          ev("tool_call", { tool: "market_data", arguments: { symbol: "TCS.NS" } }),
          ev("tool_result", { tool: "market_data", result: { price: 1 }, latency_ms: 40 }),
          ev("final_answer", { content: "TCS is **up**." }),
          ev("done", {}),
        ]);
      }
      return new Response("{}", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    act(() => setChatOpen(true));
  });

  afterEach(() => {
    act(() => setChatOpen(false));
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the active model and lets the user switch to another on disk", async () => {
    render(<ChatPanel />);
    const trigger = await screen.findByRole("button", { name: /mistral:7b/ });
    expect(within(trigger).getByText("7B")).toBeTruthy();

    fireEvent.click(trigger);
    expect(await screen.findByText("qwen2.5:7b")).toBeTruthy();
    expect(screen.getByText("unavailable")).toBeTruthy(); // OpenAI has no key
    fireEvent.click(screen.getByRole("option", { name: /qwen2\.5:7b/ }));

    await waitFor(() => expect(screen.getByRole("button", { name: /qwen2\.5:7b/ })).toBeTruthy());
    expect(JSON.parse(localStorage.getItem("aletheia_chat_model")!)).toMatchObject({
      provider: "ollama",
      model: "qwen2.5:7b",
    });
  });

  it("sends the chosen model, streams the answer, and reuses the thread on follow-ups", async () => {
    localStorage.setItem("aletheia_chat_model", JSON.stringify({ provider: "ollama", model: "qwen2.5:7b" }));
    render(<ChatPanel />);
    const box = await findComposer();
    typeInto(box, "How is TCS?");
    fireEvent.keyDown(box, { key: "Enter" });

    expect(await screen.findByText("up")).toBeTruthy(); // bold markdown rendered
    expect(screen.getByText("How is TCS?")).toBeTruthy();
    expect(screen.getByText("market_data")).toBeTruthy(); // collapsed tool step
    expect(bodies[0]).toMatchObject({ prompt: "How is TCS?", provider: "ollama", model: "qwen2.5:7b" });
    expect(bodies[0].thread_id).toBeUndefined();

    typeInto(box, "and Infosys?");
    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1].thread_id).toBe("t1");
  });

  it("does not send on Shift+Enter", async () => {
    render(<ChatPanel />);
    const box = await findComposer();
    typeInto(box, "line one");
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(bodies).toHaveLength(0);
  });

  it("surfaces a backend error from the stream", async () => {
    fetchMock.mockImplementationOnce(async () => Response.json(PROVIDERS));
    fetchMock.mockImplementationOnce(async () =>
      sseResponse([
        ev("thread", { thread_id: "t9", provider: "ollama", model: "mistral:7b" }),
        ev("error", { message: "Ollama isn't reachable at http://127.0.0.1:11434." }),
        ev("done", {}),
      ]),
    );
    render(<ChatPanel />);
    const box = await findComposer();
    typeInto(box, "hi");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(await screen.findByText(/isn't reachable/)).toBeTruthy();
  });
});
