import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LiveMarket from "./LiveMarket";

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.());
  }
  close() {
    this.onclose?.();
  }
  push(payload: object) {
    this.onmessage?.({ data: JSON.stringify({ topic: "market.quote", payload }) });
  }
}

const quote = (symbol: string, close: number, extra: object = {}) => ({
  symbol,
  exchange: "NSE",
  close,
  open: close - 5,
  high: close + 7,
  low: close - 9,
  volume: 123456,
  prev_close: close - 10,
  change_pct: 0.8,
  as_of: new Date().toISOString(),
  provider: "angel_one_stream",
  stream: true,
  ...extra,
});

let status: object;
let watch: { symbol: string; exchange: string }[];
let saved: unknown[] = [];

function market(open = true) {
  return { state: open ? "open" : "closed", label: open ? "Market open" : "Closed (after 15:30 IST)", is_open: open, ist_time: "10:00:00", note: "" };
}
const streamStatus = (over: object = {}) => ({
  mode: "stream",
  source: "Angel One (live, ~1s)",
  market: market(),
  stream: { connected: true, symbols: 2, ticks: 10, last_tick_age_secs: 0.5, reconnects: 0, price_scale_verified: true, error: null },
  stream_configured: true,
  setup_hint: null,
  unresolved_symbols: [],
  ...over,
});

beforeEach(() => {
  FakeSocket.instances = [];
  saved = [];
  watch = [
    { symbol: "RELIANCE", exchange: "NSE" },
    { symbol: "TCS", exchange: "NSE" },
  ];
  status = streamStatus();
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/watchlist") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body));
        saved.push(body.items);
        watch = body.items;
        return new Response(JSON.stringify({ items: watch, unresolved_symbols: [] }), { status: 200 });
      }
      if (url.includes("/watchlist")) return new Response(JSON.stringify({ items: watch }), { status: 200 });
      return new Response(JSON.stringify(status), { status: 200 });
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <LiveMarket />
    </MemoryRouter>,
  );

describe("LiveMarket", () => {
  it("renders the watchlist and updates a price from the socket", async () => {
    renderPage();
    await screen.findByText("RELIANCE");
    await waitFor(() => expect(FakeSocket.instances.length).toBe(1));
    expect(FakeSocket.instances[0].url).toContain("/api/v1/ws/market");

    act(() => FakeSocket.instances[0].push(quote("RELIANCE", 1250.5)));
    await waitFor(() => expect(screen.getByText("1,250.50")).toBeTruthy());
    expect(screen.getByText("+0.80%")).toBeTruthy();

    act(() => FakeSocket.instances[0].push(quote("RELIANCE", 1251.75)));
    const price = await screen.findByText("1,251.75");
    expect((price as HTMLElement).style.color).toBe("var(--green)"); // ticked up
  });

  it("labels the feed LIVE when streaming, and delayed when polling", async () => {
    renderPage();
    expect(await screen.findByText(/LIVE · Angel One \(live, ~1s\)/)).toBeTruthy();
    cleanup();
    status = streamStatus({
      mode: "polling",
      source: "Polling every 15s (delayed)",
      stream: null,
      stream_configured: false,
      setup_hint: "Angel One credentials are not saved yet.",
    });
    renderPage();
    expect(await screen.findByText(/Polling every 15s/)).toBeTruthy();
    expect(await screen.findByText(/Not streaming/)).toBeTruthy();
    expect(screen.getByText(/credentials are not saved/)).toBeTruthy();
  });

  it("names whichever broker is streaming, e.g. Fyers", async () => {
    status = streamStatus({ source: "Fyers (live, ~1s)", provider: "fyers" });
    renderPage();
    expect(await screen.findByText(/LIVE · Fyers \(live, ~1s\)/)).toBeTruthy();
  });

  it("asks for a Fyers login when the stream needs one", async () => {
    status = streamStatus({
      mode: "polling",
      source: "Polling every 15s (delayed)",
      provider: "fyers",
      stream: { ...(streamStatus() as any).stream, connected: false, needs_login: true, error: "Fyers login required." },
      setup_hint: "Fyers login required.",
    });
    renderPage();
    expect(await screen.findByText(/Not streaming/)).toBeTruthy();
    expect(screen.getByText(/Fyers login required/)).toBeTruthy();
  });

  it("says plainly when the market is closed instead of looking broken", async () => {
    status = streamStatus({ market: market(false) });
    renderPage();
    expect(await screen.findByText(/market is closed, so prices are not moving/)).toBeTruthy();
  });

  it("warns loudly if streamed prices don't match the REST quote", async () => {
    status = streamStatus({ stream: { ...(streamStatus() as any).stream, price_scale_verified: false } });
    renderPage();
    expect(await screen.findByText(/Do not trade on them/)).toBeTruthy();
  });

  it("shows a stream error from the backend", async () => {
    status = streamStatus({ stream: { ...(streamStatus() as any).stream, error: "401: Invalid token" } });
    renderPage();
    expect(await screen.findByText(/Invalid token/)).toBeTruthy();
  });

  it("adds and removes symbols through the API", async () => {
    renderPage();
    await screen.findByText("RELIANCE");

    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "wipro" } });
    fireEvent.click(screen.getByRole("button", { name: /Add/ }));
    await waitFor(() => expect(saved.length).toBe(1));
    expect(saved[0]).toEqual([
      { symbol: "RELIANCE", exchange: "NSE" },
      { symbol: "TCS", exchange: "NSE" },
      { symbol: "WIPRO", exchange: "NSE" },
    ]);
    await screen.findByText("WIPRO");

    fireEvent.click(screen.getByRole("button", { name: "Remove TCS" }));
    await waitFor(() => expect(saved.length).toBe(2));
    expect((saved[1] as { symbol: string }[]).map((i) => i.symbol)).toEqual(["RELIANCE", "WIPRO"]);
  });

  it("marks symbols Angel One doesn't know", async () => {
    status = streamStatus({ unresolved_symbols: ["TCS:NSE"] });
    renderPage();
    expect(await screen.findByText(/unknown/)).toBeTruthy();
  });
});

