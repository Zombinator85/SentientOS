from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES
from sentientos.work_item_lifecycle_completion_dossier import STAGE_ORDER

PASS_STATUSES = {"lifecycle_completion_verification_passed", "lifecycle_completion_verification_passed_with_warnings", "lifecycle_completion_verification_manual_review_required"}

@dataclass(frozen=True)
class WorkItemLifecycleCompletionVerificationPolicy:
    allow_warning_completion: bool = False
    allow_blocked_dossier_review: bool = False
    full_chain_required: bool = False
    matrix_required: bool = False
    artifact_refs_required: bool = False

@dataclass(frozen=True)
class WorkItemLifecycleCompletionVerificationRequest:
    completion_dossier: Mapping[str, Any]
    proposal: Mapping[str, Any] | None = None
    closure_run_packet: Mapping[str, Any] | None = None
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
class WorkItemLifecycleCompletionVerificationFinding:
    finding_id: str
    severity: str
    code: str
    message: str
    evidence_refs: tuple[str, ...]
    stage_id: str | None = None

@dataclass(frozen=True)
class WorkItemLifecycleCompletionVerificationReport:
    verification_report_id: str
    verification_report_digest: str
    completion_dossier_id: str
    completion_dossier_digest: str
    work_item_id: str
    proposal_id: str | None
    proposal_digest: str | None
    verification_status: str
    checked_stage_order: tuple[str, ...]
    supplied_stage_count: int
    missing_stage_evidence: tuple[str, ...]
    digest_alignment_results: Mapping[str, str]
    status_alignment_results: Mapping[str, str]
    work_item_id_alignment_results: Mapping[str, str]
    authority_boundary_results: Mapping[str, str]
    matrix_report_status: str | None
    finding_count: int
    findings: tuple[WorkItemLifecycleCompletionVerificationFinding, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    verified_completion_statement: str | None
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["findings"] = [asdict(f) for f in self.findings]
        return d

@dataclass(frozen=True)
class WorkItemLifecycleCompletionVerificationResult:
    status: str
    report: WorkItemLifecycleCompletionVerificationReport
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "report": self.report.to_dict()}


