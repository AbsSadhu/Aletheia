import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  createRun,
  deletePortfolio,
  fetchHealth,
  getApiKey,
  getWebSocketUrl,
  listRuns,
  setApiKey,
} from "./api";

const BASE_URL = "http://127.0.0.1:8899";

function mockFetchOnce(body: unknown, init: Partial<Response> = {}) {
  const response = {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    statusText: init.statusText ?? "OK",
    json: async () => body,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  } as Response;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
  return response;
}

describe("api.ts auth wiring", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("getApiKey/setApiKey round-trip through localStorage", () => {
    expect(getApiKey()).toBe("");
    setApiKey("secret-123");
    expect(getApiKey()).toBe("secret-123");
    setApiKey("");
    expect(getApiKey()).toBe("");
  });

  it("apiGet omits X-API-Key when no key is configured (default open-auth case)", async () => {
    mockFetchOnce({ service: "ALETHEIA", status: "ok" });
    await fetchHealth();

    const [, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(options.headers).toEqual({});
  });

  it("apiGet attaches X-API-Key once a key is configured", async () => {
    setApiKey("secret-123");
    mockFetchOnce({ service: "ALETHEIA", status: "ok" });
    await fetchHealth();

    const [url, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/health`);
    expect(options.headers).toEqual({ "X-API-Key": "secret-123" });
  });

  it("apiPost sends Content-Type and the configured API key together", async () => {
    setApiKey("secret-123");
    mockFetchOnce({ summary: { run_id: "abc" } });
    await createRun("Analyze RELIANCE", undefined, true);

    const [url, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/runs?background=true`);
    expect(options.method).toBe("POST");
    expect(options.headers).toEqual({
      "Content-Type": "application/json",
      "X-API-Key": "secret-123",
    });
    expect(JSON.parse(options.body)).toEqual({ prompt: "Analyze RELIANCE", portfolio: undefined });
  });

  it("deletePortfolio sends DELETE with auth headers", async () => {
    setApiKey("secret-123");
    mockFetchOnce({});
    await deletePortfolio("Starter Portfolio");

    const [url, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/portfolios/Starter%20Portfolio`);
    expect(options.method).toBe("DELETE");
    expect(options.headers).toEqual({ "X-API-Key": "secret-123" });
  });

  it("propagates a readable error on a non-OK response instead of swallowing it", async () => {
    mockFetchOnce("Unauthorized", { ok: false, status: 401, statusText: "Unauthorized" });
    await expect(listRuns()).rejects.toThrow(/401/);
  });

  it("getWebSocketUrl produces a ws:// URL with no query param when no key is set", () => {
    expect(getWebSocketUrl("run-123")).toBe(`ws://127.0.0.1:8899/api/v1/ws/runs/run-123`);
  });

  it("getWebSocketUrl appends ?api_key= once a key is configured", () => {
    setApiKey("secret-123");
    expect(getWebSocketUrl("run-123")).toBe(
      `ws://127.0.0.1:8899/api/v1/ws/runs/run-123?api_key=secret-123`
    );
  });
});
