from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES
from sentientos.workspace_change_set_lifecycle_orchestrator import (
    run_workspace_change_set_lifecycle_orchestration,
)

DRY_RUN_ADAPTER_STATUSES = frozenset({
    "dry_run_adapter_completed",
    "dry_run_adapter_blocked",
    "dry_run_adapter_insufficient_metadata",
    "dry_run_adapter_manual_review_required",
    "dry_run_adapter_contradicted",
    "dry_run_adapter_failed",
})

ALLOWED_HANDOFF_SURFACES = frozenset({
    "eligible_for_dry_run_lifecycle",
    "eligible_for_workspace_change_set_admission",
})

BLOCKED_AUTHORITY_TOKENS = frozenset({"network", "provider", "prompt_export", "subprocess", "shell", "workspace_execution", "issue_mutation", "pr_creation", "branch_creation"})


@dataclass(frozen=True)
class WorkItemLifecycleDryRunAdapterPolicy:
    metadata_only: bool = True
    require_explicit_dry_run_request: bool = True
    enforce_non_invoking_lifecycle_candidate: bool = True


@dataclass(frozen=True)
class WorkItemLifecycleDryRunAdapterRequest:
    packet: Mapping[str, Any]
    handoff_plan: Mapping[str, Any]
    workspace_root: str | None
    request_dry_run: bool = False
    artifact_output_path: str | None = None


@dataclass(frozen=True)
class WorkItemLifecycleDryRunAdapterResult:
    adapter_status: str
    work_item_id: str
    handoff_plan_id: str | None
    dry_run_eligibility_status: str
    lifecycle_orchestration_invoked: bool
    lifecycle_mode_used: str | None
    lifecycle_dry_run_status: str | None
    lifecycle_stop_reason: str | None
    admission_status: str | None
    preflight_status: str | None
    transaction_plan_status: str | None
    transaction_plan_ready: bool | None
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    missing_metadata_fields: tuple[str, ...]
    artifact_records: tuple[Mapping[str, str], ...]
    explicit_non_authority_boundaries: tuple[str, ...] = EXPLICIT_NON_AUTHORITY_BOUNDARIES

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tuple(v: Any) -> tuple[str, ...]:
    if isinstance(v, (list, tuple)):
        return tuple(sorted({str(x).strip() for x in v if str(x).strip()}))
    return ()


def _handoff_id(plan: Mapping[str, Any]) -> str | None:
    wid = str(plan.get("work_item_id", "")).strip()
    if not wid:
        return None
    seed = json.dumps({"work_item_id": wid, "surface": plan.get("recommended_next_governed_surface", "")}, sort_keys=True, separators=(",", ":"))
    return "wih_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _write_artifact(path: str | None, payload: Mapping[str, Any]) -> tuple[tuple[Mapping[str, str], ...],]:
    if not path:
        return ((),)
    p = Path(path)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    return (({"stage": "dry_run_adapter", "path": str(p), "digest": digest},),)


