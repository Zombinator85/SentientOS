from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import sha256
from pathlib import Path
from typing import Callable, Mapping, Sequence
import json
import time

ADVISORY_PHASE = "ADVISORY_WINDOW"
ALLOWED_ARTIFACTS = ("plan", "diff", "test ideas")


def _deterministic_dumps(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


def _hash_payload(payload: object) -> str:
    return sha256(_deterministic_dumps(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AdvisoryRequest:
    goal: str
    constraints: Mapping[str, Sequence[str]]
    files_in_scope: tuple[str, ...]
    forbidden_changes: tuple[str, ...]
    desired_artifacts: tuple[str, ...]
    context_redactions: tuple[str, ...]
    system_phase: str
    minimal_synopsis: str = ""
    phase_required: str = ADVISORY_PHASE
    version: str = "2.0"

    def __post_init__(self) -> None:
        object.__setattr__(self, "files_in_scope", tuple(self.files_in_scope))
        object.__setattr__(self, "forbidden_changes", tuple(self.forbidden_changes))
        normalized_artifacts = tuple(item.lower() for item in self.desired_artifacts)
        object.__setattr__(self, "desired_artifacts", normalized_artifacts)
        normalized_redactions = tuple(token.lower() for token in self.context_redactions)
        object.__setattr__(self, "context_redactions", normalized_redactions)
        normalized_constraints = {
            "must": tuple(self.constraints.get("must", ())),
            "must_not": tuple(self.constraints.get("must_not", ())),
        }
        object.__setattr__(self, "constraints", normalized_constraints)

    def validate(self) -> None:
        errors: list[str] = []
        if not self.goal:
            errors.append("goal is required")
        if self.system_phase != self.phase_required:
            errors.append("phase must be ADVISORY_WINDOW")
        if not isinstance(self.files_in_scope, tuple):
            errors.append("files_in_scope must be a tuple")
        extra_artifacts = [item for item in self.desired_artifacts if item not in ALLOWED_ARTIFACTS]
        if extra_artifacts:
            errors.append(f"unsupported artifacts requested: {', '.join(sorted(extra_artifacts))}")
        if errors:
            raise ValueError("; ".join(errors))

    def redact(self) -> tuple[AdvisoryRequest, tuple[str, ...]]:
        applied: list[str] = []
        redaction_tokens = set(self.context_redactions) | {"doctrine", "constraint registry", "authority logic"}

        def _apply(text: str) -> str:
            if any(token in text.lower() for token in redaction_tokens):
                applied.extend(
                    token
                    for token in redaction_tokens
                    if token in text.lower() and token not in applied
                )
                return "[REDACTED]"
            return text

        redacted_goal = _apply(self.goal)
        redacted_synopsis = _apply(self.minimal_synopsis)
        redacted_files = tuple(_apply(entry) for entry in self.files_in_scope)
        redacted = replace(
            self,
            goal=redacted_goal,
            minimal_synopsis=redacted_synopsis,
            files_in_scope=redacted_files,
        )
        return redacted, tuple(applied)

    def restricted_view(self) -> "AdvisoryRequest":
        """Expose only backlog, files, and synopsis to external advisors."""

        return replace(
            self,
            context_redactions=(),
            forbidden_changes=tuple(self.forbidden_changes),
            constraints={
                "must": tuple(self.constraints.get("must", ())),
                "must_not": tuple(self.constraints.get("must_not", ())),
            },
        )


@dataclass(frozen=True)
class AdvisoryResponse:
    proposed_steps: tuple[str, ...]
    risks: tuple[str, ...]
    invariants_touched: tuple[str, ...]
    confidence: float
    uncertainties: tuple[str, ...]
    version: str = "2.0"
    executable: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposed_steps", tuple(self.proposed_steps))
        object.__setattr__(self, "risks", tuple(self.risks))
        object.__setattr__(self, "invariants_touched", tuple(self.invariants_touched))
        object.__setattr__(self, "uncertainties", tuple(self.uncertainties))

    def validate(self) -> None:
        sequences = (
            self.proposed_steps,
            self.risks,
            self.invariants_touched,
            self.uncertainties,
        )
        if any(callable(entry) for seq in sequences for entry in seq):
            raise ValueError("advisory responses must be inert text")
        if self.confidence < 0 or self.confidence > 1:
            raise ValueError("confidence must be between 0 and 1")
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
        request_payload = json.loads(_deterministic_dumps(request.__dict__))
        response_payload = json.loads(_deterministic_dumps(response.__dict__)) if response else None
        entry = {
            "stage": stage,
            "request": request_payload,
            "request_hash": _hash_payload(request_payload),
            "response": response_payload,
            "response_hash": _hash_payload(response_payload) if response_payload else None,
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

        if len(redacted_request.files_in_scope) > self.max_scope_size:
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
                response = responder(redacted_request.restricted_view())
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
        if self._scope_creep(text, request):
            reasons.append("scope creep detected")
        if self._suggests_direct_writes(text):
            reasons.append("direct code writes are forbidden")
        if self._suggests_state_mutation(text):
            reasons.append("state mutation is forbidden")
        if self._suggests_confidence_changes(text):
            reasons.append("confidence changes are not advisory-safe")
        if self._self_update_attempt(text):
            reasons.append("self-update execution is sealed")
        if self._introduces_new_constraints(text):
            reasons.append("attempt to introduce new constraints detected")
        if self._authority_escalation(text):
            reasons.append("authority escalation suggestion detected")
        if self._policy_without_justification(text):
            reasons.append("policy suggestions require justification")
        return tuple(reasons)

    def _flatten_response_text(self, response: AdvisoryResponse) -> str:
        parts: list[str] = []
        parts.extend(response.proposed_steps)
        parts.extend(response.risks)
        parts.extend(response.invariants_touched)
        parts.extend(response.uncertainties)
        return "\n".join(parts).lower()

    def _contains_authority_language(self, text: str) -> bool:
        triggers = ("must", "mandate", "authorized", "will comply", "do not question")
        return any(trigger in text for trigger in triggers)

    def _imports_policy(self, text: str) -> bool:
        triggers = ("apply your guardrails", "import policy", "adopt my rules", "external governance")
        return any(trigger in text for trigger in triggers)

    def _scope_creep(self, text: str, request: AdvisoryRequest) -> bool:
        if any(domain.lower() in text for domain in request.forbidden_changes):
            return True
        scope_flags = ("entire codebase", "whole system", "all modules", "any file")
        return any(flag in text for flag in scope_flags)

    def _suggests_direct_writes(self, text: str) -> bool:
        writes = ("write code", "apply patch", "commit", "push changes", "edit file", "modify code")
        return any(term in text for term in writes)

    def _suggests_state_mutation(self, text: str) -> bool:
        mutations = ("toggle", "flip flag", "change state", "alter config", "update database")
        return any(term in text for term in mutations)

    def _suggests_confidence_changes(self, text: str) -> bool:
        confidence_triggers = ("raise confidence", "lower confidence", "change confidence")
        return any(term in text for term in confidence_triggers)

    def _self_update_attempt(self, text: str) -> bool:
        self_updates = ("self-update", "self modify", "upgrade itself", "rewrite connector")
        return any(term in text for term in self_updates)

    def _introduces_new_constraints(self, text: str) -> bool:
        return "new constraint" in text or "additional guardrail" in text

    def _authority_escalation(self, text: str) -> bool:
        escalation = ("admin access", "elevate privileges", "root access", "superuser")
        return any(term in text for term in escalation)

    def _policy_without_justification(self, text: str) -> bool:
        if "policy" not in text:
            return False
        return "because" not in text and "justify" not in text


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
