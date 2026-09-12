# Aletheia Frontend

React 19 + Vite dashboard for the Aletheia platform. Talks to the FastAPI backend (`aletheia/core/main.py`, default `http://127.0.0.1:8899`) over REST and WebSocket — it has no server-side logic of its own.

## Stack

- React 19, react-router-dom 7 (client-side routing)
- Vite 6 + TypeScript 5.5 (project references, `tsc -b`)
- Recharts for charts, lucide-react for icons
- Hand-written CSS (`src/styles/app.css`) — no Tailwind/MUI/shadcn
- Vitest + jsdom for tests

## Getting started

```bash
npm install
npm run dev      # dev server on :5173, proxies to the backend at :8899
npm run build    # production build to dist/
npm run test     # vitest
```

Set `VITE_API_BASE_URL` (env var, read at build time by Vite) to point at a non-default backend host. This must be a URL reachable from the browser, not a Docker-network hostname.

## Layout

- `src/pages/` — one file per route (Dashboard, RunsList, RunDetail, Portfolio, PaperTrades, ShadowTrader, Backtest, Hypotheses, FactorExplorer, Settings)
- `src/lib/api.ts` — the full backend API client
- `src/components/` — shared chrome (Sidebar, TopBar)

## Notes

- The Tauri desktop app (`../desktop/`) wraps this app's production build (`dist/`) — it does not have its own separate frontend.
- No E2E/Playwright suite yet — only `src/lib/api.test.ts` (Vitest, mocked fetch).
