import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OfflineBanner from "./OfflineBanner";

describe("OfflineBanner", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("stays hidden while the backend is online", () => {
    render(<OfflineBanner online />);
    act(() => void vi.advanceTimersByTime(20_000));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("waits out a slow start-up before warning", () => {
    render(<OfflineBanner online={false} />);
    expect(screen.queryByRole("alert")).toBeNull();
    act(() => void vi.advanceTimersByTime(6_100));
    expect(screen.getByRole("alert").textContent).toMatch(/out of date/i);
  });

  it("clears as soon as the backend is back", () => {
    const { rerender } = render(<OfflineBanner online={false} />);
    act(() => void vi.advanceTimersByTime(7_000));
    expect(screen.getByRole("alert")).toBeTruthy();
    rerender(<OfflineBanner online />);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
