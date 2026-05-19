from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES

HANDOFF_SURFACES = frozenset({
    "no_action_required",
    "needs_operator_clarification",
    "needs_manual_review",
    "eligible_for_workspace_change_set_admission",
    "eligible_for_dry_run_lifecycle",
    "eligible_for_full_lifecycle_review",
    "blocked_authority_request",
    "blocked_external_integration_request",
    "blocked_agent_execution_request",
    "insufficient_metadata",
})

BLOCKED_AUTHORITY_TOKENS = frozenset({"network", "provider", "prompt_export", "subprocess", "shell", "issue_mutation", "pr_creation", "branch_creation", "workspace_execution"})
EXTERNAL_BLOCKER_TOKENS = frozenset({"network", "provider", "prompt_export"})


@dataclass(frozen=True)
class WorkItemLifecycleHandoffPolicy:
    metadata_only: bool = True
    allow_lifecycle_candidate_metadata: bool = True


@dataclass(frozen=True)
class WorkItemLifecycleHandoffRequest:
    packet: Mapping[str, Any]
    emit_lifecycle_candidate: bool = False


@dataclass(frozen=True)
class HandoffFinding:
    code: str
    severity: str
    detail: str


@dataclass(frozen=True)
class WorkItemLifecycleHandoffPlan:
    work_item_id: str
    source_kind: str
    intake_status: str
    risk_class: str
    requested_outcome_summary: str
    recommended_next_governed_surface: str
    workspace_change_set_admission_may_be_attempted: bool
    dry_run_lifecycle_may_be_attempted: bool
    full_lifecycle_may_be_reviewed: bool
    operator_review_required: bool
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    missing_metadata_fields: tuple[str, ...]
    authority_request_summary: tuple[str, ...]
    workspace_change_set_proposal_candidate_id: str | None
    workspace_change_set_proposal_candidate_digest: str | None
    lifecycle_orchestration_request_candidate_metadata: Mapping[str, Any] | None
    explicit_non_authority_boundaries: tuple[str, ...] = EXPLICIT_NON_AUTHORITY_BOUNDARIES


def _tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(sorted({str(x).strip() for x in value if str(x).strip()}))
    if isinstance(value, tuple):
        return tuple(sorted({str(x).strip() for x in value if str(x).strip()}))
    return ()


def _missing(packet: Mapping[str, Any]) -> tuple[str, ...]:
    miss = []
    for k in ("work_item_id", "source_kind", "intake_status", "requested_outcome"):
        v = packet.get(k)
        if not isinstance(v, str) or not v.strip():
            miss.append(k)
    return tuple(miss)


def _proposal_metadata(packet: Mapping[str, Any]) -> tuple[str | None, str | None]:
    proposal = packet.get("workspace_change_set_proposal_metadata")
    if not isinstance(proposal, Mapping):
        return None, None
    normalized = json.dumps(dict(proposal), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"wsp_{digest[:16]}", digest


def plan_work_item_lifecycle_handoff(request: WorkItemLifecycleHandoffRequest, *, policy: WorkItemLifecycleHandoffPolicy | None = None) -> WorkItemLifecycleHandoffPlan:
    chosen = policy or WorkItemLifecycleHandoffPolicy()
    packet = request.packet
    blockers = _tuple(packet.get("blocker_codes"))
    warnings = _tuple(packet.get("warning_codes"))
    authorities = _tuple(packet.get("declared_authority_requests"))
    missing = _missing(packet)

    intake_status = str(packet.get("intake_status", "")).strip()
    risk_class = str(packet.get("risk_class", "")).strip()
    outcome = str(packet.get("requested_outcome", "")).strip()
    admission_allowed = bool(packet.get("workspace_change_set_admission_may_be_attempted", False))
    agent_requested = bool(packet.get("agent_execution_is_requested", False) or "agent_execution" in authorities)

    proposal_id, proposal_digest = _proposal_metadata(packet)
    blocked_external = any(a in EXTERNAL_BLOCKER_TOKENS for a in authorities)
    blocked_authority = any(a in BLOCKED_AUTHORITY_TOKENS for a in authorities) or any(code.startswith("authority_blocked_") for code in blockers)

    surface = "needs_manual_review"
    if missing or intake_status == "intake_insufficient_metadata":
        surface = "insufficient_metadata" if missing else "needs_operator_clarification"
    elif blocked_external:
        surface = "blocked_external_integration_request"
    elif agent_requested:
        surface = "blocked_agent_execution_request"
    elif blocked_authority or intake_status in {"intake_blocked", "intake_contradicted"}:
        surface = "blocked_authority_request"
    elif admission_allowed and proposal_id:
        surface = "eligible_for_workspace_change_set_admission"
    elif risk_class in {"informational", "documentation_only"}:
        surface = "no_action_required"

    dry_run_ok = bool(surface in {"eligible_for_workspace_change_set_admission", "eligible_for_dry_run_lifecycle"} and proposal_id)
    full_review_ok = bool(surface in {"eligible_for_full_lifecycle_review", "eligible_for_dry_run_lifecycle"} and proposal_id)

    lifecycle_candidate: Mapping[str, Any] | None = None
    if chosen.allow_lifecycle_candidate_metadata and request.emit_lifecycle_candidate and proposal_id:
        lifecycle_candidate = {
            "candidate_kind": "workspace_change_set_lifecycle_orchestration_request_metadata_only",
            "work_item_id": str(packet.get("work_item_id", "")),
            "workspace_change_set_proposal_candidate_id": proposal_id,
            "workspace_change_set_proposal_candidate_digest": proposal_digest,
            "requested_mode": "admit_preflight_verify_close",
            "orchestration_not_invoked": True,
        }

    return WorkItemLifecycleHandoffPlan(
        work_item_id=str(packet.get("work_item_id", "")),
        source_kind=str(packet.get("source_kind", "")),
        intake_status=intake_status,
        risk_class=risk_class,
        requested_outcome_summary=outcome[:220],
        recommended_next_governed_surface=surface,
        workspace_change_set_admission_may_be_attempted=bool(admission_allowed and proposal_id),
        dry_run_lifecycle_may_be_attempted=dry_run_ok,
        full_lifecycle_may_be_reviewed=full_review_ok,
        operator_review_required=surface not in {"no_action_required"},
        blocker_codes=blockers,
        warning_codes=warnings,
        missing_metadata_fields=missing,
        authority_request_summary=authorities,
        workspace_change_set_proposal_candidate_id=proposal_id,
        workspace_change_set_proposal_candidate_digest=proposal_digest,
        lifecycle_orchestration_request_candidate_metadata=lifecycle_candidate,
    )


def summarize_work_item_lifecycle_handoff_plan(plan: WorkItemLifecycleHandoffPlan) -> dict[str, Any]:
    return asdict(plan)


__all__ = [
    "HANDOFF_SURFACES",
    "HandoffFinding",
    "WorkItemLifecycleHandoffPlan",
    "WorkItemLifecycleHandoffPolicy",
    "WorkItemLifecycleHandoffRequest",
    "plan_work_item_lifecycle_handoff",
    "summarize_work_item_lifecycle_handoff_plan",
]
