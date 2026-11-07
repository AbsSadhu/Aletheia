import { WifiOff } from "lucide-react";
import { useEffect, useState } from "react";

/** How long the backend must stay unreachable before the banner shows, so a slow start-up does not flash it. */
const GRACE_MS = 6000;

/**
 * Says so, loudly, when the backend is unreachable: whatever is on screen is the last thing that
 * arrived, not the current state of anything.
 */
export default function OfflineBanner({ online }: { online: boolean }) {
  const [grace, setGrace] = useState(false);

  useEffect(() => {
    if (online) {
      setGrace(false);
      return;
    }
    const t = window.setTimeout(() => setGrace(true), GRACE_MS);
    return () => window.clearTimeout(t);
  }, [online]);

  if (online || !grace) return null;
  return (
    <div className="offline-banner" role="alert">
      <WifiOff size={16} aria-hidden="true" />
      <span>
        <b>Cannot reach the Aletheia backend.</b> Numbers on this screen may be out of date until it reconnects.
      </span>
    </div>
  );
}
