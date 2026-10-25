import { describe, expect, it } from "vitest";

import { applyTick, barStart } from "./chartBars";
import type { Candle } from "./chartBars";

const IST = 19800;
const bar = (time: number, o: number, h: number, l: number, c: number): Candle => ({
  time,
  open: o,
  high: h,
  low: l,
  close: c,
  volume: 1,
});

describe("barStart", () => {
  it("buckets by interval in shifted (IST) time", () => {
    // 2026-10-26 04:03:30 UTC = 09:33:30 IST -> the 09:30 IST 5m bar
    const t = Date.UTC(2026, 9, 26, 4, 3, 30) / 1000;
    const start = barStart(t, "5m", IST);
    expect(new Date((start - IST) * 1000).toISOString()).toBe("2026-10-26T04:00:00.000Z");
    expect(start % 300).toBe(0);
  });

  it("daily bars land on UTC midnight with no offset", () => {
    const t = Date.UTC(2026, 9, 26, 10, 0, 0) / 1000;
    expect(barStart(t, "1d", 0)).toBe(Date.UTC(2026, 9, 26) / 1000);
  });
});

describe("applyTick", () => {
  const t0 = Date.UTC(2026, 9, 26, 4, 0, 0) / 1000;
  const start = barStart(t0, "5m", IST);

  it("extends the current bar's high, low and close", () => {
    const bars = [bar(start, 100, 101, 99, 100.5)];
    expect(applyTick(bars, 102, t0 + 60, "5m", IST)).toMatchObject({ time: start, open: 100, high: 102, low: 99, close: 102 });
    expect(applyTick(bars, 98, t0 + 60, "5m", IST)).toMatchObject({ high: 101, low: 98, close: 98 });
  });

  it("opens a new bar from the previous close when the bucket rolls over", () => {
    const bars = [bar(start, 100, 101, 99, 100.5)];
    const next = applyTick(bars, 103, t0 + 301, "5m", IST)!;
    expect(next.time).toBe(start + 300);
    expect(next).toMatchObject({ open: 100.5, high: 103, low: 100.5, close: 103 });
  });

  it("ignores a price older than the last bar instead of rewriting history", () => {
    const bars = [bar(start + 300, 100, 101, 99, 100)];
    expect(applyTick(bars, 120, t0, "5m", IST)).toBeNull();
  });

  it("starts the first bar when there is no history", () => {
    expect(applyTick([], 50, t0, "5m", IST)).toMatchObject({ open: 50, high: 50, low: 50, close: 50 });
  });
});
