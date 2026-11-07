import { useCallback } from "react";

import EChart from "./EChart";
import type { Palette } from "./EChart";
import type { EChartsCoreOption } from "echarts/core";

export interface RadarFactor {
  name: string;
  /** 0..1 */
  normalized: number;
}

/** Factor profile: one spoke per factor, a flat filled polygon of the normalised readings. */
export default function FactorRadar({ factors, height = 300 }: { factors: RadarFactor[]; height?: number }) {
  const option = useCallback(
    (p: Palette): EChartsCoreOption => ({
      animationDuration: 800,
      animationEasing: "quarticOut",
      tooltip: {
        backgroundColor: p.surface,
        borderColor: p.border,
        textStyle: { color: p.text, fontFamily: p.mono, fontSize: 12 },
      },
      radar: {
        radius: "66%",
        splitNumber: 4,
        indicator: factors.map((f) => ({ name: f.name.replace(/_/g, " "), max: 1 })),
        axisName: { color: p.muted, fontFamily: p.mono, fontSize: 10.5 },
        axisLine: { lineStyle: { color: p.grid } },
        splitLine: { lineStyle: { color: p.grid } },
        splitArea: { show: false },
      },
      series: [
        {
          type: "radar",
          symbol: "circle",
          symbolSize: 5,
          data: [
            {
              name: "Normalised reading",
              value: factors.map((f) => Math.max(0, Math.min(1, f.normalized))),
              lineStyle: { color: p.accent, width: 2 },
              itemStyle: { color: p.orange },
              areaStyle: { color: p.accent, opacity: 0.14 },
            },
          ],
        },
      ],
    }),
    [factors],
  );
  return <EChart option={option} height={height} label="Radar of normalised factor readings" />;
}
