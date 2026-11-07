import { useCallback, useEffect, useRef, useState } from "react";

import { getThread, streamChat } from "./chatApi";
import type { ChatEvent, ModelChoice, Step } from "./chatApi";
import type { ToolDisplay } from "./ohlcv";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  steps: Step[];
  /** model that produced an assistant message */
  model?: string | null;
  provider?: string | null;
  /** assistant message still being produced */
  pending?: boolean;
}

let counter = 0;
const nextId = () => `m${Date.now()}-${counter++}`;

/** Fold one stream event into the assistant message being built. */
export function applyEvent(msg: ChatMessage, { event, data }: ChatEvent): ChatMessage {
  switch (event) {
    case "thread":
      return { ...msg, model: String(data.model ?? ""), provider: String(data.provider ?? "") };
    case "token":
      // Text typed out live. If the turn ends in tool calls it is re-filed as a "thought" below.
      return { ...msg, content: msg.content + String(data.content ?? "") };
    case "thought":
      return {
        ...msg,
        content: "",
        steps: [...msg.steps, { type: "thought", content: String(data.content) }],
      };
    case "tool_call":
      return {
        ...msg,
        steps: [
          ...msg.steps,
          {
            type: "tool",
            id: data.id ? String(data.id) : undefined,
            tool: String(data.tool),
            arguments: data.arguments as Record<string, unknown>,
          },
        ],
      };
    case "tool_result": {
      // Attach to the call with the same id, else the latest same-named call still waiting.
      const steps = [...msg.steps];
      const done = (s: Step) => ({
        ...s,
        result: data.result,
        latency_ms: data.latency_ms as number,
        ...(data.display ? { display: data.display as ToolDisplay } : {}),
      });
      let idx = data.id
        ? steps.findIndex((s) => s.type === "tool" && s.id === String(data.id))
        : -1;
      if (idx === -1) {
        for (let i = steps.length - 1; i >= 0; i--) {
          const s = steps[i];
          if (s.type === "tool" && s.tool === data.tool && s.result === undefined) {
            idx = i;
            break;
          }
        }
      }
      if (idx !== -1) steps[idx] = done(steps[idx]) as Step;
      return { ...msg, steps };
    }
    case "final_answer":
      return { ...msg, content: String(data.content ?? "") };
    case "error":
      return { ...msg, steps: [...msg.steps, { type: "error", content: String(data.message) }] };
    default:
      return msg;
  }
}

export function useChat(choice: ModelChoice | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  // The choice is read when a turn starts, so changing it mid-stream doesn't affect that turn.
  const choiceRef = useRef(choice);
  choiceRef.current = choice;
  const threadRef = useRef<string | null>(null);
  threadRef.current = threadId;

  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(async (prompt: string) => {
    const text = prompt.trim();
    if (!text || abortRef.current) return;
    const assistantId = nextId();
    setMessages((m) => [
      ...m,
      { id: nextId(), role: "user", content: text, steps: [] },
      { id: assistantId, role: "assistant", content: "", steps: [], pending: true },
    ]);
    const controller = new AbortController();
    abortRef.current = controller;
    setStreaming(true);
    const update = (fn: (msg: ChatMessage) => ChatMessage) =>
      setMessages((all) => all.map((x) => (x.id === assistantId ? fn(x) : x)));
    try {
      await streamChat(
        { prompt: text, thread_id: threadRef.current, choice: choiceRef.current },
        (e) => {
          if (e.event === "thread") setThreadId(String(e.data.thread_id));
          update((msg) => applyEvent(msg, e));
        },
        controller.signal,
      );
    } catch (err) {
      if (!controller.signal.aborted) {
        const message = err instanceof Error ? err.message : String(err);
        update((msg) => applyEvent(msg, { event: "error", data: { message } }));
      }
    } finally {
      update((msg) => ({ ...msg, pending: false }));
      abortRef.current = null;
      setStreaming(false);
    }
  }, []);

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setThreadId(null);
  }, []);

  const open = useCallback(async (id: string) => {
    abortRef.current?.abort();
    const thread = await getThread(id);
    setThreadId(thread.id);
    setMessages(
      thread.messages.map((m) => ({
        id: `s${m.id}`,
        role: m.role,
        content: m.content,
        steps: m.steps,
        model: m.model,
        provider: m.provider,
      })),
    );
  }, []);

  return { messages, threadId, streaming, send, stop, reset, open };
}
