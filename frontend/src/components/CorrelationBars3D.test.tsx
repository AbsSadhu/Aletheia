import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CorrelationBars3D, { correlationColor } from "./CorrelationBars3D";

const matrix = { labels: ["AAA", "BBB"], values: [[1, 0.4], [0.4, 1]] };

describe("CorrelationBars3D", () => {
  afterEach(() => vi.restoreAllMocks());

  it("colours positive warm, negative cool and zero dark", () => {
    const [pr, , pb] = correlationColor(1);
    const [nr, , nb] = correlationColor(-1);
    expect(pr).toBeGreaterThan(pb);
    expect(nb).toBeGreaterThan(nr);
    expect(correlationColor(0)[0]).toBeLessThan(0.2);
  });

  it("falls back to a readable table without WebGL", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    render(<CorrelationBars3D matrix={matrix} />);
    expect(screen.getAllByText("0.40").length).toBe(2);
  });
});
