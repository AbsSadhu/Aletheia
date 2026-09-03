"""Hypothesis-tracking endpoints.

GET   /hypotheses
POST  /hypotheses
GET   /hypotheses/{id}
PATCH /hypotheses/{id}/transition
POST  /hypotheses/{id}/link-backtest
POST  /hypotheses/{id}/evidence
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aletheia.core.config.settings import get_settings

router = APIRouter(prefix="/api/v1")


class ProposeHypothesisRequest(BaseModel):
    title: str
    description: str
    test_criteria: str


class TransitionRequest(BaseModel):
    new_status: str


class AddEvidenceRequest(BaseModel):
    source: str
    summary: str
    supports: bool


class LinkBacktestRequest(BaseModel):
    backtest_run_id: str


def _get_hypothesis_registry():
    settings = get_settings()
    from aletheia.extensions.hypotheses.registry import HypothesisRegistry

    return HypothesisRegistry(db_path=str(settings.data_dir / "hypotheses.db"))


@router.get("/hypotheses")
async def list_hypotheses(status: str | None = None) -> dict:
    reg = _get_hypothesis_registry()
    items = reg.list_all(status=status)
    return {"hypotheses": [h.model_dump(mode="json") for h in items]}


@router.post("/hypotheses", status_code=201)
async def propose_hypothesis(request: ProposeHypothesisRequest) -> dict:
    reg = _get_hypothesis_registry()
    hypo = reg.propose(
        title=request.title,
        description=request.description,
        test_criteria=request.test_criteria,
    )
    return hypo.model_dump(mode="json")


@router.get("/hypotheses/{hypo_id}")
async def get_hypothesis(hypo_id: str) -> dict:
    reg = _get_hypothesis_registry()
    hypo = reg.get(hypo_id)
    if hypo is None:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    return hypo.model_dump(mode="json")


@router.patch("/hypotheses/{hypo_id}/transition")
async def transition_hypothesis(hypo_id: str, request: TransitionRequest) -> dict:
    reg = _get_hypothesis_registry()
    try:
        hypo = reg.transition(hypo_id, request.new_status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return hypo.model_dump(mode="json")


@router.post("/hypotheses/{hypo_id}/link-backtest")
async def link_hypothesis_backtest(hypo_id: str, request: LinkBacktestRequest) -> dict:
    reg = _get_hypothesis_registry()
    try:
        hypo = reg.link_to_backtest(hypo_id, request.backtest_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return hypo.model_dump(mode="json")


@router.post("/hypotheses/{hypo_id}/evidence")
async def add_hypothesis_evidence(hypo_id: str, request: AddEvidenceRequest) -> dict:
    reg = _get_hypothesis_registry()
    try:
        hypo = reg.add_evidence(
            hypo_id=hypo_id,
            source=request.source,
            summary=request.summary,
            supports=request.supports,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return hypo.model_dump(mode="json")
