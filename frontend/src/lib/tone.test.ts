import { describe, expect, it } from "vitest";

import { toneBadge } from "./tone";

describe("toneBadge", () => {
  it.each(["BUY", "POSITIVE", "STRONGLY_POSITIVE", "UNDERVALUED", "BULLISH_OI"])("%s is positive", (v) => {
    expect(toneBadge(v)).toBe("badge-buy");
  });

  it.each(["SELL", "REDUCE", "NEGATIVE", "STRONGLY_NEGATIVE", "OVERVALUED", "BEARISH_OI"])("%s is negative", (v) => {
    expect(toneBadge(v)).toBe("badge-reduce");
  });

  it.each(["HOLD", "NEUTRAL", "FAIR", "", "something new"])("%s is neutral", (v) => {
    expect(toneBadge(v)).toBe("badge-hold");
  });
});
