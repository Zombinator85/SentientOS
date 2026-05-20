from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES
from sentientos.workspace_change_set_admission import run_workspace_change_set_admission_wing, summarize_workspace_change_set_admission_decision


@dataclass(frozen=True)
class OperatorConfirmedAdmissionPolicy:
    allow_warning_review: bool = False
    matrix_required: bool = False
    dry_run_review_only: bool = False


@dataclass(frozen=True)
class OperatorConfirmedAdmissionRequest:
    operator_review_packet: Mapping[str, Any]
    proposal: Mapping[str, Any] | None
    promotion_dossier: Mapping[str, Any] | None = None
    review_packet: Mapping[str, Any] | None = None
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class OperatorConfirmedAdmissionDecision:
    status: str
    admission_controller_invoked: bool
    workspace_change_set_admission_status: str | None
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    decision_summary: str
    next_eligible_surface: str | None


@dataclass(frozen=True)
class OperatorConfirmedAdmissionRunPacket:
    admission_run_packet_id: str
    admission_run_packet_digest: str
    work_item_id: str
    source_kind: str | None
    source_ref: str | None
    operator_admission_review_packet_id: str
    operator_admission_review_packet_digest: str
    operator_admission_review_status: str
    proposal_id: str | None
    proposal_digest: str | None
    admission_controller_invoked: bool
    workspace_change_set_admission_status: str | None
    admission_blocker_codes: tuple[str, ...]
    admission_warning_codes: tuple[str, ...]
    admission_decision_summary: str
    operator_acknowledgements: tuple[str, ...]
    readiness_summary: tuple[str, ...]
    evidence_references: tuple[str, ...]
    artifact_references: tuple[str, ...]
    next_eligible_surface: str | None
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OperatorConfirmedAdmissionResult:
    status: str
    decision: OperatorConfirmedAdmissionDecision
    packet: OperatorConfirmedAdmissionRunPacket

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "decision": asdict(self.decision), "packet": self.packet.to_dict()}


def _tuple(v: Any) -> tuple[str, ...]:
    return tuple(str(x) for x in v) if isinstance(v, (list, tuple)) else ()


def evaluate_operator_confirmed_admission(request: OperatorConfirmedAdmissionRequest, *, policy: OperatorConfirmedAdmissionPolicy | None = None) -> OperatorConfirmedAdmissionResult:
    p = policy or OperatorConfirmedAdmissionPolicy()
    review = dict(request.operator_review_packet.get("packet", request.operator_review_packet))
    review_status = str(request.operator_review_packet.get("status") or review.get("status") or "")
    work_item_id = str(review.get("work_item_id") or "")
    blockers = set(_tuple(review.get("blocker_codes"))) | set(_tuple(review.get("admission_attempt_blockers")))
    warnings = set(_tuple(review.get("warning_codes"))) | set(_tuple(review.get("admission_attempt_warnings")))
    contradictions = set(_tuple(review.get("contradiction_codes")))
    missing_ack = not _tuple(review.get("required_operator_acknowledgements"))
    status = "admission_run_failed"
    invoke = False
    ws_status = None
    summary = ""
    next_surface = None

    matrix_status = str((request.matrix_report or {}).get("status") or "")
    if request.proposal is None:
        status = "admission_run_insufficient_evidence"; blockers.add("proposal_required")
    elif p.matrix_required and matrix_status != "passed":
        status = "admission_run_blocked_by_policy"; blockers.add("matrix_report_required_passed")
    elif contradictions:
        status = "admission_run_contradicted"
    elif blockers or missing_ack:
        if missing_ack:
            blockers.add("operator_acknowledgements_missing")
        status = "admission_run_blocked_by_operator_review"
    elif review_status == "admission_review_ready" or (review_status == "admission_review_ready_with_warnings" and p.allow_warning_review):
        if p.dry_run_review_only:
            status = "admission_run_accepted_with_warnings" if warnings else "admission_run_accepted"
            summary = "review-only requested; admission controller not invoked"
        else:
            invoke = True
            wing = run_workspace_change_set_admission_wing(dict(request.proposal), artifact_output_path=None)
            s = summarize_workspace_change_set_admission_decision(wing.decision)
            ws_status = str(s["admission_status"])
            blockers |= set(s["blocker_codes"])
            warnings |= set(s["warning_codes"])
            summary = f"workspace admission returned {ws_status}"
            if ws_status in {"admission_accepted", "admission_accepted_with_warnings"}:
                status = "admission_run_accepted_with_warnings" if warnings else "admission_run_accepted"
                next_surface = "workspace_change_set_preflight_may_be_attempted"
            else:
                status = "admission_run_blocked_by_admission"
    elif review_status in {"admission_review_manual_review_required", "admission_review_requires_clarification", "admission_review_blocked"}:
        status = "admission_run_blocked_by_operator_review"
    elif review_status in {"admission_review_contradicted"}:
        status = "admission_run_contradicted"
    elif review_status in {"admission_review_insufficient_evidence"}:
        status = "admission_run_insufficient_evidence"
    else:
        status = "admission_run_blocked_by_policy"; blockers.add("operator_review_not_ready")

    basis = {"work_item_id": work_item_id, "status": status, "review": review.get("admission_review_packet_digest"), "proposal": request.proposal}
    dg = hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    packet = OperatorConfirmedAdmissionRunPacket(
        admission_run_packet_id=f"wiarun_{dg[:16]}", admission_run_packet_digest=dg, work_item_id=work_item_id,
        source_kind=(str(review.get("source_kind") or "") or None), source_ref=(str(review.get("source_ref") or "") or None),
        operator_admission_review_packet_id=str(review.get("admission_review_packet_id") or ""), operator_admission_review_packet_digest=str(review.get("admission_review_packet_digest") or ""), operator_admission_review_status=review_status,
        proposal_id=(str((request.proposal or {}).get("proposal_id") or "") or None), proposal_digest=(str((request.proposal or {}).get("proposal_digest") or "") or None),
        admission_controller_invoked=invoke, workspace_change_set_admission_status=ws_status,
        admission_blocker_codes=tuple(sorted(blockers)), admission_warning_codes=tuple(sorted(warnings)), admission_decision_summary=summary or status,
        operator_acknowledgements=_tuple(review.get("required_operator_acknowledgements")), readiness_summary=tuple(sorted(_tuple(review.get("admission_attempt_preconditions")))),
        evidence_references=tuple(sorted(_tuple(review.get("evidence_artifact_references")))), artifact_references=(), next_eligible_surface=next_surface,
        explicit_non_authority_boundaries=tuple(review.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    decision = OperatorConfirmedAdmissionDecision(status=status, admission_controller_invoked=invoke, workspace_change_set_admission_status=ws_status, blocker_codes=packet.admission_blocker_codes, warning_codes=packet.admission_warning_codes, decision_summary=packet.admission_decision_summary, next_eligible_surface=next_surface)
    return OperatorConfirmedAdmissionResult(status=status, decision=decision, packet=packet)


def write_operator_confirmed_admission_packet(result: OperatorConfirmedAdmissionResult, path: str | Path) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
