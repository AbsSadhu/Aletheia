import { useEffect } from "react";
import { ArrowRight, X } from "lucide-react";
import { Link } from "react-router-dom";

import { dismissToast, useNews } from "../lib/newsStore";
import type { SentimentAlert } from "../lib/api";

const AUTO_DISMISS_MS = 12_000;

function Toast({ alert }: { alert: SentimentAlert }) {
  useEffect(() => {
    const id = window.setTimeout(() => dismissToast(alert.id), AUTO_DISMISS_MS);
    return () => window.clearTimeout(id);
  }, [alert.id]);
  const sign = alert.score >= 0 ? "+" : "";
  return (
    <div className={`flip-toast ${alert.to}`} role="status">
      <i className="flip-toast-mark" aria-hidden="true" />
      <div className="flip-toast-body">
        <div className="flip-toast-head">
          <b>{alert.symbol}</b> turned <b className={`tone ${alert.to}`}>{alert.to}</b>
          <span className="flip-toast-path">
            {alert.from} <ArrowRight size={11} aria-hidden="true" /> {alert.to} · {sign}
            {alert.score.toFixed(2)}
          </span>
        </div>
        {alert.headline && (
          <a className="flip-toast-why" href={alert.headline.url} target="_blank" rel="noopener noreferrer">
            {alert.headline.title}
          </a>
        )}
        <Link to="/pulse" className="flip-toast-more">
          Open Market Pulse
        </Link>
      </div>
      <button type="button" className="flip-toast-x" onClick={() => dismissToast(alert.id)} aria-label={`Dismiss ${alert.symbol} alert`}>
        <X size={14} />
      </button>
    </div>
  );
}

/** Sentiment-flip alerts, stacked under the top bar. Each one clears itself after a few seconds. */
export default function AlertToasts() {
  const { toasts } = useNews();
  if (toasts.length === 0) return null;
  return (
    <div className="flip-toasts" aria-live="polite">
      {toasts.map((t) => (
        <Toast key={t.id} alert={t} />
      ))}
    </div>
  );
}
