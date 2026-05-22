from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES

SUCCESS_STATUSES = {
    "lifecycle_attestation_review_digest_clear",
    "lifecycle_attestation_review_digest_clear_with_warnings",
    "lifecycle_attestation_review_digest_attention_required",
}


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestPolicy:
    allow_warnings: bool = False
    allow_blockers_for_review: bool = False
    require_no_attention_items: bool = False
    matrix_required: bool = False


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestRequest:
    attestation_index: Mapping[str, Any]
    index_verification_report: Mapping[str, Any]
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestEntry:
    entry_id: str
    work_item_id: str
    source_kind: str | None
    source_ref: str | None
    attestation_status: str
    verification_status: str | None
    attention_required: bool
    reviewer_posture: str
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    unresolved_risks: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    sort_key: str


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigest:
    review_digest_id: str
    review_digest_digest: str
    attestation_index_id: str
    attestation_index_digest: str
    index_verification_report_id: str
    index_verification_report_digest: str
    work_item_count: int
    sealed_count: int
    sealed_with_warnings_count: int
    attention_required_count: int
    blocked_count: int
    contradicted_count: int
    insufficient_count: int
    digest_status: str
    reviewer_posture: str
    entries: tuple[WorkItemLifecycleAttestationReviewDigestEntry, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    unresolved_risks: tuple[str, ...]
    matrix_report_status: str | None
    final_review_statement: str | None
    artifact_references: tuple[str, ...]
    artifact_digests: tuple[str, ...]
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["entries"] = [asdict(e) for e in self.entries]
        return data


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestResult:
    status: str
    digest: WorkItemLifecycleAttestationReviewDigest

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "digest": self.digest.to_dict()}


