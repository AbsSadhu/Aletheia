// Pure helpers behind the chat's candlestick widget, so the data handling is testable without a
// canvas. Bars arrive as compact rows [epochSecs, open, high, low, close, volume].

export type BarRow = [number, number, number, number, number, number];
export type SeriesRow = [number, number];

export interface OhlcvDisplay {
  type: "ohlcv";
  symbol: string;
  currency: string;
  interval: string;
  /** seconds added to every timestamp so intraday NSE bars read in IST on the chart axis */
  tz_offset_secs: number;
  bars: BarRow[];
  overlays?: Record<string, SeriesRow[]>;
  panes?: Record<
    string,
    | { kind: "line"; levels?: number[]; series: SeriesRow[] }
    | { kind: "macd"; macd: SeriesRow[]; signal: SeriesRow[]; histogram: SeriesRow[] }
  >;
}

export interface TableDisplay {
  type: "table";
  title: string;
  rows: [string, string][];
  note?: string;
  /** optional square matrix (e.g. correlations) drawn as an interactive 3D bar chart */
  matrix?: { title?: string; labels: string[]; values: number[][] };
}

export interface LineDisplay {
  type: "line";
  title: string;
  x_label?: string;
  /** reference level, e.g. starting capital */
  baseline?: number;
  points: [number, number][];
}

export interface ProposalDisplay {
  type: "proposal";
  proposal_id: string;
  symbol: string;
  exchange: string;
  side: "BUY" | "SELL";
  quantity: number;
  order_type: "MARKET" | "LIMIT";
  limit_price: number | null;
  reference_price: number;
  estimated_value: number;
  currency: string;
  rationale: string;
}

export type ToolDisplay = OhlcvDisplay | TableDisplay | LineDisplay | ProposalDisplay;

export interface Bar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export function toBars(d: OhlcvDisplay): Bar[] {
  return d.bars.map(([t, o, h, l, c, v]) => ({
    time: t + d.tz_offset_secs,
    open: o,
    high: h,
    low: l,
    close: c,
    volume: v,
  }));
}

export function toSeries(rows: SeriesRow[], offset: number): { time: number; value: number }[] {
  return rows.map(([t, v]) => ({ time: t + offset, value: v }));
}

/** Percent change of a bar's close against the previous bar's close (or its own open for the first). */
export function changePct(bars: Bar[], index: number): number | null {
  const bar = bars[index];
  if (!bar) return null;
  const base = index > 0 ? bars[index - 1].close : bar.open;
  return base ? (bar.close / base - 1) * 100 : null;
}

const SYMBOLS: Record<string, string> = { INR: "₹", USD: "$", EUR: "€", GBP: "£", JPY: "¥" };

export function money(value: number, currency: string): string {
  const sym = SYMBOLS[currency] ?? `${currency} `;
  const digits = 2;
  return `${sym}${value.toLocaleString(currency === "INR" ? "en-IN" : "en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function compact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e7) return `${(value / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${(value / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return String(Math.round(value));
}
