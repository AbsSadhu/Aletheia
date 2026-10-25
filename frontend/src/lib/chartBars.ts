export type Interval = "1m" | "5m" | "15m" | "1h" | "1d";

export const INTERVALS: Interval[] = ["1m", "5m", "15m", "1h", "1d"];

export interface Candle {
  time: number; // epoch seconds (already shifted by tz_offset_secs for display)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const SECONDS: Record<Interval, number> = { "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400 };

/** Start (epoch s) of the bar a timestamp falls into. `offset` is the display shift in seconds. */
export function barStart(epochSecs: number, interval: Interval, offset: number): number {
  const size = SECONDS[interval];
  const shifted = epochSecs + offset;
  return Math.floor(shifted / size) * size;
}

/**
 * Fold one live price into the bar list, returning the updated last bar (or null if the price
 * is older than the last bar, i.e. out of order). Opens a new bar when the price falls into a
 * later bucket. Pure: the caller decides how to render the result.
 */
export function applyTick(
  bars: Candle[],
  price: number,
  epochSecs: number,
  interval: Interval,
  offset: number,
): Candle | null {
  const start = barStart(epochSecs, interval, offset);
  const last = bars[bars.length - 1];
  if (last && start < last.time) return null;
  if (last && start === last.time) {
    return {
      ...last,
      high: Math.max(last.high, price),
      low: Math.min(last.low, price),
      close: price,
    };
  }
  const open = last ? last.close : price;
  return { time: start, open, high: Math.max(open, price), low: Math.min(open, price), close: price, volume: 0 };
}
