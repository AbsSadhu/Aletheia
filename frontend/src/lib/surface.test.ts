import { describe, expect, it } from "vitest";

import { formatMetric, normalise, rampColor, valueAt } from "./surface";
import type { SurfaceData } from "./surface";

// values[i][j] = days[i] * 10 + spots[j] / 10, a plane, so interpolation can be checked exactly.
const spots = [80, 100, 120];
const days = [1, 31, 61];
const data: SurfaceData = {
  metric: "price",
  kind: "call",
  strike: 100,
  spots,
  days,
  values: days.map((d) => spots.map((s) => d * 10 + s / 10)),
  min: 18,
  max: 622,
};

describe("surface data", () => {
  it("returns grid values exactly at grid points", () => {
    expect(valueAt(data, 100, 31)).toBeCloseTo(31 * 10 + 10);
    expect(valueAt(data, 80, 1)).toBeCloseTo(18);
    expect(valueAt(data, 120, 61)).toBeCloseTo(622);
  });

  it("interpolates between grid points", () => {
    // halfway in spot (110) and days (16): a plane, so the exact value is known.
    expect(valueAt(data, 110, 16)).toBeCloseTo(16 * 10 + 11);
    expect(valueAt(data, 90, 46)).toBeCloseTo(46 * 10 + 9);
  });

  it("is null off the grid, never extrapolated", () => {
    expect(valueAt(data, 79.9, 10)).toBeNull();
    expect(valueAt(data, 100, 0.5)).toBeNull();
    expect(valueAt(data, 130, 10)).toBeNull();
  });

  it("normalises into 0..1 and tolerates a flat surface", () => {
    expect(normalise(18, 18, 622)).toBe(0);
    expect(normalise(622, 18, 622)).toBe(1);
    expect(normalise(5, 5, 5)).toBe(0.5);
  });

  it("maps low to dark and high to light, staying inside 0..1", () => {
    const lo = rampColor(0);
    const hi = rampColor(1);
    expect(lo[0] + lo[1] + lo[2]).toBeLessThan(hi[0] + hi[1] + hi[2]);
    for (const t of [-1, 0, 0.2, 0.5, 0.9, 1, 3]) {
      for (const c of rampColor(t)) expect(c >= 0 && c <= 1).toBe(true);
    }
  });

  it("formats each metric with a sensible precision", () => {
    expect(formatMetric("price", 5.12345)).toBe("5.12");
    expect(formatMetric("delta", 0.512345)).toBe("0.5123");
    expect(formatMetric("gamma", 0.0123456)).toBe("0.01235");
  });
});
