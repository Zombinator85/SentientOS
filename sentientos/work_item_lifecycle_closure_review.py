from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES


@dataclass(frozen=True)
class OperatorLifecycleClosureReviewPolicy:
    allow_warning_verification: bool = False
    matrix_required: bool = False
    artifacts_required: bool = False


@dataclass(frozen=True)
class OperatorLifecycleClosureReviewRequest:
    verification_run_packet: Mapping[str, Any]
    proposal: Mapping[str, Any] | None
    execution_run_packet: Mapping[str, Any] | None = None
    preflight_run_packet: Mapping[str, Any] | None = None
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class OperatorLifecycleClosureReviewChecklistItem:
    id: str
    status: str
    reason: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperatorLifecycleClosureReviewPacket:
    closure_review_packet_id: str
    closure_review_packet_digest: str
    work_item_id: str
    source_kind: str | None
    source_ref: str | None
    verification_run_packet_id: str
    verification_run_packet_digest: str
    verification_run_status: str
    workspace_change_set_verification_status: str | None
    proposal_id: str | None
    proposal_digest: str | None
    operation_types: tuple[str, ...]
    verified_paths_summary: tuple[str, ...]
    affected_paths_summary: tuple[str, ...]
    verification_blockers: tuple[str, ...]
    verification_warnings: tuple[str, ...]
    closure_attempt_preconditions: tuple[str, ...]
    closure_attempt_blockers: tuple[str, ...]
    closure_attempt_warnings: tuple[str, ...]
    operator_acknowledgements: tuple[str, ...]
    operator_checklist: tuple[OperatorLifecycleClosureReviewChecklistItem, ...]
    evidence_references: tuple[str, ...]
    artifact_references: tuple[str, ...]
    candidate_manual_closure_command: str | None
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["operator_checklist"] = [asdict(i) for i in self.operator_checklist]
        return d


@dataclass(frozen=True)
class OperatorLifecycleClosureReviewResult:
    status: str
    packet: OperatorLifecycleClosureReviewPacket

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict()}


def _tuple(v: Any) -> tuple[str, ...]:
    return tuple(str(x) for x in v) if isinstance(v, (list, tuple)) else ()


