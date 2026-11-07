import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, CustomChart, HeatmapChart, LineChart, RadarChart, TreemapChart, GaugeChart } from "echarts/charts";
import {
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  RadarComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";

echarts.use([
  BarChart,
  CustomChart,
  GaugeChart,
  HeatmapChart,
  LineChart,
  RadarChart,
  TreemapChart,
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  RadarComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

interface Props {
  /** Build the option from the current palette (re-run whenever the theme flips) */
  option: (p: Palette) => EChartsCoreOption;
  height?: number | string;
  className?: string;
  /** accessible summary for screen readers */
  label: string;
}

export interface Palette {
  text: string;
  muted: string;
  grid: string;
  border: string;
  surface: string;
  card: string;
  accent: string;
  orange: string;
  green: string;
  red: string;
  amber: string;
  teal: string;
  purple: string;
  mono: string;
  sans: string;
}

let canvasOk: boolean | null = null;
/** Headless and test environments have no 2D canvas; the chart then simply does not draw. */
function hasCanvas(): boolean {
  if (canvasOk === null) {
    try {
      const spy = console.error;
      console.error = () => undefined; // jsdom logs "not implemented" on getContext
      canvasOk = !!document.createElement("canvas").getContext("2d");
      console.error = spy;
    } catch {
      canvasOk = false;
    }
  }
  return canvasOk;
}

function css(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export function palette(): Palette {
  return {
    text: css("--text-primary", "#f4f1ee"),
    muted: css("--text-muted", "#6d6762"),
    grid: css("--border-subtle", "rgba(255,255,255,0.07)"),
    border: css("--border-medium", "rgba(255,255,255,0.14)"),
    surface: css("--bg-surface", "#070707"),
    card: css("--bg-card", "#0d0d0d"),
    accent: css("--accent", "#ff2b1c"),
    orange: css("--accent-2", "#ff7a00"),
    green: css("--green", "#1fd68a"),
    red: css("--red", "#ff5470"),
    amber: css("--amber", "#ffb020"),
    teal: css("--teal", "#2bd4c0"),
    purple: css("--purple", "#b57bff"),
    mono: css("--font-mono", "monospace"),
    sans: css("--font-sans", "sans-serif"),
  };
}

/** Shared axis and tooltip styling: flat, hairline grid, mono numerals. */
export function baseOption(p: Palette): EChartsCoreOption {
  return {
    animationDuration: 700,
    animationEasing: "quarticOut",
    textStyle: { fontFamily: p.sans, color: p.muted },
    grid: { left: 8, right: 14, top: 28, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      backgroundColor: p.surface,
      borderColor: p.border,
      borderWidth: 1,
      padding: [8, 10],
      textStyle: { color: p.text, fontFamily: p.mono, fontSize: 12 },
      axisPointer: { type: "line", lineStyle: { color: p.orange, width: 1 } },
    },
  };
}

export function axisStyle(p: Palette) {
  return {
    axisLine: { lineStyle: { color: p.border } },
    axisTick: { show: false },
    axisLabel: { color: p.muted, fontFamily: p.mono, fontSize: 11 },
    splitLine: { lineStyle: { color: p.grid } },
  };
}

/**
 * A small ECharts host. Canvas renderer, tree-shaken chart types, theme read from the CSS
 * variables, so the light/dark toggle re-skins every chart. Resizes with its container and
 * disposes with the component.
 */
export default function EChart({ option, height = 280, className = "", label }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const build = useRef(option);
  build.current = option;

  useEffect(() => {
    const el = host.current;
    if (!el || !hasCanvas()) return;
    let c: echarts.ECharts;
    try {
      c = echarts.init(el, undefined, { renderer: "canvas" });
    } catch {
      return; // no canvas (headless/test environments): the chart simply does not draw
    }
    chart.current = c;
    const apply = () => c.setOption(build.current(palette()), true);
    apply();
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el);
    const themeObs = new MutationObserver(apply);
    themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      themeObs.disconnect();
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
  }, []);

  // data or option changed
  useEffect(() => {
    chart.current?.setOption(option(palette()), true);
  }, [option]);

  return <div ref={host} className={className} style={{ width: "100%", height }} role="img" aria-label={label} />;
}
