export interface TickItem {
  symbol: string;
  price: string;
  change: string;
  dir: "up" | "down" | "flat";
}

/**
 * A scrolling tape of the watchlist. It is decoration over data the table already shows, so it is
 * hidden from assistive tech and its text lives in CSS (data attributes), which also keeps it out
 * of text queries. Pauses on hover; stands still when motion is reduced.
 */
export default function Ticker({ items }: { items: TickItem[] }) {
  if (items.length === 0) return null;
  // two copies so the loop is seamless
  const row = [...items, ...items];
  return (
    <div className="ticker" aria-hidden="true">
      <div className="ticker-track" style={{ ["--count" as string]: items.length } as React.CSSProperties}>
        {row.map((t, i) => (
          <span key={i} className="tk" data-s={t.symbol} data-p={t.price} data-c={t.change} data-dir={t.dir} />
        ))}
      </div>
    </div>
  );
}
