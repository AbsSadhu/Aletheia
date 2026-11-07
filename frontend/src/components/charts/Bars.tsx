import { useCallback } from "react";
import type { EChartsCoreOption } from "echarts/core";

import EChart, { axisStyle, baseOption } from "./EChart";
import type { Palette } from "./EChart";

/**
 * Plain bars. With `signed`, gains are green and losses rose; otherwise every bar is the same
 * neutral orange (for counts, where a colour would suggest a verdict that is not there).
 */
export function Bars({
  items,
  signed = false,
  format = (v: number) => String(v),
  height = 220,
  label,
}: {
  items: { label: string; value: number }[];
  signed?: boolean;
  format?: (v: number) => string;
  height?: number;
  label: string;
}) {
  const option = useCallback(
    (p: Palette): EChartsCoreOption => {
      const ax = axisStyle(p);
      return {
        ...baseOption(p),
        grid: { left: 8, right: 14, top: 14, bottom: 8, containLabel: true },
        tooltip: { ...(baseOption(p).tooltip as object), valueFormatter: (v: number) => format(Number(v)) },
        xAxis: { type: "category", data: items.map((i) => i.label), ...ax, splitLine: { show: false }, axisLabel: { ...ax.axisLabel, hideOverlap: true } },
        yAxis: { type: "value", ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => format(v) } },
        series: [
          {
            type: "bar",
            barCategoryGap: "28%",
            itemStyle: { borderRadius: [2, 2, 0, 0] },
            data: items.map((i) => ({ value: i.value, itemStyle: { color: signed ? (i.value >= 0 ? p.green : p.red) : p.orange } })),
          },
        ],
      };
    },
    [items, signed, format],
  );
  return <EChart option={option} height={height} label={label} />;
}
