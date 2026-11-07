// The data side of the options 3D chart: kept free of three.js so it can be tested without a GPU.

export type SurfaceMetric = "price" | "delta" | "gamma" | "theta" | "vega";

export interface SurfaceData {
  metric: SurfaceMetric;
  kind: "call" | "put";
  strike: number;
  spots: number[];
  days: number[];
  /** values[i][j] is the metric at days[i] and spots[j] */
  values: number[][];
  min: number;
  max: number;
}

export const METRICS: { id: SurfaceMetric; label: string; hint: string }[] = [
  { id: "price", label: "Price", hint: "Option value" },
  { id: "delta", label: "Delta", hint: "Price change per 1 move in spot" },
  { id: "gamma", label: "Gamma", hint: "Change in delta per 1 move in spot" },
  { id: "theta", label: "Theta", hint: "Value lost per calendar day" },
  { id: "vega", label: "Vega", hint: "Value change per volatility point" },
];

/** Index of the grid cell [i, i+1] that contains x (clamped), plus the fraction within it. */
function locate(axis: number[], x: number): { i: number; f: number } | null {
  const lo = axis[0];
  const hi = axis[axis.length - 1];
  if (x < lo || x > hi || axis.length < 2) return null;
  let i = 0;
  while (i < axis.length - 2 && x > axis[i + 1]) i++;
  const span = axis[i + 1] - axis[i];
  return { i, f: span === 0 ? 0 : (x - axis[i]) / span };
}

/** The metric at an arbitrary (spot, days), interpolated between grid points; null if off the grid. */
export function valueAt(data: SurfaceData, spot: number, days: number): number | null {
  const a = locate(data.spots, spot);
  const b = locate(data.days, days);
  if (!a || !b) return null;
  const v = data.values;
  const top = v[b.i][a.i] * (1 - a.f) + v[b.i][a.i + 1] * a.f;
  const bottom = v[b.i + 1][a.i] * (1 - a.f) + v[b.i + 1][a.i + 1] * a.f;
  return top * (1 - b.f) + bottom * b.f;
}

/** 0..1 position of v within [min, max] (0.5 when the surface is flat). */
export function normalise(v: number, min: number, max: number): number {
  return max === min ? 0.5 : (v - min) / (max - min);
}

// Low to high, in flat bands (no blending): black ember, deep red, brand red, brand orange, amber.
export const BANDS: [number, number, number][] = [
  [0.1, 0.02, 0.02],
  [0.42, 0.04, 0.03],
  [1.0, 0.17, 0.11],
  [1.0, 0.48, 0.0],
  [1.0, 0.72, 0.2],
];

/** Colour for a normalised value: the flat band it falls in, as 0..1 RGB. */
export function rampColor(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t));
  return BANDS[Math.min(BANDS.length - 1, Math.floor(x * BANDS.length))];
}

export function formatMetric(metric: SurfaceMetric, v: number): string {
  const digits = metric === "gamma" ? 5 : metric === "price" ? 2 : 4;
  return v.toFixed(digits);
}
