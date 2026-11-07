// Black-Scholes for the payoff diagram. The Options page prices through the backend; this is the same
// closed form, used only to draw "value today" across a range of spots.

function normCdf(x: number): number {
  // Abramowitz and Stegun 26.2.17, accurate to about 7.5e-8
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989422804014327 * Math.exp((-x * x) / 2);
  const p = d * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  return x >= 0 ? 1 - p : p;
}

export function bsPrice(spot: number, strike: number, days: number, volPct: number, ratePct: number, kind: "call" | "put"): number {
  const t = Math.max(days, 0) / 365;
  const sigma = volPct / 100;
  const r = ratePct / 100;
  if (t === 0 || sigma === 0) {
    return kind === "call" ? Math.max(spot - strike, 0) : Math.max(strike - spot, 0);
  }
  const d1 = (Math.log(spot / strike) + (r + (sigma * sigma) / 2) * t) / (sigma * Math.sqrt(t));
  const d2 = d1 - sigma * Math.sqrt(t);
  return kind === "call"
    ? spot * normCdf(d1) - strike * Math.exp(-r * t) * normCdf(d2)
    : strike * Math.exp(-r * t) * normCdf(-d2) - spot * normCdf(-d1);
}

export interface PayoffPoint {
  spot: number;
  expiry: number;
  today: number;
}

/** P&L of a long option across spot, at expiry and priced today, net of the premium paid. */
export function payoffCurve(args: {
  strike: number;
  days: number;
  volPct: number;
  ratePct: number;
  kind: "call" | "put";
  premium: number;
  points?: number;
}): PayoffPoint[] {
  const { strike, days, volPct, ratePct, kind, premium, points = 61 } = args;
  const lo = strike * 0.6;
  const hi = strike * 1.4;
  return Array.from({ length: points }, (_, i) => {
    const spot = lo + ((hi - lo) * i) / (points - 1);
    const intrinsic = kind === "call" ? Math.max(spot - strike, 0) : Math.max(strike - spot, 0);
    return { spot, expiry: intrinsic - premium, today: bsPrice(spot, strike, days, volPct, ratePct, kind) - premium };
  });
}
