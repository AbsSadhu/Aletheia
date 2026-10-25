import { describe, expect, it } from "vitest";

import { toTradingViewSymbol, tradingViewUrl } from "./tradingview";

describe("toTradingViewSymbol", () => {
  it("maps Indian exchanges and crypto", () => {
    expect(toTradingViewSymbol("reliance", "nse")).toBe("NSE:RELIANCE");
    expect(toTradingViewSymbol("TCS", "BSE")).toBe("BSE:TCS");
    expect(toTradingViewSymbol("BTC/USDT", "BINANCE")).toBe("BINANCE:BTCUSDT");
    expect(toTradingViewSymbol("ETH/USDT", "NSE")).toBe("BINANCE:ETHUSDT"); // slash means crypto
  });
});

describe("tradingViewUrl", () => {
  it("builds a link to the full TradingView chart, URL-encoded", () => {
    expect(tradingViewUrl("M&M", "NSE")).toBe("https://www.tradingview.com/chart/?symbol=NSE%3AM%26M");
    expect(tradingViewUrl("RELIANCE", "NSE")).toContain("symbol=NSE%3ARELIANCE");
  });
});
