/** Crypto bases the app knows how to quote against USDT. */
const CRYPTO = new Set(["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA"]);

/** `/symbol/NSE/INFY`, or `/symbol/BINANCE/BTC%2FUSDT`: the detail page for a symbol. */
export function symbolPath(symbol: string, exchange = "NSE"): string {
  return `/symbol/${encodeURIComponent(exchange)}/${encodeURIComponent(symbol)}`;
}

/** A bare ticker from a headline tag (INFY, BTC) to the symbol and exchange the feed uses. */
export function resolveTag(tag: string): { symbol: string; exchange: string } {
  const base = tag.toUpperCase();
  if (CRYPTO.has(base)) return { symbol: `${base}/USDT`, exchange: "BINANCE" };
  return { symbol: base, exchange: "NSE" };
}

/** The factor engine's exchange names differ from the feed's. */
export function factorExchange(exchange: string): string {
  return exchange.toUpperCase() === "BINANCE" ? "crypto" : exchange;
}

/** The ticker as headlines tag it: BTC/USDT -> BTC, RELIANCE.NS -> RELIANCE. */
export function baseSymbol(symbol: string): string {
  return symbol.toUpperCase().split(/[/.\-:]/)[0];
}

/** The factor engine takes crypto as BTC-USD; a slash in a path segment does not survive routing. */
export function factorTicker(symbol: string, exchange: string): string {
  if (exchange.toUpperCase() === "BINANCE" && symbol.includes("/")) return `${symbol.split("/")[0].toUpperCase()}-USD`;
  return symbol;
}
