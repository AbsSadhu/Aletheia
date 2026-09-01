from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def coerce_none_and_nan(cls, data: Any) -> Any:
    if isinstance(data, dict):
        import math

        for klass in cls.__mro__:
            for field_name, annotation in getattr(klass, "__annotations__", {}).items():
                if field_name not in data:
                    continue
                val = data[field_name]
                ann_str = str(annotation)

                # Check for strict float vs optional float
                is_strict_float = annotation is float or annotation == "float"

                if is_strict_float:
                    if val is None:
                        data[field_name] = 0.0
                    elif isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                        data[field_name] = 0.0
                elif isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    data[field_name] = 0.0

                # Check if it is a dictionary of floats
                if "dict[str, float]" in ann_str or "Dict[str, float]" in ann_str:
                    if isinstance(val, dict):
                        cleaned = {}
                        for k, v in val.items():
                            if v is None:
                                cleaned[k] = 0.0
                            elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                                cleaned[k] = 0.0
                            else:
                                cleaned[k] = v
                        data[field_name] = cleaned
    return data


class AnalystContract(BaseModel):
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        forbidden_keys = {
            "recommendations",
            "executive_summary",
            "final_decision",
            "portfolio_manager_overrides",
        }
        for key in forbidden_keys:
            if key in cls.__annotations__ or key in cls.__dict__:
                raise TypeError(
                    f"Analyst contract violation: class {cls.__name__} cannot define forbidden field '{key}'"
                )

    @model_validator(mode="before")
    @classmethod
    def validate_analyst_mandate(cls, data: Any) -> Any:
        if isinstance(data, dict):
            forbidden_keys = {
                "recommendations",
                "executive_summary",
                "final_decision",
                "portfolio_manager_overrides",
            }
            for key in forbidden_keys:
                if key in data:
                    raise ValueError(
                        f"Analyst contract violation: analyst role is forbidden from emitting final decisions/synthesis (field '{key}' found)"
                    )
            coerce_none_and_nan(cls, data)
        return data


class RiskConstraintContract(BaseModel):
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        forbidden_keys = {"quotes", "executive_summary", "recommendations"}
        for key in forbidden_keys:
            if key in cls.__annotations__ or key in cls.__dict__:
                raise TypeError(
                    f"RiskConstraint contract violation: class {cls.__name__} cannot define forbidden field '{key}'"
                )

    @model_validator(mode="before")
    @classmethod
    def validate_risk_mandate(cls, data: Any) -> Any:
        if isinstance(data, dict):
            forbidden_keys = {"quotes", "executive_summary", "recommendations"}
            for key in forbidden_keys:
                if key in data:
                    raise ValueError(
                        f"RiskConstraint contract violation: risk/constraint role is forbidden from emitting analyst details or final synthesis (field '{key}' found)"
                    )
            coerce_none_and_nan(cls, data)
        return data


class SynthesisContract(BaseModel):
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        forbidden_keys = {"quotes"}
        for key in forbidden_keys:
            if key in cls.__annotations__ or key in cls.__dict__:
                raise TypeError(
                    f"Synthesis contract violation: class {cls.__name__} cannot define forbidden field '{key}'"
                )

    @model_validator(mode="before")
    @classmethod
    def validate_synthesis_mandate(cls, data: Any) -> Any:
        if isinstance(data, dict):
            forbidden_keys = {"quotes"}
            for key in forbidden_keys:
                if key in data:
                    raise ValueError(
                        f"Synthesis contract violation: synthesis role is forbidden from emitting analyst details (field '{key}' found)"
                    )
            coerce_none_and_nan(cls, data)
        return data


class AgentName(str, Enum):
    COLLECTOR = "collector"
    ORACLE = "oracle"
    SENTINEL = "sentinel"
    SAGE = "sage"
    SCRIBE = "scribe"
    DEBATE = "debate"
    PORTFOLIO_MANAGER = "portfolio_manager"
    SENTIMENT = "sentiment"
    FUNDAMENTAL = "fundamental"
    OPTIONS_FLOW = "options_flow"
    CRITIC = "critic"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PARTIAL = "partial"
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
    symbol: str = Field(..., min_length=1, max_length=30, pattern=r"^[A-Za-z0-9/.:-]+$")
    quantity: float = Field(..., gt=0, le=1e9)
    average_price: float = Field(..., gt=0, le=1e7)
    asset_type: AssetType = AssetType.EQUITY
    exchange: str = "NSE"
    tax_profile: TaxProfile = TaxProfile.EQUITY
    sector: str = "Technology"


class Portfolio(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9 _-]+$")
    base_currency: str = "INR"
    holdings: list[Holding] = Field(..., max_length=100)


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
            AgentName.SENTIMENT,
            AgentName.FUNDAMENTAL,
            AgentName.OPTIONS_FLOW,
            AgentName.CRITIC,
        ]
    )


