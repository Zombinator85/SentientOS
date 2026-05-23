from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES

PASS_STATUSES = {
    "lifecycle_attestation_review_digest_index_verification_passed",
    "lifecycle_attestation_review_digest_index_verification_passed_with_warnings",
    "lifecycle_attestation_review_digest_index_verification_manual_review_required",
}


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestIndexVerificationPolicy:
    allow_warning_index: bool = False
    allow_attention_index_review: bool = False
    allow_blocked_index_review: bool = False
    source_digests_required: bool = False
    verifier_reports_required: bool = False
    matrix_required: bool = False


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestIndexVerificationRequest:
    review_digest_index: Mapping[str, Any]
    review_digests: tuple[tuple[str, Mapping[str, Any]], ...] = ()
    review_digest_verifier_reports: tuple[tuple[str, Mapping[str, Any]], ...] = ()
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestIndexVerificationFinding:
    finding_id: str
    severity: str
    code: str
    message: str
    evidence_refs: tuple[str, ...]
    entry_id: str | None = None
    review_digest_id: str | None = None
    work_item_id: str | None = None


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestIndexVerificationReport:
    review_digest_index_verification_report_id: str
    review_digest_index_verification_report_digest: str
    review_digest_index_id: str
    review_digest_index_digest: str
    verification_status: str
    indexed_count: int
    supplied_digest_count: int
    supplied_verifier_report_count: int
    checked_entry_count: int
    checked_digest_count: int
    checked_verifier_report_count: int
    digest_alignment_results: tuple[str, ...]
    verifier_report_alignment_results: tuple[str, ...]
    duplicate_detection_results: tuple[str, ...]
    skipped_input_results: tuple[str, ...]
    attention_required_results: tuple[str, ...]
    aggregate_reviewer_posture_alignment: str
    deterministic_order_results: tuple[str, ...]
    matrix_report_status: str | None
    finding_count: int
    findings: tuple[WorkItemLifecycleAttestationReviewDigestIndexVerificationFinding, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    verified_review_digest_index_statement: str | None
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = [asdict(f) for f in self.findings]
        return data


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestIndexVerificationResult:
    status: str
    report: WorkItemLifecycleAttestationReviewDigestIndexVerificationReport

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "report": self.report.to_dict()}