const cryptoStatus = (over: object = {}) => ({
  connected: true, source: "Binance (live, ~1s)", symbols: 1, ticks: 40, last_tick_age_secs: 0.4,
  error: null, window: "24h rolling", ...over,
});

describe("LiveMarket crypto stream", () => {
  it("says crypto is live while stocks are delayed when no broker is connected", async () => {
    status = streamStatus({
      mode: "polling", source: "Polling every 15s (delayed)", stream: null,
      stream_configured: false, crypto: cryptoStatus(),
    });
    renderPage();
    expect(await screen.findByText(/Crypto LIVE \(Binance, ~1s\).*stocks delayed/)).toBeTruthy();
  });

  it("appends crypto to the badge when a broker stream is also live", async () => {
    status = streamStatus({ crypto: cryptoStatus() });
    renderPage();
    expect(await screen.findByText(/LIVE · Angel One \(live, ~1s\) · crypto live \(Binance\)/)).toBeTruthy();
  });

  it("explains a crypto stream failure and how to switch it off", async () => {
    status = streamStatus({
      mode: "polling", source: "Polling every 15s (delayed)", stream: null, stream_configured: false,
      crypto: cryptoStatus({ connected: false, error: "Binance is not available from your location (HTTP 451)" }),
    });
    renderPage();
    expect(await screen.findByText(/Crypto stream problem: Binance is not available/)).toBeTruthy();
    expect(screen.getByText(/ALETHEIA_CRYPTO_STREAM_ENABLED=false/)).toBeTruthy();
  });

  it("marks a silent crypto row stale even when the stock market is closed, but not a silent stock", async () => {
    watch = [
      { symbol: "BTC/USDT", exchange: "BINANCE" },
      { symbol: "TCS", exchange: "NSE" },
    ];
    status = streamStatus({ market: market(false), crypto: cryptoStatus() });
    renderPage();
    await screen.findByText("TCS");
    await waitFor(() => expect(FakeSocket.instances.length).toBe(1));
    const old = new Date(Date.now() - 120_000).toISOString();
    act(() => {
      FakeSocket.instances[0].push({ ...quote("BTC/USDT", 80000, { exchange: "BINANCE", as_of: old, provider: "binance_stream" }) });
      FakeSocket.instances[0].push(quote("TCS", 3000, { as_of: old }));
    });
    await waitFor(() => expect(screen.getByTestId("row-BTC/USDT").textContent).toContain("STALE"));
    expect(screen.getByTestId("row-TCS").textContent).not.toContain("STALE"); // market closed: silence is normal
  });
});