def _extract(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    inner = raw.get(key)
    return dict(inner) if isinstance(inner, Mapping) else dict(raw)


def _entry_posture(attention: bool, contradictions: tuple[str, ...], blockers: tuple[str, ...], warnings: tuple[str, ...]) -> str:
    if contradictions:
        return "reviewer_must_resolve_contradictions"
    if blockers:
        return "reviewer_must_block"
    if attention:
        return "reviewer_should_review_attention_items"
    if warnings:
        return "reviewer_can_accept_with_warnings"
    return "reviewer_can_accept_index"


def evaluate_work_item_lifecycle_attestation_review_digest(request: WorkItemLifecycleAttestationReviewDigestRequest, *, policy: WorkItemLifecycleAttestationReviewDigestPolicy | None = None) -> WorkItemLifecycleAttestationReviewDigestResult:
    policy = policy or WorkItemLifecycleAttestationReviewDigestPolicy()
    index = _extract(request.attestation_index, "index")
    report = _extract(request.index_verification_report, "report")

    index_id = str(index.get("attestation_index_id") or "")
    index_digest = str(index.get("attestation_index_digest") or "")
    index_status = str(index.get("index_status") or "")
    report_id = str(report.get("index_verification_report_id") or "")
    report_digest = str(report.get("index_verification_report_digest") or "")
    report_status = str(report.get("verification_status") or "")

    blockers = set(str(v) for v in (report.get("blocker_codes") or ()) if v)
    warnings = set(str(v) for v in (report.get("warning_codes") or ()) if v)
    contradictions = set(str(v) for v in (report.get("contradiction_codes") or ()) if v)
    unresolved_risks: set[str] = set()

    entries_raw = tuple(e for e in (index.get("entries") or ()) if isinstance(e, Mapping))
    entries: list[WorkItemLifecycleAttestationReviewDigestEntry] = []
    sealed = sealed_warn = attention = blocked = contradicted = insufficient = 0

    for e in sorted(entries_raw, key=lambda x: f"{str(x.get('sort_key') or '')}|{str(x.get('entry_id') or '')}"):
        att = str(e.get("attestation_status") or "")
        bcodes = tuple(sorted(str(v) for v in (e.get("blocker_codes") or ()) if v))
        wcodes = tuple(sorted(str(v) for v in (e.get("warning_codes") or ()) if v))
        ccodes = tuple(sorted(str(v) for v in (e.get("contradiction_codes") or ()) if v))
        risks = tuple(sorted(set(bcodes + wcodes + ccodes)))
        is_attention = bool(e.get("attention_required") or risks)

        if att == "lifecycle_final_attestation_sealed":
            sealed += 1
        elif att == "lifecycle_final_attestation_sealed_with_warnings":
            sealed_warn += 1
        elif "blocked" in att:
            blocked += 1
        elif "contradicted" in att:
            contradicted += 1
        elif not att:
            insufficient += 1

        if is_attention:
            attention += 1

        entries.append(
            WorkItemLifecycleAttestationReviewDigestEntry(
                entry_id=str(e.get("entry_id") or ""),
                work_item_id=str(e.get("work_item_id") or ""),
                source_kind=(str(e.get("source_kind")) if e.get("source_kind") else None),
                source_ref=(str(e.get("source_ref")) if e.get("source_ref") else None),
                attestation_status=att,
                verification_status=(report_status or None),
                attention_required=is_attention,
                reviewer_posture=_entry_posture(is_attention, ccodes, bcodes, wcodes),
                blocker_codes=bcodes,
                warning_codes=wcodes,
                contradiction_codes=ccodes,
                unresolved_risks=risks,
                artifact_refs=tuple(str(v) for v in (e.get("artifact_refs") or ()) if v),
                sort_key=str(e.get("sort_key") or ""),
            )
        )

    if not index_id or not index_digest or not report_id or not report_digest:
        blockers.add("missing_required_ids_or_digests")
    if index_id and report.get("attestation_index_id") and index_id != str(report.get("attestation_index_id")):
        contradictions.add("index_id_mismatch")
    if index_digest and report.get("attestation_index_digest") and index_digest != str(report.get("attestation_index_digest")):
        contradictions.add("index_digest_mismatch")
    if policy.matrix_required:
        ms = str((request.matrix_report or {}).get("status") or "")
        if ms != "passed":
            blockers.add("matrix_required_not_passed")

    matrix_status = str((request.matrix_report or {}).get("status") or report.get("matrix_report_status") or "") or None

    if index_status not in {"lifecycle_attestation_index_ready", "lifecycle_attestation_index_ready_with_warnings"}:
        if not index_status:
            blockers.add("index_status_missing")
        elif "contradicted" in index_status:
            contradictions.add("index_contradicted")
        elif "blocked" in index_status:
            blockers.add("index_blocked")
        else:
            blockers.add("index_not_ready")

    if report_status not in {"lifecycle_attestation_index_verification_passed", "lifecycle_attestation_index_verification_passed_with_warnings", "lifecycle_attestation_index_verification_manual_review_required"}:
        if "contradicted" in report_status:
            contradictions.add("verification_contradicted")
        elif report_status:
            blockers.add("verification_not_passed")
        else:
            blockers.add("verification_missing")

    if policy.require_no_attention_items and attention > 0:
        blockers.add("attention_items_not_allowed")
    if index_status == "lifecycle_attestation_index_ready_with_warnings" or report_status == "lifecycle_attestation_index_verification_passed_with_warnings" or warnings:
        if not policy.allow_warnings:
            blockers.add("warnings_not_allowed")

    blocker_codes = tuple(sorted(blockers))
    warning_codes = tuple(sorted(warnings))
    contradiction_codes = tuple(sorted(contradictions))

    if contradiction_codes:
        status, posture = "lifecycle_attestation_review_digest_contradicted", "reviewer_must_resolve_contradictions"
    elif any(code.startswith("missing_") for code in blocker_codes):
        status, posture = "lifecycle_attestation_review_digest_insufficient_evidence", "reviewer_needs_more_evidence"
    elif blocker_codes and not (policy.allow_blockers_for_review and attention > 0):
        status, posture = "lifecycle_attestation_review_digest_blocked", "reviewer_must_block"
    elif attention > 0 or (blocker_codes and policy.allow_blockers_for_review):
        status, posture = "lifecycle_attestation_review_digest_attention_required", "reviewer_should_review_attention_items"
    elif warning_codes or index_status.endswith("with_warnings") or report_status.endswith("with_warnings"):
        status, posture = "lifecycle_attestation_review_digest_clear_with_warnings", "reviewer_can_accept_with_warnings"
    elif index_id and report_id:
        status, posture = "lifecycle_attestation_review_digest_clear", "reviewer_can_accept_index"
    else:
        status, posture = "lifecycle_attestation_review_digest_failed", "reviewer_needs_more_evidence"

    final_statement = f"Verified lifecycle attestation index {index_id} summarized for reviewer posture {posture}." if status in SUCCESS_STATUSES else None

    payload = {
        "attestation_index_id": index_id,
        "attestation_index_digest": index_digest,
        "index_verification_report_id": report_id,
        "index_verification_report_digest": report_digest,
        "status": status,
        "posture": posture,
        "entry_ids": [e.entry_id for e in entries],
        "blocker_codes": blocker_codes,
        "warning_codes": warning_codes,
        "contradiction_codes": contradiction_codes,
    }
    digest_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    digest = WorkItemLifecycleAttestationReviewDigest(
        review_digest_id=f"wiard_{digest_hash[:16]}",
        review_digest_digest=digest_hash,
        attestation_index_id=index_id,
        attestation_index_digest=index_digest,
        index_verification_report_id=report_id,
        index_verification_report_digest=report_digest,
        work_item_count=len(entries),
        sealed_count=sealed,
        sealed_with_warnings_count=sealed_warn,
        attention_required_count=attention,
        blocked_count=blocked,
        contradicted_count=contradicted,
        insufficient_count=insufficient,
        digest_status=status,
        reviewer_posture=posture,
        entries=tuple(entries),
        blocker_codes=blocker_codes,
        warning_codes=warning_codes,
        contradiction_codes=contradiction_codes,
        unresolved_risks=tuple(sorted(unresolved_risks.union(blockers, warnings, contradictions))),
        matrix_report_status=matrix_status,
        final_review_statement=final_statement,
        artifact_references=("attestation_index", "index_verification_report"),
        artifact_digests=tuple(v for v in (index_digest, report_digest) if v),
        explicit_non_authority_boundaries=tuple(EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    return WorkItemLifecycleAttestationReviewDigestResult(status=status, digest=digest)


def write_work_item_lifecycle_attestation_review_digest(result: WorkItemLifecycleAttestationReviewDigestResult, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
