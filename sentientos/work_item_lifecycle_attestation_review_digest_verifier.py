from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES

PASS_STATUSES = {
    "lifecycle_attestation_review_digest_verification_passed",
    "lifecycle_attestation_review_digest_verification_passed_with_warnings",
    "lifecycle_attestation_review_digest_verification_manual_review_required",
}


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestVerificationPolicy:
    allow_warnings: bool = False
    allow_blockers_for_review: bool = False
    matrix_required: bool = False


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestVerificationRequest:
    review_digest: Mapping[str, Any]
    attestation_index: Mapping[str, Any]
    index_verification_report: Mapping[str, Any]
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestVerificationFinding:
    finding_id: str
    severity: str
    code: str
    message: str
    evidence_refs: tuple[str, ...]
    entry_id: str | None = None
    work_item_id: str | None = None


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestVerificationReport:
    review_digest_verification_report_id: str
    review_digest_verification_report_digest: str
    review_digest_id: str
    review_digest_digest: str
    attestation_index_id: str
    attestation_index_digest: str
    index_verification_report_id: str
    index_verification_report_digest: str
    verification_status: str
    work_item_count_alignment: str
    sealed_count_alignment: str
    attention_required_count_alignment: str
    blocker_count_alignment: str
    warning_count_alignment: str
    contradiction_count_alignment: str
    reviewer_posture_alignment: str
    entry_alignment_results: tuple[str, ...]
    matrix_report_status: str | None
    finding_count: int
    findings: tuple[WorkItemLifecycleAttestationReviewDigestVerificationFinding, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    verified_review_digest_statement: str | None
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = [asdict(f) for f in self.findings]
        return data


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestVerificationResult:
    status: str
    report: WorkItemLifecycleAttestationReviewDigestVerificationReport

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "report": self.report.to_dict()}


