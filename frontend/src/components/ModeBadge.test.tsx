import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ModeBadge from "./ModeBadge";

let state: { mode: string; paused: boolean } | "down";

beforeEach(() => {
  state = { mode: "simulation", paused: false };
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => (state === "down" ? new Response("x", { status: 500 }) : Response.json({ state }))),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ModeBadge", () => {
  it("says which execution mode is active, so simulated and real orders are never confused", async () => {
    render(<ModeBadge />);
    expect(await screen.findByText("SIMULATION")).toBeTruthy();
    cleanup();

    state = { mode: "paper", paused: false };
    render(<ModeBadge />);
    expect(await screen.findByText("PAPER")).toBeTruthy();
    cleanup();

    state = { mode: "live", paused: false };
    const { container } = render(<ModeBadge />);
    expect(await screen.findByText("LIVE · REAL MONEY")).toBeTruthy();
    expect(container.querySelector(".mode-badge.live")).toBeTruthy(); // the pulsing class
  });

  it("shows PAUSED over the mode, and nothing at all when the backend can't be reached", async () => {
    state = { mode: "live", paused: true };
    render(<ModeBadge />);
    expect(await screen.findByText("PAUSED")).toBeTruthy();
    expect(screen.queryByText(/LIVE/)).toBeNull();
    cleanup();

    state = "down";
    const { container } = render(<ModeBadge />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});
