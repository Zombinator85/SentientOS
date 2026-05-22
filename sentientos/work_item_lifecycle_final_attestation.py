from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES
from sentientos.work_item_lifecycle_completion_dossier import STAGE_ORDER

PASS_STATUSES = {
    "lifecycle_final_attestation_sealed",
    "lifecycle_final_attestation_sealed_with_warnings",
    "lifecycle_final_attestation_manual_review_required",
}


@dataclass(frozen=True)
class WorkItemLifecycleFinalAttestationPolicy:
    allow_warnings: bool = False
    allow_blockers_for_review: bool = False
    matrix_required: bool = False
    proof_bundle_required: bool = False
    artifact_refs_required: bool = False


@dataclass(frozen=True)
class WorkItemLifecycleFinalAttestationRequest:
    completion_dossier: Mapping[str, Any]
    verification_report: Mapping[str, Any]
    proposal: Mapping[str, Any] | None = None
    closure_run: Mapping[str, Any] | None = None
    matrix_report: Mapping[str, Any] | None = None
    proof_bundle: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class WorkItemLifecycleFinalAttestationEvidenceSummary:
    evidence_id: str
    evidence_type: str
    supplied: bool
    status: str | None
    digest: str | None
    artifact_refs: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]


@dataclass(frozen=True)
class WorkItemLifecycleFinalAttestationBundle:
    final_attestation_bundle_id: str
    final_attestation_bundle_digest: str
    work_item_id: str
    source_kind: str | None
    source_ref: str | None
    completion_dossier_id: str
    completion_dossier_digest: str
    completion_dossier_status: str
    verification_report_id: str
    verification_report_digest: str
    verification_status: str
    proposal_id: str | None
    proposal_digest: str | None
    lifecycle_completion_statement: str | None
    verified_completion_statement: str | None
    attestation_status: str
    evidence_summaries: tuple[WorkItemLifecycleFinalAttestationEvidenceSummary, ...]
    stage_count: int
    completed_stage_order: tuple[str, ...]
    missing_stage_evidence: tuple[str, ...]
    matrix_report_status: str | None
    proof_bundle_status: str | None
    authority_boundary_summary: str
    non_authority_boundary_summary: str
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    unresolved_risks: tuple[str, ...]
    final_attestation_statement: str | None
    artifact_references: tuple[str, ...]
    artifact_digests: tuple[str, ...]
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_summaries"] = [asdict(s) for s in self.evidence_summaries]
        return data


@dataclass(frozen=True)
class WorkItemLifecycleFinalAttestationResult:
    status: str
    bundle: WorkItemLifecycleFinalAttestationBundle

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "bundle": self.bundle.to_dict()}


