import type { SurfaceData, SurfaceMetric } from "./surface";
import type {
  AgentEvent,
  BacktestResult,
  HealthData,
  PortfolioData,
  RunResult,
  RunSummary,
} from "./types";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8899";

// API key (paired with the backend's ALETHEIA_API_KEYS — see SECURITY.md).
// Stored client-side only; the backend stays open by default and this is a
// no-op until the user sets both sides.

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

export function authHeaders(): Record<string, string> {
  const key = getApiKey();
  return key ? { "X-API-Key": key } : {};
}

// Helper

/** The backend answers errors as {"code","message","detail"}; show the message, not the JSON. */
export function apiErrorMessage(status: number, body: string): string {
  try {
    const j = JSON.parse(body) as { message?: unknown; detail?: unknown };
    if (typeof j.message === "string" && j.message) return j.message;
    if (typeof j.detail === "string" && j.detail) return j.detail;
  } catch {
    /* not JSON: fall through */
  }
  return `API error ${status}: ${body}`;
}

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(apiErrorMessage(response.status, text));
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
    throw new Error(apiErrorMessage(response.status, text));
  }
  return response.json();
}

// Health

export async function fetchHealth(): Promise<HealthData> {
  return apiGet<HealthData>("/api/v1/health");
}

// Runs

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

// Portfolios

