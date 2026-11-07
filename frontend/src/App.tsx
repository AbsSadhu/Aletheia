import { Suspense, lazy, useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from "react-router-dom";
import { LinkProvider } from "@astryxdesign/core/Link";

import AlertToasts from "./components/AlertToasts";
import OfflineBanner from "./components/OfflineBanner";
import PageErrorBoundary from "./components/PageErrorBoundary";
import Sidebar from "./components/Sidebar";
const CommandMenu = lazy(() => import("./components/CommandMenu"));
const ChatPanel = lazy(() => import("./components/chat/ChatPanel"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const RunsList = lazy(() => import("./pages/RunsList"));
const RunDetail = lazy(() => import("./pages/RunDetail"));
const Portfolio = lazy(() => import("./pages/Portfolio"));
const SettingsPage = lazy(() => import("./pages/Settings"));
const PaperTrades = lazy(() => import("./pages/PaperTrades"));
const FactorExplorer = lazy(() => import("./pages/FactorExplorer"));
const ShadowTrader = lazy(() => import("./pages/ShadowTrader"));
const Backtest = lazy(() => import("./pages/Backtest"));
const Hypotheses = lazy(() => import("./pages/Hypotheses"));
const Options = lazy(() => import("./pages/Options"));
const SignalValidation = lazy(() => import("./pages/SignalValidation"));
const LiveMarket = lazy(() => import("./pages/LiveMarket"));
const Pulse = lazy(() => import("./pages/Pulse"));
const Journal = lazy(() => import("./pages/Journal"));
const Correlation = lazy(() => import("./pages/Correlation"));
const SymbolDetail = lazy(() => import("./pages/SymbolDetail"));
import RouterLink from "./components/RouterLink";
import { fetchHealth } from "./lib/api";
import { initDeepLinks } from "./lib/desktop";

// The Cmd+K menu is loaded the first time it is asked for, so it costs nothing until used.
function CommandMenuLoader() {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setArmed(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  if (!armed) return null;
  return (
    <Suspense fallback={null}>
      <CommandMenu initiallyOpen />
    </Suspense>
  );
}

// Must render inside <BrowserRouter>; routes aletheia://run/<id> links from the desktop shell.
function DeepLinkBridge() {
  const navigate = useNavigate();
  useEffect(() => {
    let cleanup = () => {};
    void initDeepLinks(navigate).then((c) => (cleanup = c));
    return () => cleanup();
  }, [navigate]);
  return null;
}

// Keeps the sidebar alive when a page throws; resets on navigation.
function GuardedRoutes({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  return <PageErrorBoundary resetKey={pathname}>{children}</PageErrorBoundary>;
}

export default function App() {
  const [backendOnline, setBackendOnline] = useState(false);

  useEffect(() => {
    const check = () =>
      fetchHealth()
        .then(() => setBackendOnline(true))
        .catch(() => setBackendOnline(false));
    void check();
    // While the backend is unreachable (e.g. the desktop app's sidecar is still starting) retry
    // every 3s so "offline" clears as soon as it is up; once connected, a relaxed 30s check.
    const interval = setInterval(check, backendOnline ? 30_000 : 3_000);
    return () => clearInterval(interval);
  }, [backendOnline]);

  return (
    <BrowserRouter>
      <LinkProvider component={RouterLink}>
      <DeepLinkBridge />
      <div className="app-layout">
        <Sidebar backendOnline={backendOnline} />
        <Suspense fallback={<main className="page-loading" role="status">Loading…</main>}>
        <GuardedRoutes>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/runs" element={<RunsList />} />
          <Route path="/runs/:runId" element={<RunDetail />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/paper-trades" element={<PaperTrades />} />
          <Route path="/shadow-trader" element={<ShadowTrader />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/hypotheses" element={<Hypotheses />} />
          <Route path="/factors" element={<FactorExplorer />} />
          <Route path="/live" element={<LiveMarket />} />
          <Route path="/pulse" element={<Pulse />} />
          <Route path="/journal" element={<Journal />} />
          <Route path="/correlation" element={<Correlation />} />
          <Route path="/symbol/:exchange/:symbol" element={<SymbolDetail />} />
          <Route path="/options" element={<Options />} />
          <Route path="/validation" element={<SignalValidation />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
        </GuardedRoutes>
        </Suspense>
      </div>
      <OfflineBanner online={backendOnline} />
      <AlertToasts />
      <Suspense fallback={null}>
        <ChatPanel />
      </Suspense>
      <CommandMenuLoader />
      </LinkProvider>
    </BrowserRouter>
  );
}
