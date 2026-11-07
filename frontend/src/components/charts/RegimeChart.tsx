import { useCallback } from "react";
import type { EChartsCoreOption } from "echarts/core";

import EChart, { axisStyle, baseOption } from "./EChart";
import type { Palette } from "./EChart";

interface Props {
  dates: string[];
  smoothed: (number | null)[];
  fused: number[];
  enter: number;
  exit: number;
  height?: number;
}

/** Smoothed edge density over time, the enter and exit thresholds as lines, FUSED stretches shaded. */
export default function RegimeChart({ dates, smoothed, fused, enter, exit, height = 300 }: Props) {
  const option = useCallback(
    (p: Palette): EChartsCoreOption => {
      const ax = axisStyle(p);
      // contiguous runs of fused bars as [start, end] index pairs
      const runs: [number, number][] = [];
      let s = -1;
      fused.forEach((f, i) => {
        if (f && s < 0) s = i;
        if ((!f || i === fused.length - 1) && s >= 0) {
          runs.push([s, f ? i : i - 1]);
          s = -1;
        }
      });
      return {
        ...baseOption(p),
        grid: { left: 8, right: 14, top: 16, bottom: 28, containLabel: true },
        tooltip: { ...(baseOption(p).tooltip as object), valueFormatter: (v: number) => `${(Number(v) * 100).toFixed(0)}% of pairs` },
        xAxis: { type: "category", data: dates, boundaryGap: false, ...ax, splitLine: { show: false }, axisLabel: { ...ax.axisLabel, hideOverlap: true } },
        yAxis: { type: "value", min: 0, max: 1, ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => `${Math.round(v * 100)}%` } },
        series: [
          {
            name: "Share of pairs moving together",
            type: "line",
            data: smoothed,
            showSymbol: false,
            lineStyle: { width: 2.4, color: p.accent },
            areaStyle: { color: p.accent, opacity: 0.1 },
            markArea: {
              silent: true,
              itemStyle: { color: p.accent, opacity: 0.16 },
              data: runs.map(([a, b]) => [{ xAxis: dates[a] }, { xAxis: dates[b] }]),
            },
            markLine: {
              silent: true,
              symbol: "none",
              label: { color: p.muted, fontFamily: p.mono, fontSize: 10.5 },
              lineStyle: { type: "dashed", width: 1 },
              data: [
                { yAxis: enter, name: "enter", lineStyle: { color: p.orange }, label: { formatter: `enter ${Math.round(enter * 100)}%`, position: "insideEndTop", color: p.orange } },
                { yAxis: exit, name: "exit", lineStyle: { color: p.muted }, label: { formatter: `exit ${Math.round(exit * 100)}%`, position: "insideEndBottom" } },
              ],
            },
          },
        ],
      };
    },
    [dates, smoothed, fused, enter, exit],
  );
  return <EChart option={option} height={height} label="Correlation regime: share of asset pairs moving together over time" />;
}
