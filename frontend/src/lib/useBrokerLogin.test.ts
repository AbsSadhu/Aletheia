import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useBrokerLogin } from "./useBrokerLogin";

const loginUrl = () => Promise.resolve({ url: "https://broker.example/login" });

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(window, "open").mockReturnValue(null);
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useBrokerLogin", () => {
  it("polls after login starts and stops once the broker reports logged in", async () => {
    let loggedIn = false;
    const getStatus = vi.fn(() => Promise.resolve({ logged_in: loggedIn }));
    const { result } = renderHook(() => useBrokerLogin(getStatus, loginUrl, vi.fn(), "Kite"));
    await act(async () => {});
    expect(result.current.status).toEqual({ logged_in: false });

    await act(async () => result.current.login());
    expect(window.open).toHaveBeenCalledWith("https://broker.example/login", "_blank", "noopener");

    loggedIn = true;
    await act(async () => void (await vi.advanceTimersByTimeAsync(3000)));
    expect(result.current.status).toEqual({ logged_in: true });

    const calls = getStatus.mock.calls.length;
    await act(async () => void (await vi.advanceTimersByTimeAsync(30_000)));
    expect(getStatus.mock.calls.length).toBe(calls);
  });

  it("stops polling when the page goes away", async () => {
    const getStatus = vi.fn(() => Promise.resolve({ logged_in: false }));
    const { result, unmount } = renderHook(() => useBrokerLogin(getStatus, loginUrl, vi.fn(), "Kite"));
    await act(async () => {});
    await act(async () => result.current.login());
    unmount();

    const calls = getStatus.mock.calls.length;
    await vi.advanceTimersByTimeAsync(30_000);
    expect(getStatus.mock.calls.length).toBe(calls);
  });

  it("reports a failed login start through onError", async () => {
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useBrokerLogin(() => Promise.resolve({ logged_in: false }), () => Promise.reject(new Error("no key")), onError, "Kite"),
    );
    await act(async () => result.current.login());
    expect(onError).toHaveBeenCalledWith("no key");
  });
});