def _packet(raw: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not raw:
        return {}
    packet = raw.get("packet")
    return dict(packet) if isinstance(packet, Mapping) else dict(raw)


def evaluate_work_item_lifecycle_completion_verification(request: WorkItemLifecycleCompletionVerificationRequest, *, policy: WorkItemLifecycleCompletionVerificationPolicy | None = None) -> WorkItemLifecycleCompletionVerificationResult:
    policy = policy or WorkItemLifecycleCompletionVerificationPolicy()
    dossier = dict(request.completion_dossier)
    findings: list[WorkItemLifecycleCompletionVerificationFinding] = []
    blockers: set[str] = set(); warnings: set[str] = set(); contradictions: set[str] = set()
    did = str(dossier.get("completion_dossier_id") or "")
    ddg = str(dossier.get("completion_dossier_digest") or "")
    w = str(dossier.get("work_item_id") or "")
    ds = str(dossier.get("lifecycle_closure_run_status") or dossier.get("status") or "")
    status = str(dossier.get("status") or "")
    if not did or not ddg:
        blockers.add("dossier_id_digest_required")
    if status == "lifecycle_completion_dossier_complete":
        vstatus = "lifecycle_completion_verification_passed"
    elif status == "lifecycle_completion_dossier_complete_with_warnings" and policy.allow_warning_completion:
        vstatus = "lifecycle_completion_verification_passed_with_warnings"
    elif status.startswith("lifecycle_completion_dossier_contradicted"):
        contradictions.add("dossier_contradicted")
        vstatus = "lifecycle_completion_verification_contradicted"
    elif status.startswith("lifecycle_completion_dossier_blocked") and not policy.allow_blocked_dossier_review:
        blockers.add("dossier_blocked")
        vstatus = "lifecycle_completion_verification_blocked"
    else:
        vstatus = "lifecycle_completion_verification_insufficient_evidence"
    supplied = tuple(str(s.get("stage_id")) for s in dossier.get("stage_summaries", []) if isinstance(s, Mapping) and s.get("supplied"))
    if tuple(s for s in supplied if s in STAGE_ORDER) != supplied:
        contradictions.add("unrecognized_stage_order")
    missing = tuple(s for s in STAGE_ORDER if s not in supplied)
    if policy.full_chain_required and missing:
        blockers.add("full_chain_required")
        vstatus = "lifecycle_completion_verification_insufficient_evidence"
    if policy.matrix_required and str((request.matrix_report or {}).get("status") or dossier.get("matrix_report_status") or "") != "passed":
        blockers.add("matrix_required_passed")
        vstatus = "lifecycle_completion_verification_blocked"
    if policy.artifact_refs_required and not dossier.get("evidence_artifact_references"):
        blockers.add("artifact_refs_required")
        vstatus = "lifecycle_completion_verification_insufficient_evidence"

    stage_map = {"intake": request.intake_packet, "review_packet": request.review_packet, "promotion_gate": request.promotion_dossier, "operator_admission_review": request.operator_admission_review_packet, "admission_run": request.admission_run_packet, "preflight_run": request.preflight_run_packet, "execution_review": request.execution_review_packet, "execution_run": request.execution_run_packet, "verification_run": request.verification_run_packet, "closure_review": request.closure_review_packet, "lifecycle_closure_run": request.closure_run_packet}
    digest_align: dict[str, str] = {}
    status_align: dict[str, str] = {}
    work_align: dict[str, str] = {}
    stage_summaries = {str(s.get("stage_id")): s for s in dossier.get("stage_summaries", []) if isinstance(s, Mapping)}
    for sid, raw in stage_map.items():
        if not raw:
            continue
        pk = _packet(raw)
        sumr = stage_summaries.get(sid, {})
        exp_d = str(sumr.get("packet_digest") or "")
        got_d = str(pk.get("packet_digest") or pk.get(f"{sid}_packet_digest") or "")
        digest_align[sid] = "match" if exp_d and got_d and exp_d == got_d else "unavailable" if not exp_d or not got_d else "mismatch"
        if digest_align[sid] == "mismatch": contradictions.add(f"{sid}_digest_mismatch")
        exp_s = str(sumr.get("status") or "")
        got_s = str(raw.get("status") or pk.get("status") or "")
        status_align[sid] = "match" if exp_s and got_s and exp_s == got_s else "unavailable" if not exp_s or not got_s else "mismatch"
        if status_align[sid] == "mismatch": contradictions.add(f"{sid}_status_mismatch")
        got_w = str(pk.get("work_item_id") or "")
        work_align[sid] = "match" if got_w and w and got_w == w else "unavailable" if not got_w or not w else "mismatch"
        if work_align[sid] == "mismatch": contradictions.add(f"{sid}_work_item_id_mismatch")

    if contradictions:
        vstatus = "lifecycle_completion_verification_contradicted"
    elif blockers and vstatus in PASS_STATUSES:
        vstatus = "lifecycle_completion_verification_blocked"

    codes = [("blocker", c) for c in sorted(blockers)] + [("warning", c) for c in sorted(warnings)] + [("contradiction", c) for c in sorted(contradictions)]
    for i, (sev, code) in enumerate(codes, start=1):
        findings.append(WorkItemLifecycleCompletionVerificationFinding(f"wicv_find_{i:03d}", sev, code, code.replace("_", " "), (did or "missing_dossier",), None))

    payload = {"status": vstatus, "completion_dossier_id": did, "completion_dossier_digest": ddg, "work_item_id": w, "dossier_status": status, "closure_status": ds, "blocker_codes": sorted(blockers), "warning_codes": sorted(warnings), "contradiction_codes": sorted(contradictions)}
    rd = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    report = WorkItemLifecycleCompletionVerificationReport(
        verification_report_id=f"wiclcv_{rd[:16]}", verification_report_digest=rd, completion_dossier_id=did, completion_dossier_digest=ddg, work_item_id=w,
        proposal_id=str((request.proposal or {}).get("proposal_id") or dossier.get("proposal_id") or "") or None, proposal_digest=str((request.proposal or {}).get("proposal_digest") or dossier.get("proposal_digest") or "") or None,
        verification_status=vstatus, checked_stage_order=tuple(s for s in supplied if s in STAGE_ORDER), supplied_stage_count=len(supplied), missing_stage_evidence=missing,
        digest_alignment_results=digest_align, status_alignment_results=status_align, work_item_id_alignment_results=work_align, authority_boundary_results={"authority_level": "metadata_verification_only", "non_authority_boundary_summary": "metadata verification only; no lifecycle or workspace actions", "shell_subprocess_network_provider_prompt": "not_invoked"},
        matrix_report_status=str((request.matrix_report or {}).get("status") or dossier.get("matrix_report_status") or "") or None, finding_count=len(findings), findings=tuple(findings), blocker_codes=tuple(sorted(blockers)), warning_codes=tuple(sorted(warnings)), contradiction_codes=tuple(sorted(contradictions)),
        verified_completion_statement=f"Lifecycle completion dossier for {w} verified as coherent." if vstatus in PASS_STATUSES else None, explicit_non_authority_boundaries=tuple(dossier.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    return WorkItemLifecycleCompletionVerificationResult(status=vstatus, report=report)


def write_work_item_lifecycle_completion_verification_report(result: WorkItemLifecycleCompletionVerificationResult, path: str | Path) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True)+"\n", encoding="utf-8")
