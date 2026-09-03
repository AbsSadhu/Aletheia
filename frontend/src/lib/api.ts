import type {
  AgentEvent,
  BacktestResult,
  HealthData,
  PortfolioData,
  RunResult,
  RunSummary,
} from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8899";

// ---------------------------------------------------------------------------
// API key (paired with the backend's ALETHEIA_API_KEYS — see SECURITY.md).
// Stored client-side only; the backend stays open by default and this is a
// no-op until the user sets both sides.
// ---------------------------------------------------------------------------

const API_KEY_STORAGE_KEY = "aletheia_api_key";

export function getApiKey(): string {
  try {
    return localStorage.getItem(API_KEY_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setApiKey(key: string): void {
  try {
    if (key) {
      localStorage.setItem(API_KEY_STORAGE_KEY, key);
    } else {
      localStorage.removeItem(API_KEY_STORAGE_KEY);
    }
  } catch {
    /* localStorage unavailable — ignore, auth stays open */
  }
}

function authHeaders(): Record<string, string> {
  const key = getApiKey();
  return key ? { "X-API-Key": key } : {};
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`API error ${response.status}: ${text}`);
  }
  return response.json();
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`API error ${response.status}: ${text}`);
  }
  return response.json();
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export async function fetchHealth(): Promise<HealthData> {
  return apiGet<HealthData>("/api/v1/health");
}

export async function fetchReadiness(): Promise<{ ready: boolean }> {
  return apiGet<{ ready: boolean }>("/api/v1/health/ready");
}

