from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES

STAGE_ORDER = (
    "intake","handoff","dry_run_adapter","dry_run_closure","review_packet","promotion_gate","operator_admission_review","admission_run","preflight_run","execution_review","execution_run","verification_run","closure_review","lifecycle_closure_run",
)

@dataclass(frozen=True)
class WorkItemLifecycleCompletionPolicy:
    allow_warning_closure: bool = False
    full_chain_required: bool = False
    matrix_required: bool = False
    artifacts_required: bool = False

@dataclass(frozen=True)
class WorkItemLifecycleCompletionRequest:
    lifecycle_closure_run_packet: Mapping[str, Any]
    proposal: Mapping[str, Any] | None
    closure_review_packet: Mapping[str, Any] | None = None
    verification_run_packet: Mapping[str, Any] | None = None
    execution_run_packet: Mapping[str, Any] | None = None
    execution_review_packet: Mapping[str, Any] | None = None
    preflight_run_packet: Mapping[str, Any] | None = None
    admission_run_packet: Mapping[str, Any] | None = None
    operator_admission_review_packet: Mapping[str, Any] | None = None
    promotion_dossier: Mapping[str, Any] | None = None
    review_packet: Mapping[str, Any] | None = None
    intake_packet: Mapping[str, Any] | None = None
    matrix_report: Mapping[str, Any] | None = None

@dataclass(frozen=True)
class WorkItemLifecycleCompletionStageSummary:
    stage_id: str
    supplied: bool
    status: str | None
    packet_id: str | None
    packet_digest: str | None
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    authority_boundary_notes: tuple[str, ...]

@dataclass(frozen=True)
class WorkItemLifecycleCompletionDossier:
    completion_dossier_id: str
    completion_dossier_digest: str
    work_item_id: str
    source_kind: str | None
    source_ref: str | None
    proposal_id: str | None
    proposal_digest: str | None
    lifecycle_closure_run_packet_id: str
    lifecycle_closure_run_packet_digest: str
    lifecycle_closure_run_status: str
    workspace_change_set_lifecycle_closure_status: str | None
    lifecycle_completed: bool
    lifecycle_completion_recorded: bool
    stage_summaries: tuple[WorkItemLifecycleCompletionStageSummary, ...]
    completed_stage_order: tuple[str, ...]
    missing_stage_evidence: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    authority_claim_summary: str
    non_authority_boundary_summary: str
    evidence_artifact_references: tuple[str, ...]
    artifact_digests: tuple[str, ...]
    matrix_report_status: str | None
    final_operator_acknowledgements: tuple[str, ...]
    final_completion_statement: str | None
    unresolved_risks: tuple[str, ...]
    explicit_non_authority_boundaries: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stage_summaries"] = [asdict(x) for x in self.stage_summaries]
        return d

@dataclass(frozen=True)
class WorkItemLifecycleCompletionResult:
    status: str
    dossier: WorkItemLifecycleCompletionDossier
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "dossier": self.dossier.to_dict()}


def _tuple(v: Any) -> tuple[str, ...]:
    return tuple(str(x) for x in v) if isinstance(v, (list, tuple)) else ()


