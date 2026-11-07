import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
} from "lightweight-charts";
import type { IChartApi, ISeriesApi, MouseEventParams, UTCTimestamp } from "lightweight-charts";
import { Maximize2, Minimize2 } from "lucide-react";

import {
  baseChartOptions,
  candleOptions,
  chartPalette,
  followTheme,
  themeOptions,
  volumeColor,
} from "../../../lib/chartTheme";
import type { ChartPalette } from "../../../lib/chartTheme";
import { changePct, compact, money, toBars, toSeries } from "../../../lib/ohlcv";
import type { OhlcvDisplay } from "../../../lib/ohlcv";

const OVERLAY_COLORS = (p: ChartPalette): Record<string, string> => ({
  // Indicator lines avoid red/rose (loss) and green (profit): orange, grey-white, violet.
  "SMA 20": p.orange,
  "SMA 50": p.text,
  "BB upper": p.purple,
  "BB lower": p.purple,
});

const MAIN_HEIGHT = 250;
const PANE_HEIGHT = 90;

interface Legend {
  index: number;
  overlays: Record<string, number | undefined>;
  panes: Record<string, number | undefined>;
}

export default function OhlcvChart({ display }: { display: OhlcvDisplay }) {
  const box = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [expanded, setExpanded] = useState(false);
  const bars = useMemo(() => toBars(display), [display]);
  const [legend, setLegend] = useState<Legend>({ index: bars.length - 1, overlays: {}, panes: {} });
  const paneNames = Object.keys(display.panes ?? {});
  const height = MAIN_HEIGHT + PANE_HEIGHT * paneNames.length;

  useEffect(() => {
    const el = box.current;
    if (!el || bars.length === 0) return;
    const offset = display.tz_offset_secs;
    const p = chartPalette();
    const chart: IChartApi = createChart(el, {
      ...baseChartOptions(p, {
        intraday: display.interval !== "1d" && display.interval !== "1wk",
      }),
      // Inline, the wheel must scroll the conversation, not zoom the chart; see the effect below.
      handleScroll: { mouseWheel: false },
      handleScale: { mouseWheel: false },
    });
    chartRef.current = chart;

    const candles = chart.addSeries(CandlestickSeries, candleOptions(p));
    candles.setData(bars.map((b) => ({ ...b, time: b.time as UTCTimestamp })));

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volume.setData(
      bars.map((b) => ({
        time: b.time as UTCTimestamp,
        value: b.volume,
        color: volumeColor(p, b.close, b.open),
      })),
    );

    // Overlays on the price pane.
    const colors = OVERLAY_COLORS(p);
    const overlaySeries: Record<string, ISeriesApi<"Line">> = {};
    for (const [name, rows] of Object.entries(display.overlays ?? {})) {
      const band = name.startsWith("BB");
      const s = chart.addSeries(LineSeries, {
        color: colors[name] ?? p.accent,
        lineWidth: 1,
        lineStyle: band ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      s.setData(toSeries(rows, offset).map((r) => ({ ...r, time: r.time as UTCTimestamp })));
      overlaySeries[name] = s;
    }

    // Indicator panes below.
    const paneSeries: Record<string, ISeriesApi<"Line" | "Histogram">> = {};
    paneNames.forEach((name, i) => {
      const def = display.panes![name];
      const paneIndex = i + 1;
      if (def.kind === "line") {
        const s = chart.addSeries(
          LineSeries,
          { color: p.orange, lineWidth: 1, priceLineVisible: false, lastValueVisible: true },
          paneIndex,
        );
        s.setData(toSeries(def.series, offset).map((r) => ({ ...r, time: r.time as UTCTimestamp })));
        for (const level of def.levels ?? []) {
          s.createPriceLine({
            price: level,
            color: p.muted,
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: false,
            title: "",
          });
        }
        paneSeries[name] = s;
      } else {
        const hist = chart.addSeries(
          HistogramSeries,
          { priceLineVisible: false, lastValueVisible: false },
          paneIndex,
        );
        hist.setData(
          toSeries(def.histogram, offset).map((r) => ({
            time: r.time as UTCTimestamp,
            value: r.value,
            color: r.value >= 0 ? `${p.up}99` : `${p.down}99`,
          })),
        );
        const line = chart.addSeries(
          LineSeries,
          { color: p.text, lineWidth: 1, priceLineVisible: false, lastValueVisible: false },
          paneIndex,
        );
        line.setData(toSeries(def.macd, offset).map((r) => ({ ...r, time: r.time as UTCTimestamp })));
        const sig = chart.addSeries(
          LineSeries,
          { color: p.orange, lineWidth: 1, priceLineVisible: false, lastValueVisible: false },
          paneIndex,
        );
        sig.setData(toSeries(def.signal, offset).map((r) => ({ ...r, time: r.time as UTCTimestamp })));
        paneSeries[name] = line;
        paneSeries[`${name}:signal`] = sig;
      }
    });
    const panes = chart.panes();
    if (panes.length > 1) {
      panes[0].setStretchFactor(MAIN_HEIGHT / PANE_HEIGHT);
      for (let i = 1; i < panes.length; i++) panes[i].setStretchFactor(1);
    }

    const indexByTime = new Map(bars.map((b, i) => [b.time, i]));
    const onMove = (param: MouseEventParams) => {
      const t = typeof param.time === "number" ? param.time : null;
      const idx = t !== null ? indexByTime.get(t) : undefined;
      const read = (s: ISeriesApi<"Line" | "Histogram">) => {
        const d = param.seriesData.get(s) as { value?: number } | undefined;
        return d?.value;
      };
      setLegend({
        index: idx ?? bars.length - 1,
        overlays: Object.fromEntries(Object.entries(overlaySeries).map(([k, s]) => [k, read(s)])),
        panes: Object.fromEntries(Object.entries(paneSeries).map(([k, s]) => [k, read(s)])),
      });
    };
    chart.subscribeCrosshairMove(onMove);
    chart.timeScale().fitContent();

    // Follow the app's light/dark toggle.
    const stopTheme = followTheme((n) => {
      chart.applyOptions(themeOptions(n));
      candles.applyOptions({
        upColor: n.up,
        downColor: n.down,
        wickUpColor: n.up,
        wickDownColor: n.down,
      });
    });

    return () => {
      stopTheme();
      chart.unsubscribeCrosshairMove(onMove);
      chart.remove();
      chartRef.current = null;
    };
    // paneNames is derived from display; rebuild only when the data changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [display, bars]);

  // Wheel zoom/pan only once expanded (drag and pinch always work).
  useEffect(() => {
    chartRef.current?.applyOptions({
      handleScroll: { mouseWheel: expanded },
      handleScale: { mouseWheel: expanded },
    });
  }, [expanded, display]);

  if (bars.length === 0) return <p className="chat-muted">No price data.</p>;

  const bar = bars[Math.min(legend.index, bars.length - 1)];
  const chg = changePct(bars, Math.min(legend.index, bars.length - 1));
  const last = bars[bars.length - 1];
  const lastChg = changePct(bars, bars.length - 1);
  const up = (chg ?? 0) >= 0;
  const cur = display.currency;

  return (
    <figure className={`chat-ohlcv ${expanded ? "expanded" : ""}`} aria-label={`${display.symbol} chart`}>
      <figcaption className="chat-ohlcv-head">
        <span className="chat-ohlcv-sym">{display.symbol}</span>
        <span className="chat-muted">
          {display.interval} · {cur}
        </span>
        <span className="chat-ohlcv-last">{money(last.close, cur)}</span>
        {lastChg !== null && (
          <span className={lastChg >= 0 ? "pos" : "neg"}>
            {lastChg >= 0 ? "+" : ""}
            {lastChg.toFixed(2)}%
          </span>
        )}
        <button
          type="button"
          className="chat-icon-btn chat-ohlcv-expand"
          onClick={() => setExpanded((e) => !e)}
          aria-label={expanded ? "Shrink chart" : "Expand chart"}
          title={expanded ? "Shrink" : "Expand"}
        >
          {expanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
        </button>
      </figcaption>
      <div className="chat-ohlcv-body" style={{ height: expanded ? undefined : height }}>
        <div className="chat-ohlcv-legend" aria-live="off">
          <span>
            O <b>{bar.open.toFixed(2)}</b>
          </span>
          <span>
            H <b>{bar.high.toFixed(2)}</b>
          </span>
          <span>
            L <b>{bar.low.toFixed(2)}</b>
          </span>
          <span>
            C <b className={up ? "pos" : "neg"}>{bar.close.toFixed(2)}</b>
          </span>
          {chg !== null && (
            <b className={up ? "pos" : "neg"}>
              {chg >= 0 ? "+" : ""}
              {chg.toFixed(2)}%
            </b>
          )}
          <span>
            Vol <b>{compact(bar.volume)}</b>
          </span>
          {Object.entries(legend.overlays)
            .filter(([k, v]) => v !== undefined && !k.startsWith("BB"))
            .map(([k, v]) => (
              <span key={k}>
                {k} <b>{v!.toFixed(2)}</b>
              </span>
            ))}
        </div>
        <div ref={box} className="chat-ohlcv-canvas" data-testid="ohlcv-chart" />
      </div>
    </figure>
  );
}
