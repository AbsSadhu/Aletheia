from pydantic import BaseModel, Field
from typing import Optional


class OracleLLMOutput(BaseModel):
    signal: str = Field(..., description="BUY, HOLD, or REDUCE")
    confidence: float = Field(..., description="Confidence score between 0 and 1")
    rationale: str = Field(..., description="Explanation of the signal")


class ScribeLLMOutput(BaseModel):
    executive_summary: str = Field(..., description="Overall summary")
    synthesized_recommendation: str = Field(..., description="Actionable advice")
    market_regime: str = Field(..., description="Market regime string")
    stop_loss_suggested: bool = Field(False, description="Whether to implement stop loss")
    target_allocation_shift: Optional[str] = Field(
        None, description="Suggested shift in allocation"
    )
