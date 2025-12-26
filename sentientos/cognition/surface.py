"""Isolated cognitive surface for proposal-only inference."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Sequence
import uuid


PreferenceScope = Literal["session", "install", "revoked-on-restart"]


@dataclass(frozen=True)
class CognitiveProposal:
    proposal_id: str
    proposed_action: str
    confidence: float
    rationale: str
    observations: Sequence[str]
    authority_impact: str
    expires_at: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposed_action": self.proposed_action,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "observations": list(self.observations),
            "authority_impact": self.authority_impact,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class IntentBundleDraft:
    proposal_id: str
    summary: str
    notes: str


@dataclass(frozen=True)
class PreferenceInference:
    key: str
    value: str
    scope: PreferenceScope
    inferred_at: str
    source: str


class CognitiveViolation(RuntimeError):
    """Raised when a cognitive proposal violates safety constraints."""


class CognitiveCache:
    """Purgeable cache for cognitive state."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def write_preferences(self, preferences: Iterable[PreferenceInference]) -> None:
        payload = [pref.__dict__ for pref in preferences]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_preferences(self) -> list[PreferenceInference]:
        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return [
            PreferenceInference(
                key=item["key"],
                value=item["value"],
                scope=item["scope"],
                inferred_at=item["inferred_at"],
                source=item.get("source", "cache"),
            )
            for item in raw
        ]

    def purge(self) -> None:
        if self._path.exists():
            self._path.unlink()


class CognitiveSurface:
    """Cognitive layer restricted to proposal-only output and purgeable memory."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        cache: CognitiveCache | None = None,
        default_expiration: timedelta = timedelta(minutes=30),
    ) -> None:
        self.enabled = enabled
        self._cache = cache
        self._default_expiration = default_expiration
        self._preferences: list[PreferenceInference] = []
        self._preference_usage: list[str] = []

    def infer_preferences(
        self,
        *,
        observations: Sequence[str],
        scope: PreferenceScope,
        source: str,
    ) -> list[PreferenceInference]:
        inferred: list[PreferenceInference] = []
        timestamp = datetime.now(timezone.utc).isoformat()
        for obs in observations:
            key = f"preference::{len(self._preferences) + len(inferred) + 1}"
            inferred.append(
                PreferenceInference(
                    key=key,
                    value=obs,
                    scope=scope,
                    inferred_at=timestamp,
                    source=source,
                )
            )
        self._preferences.extend(inferred)
        return inferred

    def mark_preference_used(self, key: str) -> None:
        self._preference_usage.append(key)

    def preference_usage_summary(self) -> list[str]:
        return [f"used inferred preference {key}" for key in self._preference_usage]

    def persist_preferences(self) -> None:
        if self._cache is None:
            return
        persistable = [pref for pref in self._preferences if pref.scope == "install"]
        self._cache.write_preferences(persistable)

    def load_cached_preferences(self) -> list[PreferenceInference]:
        if self._cache is None:
            return []
        loaded = self._cache.load_preferences()
        self._preferences = list(loaded)
        return loaded

    def revoke_preferences(self) -> None:
        self._preferences = []
        self._preference_usage = []
        if self._cache is not None:
            self._cache.purge()

    def build_proposal(
        self,
        *,
        proposed_action: str,
        confidence: float,
        rationale: str,
        observations: Sequence[str],
        authority_impact: str,
        expires_at: str | None = None,
    ) -> CognitiveProposal:
        if not self.enabled:
            raise CognitiveViolation("Cognition is disabled")
        proposal = CognitiveProposal(
            proposal_id=str(uuid.uuid4()),
            proposed_action=proposed_action,
            confidence=confidence,
            rationale=rationale,
            observations=observations,
            authority_impact=authority_impact,
            expires_at=expires_at or self._default_expiration_at(),
        )
        self._ensure_proposal_safe(proposal)
        return proposal

    def proposals_from_state(self, state: Mapping[str, Any]) -> list[CognitiveProposal]:
        if not self.enabled:
            return []
        requests = state.get("cognitive_requests", [])
        proposals: list[CognitiveProposal] = []
        for req in requests:
            if not isinstance(req, Mapping):
                continue
            proposal = self.build_proposal(
                proposed_action=str(req.get("proposed_action", "")),
                confidence=float(req.get("confidence", 0.5)),
                rationale=str(req.get("rationale", "")),
                observations=[str(item) for item in req.get("observations", [])],
                authority_impact=str(req.get("authority_impact", "none")),
                expires_at=req.get("expires_at"),
            )
            proposals.append(proposal)
        return proposals

    def handoff_to_operator(self, proposal: CognitiveProposal, *, notes: str = "") -> IntentBundleDraft:
        summary = f"Proposal {proposal.proposal_id}: {proposal.proposed_action}"
        return IntentBundleDraft(proposal_id=proposal.proposal_id, summary=summary, notes=notes)

    def _default_expiration_at(self) -> str:
        expires = datetime.now(timezone.utc) + self._default_expiration
        return expires.isoformat()

    def _ensure_proposal_safe(self, proposal: CognitiveProposal) -> None:
        lowered = proposal.proposed_action.lower()
        forbidden_tokens = (
            "execute_task",
            "approval_request",
            "apply_patch",
            "task_executor",
            "intent_bundle",
            "authorization",
            "admission_token",
            "epr",
            "closure",
        )
        if any(token in lowered for token in forbidden_tokens):
            raise CognitiveViolation("Proposal contains execution or authority language")
        if lowered.strip().startswith("run ") or lowered.strip().startswith("python "):
            raise CognitiveViolation("Proposal looks executable")


__all__ = [
    "CognitiveSurface",
    "CognitiveProposal",
    "CognitiveViolation",
    "CognitiveCache",
    "PreferenceInference",
    "IntentBundleDraft",
]
