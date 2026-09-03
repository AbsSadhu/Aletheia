import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";

import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import RunsList from "./pages/RunsList";
import RunDetail from "./pages/RunDetail";
import Portfolio from "./pages/Portfolio";
import SettingsPage from "./pages/Settings";
import PaperTrades from "./pages/PaperTrades";
import FactorExplorer from "./pages/FactorExplorer";
import ShadowTrader from "./pages/ShadowTrader";
import Backtest from "./pages/Backtest";
import Hypotheses from "./pages/Hypotheses";
import { fetchHealth } from "./lib/api";

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
      <div className="app-layout">
        <Sidebar backendOnline={backendOnline} />
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
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
