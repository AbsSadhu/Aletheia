import { Suspense, lazy, useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, useNavigate } from "react-router-dom";

import Sidebar from "./components/Sidebar";
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
import { fetchHealth } from "./lib/api";
import { initDeepLinks } from "./lib/desktop";

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

export default function App() {
  const [backendOnline, setBackendOnline] = useState(false);

  useEffect(() => {
    fetchHealth()
      .then(() => setBackendOnline(true))
      .catch(() => setBackendOnline(false));

    // Poll backend status every 30s
    const interval = setInterval(() => {
      fetchHealth()
        .then(() => setBackendOnline(true))
        .catch(() => setBackendOnline(false));
    }, 30_000);

    return () => clearInterval(interval);
  }, []);

  return (
    <BrowserRouter>
      <DeepLinkBridge />
      <div className="app-layout">
        <Sidebar backendOnline={backendOnline} />
        <Suspense fallback={<main className="page-loading" role="status">Loading…</main>}>
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
          <Route path="/options" element={<Options />} />
          <Route path="/validation" element={<SignalValidation />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
        </Suspense>
      </div>
    </BrowserRouter>
  );
}
