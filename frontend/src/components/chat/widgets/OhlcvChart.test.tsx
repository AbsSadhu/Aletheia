import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { changePct, compact, money, toBars, toSeries } from "../../../lib/ohlcv";
import type { OhlcvDisplay } from "../../../lib/ohlcv";

const created: { type: string; pane?: number; setData: ReturnType<typeof vi.fn> }[] = [];
const stretch = vi.fn();
const chart = {
  addSeries: vi.fn((type: string, _opts: unknown, pane?: number) => {
    const s = {
      type,
      pane,
      setData: vi.fn(),
      applyOptions: vi.fn(),
      priceScale: () => ({ applyOptions: vi.fn() }),
      createPriceLine: vi.fn(),
    };
    created.push(s);
    return s;
  }),
  applyOptions: vi.fn(),
  panes: vi.fn(() => [{ setStretchFactor: stretch }, { setStretchFactor: stretch }, { setStretchFactor: stretch }]),
  subscribeCrosshairMove: vi.fn(),
  unsubscribeCrosshairMove: vi.fn(),
  timeScale: () => ({ fitContent: vi.fn() }),
  remove: vi.fn(),
};

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => chart),
  CandlestickSeries: "candles",
  HistogramSeries: "hist",
  LineSeries: "line",
  LineStyle: { Dashed: 2, Solid: 0 },
  CrosshairMode: { Normal: 0 },
  ColorType: { Solid: "solid" },
}));

import OhlcvChart from "./OhlcvChart";

const display: OhlcvDisplay = {
  type: "ohlcv",
  symbol: "INFY.NS",
  currency: "INR",
  interval: "1d",
  tz_offset_secs: 0,
  bars: [
    [1_700_000_000, 100, 105, 99, 102, 1_000_000],
    [1_700_086_400, 102, 110, 101, 108, 25_000_000],
  ],
  overlays: { "SMA 20": [[1_700_086_400, 104.5]], "BB upper": [[1_700_086_400, 120]] },
  panes: {
    "RSI 14": { kind: "line", levels: [30, 70], series: [[1_700_086_400, 61.2]] },
    MACD: { kind: "macd", macd: [[1_700_086_400, 1]], signal: [[1_700_086_400, 0.5]], histogram: [[1_700_086_400, 0.5]] },
  },
};

describe("ohlcv helpers", () => {
  it("shifts intraday times by the IST offset and leaves values alone", () => {
    const bars = toBars({ ...display, tz_offset_secs: 19800 });
    expect(bars[0]).toEqual({ time: 1_700_000_000 + 19800, open: 100, high: 105, low: 99, close: 102, volume: 1_000_000 });
    expect(toSeries([[10, 5]], 19800)).toEqual([{ time: 19810, value: 5 }]);
  });

  it("computes change against the previous close, and the open for the first bar", () => {
    const bars = toBars(display);
    expect(changePct(bars, 1)).toBeCloseTo((108 / 102 - 1) * 100);
    expect(changePct(bars, 0)).toBeCloseTo((102 / 100 - 1) * 100);
    expect(changePct(bars, 9)).toBeNull();
  });

  it("formats money in the right currency and volume in lakh/crore", () => {
    expect(money(1190, "INR")).toBe("₹1,190.00");
    expect(money(1234567.5, "INR")).toBe("₹12,34,567.50");
    expect(money(347.73, "USD")).toBe("$347.73");
    expect(compact(25_000_000)).toBe("2.50Cr");
    expect(compact(150_000)).toBe("1.50L");
  });
});

describe("OhlcvChart", () => {
  beforeEach(() => {
    created.length = 0;
    vi.clearAllMocks();
  });
  afterEach(cleanup);

  it("draws candles, volume, overlays and one pane per indicator", () => {
    render(<OhlcvChart display={display} />);
    const types = created.map((s) => `${s.type}@${s.pane ?? 0}`);
    expect(types).toEqual([
      "candles@0",
      "hist@0", // volume
      "line@0", // SMA 20
      "line@0", // BB upper
      "line@1", // RSI
      "hist@2", // MACD histogram
      "line@2", // MACD line
      "line@2", // signal
    ]);
    const candleData = created[0].setData.mock.calls[0][0];
    expect(candleData).toHaveLength(2);
    expect(created[1].setData.mock.calls[0][0][1].value).toBe(25_000_000); // volume from the data
    expect(stretch).toHaveBeenCalled();
  });

  it("shows the symbol, currency, last price and the last bar in the legend", () => {
    render(<OhlcvChart display={display} />);
    expect(screen.getByText("INFY.NS")).toBeTruthy();
    expect(screen.getByText("₹108.00")).toBeTruthy();
    expect(screen.getByText("+5.88%", { selector: "span" })).toBeTruthy();
    expect(screen.getByText("2.50Cr")).toBeTruthy();
  });

  it("expands and shrinks, and cleans the chart up on unmount", () => {
    const { unmount, container } = render(<OhlcvChart display={display} />);
    fireEvent.click(screen.getByRole("button", { name: "Expand chart" }));
    expect(container.querySelector(".chat-ohlcv.expanded")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Shrink chart" }));
    expect(container.querySelector(".chat-ohlcv.expanded")).toBeNull();
    unmount();
    expect(chart.remove).toHaveBeenCalled();
    expect(chart.unsubscribeCrosshairMove).toHaveBeenCalled();
  });

  it("says so instead of drawing an empty chart", () => {
    render(<OhlcvChart display={{ ...display, bars: [] }} />);
    expect(screen.getByText("No price data.")).toBeTruthy();
    expect(chart.addSeries).not.toHaveBeenCalled();
  });
});
