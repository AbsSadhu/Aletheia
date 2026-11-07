import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Surface3D from "./Surface3D";
import type { SurfaceData } from "../lib/surface";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const data: SurfaceData = {
  metric: "price",
  kind: "call",
  strike: 100,
  spots: [80, 100, 120],
  days: [1, 31, 61],
  values: [[0, 1, 2], [1, 2, 3], [2, 3, 4]],
  min: 0,
  max: 4,
};

describe("Surface3D", () => {
  it("says so instead of failing when WebGL is unavailable", () => {
    // jsdom has no canvas context, which is exactly the "no WebGL" case.
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    render(<Surface3D data={data} marker={{ spot: 100, days: 30 }} />);
    expect(screen.getByRole("status").textContent).toMatch(/needs WebGL/);
    expect(screen.queryByTestId("surface3d")).toBeNull();
  });
});