def _extract(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    inner = raw.get(key)
    return dict(inner) if isinstance(inner, Mapping) else dict(raw)


def evaluate_work_item_lifecycle_attestation_review_digest_index_verification(request: WorkItemLifecycleAttestationReviewDigestIndexVerificationRequest, *, policy: WorkItemLifecycleAttestationReviewDigestIndexVerificationPolicy | None = None) -> WorkItemLifecycleAttestationReviewDigestIndexVerificationResult:
    policy = policy or WorkItemLifecycleAttestationReviewDigestIndexVerificationPolicy()
    index = _extract(request.review_digest_index, "index")
    blockers: set[str] = set()
    warnings: set[str] = set()
    contradictions: set[str] = set()
    findings: list[WorkItemLifecycleAttestationReviewDigestIndexVerificationFinding] = []

    def add(sev: str, code: str, msg: str, refs: tuple[str, ...] = (), entry_id: str | None = None, review_digest_id: str | None = None) -> None:
        fid = hashlib.sha256(f"{sev}|{code}|{msg}|{entry_id or ''}|{review_digest_id or ''}|{'|'.join(refs)}".encode()).hexdigest()[:16]
        findings.append(WorkItemLifecycleAttestationReviewDigestIndexVerificationFinding(f"wiardixv_{fid}", sev, code, msg, refs, entry_id, review_digest_id, None))

    idx_id = str(index.get("review_digest_index_id") or "")
    idx_digest = str(index.get("review_digest_index_digest") or "")
    idx_status = str(index.get("index_status") or "")
    entries = tuple(e for e in index.get("entries") or () if isinstance(e, Mapping))

    if not idx_id or not idx_digest:
        blockers.add("review_digest_index_id_digest_required")
    if int(index.get("indexed_count") or 0) != len(entries):
        contradictions.add("indexed_count_mismatch")
    dup_keys = tuple(sorted(str(v) for v in (index.get("duplicate_keys") or ()) if v))
    if int(index.get("duplicate_count") or 0) != len(dup_keys):
        contradictions.add("duplicate_count_mismatch")
    skipped = tuple(sorted(str(v) for v in (index.get("skipped_inputs") or ()) if v))
    if int(index.get("skipped_count") or 0) != len(skipped):
        contradictions.add("skipped_count_mismatch")

    expected_order = sorted(entries, key=lambda e: f"{str(e.get('sort_key') or '')}|{str(e.get('entry_id') or '')}")
    order_results = ("entry_order_verified",) if list(entries) == expected_order else ("entry_order_mismatch",)
    if order_results[0] == "entry_order_mismatch":
        contradictions.add("non_deterministic_entry_order")

    digest_map: dict[str, Mapping[str, Any]] = {}
    for src, raw in sorted(request.review_digests, key=lambda x: x[0]):
        d = _extract(raw, "digest")
        did = str(d.get("review_digest_id") or "")
        ddg = str(d.get("review_digest_digest") or "")
        if did:
            digest_map[f"id:{did}"] = d
        if ddg:
            digest_map[f"digest:{ddg}"] = d

    vr_map: dict[str, Mapping[str, Any]] = {}
    for src, raw in sorted(request.review_digest_verifier_reports, key=lambda x: x[0]):
        r = _extract(raw, "report")
        rid = str(r.get("review_digest_id") or "")
        rdg = str(r.get("review_digest_digest") or "")
        if rid:
            vr_map[f"id:{rid}"] = r
        if rdg:
            vr_map[f"digest:{rdg}"] = r

    digest_results: list[str] = []
    vr_results: list[str] = []
    attn_results: list[str] = []
    checked_digest_count = checked_verifier_count = 0
    derived_posture = "reviewer_can_accept_all"
    has_attention = False
    has_warning = False
    has_block = False
    has_contra = False

    for entry in entries:
        did = str(entry.get("review_digest_id") or "")
        ddg = str(entry.get("review_digest_digest") or "")
        eid = str(entry.get("entry_id") or "") or None
        expected_attention = bool(entry.get("attention_required_count") or entry.get("warning_codes") or entry.get("blocker_codes") or entry.get("contradiction_codes") or str(entry.get("digest_status") or "") != "lifecycle_attestation_review_digest_clear")
        if bool(entry.get("attention_required")) != expected_attention:
            contradictions.add("attention_required_mismatch")
            attn_results.append("attention_required_mismatch")
        digest_rec = digest_map.get(f"id:{did}") or digest_map.get(f"digest:{ddg}")
        if digest_rec is not None:
            checked_digest_count += 1
            if did and str(digest_rec.get("review_digest_id") or "") != did:
                contradictions.add("review_digest_id_mismatch")
            if ddg and str(digest_rec.get("review_digest_digest") or "") != ddg:
                contradictions.add("review_digest_digest_mismatch")
            digest_results.append("digest_aligned")
        v = vr_map.get(f"id:{did}") or vr_map.get(f"digest:{ddg}")
        if v is not None:
            checked_verifier_count += 1
            if did and str(v.get("review_digest_id") or "") != did:
                contradictions.add("review_digest_verifier_id_mismatch")
            if ddg and str(v.get("review_digest_digest") or "") != ddg:
                contradictions.add("review_digest_verifier_digest_mismatch")
            vr_results.append("verifier_report_aligned")

        has_attention = has_attention or bool(entry.get("attention_required"))
        has_warning = has_warning or bool(entry.get("warning_codes"))
        has_block = has_block or bool(entry.get("blocker_codes"))
        has_contra = has_contra or bool(entry.get("contradiction_codes"))

    if policy.source_digests_required and not request.review_digests:
        blockers.add("source_digests_required")
    if policy.source_digests_required and checked_digest_count != len(entries):
        blockers.add("source_digests_coverage_incomplete")
    if policy.verifier_reports_required and not request.review_digest_verifier_reports:
        blockers.add("verifier_reports_required")
    if policy.verifier_reports_required and checked_verifier_count != len(entries):
        blockers.add("verifier_reports_coverage_incomplete")

    expected_posture = "reviewer_can_accept_all"
    if has_contra:
        expected_posture = "reviewer_must_resolve_contradictions"
    elif has_block:
        expected_posture = "reviewer_must_block"
    elif has_attention:
        expected_posture = "reviewer_should_review_attention_items"
    elif has_warning:
        expected_posture = "reviewer_can_accept_with_warnings"
    posture_alignment = "aggregate_reviewer_posture_aligned"
    if str(index.get("aggregate_reviewer_posture") or "") != expected_posture:
        contradictions.add("aggregate_reviewer_posture_mismatch")
        posture_alignment = "aggregate_reviewer_posture_mismatch"

    if idx_status == "lifecycle_attestation_review_digest_index_ready":
        pass
    elif idx_status == "lifecycle_attestation_review_digest_index_ready_with_warnings" and policy.allow_warning_index:
        warnings.add("warning_index_allowed")
    elif idx_status == "lifecycle_attestation_review_digest_index_attention_required" and policy.allow_attention_index_review:
        blockers.add("attention_index_requires_manual_review")
    elif idx_status == "lifecycle_attestation_review_digest_index_blocked":
        blockers.add("index_blocked")
    elif idx_status == "lifecycle_attestation_review_digest_index_contradicted":
        contradictions.add("index_contradicted")
    elif idx_status == "lifecycle_attestation_review_digest_index_insufficient_evidence":
        blockers.add("index_insufficient_evidence")
    else:
        blockers.add("index_status_not_acceptable")

    matrix_status = str((request.matrix_report or {}).get("status") or index.get("matrix_report_status") or "") or None
    if policy.matrix_required and matrix_status != "passed":
        blockers.add("matrix_required_not_passed")

    blocker_codes = tuple(sorted(set(blockers).union(str(v) for v in (index.get("blocker_codes") or ()) if v)))
    warning_codes = tuple(sorted(set(warnings).union(str(v) for v in (index.get("warning_codes") or ()) if v)))
    contradiction_codes = tuple(sorted(set(contradictions).union(str(v) for v in (index.get("contradiction_codes") or ()) if v)))

    if contradiction_codes:
        status = "lifecycle_attestation_review_digest_index_verification_contradicted"
    elif blocker_codes and policy.allow_blocked_index_review and ("index_blocked" in blocker_codes or "attention_index_requires_manual_review" in blocker_codes):
        status = "lifecycle_attestation_review_digest_index_verification_manual_review_required"
    elif blocker_codes:
        status = "lifecycle_attestation_review_digest_index_verification_insufficient_evidence" if any("required" in c or "insufficient" in c for c in blocker_codes) else "lifecycle_attestation_review_digest_index_verification_blocked"
    elif warning_codes:
        status = "lifecycle_attestation_review_digest_index_verification_passed_with_warnings"
    elif idx_id and idx_digest:
        status = "lifecycle_attestation_review_digest_index_verification_passed"
    else:
        status = "lifecycle_attestation_review_digest_index_verification_failed"

    findings_out = tuple(sorted(findings, key=lambda f: (f.severity, f.code, f.finding_id)))
    payload = {"status": status, "id": idx_id, "digest": idx_digest, "blockers": blocker_codes, "warnings": warning_codes, "contradictions": contradiction_codes}
    dg = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    report = WorkItemLifecycleAttestationReviewDigestIndexVerificationReport(
        review_digest_index_verification_report_id=f"wiardixv_{dg[:16]}",
        review_digest_index_verification_report_digest=dg,
        review_digest_index_id=idx_id,
        review_digest_index_digest=idx_digest,
        verification_status=status,
        indexed_count=int(index.get("indexed_count") or 0),
        supplied_digest_count=len(request.review_digests),
        supplied_verifier_report_count=len(request.review_digest_verifier_reports),
        checked_entry_count=len(entries),
        checked_digest_count=checked_digest_count,
        checked_verifier_report_count=checked_verifier_count,
        digest_alignment_results=tuple(sorted(set(digest_results) or {"no_source_digest_checks_performed"})),
        verifier_report_alignment_results=tuple(sorted(set(vr_results) or {"no_verifier_report_checks_performed"})),
        duplicate_detection_results=("duplicate_structure_verified" if int(index.get("duplicate_count") or 0) == len(dup_keys) else "duplicate_structure_mismatch",),
        skipped_input_results=("skipped_structure_verified" if int(index.get("skipped_count") or 0) == len(skipped) else "skipped_structure_mismatch",),
        attention_required_results=tuple(sorted(set(attn_results) or {"attention_required_flags_verified"})),
        aggregate_reviewer_posture_alignment=posture_alignment,
        deterministic_order_results=order_results,
        matrix_report_status=matrix_status,
        finding_count=len(findings_out),
        findings=findings_out,
        blocker_codes=blocker_codes,
        warning_codes=warning_codes,
        contradiction_codes=contradiction_codes,
        verified_review_digest_index_statement=(f"Lifecycle attestation review digest index {idx_id} verified as metadata-only and internally coherent." if status in PASS_STATUSES else None),
        explicit_non_authority_boundaries=tuple(EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    return WorkItemLifecycleAttestationReviewDigestIndexVerificationResult(status=status, report=report)


def write_work_item_lifecycle_attestation_review_digest_index_verification_report(result: WorkItemLifecycleAttestationReviewDigestIndexVerificationResult, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
