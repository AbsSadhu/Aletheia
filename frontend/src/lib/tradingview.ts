/** Aletheia (symbol, exchange) -> TradingView symbol, e.g. RELIANCE/NSE -> NSE:RELIANCE. */
export function toTradingViewSymbol(symbol: string, exchange: string): string {
  const s = symbol.toUpperCase();
  const e = exchange.toUpperCase();
  if (e === "BINANCE" || s.includes("/")) return `BINANCE:${s.replace("/", "")}`;
  return `${e}:${s}`;
}

/** Full TradingView chart for a symbol, for opening in a new tab (their site carries NSE data). */
export function tradingViewUrl(symbol: string, exchange: string): string {
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(toTradingViewSymbol(symbol, exchange))}`;
}
