import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AstryxProvider } from "../lib/AstryxProvider";
import Dashboard from "./Dashboard";

const api = vi.hoisted(() => ({
  fetchHealth: vi.fn(),
  listRuns: vi.fn(),
  listPortfolios: vi.fn(),
  createRun: vi.fn(),
  getRun: vi.fn(),
}));
vi.mock("../lib/api", () => api);
vi.mock("../components/TopBar", () => ({
  default: ({ onNewRun }: { onNewRun?: () => void }) => <button onClick={onNewRun}>New analysis</button>,
}));

const portfolio = (name: string) => ({ name, holdings: [{ symbol: "TCS", exchange: "NSE", quantity: 1, average_price: 100 }] });

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  api.fetchHealth.mockResolvedValue({ status: "ok" });
  api.listRuns.mockResolvedValue({ runs: [] });
  api.listPortfolios.mockResolvedValue({ portfolios: [portfolio("Alpha"), portfolio("Beta")] });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("Dashboard", () => {
  it("keeps the portfolio the user picked when the page refreshes itself", async () => {
    render(
      <AstryxProvider>
        <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
      </AstryxProvider>,
    );
    await waitFor(() => expect(api.listPortfolios).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByText("New analysis"));
    const select = (await screen.findByRole("combobox")) as HTMLSelectElement;
    expect(select.value).toBe("Alpha");
    fireEvent.change(select, { target: { value: "Beta" } });
    expect(select.value).toBe("Beta");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(16_000);
    });
    await waitFor(() => expect(api.listPortfolios).toHaveBeenCalledTimes(2));

    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("Beta");
  });
});