export async function fetchHealthDetails(): Promise<{ checks: { name: string; ok: boolean; details: string }[] }> {
  return apiGet("/api/v1/health/details");
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export async function listRuns(limit = 20): Promise<{ runs: RunSummary[] }> {
  return apiGet<{ runs: RunSummary[] }>(`/api/v1/runs?limit=${limit}`);
}

export async function getRun(runId: string): Promise<RunResult> {
  return apiGet<RunResult>(`/api/v1/runs/${runId}`);
}

export async function createRun(
  prompt: string,
  portfolio?: PortfolioData,
  background = false
): Promise<any> {
  return apiPost(`/api/v1/runs?background=${background}`, { prompt, portfolio });
}

export async function createDemoRun(): Promise<RunResult> {
  return createRun("Analyze an India-first starter portfolio", {
    name: "Starter",
    base_currency: "INR",
    holdings: [
      { symbol: "RELIANCE", quantity: 5, average_price: 2500, asset_type: "equity", exchange: "NSE", tax_profile: "equity" },
      { symbol: "TCS", quantity: 3, average_price: 3700, asset_type: "equity", exchange: "NSE", tax_profile: "equity" },
      { symbol: "INFY", quantity: 8, average_price: 1480, asset_type: "equity", exchange: "NSE", tax_profile: "equity" },
      { symbol: "HDFCBANK", quantity: 4, average_price: 1650, asset_type: "equity", exchange: "NSE", tax_profile: "equity" },
    ],
  });
}

export async function getRunEvents(runId: string): Promise<{ events: AgentEvent[] }> {
  return apiGet<{ events: AgentEvent[] }>(`/api/v1/runs/${runId}/events`);
}

export function getWebSocketUrl(runId: string): string {
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  const key = getApiKey();
  const qs = key ? `?api_key=${encodeURIComponent(key)}` : "";
  return `${wsBase}/api/v1/ws/runs/${runId}${qs}`;
}

// ---------------------------------------------------------------------------
// Portfolios
// ---------------------------------------------------------------------------

export async function listPortfolios(): Promise<{ portfolios: PortfolioData[] }> {
  return apiGet<{ portfolios: PortfolioData[] }>("/api/v1/portfolios");
}

export async function getPortfolio(name: string): Promise<PortfolioData> {
  return apiGet<PortfolioData>(`/api/v1/portfolios/${encodeURIComponent(name)}`);
}

export async function savePortfolio(portfolio: PortfolioData): Promise<PortfolioData> {
  return apiPost<PortfolioData>("/api/v1/portfolios", portfolio);
}

export async function deletePortfolio(name: string): Promise<boolean> {
  const response = await fetch(`${API_BASE_URL}/api/v1/portfolios/${encodeURIComponent(name)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return response.ok;
}

export async function syncZerodha(name: string): Promise<{ status: string; synced: number; is_mock: boolean; portfolio: PortfolioData }> {
  return apiPost(`/api/v1/portfolios/${encodeURIComponent(name)}/sync-zerodha`, {});
}

// ---------------------------------------------------------------------------
// Paper Trades
// ---------------------------------------------------------------------------

export interface PaperTrade {
  trade_id: string;
  run_id: string | null;
  symbol: string;
  exchange: string;
  side: string;
  recommendation: string;
  simulated_qty: number;
  simulated_fill_price: number;
  simulated_pnl: number;
  status: string;
  timestamp: string;
  actual_close?: number | null;
}

export interface PaperPosition {
  symbol: string;
  exchange: string;
  quantity: number;
  average_price: number;
  realized_pnl: number;
  updated_at: string;
}

export async function listPaperTrades(limit = 50): Promise<{ trades: PaperTrade[] }> {
  return apiGet<{ trades: PaperTrade[] }>(`/api/v1/execution/paper-trades?limit=${limit}`);
}

export interface VirtualPosition {
  symbol: string;
  quantity: number;
  average_price: number;
  current_price: number;
  unrealized_pnl: number;
}

export interface ShadowOrder {
  id: string;
  symbol: string;
  action: string;
  quantity: number;
  price: number;
  timestamp: string;
}

export interface ShadowSnapshot {
  timestamp: string;
  total_equity: number;
  cash_balance: number;
  positions: VirtualPosition[];
}

export async function getShadowPositions(): Promise<{ positions: VirtualPosition[] }> {
  return apiGet<{ positions: VirtualPosition[] }>("/api/v1/shadow/positions");
}

export async function getShadowOrders(limit = 100): Promise<{ orders: ShadowOrder[] }> {
  return apiGet<{ orders: ShadowOrder[] }>(`/api/v1/shadow/orders?limit=${limit}`);
}

export async function getShadowPerformance(
  limit = 200
): Promise<{ equity_curve: ShadowSnapshot[]; latest: ShadowSnapshot | null }> {
  return apiGet<{ equity_curve: ShadowSnapshot[]; latest: ShadowSnapshot | null }>(
    `/api/v1/shadow/performance?limit=${limit}`
  );
}

export async function submitShadowOrder(
  symbol: string,
  exchange: string,
  action: string,
  quantity: number
): Promise<{ trade: ShadowOrder }> {
  return apiPost<{ trade: ShadowOrder }>("/api/v1/shadow/orders", { symbol, exchange, action, quantity });
}

export async function getPaperPositions(): Promise<{ positions: PaperPosition[] }> {
  return apiGet<{ positions: PaperPosition[] }>("/api/v1/execution/positions");
}

export async function settlePaperTrade(tradeId: string, actualClose: number): Promise<{ trade: PaperTrade }> {
  return apiPost<{ trade: PaperTrade }>(
    `/api/v1/execution/paper-trades/${tradeId}/settle?actual_close=${actualClose}`,
    {}
  );
}

// ---------------------------------------------------------------------------
// Factors
// ---------------------------------------------------------------------------

export interface FactorOutput {
  name: string;
  category: string;
  value: number;
  normalized: number;
  signal: "BUY" | "HOLD" | "SELL";
  confidence: number;
  description: string;
}

export interface FactorResult {
  ticker: string;
  exchange: string;
  bars: number;
  from: string;
  to: string;
  factors: Record<string, FactorOutput>;
  composite: {
    composite_score: number;
    signal: "BUY" | "HOLD" | "SELL";
    confidence: number;
    factor_count: number;
  };
}

export async function computeFactors(ticker: string, exchange = "NSE"): Promise<FactorResult> {
  return apiGet<FactorResult>(`/api/v1/factors/${encodeURIComponent(ticker)}?exchange=${exchange}`);
}

export async function getICScores(ticker: string): Promise<{ ticker: string; ic_scores: any[] }> {
  return apiGet(`/api/v1/factors/${encodeURIComponent(ticker)}/ic-scores`);
}

// ---------------------------------------------------------------------------
// Agent Memory
// ---------------------------------------------------------------------------

export interface AgentObservation {
  id: number;
  agent_name: string;
  ticker: string;
  observation: string;
  confidence: number;
  timestamp: string;
  run_id: string | null;
}

export async function getAgentMemory(
  agentName: string,
  ticker?: string,
  limit = 20
): Promise<{ agent: string; observations: AgentObservation[] }> {
  const qs = `?limit=${limit}${ticker ? `&ticker=${encodeURIComponent(ticker)}` : ""}`;
  return apiGet(`/api/v1/memory/${agentName}${qs}`);
}

export async function getAgentCritique(agentName: string): Promise<{ agent: string; latest_critique: string | null; history: any[] }> {
  return apiGet(`/api/v1/memory/${agentName}/critique`);
}

// ---------------------------------------------------------------------------
// Risk Metrics
// ---------------------------------------------------------------------------

export interface RiskMetrics {
  sharpe: number;
  sortino: number;
  calmar: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  var_95: number;
  cvar_95: number;
  skewness: number;
  kurtosis: number;
  information_ratio: number | null;
  comment: string;
}

export async function getRiskMetrics(): Promise<{ metrics: RiskMetrics | null; message?: string }> {
  return apiGet("/api/v1/risk/metrics");
}

// ---------------------------------------------------------------------------
// Backtest
// ---------------------------------------------------------------------------

export async function runBacktest(config: {
  symbols: string[];
  start_date: string;
  end_date: string;
  strategy?: string;
  initial_capital?: number;
}): Promise<BacktestResult> {
  return apiPost<BacktestResult>("/api/v1/backtest", config);
}

// ---------------------------------------------------------------------------
// Hypotheses
// ---------------------------------------------------------------------------

export interface Evidence {
  source: string;
  description: string;
  date_added: string;
  supports_hypothesis: boolean;
}

export interface Hypothesis {
  id: string;
  title: string;
  description: string;
  status: "proposed" | "testing" | "validated" | "rejected";
  test_criteria: string;
  evidence: Evidence[];
  backtest_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export async function listHypotheses(status?: string): Promise<{ hypotheses: Hypothesis[] }> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiGet<{ hypotheses: Hypothesis[] }>(`/api/v1/hypotheses${qs}`);
}

export async function getHypothesis(id: string): Promise<Hypothesis> {
  return apiGet<Hypothesis>(`/api/v1/hypotheses/${encodeURIComponent(id)}`);
}

export async function proposeHypothesis(
  title: string,
  description: string,
  test_criteria: string,
): Promise<Hypothesis> {
  return apiPost<Hypothesis>("/api/v1/hypotheses", { title, description, test_criteria });
}

export async function transitionHypothesis(id: string, new_status: string): Promise<Hypothesis> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/hypotheses/${encodeURIComponent(id)}/transition`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ new_status }),
    },
  );
  if (!response.ok) {
    throw new Error(`Failed to transition hypothesis: ${response.status}`);
  }
  return response.json();
}

export async function addHypothesisEvidence(
  id: string,
  source: string,
  summary: string,
  supports: boolean,
): Promise<Hypothesis> {
  return apiPost<Hypothesis>(`/api/v1/hypotheses/${encodeURIComponent(id)}/evidence`, {
    source,
    summary,
    supports,
  });
}

export async function linkHypothesisToBacktest(
  id: string,
  backtest_run_id: string,
): Promise<Hypothesis> {
  return apiPost<Hypothesis>(`/api/v1/hypotheses/${encodeURIComponent(id)}/link-backtest`, {
    backtest_run_id,
  });
}

// ---------------------------------------------------------------------------
// Memory Search
// ---------------------------------------------------------------------------

export async function searchMemory(q: string, limit = 8): Promise<any> {
  return apiGet(`/api/v1/memory/search?q=${encodeURIComponent(q)}&limit=${limit}`);
}

// ---------------------------------------------------------------------------
// Configuration / Settings
// ---------------------------------------------------------------------------

export async function getSystemConfig(): Promise<any> {
  return apiGet("/api/v1/config");
}

export async function updateSystemConfig(config: Record<string, any>): Promise<any> {
  return apiPost("/api/v1/config", config);
}
