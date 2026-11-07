import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import Sidebar from "./Sidebar";

afterEach(cleanup);

const renderSidebar = (online: boolean) =>
  render(
    <MemoryRouter>
      <Sidebar backendOnline={online} />
    </MemoryRouter>,
  );

describe("Sidebar", () => {
  it("links to every page", () => {
    renderSidebar(true);
    for (const label of [
      "Dashboard",
      "Runs",
      "Live Market",
      "Portfolio",
      "Paper Trades",
      "Shadow Trader",
      "Backtest",
      "Hypotheses",
      "Factor Explorer",
      "Options",
      "Signal Validation",
      "Settings",
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeTruthy();
    }
  });

  it("groups pages into sections and marks the current page", () => {
    render(
      <MemoryRouter initialEntries={["/runs/abc123"]}>
        <Sidebar backendOnline />
      </MemoryRouter>,
    );
    for (const title of ["Overview", "Markets", "Trading", "Research", "System"]) {
      expect(screen.getByText(title)).toBeTruthy();
    }
    // A nested route (a single run) still highlights its parent page.
    expect(screen.getByRole("link", { name: "Runs" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Dashboard" }).getAttribute("aria-current")).toBeNull();
  });

  it("reflects backend connectivity", () => {
    renderSidebar(false);
    expect(screen.getByText("Backend offline")).toBeTruthy();
    cleanup();
    renderSidebar(true);
    expect(screen.getByText("Backend connected")).toBeTruthy();
  });

  it("shows the package version, not a hard-coded one", () => {
    renderSidebar(true);
    expect(screen.getByText(`v${__APP_VERSION__} · alpha`)).toBeTruthy();
    expect(__APP_VERSION__).toMatch(/^\d+\.\d+\.\d+$/);
  });
});
