import { useCallback } from "react";

import EChart from "./EChart";
import type { Palette } from "./EChart";

export interface HeatCell {
  name: string;
  /** area weight (volume when known, otherwise 1) */
  weight: number;
  /** percent change, null when there is no quote yet */
  change: number | null;
}

/**
 * Watchlist heat map: tile area is trading volume (equal when unknown), colour is the day's move.
 * Flat fills in the semantic hues, stepped by size of move; tiles with no quote stay neutral.
 */
export default function MarketHeat({ cells, height = 260 }: { cells: HeatCell[]; height?: number }) {
  const option = useCallback(
    (p: Palette) => ({
      animationDuration: 600,
      tooltip: {
        backgroundColor: p.surface,
        borderColor: p.border,
        textStyle: { color: p.text, fontFamily: p.mono, fontSize: 12 },
        formatter: (i: { name: string; data: { change: number | null } }) =>
          `${i.name}  ${i.data.change == null ? "no quote" : `${i.data.change >= 0 ? "+" : ""}${i.data.change.toFixed(2)}%`}`,
      },
      series: [
        {
          type: "treemap",
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          left: 0,
          right: 0,
          top: 0,
          bottom: 0,
          squareRatio: 1.3,
          itemStyle: { borderColor: p.card, borderWidth: 3, gapWidth: 2, borderRadius: 4 },
          label: {
            show: true,
            position: "insideTopLeft",
            padding: [8, 10],
            color: "#fff",
            fontFamily: p.mono,
            fontWeight: 700,
            fontSize: 14,
            formatter: (i: { name: string; data: { change: number | null } }) =>
              `${i.name}\n${i.data.change == null ? "–" : `${i.data.change >= 0 ? "+" : ""}${i.data.change.toFixed(2)}%`}`,
          },
          data: cells.map((c) => {
            const ch = c.change;
            const color = ch == null ? p.border : ch >= 0 ? p.green : p.red;
            const strength = ch == null ? 0.5 : Math.abs(ch) >= 2 ? 1 : Math.abs(ch) >= 1 ? 0.78 : Math.abs(ch) >= 0.3 ? 0.58 : 0.4;
            return { name: c.name, value: Math.max(c.weight, 1), change: ch, itemStyle: { color, opacity: strength } };
          }),
        },
      ],
    }),
    [cells],
  );
  return <EChart option={option} height={height} label="Watchlist heat map: size is volume, colour is the day's change" />;
}
