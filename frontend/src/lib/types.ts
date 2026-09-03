/* Shared TypeScript types mirroring backend Pydantic models */

export interface HealthData {
  service: string;
  status: string;
  version: string;
  sqlite_path: string;
  duckdb_path: string;
}

export interface RunSummary {
  run_id: string;
  status: "pending" | "running" | "completed" | "failed";
  prompt: string;
  created_at: string;
  updated_at: string;
  error_message: string | null;
}

export interface MarketQuote {
  symbol: string;
  exchange: string;
  currency: string;
  close: number;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  as_of: string;
  provider: string;
}

export interface CollectorOutput {
  symbol: string;
  provider_used: string;
  quotes: MarketQuote[];
  warnings: string[];
  provenance: Record<string, string>[];
}

export interface OracleOutput {
  symbol: string;
  signal: "BUY" | "HOLD" | "REDUCE";
  confidence: number;
  rationale: string[];
  fair_value_gap_pct: number;
  momentum_pct: number;
}

export interface SentinelOutput {
  portfolio_var_95: number;
  concentration_risk: number;
  max_single_position_pct: number;
  market_regime: string;
  confidence: number;
  alerts: string[];
}

export interface TaxSummary {
  tax_profile: string;
  pre_tax_profit: number;
  tax_drag_pct: number;
  estimated_tax_amount: number;
  post_tax_profit: number;
}

export interface SageScenario {
  scenario_name: string;
  projected_return_pct: number;
  projected_post_tax_return_pct: number;
  projected_sharpe: number;
  tax_summary: TaxSummary;
}

export interface SageOutput {
  symbol: string;
  scenario: SageScenario;
  confidence: number;
  rationale: string[];
}

export interface Recommendation {
  symbol: string;
  action: string;
  confidence: number;
  explanation: string;
  stop_loss: number | null;
  target_price: number | null;
}

export interface ScribeOutput {
  executive_summary: string;
  overall_confidence: number;
  agreement_level: string;
  recommendations: Recommendation[];
  notes: string[];
}

export interface SentimentOutput {
  symbol: string;
  sentiment_score: number; // -1.0 to 1.0
  headline_count: number;
  top_headlines: string[];
  source_breakdown: Record<string, number>;
  verdict: "STRONGLY_POSITIVE" | "POSITIVE" | "NEUTRAL" | "NEGATIVE" | "STRONGLY_NEGATIVE";
  confidence: number;
}

export interface FundamentalOutput {
  symbol: string;
  pe_ratio: number | null;
  eps_growth_pct: number | null;
  revenue_growth_pct: number | null;
  debt_to_equity: number | null;
  promoter_holding_pct: number | null;
  sector_pe: number | null;
  valuation_verdict: "OVERVALUED" | "FAIR" | "UNDERVALUED";
  valuation_commentary: string;
  confidence: number;
}

export interface OptionsFlowOutput {
  symbol: string;
  put_call_ratio: number;
  iv_rank: number; // 0-100
  max_pain_level: number | null;
  oi_concentration: "BULLISH_OI" | "BEARISH_OI" | "NEUTRAL";
  signal_hint: string;
  confidence: number;
}

export interface AgentEvent {
  run_id: string;
  agent: string;
  message: string;
  timestamp: string;
  payload: Record<string, unknown> | null;
}

export interface RunResult {
  summary: RunSummary;
  collector_output: CollectorOutput[];
  oracle_output: OracleOutput[];
  sentinel_output: SentinelOutput | null;
  sage_output: SageOutput[];
  scribe_output: ScribeOutput | null;
  sentiment_outputs: SentimentOutput[];
  fundamental_outputs: FundamentalOutput[];
  options_flow_outputs: OptionsFlowOutput[];
  insights: string[];
  confidence_score: number;
}

export interface BacktestOrder {
  id: string;
  symbol: string;
  order_type: string;
  action: string;
  quantity: number;
  price: number | null;
  status: string;
  created_at: string;
  filled_at: string | null;
  filled_price: number | null;
}

export interface BacktestEquityPoint {
  step: number;
  value: number;
}

export interface BacktestResult {
  strategy_name: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_capital: number;
  total_return: number;
  metrics: {
    sharpe_ratio: number;
    max_drawdown: number;
    win_rate: number;
    profit_factor: number;
    total_trades: number;
  };
  orders: BacktestOrder[];
  equity_curve: BacktestEquityPoint[];
}

export interface Holding {
  symbol: string;
  quantity: number;
  average_price: number;
  asset_type: "equity" | "etf" | "future" | "crypto" | "cash" | "unknown";
  exchange: string;
  tax_profile: "equity" | "fno" | "crypto" | "mutual_fund";
}

export interface PortfolioData {
  name: string;
  base_currency: string;
  holdings: Holding[];
}
