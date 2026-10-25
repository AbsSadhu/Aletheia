import { useEffect, useRef, useState } from "react";

import { getMarketSocketUrl } from "./api";
import type { LiveQuote } from "./api";

export type FeedConnection = "connecting" | "open" | "closed";

export interface FeedState {
  quotes: Record<string, LiveQuote>;
  /** key -> direction of the most recent price move, for the flash animation */
  moves: Record<string, "up" | "down">;
  connection: FeedConnection;
  lastMessageAt: number | null;
}

export const quoteKey = (symbol: string, exchange: string) => `${exchange}:${symbol}`;

/** Subscribes to /ws/market and keeps the latest quote per symbol; reconnects with backoff. */
export function useMarketFeed(): FeedState {
  const [state, setState] = useState<FeedState>({
    quotes: {},
    moves: {},
    connection: "connecting",
    lastMessageAt: null,
  });
  const pending = useRef<Record<string, LiveQuote>>({});

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry = 0;
    let timer: number | undefined;
    let closed = false;

    // Apply incoming quotes in one render per animation frame, however fast they arrive.
    const flush = window.setInterval(() => {
      const batch = pending.current;
      if (Object.keys(batch).length === 0) return;
      pending.current = {};
      setState((prev) => {
        const quotes = { ...prev.quotes };
        const moves = { ...prev.moves };
        for (const [key, q] of Object.entries(batch)) {
          const old = prev.quotes[key];
          if (old && q.close !== old.close) moves[key] = q.close > old.close ? "up" : "down";
          quotes[key] = q;
        }
        return { ...prev, quotes, moves, lastMessageAt: Date.now() };
      });
    }, 250);

    const connect = () => {
      if (closed) return;
      setState((p) => ({ ...p, connection: "connecting" }));
      socket = new WebSocket(getMarketSocketUrl());
      socket.onopen = () => {
        retry = 0;
        setState((p) => ({ ...p, connection: "open" }));
      };
      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          const q = msg.payload as LiveQuote | undefined;
          if (q?.symbol && typeof q.close === "number") {
            pending.current[quoteKey(q.symbol, q.exchange)] = q;
          }
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onclose = () => {
        setState((p) => ({ ...p, connection: "closed" }));
        if (closed) return;
        retry += 1;
        timer = window.setTimeout(connect, Math.min(1000 * 2 ** retry, 15000));
      };
      socket.onerror = () => socket?.close();
    };
    connect();

    return () => {
      closed = true;
      window.clearInterval(flush);
      if (timer) window.clearTimeout(timer);
      socket?.close();
    };
  }, []);

  return state;
}
