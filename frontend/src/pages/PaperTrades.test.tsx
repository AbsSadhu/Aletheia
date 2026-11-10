import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import PaperTrades from "./PaperTrades";

const api = vi.hoisted(() => ({
  listPaperTrades: vi.fn(),
  getPaperPositions: vi.fn(),
  settlePaperTrade: vi.fn(),
}));

vi.mock("../lib/api", () => api);

vi.mock("../components/TopBar", () => ({
  default: () => null,
}));

vi.mock("../components/PageHero", () => ({
  default: () => null,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PaperTrades", () => {
  it("guides users with no paper trades to start an analysis", async () => {
    api.listPaperTrades.mockResolvedValue({ trades: [] });
    api.getPaperPositions.mockResolvedValue({ positions: [] });

    render(
      <MemoryRouter>
        <PaperTrades />
      </MemoryRouter>,
    );

    expect(await screen.findByText("No paper trades recorded")).toBeTruthy();

    const link = screen.getByRole("link", { name: "Start an analysis" });
    expect(link.getAttribute("href")).toBe("/");
  });
});
