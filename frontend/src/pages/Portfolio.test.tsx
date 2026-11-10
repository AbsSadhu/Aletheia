import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import Portfolio from "./Portfolio";

const api = vi.hoisted(() => ({
  listPortfolios: vi.fn(),
  savePortfolio: vi.fn(),
  deletePortfolio: vi.fn(),
  syncZerodha: vi.fn(),
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
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe("Portfolio", () => {
  it("offers CSV import and a sample when a portfolio has no holdings", async () => {
    api.listPortfolios.mockResolvedValue({
      portfolios: [{ name: "Sample", base_currency: "INR", holdings: [] }],
    });

    render(
      <MemoryRouter>
        <Portfolio />
      </MemoryRouter>,
    );

    expect(await screen.findByText("No holdings yet")).toBeTruthy();

    const filePickerClick = vi.spyOn(HTMLInputElement.prototype, "click");
    fireEvent.click(screen.getByRole("button", { name: "Import a CSV" }));
    expect(filePickerClick).toHaveBeenCalled();

    const sample = screen.getByRole("link", { name: "Download sample CSV" });
    expect(sample.getAttribute("href")).toBe("/sample_portfolio.csv");
    expect(sample.hasAttribute("download")).toBe(true);
  });
});