describe("LiveMarket BSE website source", () => {
  const bseStatus = (streamOver: object = {}, over: object = {}) =>
    streamStatus({
      source: "BSE website (live, ~2s)", provider: "bse_web",
      stream: { ...(streamStatus() as any).stream, unofficial: true, poll_secs: 2, data_lag_secs: 5, ...streamOver },
      ...over,
    });

  it("labels the feed unofficial and says it is the BSE price on an NSE row", async () => {
    status = bseStatus();
    renderPage();
    expect(await screen.findByText(/LIVE · BSE website \(live, ~2s\)/)).toBeTruthy();
    expect(await screen.findByText(/Unofficial free source/)).toBeTruthy();
    await waitFor(() => expect(FakeSocket.instances.length).toBe(1));
    act(() =>
      FakeSocket.instances[0].push(
        quote("RELIANCE", 1190, { provider: "bse_web", price_exchange: "BSE", data_lag_secs: 10, volume: null }),
      ),
    );
    await waitFor(() => expect(screen.getByTestId("row-RELIANCE").textContent).toContain("BSE price"));
    expect(screen.getByTestId("row-RELIANCE").textContent).not.toContain("exchange data");
  });

  it("shows how old the exchange's own data is when BSE trails the clock", async () => {
    status = bseStatus({ data_lag_secs: 900 });
    renderPage();
    expect(await screen.findByText(/trail your clock by about 15 minutes/)).toBeTruthy();
    expect(screen.getByText(/not live/)).toBeTruthy();
    await waitFor(() => expect(FakeSocket.instances.length).toBe(1));
    act(() => FakeSocket.instances[0].push(quote("RELIANCE", 1190, { price_exchange: "BSE", data_lag_secs: 900 })));
    await waitFor(() => expect(screen.getByTestId("row-RELIANCE").textContent).toContain("exchange data 15 min old"));
  });

  it("does not raise a lag alarm when the market is closed", async () => {
    status = bseStatus({ data_lag_secs: 86400 }, { market: market(false) });
    renderPage();
    await screen.findByText(/Unofficial free source/);
    expect(screen.queryByText(/trail your clock/)).toBeNull();
  });
});

vi.mock("../components/PriceChart", () => ({
  default: ({ symbol, exchange, quote }: { symbol: string; exchange: string; quote?: { close: number } }) => (
    <div data-testid="price-chart">
      chart:{exchange}:{symbol}:{quote ? quote.close : "no-quote"}
    </div>
  ),
}));

describe("LiveMarket chart", () => {
  it("opens a chart for the clicked symbol, passes it the live quote, and closes", async () => {
    renderPage();
    await screen.findByText("RELIANCE");
    await waitFor(() => expect(FakeSocket.instances.length).toBe(1));
    act(() => FakeSocket.instances[0].push(quote("RELIANCE", 1250.5)));
    await screen.findByText("1,250.50");

    expect(screen.queryByTestId("price-chart")).toBeNull();

    fireEvent.click(screen.getByTestId("row-RELIANCE"));
    expect((await screen.findByTestId("price-chart")).textContent).toBe("chart:NSE:RELIANCE:1250.5");
    expect(screen.getAllByText(/your live feed/).length).toBeGreaterThan(0);

    act(() => FakeSocket.instances[0].push(quote("RELIANCE", 1251.75)));
    await waitFor(() => expect(screen.getByTestId("price-chart").textContent).toContain("1251.75"));

    fireEvent.click(screen.getByRole("button", { name: "Open chart for TCS" }));
    await waitFor(() => expect(screen.getByTestId("price-chart").textContent).toContain("NSE:TCS"));

    fireEvent.click(screen.getByRole("button", { name: "Close chart" }));
    expect(screen.queryByTestId("price-chart")).toBeNull();
  });

  it("links to the full TradingView chart in a new tab", async () => {
    renderPage();
    await screen.findByText("TCS");
    fireEvent.click(screen.getByTestId("row-TCS"));
    const link = (await screen.findByText(/Open in TradingView/)) as HTMLAnchorElement;
    expect(link.href).toContain("tradingview.com/chart/?symbol=NSE%3ATCS");
    expect(link.target).toBe("_blank");
    expect(link.rel).toContain("noopener");
  });

  it("closes the chart when its symbol is removed from the watchlist", async () => {
    renderPage();
    await screen.findByText("TCS");
    fireEvent.click(screen.getByTestId("row-TCS"));
    await screen.findByTestId("price-chart");
    fireEvent.click(screen.getByRole("button", { name: "Remove TCS" }));
    await waitFor(() => expect(screen.queryByTestId("price-chart")).toBeNull());
  });
});
