import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { NewsPulse, SentimentAlert } from "./api";

const alert = (id: string, minutesAhead: number): SentimentAlert => ({
  id,
  t: new Date(Date.now() + minutesAhead * 60_000).toISOString(),
  symbol: "INFY",
  from: "bullish",
  to: "bearish",
  score: -0.41,
  mentions: 4,
  headline: null,
});

const pulse = (alerts: SentimentAlert[]): NewsPulse => ({
  mood: { value: 0, label: "neutral", window_hours: 6, counts: { bullish: 0, bearish: 0, neutral: 0 }, headlines: 0 },
  history: [],
  tracker: [],
  movers: [],
  alerts,
  sources: {},
  updated_at: null,
  method: "",
});

describe("newsStore", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  async function load(alerts: SentimentAlert[]) {
    const notify = vi.fn();
    vi.doMock("./api", () => ({ getNewsPulse: async () => pulse(alerts), getNewsHeadlines: async () => ({ headlines: [] }) }));
    vi.doMock("./desktop", () => ({ notifySentimentFlip: notify }));
    const store = await import("./newsStore");
    return { store, notify };
  }

  it("polls at least every 30 seconds", async () => {
    const { store } = await load([]);
    expect(store.POLL_MS).toBeLessThanOrEqual(30_000);
  });

  it("raises a toast, an unread count and a notification for a new flip, once", async () => {
    const { store, notify } = await load([alert("a1", 5)]);
    const { result } = renderHook(() => store.useNews());
    await act(async () => {
      await store.refreshNews();
      await store.refreshNews(); // the same alert comes back on the next poll
    });
    expect(result.current.toasts).toHaveLength(1);
    expect(result.current.unread).toBe(1);
    expect(notify).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledWith("INFY", "bullish", "bearish", undefined);
    act(() => store.markAlertsRead());
    expect(result.current.unread).toBe(0);
  });

  it("does not announce alerts that predate the first run", async () => {
    const { store, notify } = await load([alert("old", -30)]);
    await store.refreshNews();
    expect(notify).not.toHaveBeenCalled();
  });
});
