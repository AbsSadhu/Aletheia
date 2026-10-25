import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  createChart,
} from "lightweight-charts";
import type { IChartApi, ISeriesApi, UTCTimestamp } from "lightweight-charts";

import { getCandles } from "../lib/api";
import type { LiveQuote } from "../lib/api";
import { INTERVALS, applyTick } from "../lib/chartBars";
import type { Candle, Interval } from "../lib/chartBars";

function cssVar(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function palette() {
  return {
    bg: cssVar("--bg-card", "#161c2a"),
    text: cssVar("--text-secondary", "#8b95a8"),
    grid: cssVar("--border-subtle", "rgba(255,255,255,0.06)"),
    up: cssVar("--green", "#22c55e"),
    down: cssVar("--red", "#ef4444"),
  };
}

interface Props {
  symbol: string;
  exchange: string;
  /** Latest quote from the live feed; each update moves the last candle. */
  quote?: LiveQuote;
  height?: number;
}

export default function PriceChart({ symbol, exchange, quote, height = 460 }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candles = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volume = useRef<ISeriesApi<"Histogram"> | null>(null);
  const bars = useRef<Candle[]>([]);
  const offset = useRef(0);

  const [interval, setIntervalState] = useState<Interval>("5m");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("");
  const [note, setNote] = useState("");

  // Create / destroy the chart once.
  useEffect(() => {
    if (!box.current) return;
    const p = palette();
    const c = createChart(box.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: p.bg }, textColor: p.text },
      grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
      rightPriceScale: { borderColor: p.grid },
      timeScale: { borderColor: p.grid, timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
    });
    candles.current = c.addSeries(CandlestickSeries, {
      upColor: p.up,
      downColor: p.down,
      wickUpColor: p.up,
      wickDownColor: p.down,
      borderVisible: false,
    });
    volume.current = c.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      color: p.grid,
    });
    volume.current.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    chart.current = c;

    // Follow the app's light/dark toggle.
    const obs = new MutationObserver(() => {
      const n = palette();
      c.applyOptions({
        layout: { background: { type: ColorType.Solid, color: n.bg }, textColor: n.text },
        grid: { vertLines: { color: n.grid }, horzLines: { color: n.grid } },
      });
      candles.current?.applyOptions({
        upColor: n.up,
        downColor: n.down,
        wickUpColor: n.up,
        wickDownColor: n.down,
      });
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    return () => {
      obs.disconnect();
      c.remove();
      chart.current = candles.current = volume.current = null;
    };
  }, []);

  // Load history when the symbol or interval changes.
  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    bars.current = [];
    candles.current?.setData([]);
    volume.current?.setData([]);
    getCandles(symbol, exchange, interval)
      .then((res) => {
        if (cancelled) return;
        offset.current = res.tz_offset_secs;
        bars.current = res.candles.map((c) => ({ ...c, time: c.time + res.tz_offset_secs }));
        const p = palette();
        candles.current?.setData(bars.current.map((b) => ({ ...b, time: b.time as UTCTimestamp })));
        volume.current?.setData(
          bars.current.map((b) => ({
            time: b.time as UTCTimestamp,
            value: b.volume,
            color: b.close >= b.open ? `${p.up}55` : `${p.down}55`,
          })),
        );
        chart.current?.timeScale().fitContent();
        setNote(res.note);
        setStatus("ready");
      })
      .catch((e) => {
        if (cancelled) return;
        setMessage(e instanceof Error ? e.message : "Could not load the chart");
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, exchange, interval]);

  // Move the last candle with every live price.
  useEffect(() => {
    if (!quote || status !== "ready" || !candles.current) return;
    const t = Date.parse(quote.as_of);
    if (Number.isNaN(t)) return;
    const bar = applyTick(bars.current, quote.close, t / 1000, interval, offset.current);
    if (!bar) return;
    const last = bars.current[bars.current.length - 1];
    if (last && last.time === bar.time) bars.current[bars.current.length - 1] = bar;
    else bars.current.push(bar);
    candles.current.update({ ...bar, time: bar.time as UTCTimestamp });
  }, [quote, status, interval]);

  return (
    <div>
      <div role="group" aria-label="Chart interval" style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-2)" }}>
        {INTERVALS.map((i) => (
          <button
            key={i}
            type="button"
            className={`btn ${i === interval ? "btn-primary" : "btn-ghost"}`}
            aria-pressed={i === interval}
            onClick={() => setIntervalState(i)}
          >
            {i === "1d" ? "1D" : i}
          </button>
        ))}
      </div>
      <div style={{ position: "relative", height }}>
        <div ref={box} data-testid="price-chart" style={{ height: "100%", width: "100%" }} />
        {status !== "ready" && (
          <div
            role={status === "error" ? "alert" : "status"}
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              padding: "var(--space-4)",
              color: status === "error" ? "var(--red)" : "var(--text-muted)",
            }}
          >
            {status === "loading" ? "Loading chart…" : message}
          </div>
        )}
      </div>
      {note && (
        <p style={{ color: "var(--text-muted)", fontSize: "var(--text-xs)", marginTop: "var(--space-2)" }}>{note}</p>
      )}
    </div>
  );
}
