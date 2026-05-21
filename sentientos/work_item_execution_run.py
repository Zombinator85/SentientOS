from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, cast

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES
from sentientos.workspace_change_set_execution import run_workspace_change_set_execution_wing


@dataclass(frozen=True)
class OperatorConfirmedExecutionPolicy:
    allow_warning_review: bool = False
    matrix_required: bool = False
    artifacts_required: bool = False
    review_only: bool = False


@dataclass(frozen=True)
class OperatorConfirmedExecutionRequest:
    execution_review_packet: Mapping[str, Any]
    proposal: Mapping[str, Any] | None
    workspace_root: str | None
    operator_confirmation: bool
    preflight_run_packet: Mapping[str, Any] | None = None
    admission_run_packet: Mapping[str, Any] | None = None
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class OperatorConfirmedExecutionDecision:
    status: str
    execution_wing_invoked: bool
    workspace_change_set_execution_status: str | None
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    decision_summary: str
    next_eligible_surface: str | None


@dataclass(frozen=True)
class OperatorConfirmedExecutionRunPacket:
    execution_run_packet_id: str
    execution_run_packet_digest: str
    work_item_id: str
    source_kind: str | None
    source_ref: str | None
    execution_review_packet_id: str
    execution_review_packet_digest: str
    execution_review_status: str
    proposal_id: str | None
    proposal_digest: str | None
    workspace_root_summary: str
    operator_confirmation_present: bool
    execution_wing_invoked: bool
    workspace_change_set_execution_status: str | None
    execution_blocker_codes: tuple[str, ...]
    execution_warning_codes: tuple[str, ...]
    execution_decision_summary: str
    files_changed_count: int | None
    operations_applied_count: int | None
    operation_types: tuple[str, ...]
    affected_paths_summary: tuple[str, ...]
    rollback_or_atomicity_summary: str | None
    evidence_references: tuple[str, ...]
    artifact_references: tuple[str, ...]
    next_eligible_surface: str | None
    explicit_non_authority_boundaries: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class OperatorConfirmedExecutionResult:
    status: str
    decision: OperatorConfirmedExecutionDecision
    packet: OperatorConfirmedExecutionRunPacket
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "decision": asdict(self.decision), "packet": self.packet.to_dict()}


def _tuple(v: Any) -> tuple[str, ...]:
    return tuple(str(x) for x in v) if isinstance(v, (list, tuple)) else ()


