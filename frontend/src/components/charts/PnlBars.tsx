import { useCallback, useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";

import EChart, { axisStyle, baseOption } from "./EChart";
import type { Palette } from "./EChart";

export interface PnlTrade {
  label: string;
  time: string;
  pnl: number;
}

const inr = (v: number) => `${v < 0 ? "-" : ""}₹${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

/** One bar per closed trade (green gain, rose loss) with the running total drawn over it. */
export function PnlBars({ trades, height = 240 }: { trades: PnlTrade[]; height?: number }) {
  const ordered = useMemo(() => [...trades].sort((a, b) => a.time.localeCompare(b.time)), [trades]);
  const option = useCallback(
    (p: Palette): EChartsCoreOption => {
      const ax = axisStyle(p);
      let run = 0;
      const total = ordered.map((t) => (run += t.pnl));
      return {
        ...baseOption(p),
        tooltip: { ...(baseOption(p).tooltip as object), valueFormatter: (v: number) => inr(Number(v)) },
        legend: { top: 0, right: 0, textStyle: { color: p.muted, fontFamily: p.sans }, itemWidth: 14, itemHeight: 3, icon: "rect" },
        grid: { left: 8, right: 14, top: 32, bottom: 8, containLabel: true },
        xAxis: { type: "category", data: ordered.map((t) => `${t.label} ${t.time.slice(5, 10)}`), ...ax, splitLine: { show: false }, axisLabel: { show: false } },
        yAxis: { type: "value", ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => inr(v) } },
        series: [
          {
            name: "Trade P&L",
            type: "bar",
            data: ordered.map((t) => ({ value: t.pnl, itemStyle: { color: t.pnl >= 0 ? p.green : p.red } })),
            barCategoryGap: "30%",
            itemStyle: { borderRadius: [2, 2, 0, 0] },
          },
          { name: "Running total", type: "line", data: total, showSymbol: false, lineStyle: { color: p.orange, width: 2 }, itemStyle: { color: p.orange } },
        ],
      };
    },
    [ordered],
  );
  return <EChart option={option} height={height} label="Realized profit and loss per trade with running total" />;
}
