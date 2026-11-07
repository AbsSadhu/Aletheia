import { useSyncExternalStore } from "react";

import { getNewsHeadlines, getNewsPulse } from "./api";
import type { NewsHeadline, NewsPulse, SentimentAlert } from "./api";
import { notifySentimentFlip } from "./desktop";

// One poller for the whole app: the top tape, the toasts and the Pulse page read the same state,
// so the feeds are asked for once per interval however many views are mounted.
/** News is fetched at least this often while the window is visible. */
export const POLL_MS = 30_000;
/** How long a freshly arrived headline stays marked as new. */
const NEW_FOR_MS = 20_000;
const SEEN_KEY = "aletheia_alerts_seen_ts";
const MAX_TOASTS = 3;

export interface NewsState {
  pulse: NewsPulse | null;
  headlines: NewsHeadline[];
  /** ids that arrived on the last refresh, for the "new" flash */
  fresh: ReadonlySet<string>;
  error: string | null;
  loaded: boolean;
  /** flip alerts waiting to be shown as toasts */
  toasts: SentimentAlert[];
  /** flip alerts raised since the Pulse page was last opened */
  unread: number;
  /** epoch ms of the last successful refresh */
  updatedAt: number | null;
}

let state: NewsState = { pulse: null, headlines: [], fresh: new Set(), error: null, loaded: false, toasts: [], unread: 0, updatedAt: null };
const listeners = new Set<() => void>();
let timer: number | null = null;
let freshTimer: number | null = null;
let inflight = false;

function readSeen(): number | null {
  try {
    const v = localStorage.getItem(SEEN_KEY);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}
function writeSeen(ms: number): void {
  try {
    localStorage.setItem(SEEN_KEY, String(ms));
  } catch {
    /* storage unavailable: alerts then re-announce after a reload, which is harmless */
  }
}
// The first run ever starts "now", so existing alerts are not announced as if they just happened.
let announcedUpTo = readSeen() ?? Date.now();
writeSeen(announcedUpTo);

function set(next: Partial<NewsState>): void {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

export function dismissToast(id: string): void {
  set({ toasts: state.toasts.filter((t) => t.id !== id) });
}

export function markAlertsRead(): void {
  if (state.unread !== 0) set({ unread: 0 });
}

function announce(alerts: SentimentAlert[]): void {
  const fresh = alerts.filter((a) => Date.parse(a.t) > announcedUpTo).sort((a, b) => Date.parse(a.t) - Date.parse(b.t));
  if (fresh.length === 0) return;
  announcedUpTo = Math.max(announcedUpTo, ...fresh.map((a) => Date.parse(a.t)));
  writeSeen(announcedUpTo);
  set({ toasts: [...state.toasts, ...fresh].slice(-MAX_TOASTS), unread: state.unread + fresh.length });
  fresh.slice(-MAX_TOASTS).forEach((a) => void notifySentimentFlip(a.symbol, a.from, a.to, a.headline?.title));
}

export async function refreshNews(): Promise<void> {
  if (inflight) return;
  inflight = true;
  try {
    const [pulse, heads] = await Promise.all([getNewsPulse(), getNewsHeadlines(80)]);
    // a malformed answer (an old backend, a proxy page) is an error, not state
    if (!pulse?.mood || !Array.isArray(heads?.headlines)) throw new Error("News response not understood");
    const known = new Set(state.headlines.map((h) => h.id));
    const arrived = state.loaded ? heads.headlines.filter((h) => !known.has(h.id)).map((h) => h.id) : [];
    set({ pulse, headlines: heads.headlines, fresh: new Set(arrived), error: null, loaded: true, updatedAt: Date.now() });
    announce(pulse.alerts ?? []);
    if (arrived.length) {
      if (freshTimer) window.clearTimeout(freshTimer);
      freshTimer = window.setTimeout(() => set({ fresh: new Set() }), NEW_FOR_MS);
    }
  } catch (e) {
    set({ error: e instanceof Error ? e.message : "News unavailable", loaded: true });
  } finally {
    inflight = false;
  }
}

// Polling runs only while the window is visible; coming back to it refreshes straight away, so
// what you see on return is never stale.
function onVisibility(): void {
  if (!document.hidden) void refreshNews();
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  if (listeners.size === 1) {
    void refreshNews();
    timer = window.setInterval(() => {
      if (!document.hidden) void refreshNews();
    }, POLL_MS);
    document.addEventListener("visibilitychange", onVisibility);
  }
  return () => {
    listeners.delete(cb);
    if (listeners.size === 0) {
      if (timer) window.clearInterval(timer);
      timer = null;
      document.removeEventListener("visibilitychange", onVisibility);
    }
  };
}

export function useNews(): NewsState {
  return useSyncExternalStore(subscribe, () => state);
}

/** "3m", "2h", "1d": how long ago an ISO timestamp was. */
export function ago(iso: string, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}
