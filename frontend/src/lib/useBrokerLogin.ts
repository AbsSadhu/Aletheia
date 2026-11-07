import { useCallback, useEffect, useRef, useState } from "react";

const POLL_MS = 3000;
const GIVE_UP_MS = 120_000;

/**
 * A broker whose daily login happens on the broker's own site (Zerodha, Fyers). `login()` opens that
 * site in a new tab; the broker redirects back to the backend, which stores the token, so we poll the
 * status until it flips to logged in (or two minutes pass) and stop polling when the page goes away.
 */
export function useBrokerLogin<S extends { logged_in: boolean }>(
  getStatus: () => Promise<S>,
  getLoginUrl: () => Promise<{ url: string }>,
  onError: (message: string) => void,
  name: string,
) {
  const [status, setStatus] = useState<S | null>(null);
  const timers = useRef<{ poll?: ReturnType<typeof setInterval>; giveUp?: ReturnType<typeof setTimeout> }>({});
  // Callers may pass inline functions; keep the latest in a ref so the effects below run once.
  const latest = useRef({ getStatus, getLoginUrl, onError });
  latest.current = { getStatus, getLoginUrl, onError };

  const stopPolling = useCallback(() => {
    clearInterval(timers.current.poll);
    clearTimeout(timers.current.giveUp);
  }, []);

  const refresh = useCallback(
    () =>
      latest.current
        .getStatus()
        .then((s) => {
          setStatus(s);
          if (s.logged_in) stopPolling();
        })
        .catch(() => setStatus(null)),
    [stopPolling],
  );

  useEffect(() => {
    void refresh();
    return stopPolling;
  }, [refresh, stopPolling]);

  const login = useCallback(async () => {
    try {
      const { url } = await latest.current.getLoginUrl();
      window.open(url, "_blank", "noopener");
      stopPolling();
      timers.current.poll = setInterval(() => void refresh(), POLL_MS);
      timers.current.giveUp = setTimeout(stopPolling, GIVE_UP_MS);
    } catch (err) {
      latest.current.onError(err instanceof Error ? err.message : `Could not start ${name} login`);
    }
  }, [refresh, stopPolling, name]);

  return { status, login };
}
