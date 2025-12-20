from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List

from advisory_connector import AdvisoryRequest, AdvisoryResponse
from pydantic import BaseModel, Field, validator


class AdvisoryRequestPayload(BaseModel):
    """Pydantic wrapper for inbound advisory requests."""

    goal: str = Field(..., description="High-level non-authoritative goal")
    context_slice: List[str]
    constraints: Dict[str, List[str]]
    forbidden_domains: List[str]
    desired_artifacts: List[str]
    phase: str
    redaction_profile: List[str]
    version: str = "1.0"

    @validator("goal", "phase")
    def _not_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("value cannot be empty")
        return value

    @validator("redaction_profile")
    def _redaction_profile_required(cls, profile: List[str]) -> List[str]:
        if not profile:
            raise ValueError("redaction_profile cannot be empty")
        return profile

    def to_dataclass(self) -> AdvisoryRequest:
        return AdvisoryRequest(
            goal=self.goal,
            context_slice=tuple(self.context_slice),
            constraints=self.constraints,
            forbidden_domains=tuple(self.forbidden_domains),
            desired_artifacts=tuple(self.desired_artifacts),
            phase=self.phase,
            redaction_profile=tuple(self.redaction_profile),
            version=self.version,
        )


class AdvisoryResponsePayload(BaseModel):
    proposed_steps: List[str]
    risk_notes: List[str]
    assumptions: List[str]
    confidence_estimate: float
    unknowns: List[str]
    diff_suggestions: List[str] | None = None
    version: str = "1.0"
    executable: bool = False

    @classmethod
    def from_dataclass(cls, response: AdvisoryResponse) -> "AdvisoryResponsePayload":
        data = asdict(response)
        # Ensure tuples remain deterministic lists for JSON responses
        return cls(**data)


class HandshakeResponse(BaseModel):
    server: str
    version: str
    phase: str
    advisory_only: bool
    endpoints: Dict[str, str]
    tools: List[Dict[str, object]]
