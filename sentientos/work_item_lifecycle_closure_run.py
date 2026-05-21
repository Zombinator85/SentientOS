from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, cast

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES
from sentientos.workspace_change_set_lifecycle_closure import build_workspace_change_set_lifecycle_closure_manifest, lifecycle_closure_evidence_from_mapping


@dataclass(frozen=True)
class OperatorConfirmedLifecycleClosurePolicy:
    allow_warning_review: bool = False
    matrix_required: bool = False
    artifacts_required: bool = False
    review_only: bool = False


@dataclass(frozen=True)
class OperatorConfirmedLifecycleClosureRequest:
    closure_review_packet: Mapping[str, Any]
    proposal: Mapping[str, Any] | None
    operator_confirmation: bool
    verification_run_packet: Mapping[str, Any] | None = None
    execution_run_packet: Mapping[str, Any] | None = None
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class OperatorConfirmedLifecycleClosureDecision:
    status: str
    lifecycle_closure_wing_invoked: bool
    workspace_change_set_lifecycle_closure_status: str | None
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    decision_summary: str
    final_eligible_surface: str | None


@dataclass(frozen=True)
class OperatorConfirmedLifecycleClosureRunPacket:
    lifecycle_closure_run_packet_id: str
    lifecycle_closure_run_packet_digest: str
    work_item_id: str
    source_kind: str | None
    source_ref: str | None
    closure_review_packet_id: str
    closure_review_packet_digest: str
    closure_review_status: str
    proposal_id: str | None
    proposal_digest: str | None
    operator_confirmation_present: bool
    lifecycle_closure_wing_invoked: bool
    workspace_change_set_lifecycle_closure_status: str | None
    closure_blocker_codes: tuple[str, ...]
    closure_warning_codes: tuple[str, ...]
    closure_decision_summary: str
    lifecycle_closed: bool | None
    lifecycle_closure_recorded: bool | None
    closed_surfaces: tuple[str, ...]
    completed_stage_summary: str | None
    evidence_references: tuple[str, ...]
    artifact_references: tuple[str, ...]
    final_eligible_surface: str | None
    explicit_non_authority_boundaries: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class OperatorConfirmedLifecycleClosureResult:
    status: str
    decision: OperatorConfirmedLifecycleClosureDecision
    packet: OperatorConfirmedLifecycleClosureRunPacket
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "decision": asdict(self.decision), "packet": self.packet.to_dict()}


def _tuple(v: Any) -> tuple[str, ...]:
    return tuple(str(x) for x in v) if isinstance(v, (list, tuple)) else ()


