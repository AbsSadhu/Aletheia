import { describe, expect, it } from "vitest";

import { resolveChoice } from "./chatApi";
import type { ProvidersResponse } from "./chatApi";

const model = (name: string, installed = true) => ({ model: name, label: name, installed, custom_id: null });
const providers = (over: Partial<ProvidersResponse> = {}, ollamaModels = [model("gemma4:e4b"), model("qwen3.5:9b")]): ProvidersResponse => ({
  default: { provider: "ollama", model: "mistral:7b" },
  providers: [
    { id: "ollama", label: "Ollama", configured: true, available: true, error: null, models: ollamaModels },
    { id: "anthropic", label: "Claude", configured: false, available: false, error: "no key", models: [model("claude-haiku-4-5")] },
  ],
  ...over,
});

describe("resolveChoice", () => {
  it("falls back to an installed model when the default isn't on disk (fresh install)", () => {
    expect(resolveChoice(null, providers())).toMatchObject({ provider: "ollama", model: "gemma4:e4b" });
  });
  it("keeps a saved pick that still works", () => {
    const saved = { provider: "ollama" as const, model: "qwen3.5:9b" };
    expect(resolveChoice(saved, providers())).toBe(saved);
  });
  it("drops a saved pick whose model was removed from disk", () => {
    const saved = { provider: "ollama" as const, model: "gone:1b" };
    expect(resolveChoice(saved, providers())?.model).toBe("gemma4:e4b");
  });
  it("uses the backend default when it is installed, and treats name and name:latest alike", () => {
    expect(resolveChoice(null, providers({}, [model("mistral:7b")]))?.model).toBe("mistral:7b");
    expect(resolveChoice(null, providers({ default: { provider: "ollama", model: "llama3" } }, [model("llama3:latest")]))?.model).toBe("llama3");
  });
  it("does not pick a cloud provider with no key, and passes through while providers load", () => {
    const saved = { provider: "anthropic" as const, model: "claude-haiku-4-5" };
    expect(resolveChoice(saved, providers())?.provider).toBe("ollama");
    expect(resolveChoice(saved, null)).toBe(saved);
  });
  it("leaves things alone when Ollama is down and nothing else works", () => {
    const p = providers();
    p.providers[0] = { ...p.providers[0], available: false, models: [] };
    expect(resolveChoice(null, p)).toMatchObject({ provider: "ollama", model: "mistral:7b" });
  });
});
