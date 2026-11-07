import { useCallback } from "react";
import type { EChartsCoreOption } from "echarts/core";

import EChart from "./EChart";
import type { Palette } from "./EChart";

/**
 * Correlation matrix as a heat map in flat bands: green where assets move apart (they diversify),
 * grey near zero, amber to red where they move together. Cells carry their value.
 */
export function CorrelationMatrix({ labels, matrix, height }: { labels: string[]; matrix: (number | null)[][]; height?: number }) {
  const option = useCallback(
    (p: Palette): EChartsCoreOption => {
      const data: [number, number, number | string][] = [];
      matrix.forEach((row, y) => row.forEach((v, x) => data.push([x, y, v == null ? "-" : v])));
      return {
        animationDuration: 500,
        tooltip: {
          backgroundColor: p.surface,
          borderColor: p.border,
          textStyle: { color: p.text, fontFamily: p.mono, fontSize: 12 },
          formatter: (i: { data: [number, number, number | string] }) => `${labels[i.data[1]]} / ${labels[i.data[0]]}: ${i.data[2]}`,
        },
        grid: { left: 8, right: 8, top: 8, bottom: 8, containLabel: true },
        xAxis: { type: "category", data: labels, position: "top", splitArea: { show: false }, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: p.muted, fontFamily: p.mono, fontSize: 11, rotate: 35 } },
        yAxis: { type: "category", data: labels, inverse: true, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: p.muted, fontFamily: p.mono, fontSize: 11 } },
        visualMap: {
          show: false,
          type: "piecewise",
          dimension: 2,
          pieces: [
            { lt: -0.2, color: p.green },
            { gte: -0.2, lt: 0.2, color: p.border },
            { gte: 0.2, lt: 0.5, color: p.amber },
            { gte: 0.5, lt: 0.8, color: p.orange },
            { gte: 0.8, color: p.accent },
          ],
          outOfRange: { color: p.card },
        },
        series: [
          {
            type: "heatmap",
            data,
            itemStyle: { borderColor: p.card, borderWidth: 2, borderRadius: 3 },
            label: { show: labels.length <= 14, formatter: (i: { data: [number, number, number | string] }) => (typeof i.data[2] === "number" ? i.data[2].toFixed(2) : ""), color: "#fff", fontFamily: p.mono, fontSize: 10.5, fontWeight: 600 },
            emphasis: { itemStyle: { borderColor: p.orange, borderWidth: 2 } },
          },
        ],
      };
    },
    [labels, matrix],
  );
  return <EChart option={option} height={height ?? Math.max(260, labels.length * 34 + 70)} label="Correlation matrix of daily returns" />;
}
