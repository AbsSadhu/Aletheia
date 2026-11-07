import { ColorType, CrosshairMode } from "lightweight-charts";
import type { DeepPartial, ChartOptions } from "lightweight-charts";

// One look for every candlestick chart in the app (Live Market and the chat widget): flat panels,
// thin grid, theme colors read from the CSS variables so the light/dark toggle applies.

function cssVar(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export interface ChartPalette {
  bg: string;
  text: string;
  grid: string;
  border: string;
  up: string;
  down: string;
  accent: string;
  orange: string;
  amber: string;
  purple: string;
  muted: string;
}

export function chartPalette(): ChartPalette {
  return {
    bg: cssVar("--bg-surface", "#0a0a0c"),
    text: cssVar("--text-secondary", "#8b95a8"),
    grid: cssVar("--border-subtle", "rgba(255,255,255,0.06)"),
    border: cssVar("--border-medium", "rgba(255,255,255,0.12)"),
    up: cssVar("--green", "#1fd68a"),
    down: cssVar("--red", "#ff5470"),
    accent: cssVar("--accent", "#ff3d2e"),
    orange: cssVar("--accent-2", "#ff8a1f"),
    amber: cssVar("--amber", "#ffb020"),
    purple: cssVar("--purple", "#b57bff"),
    muted: cssVar("--text-muted", "#5a6478"),
  };
}

/** Options that depend on the palette, so they can be re-applied when the theme flips. */
export function themeOptions(p: ChartPalette): DeepPartial<ChartOptions> {
  return {
    layout: {
      background: { type: ColorType.Solid, color: p.bg },
      textColor: p.text,
      fontSize: 11,
      panes: { separatorColor: p.border },
    },
    grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
    rightPriceScale: { borderColor: p.border },
    timeScale: { borderColor: p.border },
  };
}

export function baseChartOptions(
  p: ChartPalette,
  opts: { intraday: boolean },
): DeepPartial<ChartOptions> {
  const theme = themeOptions(p);
  return {
    ...theme,
    autoSize: true,
    timeScale: {
      ...(theme.timeScale ?? {}),
      timeVisible: opts.intraday,
      secondsVisible: false,
    },
    crosshair: { mode: CrosshairMode.Normal },
  };
}

export function candleOptions(p: ChartPalette) {
  return {
    upColor: p.up,
    downColor: p.down,
    wickUpColor: p.up,
    wickDownColor: p.down,
    borderVisible: false,
    priceLineVisible: true,
    lastValueVisible: true,
  };
}

/** Volume bars take the candle's direction, translucent so they never fight the price. */
export function volumeColor(p: ChartPalette, close: number, open: number): string {
  return `${close >= open ? p.up : p.down}66`;
}

/** Re-apply theme colors when the app's data-theme attribute changes. Returns a disposer. */
export function followTheme(apply: (p: ChartPalette) => void): () => void {
  const obs = new MutationObserver(() => apply(chartPalette()));
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => obs.disconnect();
}
