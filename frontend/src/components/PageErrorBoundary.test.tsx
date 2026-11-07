import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PageErrorBoundary from "./PageErrorBoundary";

function Boom(): never {
  throw new Error("kaboom");
}

afterEach(cleanup);

describe("PageErrorBoundary", () => {
  it("shows the error instead of blanking the app, and keeps siblings alive", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <>
        <nav>sidebar</nav>
        <PageErrorBoundary resetKey="/runs/1">
          <Boom />
        </PageErrorBoundary>
      </>,
    );
    expect(screen.getByText("sidebar")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("kaboom");
    expect(screen.getByRole("button", { name: /try again/i })).toBeTruthy();
  });

  it("renders children normally when nothing throws", () => {
    render(
      <PageErrorBoundary resetKey="/">
        <p>fine</p>
      </PageErrorBoundary>,
    );
    expect(screen.getByText("fine")).toBeTruthy();
  });

  it("clears the error when the route changes", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { rerender } = render(
      <PageErrorBoundary resetKey="/a">
        <Boom />
      </PageErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    rerender(
      <PageErrorBoundary resetKey="/b">
        <p>other page</p>
      </PageErrorBoundary>,
    );
    expect(screen.getByText("other page")).toBeTruthy();
  });
});
