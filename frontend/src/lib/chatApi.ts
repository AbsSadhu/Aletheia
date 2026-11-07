import { API_BASE_URL, authHeaders } from "./api";
import type { ToolDisplay } from "./ohlcv";

// Types (mirror aletheia/core/api/routers/chat.py)

export type ProviderId = "ollama" | "openai" | "anthropic" | "openai_compatible";

export interface ModelEntry {
  model: string;
  label: string;
  /** false for a custom Ollama entry that has not been downloaded yet */
  installed: boolean;
  custom_id: string | null;
  size_bytes?: number;
  parameter_size?: string | null;
  quantization?: string | null;
  family?: string | null;
  base_url?: string | null;
}

export interface ProviderInfo {
  id: ProviderId;
  label: string;
  configured: boolean;
  available: boolean;
  error: string | null;
  base_url?: string;
  models: ModelEntry[];
}

export interface ProvidersResponse {
  default: { provider: ProviderId; model: string };
  providers: ProviderInfo[];
}

/** What the user picked; custom_model_id wins when set. */
export interface ModelChoice {
  provider: ProviderId;
  model: string;
  custom_model_id?: string | null;
}

export interface ThreadSummary {
  id: string;
  title: string;
  provider: string | null;
  model: string | null;
  updated_at: string;
}

export type Step =
  | { type: "thought"; content: string }
  | {
      type: "tool";
      id?: string;
      tool: string;
      arguments?: Record<string, unknown>;
      result?: unknown;
      latency_ms?: number;
      truncated?: boolean;
      /** structured payload for a widget (chart, table); never sent to the model */
      display?: ToolDisplay;
    }
  | { type: "error"; content: string };

export interface StoredMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  steps: Step[];
  provider: string | null;
  model: string | null;
}

export interface ThreadDetail extends ThreadSummary {
  messages: StoredMessage[];
}

export interface ChatEvent {
  event: string;
  data: Record<string, unknown>;
}

// HTTP helpers

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/v1${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...authHeaders(),
      ...init.headers,
    },
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

async function errorMessage(response: Response): Promise<string> {
  const text = await response.text().catch(() => "");
  try {
    const body = JSON.parse(text);
    if (typeof body.message === "string") return body.message;
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* not JSON */
  }
  return text || `${response.status} ${response.statusText}`;
}

/**
 * Read a text/event-stream body, calling onEvent for each complete event.
 * Exported for tests; handles events split across network chunks.
 */
export async function readSSE(
  response: Response,
  onEvent: (e: ChatEvent) => void,
): Promise<void> {
  if (!response.body) throw new Error("Response has no body");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const flush = (block: string) => {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    if (!dataLines.length) return;
    try {
      onEvent({ event, data: JSON.parse(dataLines.join("\n")) });
    } catch {
      /* a malformed event must not kill the stream */
    }
  };
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      flush(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 2);
    }
  }
  if (buffer.trim()) flush(buffer);
}

// Models

export const getProviders = () => request<ProvidersResponse>("/chat/providers");

export interface CustomModelInput {
  provider: ProviderId;
  model: string;
  label?: string;
  base_url?: string;
  api_key?: string;
}

export const addCustomModel = (input: CustomModelInput) =>
  request<{ id: string }>("/chat/models/custom", {
    method: "POST",
    body: JSON.stringify(input),
  });

export const deleteCustomModel = (id: string) =>
  request<void>(`/chat/models/custom/${id}`, { method: "DELETE" });

export interface PullProgress {
  status: string;
  completed?: number;
  total?: number;
}

/** Download a model into Ollama. Resolves when finished; rejects on error or abort. */
export async function pullModel(
  model: string,
  onProgress: (p: PullProgress) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/chat/models/pull`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ model }),
    signal,
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  let failure: string | null = null;
  let finished = false;
  await readSSE(response, ({ event, data }) => {
    if (event === "progress") onProgress(data as unknown as PullProgress);
    else if (event === "error") failure = String(data.message ?? "Download failed");
    else if (event === "done") finished = true;
  });
  if (failure) throw new Error(failure);
  if (!finished) throw new Error("Download ended unexpectedly");
}

// Threads

export const listThreads = () => request<ThreadSummary[]>("/chat/threads");
export const getThread = (id: string) => request<ThreadDetail>(`/chat/threads/${id}`);
export const deleteThread = (id: string) =>
  request<void>(`/chat/threads/${id}`, { method: "DELETE" });

// Chat

export interface ChatTurn {
  prompt: string;
  thread_id?: string | null;
  choice?: ModelChoice | null;
}

/** Stream one agent turn. Rejects on HTTP failure or abort; stream-level errors arrive as events. */
export async function streamChat(
  turn: ChatTurn,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const body: Record<string, unknown> = { prompt: turn.prompt };
  if (turn.thread_id) body.thread_id = turn.thread_id;
  if (turn.choice) {
    body.provider = turn.choice.provider;
    body.model = turn.choice.model;
    if (turn.choice.custom_model_id) body.custom_model_id = turn.choice.custom_model_id;
  }
  const response = await fetch(`${API_BASE_URL}/api/v1/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  await readSSE(response, onEvent);
}

// Order proposals

export type ProposalStatus = "pending" | "executing" | "executed" | "rejected" | "expired" | "failed";

export interface ProposalState {
  id: string;
  status: ProposalStatus;
  outcome: Record<string, unknown> | null;
}

export const getProposal = (id: string) => request<ProposalState>(`/chat/proposals/${id}`);

export const rejectProposal = (id: string) =>
  request<ProposalState>(`/chat/proposals/${id}/reject`, { method: "POST" });

export const executeProposal = (id: string) =>
  request<{ proposal: ProposalState; trade: Record<string, unknown> }>(
    `/chat/proposals/${id}/execute`,
    { method: "POST" },
  );

// Choosing a model that will actually work

const withTag = (name: string) => (name.includes(":") ? name : `${name}:latest`);

function isUsable(c: ModelChoice, p: ProvidersResponse): boolean {
  const prov = p.providers.find((x) => x.id === c.provider);
  if (!prov || !prov.available) return false;
  // A local model must really be on disk; cloud/custom models are taken at their word.
  if (c.provider === "ollama") {
    return prov.models.some((m) => m.installed && withTag(m.model) === withTag(c.model));
  }
  return true;
}

/**
 * The model to use: the user's saved pick if it still works, else the backend default if it
 * works, else the first model actually installed in Ollama. A fresh install otherwise defaults to
 * a model the machine may not have, and the first message would just fail.
 */
export function resolveChoice(saved: ModelChoice | null, p: ProvidersResponse | null): ModelChoice | null {
  if (!p) return saved;
  if (saved && isUsable(saved, p)) return saved;
  const def: ModelChoice = { provider: p.default.provider, model: p.default.model };
  if (isUsable(def, p)) return def;
  const ollama = p.providers.find((x) => x.id === "ollama");
  const first = ollama?.available ? ollama.models.find((m) => m.installed) : undefined;
  if (first) return { provider: "ollama", model: first.model, custom_model_id: first.custom_id };
  return saved ?? def;
}
