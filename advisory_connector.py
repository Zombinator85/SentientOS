from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Mapping, Sequence
import json
import time

ADVISORY_PHASE = "ADVISORY_WINDOW"


@dataclass(frozen=True)
class AdvisoryRequest:
    goal: str
    context_slice: tuple[str, ...]
    constraints: Mapping[str, Sequence[str]]
    forbidden_domains: tuple[str, ...]
    desired_artifacts: tuple[str, ...]
    phase: str
    redaction_profile: tuple[str, ...]
    version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(self, "context_slice", tuple(self.context_slice))
        object.__setattr__(self, "forbidden_domains", tuple(self.forbidden_domains))
        object.__setattr__(self, "desired_artifacts", tuple(self.desired_artifacts))
        object.__setattr__(self, "redaction_profile", tuple(self.redaction_profile))
        normalized_constraints = {
            "must": tuple(self.constraints.get("must", ())),
            "must_not": tuple(self.constraints.get("must_not", ())),
        }
        object.__setattr__(self, "constraints", normalized_constraints)

    def validate(self) -> None:
        errors: list[str] = []
        if not self.goal:
            errors.append("goal is required")
        if self.phase != ADVISORY_PHASE:
            errors.append("phase must be ADVISORY_WINDOW")
        if not isinstance(self.context_slice, tuple):
            errors.append("context_slice must be a tuple")
        if errors:
            raise ValueError("; ".join(errors))

    def redact(self) -> tuple[AdvisoryRequest, tuple[str, ...]]:
        redacted_entries: list[str] = []
        applied: list[str] = []
        for entry in self.context_slice:
            if any(token.lower() in entry.lower() for token in self.redaction_profile):
                redacted_entries.append("[REDACTED]")
                applied.extend(
                    token
                    for token in self.redaction_profile
                    if token.lower() in entry.lower() and token not in applied
                )
            else:
                redacted_entries.append(entry)
        redacted = replace(self, context_slice=tuple(redacted_entries))
        return redacted, tuple(applied)


@dataclass(frozen=True)
class AdvisoryResponse:
    proposed_steps: tuple[str, ...]
    risk_notes: tuple[str, ...]
    assumptions: tuple[str, ...]
    confidence_estimate: float
    unknowns: tuple[str, ...]
    diff_suggestions: tuple[str, ...] | None = None
    version: str = "1.0"
    executable: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposed_steps", tuple(self.proposed_steps))
        object.__setattr__(self, "risk_notes", tuple(self.risk_notes))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "unknowns", tuple(self.unknowns))
        if self.diff_suggestions is not None:
            object.__setattr__(self, "diff_suggestions", tuple(self.diff_suggestions))

    def validate(self) -> None:
        if any(callable(step) for step in self.diff_suggestions or ()):  # type: ignore[arg-type]
            raise ValueError("diff suggestions must be inert text, not callables")
        if self.confidence_estimate < 0 or self.confidence_estimate > 1:
            raise ValueError("confidence_estimate must be between 0 and 1")
        if self.executable:
            raise ValueError("advisory responses cannot be executable")


@dataclass(frozen=True)
class AdvisoryDecision:
    status: str
    reason: str
    deltas: tuple[str, ...] = ()
    downstream_effects: tuple[str, ...] = ()


