import { useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import { Theme } from "@astryxdesign/core/theme";
import { aletheiaTheme } from "./aletheiaTheme";

import { resolveTheme } from "./theme";
import type { Theme as Mode } from "./theme";

// The app's light/dark toggle (lib/theme.ts) writes `data-theme` on <html>, and the charts watch
// it. Astryx's <Theme> reads a `mode` prop and writes the same attribute back, so we feed it the
// attribute's value (never "system", which would make Astryx delete the attribute).

function subscribe(cb: () => void): () => void {
  const obs = new MutationObserver(cb);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => obs.disconnect();
}

function currentMode(): Mode {
  const v = document.documentElement.getAttribute("data-theme");
  return v === "light" || v === "dark" ? v : resolveTheme();
}

export function AstryxProvider({ children }: { children: ReactNode }) {
  const mode = useSyncExternalStore(subscribe, currentMode, () => "dark" as Mode);
  return (
    <Theme theme={aletheiaTheme} mode={mode}>
      {children}
    </Theme>
  );
}
