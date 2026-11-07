import { defineTheme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral";

import { ASTRYX_COLOR_TOKENS } from "./palette.generated";

// The app's Astryx theme (black / red-orange). Its colors deliberately equal the legacy tokens in
// styles/app.css (light, dark), so Astryx components and legacy pages read as one UI. The palette
// decision lives in styles/palette.json (edit it, then `npm run palette`); this file only wires it in.
// Chart colors still come from the legacy hex tokens (see lib/chartTheme.ts), not from here.
export const aletheiaTheme = defineTheme({
  name: "aletheia",
  extends: neutralTheme,
  typography: {
    scale: { base: 14, ratio: 1.2 },
    body: { family: "Geist Variable", fallbacks: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" },
    heading: { family: "Bricolage Grotesque Variable", fallbacks: "'Geist Variable', sans-serif" },
    code: { family: "Geist Mono Variable", fallbacks: "'Cascadia Code', monospace" },
  },
  tokens: ASTRYX_COLOR_TOKENS,
});
