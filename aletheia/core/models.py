from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentName(str, Enum):
    COLLECTOR = "collector"
    ORACLE = "oracle"
    SENTINEL = "sentinel"
    SAGE = "sage"
    SCRIBE = "scribe"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AssetType(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    FUTURE = "future"
    CRYPTO = "crypto"
    CASH = "cash"
    UNKNOWN = "unknown"


class TaxProfile(str, Enum):
    EQUITY = "equity"
    FNO = "fno"
    CRYPTO = "crypto"
    MUTUAL_FUND = "mutual_fund"


class DesktopSettings(BaseModel):
    backend_url: str = "http://127.0.0.1:8899"
    offline_mode: bool = True
    ollama_endpoint: str = "http://127.0.0.1:11434"
    export_permissions: list[str] = Field(default_factory=lambda: ["reports", "csv", "json"])


class SecureCredentialRef(BaseModel):
    key: str
    provider: str
    scope: str = "local_machine"


class DesktopRunBridge(BaseModel):
    run_id: str
    status: RunStatus
    websocket_url: str


class Holding(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    asset_type: AssetType = AssetType.EQUITY
    exchange: str = "NSE"
    tax_profile: TaxProfile = TaxProfile.EQUITY


class Portfolio(BaseModel):
    name: str
    base_currency: str = "INR"
    holdings: list[Holding]


class RunRequest(BaseModel):
    prompt: str
    portfolio: Portfolio | None = None
    selected_agents: list[AgentName] = Field(
        default_factory=lambda: [
            AgentName.COLLECTOR,
            AgentName.ORACLE,
            AgentName.SENTINEL,
            AgentName.SAGE,
            AgentName.SCRIBE,
        ]
    )


class RunSummary(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    status: RunStatus = RunStatus.PENDING
    prompt: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error_message: str | None = None


class MarketQuote(BaseModel):
    symbol: str
    exchange: str
    currency: str = "INR"
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider: str


class CollectorOutput(BaseModel):
    symbol: str
    provider_used: str
    quotes: list[MarketQuote]
    warnings: list[str] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class OracleOutput(BaseModel):
    symbol: str
    signal: str
    confidence: float
    rationale: list[str] = Field(default_factory=list)
    fair_value_gap_pct: float = 0.0
    momentum_pct: float = 0.0


class SentinelOutput(BaseModel):
    portfolio_var_95: float
    concentration_risk: float
    max_single_position_pct: float
    market_regime: str
    confidence: float
    alerts: list[str] = Field(default_factory=list)


class TaxSummary(BaseModel):
    tax_profile: TaxProfile
    pre_tax_profit: float
    tax_drag_pct: float
    estimated_tax_amount: float
    post_tax_profit: float


class SageScenario(BaseModel):
    scenario_name: str
    projected_return_pct: float
    projected_post_tax_return_pct: float
    projected_sharpe: float
    tax_summary: TaxSummary


class SageOutput(BaseModel):
    symbol: str
    scenario: SageScenario
    confidence: float
    rationale: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    symbol: str
    action: str
    confidence: float
    explanation: str
    stop_loss: float | None = None
    target_price: float | None = None


class ScribeOutput(BaseModel):
    executive_summary: str
    overall_confidence: float
    agreement_level: str
    recommendations: list[Recommendation] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AgentEvent(BaseModel):
    run_id: str
    agent: AgentName
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] | None = None


class RunResult(BaseModel):
    summary: RunSummary
    collector_output: list[CollectorOutput] = Field(default_factory=list)
    oracle_output: list[OracleOutput] = Field(default_factory=list)
    sentinel_output: SentinelOutput | None = None
    sage_output: list[SageOutput] = Field(default_factory=list)
    scribe_output: ScribeOutput | None = None
    insights: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0


class HealthResponse(BaseModel):
    service: str = "ALETHEIA"
    status: str = "ok"
    version: str = "0.1.0"
    sqlite_path: str
    duckdb_path: str