class AdvisoryAuditTrail:
    """Immutable JSONL-backed audit trail for advisory connector events."""

    def __init__(self, path: Path | None = None):
        self.path = path or Path("audit_log/advisory_connector.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[dict[str, object]] = []

    def record_interaction(
        self,
        *,
        request: AdvisoryRequest,
        response: AdvisoryResponse | None,
        redactions: tuple[str, ...],
        decision: AdvisoryDecision,
        downstream_effects: tuple[str, ...] = (),
        stage: str = "gate",
    ) -> None:
        entry = {
            "stage": stage,
            "request": json.loads(json.dumps(request.__dict__)),
            "response": json.loads(json.dumps(response.__dict__)) if response else None,
            "redactions": list(redactions),
            "decision": decision.__dict__,
            "downstream_effects": list(downstream_effects),
            "timestamp": time.time(),
        }
        self._records.append(entry)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def records(self) -> list[dict[str, object]]:
        return [json.loads(json.dumps(entry)) for entry in self._records]


class AdvisoryConnectorGate:
    """Gate external advisory connectors with strict scope and tone controls."""

    def __init__(
        self,
        *,
        max_scope_size: int = 20,
        timeout_seconds: float = 2.0,
        max_retries: int = 0,
        audit_trail: AdvisoryAuditTrail | None = None,
    ) -> None:
        self.max_scope_size = max_scope_size
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.audit_trail = audit_trail or AdvisoryAuditTrail()

    def send(
        self, request: AdvisoryRequest, responder: Callable[[AdvisoryRequest], AdvisoryResponse]
    ) -> tuple[AdvisoryDecision, AdvisoryResponse | None]:
        redacted_request, applied_redactions = request.redact()
        try:
            redacted_request.validate()
        except ValueError as exc:  # phase enforcement and schema validation
            decision = AdvisoryDecision(status="rejected", reason=str(exc))
            self.audit_trail.record_interaction(
                request=redacted_request,
                response=None,
                redactions=applied_redactions,
                decision=decision,
            )
            return decision, None

        if len(redacted_request.context_slice) > self.max_scope_size:
            decision = AdvisoryDecision(status="rejected", reason="context scope exceeds maximum")
            self.audit_trail.record_interaction(
                request=redacted_request,
                response=None,
                redactions=applied_redactions,
                decision=decision,
            )
            return decision, None

        response: AdvisoryResponse | None = None
        attempts = 0
        errors: list[str] = []
        while attempts <= self.max_retries and response is None:
            attempts += 1
            start = time.monotonic()
            try:
                response = responder(redacted_request)
            except Exception as exc:  # pragma: no cover - defensive logging
                errors.append(str(exc))
                response = None
            if time.monotonic() - start > self.timeout_seconds:
                errors.append("timeout")
                response = None

        if response is None:
            reason = "; ".join(errors) if errors else "no response"
            decision = AdvisoryDecision(status="rejected", reason=reason)
            self.audit_trail.record_interaction(
                request=redacted_request,
                response=None,
                redactions=applied_redactions,
                decision=decision,
            )
            return decision, None

        try:
            response.validate()
        except ValueError as exc:
            decision = AdvisoryDecision(status="rejected", reason=str(exc))
            self.audit_trail.record_interaction(
                request=redacted_request,
                response=response,
                redactions=applied_redactions,
                decision=decision,
            )
            return decision, None

        rejection_reasons = self._rejection_reasons(response, redacted_request)
        if rejection_reasons:
            decision = AdvisoryDecision(status="rejected", reason="; ".join(rejection_reasons))
            self.audit_trail.record_interaction(
                request=redacted_request,
                response=response,
                redactions=applied_redactions,
                decision=decision,
            )
            return decision, None

        decision = AdvisoryDecision(status="pending", reason="awaiting operator review")
        self.audit_trail.record_interaction(
            request=redacted_request,
            response=response,
            redactions=applied_redactions,
            decision=decision,
        )
        return decision, response

    def _rejection_reasons(
        self, response: AdvisoryResponse, request: AdvisoryRequest
    ) -> tuple[str, ...]:
        text = self._flatten_response_text(response)
        reasons: list[str] = []
        if self._contains_authority_language(text):
            reasons.append("prescriptive authority language detected")
        if self._imports_policy(text):
            reasons.append("external policy import attempt detected")
        if self._moral_framing(text):
            reasons.append("moral framing not permitted")
        if self._scope_creep(text, request):
            reasons.append("scope creep detected")
        return tuple(reasons)

    def _flatten_response_text(self, response: AdvisoryResponse) -> str:
        parts: list[str] = []
        parts.extend(response.proposed_steps)
        parts.extend(response.risk_notes)
        parts.extend(response.assumptions)
        parts.extend(response.unknowns)
        if response.diff_suggestions:
            parts.extend(response.diff_suggestions)
        return "\n".join(parts).lower()

    def _contains_authority_language(self, text: str) -> bool:
        triggers = ("must", "mandate", "authorized", "will comply", "do not question")
        return any(trigger in text for trigger in triggers)

    def _imports_policy(self, text: str) -> bool:
        triggers = ("apply your guardrails", "import policy", "adopt my rules", "external governance")
        return any(trigger in text for trigger in triggers)

    def _moral_framing(self, text: str) -> bool:
        return any(term in text for term in ("moral", "ethical duty", "virtue"))

    def _scope_creep(self, text: str, request: AdvisoryRequest) -> bool:
        if any(domain.lower() in text for domain in request.forbidden_domains):
            return True
        scope_flags = ("entire codebase", "whole system", "all modules")
        return any(flag in text for flag in scope_flags)


class AdvisoryAcceptanceWorkflow:
    """Ensure advice is explicitly accepted, partially accepted, or rejected."""

    def __init__(self, audit_trail: AdvisoryAuditTrail):
        self.audit_trail = audit_trail

    def accept(
        self,
        request: AdvisoryRequest,
        response: AdvisoryResponse,
        *,
        reason: str,
        downstream_effects: Sequence[str] = (),
    ) -> AdvisoryDecision:
        decision = AdvisoryDecision(
            status="accepted",
            reason=reason,
            downstream_effects=tuple(downstream_effects),
        )
        self.audit_trail.record_interaction(
            request=request,
            response=response,
            redactions=(),
            decision=decision,
            downstream_effects=tuple(downstream_effects),
            stage="acceptance",
        )
        return decision

    def partial_accept(
        self,
        request: AdvisoryRequest,
        response: AdvisoryResponse,
        *,
        deltas: Sequence[str],
        reason: str,
    ) -> AdvisoryDecision:
        decision = AdvisoryDecision(
            status="partial", reason=reason, deltas=tuple(deltas)
        )
        self.audit_trail.record_interaction(
            request=request,
            response=response,
            redactions=(),
            decision=decision,
            downstream_effects=tuple(deltas),
            stage="acceptance",
        )
        return decision

    def reject(
        self,
        request: AdvisoryRequest,
        response: AdvisoryResponse | None,
        *,
        cause: str,
    ) -> AdvisoryDecision:
        decision = AdvisoryDecision(status="rejected", reason=cause)
        self.audit_trail.record_interaction(
            request=request,
            response=response,
            redactions=(),
            decision=decision,
            stage="acceptance",
        )
        return decision