def evaluate_operator_confirmed_execution(request: OperatorConfirmedExecutionRequest, *, policy: OperatorConfirmedExecutionPolicy | None = None) -> OperatorConfirmedExecutionResult:
    p = policy or OperatorConfirmedExecutionPolicy()
    er = dict(request.execution_review_packet.get("packet", request.execution_review_packet))
    review_status = str(request.execution_review_packet.get("status") or er.get("status") or "")
    blockers, warnings = set(), set(_tuple(er.get("execution_attempt_warnings")))
    invoke = False
    wing_status = None
    work_item_id = str(er.get("work_item_id") or (request.proposal or {}).get("work_item_id") or "")
    status = "execution_run_failed"

    if request.proposal is None:
        status = "execution_run_insufficient_evidence"; blockers.add("proposal_required")
    elif not request.workspace_root:
        status = "execution_run_insufficient_evidence"; blockers.add("workspace_root_required")
    elif not request.operator_confirmation and not p.review_only:
        status = "execution_run_blocked_by_policy"; blockers.add("operator_confirmation_required")
    elif p.matrix_required and str((request.matrix_report or {}).get("status") or "") != "passed":
        status = "execution_run_blocked_by_policy"; blockers.add("matrix_report_required_passed")
    elif p.artifacts_required and not _tuple(er.get("artifact_references")):
        status = "execution_run_insufficient_evidence"; blockers.add("artifact_references_required")
    elif bool(er.get("transaction_plan_ready")) is False:
        status = "execution_run_blocked_by_review"; blockers.add("transaction_plan_not_ready")
    elif str(er.get("work_item_id") or "") and str((request.proposal or {}).get("work_item_id") or "") and str(er.get("work_item_id")) != str((request.proposal or {}).get("work_item_id")):
        status = "execution_run_contradicted"; blockers.add("work_item_id_mismatch")
    elif review_status == "execution_review_ready_with_warnings" and not p.allow_warning_review:
        status = "execution_run_blocked_by_review"; blockers.add("warning_review_not_allowed")
    elif review_status not in {"execution_review_ready", "execution_review_ready_with_warnings"}:
        status = "execution_run_blocked_by_review"; blockers.add("execution_review_not_ready")
    elif p.review_only:
        status = "execution_run_completed"; warnings.add("review_only_execution_not_invoked")
    else:
        invoke = True
        runner = cast(Any, run_workspace_change_set_execution_wing)
        wing = runner(proposal=dict(request.proposal), workspace_root=str(request.workspace_root))
        wing_status = str(wing.get("status") or wing.get("result", {}).get("execution_status") or "")
        warnings |= set(_tuple(wing.get("warning_codes")))
        blockers |= set(_tuple(wing.get("blocker_codes")))
        if wing_status in {"workspace_change_set_execution_performed", "workspace_change_set_execution_receipt_recorded"}:
            status = "execution_run_completed"
        elif wing_status in {"workspace_change_set_execution_performed_with_warnings", "workspace_change_set_execution_receipt_recorded_with_warnings"}:
            status = "execution_run_completed_with_warnings"
        elif "blocked" in wing_status:
            status = "execution_run_blocked_by_execution"
        else:
            status = "execution_run_failed"

    next_surface = "workspace_change_set_verification_may_be_considered" if status in {"execution_run_completed", "execution_run_completed_with_warnings"} and invoke else None
    digest_basis = {"work_item_id": work_item_id, "status": status, "review": er.get("execution_review_packet_digest"), "proposal": request.proposal, "workspace_root": request.workspace_root}
    dg = hashlib.sha256(json.dumps(digest_basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    operation_types = tuple(sorted({str(t.get("operation")) for t in (request.proposal or {}).get("proposed_targets", ()) if t.get("operation")}))
    paths = tuple(sorted(str(t.get("relative_target_path")) for t in (request.proposal or {}).get("proposed_targets", ()) if t.get("relative_target_path")))
    packet = OperatorConfirmedExecutionRunPacket(
        execution_run_packet_id=f"wierun_{dg[:16]}", execution_run_packet_digest=dg, work_item_id=work_item_id,
        source_kind=(str(er.get("source_kind") or "") or None), source_ref=(str(er.get("source_ref") or "") or None),
        execution_review_packet_id=str(er.get("execution_review_packet_id") or ""), execution_review_packet_digest=str(er.get("execution_review_packet_digest") or ""), execution_review_status=review_status,
        proposal_id=(str((request.proposal or {}).get("proposal_id") or "") or None), proposal_digest=(str((request.proposal or {}).get("proposal_digest") or "") or None),
        workspace_root_summary=str(request.workspace_root or ""), operator_confirmation_present=bool(request.operator_confirmation), execution_wing_invoked=invoke,
        workspace_change_set_execution_status=wing_status, execution_blocker_codes=tuple(sorted(blockers)), execution_warning_codes=tuple(sorted(warnings)), execution_decision_summary=status,
        files_changed_count=None, operations_applied_count=int((request.proposal or {}).get("declared_target_count") or len((request.proposal or {}).get("proposed_targets", ()))) if invoke else None,
        operation_types=operation_types, affected_paths_summary=paths, rollback_or_atomicity_summary="delegated_to_execution_wing_only" if invoke else None,
        evidence_references=("execution_review_packet", "proposal", "workspace_root"), artifact_references=_tuple(er.get("artifact_references")), next_eligible_surface=next_surface,
        explicit_non_authority_boundaries=tuple(er.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    decision = OperatorConfirmedExecutionDecision(status=status, execution_wing_invoked=invoke, workspace_change_set_execution_status=wing_status, blocker_codes=packet.execution_blocker_codes, warning_codes=packet.execution_warning_codes, decision_summary=status, next_eligible_surface=next_surface)
    return OperatorConfirmedExecutionResult(status=status, decision=decision, packet=packet)


def write_operator_confirmed_execution_packet(result: OperatorConfirmedExecutionResult, path: str | Path) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