def _packet(m: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not m:
        return {}
    p = m.get("packet")
    return dict(p) if isinstance(p, Mapping) else dict(m)


def evaluate_work_item_lifecycle_completion_dossier(request: WorkItemLifecycleCompletionRequest, *, policy: WorkItemLifecycleCompletionPolicy | None = None) -> WorkItemLifecycleCompletionResult:
    p = policy or WorkItemLifecycleCompletionPolicy()
    cr = _packet(request.lifecycle_closure_run_packet)
    proposal = dict(request.proposal or {})
    work_item_id = str(cr.get("work_item_id") or proposal.get("work_item_id") or "")
    blockers: set[str] = set(); warnings: set[str] = set(); contradictions: set[str] = set()
    closure_status = str(request.lifecycle_closure_run_packet.get("status") or cr.get("status") or "")
    allowed = {"lifecycle_closure_run_completed"}
    if p.allow_warning_closure:
        allowed.add("lifecycle_closure_run_completed_with_warnings")
    if not proposal:
        blockers.add("proposal_required")
        status = "lifecycle_completion_dossier_insufficient_evidence"
    elif closure_status in {"lifecycle_closure_run_contradicted"}:
        contradictions.add("closure_run_contradicted")
        status = "lifecycle_completion_dossier_contradicted"
    elif closure_status in {"lifecycle_closure_run_insufficient_evidence"}:
        blockers.add("closure_run_insufficient_evidence")
        status = "lifecycle_completion_dossier_insufficient_evidence"
    elif closure_status in {"lifecycle_closure_run_blocked_by_closure", "lifecycle_closure_run_blocked_by_policy", "lifecycle_closure_run_blocked_by_review"}:
        blockers.add("closure_run_blocked")
        status = "lifecycle_completion_dossier_blocked_by_closure"
    elif closure_status not in allowed:
        blockers.add("closure_run_not_completed")
        status = "lifecycle_completion_dossier_failed"
    else:
        status = "lifecycle_completion_dossier_complete_with_warnings" if closure_status.endswith("with_warnings") else "lifecycle_completion_dossier_complete"

    if str(cr.get("lifecycle_closure_wing_invoked") or "").lower() in {"false", "0", ""} and "lifecycle_closure_wing_invoked" in cr:
        blockers.add("lifecycle_closure_wing_not_invoked")
        status = "lifecycle_completion_dossier_blocked_by_closure"
    if work_item_id and proposal.get("work_item_id") and work_item_id != str(proposal.get("work_item_id")):
        contradictions.add("work_item_id_mismatch")
        status = "lifecycle_completion_dossier_contradicted"
    if p.matrix_required and str((request.matrix_report or {}).get("status") or "") != "passed":
        blockers.add("matrix_required_passed")
        status = "lifecycle_completion_dossier_blocked_by_closure"

    stage_map = {
        "intake": request.intake_packet, "handoff": None, "dry_run_adapter": None, "dry_run_closure": None,
        "review_packet": request.review_packet, "promotion_gate": request.promotion_dossier, "operator_admission_review": request.operator_admission_review_packet,
        "admission_run": request.admission_run_packet, "preflight_run": request.preflight_run_packet, "execution_review": request.execution_review_packet,
        "execution_run": request.execution_run_packet, "verification_run": request.verification_run_packet, "closure_review": request.closure_review_packet,
        "lifecycle_closure_run": request.lifecycle_closure_run_packet,
    }
    summaries = []
    missing = []
    for sid in STAGE_ORDER:
        raw = stage_map.get(sid)
        pk = _packet(raw)
        supplied = bool(raw)
        if p.full_chain_required and not supplied:
            missing.append(sid)
        summaries.append(WorkItemLifecycleCompletionStageSummary(sid, supplied, str((raw or {}).get("status") or pk.get("status") or "") or None, str(pk.get(f"{sid}_packet_id") or pk.get("packet_id") or "") or None, str(pk.get(f"{sid}_packet_digest") or pk.get("packet_digest") or "") or None, _tuple(pk.get("blocker_codes")), _tuple(pk.get("warning_codes")), _tuple(pk.get("contradiction_codes")), _tuple(pk.get("artifact_references")), _tuple(pk.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES)))
    if missing:
        blockers.add("full_chain_required")
        if status.startswith("lifecycle_completion_dossier_complete"):
            status = "lifecycle_completion_dossier_insufficient_evidence"

    artifact_refs = _tuple(cr.get("artifact_references"))
    if p.artifacts_required and not artifact_refs:
        blockers.add("artifact_references_required")
        status = "lifecycle_completion_dossier_insufficient_evidence"

    completed_order = tuple(s.stage_id for s in summaries if s.supplied)
    dg = hashlib.sha256(json.dumps({"status": status, "work_item_id": work_item_id, "closure": cr, "proposal": proposal, "matrix": request.matrix_report}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    dossier = WorkItemLifecycleCompletionDossier(
        completion_dossier_id=f"wiclcd_{dg[:16]}", completion_dossier_digest=dg, work_item_id=work_item_id,
        source_kind=(str(cr.get("source_kind") or "") or None), source_ref=(str(cr.get("source_ref") or "") or None), proposal_id=(str(proposal.get("proposal_id") or "") or None), proposal_digest=(str(proposal.get("proposal_digest") or "") or None),
        lifecycle_closure_run_packet_id=str(cr.get("lifecycle_closure_run_packet_id") or ""), lifecycle_closure_run_packet_digest=str(cr.get("lifecycle_closure_run_packet_digest") or ""), lifecycle_closure_run_status=closure_status,
        workspace_change_set_lifecycle_closure_status=(str(cr.get("workspace_change_set_lifecycle_closure_status") or "") or None), lifecycle_completed=status in {"lifecycle_completion_dossier_complete","lifecycle_completion_dossier_complete_with_warnings"}, lifecycle_completion_recorded=status in {"lifecycle_completion_dossier_complete","lifecycle_completion_dossier_complete_with_warnings","lifecycle_completion_dossier_manual_review_required"},
        stage_summaries=tuple(summaries), completed_stage_order=completed_order, missing_stage_evidence=tuple(missing), contradiction_codes=tuple(sorted(contradictions)), blocker_codes=tuple(sorted(blockers)), warning_codes=tuple(sorted(warnings | set(_tuple(cr.get("closure_warning_codes"))))),
        authority_claim_summary="metadata-only completion dossier from supplied lifecycle evidence", non_authority_boundary_summary="no lifecycle invocation, orchestration, execution, verification, rollback, cleanup, or workspace mutation performed", evidence_artifact_references=artifact_refs, artifact_digests=tuple(sorted(set([str(cr.get('lifecycle_closure_run_packet_digest') or ''), str(proposal.get('proposal_digest') or '')]) - {''})), matrix_report_status=(str((request.matrix_report or {}).get("status") or "") or None),
        final_operator_acknowledgements=("operator_confirmed_lifecycle_closure_run_consumed",), final_completion_statement=(f"Work item {work_item_id} lifecycle completion dossier recorded." if status in {"lifecycle_completion_dossier_complete","lifecycle_completion_dossier_complete_with_warnings"} else None), unresolved_risks=tuple(sorted(set(_tuple(cr.get("closure_warning_codes"))))), explicit_non_authority_boundaries=tuple(cr.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    return WorkItemLifecycleCompletionResult(status=status, dossier=dossier)


def write_work_item_lifecycle_completion_dossier(result: WorkItemLifecycleCompletionResult, path: str | Path) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True)+"\n", encoding="utf-8")