def evaluate_operator_confirmed_lifecycle_closure(request: OperatorConfirmedLifecycleClosureRequest, *, policy: OperatorConfirmedLifecycleClosurePolicy | None = None) -> OperatorConfirmedLifecycleClosureResult:
    p = policy or OperatorConfirmedLifecycleClosurePolicy()
    cr = dict(request.closure_review_packet.get("packet", request.closure_review_packet))
    review_status = str(request.closure_review_packet.get("status") or cr.get("status") or "")
    blockers, warnings = set(_tuple(cr.get("closure_attempt_blockers"))), set(_tuple(cr.get("closure_attempt_warnings")))
    invoke = False
    wing_status = None
    work_item_id = str(cr.get("work_item_id") or (request.proposal or {}).get("work_item_id") or "")

    if request.proposal is None:
        status = "lifecycle_closure_run_insufficient_evidence"; blockers.add("proposal_required")
    elif not request.operator_confirmation and not p.review_only:
        status = "lifecycle_closure_run_blocked_by_policy"; blockers.add("operator_confirmation_required")
    elif p.matrix_required and str((request.matrix_report or {}).get("status") or "") != "passed":
        status = "lifecycle_closure_run_blocked_by_policy"; blockers.add("matrix_report_required_passed")
    elif p.artifacts_required and not _tuple(cr.get("artifact_references")):
        status = "lifecycle_closure_run_insufficient_evidence"; blockers.add("artifact_references_required")
    elif str(cr.get("work_item_id") or "") and str((request.proposal or {}).get("work_item_id") or "") and str(cr.get("work_item_id")) != str((request.proposal or {}).get("work_item_id")):
        status = "lifecycle_closure_run_contradicted"; blockers.add("work_item_id_mismatch")
    elif review_status == "closure_review_ready_with_warnings" and not p.allow_warning_review:
        status = "lifecycle_closure_run_blocked_by_review"; blockers.add("warning_review_not_allowed")
    elif review_status not in {"closure_review_ready", "closure_review_ready_with_warnings"}:
        status = "lifecycle_closure_run_blocked_by_review"; blockers.add("closure_review_not_ready")
    elif p.review_only:
        status = "lifecycle_closure_run_completed"; warnings.add("review_only_closure_not_invoked")
    else:
        invoke = True
        evidence = lifecycle_closure_evidence_from_mapping(request.proposal)
        wing = cast(Any, build_workspace_change_set_lifecycle_closure_manifest)(**evidence)
        wing_status = str(wing.closure_manifest.lifecycle_closure_status)
        blockers |= set(_tuple(wing.closure_manifest.blocker_codes))
        warnings |= set(_tuple(wing.closure_manifest.unresolved_risk_codes))
        if wing_status in {"lifecycle_closed_clean", "lifecycle_closed_after_rollback"}:
            status = "lifecycle_closure_run_completed"
        elif wing_status in {"lifecycle_closed_with_partial_state", "lifecycle_open"}:
            status = "lifecycle_closure_run_completed_with_warnings"
        elif wing_status in {"lifecycle_blocked"}:
            status = "lifecycle_closure_run_blocked_by_closure"
        elif wing_status in {"lifecycle_contradicted"}:
            status = "lifecycle_closure_run_contradicted"
        elif wing_status in {"lifecycle_insufficient_evidence"}:
            status = "lifecycle_closure_run_insufficient_evidence"
        else:
            status = "lifecycle_closure_run_failed"

    final_surface = "work_item_lifecycle_completed" if status in {"lifecycle_closure_run_completed", "lifecycle_closure_run_completed_with_warnings"} and invoke else None
    dg = hashlib.sha256(json.dumps({"work_item_id": work_item_id, "status": status, "closure_review": cr.get("closure_review_packet_digest"), "proposal": request.proposal}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    packet = OperatorConfirmedLifecycleClosureRunPacket(
        lifecycle_closure_run_packet_id=f"wiclrun_{dg[:16]}", lifecycle_closure_run_packet_digest=dg, work_item_id=work_item_id,
        source_kind=(str(cr.get("source_kind") or "") or None), source_ref=(str(cr.get("source_ref") or "") or None),
        closure_review_packet_id=str(cr.get("closure_review_packet_id") or ""), closure_review_packet_digest=str(cr.get("closure_review_packet_digest") or ""), closure_review_status=review_status,
        proposal_id=(str((request.proposal or {}).get("proposal_id") or "") or None), proposal_digest=(str((request.proposal or {}).get("proposal_digest") or "") or None),
        operator_confirmation_present=bool(request.operator_confirmation), lifecycle_closure_wing_invoked=invoke, workspace_change_set_lifecycle_closure_status=wing_status,
        closure_blocker_codes=tuple(sorted(blockers)), closure_warning_codes=tuple(sorted(warnings)), closure_decision_summary=status,
        lifecycle_closed=bool(invoke and wing_status and wing_status.startswith("lifecycle_closed")) if invoke else None, lifecycle_closure_recorded=invoke,
        closed_surfaces=("workspace_change_set_lifecycle_closure",) if invoke else (), completed_stage_summary=("closure_wing_invoked" if invoke else None),
        evidence_references=("closure_review_packet", "proposal"), artifact_references=_tuple(cr.get("artifact_references")), final_eligible_surface=final_surface,
        explicit_non_authority_boundaries=tuple(cr.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    decision = OperatorConfirmedLifecycleClosureDecision(status=status, lifecycle_closure_wing_invoked=invoke, workspace_change_set_lifecycle_closure_status=wing_status, blocker_codes=packet.closure_blocker_codes, warning_codes=packet.closure_warning_codes, decision_summary=status, final_eligible_surface=final_surface)
    return OperatorConfirmedLifecycleClosureResult(status=status, decision=decision, packet=packet)


def write_operator_confirmed_lifecycle_closure_packet(result: OperatorConfirmedLifecycleClosureResult, path: str | Path) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
