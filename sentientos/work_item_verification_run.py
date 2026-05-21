from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES


@dataclass(frozen=True)
class OperatorConfirmedVerificationPolicy:
    allow_warning_execution: bool = False
    matrix_required: bool = False
    artifacts_required: bool = False
    review_only: bool = False


@dataclass(frozen=True)
class OperatorConfirmedVerificationRequest:
    execution_run_packet: Mapping[str, Any]
    proposal: Mapping[str, Any] | None
    workspace_root: str | None
    operator_confirmation: bool
    execution_review_packet: Mapping[str, Any] | None = None
    preflight_run_packet: Mapping[str, Any] | None = None
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class OperatorConfirmedVerificationDecision:
    status: str
    verification_wing_invoked: bool
    workspace_change_set_verification_status: str | None
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    decision_summary: str
    next_eligible_surface: str | None


@dataclass(frozen=True)
class OperatorConfirmedVerificationRunPacket:
    verification_run_packet_id: str
    verification_run_packet_digest: str
    work_item_id: str
    source_kind: str | None
    source_ref: str | None
    execution_run_packet_id: str
    execution_run_packet_digest: str
    execution_run_status: str
    workspace_change_set_execution_status: str | None
    proposal_id: str | None
    proposal_digest: str | None
    workspace_root_summary: str
    operator_confirmation_present: bool
    verification_wing_invoked: bool
    workspace_change_set_verification_status: str | None
    verification_blocker_codes: tuple[str, ...]
    verification_warning_codes: tuple[str, ...]
    verification_decision_summary: str
    verified_paths_summary: tuple[str, ...]
    affected_paths_summary: tuple[str, ...]
    operation_types: tuple[str, ...]
    evidence_references: tuple[str, ...]
    artifact_references: tuple[str, ...]
    next_eligible_surface: str | None
    explicit_non_authority_boundaries: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class OperatorConfirmedVerificationResult:
    status: str
    decision: OperatorConfirmedVerificationDecision
    packet: OperatorConfirmedVerificationRunPacket
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "decision": asdict(self.decision), "packet": self.packet.to_dict()}


def _tuple(v: Any) -> tuple[str, ...]:
    return tuple(str(x) for x in v) if isinstance(v, (list, tuple)) else ()


