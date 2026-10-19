import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import DataWarnings from "./DataWarnings";

afterEach(cleanup);

describe("DataWarnings", () => {
  it("renders nothing when there are no warnings", () => {
    const { container } = render(<DataWarnings warnings={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when warnings are omitted (older runs)", () => {
    const { container } = render(<DataWarnings />);
    expect(container.firstChild).toBeNull();
  });

  it("shows every warning inside an alert", () => {
    render(<DataWarnings warnings={["Sample data used for TCS", "No data for XYZ"]} />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Sample data used for TCS");
    expect(alert.textContent).toContain("No data for XYZ");
  });
});
