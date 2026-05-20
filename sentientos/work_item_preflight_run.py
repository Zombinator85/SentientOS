from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES
from sentientos.workspace_change_set_preflight import WorkspaceChangeSetPolicy, WorkspaceChangeTargetDeclaration, run_workspace_change_set_preflight_wing


@dataclass(frozen=True)
class OperatorConfirmedPreflightPolicy:
    allow_warning_admission: bool = False
    matrix_required: bool = False
    review_only: bool = False


@dataclass(frozen=True)
class OperatorConfirmedPreflightRequest:
    admission_run_packet: Mapping[str, Any]
    proposal: Mapping[str, Any] | None
    workspace_root: str | None
    operator_review_packet: Mapping[str, Any] | None = None
    promotion_dossier: Mapping[str, Any] | None = None
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class OperatorConfirmedPreflightDecision:
    status: str
    preflight_controller_invoked: bool
    workspace_change_set_preflight_status: str | None
    transaction_plan_ready: bool
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    decision_summary: str
    next_eligible_surface: str | None


@dataclass(frozen=True)
class OperatorConfirmedPreflightRunPacket:
    preflight_run_packet_id: str
    preflight_run_packet_digest: str
    work_item_id: str
    source_kind: str | None
    source_ref: str | None
    admission_run_packet_id: str
    admission_run_packet_digest: str
    admission_run_status: str
    workspace_change_set_admission_status: str | None
    proposal_id: str | None
    proposal_digest: str | None
    workspace_root_summary: str
    preflight_controller_invoked: bool
    workspace_change_set_preflight_status: str | None
    transaction_plan_ready: bool
    target_count: int
    operation_types: tuple[str, ...]
    proposed_paths_summary: tuple[str, ...]
    preflight_blocker_codes: tuple[str, ...]
    preflight_warning_codes: tuple[str, ...]
    preflight_decision_summary: str
    operator_acknowledgements: tuple[str, ...]
    readiness_summary: tuple[str, ...]
    evidence_references: tuple[str, ...]
    artifact_references: tuple[str, ...]
    next_eligible_surface: str | None
    explicit_non_authority_boundaries: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class OperatorConfirmedPreflightResult:
    status: str
    decision: OperatorConfirmedPreflightDecision
    packet: OperatorConfirmedPreflightRunPacket
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "decision": asdict(self.decision), "packet": self.packet.to_dict()}


def _tuple(v: Any) -> tuple[str, ...]:
    return tuple(str(x) for x in v) if isinstance(v, (list, tuple)) else ()


