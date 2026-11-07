import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { LineDisplay } from "../../../lib/ohlcv";

/** A plain line chart for non-price series such as a backtest equity curve. */
export default function LineWidget({ display }: { display: LineDisplay }) {
  const data = display.points.map(([x, y]) => ({ x, y }));
  if (data.length === 0) return <p className="chat-muted">No data.</p>;
  const first = data[0].y;
  const last = data[data.length - 1].y;
  const change = first ? (last / first - 1) * 100 : 0;
  return (
    <figure className="chat-line">
      <figcaption>
        <span>{display.title}</span>
        <span className={change >= 0 ? "pos" : "neg"}>
          {last.toLocaleString("en-IN", { maximumFractionDigits: 0 })} ({change >= 0 ? "+" : ""}
          {change.toFixed(2)}%)
        </span>
      </figcaption>
      <div className="chat-line-body">
        <ResponsiveContainer width="100%" height={170}>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
            <XAxis dataKey="x" tick={{ fontSize: 10, fill: "var(--text-muted)" }} stroke="var(--border-medium)" />
            <YAxis
              domain={["auto", "auto"]}
              width={52}
              tick={{ fontSize: 10, fill: "var(--text-muted)" }}
              stroke="var(--border-medium)"
              tickFormatter={(v: number) => v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
            />
            {display.baseline !== undefined && (
              <ReferenceLine y={display.baseline} stroke="var(--text-muted)" strokeDasharray="3 3" />
            )}
            <Tooltip
              contentStyle={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 3, fontSize: 11 }}
              labelFormatter={(x) => `${display.x_label ?? "Step"} ${x}`}
              formatter={(v) => [Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 }), "Equity"]}
            />
            <Line type="monotone" dataKey="y" stroke="var(--accent)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="chat-hint">{display.x_label ?? "Step"} on the x-axis; dashed line is the starting level.</p>
    </figure>
  );
}
