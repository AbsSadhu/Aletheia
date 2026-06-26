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
  insights: string[];
  confidence_score: number;
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
