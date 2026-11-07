import { ago, useNews } from "../lib/newsStore";
import SafeLink from "./SafeLink";

/**
 * The bottom strip on every page: market mood on the left, the latest headlines rolling past.
 * Sentiment is a small coloured square, the first mentioned symbol is a tag. Pauses on hover and
 * stays still under reduced motion. Hidden until there is something to show.
 */
export default function NewsTape() {
  const { pulse, headlines } = useNews();
  const items = headlines.slice(0, 24);
  if (items.length === 0) return null;
  const mood = pulse?.mood;
  const arrow = !mood ? "" : mood.label === "bullish" ? "▲" : mood.label === "bearish" ? "▼" : "■";
  const row = [...items, ...items];
  return (
    <div className="newstape" role="region" aria-label="Market headlines">
      <SafeLink to="/pulse" className={`newstape-mood ${mood?.label ?? "neutral"}`} title="Open Market Pulse">
        <span className="newstape-arrow" aria-hidden="true">{arrow}</span>
        <span>PULSE</span>
        <b>{mood ? `${mood.value >= 0 ? "+" : ""}${mood.value.toFixed(2)}` : "–"}</b>
      </SafeLink>
      <div className="newstape-window">
        <div className="newstape-track" style={{ ["--count" as string]: items.length } as React.CSSProperties}>
          {row.map((h, i) => (
            <a key={`${h.id}-${i}`} className="nt-item" href={h.url} target="_blank" rel="noopener noreferrer" tabIndex={i >= items.length ? -1 : 0}>
              <i className={`nt-dot ${h.label}`} aria-hidden="true" />
              {h.symbols[0] && <span className="nt-sym">{h.symbols[0]}</span>}
              <span className="nt-title">{h.title}</span>
              <span className="nt-meta">
                {h.source} · {ago(h.published)}
              </span>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
