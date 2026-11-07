import { ExternalLink } from "lucide-react";

import { ago } from "../lib/newsStore";
import { resolveTag, symbolPath } from "../lib/symbols";
import type { NewsHeadline, SentimentLabel } from "../lib/api";
import SafeLink from "./SafeLink";

export const BADGE: Record<SentimentLabel, string> = { bullish: "badge-buy", bearish: "badge-reduce", neutral: "badge-pending" };

/** One headline: tone badge, the title (opens the article), and symbol tags that open the symbol page. */
export function NewsItem({ h, fresh = false, now }: { h: NewsHeadline; fresh?: boolean; now: number }) {
  return (
    <li className={`news-item${fresh ? " is-fresh" : ""}`}>
      <span className={`badge ${BADGE[h.label]}`}>{h.label}</span>
      <div className="news-body">
        <a className="news-title" href={h.url} target="_blank" rel="noopener noreferrer">
          {h.title}
          <ExternalLink size={11} aria-hidden="true" />
        </a>
        <div className="news-meta">
          {h.symbols.slice(0, 3).map((s) => {
            const r = resolveTag(s);
            return (
              <SafeLink key={s} to={symbolPath(r.symbol, r.exchange)} className="nt-sym nt-link" title={`Open ${s}`}>
                {s}
              </SafeLink>
            );
          })}
          <span>
            {h.source} · {ago(h.published, now)}
          </span>
        </div>
      </div>
    </li>
  );
}

export function NewsList({ items, fresh, now, empty }: { items: NewsHeadline[]; fresh?: ReadonlySet<string>; now: number; empty: string }) {
  if (items.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-title">No headlines</div>
        <div className="empty-state-text">{empty}</div>
      </div>
    );
  }
  return (
    <ul className="news-list">
      {items.map((h) => (
        <NewsItem key={h.id} h={h} fresh={fresh?.has(h.id)} now={now} />
      ))}
    </ul>
  );
}
