from datetime import datetime, UTC
from typing import List
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    source: str
    description: str
    date_added: datetime = Field(default_factory=lambda: datetime.now(UTC))
    supports_hypothesis: bool


class Hypothesis(BaseModel):
    id: str
    title: str
    description: str
    status: str = "proposed"  # proposed, testing, validated, rejected
    test_criteria: str
    evidence: List[Evidence] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def add_evidence(self, ev: Evidence):
        self.evidence.append(ev)
        self.updated_at = datetime.now(UTC)
