import { useEffect, useState } from "react";
import { Check, ShieldAlert, X } from "lucide-react";

import { executeProposal, getProposal, rejectProposal } from "../../../lib/chatApi";
import type { ProposalStatus } from "../../../lib/chatApi";
import { money } from "../../../lib/ohlcv";
import type { ProposalDisplay } from "../../../lib/ohlcv";

const STATUS_TEXT: Record<ProposalStatus, string> = {
  pending: "Waiting for your confirmation",
  executing: "Placing…",
  executed: "Placed (paper)",
  rejected: "Rejected",
  expired: "Expired",
  failed: "Not placed",
};

/**
 * A trade the assistant proposed. It is only a request: nothing happens until the user presses
 * Confirm, and the order goes through the normal paper-trading path with its risk limits.
 */
export default function ProposalCard({ display }: { display: ProposalDisplay }) {
  const [status, setStatus] = useState<ProposalStatus>("pending");
  const [detail, setDetail] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // A reopened thread must show what actually happened, not "pending" forever.
  useEffect(() => {
    let live = true;
    getProposal(display.proposal_id)
      .then((p) => {
        if (!live) return;
        setStatus(p.status);
        const outcome = p.outcome as { trade?: { simulated_fill_price?: number }; error?: string } | null;
        if (outcome?.error) setDetail(outcome.error);
        if (outcome?.trade?.simulated_fill_price)
          setDetail(`Filled at ${money(outcome.trade.simulated_fill_price, display.currency)}`);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [display.proposal_id, display.currency]);

  const act = async (kind: "execute" | "reject") => {
    if (busy) return;
    setBusy(true);
    setDetail(null);
    try {
      if (kind === "reject") {
        const p = await rejectProposal(display.proposal_id);
        setStatus(p.status);
      } else {
        setStatus("executing");
        const res = await executeProposal(display.proposal_id);
        setStatus(res.proposal.status);
        const fill = (res.trade as { simulated_fill_price?: number }).simulated_fill_price;
        if (fill) setDetail(`Filled at ${money(fill, display.currency)}`);
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : "Something went wrong";
      setDetail(message);
      // Ask the server what state it is really in (it may have failed, or already been placed).
      getProposal(display.proposal_id)
        .then((p) => setStatus(p.status))
        .catch(() => setStatus("failed"));
    } finally {
      setBusy(false);
    }
  };

  const buy = display.side === "BUY";
  return (
    <figure className={`chat-proposal ${status}`} aria-label="Proposed paper order">
      <figcaption>
        <ShieldAlert size={13} /> Proposed paper order
        <span className="chat-chip warn">simulated</span>
      </figcaption>
      <div className="chat-proposal-main">
        <span className={`chat-proposal-side ${buy ? "buy" : "sell"}`}>{display.side}</span>
        <span className="chat-proposal-qty">
          {display.quantity} × <b>{display.symbol}</b>
        </span>
        <span className="chat-muted">{display.exchange}</span>
      </div>
      <dl>
        <dt>Type</dt>
        <dd>{display.order_type === "LIMIT" && display.limit_price ? `LIMIT @ ${money(display.limit_price, display.currency)}` : "MARKET"}</dd>
        <dt>Last close</dt>
        <dd>{money(display.reference_price, display.currency)}</dd>
        <dt>Est. value</dt>
        <dd>{money(display.estimated_value, display.currency)}</dd>
      </dl>
      {display.rationale && <p className="chat-proposal-why">{display.rationale}</p>}
      <div className="chat-proposal-foot">
        <span className="chat-proposal-status" role="status">
          {STATUS_TEXT[status]}
          {detail ? ` · ${detail}` : ""}
        </span>
        {status === "pending" && (
          <span className="chat-proposal-actions">
            <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void act("reject")}>
              <X size={13} /> Reject
            </button>
            <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => void act("execute")}>
              <Check size={13} /> Confirm
            </button>
          </span>
        )}
      </div>
    </figure>
  );
}