def evaluate_operator_lifecycle_closure_review(request: OperatorLifecycleClosureReviewRequest, *, policy: OperatorLifecycleClosureReviewPolicy | None = None) -> OperatorLifecycleClosureReviewResult:
    p = policy or OperatorLifecycleClosureReviewPolicy()
    vr = dict(request.verification_run_packet.get("packet", request.verification_run_packet))
    st = str(request.verification_run_packet.get("status") or vr.get("verification_run_status") or "")
    proposal = request.proposal or {}
    blockers, warnings = set(_tuple(vr.get("verification_blocker_codes"))), set(_tuple(vr.get("verification_warning_codes")))
    work_item_id = str(vr.get("work_item_id") or proposal.get("work_item_id") or "")
    matrix_status = str((request.matrix_report or {}).get("status") or "")
    verification_invoked = bool(vr.get("verification_controller_invoked"))

    operation_types = tuple(sorted({str(t.get("operation")) for t in proposal.get("proposed_targets", ()) if t.get("operation")}))
    affected_paths = tuple(sorted(str(t.get("relative_target_path")) for t in proposal.get("proposed_targets", ()) if t.get("relative_target_path")))
    verified_paths = _tuple(vr.get("verified_paths_summary"))

    if request.proposal is None:
        status = "closure_review_insufficient_evidence"; blockers.add("proposal_required")
    elif str(vr.get("work_item_id") or "") and str(proposal.get("work_item_id") or "") and str(vr.get("work_item_id")) != str(proposal.get("work_item_id")):
        status = "closure_review_contradicted"; blockers.add("work_item_id_mismatch")
    elif request.execution_run_packet and str((request.execution_run_packet.get("packet", request.execution_run_packet)).get("work_item_id") or "") and str((request.execution_run_packet.get("packet", request.execution_run_packet)).get("work_item_id")) != work_item_id:
        status = "closure_review_contradicted"; blockers.add("execution_work_item_id_mismatch")
    elif not verification_invoked:
        status = "closure_review_blocked_by_policy"; blockers.add("verification_controller_not_invoked")
    elif p.matrix_required and matrix_status != "passed":
        status = "closure_review_blocked_by_policy"; blockers.add("matrix_report_required_passed")
    elif p.artifacts_required and not _tuple(vr.get("artifact_references")):
        status = "closure_review_insufficient_evidence"; blockers.add("artifact_references_required")
    elif st == "verification_run_passed":
        status = "closure_review_ready"
    elif st == "verification_run_passed_with_warnings" and p.allow_warning_verification:
        status = "closure_review_ready_with_warnings"; warnings.add("verification_warnings_present")
    elif st == "verification_run_passed_with_warnings":
        status = "closure_review_manual_review_required"; blockers.add("warning_verification_requires_manual_review")
    elif st in {"verification_run_blocked_by_verification", "verification_run_failed"}:
        status = "closure_review_blocked_by_verification"
    elif st == "verification_run_contradicted":
        status = "closure_review_contradicted"
    elif st == "verification_run_insufficient_evidence":
        status = "closure_review_insufficient_evidence"
    else:
        status = "closure_review_failed"; blockers.add("verification_status_not_eligible")

    cmd = None
    if status in {"closure_review_ready", "closure_review_ready_with_warnings"}:
        cmd = "manual_operator_command_candidate: python scripts/build_workspace_change_set_lifecycle_closure.py --proposal <proposal.json> --summary (not authorization)"

    checklist_ids = [
        "review_original_work_item_scope","review_execution_run_receipt","review_verification_run_receipt","review_verified_paths_summary",
        "review_operation_types","review_verification_blockers_and_warnings","confirm_no_unresolved_verification_failures","confirm_no_agent_execution",
        "confirm_no_network_provider_prompt_authority","confirm_no_branch_pr_issue_mutation","confirm_artifact_digests_match",
        "confirm_matrix_report_current","manually_run_lifecycle_closure_only_if_appropriate",
    ]
    checklist = []
    for cid in checklist_ids:
        cst, reason = "required", "operator review required"
        if cid == "confirm_no_unresolved_verification_failures":
            cst, reason = (("satisfied", "verification run is closure-review eligible") if status in {"closure_review_ready", "closure_review_ready_with_warnings", "closure_review_manual_review_required"} else ("blocked", "verification not closure-review eligible"))
        elif cid == "review_verification_blockers_and_warnings" and warnings:
            cst, reason = "warning", "verification blockers/warnings carried forward"
        elif cid == "confirm_artifact_digests_match" and p.artifacts_required and not _tuple(vr.get("artifact_references")):
            cst, reason = "blocked", "artifact references required"
        elif cid == "confirm_matrix_report_current" and p.matrix_required:
            cst, reason = (("satisfied", "matrix report passed") if matrix_status == "passed" else ("blocked", "matrix report missing or failing"))
        checklist.append(OperatorLifecycleClosureReviewChecklistItem(id=cid, status=cst, reason=reason, evidence_refs=("verification_run_packet", "proposal")))

    basis = {"work_item_id": work_item_id, "status": status, "verification": vr.get("verification_run_packet_digest"), "proposal": proposal}
    dg = hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    packet = OperatorLifecycleClosureReviewPacket(
        closure_review_packet_id=f"wclr_{dg[:16]}", closure_review_packet_digest=dg, work_item_id=work_item_id,
        source_kind=(str(vr.get("source_kind") or "") or None), source_ref=(str(vr.get("source_ref") or "") or None),
        verification_run_packet_id=str(vr.get("verification_run_packet_id") or ""), verification_run_packet_digest=str(vr.get("verification_run_packet_digest") or ""),
        verification_run_status=st, workspace_change_set_verification_status=(str(vr.get("workspace_change_set_verification_status") or "") or None),
        proposal_id=(str(proposal.get("proposal_id") or "") or None), proposal_digest=(str(proposal.get("proposal_digest") or "") or None),
        operation_types=operation_types, verified_paths_summary=verified_paths, affected_paths_summary=affected_paths,
        verification_blockers=_tuple(vr.get("verification_blocker_codes")), verification_warnings=tuple(sorted(warnings)),
        closure_attempt_preconditions=("human_operator_review_required", "verification_packet_accepted"), closure_attempt_blockers=tuple(sorted(blockers)), closure_attempt_warnings=tuple(sorted(warnings)),
        operator_acknowledgements=_tuple(vr.get("operator_acknowledgements")), operator_checklist=tuple(checklist),
        evidence_references=tuple(sorted(set(_tuple(vr.get("evidence_references"))) | {"verification_run_packet", "proposal"})),
        artifact_references=_tuple(vr.get("artifact_references")), candidate_manual_closure_command=cmd,
        explicit_non_authority_boundaries=tuple(vr.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    return OperatorLifecycleClosureReviewResult(status=status, packet=packet)


def write_operator_lifecycle_closure_review_packet(result: OperatorLifecycleClosureReviewResult, path: str | Path) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
