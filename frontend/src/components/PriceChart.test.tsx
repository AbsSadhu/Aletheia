import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const series = {
  setData: vi.fn(),
  update: vi.fn(),
  applyOptions: vi.fn(),
  priceScale: () => ({ applyOptions: vi.fn() }),
};
const chart = {
  addSeries: vi.fn(() => ({ ...series })),
  applyOptions: vi.fn(),
  timeScale: () => ({ fitContent: vi.fn() }),
  remove: vi.fn(),
};

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => chart),
  CandlestickSeries: "candles",
  HistogramSeries: "hist",
  ColorType: { Solid: "solid" },
}));

import PriceChart from "./PriceChart";

const OFFSET = 19800;
const t0 = Date.UTC(2026, 9, 26, 4, 0, 0) / 1000;
const history = {
  symbol: "RELIANCE",
  exchange: "NSE",
  interval: "5m",
  candles: [
    { time: t0 - 300, open: 100, high: 101, low: 99, close: 100.5, volume: 10 },
    { time: t0, open: 100.5, high: 102, low: 100, close: 101, volume: 20 },
  ],
  tz_offset_secs: OFFSET,
  source: "Yahoo Finance",
  note: "Yahoo's NSE/BSE intraday data can lag by up to ~15 minutes.",
};

let urls: string[];
beforeEach(() => {
  urls = [];
  vi.clearAllMocks();
  chart.addSeries.mockImplementation(() => ({ ...series }));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      if (url.includes("interval=bad")) return new Response("nope", { status: 404 });
      return new Response(JSON.stringify(history), { status: 200 });
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const quote = (close: number, whenSecs: number) => ({
  symbol: "RELIANCE", exchange: "NSE", close, as_of: new Date(whenSecs * 1000).toISOString(), provider: "x", stream: true,
});

describe("PriceChart", () => {
  it("loads candles for the symbol, shifts times to IST and shows the data note", async () => {
    render(<PriceChart symbol="RELIANCE" exchange="NSE" />);
    await screen.findByText(/lag by up to ~15 minutes/);

    expect(urls[0]).toContain("symbol=RELIANCE");
    expect(urls[0]).toContain("interval=5m");
    const candleSeries = chart.addSeries.mock.results[0].value;
    const data = candleSeries.setData.mock.calls.at(-1)[0];
    expect(data).toHaveLength(2);
    expect(data[1].time).toBe(t0 + OFFSET);
  });

  it("moves the last candle with a live price (no refetch)", async () => {
    const { rerender } = render(<PriceChart symbol="RELIANCE" exchange="NSE" />);
    await screen.findByText(/lag by up to/);
    const candleSeries = chart.addSeries.mock.results[0].value;
    candleSeries.update.mockClear();

    rerender(<PriceChart symbol="RELIANCE" exchange="NSE" quote={quote(103.25, t0 + 60)} />);
    await waitFor(() => expect(candleSeries.update).toHaveBeenCalled());
    const bar = candleSeries.update.mock.calls.at(-1)[0];
    expect(bar).toMatchObject({ time: t0 + OFFSET, close: 103.25, high: 103.25, low: 100 });
    expect(urls).toHaveLength(1);
  });

  it("opens a new candle when the live price crosses into the next interval", async () => {
    const { rerender } = render(<PriceChart symbol="RELIANCE" exchange="NSE" />);
    await screen.findByText(/lag by up to/);
    const candleSeries = chart.addSeries.mock.results[0].value;

    rerender(<PriceChart symbol="RELIANCE" exchange="NSE" quote={quote(104, t0 + 305)} />);
    await waitFor(() => expect(candleSeries.update).toHaveBeenCalled());
    expect(candleSeries.update.mock.calls.at(-1)[0]).toMatchObject({ time: t0 + 300 + OFFSET, open: 101 });
  });

  it("refetches when the interval button changes", async () => {
    render(<PriceChart symbol="RELIANCE" exchange="NSE" />);
    await screen.findByText(/lag by up to/);
    fireEvent.click(screen.getByRole("button", { name: "1D" }));
    await waitFor(() => expect(urls.some((u) => u.includes("interval=1d"))).toBe(true));
    expect(screen.getByRole("button", { name: "1D" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("shows the error instead of an empty chart when history can't load", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("No 5m data for ZZZ.", { status: 404 })));
    render(<PriceChart symbol="ZZZ" exchange="NSE" />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("404");
  });

  it("destroys the chart on unmount", async () => {
    const { unmount } = render(<PriceChart symbol="RELIANCE" exchange="NSE" />);
    await screen.findByText(/lag by up to/);
    unmount();
    expect(chart.remove).toHaveBeenCalled();
  });

  it("is a harmless no-op on a stray live price before history has loaded", () => {
    act(() => {
      render(<PriceChart symbol="RELIANCE" exchange="NSE" quote={quote(99, t0)} />);
    });
    expect(chart.addSeries.mock.results[0].value.update).not.toHaveBeenCalled();
  });
});
