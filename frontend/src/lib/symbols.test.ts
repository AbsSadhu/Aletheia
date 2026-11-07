import { describe, expect, it } from "vitest";

import { apiErrorMessage } from "./api";
import { baseSymbol, factorExchange, factorTicker, resolveTag, symbolPath } from "./symbols";

describe("symbol helpers", () => {
  it("builds a path that survives a slash in the symbol", () => {
    expect(symbolPath("INFY", "NSE")).toBe("/symbol/NSE/INFY");
    expect(symbolPath("BTC/USDT", "BINANCE")).toBe("/symbol/BINANCE/BTC%2FUSDT");
  });

  it("resolves a headline tag to a feed symbol", () => {
    expect(resolveTag("infy")).toEqual({ symbol: "INFY", exchange: "NSE" });
    expect(resolveTag("BTC")).toEqual({ symbol: "BTC/USDT", exchange: "BINANCE" });
  });

  it("maps to the factor engine's names", () => {
    expect(factorExchange("BINANCE")).toBe("crypto");
    expect(factorExchange("NSE")).toBe("NSE");
    expect(factorTicker("BTC/USDT", "BINANCE")).toBe("BTC-USD");
    expect(factorTicker("INFY", "NSE")).toBe("INFY");
  });

  it("reduces a ticker to the form headlines use", () => {
    expect(baseSymbol("BTC/USDT")).toBe("BTC");
    expect(baseSymbol("reliance.ns")).toBe("RELIANCE");
  });
});

describe("apiErrorMessage", () => {
  it("shows the backend's message, not the JSON", () => {
    expect(apiErrorMessage(404, '{"code":"HTTP_404","message":"No 5m data for X.","detail":null}')).toBe("No 5m data for X.");
  });
  it("falls back to detail, then to the raw body", () => {
    expect(apiErrorMessage(422, '{"detail":"symbol is required"}')).toBe("symbol is required");
    expect(apiErrorMessage(500, "boom")).toBe("API error 500: boom");
  });
});