def _extract(raw: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    inner = raw.get(name)
    if isinstance(inner, Mapping):
        return dict(inner)
    return dict(raw)


def _codes(raw: Mapping[str, Any], code: str) -> tuple[str, ...]:
    data = raw.get(code)
    if not isinstance(data, list):
        return ()
    return tuple(sorted(str(c) for c in data if c))


def _evidence_summary(kind: str, raw: Mapping[str, Any] | None, *, status_key: str, id_key: str, digest_key: str) -> WorkItemLifecycleFinalAttestationEvidenceSummary:
    packet = dict(raw or {})
    refs = packet.get("artifact_references") or packet.get("evidence_artifact_references") or ()
    ref_tuple = tuple(sorted(str(r) for r in refs if r)) if isinstance(refs, list) else ()
    evidence_id = str(packet.get(id_key) or f"missing_{kind}_id")
    return WorkItemLifecycleFinalAttestationEvidenceSummary(
        evidence_id=evidence_id,
        evidence_type=kind,
        supplied=raw is not None,
        status=str(packet.get(status_key) or "") or None,
        digest=str(packet.get(digest_key) or "") or None,
        artifact_refs=ref_tuple,
        blocker_codes=_codes(packet, "blocker_codes"),
        warning_codes=_codes(packet, "warning_codes"),
        contradiction_codes=_codes(packet, "contradiction_codes"),
    )


def evaluate_work_item_lifecycle_final_attestation(request: WorkItemLifecycleFinalAttestationRequest, *, policy: WorkItemLifecycleFinalAttestationPolicy | None = None) -> WorkItemLifecycleFinalAttestationResult:
    policy = policy or WorkItemLifecycleFinalAttestationPolicy()
    dossier = _extract(request.completion_dossier, "dossier")
    report = _extract(request.verification_report, "report")
    blockers: set[str] = set()
    warnings: set[str] = set()
    contradictions: set[str] = set()

    did = str(dossier.get("completion_dossier_id") or "")
    ddg = str(dossier.get("completion_dossier_digest") or "")
    ds = str(dossier.get("status") or "")
    rid = str(report.get("verification_report_id") or "")
    rdg = str(report.get("verification_report_digest") or "")
    rs = str(report.get("verification_status") or "")
    work_item_id = str(dossier.get("work_item_id") or report.get("work_item_id") or "")
    if not did or not ddg or not rid or not rdg:
        blockers.add("required_id_digest_missing")
    if not work_item_id:
        blockers.add("work_item_id_required")
    if str(dossier.get("work_item_id") or "") != str(report.get("work_item_id") or ""):
        contradictions.add("work_item_id_mismatch")
    if ds != "lifecycle_completion_dossier_complete":
        if ds == "lifecycle_completion_dossier_complete_with_warnings" and policy.allow_warnings:
            warnings.add("completion_dossier_warnings")
        else:
            blockers.add("completion_dossier_not_complete")
    if rs != "lifecycle_completion_verification_passed":
        if rs == "lifecycle_completion_verification_passed_with_warnings" and policy.allow_warnings:
            warnings.add("verification_report_warnings")
        else:
            blockers.add("verification_not_passed")

    for code in _codes(dossier, "blocker_codes") + _codes(report, "blocker_codes"):
        blockers.add(code)
    for code in _codes(dossier, "warning_codes") + _codes(report, "warning_codes"):
        warnings.add(code)
    for code in _codes(dossier, "contradiction_codes") + _codes(report, "contradiction_codes"):
        contradictions.add(code)

    matrix_status = str((request.matrix_report or {}).get("status") or dossier.get("matrix_report_status") or report.get("matrix_report_status") or "") or None
    if policy.matrix_required and matrix_status != "passed":
        blockers.add("matrix_required_not_passed")

    proof_status = str((request.proof_bundle or {}).get("status") or "") or None
    if policy.proof_bundle_required and proof_status not in {"reviewer_proof_bundle_ready", "reviewer_proof_bundle_ready_with_warnings", "passed"}:
        blockers.add("proof_bundle_required_not_passing")

    artifact_refs = tuple(sorted(set(str(r) for r in (dossier.get("evidence_artifact_references") or []) if r)))
    artifact_digests = tuple(sorted(set(str(r) for r in (dossier.get("evidence_artifact_digests") or []) if r)))
    if policy.artifact_refs_required and (not artifact_refs or not artifact_digests):
        blockers.add("artifact_refs_required")

    evidence = (
        _evidence_summary("completion_dossier", dossier, status_key="status", id_key="completion_dossier_id", digest_key="completion_dossier_digest"),
        _evidence_summary("verification_report", report, status_key="verification_status", id_key="verification_report_id", digest_key="verification_report_digest"),
        _evidence_summary("closure_run", request.closure_run, status_key="status", id_key="closure_run_id", digest_key="closure_run_digest"),
        _evidence_summary("proposal", request.proposal, status_key="status", id_key="proposal_id", digest_key="proposal_digest"),
        _evidence_summary("matrix_report", request.matrix_report, status_key="status", id_key="matrix_report_id", digest_key="matrix_report_digest"),
        _evidence_summary("proof_bundle", request.proof_bundle, status_key="status", id_key="bundle_id", digest_key="bundle_digest"),
    )

    stage_order = tuple(str(s) for s in dossier.get("completed_stage_order") or report.get("checked_stage_order") or () if s)
    missing = tuple(str(s) for s in dossier.get("missing_stage_evidence") or report.get("missing_stage_evidence") or () if s)
    stage_count = int(dossier.get("stage_count") or len(stage_order))

    if contradictions:
        status = "lifecycle_final_attestation_contradicted"
    elif blockers and policy.allow_blockers_for_review:
        status = "lifecycle_final_attestation_manual_review_required"
    elif blockers:
        status = "lifecycle_final_attestation_insufficient_evidence" if any(c.endswith("required") or "missing" in c for c in blockers) else "lifecycle_final_attestation_blocked"
    elif warnings and policy.allow_warnings:
        status = "lifecycle_final_attestation_sealed_with_warnings"
    elif warnings:
        status = "lifecycle_final_attestation_manual_review_required"
    else:
        status = "lifecycle_final_attestation_sealed"

    final_statement = f"Final lifecycle attestation for {work_item_id} sealed with deterministic metadata-only evidence." if status in {"lifecycle_final_attestation_sealed", "lifecycle_final_attestation_sealed_with_warnings"} else None
    payload = {"work_item_id": work_item_id, "completion_dossier_digest": ddg, "verification_report_digest": rdg, "status": status, "blocker_codes": sorted(blockers), "warning_codes": sorted(warnings), "contradiction_codes": sorted(contradictions)}
    dg = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    bundle = WorkItemLifecycleFinalAttestationBundle(
        final_attestation_bundle_id=f"wicfa_{dg[:16]}",
        final_attestation_bundle_digest=dg,
        work_item_id=work_item_id,
        source_kind=str(dossier.get("source_kind") or "") or None,
        source_ref=str(dossier.get("source_ref") or "") or None,
        completion_dossier_id=did,
        completion_dossier_digest=ddg,
        completion_dossier_status=ds,
        verification_report_id=rid,
        verification_report_digest=rdg,
        verification_status=rs,
        proposal_id=str((request.proposal or {}).get("proposal_id") or dossier.get("proposal_id") or report.get("proposal_id") or "") or None,
        proposal_digest=str((request.proposal or {}).get("proposal_digest") or dossier.get("proposal_digest") or report.get("proposal_digest") or "") or None,
        lifecycle_completion_statement=str(dossier.get("lifecycle_completion_statement") or "") or None,
        verified_completion_statement=str(report.get("verified_completion_statement") or "") or None,
        attestation_status=status,
        evidence_summaries=evidence,
        stage_count=stage_count,
        completed_stage_order=stage_order,
        missing_stage_evidence=missing,
        matrix_report_status=matrix_status,
        proof_bundle_status=proof_status,
        authority_boundary_summary="metadata_attestation_only",
        non_authority_boundary_summary="final attestation metadata only; no lifecycle actions, workspace mutation, or runtime authority",
        blocker_codes=tuple(sorted(blockers)),
        warning_codes=tuple(sorted(warnings)),
        contradiction_codes=tuple(sorted(contradictions)),
        unresolved_risks=tuple(sorted(set(sorted(blockers) + sorted(contradictions)))),
        final_attestation_statement=final_statement,
        artifact_references=artifact_refs,
        artifact_digests=artifact_digests,
        explicit_non_authority_boundaries=tuple(dossier.get("explicit_non_authority_boundaries") or report.get("explicit_non_authority_boundaries") or EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    return WorkItemLifecycleFinalAttestationResult(status=status, bundle=bundle)


def write_work_item_lifecycle_final_attestation_bundle(result: WorkItemLifecycleFinalAttestationResult, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
