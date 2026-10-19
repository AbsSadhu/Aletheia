/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf-8"));

export default defineConfig({
  plugins: [react()],
  define: {
    // Single source for the version shown in the UI.
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    port: 5173
  },
  build: {
    rollupOptions: {
      output: {
        // Keep the heavy charting library out of the entry chunk; it is only
        // needed by pages that draw charts.
        manualChunks: {
          recharts: ["recharts"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
  }
});
