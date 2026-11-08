"""Backtest significance.

POST /validation/sharpe    how likely is it that an equity curve's Sharpe is real, not luck?
POST /validation/fdr       which of many tested ideas survive a false-discovery-rate correction?
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aletheia.core.validation.stats import ValidationInputError, assess, benjamini_hochberg

logger = logging.getLogger(__name__)


def _unprocessable(exc: ValueError) -> HTTPException:
    """Show our own input messages; keep anything else (a library error) out of the response."""
    if isinstance(exc, ValidationInputError):
        return HTTPException(status_code=422, detail=str(exc))
    logger.warning("Validation request failed: %s", exc)
    return HTTPException(status_code=422, detail="The input could not be processed.")


router = APIRouter(prefix="/api/v1")


class SharpeRequest(BaseModel):
    values: list[float] = Field(..., min_length=2, max_length=50_000)
    kind: Literal["equity", "returns"] = "equity"
    n_trials: int = Field(
        1,
        ge=1,
        le=100_000,
        description="How many strategies or parameter sets were tried to find this one",
    )
    trial_sharpe_std: float | None = Field(
        None, ge=0, description="Per-period spread of the trials' Sharpes, if known"
    )
    periods_per_year: int = Field(252, ge=1, le=100_000)
    confidence: float = Field(0.95, gt=0.5, lt=1)


class FdrRequest(BaseModel):
    p_values: list[float] = Field(..., min_length=1, max_length=100_000)
    fdr: float = Field(0.05, gt=0, lt=1)


@router.post("/validation/sharpe")
async def validate_sharpe(body: SharpeRequest) -> dict:
    try:
        return assess(
            body.values,
            body.kind,
            body.n_trials,
            body.trial_sharpe_std,
            body.periods_per_year,
            body.confidence,
        )
    except ValueError as exc:
        raise _unprocessable(exc) from exc


@router.post("/validation/fdr")
async def validate_fdr(body: FdrRequest) -> dict:
    try:
        r = benjamini_hochberg(body.p_values, body.fdr)
    except ValueError as exc:
        raise _unprocessable(exc) from exc
    return {
        "rejected": [bool(x) for x in r.rejected],
        "adjusted_p_values": [round(float(x), 6) for x in r.adjusted_p_values],
        "n_rejected": r.n_rejected,
        "threshold": r.threshold,
        "fdr": r.fdr,
    }