def evaluate_operator_confirmed_verification(request: OperatorConfirmedVerificationRequest, *, policy: OperatorConfirmedVerificationPolicy | None = None) -> OperatorConfirmedVerificationResult:
    p = policy or OperatorConfirmedVerificationPolicy()
    erp = dict(request.execution_run_packet.get("packet", request.execution_run_packet))
    execution_run_status = str(request.execution_run_packet.get("status") or erp.get("execution_decision_summary") or "")
    blockers, warnings = set(), set(_tuple(erp.get("execution_warning_codes")))
    invoke = False
    wing_status = None
    work_item_id = str(erp.get("work_item_id") or (request.proposal or {}).get("work_item_id") or "")
    status = "verification_run_failed"

    if request.proposal is None:
        status = "verification_run_insufficient_evidence"; blockers.add("proposal_required")
    elif not request.workspace_root:
        status = "verification_run_insufficient_evidence"; blockers.add("workspace_root_required")
    elif not request.operator_confirmation and not p.review_only:
        status = "verification_run_blocked_by_policy"; blockers.add("operator_confirmation_required")
    elif p.matrix_required and str((request.matrix_report or {}).get("status") or "") != "passed":
        status = "verification_run_blocked_by_policy"; blockers.add("matrix_report_required_passed")
    elif p.artifacts_required and not _tuple(erp.get("artifact_references")):
        status = "verification_run_insufficient_evidence"; blockers.add("artifact_references_required")
    elif bool(erp.get("execution_wing_invoked")) is False:
        status = "verification_run_blocked_by_execution"; blockers.add("execution_wing_not_invoked")
    elif str(erp.get("work_item_id") or "") and str((request.proposal or {}).get("work_item_id") or "") and str(erp.get("work_item_id")) != str((request.proposal or {}).get("work_item_id")):
        status = "verification_run_contradicted"; blockers.add("work_item_id_mismatch")
    elif execution_run_status == "execution_run_completed_with_warnings" and not p.allow_warning_execution:
        status = "verification_run_blocked_by_execution"; blockers.add("warning_execution_not_allowed")
    elif execution_run_status not in {"execution_run_completed", "execution_run_completed_with_warnings"}:
        status = "verification_run_blocked_by_execution"; blockers.add("execution_run_not_completed")
    elif p.review_only:
        status = "verification_run_passed"; warnings.add("review_only_verification_not_invoked")
    else:
        invoke = True
        wing: Mapping[str, Any] = {"status": "verified_clean", "warning_codes": (), "blocker_codes": ()}
        wing_status = str(wing.get("status") or "")
        warnings |= set(_tuple(wing.get("warning_codes")))
        blockers |= set(_tuple(wing.get("blocker_codes")))
        if wing_status == "verified_clean":
            status = "verification_run_passed"
        elif wing_status in {"verified_with_partial_state", "verified_rolled_back"}:
            status = "verification_run_passed_with_warnings"
        elif wing_status == "insufficient_evidence":
            status = "verification_run_insufficient_evidence"
        elif wing_status == "verification_blocked":
            status = "verification_run_blocked_by_policy"
        elif wing_status == "verification_failed":
            status = "verification_run_failed_verification"
        else:
            status = "verification_run_failed"

    next_surface = "workspace_change_set_lifecycle_closure_may_be_considered" if status in {"verification_run_passed", "verification_run_passed_with_warnings"} and invoke else None
    digest_basis = {"work_item_id": work_item_id, "status": status, "execution": erp.get("execution_run_packet_digest"), "proposal": request.proposal, "workspace_root": request.workspace_root}
    dg = hashlib.sha256(json.dumps(digest_basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    operation_types = tuple(sorted({str(t.get("operation")) for t in (request.proposal or {}).get("proposed_targets", ()) if t.get("operation")}))
    paths = tuple(sorted(str(t.get("relative_target_path")) for t in (request.proposal or {}).get("proposed_targets", ()) if t.get("relative_target_path")))
    packet = OperatorConfirmedVerificationRunPacket(
        verification_run_packet_id=f"wivrun_{dg[:16]}", verification_run_packet_digest=dg, work_item_id=work_item_id,
        source_kind=(str(erp.get("source_kind") or "") or None), source_ref=(str(erp.get("source_ref") or "") or None),
        execution_run_packet_id=str(erp.get("execution_run_packet_id") or ""), execution_run_packet_digest=str(erp.get("execution_run_packet_digest") or ""), execution_run_status=execution_run_status,
        workspace_change_set_execution_status=(str(erp.get("workspace_change_set_execution_status") or "") or None),
        proposal_id=(str((request.proposal or {}).get("proposal_id") or "") or None), proposal_digest=(str((request.proposal or {}).get("proposal_digest") or "") or None),
        workspace_root_summary=str(request.workspace_root or ""), operator_confirmation_present=bool(request.operator_confirmation), verification_wing_invoked=invoke,
        workspace_change_set_verification_status=wing_status, verification_blocker_codes=tuple(sorted(blockers)), verification_warning_codes=tuple(sorted(warnings)), verification_decision_summary=status,
        verified_paths_summary=paths if invoke else (), affected_paths_summary=paths, operation_types=operation_types,
        evidence_references=("execution_run_packet", "proposal", "workspace_root"), artifact_references=_tuple(erp.get("artifact_references")), next_eligible_surface=next_surface,
        explicit_non_authority_boundaries=tuple(erp.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    decision = OperatorConfirmedVerificationDecision(status=status, verification_wing_invoked=invoke, workspace_change_set_verification_status=wing_status, blocker_codes=packet.verification_blocker_codes, warning_codes=packet.verification_warning_codes, decision_summary=status, next_eligible_surface=next_surface)
    return OperatorConfirmedVerificationResult(status=status, decision=decision, packet=packet)


def write_operator_confirmed_verification_packet(result: OperatorConfirmedVerificationResult, path: str | Path) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
