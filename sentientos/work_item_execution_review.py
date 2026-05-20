from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES


@dataclass(frozen=True)
class OperatorExecutionReviewPolicy:
    allow_warning_preflight: bool = False
    matrix_required: bool = False
    artifacts_required: bool = False
    review_only: bool = False


@dataclass(frozen=True)
class OperatorExecutionReviewRequest:
    preflight_run_packet: Mapping[str, Any]
    proposal: Mapping[str, Any] | None
    admission_run_packet: Mapping[str, Any] | None = None
    operator_review_packet: Mapping[str, Any] | None = None
    promotion_dossier: Mapping[str, Any] | None = None
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class OperatorExecutionReviewChecklistItem:
    id: str
    status: str
    reason: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperatorExecutionReviewPacket:
    execution_review_packet_id: str
    execution_review_packet_digest: str
    work_item_id: str
    source_kind: str | None
    source_ref: str | None
    preflight_run_packet_id: str
    preflight_run_packet_digest: str
    preflight_run_status: str
    workspace_change_set_preflight_status: str | None
    transaction_plan_ready: bool
    proposal_id: str | None
    proposal_digest: str | None
    target_count: int
    operation_types: tuple[str, ...]
    proposed_paths_summary: tuple[str, ...]
    preflight_blockers: tuple[str, ...]
    preflight_warnings: tuple[str, ...]
    execution_attempt_preconditions: tuple[str, ...]
    execution_attempt_blockers: tuple[str, ...]
    execution_attempt_warnings: tuple[str, ...]
    rollback_review_requirements: tuple[str, ...]
    operator_acknowledgements: tuple[str, ...]
    operator_checklist: tuple[OperatorExecutionReviewChecklistItem, ...]
    evidence_references: tuple[str, ...]
    artifact_references: tuple[str, ...]
    candidate_manual_execution_command: str | None
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["operator_checklist"] = [asdict(i) for i in self.operator_checklist]
        return d


@dataclass(frozen=True)
class OperatorExecutionReviewResult:
    status: str
    packet: OperatorExecutionReviewPacket

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict()}


def _tuple(v: Any) -> tuple[str, ...]:
    return tuple(str(x) for x in v) if isinstance(v, (list, tuple)) else ()


