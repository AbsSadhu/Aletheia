// Bridges to the Tauri desktop shell. Every export is a no-op in a plain browser, and the
// plugin modules are imported lazily so the web build never loads them.

export function isDesktop(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** `aletheia://run/<id>` -> `/runs/<id>`; anything else -> null. */
export function routeForDeepLink(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.protocol !== "aletheia:") return null;
  // For custom schemes the first segment parses as the host: aletheia://run/abc -> host "run".
  const [kind, id] = [parsed.hostname, parsed.pathname.replace(/^\/+/, "").split("/")[0]];
  if (kind === "run" && /^[A-Za-z0-9_-]{1,64}$/.test(id)) return `/runs/${id}`;
  return null;
}

/** Native "run finished" notification; skipped when the window is already focused. */
export async function notifyRunFinished(runId: string, status: string): Promise<void> {
  if (!isDesktop() || document.hasFocus()) return;
  try {
    const n = await import("@tauri-apps/plugin-notification");
    let granted = await n.isPermissionGranted();
    if (!granted) granted = (await n.requestPermission()) === "granted";
    if (!granted) return;
    n.sendNotification({
      title: status === "completed" ? "Analysis complete" : `Analysis ${status}`,
      body: `Run ${runId.slice(0, 8)} finished. Click to view.`,
    });
  } catch (err) {
    console.warn("Desktop notification failed", err);
  }
}

/** Route `aletheia://` links (cold start and while running) through `navigate`. Returns a cleanup. */
export async function initDeepLinks(navigate: (path: string) => void): Promise<() => void> {
  if (!isDesktop()) return () => {};
  try {
    const dl = await import("@tauri-apps/plugin-deep-link");
    const handle = (urls: string[]) => {
      for (const url of urls) {
        const route = routeForDeepLink(url);
        if (route) {
          navigate(route);
          return;
        }
      }
    };
    const initial = await dl.getCurrent();
    if (initial) handle(initial);
    return await dl.onOpenUrl(handle);
  } catch (err) {
    console.warn("Deep-link setup failed", err);
    return () => {};
  }
}
