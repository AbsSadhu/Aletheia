// One place that decides whether a verdict reads as good, bad or neutral, so every page colours
// BUY / POSITIVE / UNDERVALUED / BULLISH_OI the same way.
const POSITIVE = new Set(["BUY", "POSITIVE", "STRONGLY_POSITIVE", "UNDERVALUED", "BULLISH_OI"]);
const NEGATIVE = new Set(["SELL", "REDUCE", "NEGATIVE", "STRONGLY_NEGATIVE", "OVERVALUED", "BEARISH_OI"]);

/** CSS class for a verdict badge: `badge-buy`, `badge-reduce` or `badge-hold`. */
export function toneBadge(verdict: string): string {
  if (POSITIVE.has(verdict)) return "badge-buy";
  if (NEGATIVE.has(verdict)) return "badge-reduce";
  return "badge-hold";
}