def evaluate_operator_execution_review(request: OperatorExecutionReviewRequest, *, policy: OperatorExecutionReviewPolicy | None = None) -> OperatorExecutionReviewResult:
    p = policy or OperatorExecutionReviewPolicy()
    pr = dict(request.preflight_run_packet.get("packet", request.preflight_run_packet))
    st = str(request.preflight_run_packet.get("status") or pr.get("preflight_run_status") or "")
    proposal = request.proposal or {}
    blockers, warnings = set(), set(_tuple(pr.get("preflight_warning_codes")))
    work_item_id = str(pr.get("work_item_id") or proposal.get("work_item_id") or "")
    tx_ready = bool(pr.get("transaction_plan_ready"))
    target_count = int(pr.get("target_count") or proposal.get("declared_target_count") or len(proposal.get("proposed_targets", ())))
    operation_types = tuple(sorted({str(t.get("operation")) for t in proposal.get("proposed_targets", ()) if t.get("operation")}))
    path_summary = tuple(sorted(str(t.get("relative_target_path")) for t in proposal.get("proposed_targets", ()) if t.get("relative_target_path")))
    matrix_status = str((request.matrix_report or {}).get("status") or "")

    status = "execution_review_failed"
    if request.proposal is None:
        status = "execution_review_insufficient_evidence"; blockers.add("proposal_required")
    elif str(pr.get("work_item_id") or "") and str(proposal.get("work_item_id") or "") and str(pr.get("work_item_id")) != str(proposal.get("work_item_id")):
        status = "execution_review_contradicted"; blockers.add("work_item_id_mismatch")
    elif not bool(pr.get("preflight_controller_invoked")) and not p.review_only:
        status = "execution_review_blocked_by_policy"; blockers.add("preflight_controller_not_invoked")
    elif not tx_ready:
        status = "execution_review_blocked_by_preflight"; blockers.add("transaction_plan_not_ready")
    elif p.matrix_required and matrix_status != "passed":
        status = "execution_review_blocked_by_policy"; blockers.add("matrix_report_required_passed")
    elif p.artifacts_required and not _tuple(pr.get("artifact_references")):
        status = "execution_review_insufficient_evidence"; blockers.add("artifact_references_required")
    elif st == "preflight_run_ready":
        status = "execution_review_ready"
    elif st == "preflight_run_ready_with_warnings" and p.allow_warning_preflight:
        status = "execution_review_ready_with_warnings"; warnings.add("preflight_warnings_present")
    elif st == "preflight_run_ready_with_warnings":
        status = "execution_review_manual_review_required"; blockers.add("warning_preflight_requires_manual_review")
    elif st in {"preflight_run_blocked_by_preflight", "preflight_run_blocked_by_admission"}:
        status = "execution_review_blocked_by_preflight"; blockers |= set(_tuple(pr.get("preflight_blocker_codes")))
    elif st in {"preflight_run_contradicted"}:
        status = "execution_review_contradicted"
    elif st in {"preflight_run_insufficient_evidence"}:
        status = "execution_review_insufficient_evidence"
    else:
        status = "execution_review_blocked_by_policy"; blockers.add("preflight_not_ready")

    cmd = None
    if status in {"execution_review_ready", "execution_review_ready_with_warnings"}:
        cmd = "python scripts/run_workspace_change_set_transaction.py --proposal <proposal.json> --workspace-root <path> --summary"

    checklist_ids = [
        "review_original_work_item_scope","review_admission_run_receipt","review_preflight_run_receipt","review_transaction_plan_readiness",
        "review_declared_workspace_targets","review_operation_types","review_proposed_paths_summary","review_preflight_blockers_and_warnings",
        "confirm_no_agent_execution","confirm_no_network_provider_prompt_authority","confirm_no_branch_pr_issue_mutation",
        "confirm_workspace_root_is_expected","confirm_rollback_policy_before_execution","confirm_artifact_digests_match",
        "confirm_matrix_report_current","manually_run_workspace_execution_only_if_appropriate",
    ]
    checklist = []
    for cid in checklist_ids:
        cst, reason = "required", "operator review required"
        if cid == "review_transaction_plan_readiness":
            cst, reason = ("satisfied", "transaction plan is ready") if tx_ready else ("blocked", "transaction plan not ready")
        elif cid == "review_preflight_blockers_and_warnings" and warnings:
            cst, reason = "warning", "preflight warnings carried forward"
        elif cid == "confirm_artifact_digests_match" and p.artifacts_required and not _tuple(pr.get("artifact_references")):
            cst, reason = "blocked", "artifact references required"
        elif cid == "confirm_matrix_report_current" and p.matrix_required:
            cst, reason = (("satisfied", "matrix report passed") if matrix_status == "passed" else ("blocked", "matrix report missing or failing"))
        checklist.append(OperatorExecutionReviewChecklistItem(id=cid, status=cst, reason=reason, evidence_refs=("preflight_run_packet",)))

    basis = {"work_item_id": work_item_id, "status": status, "preflight": pr.get("preflight_run_packet_digest"), "proposal": proposal}
    dg = hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    packet = OperatorExecutionReviewPacket(
        execution_review_packet_id=f"wier_{dg[:16]}", execution_review_packet_digest=dg,
        work_item_id=work_item_id, source_kind=(str(pr.get("source_kind") or "") or None), source_ref=(str(pr.get("source_ref") or "") or None),
        preflight_run_packet_id=str(pr.get("preflight_run_packet_id") or ""), preflight_run_packet_digest=str(pr.get("preflight_run_packet_digest") or ""), preflight_run_status=st,
        workspace_change_set_preflight_status=(str(pr.get("workspace_change_set_preflight_status") or "") or None), transaction_plan_ready=tx_ready,
        proposal_id=(str(proposal.get("proposal_id") or "") or None), proposal_digest=(str(proposal.get("proposal_digest") or "") or None), target_count=target_count,
        operation_types=operation_types, proposed_paths_summary=path_summary, preflight_blockers=_tuple(pr.get("preflight_blocker_codes")), preflight_warnings=tuple(sorted(warnings)),
        execution_attempt_preconditions=("human_operator_review_required", "preflight_packet_accepted"), execution_attempt_blockers=tuple(sorted(blockers)), execution_attempt_warnings=tuple(sorted(warnings)),
        rollback_review_requirements=("review_rollback_policy_before_execution",), operator_acknowledgements=_tuple(pr.get("operator_acknowledgements")), operator_checklist=tuple(checklist),
        evidence_references=tuple(sorted(set(_tuple(pr.get("evidence_references"))) | {"preflight_run_packet", "proposal"})), artifact_references=_tuple(pr.get("artifact_references")),
        candidate_manual_execution_command=cmd, explicit_non_authority_boundaries=tuple(pr.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES)
    )
    return OperatorExecutionReviewResult(status=status, packet=packet)


def write_operator_execution_review_packet(result: OperatorExecutionReviewResult, path: str | Path) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
