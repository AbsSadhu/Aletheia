import { useEffect, useRef, useState } from "react";
import { CandlestickSeries, HistogramSeries, createChart } from "lightweight-charts";
import type { IChartApi, ISeriesApi, MouseEventParams, UTCTimestamp } from "lightweight-charts";

import { getCandles } from "../lib/api";
import type { LiveQuote } from "../lib/api";
import { INTERVALS, applyTick } from "../lib/chartBars";
import type { Candle, Interval } from "../lib/chartBars";
import {
  baseChartOptions,
  candleOptions,
  chartPalette,
  followTheme,
  themeOptions,
  volumeColor,
} from "../lib/chartTheme";
import { compact } from "../lib/ohlcv";
import "../styles/chart.css";

interface Props {
  symbol: string;
  exchange: string;
  /** Latest quote from the live feed; each update moves the last candle. */
  quote?: LiveQuote;
  height?: number;
}

const price = (v: number) =>
  v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function PriceChart({ symbol, exchange, quote, height = 460 }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candles = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volume = useRef<ISeriesApi<"Histogram"> | null>(null);
  const bars = useRef<Candle[]>([]);
  const offset = useRef(0);
  const hovering = useRef(false);

  const [interval, setIntervalState] = useState<Interval>("5m");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("");
  const [note, setNote] = useState("");
  // The bar the legend describes: the one under the crosshair, else the latest (live) bar.
  const [shown, setShown] = useState<{ bar: Candle; prev: number | null } | null>(null);

  const showLast = () => {
    const all = bars.current;
    const last = all[all.length - 1];
    setShown(last ? { bar: last, prev: all.length > 1 ? all[all.length - 2].close : null } : null);
  };

  // Create / destroy the chart once.
  useEffect(() => {
    if (!box.current) return;
    const p = chartPalette();
    const c = createChart(box.current, baseChartOptions(p, { intraday: true }));
    candles.current = c.addSeries(CandlestickSeries, candleOptions(p));
    volume.current = c.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volume.current.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    chart.current = c;

    const onMove = (param: MouseEventParams) => {
      const t = typeof param.time === "number" ? param.time : null;
      const i = t === null ? -1 : bars.current.findIndex((b) => b.time === t);
      if (i < 0) {
        hovering.current = false;
        showLast();
        return;
      }
      hovering.current = true;
      setShown({ bar: bars.current[i], prev: i > 0 ? bars.current[i - 1].close : null });
    };
    c.subscribeCrosshairMove(onMove);

    // Follow the app's light/dark toggle.
    const stopTheme = followTheme((n) => {
      c.applyOptions(themeOptions(n));
      candles.current?.applyOptions({
        upColor: n.up,
        downColor: n.down,
        wickUpColor: n.up,
        wickDownColor: n.down,
      });
    });

    return () => {
      stopTheme();
      c.unsubscribeCrosshairMove(onMove);
      c.remove();
      chart.current = candles.current = volume.current = null;
    };
  }, []);

  // Load history when the symbol or interval changes.
  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    bars.current = [];
    setShown(null);
    candles.current?.setData([]);
    volume.current?.setData([]);
    chart.current?.applyOptions({ timeScale: { timeVisible: interval !== "1d" } });
    getCandles(symbol, exchange, interval)
      .then((res) => {
        if (cancelled) return;
        offset.current = res.tz_offset_secs;
        bars.current = res.candles.map((c) => ({ ...c, time: c.time + res.tz_offset_secs }));
        const p = chartPalette();
        candles.current?.setData(bars.current.map((b) => ({ ...b, time: b.time as UTCTimestamp })));
        volume.current?.setData(
          bars.current.map((b) => ({
            time: b.time as UTCTimestamp,
            value: b.volume,
            color: volumeColor(p, b.close, b.open),
          })),
        );
        chart.current?.timeScale().fitContent();
        setNote(res.note);
        setStatus("ready");
        showLast();
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
    if (!hovering.current) showLast();
  }, [quote, status, interval]);

  const bar = shown?.bar;
  const chg = bar && (shown?.prev ?? bar.open) ? (bar.close / (shown?.prev ?? bar.open) - 1) * 100 : null;
  const up = (chg ?? 0) >= 0;
  const latest = bars.current[bars.current.length - 1];

  return (
    <figure className="pc" aria-label={`${symbol} price chart`}>
      <figcaption className="pc-head">
        <span className="pc-sym">{symbol}</span>
        <span className="pc-muted">{exchange}</span>
        {quote?.stream && <span className="pc-live" title="Live feed">LIVE</span>}
        {latest && status === "ready" && (
          <span className="pc-last">{price(latest.close)}</span>
        )}
        <div role="group" aria-label="Chart interval" className="pc-intervals">
          {INTERVALS.map((i) => (
            <button
              key={i}
              type="button"
              className={i === interval ? "active" : ""}
              aria-pressed={i === interval}
              onClick={() => setIntervalState(i)}
            >
              {i === "1d" ? "1D" : i}
            </button>
          ))}
        </div>
      </figcaption>
      <div className="pc-body" style={{ height }}>
        {bar && status === "ready" && (
          <div className="pc-legend" aria-live="off">
            <span>O <b>{price(bar.open)}</b></span>
            <span>H <b>{price(bar.high)}</b></span>
            <span>L <b>{price(bar.low)}</b></span>
            <span>C <b className={up ? "pos" : "neg"}>{price(bar.close)}</b></span>
            {chg !== null && (
              <b className={up ? "pos" : "neg"}>
                {chg >= 0 ? "+" : ""}
                {chg.toFixed(2)}%
              </b>
            )}
            {/* A candle opened from live ticks has no volume yet; "0" would read as real. */}
            <span>Vol <b>{bar.volume > 0 ? compact(bar.volume) : "–"}</b></span>
          </div>
        )}
        <div ref={box} data-testid="price-chart" className="pc-canvas" />
        {status !== "ready" && (
          <div className={`pc-overlay ${status === "error" ? "error" : ""}`} role={status === "error" ? "alert" : "status"}>
            {status === "loading" ? "Loading chart…" : message}
          </div>
        )}
      </div>
      {note && <p className="pc-note">{note}</p>}
    </figure>
  );
}
