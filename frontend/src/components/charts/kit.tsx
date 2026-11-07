import { useCallback } from "react";

import EChart, { axisStyle, baseOption } from "./EChart";
import type { Palette } from "./EChart";

export interface Series {
  name: string;
  data: number[];
  /** "accent" = brand red (the subject), others use the semantic hues */
  tone?: "accent" | "orange" | "amber" | "teal" | "green" | "purple" | "muted";
  /** draw as the filled hero series */
  area?: boolean;
  dashed?: boolean;
}

const tone = (p: Palette, t: Series["tone"]) =>
  ({ accent: p.accent, orange: p.orange, amber: p.amber, teal: p.teal, green: p.green, purple: p.purple, muted: p.muted })[t ?? "accent"];

/**
 * Multi-series line chart with a flat translucent area under the hero series, a zoom slider, and
 * a mono tooltip. The y axis format is supplied by the caller.
 */
export function LineArea({
  x,
  series,
  format,
  height = 300,
  zoom = true,
  label,
}: {
  x: string[];
  series: Series[];
  format: (v: number) => string;
  height?: number;
  zoom?: boolean;
  label: string;
}) {
  const option = useCallback(
    (p: Palette) => {
      const ax = axisStyle(p);
      return {
        ...baseOption(p),
        legend: series.length > 1 ? { top: 0, right: 0, textStyle: { color: p.muted, fontFamily: p.sans }, itemWidth: 14, itemHeight: 3, icon: "rect" } : undefined,
        grid: { left: 8, right: 14, top: series.length > 1 ? 32 : 16, bottom: zoom ? 44 : 8, containLabel: true },
        tooltip: { ...(baseOption(p).tooltip as object), valueFormatter: (v: number) => format(Number(v)) },
        xAxis: { type: "category", data: x, boundaryGap: false, ...ax, splitLine: { show: false }, axisLabel: { ...ax.axisLabel, hideOverlap: true } },
        yAxis: { type: "value", scale: true, ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => format(v) } },
        dataZoom: zoom
          ? [
              { type: "inside" },
              { type: "slider", height: 16, bottom: 6, borderColor: p.border, backgroundColor: "transparent", fillerColor: "rgba(255,122,0,0.16)", handleStyle: { color: p.orange, borderColor: p.orange }, moveHandleStyle: { color: p.border }, textStyle: { color: p.muted }, dataBackground: { lineStyle: { color: p.border }, areaStyle: { color: p.grid } }, selectedDataBackground: { lineStyle: { color: p.orange }, areaStyle: { color: p.grid } } },
            ]
          : undefined,
        series: series.map((s) => ({
          name: s.name,
          type: "line",
          data: s.data,
          showSymbol: false,
          smooth: false,
          sampling: "lttb",
          lineStyle: { width: s.area ? 2.4 : 1.6, color: tone(p, s.tone), type: s.dashed ? "dashed" : "solid" },
          itemStyle: { color: tone(p, s.tone) },
          areaStyle: s.area ? { color: tone(p, s.tone), opacity: 0.1 } : undefined,
          emphasis: { focus: "series" },
        })),
      };
    },
    [x, series, format, zoom],
  );
  return <EChart option={option} height={height} label={label} />;
}

/** Underwater chart: how far below its previous peak a value series sits, in percent. */
export function Drawdown({ x, values, height = 150, label }: { x: string[]; values: number[]; height?: number; label: string }) {
  let peak = -Infinity;
  const dd = values.map((v) => {
    peak = Math.max(peak, v);
    return peak > 0 ? ((v - peak) / peak) * 100 : 0;
  });
  const option = useCallback(
    (p: Palette) => {
      const ax = axisStyle(p);
      return {
        ...baseOption(p),
        grid: { left: 8, right: 14, top: 10, bottom: 8, containLabel: true },
        tooltip: { ...(baseOption(p).tooltip as object), valueFormatter: (v: number) => `${Number(v).toFixed(2)}%` },
        xAxis: { type: "category", data: x, boundaryGap: false, ...ax, splitLine: { show: false }, axisLabel: { show: false } },
        yAxis: { type: "value", max: 0, ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => `${v.toFixed(0)}%` } },
        series: [
          { name: "Drawdown", type: "line", data: dd, showSymbol: false, step: "end", lineStyle: { width: 1.4, color: p.red }, areaStyle: { color: p.red, opacity: 0.18 } },
        ],
      };
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [x, values],
  );
  return <EChart option={option} height={height} label={label} />;
}

/** Histogram of period-over-period returns, bars coloured by sign. */
export function ReturnsHistogram({ values, height = 200, label }: { values: number[]; height?: number; label: string }) {
  const rets = values.slice(1).map((v, i) => (values[i] > 0 ? ((v - values[i]) / values[i]) * 100 : 0));
  const lo = Math.min(...rets, 0);
  const hi = Math.max(...rets, 0);
  const bins = 24;
  const w = (hi - lo) / bins || 1;
  const counts = Array.from({ length: bins }, () => 0);
  rets.forEach((r) => (counts[Math.min(bins - 1, Math.floor((r - lo) / w))] += 1));
  const centers = counts.map((_, i) => lo + w * (i + 0.5));
  const option = useCallback(
    (p: Palette) => {
      const ax = axisStyle(p);
      return {
        ...baseOption(p),
        grid: { left: 8, right: 14, top: 10, bottom: 8, containLabel: true },
        tooltip: { ...(baseOption(p).tooltip as object), trigger: "axis", valueFormatter: (v: number) => `${v} periods` },
        xAxis: { type: "category", data: centers.map((c) => `${c.toFixed(2)}%`), ...ax, splitLine: { show: false }, axisLabel: { ...ax.axisLabel, interval: 3 } },
        yAxis: { type: "value", ...ax },
        series: [
          { type: "bar", data: counts.map((c, i) => ({ value: c, itemStyle: { color: centers[i] >= 0 ? p.green : p.red } })), barCategoryGap: "12%", itemStyle: { borderRadius: [2, 2, 0, 0] } },
        ],
      };
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [values],
  );
  return <EChart option={option} height={height} label={label} />;
}