class RunSummary(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    status: RunStatus = RunStatus.PENDING
    prompt: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error_message: str | None = None
    agent_statuses: dict[str, str] = Field(default_factory=dict)


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


class CollectorOutput(AnalystContract):
    symbol: str
    provider_used: str
    quotes: list[MarketQuote]
    warnings: list[str] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 1.0


class MultiTimeframeSignal(BaseModel):
    timeframe: str  # "1D" | "1W" | "1M"
    signal: str
    confidence: float = 0.0
    indicators: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_fields(cls, data: Any) -> Any:
        return coerce_none_and_nan(cls, data)


class OracleOutput(AnalystContract):
    symbol: str
    signal: str
    confidence: float = 0.0
    rationale: list[str] = Field(default_factory=list)
    fair_value_gap_pct: float = 0.0
    momentum_pct: float = 0.0
    multi_timeframe_signals: list[MultiTimeframeSignal] = Field(default_factory=list)
    factor_exposures: dict[str, float] | None = (
        None  # alpha, beta, smb_loading, hml_loading, r_squared
    )
    timeframe_agreement: str = "UNKNOWN"  # ALL_AGREE | MAJORITY_AGREE | SPLIT | NO_AGREEMENT


class SentinelOutput(AnalystContract):
    portfolio_var_95: float = 0.0
    concentration_risk: float = 0.0
    max_single_position_pct: float = 0.0
    market_regime: str = "unknown"
    confidence: float = 0.0
    alerts: list[str] = Field(default_factory=list)
    regime_detail: str = "unknown"  # e.g. "low_vol_bull", "crash", "high_vol"
    natural_language_brief: str = ""


class SentimentOutput(AnalystContract):
    symbol: str
    sentiment_score: float  # -1.0 to 1.0
    headline_count: int = 0
    top_headlines: list[str] = Field(default_factory=list)
    source_breakdown: dict[str, int] = Field(default_factory=dict)
    verdict: str = (
        "NEUTRAL"  # STRONGLY_POSITIVE | POSITIVE | NEUTRAL | NEGATIVE | STRONGLY_NEGATIVE
    )
    confidence: float = 0.5


class FundamentalOutput(AnalystContract):
    symbol: str
    pe_ratio: float | None = None
    eps_growth_pct: float | None = None
    revenue_growth_pct: float | None = None
    debt_to_equity: float | None = None
    promoter_holding_pct: float | None = None
    sector_pe: float | None = None
    valuation_verdict: str = "FAIR"  # OVERVALUED | FAIR | UNDERVALUED
    valuation_commentary: str = ""
    confidence: float = 0.5


class OptionsFlowOutput(AnalystContract):
    symbol: str
    put_call_ratio: float = 1.0
    iv_rank: float = 50.0  # 0-100
    max_pain_level: float | None = None
    oi_concentration: str = "NEUTRAL"  # BULLISH_OI | BEARISH_OI | NEUTRAL
    signal_hint: str = "NEUTRAL"
    confidence: float = 0.5


class TaxSummary(BaseModel):
    tax_profile: TaxProfile
    pre_tax_profit: float
    tax_drag_pct: float
    estimated_tax_amount: float
    post_tax_profit: float

    @model_validator(mode="before")
    @classmethod
    def _coerce_fields(cls, data: Any) -> Any:
        return coerce_none_and_nan(cls, data)


class SageScenario(BaseModel):
    scenario_name: str
    projected_return_pct: float
    projected_post_tax_return_pct: float
    projected_sharpe: float
    tax_summary: TaxSummary

    @model_validator(mode="before")
    @classmethod
    def _coerce_fields(cls, data: Any) -> Any:
        return coerce_none_and_nan(cls, data)


class SageOutput(RiskConstraintContract):
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

    @model_validator(mode="before")
    @classmethod
    def _coerce_fields(cls, data: Any) -> Any:
        return coerce_none_and_nan(cls, data)


class CriticVerdict(BaseModel):
    passed: bool
    score: float  # 0.0-1.0
    notes: list[str] = Field(default_factory=list)
    iteration: int = 1

    @model_validator(mode="before")
    @classmethod
    def _coerce_fields(cls, data: Any) -> Any:
        return coerce_none_and_nan(cls, data)


class ConfidenceRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    symbol: str
    agent: str
    predicted_signal: str
    predicted_confidence: float
    actual_return_7d: float | None = None
    actual_return_30d: float | None = None
    brier_score: float | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="before")
    @classmethod
    def _coerce_fields(cls, data: Any) -> Any:
        return coerce_none_and_nan(cls, data)


class SEBIComplianceLog(BaseModel):
    log_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    symbol: str
    action: str
    confidence: float
    reasoning_hash: str  # SHA-256 of executive_summary
    disclaimer: str
    logged_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Hash-chain fields (tamper-evidence on top of the DB-level append-only
    # triggers): prev_hash links to the previous row's entry_hash, forming a
    # chain an editor with raw file access — bypassing the app and its SQL
    # triggers — cannot alter without breaking. Populated by
    # SQLiteStore.log_compliance(); "" here is only the pre-persist default.
    prev_hash: str = ""
    entry_hash: str = ""

    @model_validator(mode="before")
    @classmethod
    def _coerce_fields(cls, data: Any) -> Any:
        return coerce_none_and_nan(cls, data)


class ScribeOutput(SynthesisContract):
    executive_summary: str
    overall_confidence: float
    agreement_level: str
    recommendations: list[Recommendation] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    critic_passed: bool = True
    critic_notes: list[str] = Field(default_factory=list)
    sebi_disclaimer: str = (
        "This report is generated by an AI system for informational purposes only. "
        "It does not constitute financial advice. Past performance is not indicative of future results. "
        "Consult a SEBI-registered investment advisor before making any investment decisions."
    )


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
    sentiment_outputs: list[SentimentOutput] = Field(default_factory=list)
    fundamental_outputs: list[FundamentalOutput] = Field(default_factory=list)
    options_flow_outputs: list[OptionsFlowOutput] = Field(default_factory=list)
    critic_verdict: CriticVerdict | None = None
    macro_context_text: str = ""
    insights: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    traces: list[dict[str, Any]] = Field(default_factory=list)
    agent_statuses: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_fields(cls, data: Any) -> Any:
        return coerce_none_and_nan(cls, data)


class HealthResponse(BaseModel):
    service: str = "ALETHEIA"
    status: str = "ok"
    version: str = "0.1.0"
    sqlite_path: str
    duckdb_path: str