export async function listPortfolios(): Promise<{ portfolios: PortfolioData[] }> {
  return apiGet<{ portfolios: PortfolioData[] }>("/api/v1/portfolios");
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

// Paper Trades

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

export interface ExecutionState {
  mode: "simulation" | "paper" | "live";
  paused: boolean;
}

export async function getExecutionState(): Promise<{ state: ExecutionState }> {
  return apiGet("/api/v1/execution/state");
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

// Factors

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

// Agent Memory

export interface AgentObservation {
  id: number;
  agent_name: string;
  ticker: string;
  observation: string;
  confidence: number;
  timestamp: string;
  run_id: string | null;
}

// Risk Metrics

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

// Backtest

export async function runBacktest(config: {
  symbols: string[];
  start_date: string;
  end_date: string;
  strategy?: string;
  initial_capital?: number;
  cost_model?: string;
}): Promise<BacktestResult> {
  return apiPost<BacktestResult>("/api/v1/backtest", config);
}

// Hypotheses

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

// Memory Search

// Configuration / Settings

export async function getSystemConfig(): Promise<any> {
  return apiGet("/api/v1/config");
}

export async function updateSystemConfig(config: Record<string, any>): Promise<any> {
  return apiPost("/api/v1/config", config);
}

// Options pricing

export interface OptionPrice {
  kind: "call" | "put";
  price: number;
  intrinsic: number;
  delta: number;
  gamma: number;
  theta_per_day: number;
  vega_per_vol_point: number;
}

export async function priceOption(p: {
  spot: number;
  strike: number;
  days: number;
  vol_pct: number;
  rate_pct: number;
  kind: "call" | "put";
}): Promise<OptionPrice> {
  const qs = new URLSearchParams(Object.entries(p).map(([k, v]) => [k, String(v)]));
  return apiGet<OptionPrice>(`/api/v1/options/price?${qs}`);
}

export async function getOptionSurface(p: {
  spot: number;
  strike: number;
  vol_pct: number;
  rate_pct: number;
  kind: "call" | "put";
  metric: SurfaceMetric;
  max_days: number;
}): Promise<SurfaceData> {
  const qs = new URLSearchParams(Object.entries(p).map(([k, v]) => [k, String(v)]));
  return apiGet<SurfaceData>(`/api/v1/options/surface?${qs}`);
}

// Broker connection

export async function zerodhaStatus(): Promise<{ configured: boolean; logged_in: boolean }> {
  return apiGet("/api/v1/brokers/zerodha/status");
}

export async function zerodhaLoginUrl(): Promise<{ url: string }> {
  return apiGet("/api/v1/brokers/zerodha/login-url");
}

// Signal validation

export interface PerfBlock {
  total_return_pct?: number;
  cagr_pct?: number;
  volatility_pct?: number;
  sharpe?: number;
  max_drawdown_pct?: number;
  beta?: number;
  alpha_pct?: number;
  information_ratio?: number;
}

export interface SignalBacktest {
  period: { start: string; end: string };
  config: { universe_size: number; max_positions: number; rebalance_days: number };
  strategy: PerfBlock;
  strategy_post_tax: PerfBlock;
  nifty: PerfBlock;
  equal_weight: PerfBlock;
  out_of_sample: { start: string | null; strategy_post_tax: PerfBlock; nifty: PerfBlock; note: string };
  trading: {
    trades: number;
    win_rate_pct: number;
    avg_holding_days: number;
    stopped_out_pct: number;
    trading_costs_inr: number;
    tax_paid_inr: number;
    gross_final_equity: number;
    post_tax_final_equity: number;
    avg_invested_pct: number;
  };
  verdict: { status: "PASS" | "FAIL" | "INCONCLUSIVE"; headline: string; reasons: string[] };
  equity_curve: { date: string; strategy: number; nifty: number; equal_weight: number | null }[];
  caveats: string[];
  missing_symbols?: string[];
  ran_at?: string;
}

export async function runSignalBacktest(body: {
  years?: number;
  max_positions?: number;
  rebalance_days?: number;
}): Promise<SignalBacktest> {
  return apiPost<SignalBacktest>("/api/v1/backtest/signal", body);
}

export async function getLatestSignalBacktest(): Promise<{ result: SignalBacktest | null }> {
  return apiGet("/api/v1/backtest/signal/latest");
}

export interface AccuracyBlock {
  n: number;
  hit_rate_pct: number | null;
  avg_confidence: number;
  avg_return_7d_pct: number;
  brier: number | null;
}

export interface SignalAccuracy {
  resolved: number;
  pending: number;
  enough_data: boolean;
  coin_flip_brier: number;
  overall: AccuracyBlock | null;
  by_signal: Record<string, AccuracyBlock>;
  calibration: { range: string; n: number; claimed_pct: number; actual_hit_rate_pct: number | null }[];
  by_symbol: (AccuracyBlock & { symbol: string })[];
  verdict: string;
}

export async function getSignalAccuracy(): Promise<SignalAccuracy> {
  return apiGet("/api/v1/signals/accuracy");
}

export async function getShadowVsNifty(): Promise<{
  points: { date: string; shadow_pct: number; nifty_pct: number }[];
  excess_pct?: number;
  days?: number;
  note: string;
}> {
  return apiGet("/api/v1/signals/shadow-vs-nifty");
}

// Live market feed

export interface WatchItem {
  symbol: string;
  exchange: string;
}

export interface LiveQuote {
  symbol: string;
  exchange: string;
  close: number; // latest price
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
  prev_close?: number | null;
  price_exchange?: string; // the exchange the PRICE comes from, when it differs from the watchlist row
  exchange_time?: string | null; // the exchange's own 'as on' time
  data_lag_secs?: number | null; // how far the exchange time trails our clock during market hours
  change_pct?: number | null;
  as_of: string;
  provider: string;
  stream?: boolean;
  price_scale_verified?: boolean | null;
}

export interface FeedStatus {
  mode: "stream" | "polling" | "idle";
  source: string;
  provider?: "angel_one" | "fyers" | "bse_web";
  market: { state: string; label: string; is_open: boolean; ist_time: string; note: string };
  stream: {
    connected: boolean;
    symbols: number;
    ticks: number;
    last_tick_age_secs: number | null;
    reconnects: number;
    price_scale_verified: boolean | null;
    error: string | null;
    unofficial?: boolean;
    data_lag_secs?: number | null;
    poll_secs?: number;
  } | null;
  stream_configured: boolean;
  crypto?: {
    connected: boolean;
    source: string;
    symbols: number;
    ticks: number;
    last_tick_age_secs: number | null;
    error: string | null;
    window: string;
  } | null;
  setup_hint: string | null;
  unresolved_symbols: string[];
}

export function getMarketSocketUrl(): string {
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  const key = getApiKey();
  return `${wsBase}/api/v1/ws/market${key ? `?api_key=${encodeURIComponent(key)}` : ""}`;
}

export async function getWatchlist(): Promise<{ items: WatchItem[] }> {
  return apiGet("/api/v1/watchlist");
}

export async function saveWatchlist(items: WatchItem[]): Promise<{ items: WatchItem[]; unresolved_symbols: string[] }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/watchlist`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ items }),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(apiErrorMessage(response.status, text));
  }
  return response.json();
}

export async function getFeedStatus(): Promise<FeedStatus> {
  return apiGet("/api/v1/marketdata/feed-status");
}

export interface CandleResponse {
  symbol: string;
  exchange: string;
  interval: string;
  candles: { time: number; open: number; high: number; low: number; close: number; volume: number }[];
  tz_offset_secs: number;
  source: string;
  note: string;
}

export async function getCandles(symbol: string, exchange: string, interval: string): Promise<CandleResponse> {
  const qs = new URLSearchParams({ symbol, exchange, interval });
  return apiGet(`/api/v1/marketdata/candles?${qs}`);
}

export async function fyersStatus(): Promise<{ configured: boolean; logged_in: boolean; redirect_uri: string }> {
  return apiGet("/api/v1/brokers/fyers/status");
}

export async function fyersLoginUrl(): Promise<{ url: string; redirect_uri: string }> {
  return apiGet("/api/v1/brokers/fyers/login-url");
}


export type SentimentLabel = "bullish" | "bearish" | "neutral";

export interface NewsHeadline {
  id: string;
  title: string;
  source: string;
  url: string;
  published: string;
  /** -1 (bearish) to +1 (bullish), lexicon scored */
  score: number;
  label: SentimentLabel;
  symbols: string[];
}

export interface NewsMover {
  symbol: string;
  exchange: string | null;
  close: number | null;
  change_pct: number;
  direction: "up" | "down" | "flat";
  drivers: (NewsHeadline & { aligned: boolean })[];
  reason: string | null;
  note: string;
}

export interface SentimentRow {
  symbol: string;
  watched: boolean;
  mentions: number;
  score: number;
  label: SentimentLabel;
  bullish: number;
  bearish: number;
  neutral: number;
  latest: NewsHeadline | null;
}

export interface SentimentAlert {
  id: string;
  /** ISO time the flip was detected */
  t: string;
  symbol: string;
  from: SentimentLabel;
  to: SentimentLabel;
  score: number;
  mentions: number;
  headline: NewsHeadline | null;
}

export interface NewsPulse {
  mood: {
    value: number;
    label: SentimentLabel;
    window_hours: number;
    counts: Record<SentimentLabel, number>;
    headlines: number;
  };
  history: { t: string; v: number }[];
  tracker: SentimentRow[];
  movers: NewsMover[];
  alerts: SentimentAlert[];
  sources: Record<string, boolean>;
  updated_at: string | null;
  method: string;
}

export async function getNewsPulse(): Promise<NewsPulse> {
  return apiGet("/api/v1/news/pulse");
}

export async function getNewsHeadlines(limit = 80): Promise<{ headlines: NewsHeadline[] }> {
  return apiGet(`/api/v1/news/headlines?limit=${limit}`);
}

export interface SymbolNews {
  symbol: string;
  headlines: NewsHeadline[];
  tone: { score: number; label: SentimentLabel; mentions: number; bullish: number; bearish: number; neutral: number };
  /** the symbol's current stable tone, once it has enough headlines to have one */
  state: SentimentLabel | null;
  alerts: SentimentAlert[];
}

export async function getSymbolNews(symbol: string): Promise<SymbolNews> {
  return apiGet(`/api/v1/news/symbol?symbol=${encodeURIComponent(symbol)}`);
}


export type Severity = "low" | "medium" | "high";

export interface BehaviorCheck {
  severity: Severity;
  evidence: string;
  [metric: string]: unknown;
}

export interface JournalRoundTrip {
  symbol: string;
  direction: "long" | "short";
  entry_dt: string;
  exit_dt: string;
  qty: number;
  entry_price: number;
  exit_price: number;
  hold_days: number;
  pnl: number;
  pnl_pct: number;
  fees: number;
  category: "intraday" | "short_term" | "long_term";
}

export interface JournalProfile {
  total_trades: number;
  symbols: number;
  first_trade: string;
  last_trade: string;
  trades_per_week: number;
  closed_round_trips: number;
  open_positions: { symbol: string; direction: string; quantity: number; average_price: number; since: string }[];
  xirr: { value: number | null; note: string };
  note?: string;
  win_rate?: number;
  avg_win?: number;
  avg_loss?: number;
  profit_loss_ratio?: number | null;
  profit_factor?: number | null;
  expectancy?: number;
  total_pnl?: number;
  fees_paid?: number;
  max_drawdown?: number;
  avg_hold_days?: number;
  best_trip?: { symbol: string; direction: string; pnl: number; entry: string; exit: string };
  worst_trip?: { symbol: string; direction: string; pnl: number; entry: string; exit: string };
  by_category?: Record<string, { trips: number; pnl: number; win_rate: number }>;
  by_symbol?: { symbol: string; trips: number; pnl: number; win_rate: number }[];
  monthly_pnl?: { month: string; pnl: number }[];
  pnl_curve?: { t: string; v: number }[];
  entries_by_hour?: Record<string, number>;
  entries_by_weekday?: Record<string, number>;
}

export interface JournalAnalysis {
  file: { name: string; format: string; rows_used: number; rows_skipped: number; date_range: [string, string] };
  synthetic?: boolean;
  profile: JournalProfile;
  behavior: Record<"disposition_effect" | "overtrading" | "chasing_momentum" | "anchoring", BehaviorCheck>;
  findings: { key: string; title: string; severity: Severity; evidence: string }[];
  round_trips: JournalRoundTrip[];
  method: string;
}

async function parseApiError(response: Response): Promise<never> {
  const text = await response.text().catch(() => response.statusText);
  throw new Error(apiErrorMessage(response.status, text));
}

export async function analyzeJournal(file: File): Promise<JournalAnalysis> {
  const form = new FormData();
  form.append("file", file);
  // No Content-Type header: the browser sets the multipart boundary itself.
  const response = await fetch(`${API_BASE_URL}/api/v1/journal/analyze`, { method: "POST", headers: authHeaders(), body: form });
  if (!response.ok) return parseApiError(response);
  return response.json();
}

export async function analyzeSampleJournal(): Promise<JournalAnalysis> {
  return apiPost<JournalAnalysis>("/api/v1/journal/analyze-sample", {});
}


export interface SharpeAssessment {
  observations: number;
  periods_per_year: number;
  sharpe_per_period: number | null;
  sharpe_annualized: number | null;
  skew: number | null;
  kurtosis: number | null;
  annualized_return: number | null;
  max_drawdown: number | null;
  sortino_annualized: number | null;
  calmar: number | null;
  confidence_level: number;
  psr?: number | null;
  min_track_record?: number | null;
  n_trials?: number;
  trial_sharpe_std?: number | null;
  trial_std_assumed?: boolean;
  bar_per_period?: number | null;
  bar_annualized?: number | null;
  dsr?: number | null;
  verdict?: "likely_real" | "suggestive" | "indistinguishable";
  verdict_text?: string;
  error?: string;
}

export async function assessSharpe(values: number[], nTrials: number, periodsPerYear = 252): Promise<SharpeAssessment> {
  return apiPost<SharpeAssessment>("/api/v1/validation/sharpe", { values, kind: "equity", n_trials: nTrials, periods_per_year: periodsPerYear });
}


export interface CorrelationRegime {
  labels: string[];
  matrix: (number | null)[][];
  dates: string[];
  density: (number | null)[];
  smoothed: (number | null)[];
  fused: number[];
  episodes: { start: string; end: string | null }[];
  current: { state: "FUSED" | "NORMAL"; smoothed_density: number | null; average_correlation: number | null };
  most_correlated: { a: string; b: string; corr: number }[];
  least_correlated: { a: string; b: string; corr: number }[];
  unavailable: string[];
  params: { days: number; corr_window: number; edge_threshold: number; smooth_window: number; enter_threshold: number; exit_threshold: number };
}

export async function getCorrelationRegime(opts: { symbols?: string; days?: number; corrWindow?: number } = {}): Promise<CorrelationRegime> {
  const q = new URLSearchParams();
  if (opts.symbols) q.set("symbols", opts.symbols);
  if (opts.days) q.set("days", String(opts.days));
  if (opts.corrWindow) q.set("corr_window", String(opts.corrWindow));
  return apiGet(`/api/v1/analytics/correlation?${q.toString()}`);
}
