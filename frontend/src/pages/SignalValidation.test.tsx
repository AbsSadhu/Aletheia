import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SignalValidation from "./SignalValidation";

// recharts needs real layout; the page logic is what's under test here.
vi.mock("recharts", () => {
  const Stub = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Stub,
    LineChart: Stub,
    Line: Stub,
    XAxis: Stub,
    YAxis: Stub,
    CartesianGrid: Stub,
    Tooltip: Stub,
    Legend: Stub,
  };
});

const perf = { cagr_pct: 1.8, total_return_pct: 12.4, sharpe: -0.35, max_drawdown_pct: 21.2, volatility_pct: 11 };
const backtest = {
  period: { start: "2020-04-21", end: "2026-10-23" },
  config: { universe_size: 24, max_positions: 10, rebalance_days: 5 },
  strategy: perf,
  strategy_post_tax: { ...perf, cagr_pct: 0.8 },
  nifty: { ...perf, cagr_pct: 15.2 },
  equal_weight: { ...perf, cagr_pct: 19.8 },
  out_of_sample: { start: "2024-03-13", strategy_post_tax: perf, nifty: perf, note: "" },
  trading: {
    trades: 810, win_rate_pct: 48.4, avg_holding_days: 18.6, stopped_out_pct: 47.7,
    trading_costs_inr: 321829, tax_paid_inr: 70680, gross_final_equity: 1123574,
    post_tax_final_equity: 1052894, avg_invested_pct: 63.3,
  },
  verdict: { status: "FAIL", headline: "Did not clear the bar.", reasons: ["Post-tax CAGR 0.8% does not beat Nifty buy-and-hold 15.24%."] },
  equity_curve: [],
  caveats: ["Survivorship bias: the universe is today's large caps."],
};
const accuracy = {
  resolved: 0, pending: 4, enough_data: false, coin_flip_brier: 0.25, overall: null,
  by_signal: {}, calibration: [], by_symbol: [], verdict: "No resolved predictions yet.",
};

function mockApi(result: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = url.includes("/backtest/signal/latest")
        ? { result }
        : url.includes("/signals/accuracy")
          ? accuracy
          : { points: [], note: "Needs at least two shadow-account snapshots." };
      return new Response(JSON.stringify(body), { status: 200 });
    }),
  );
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(cleanup);

const renderPage = () =>
  render(
    <MemoryRouter>
      <SignalValidation />
    </MemoryRouter>,
  );

describe("SignalValidation", () => {
  it("shows the FAIL verdict and its reasons, not a flattering summary", async () => {
    mockApi(backtest);
    renderPage();
    expect(await screen.findByText("FAIL")).toBeTruthy();
    expect(screen.getByText(/does not beat Nifty buy-and-hold/)).toBeTruthy();
    expect(screen.getByText("Nifty 50, buy & hold")).toBeTruthy();
    expect(screen.getByText(/Survivorship bias/)).toBeTruthy();
  });

  it("explains itself before any backtest has been run", async () => {
    mockApi(null);
    renderPage();
    expect(await screen.findByText(/Walks 25 Nifty large caps/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Run validation/ })).toBeTruthy();
  });

  it("is honest about an empty track record", async () => {
    mockApi(null);
    renderPage();
    await waitFor(() => expect(screen.getByText(/No resolved predictions yet/)).toBeTruthy());
    expect(screen.getByText(/4 waiting/)).toBeTruthy();
  });
});