def run_work_item_lifecycle_dry_run_adapter(request: WorkItemLifecycleDryRunAdapterRequest, *, policy: WorkItemLifecycleDryRunAdapterPolicy | None = None) -> WorkItemLifecycleDryRunAdapterResult:
    chosen = policy or WorkItemLifecycleDryRunAdapterPolicy()
    packet = request.packet
    handoff = request.handoff_plan
    blockers = list(_tuple(packet.get("blocker_codes"))) + list(_tuple(handoff.get("blocker_codes")))
    warnings = _tuple(packet.get("warning_codes"))
    missing = list(_tuple(handoff.get("missing_metadata_fields")))

    if not str(packet.get("work_item_id", "")).strip():
        missing.append("work_item_id")
    if not str(handoff.get("recommended_next_governed_surface", "")).strip():
        missing.append("recommended_next_governed_surface")

    surface = str(handoff.get("recommended_next_governed_surface", "")).strip()
    intake = str(packet.get("intake_status", "")).strip()
    proposal = packet.get("workspace_change_set_proposal_metadata")
    authorities = _tuple(packet.get("declared_authority_requests"))
    candidate = handoff.get("lifecycle_orchestration_request_candidate_metadata")
    agent_requested = bool(packet.get("agent_execution_is_requested", False) or packet.get("agent_execution_is_permitted_by_this_packet", False))

    status = "dry_run_adapter_completed"
    eligibility = "eligible"
    if missing:
        status = "dry_run_adapter_insufficient_metadata"
        eligibility = "insufficient_metadata"
        blockers.append("missing_required_metadata")
    elif chosen.require_explicit_dry_run_request and not request.request_dry_run:
        status = "dry_run_adapter_manual_review_required"
        eligibility = "dry_run_not_explicitly_requested"
        blockers.append("dry_run_not_explicitly_requested")
    elif intake not in {"intake_accepted", "intake_accepted_with_warnings"}:
        status = "dry_run_adapter_blocked"
        eligibility = "packet_not_accepted"
        blockers.append("packet_not_accepted")
    elif surface not in ALLOWED_HANDOFF_SURFACES:
        status = "dry_run_adapter_manual_review_required"
        eligibility = "handoff_surface_not_dry_run_eligible"
        blockers.append("handoff_surface_not_dry_run_eligible")
    elif not isinstance(proposal, Mapping):
        status = "dry_run_adapter_insufficient_metadata"
        eligibility = "workspace_proposal_missing"
        missing.append("workspace_change_set_proposal_metadata")
    elif any(a in BLOCKED_AUTHORITY_TOKENS for a in authorities) or any(code.startswith("authority_blocked_") for code in blockers):
        status = "dry_run_adapter_blocked"
        eligibility = "blocked_authority_request"
        blockers.append("blocked_authority_request")
    elif agent_requested:
        status = "dry_run_adapter_blocked"
        eligibility = "agent_execution_requested"
        blockers.append("agent_execution_requested")
    elif isinstance(candidate, Mapping) and chosen.enforce_non_invoking_lifecycle_candidate and not bool(candidate.get("orchestration_not_invoked", False)):
        status = "dry_run_adapter_contradicted"
        eligibility = "invoking_lifecycle_candidate_forbidden"
        blockers.append("invoking_lifecycle_candidate_forbidden")

    invoked = False
    lifecycle_mode: str | None = None
    lifecycle_status: str | None = None
    stop_reason: str | None = None
    admission_status: str | None = None
    preflight_status: str | None = None
    tx_status: str | None = None
    tx_ready: bool | None = None
    artifact_records: tuple[Mapping[str, str], ...] = ()

    if status == "dry_run_adapter_completed":
        try:
            assert isinstance(proposal, Mapping)
            wing = run_workspace_change_set_lifecycle_orchestration(
                dict(proposal),
                mode="dry_run_full_lifecycle",
                workspace_root=request.workspace_root,
            )
            invoked = True
            lifecycle_mode = "dry_run_full_lifecycle"
            lifecycle_status = "dry_run_completed" if wing.result.stop_reason == "lifecycle_completed_for_requested_mode" else "dry_run_not_completed"
            stop_reason = wing.result.stop_reason
            admission_status = wing.result.admission_status
            preflight_status = wing.result.preflight_status
            tx_status = wing.result.transaction_plan_status
            tx_ready = wing.result.transaction_plan_ready
        except Exception:
            status = "dry_run_adapter_failed"
            eligibility = "dry_run_lifecycle_failed"
            blockers.append("dry_run_lifecycle_failed")

    if request.artifact_output_path:
        payload = {
            "request": {
                "work_item_id": packet.get("work_item_id"),
                "handoff_plan_id": _handoff_id(handoff),
                "workspace_root": request.workspace_root,
                "request_dry_run": request.request_dry_run,
            },
            "result": {
                "adapter_status": status,
                "dry_run_eligibility_status": eligibility,
                "lifecycle_orchestration_invoked": invoked,
                "lifecycle_mode_used": lifecycle_mode,
                "lifecycle_dry_run_status": lifecycle_status,
                "lifecycle_stop_reason": stop_reason,
                "admission_status": admission_status,
                "preflight_status": preflight_status,
                "transaction_plan_status": tx_status,
                "transaction_plan_ready": tx_ready,
            },
        }
        artifact_records = _write_artifact(request.artifact_output_path, payload)[0]

    return WorkItemLifecycleDryRunAdapterResult(
        adapter_status=status,
        work_item_id=str(packet.get("work_item_id", "")),
        handoff_plan_id=_handoff_id(handoff),
        dry_run_eligibility_status=eligibility,
        lifecycle_orchestration_invoked=invoked,
        lifecycle_mode_used=lifecycle_mode,
        lifecycle_dry_run_status=lifecycle_status,
        lifecycle_stop_reason=stop_reason,
        admission_status=admission_status,
        preflight_status=preflight_status,
        transaction_plan_status=tx_status,
        transaction_plan_ready=tx_ready,
        blocker_codes=tuple(sorted(set(blockers))),
        warning_codes=warnings,
        missing_metadata_fields=tuple(sorted(set(missing))),
        artifact_records=artifact_records,
    )


__all__ = [
    "DRY_RUN_ADAPTER_STATUSES",
    "WorkItemLifecycleDryRunAdapterPolicy",
    "WorkItemLifecycleDryRunAdapterRequest",
    "WorkItemLifecycleDryRunAdapterResult",
    "run_work_item_lifecycle_dry_run_adapter",
]