def _extract(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    inner = raw.get(key)
    return dict(inner) if isinstance(inner, Mapping) else dict(raw)


def evaluate_work_item_lifecycle_attestation_review_digest_verification(request: WorkItemLifecycleAttestationReviewDigestVerificationRequest, *, policy: WorkItemLifecycleAttestationReviewDigestVerificationPolicy | None = None) -> WorkItemLifecycleAttestationReviewDigestVerificationResult:
    policy = policy or WorkItemLifecycleAttestationReviewDigestVerificationPolicy()
    digest = _extract(request.review_digest, "digest")
    index = _extract(request.attestation_index, "index")
    report = _extract(request.index_verification_report, "report")
    blockers: set[str] = set()
    warnings: set[str] = set()
    contradictions: set[str] = set()
    findings: list[WorkItemLifecycleAttestationReviewDigestVerificationFinding] = []

    def add(severity: str, code: str, message: str, refs: tuple[str, ...] = (), entry_id: str | None = None, work_item_id: str | None = None) -> None:
        fid = hashlib.sha256(f"{severity}|{code}|{message}|{entry_id or ''}|{work_item_id or ''}|{'|'.join(refs)}".encode()).hexdigest()[:16]
        findings.append(WorkItemLifecycleAttestationReviewDigestVerificationFinding(finding_id=f"wiardv_{fid}", severity=severity, code=code, message=message, evidence_refs=refs, entry_id=entry_id, work_item_id=work_item_id))

    digest_id = str(digest.get("review_digest_id") or "")
    digest_dg = str(digest.get("review_digest_digest") or "")
    index_id = str(index.get("attestation_index_id") or "")
    index_dg = str(index.get("attestation_index_digest") or "")
    report_id = str(report.get("index_verification_report_id") or "")
    report_dg = str(report.get("index_verification_report_digest") or "")
    if not all((digest_id, digest_dg, index_id, index_dg, report_id, report_dg)):
        blockers.add("required_ids_or_digests_missing")

    for field, expected in (("attestation_index_id", index_id), ("attestation_index_digest", index_dg), ("index_verification_report_id", report_id), ("index_verification_report_digest", report_dg)):
        if expected and digest.get(field) and str(digest.get(field)) != expected:
            contradictions.add(f"digest_{field}_mismatch")

    digest_entries = tuple(e for e in (digest.get("entries") or ()) if isinstance(e, Mapping))
    index_entries = tuple(e for e in (index.get("entries") or ()) if isinstance(e, Mapping))
    d_map = {(str(e.get("entry_id") or ""), str(e.get("work_item_id") or "")): e for e in digest_entries}
    i_map = {(str(e.get("entry_id") or ""), str(e.get("work_item_id") or "")): e for e in index_entries}
    entry_results: list[str] = []
    for k in sorted(d_map):
        if k not in i_map:
            contradictions.add("digest_entry_missing_from_index")
            add("contradiction", "digest_entry_missing_from_index", "digest entry missing from index", entry_id=k[0] or None, work_item_id=k[1] or None)
        else:
            entry_results.append("entry_aligned")
    for k in sorted(i_map):
        if k not in d_map:
            contradictions.add("index_entry_missing_from_digest")
            add("contradiction", "index_entry_missing_from_digest", "index entry missing from digest", entry_id=k[0] or None, work_item_id=k[1] or None)

    digest_wcount = int(digest.get("work_item_count") or 0)
    work_align = "count_aligned"
    if digest_wcount != len(digest_entries) or digest_wcount != int(index.get("indexed_count") or 0):
        contradictions.add("work_item_count_mismatch")
        work_align = "count_mismatch"

    def _count_align(code: str, expected: int, actual: int) -> str:
        if expected != actual:
            contradictions.add(code)
            return "count_mismatch"
        return "count_aligned"

    sealed_align = _count_align("sealed_count_mismatch", int(digest.get("sealed_count") or 0), sum(1 for e in index_entries if str(e.get("attestation_status") or "") == "lifecycle_final_attestation_sealed"))
    attention_align = _count_align("attention_required_count_mismatch", int(digest.get("attention_required_count") or 0), sum(1 for e in digest_entries if bool(e.get("attention_required"))))
    blocker_align = _count_align("blocker_count_mismatch", int(digest.get("blocked_count") or 0), sum(1 for e in digest_entries if e.get("blocker_codes")))
    warning_align = _count_align("warning_count_mismatch", len(tuple(digest.get("warning_codes") or ())), len(tuple(report.get("warning_codes") or ())))
    contradiction_align = _count_align("contradiction_count_mismatch", int(digest.get("contradicted_count") or 0), sum(1 for e in digest_entries if e.get("contradiction_codes")))

    expected_posture = "reviewer_can_accept_index"
    if tuple(report.get("contradiction_codes") or ()) or contradictions:
        expected_posture = "reviewer_must_resolve_contradictions"
    elif tuple(report.get("blocker_codes") or ()):
        expected_posture = "reviewer_must_block"
    elif int(digest.get("attention_required_count") or 0) > 0:
        expected_posture = "reviewer_should_review_attention_items"
    elif tuple(report.get("warning_codes") or ()):
        expected_posture = "reviewer_can_accept_with_warnings"
    posture_align = "posture_aligned"
    if str(digest.get("reviewer_posture") or "") != expected_posture:
        contradictions.add("reviewer_posture_mismatch")
        posture_align = "posture_mismatch"

    if str(digest.get("digest_status") or "") == "lifecycle_attestation_review_digest_clear":
        pass
    elif str(digest.get("digest_status") or "") == "lifecycle_attestation_review_digest_clear_with_warnings" and policy.allow_warnings:
        warnings.add("digest_warnings_allowed")
    elif str(digest.get("digest_status") or "") == "lifecycle_attestation_review_digest_attention_required":
        blockers.add("digest_attention_required")
    elif "contradicted" in str(digest.get("digest_status") or ""):
        contradictions.add("digest_contradicted")
    else:
        blockers.add("digest_not_clear")

    if str(index.get("index_status") or "") == "lifecycle_attestation_index_ready":
        pass
    elif str(index.get("index_status") or "") == "lifecycle_attestation_index_ready_with_warnings" and policy.allow_warnings:
        warnings.add("index_warnings_allowed")
    else:
        blockers.add("index_not_ready")
    if str(report.get("verification_status") or "") == "lifecycle_attestation_index_verification_passed":
        pass
    elif str(report.get("verification_status") or "") == "lifecycle_attestation_index_verification_passed_with_warnings" and policy.allow_warnings:
        warnings.add("index_verification_warnings_allowed")
    else:
        blockers.add("index_verification_not_passed")
    if policy.matrix_required and str((request.matrix_report or {}).get("status") or "") != "passed":
        blockers.add("matrix_required_not_passed")

    blockers.update(str(v) for v in (report.get("blocker_codes") or ()) if v)
    warnings.update(str(v) for v in (report.get("warning_codes") or ()) if v)
    contradictions.update(str(v) for v in (report.get("contradiction_codes") or ()) if v)

    blocker_codes = tuple(sorted(blockers))
    warning_codes = tuple(sorted(warnings))
    contradiction_codes = tuple(sorted(contradictions))
    if contradiction_codes:
        status = "lifecycle_attestation_review_digest_verification_contradicted"
    elif blocker_codes and policy.allow_blockers_for_review:
        status = "lifecycle_attestation_review_digest_verification_manual_review_required"
    elif blocker_codes:
        status = "lifecycle_attestation_review_digest_verification_insufficient_evidence" if any("missing" in c or "required" in c for c in blocker_codes) else "lifecycle_attestation_review_digest_verification_blocked"
    elif warning_codes:
        status = "lifecycle_attestation_review_digest_verification_passed_with_warnings"
    elif all((digest_id, digest_dg, index_id, index_dg, report_id, report_dg)):
        status = "lifecycle_attestation_review_digest_verification_passed"
    else:
        status = "lifecycle_attestation_review_digest_verification_failed"

    payload = {"status": status, "review_digest_id": digest_id, "review_digest_digest": digest_dg, "attestation_index_id": index_id, "attestation_index_digest": index_dg, "index_verification_report_id": report_id, "index_verification_report_digest": report_dg}
    out_dg = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    report_out = WorkItemLifecycleAttestationReviewDigestVerificationReport(
        review_digest_verification_report_id=f"wiardv_{out_dg[:16]}",
        review_digest_verification_report_digest=out_dg,
        review_digest_id=digest_id,
        review_digest_digest=digest_dg,
        attestation_index_id=index_id,
        attestation_index_digest=index_dg,
        index_verification_report_id=report_id,
        index_verification_report_digest=report_dg,
        verification_status=status,
        work_item_count_alignment=work_align,
        sealed_count_alignment=sealed_align,
        attention_required_count_alignment=attention_align,
        blocker_count_alignment=blocker_align,
        warning_count_alignment=warning_align,
        contradiction_count_alignment=contradiction_align,
        reviewer_posture_alignment=posture_align,
        entry_alignment_results=tuple(sorted(set(entry_results) or {"entry_alignment_verified"})),
        matrix_report_status=str((request.matrix_report or {}).get("status") or digest.get("matrix_report_status") or "") or None,
        finding_count=len(findings),
        findings=tuple(sorted(findings, key=lambda f: (f.severity, f.code, f.finding_id))),
        blocker_codes=blocker_codes,
        warning_codes=warning_codes,
        contradiction_codes=contradiction_codes,
        verified_review_digest_statement=(f"Lifecycle attestation review digest {digest_id} verified against supplied index/report metadata only." if status in PASS_STATUSES else None),
        explicit_non_authority_boundaries=tuple(EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    return WorkItemLifecycleAttestationReviewDigestVerificationResult(status=status, report=report_out)


def write_work_item_lifecycle_attestation_review_digest_verification_report(result: WorkItemLifecycleAttestationReviewDigestVerificationResult, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