def evaluate_operator_confirmed_preflight(request: OperatorConfirmedPreflightRequest, *, policy: OperatorConfirmedPreflightPolicy | None = None) -> OperatorConfirmedPreflightResult:
    p = policy or OperatorConfirmedPreflightPolicy()
    ar = dict(request.admission_run_packet.get("packet", request.admission_run_packet))
    st = str(request.admission_run_packet.get("status") or ar.get("admission_run_status") or "")
    blockers, warnings = set(), set()
    invoke, preflight_status, tx_ready = False, None, False
    work_item_id = str(ar.get("work_item_id") or "")
    status = "preflight_run_failed"
    summary = ""
    matrix_status = str((request.matrix_report or {}).get("status") or "")
    admission_status = str(ar.get("workspace_change_set_admission_status") or "")
    if request.proposal is None:
        status = "preflight_run_insufficient_evidence"; blockers.add("proposal_required")
    elif not request.workspace_root:
        status = "preflight_run_insufficient_evidence"; blockers.add("workspace_root_required")
    elif p.matrix_required and matrix_status != "passed":
        status = "preflight_run_blocked_by_policy"; blockers.add("matrix_report_required_passed")
    elif str(ar.get("work_item_id") or "") and str(request.proposal.get("work_item_id") or "") and str(ar.get("work_item_id")) != str(request.proposal.get("work_item_id")):
        status = "preflight_run_contradicted"; blockers.add("work_item_id_mismatch")
    elif st == "admission_run_accepted_with_warnings" and not p.allow_warning_admission:
        status = "preflight_run_blocked_by_admission"; blockers.add("warning_admission_not_allowed")
    elif st not in {"admission_run_accepted", "admission_run_accepted_with_warnings"}:
        status = "preflight_run_blocked_by_admission"; blockers.add("admission_not_accepted")
    elif admission_status not in {"admission_accepted", "admission_accepted_with_warnings"}:
        status = "preflight_run_blocked_by_admission"; blockers.add("workspace_change_set_admission_not_accepted")
    elif not bool(ar.get("admission_controller_invoked")) and not p.review_only:
        status = "preflight_run_blocked_by_policy"; blockers.add("admission_controller_not_invoked")
    elif p.review_only:
        status = "preflight_run_ready"; summary = "review-only requested; preflight not invoked"
    else:
        invoke = True
        targets = tuple(WorkspaceChangeTargetDeclaration(target_id=str(t.get("target_id")), relative_target_path=str(t.get("relative_target_path")), operation=str(t.get("operation")), payload_text="", payload_media_type="text/plain", allow_replace=bool(t.get("allow_replace", True)), allow_create=bool(t.get("allow_create", True)), required_scope_labels=("workspace_change_set_preflight",), warning_codes=(), risk_codes=(), created_at="1970-01-01T00:00:00Z", digest=str(t.get("declared_payload_digest") or "sha256:unknown")) for t in request.proposal.get("proposed_targets", ()))
        wing = run_workspace_change_set_preflight_wing(workspace_root=request.workspace_root, targets=targets, policy=WorkspaceChangeSetPolicy())
        preflight_status = str(wing["preflight_report"]["report_status"]); tx_ready = bool(wing["summary"]["transaction_ready"])
        warnings |= set(_tuple(wing["preflight_report"].get("warning_codes"))); blockers |= set(_tuple(wing["preflight_report"].get("risk_codes")))
        if preflight_status in {"workspace_change_set_preflight_passed", "workspace_change_set_preflight_passed_with_warnings"}:
            status = "preflight_run_ready_with_warnings" if warnings else "preflight_run_ready"; summary = f"preflight returned {preflight_status}"
        else:
            status = "preflight_run_blocked_by_preflight"; summary = f"preflight returned {preflight_status}"
    next_surface = "workspace_change_set_execution_may_be_considered" if status in {"preflight_run_ready", "preflight_run_ready_with_warnings"} and invoke and tx_ready else None
    basis = {"work_item_id": work_item_id, "status": status, "admission": ar.get("admission_run_packet_digest"), "proposal": request.proposal, "workspace_root": request.workspace_root}
    dg = hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    packet = OperatorConfirmedPreflightRunPacket(
        preflight_run_packet_id=f"wipre_{dg[:16]}", preflight_run_packet_digest=dg, work_item_id=work_item_id, source_kind=(str(ar.get("source_kind") or "") or None), source_ref=(str(ar.get("source_ref") or "") or None),
        admission_run_packet_id=str(ar.get("admission_run_packet_id") or ""), admission_run_packet_digest=str(ar.get("admission_run_packet_digest") or ""), admission_run_status=st, workspace_change_set_admission_status=(admission_status or None),
        proposal_id=(str((request.proposal or {}).get("proposal_id") or "") or None), proposal_digest=(str((request.proposal or {}).get("proposal_digest") or "") or None), workspace_root_summary=str(request.workspace_root or ""),
        preflight_controller_invoked=invoke, workspace_change_set_preflight_status=preflight_status, transaction_plan_ready=tx_ready, target_count=int((request.proposal or {}).get("declared_target_count") or len((request.proposal or {}).get("proposed_targets", ()))),
        operation_types=tuple(sorted({str(t.get("operation")) for t in (request.proposal or {}).get("proposed_targets", ())})), proposed_paths_summary=tuple(sorted(str(t.get("relative_target_path")) for t in (request.proposal or {}).get("proposed_targets", ()))),
        preflight_blocker_codes=tuple(sorted(blockers)), preflight_warning_codes=tuple(sorted(warnings)), preflight_decision_summary=summary or status,
        operator_acknowledgements=_tuple(ar.get("operator_acknowledgements")), readiness_summary=tuple(sorted(_tuple(ar.get("readiness_summary")))), evidence_references=tuple(sorted(_tuple(ar.get("evidence_references")))), artifact_references=(),
        next_eligible_surface=next_surface, explicit_non_authority_boundaries=tuple(ar.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES)
    )
    decision = OperatorConfirmedPreflightDecision(status=status, preflight_controller_invoked=invoke, workspace_change_set_preflight_status=preflight_status, transaction_plan_ready=tx_ready, blocker_codes=packet.preflight_blocker_codes, warning_codes=packet.preflight_warning_codes, decision_summary=packet.preflight_decision_summary, next_eligible_surface=next_surface)
    return OperatorConfirmedPreflightResult(status=status, decision=decision, packet=packet)


def write_operator_confirmed_preflight_packet(result: OperatorConfirmedPreflightResult, path: str | Path) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
