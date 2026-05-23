from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES

SUCCESS_STATUSES = {
    "lifecycle_attestation_review_digest_index_ready",
    "lifecycle_attestation_review_digest_index_ready_with_warnings",
    "lifecycle_attestation_review_digest_index_attention_required",
}


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestIndexPolicy:
    allow_skipped_inputs: bool = False
    allow_duplicate_digests: bool = False
    require_clear: bool = True
    require_verifier_reports: bool = False
    matrix_required: bool = False


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestIndexRequest:
    review_digests: tuple[Mapping[str, Any], ...]
    review_digest_verifier_reports: tuple[Mapping[str, Any], ...] = ()
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestIndexEntry:
    entry_id: str
    source_path_or_ref: str | None
    review_digest_id: str
    review_digest_digest: str
    digest_status: str
    reviewer_posture: str
    work_item_count: int
    attention_required_count: int
    blocked_count: int
    contradicted_count: int
    insufficient_count: int
    attestation_index_id: str | None
    attestation_index_digest: str | None
    index_verification_report_id: str | None
    index_verification_report_digest: str | None
    verifier_report_id: str | None
    verifier_report_digest: str | None
    verifier_status: str | None
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    unresolved_risks: tuple[str, ...]
    attention_required: bool
    sort_key: str


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestIndex:
    review_digest_index_id: str
    review_digest_index_digest: str
    generated_from_count: int
    indexed_count: int
    verifier_report_count: int
    skipped_count: int
    duplicate_count: int
    index_status: str
    aggregate_reviewer_posture: str
    entries: tuple[WorkItemLifecycleAttestationReviewDigestIndexEntry, ...]
    duplicate_keys: tuple[str, ...]
    skipped_inputs: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    unresolved_risks: tuple[str, ...]
    matrix_report_status: str | None
    artifact_references: tuple[str, ...]
    artifact_digests: tuple[str, ...]
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["entries"] = [asdict(e) for e in self.entries]
        return data


@dataclass(frozen=True)
class WorkItemLifecycleAttestationReviewDigestIndexResult:
    status: str
    index: WorkItemLifecycleAttestationReviewDigestIndex

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "index": self.index.to_dict()}


def _extract(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    inner = raw.get(key)
    return dict(inner) if isinstance(inner, Mapping) else dict(raw)


def build_work_item_lifecycle_attestation_review_digest_index(
    request: WorkItemLifecycleAttestationReviewDigestIndexRequest, *, policy: WorkItemLifecycleAttestationReviewDigestIndexPolicy | None = None
) -> WorkItemLifecycleAttestationReviewDigestIndexResult:
    policy = policy or WorkItemLifecycleAttestationReviewDigestIndexPolicy()
    blockers: set[str] = set()
    warnings: set[str] = set()
    contradictions: set[str] = set()
    skipped: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()

    verifier_by_key: dict[str, Mapping[str, Any]] = {}
    for raw in request.review_digest_verifier_reports:
        report = _extract(raw, "report")
        rid = str(report.get("review_digest_id") or "")
        rdg = str(report.get("review_digest_digest") or "")
        if rid:
            verifier_by_key[f"id:{rid}"] = report
        if rdg:
            verifier_by_key[f"digest:{rdg}"] = report

    entries: list[WorkItemLifecycleAttestationReviewDigestIndexEntry] = []
    for pos, raw in enumerate(request.review_digests):
        digest = _extract(raw, "digest")
        did = str(digest.get("review_digest_id") or "")
        ddg = str(digest.get("review_digest_digest") or "")
        if not did and not ddg:
            skipped.append(f"input_{pos}:missing_review_digest_id_and_digest")
            continue
        dkey = f"{did}|{ddg}"
        if dkey in seen:
            duplicates.append(dkey)
            continue
        seen.add(dkey)

        status = str(digest.get("digest_status") or "")
        posture = str(digest.get("reviewer_posture") or "reviewer_needs_more_evidence")
        bcodes = tuple(sorted(str(v) for v in (digest.get("blocker_codes") or ()) if v))
        wcodes = tuple(sorted(str(v) for v in (digest.get("warning_codes") or ()) if v))
        ccodes = tuple(sorted(str(v) for v in (digest.get("contradiction_codes") or ()) if v))
        unresolved = tuple(sorted(set(str(v) for v in (digest.get("unresolved_risks") or ()) if v).union(bcodes, wcodes, ccodes)))

        verifier = verifier_by_key.get(f"id:{did}") or verifier_by_key.get(f"digest:{ddg}")
        vstatus = str((verifier or {}).get("verification_status") or "") or None
        if verifier and did and verifier.get("review_digest_id") and did != str(verifier.get("review_digest_id")):
            contradictions.add("verifier_report_digest_id_mismatch")
        if verifier and ddg and verifier.get("review_digest_digest") and ddg != str(verifier.get("review_digest_digest")):
            contradictions.add("verifier_report_digest_mismatch")

        attention = bool((digest.get("attention_required_count") or 0) or bcodes or wcodes or ccodes or (status not in {"lifecycle_attestation_review_digest_clear"}))
        entries.append(
            WorkItemLifecycleAttestationReviewDigestIndexEntry(
                entry_id=f"wiardi_{hashlib.sha256(dkey.encode()).hexdigest()[:12]}",
                source_path_or_ref=(str(digest.get("source_path_or_ref")) if digest.get("source_path_or_ref") else None),
                review_digest_id=did,
                review_digest_digest=ddg,
                digest_status=status,
                reviewer_posture=posture,
                work_item_count=int(digest.get("work_item_count") or 0),
                attention_required_count=int(digest.get("attention_required_count") or 0),
                blocked_count=int(digest.get("blocked_count") or 0),
                contradicted_count=int(digest.get("contradicted_count") or 0),
                insufficient_count=int(digest.get("insufficient_count") or 0),
                attestation_index_id=(str(digest.get("attestation_index_id")) if digest.get("attestation_index_id") else None),
                attestation_index_digest=(str(digest.get("attestation_index_digest")) if digest.get("attestation_index_digest") else None),
                index_verification_report_id=(str(digest.get("index_verification_report_id")) if digest.get("index_verification_report_id") else None),
                index_verification_report_digest=(str(digest.get("index_verification_report_digest")) if digest.get("index_verification_report_digest") else None),
                verifier_report_id=(str((verifier or {}).get("review_digest_verification_report_id")) if verifier and verifier.get("review_digest_verification_report_id") else None),
                verifier_report_digest=(str((verifier or {}).get("review_digest_verification_report_digest")) if verifier and verifier.get("review_digest_verification_report_digest") else None),
                verifier_status=vstatus,
                blocker_codes=bcodes,
                warning_codes=wcodes,
                contradiction_codes=ccodes,
                unresolved_risks=unresolved,
                attention_required=attention,
                sort_key=f"{did}|{ddg}",
            )
        )

    entries = sorted(entries, key=lambda e: (e.sort_key, e.entry_id))
    if not entries:
        blockers.add("no_review_digests_indexed")
    if skipped:
        (warnings if policy.allow_skipped_inputs else blockers).add("skipped_inputs_present")
    if duplicates:
        (warnings if policy.allow_duplicate_digests else contradictions).add("duplicate_review_digest_keys")
    if policy.require_verifier_reports and any(e.verifier_status is None for e in entries):
        blockers.add("missing_required_verifier_reports")
    if policy.require_verifier_reports and any((e.verifier_status or "").startswith("lifecycle_attestation_review_digest_verification_contradicted") for e in entries):
        contradictions.add("verifier_report_contradicted")
    if policy.require_clear and any(e.digest_status != "lifecycle_attestation_review_digest_clear" for e in entries):
        blockers.add("non_clear_digest_status_present")

    matrix_status = str((request.matrix_report or {}).get("status") or "") or None
    if policy.matrix_required and matrix_status != "passed":
        blockers.add("matrix_required_not_passed")

    has_blocked = any("blocked" in e.digest_status for e in entries)
    has_contra = contradictions or any("contradicted" in e.digest_status for e in entries)
    has_insufficient = any("insufficient" in e.digest_status for e in entries)
    has_attention = any(e.attention_required for e in entries)
    has_warnings = bool(warnings) or any(e.warning_codes for e in entries)

    if has_contra:
        status, posture = "lifecycle_attestation_review_digest_index_contradicted", "reviewer_must_resolve_contradictions"
    elif has_blocked or blockers:
        status, posture = "lifecycle_attestation_review_digest_index_blocked", "reviewer_must_block"
    elif has_insufficient:
        status, posture = "lifecycle_attestation_review_digest_index_insufficient_evidence", "reviewer_needs_more_evidence"
    elif has_attention:
        status, posture = "lifecycle_attestation_review_digest_index_attention_required", "reviewer_should_review_attention_items"
    elif has_warnings:
        status, posture = "lifecycle_attestation_review_digest_index_ready_with_warnings", "reviewer_can_accept_with_warnings"
    else:
        status, posture = "lifecycle_attestation_review_digest_index_ready", "reviewer_can_accept_all"

    payload = {
        "status": status,
        "posture": posture,
        "entry_keys": [e.sort_key for e in entries],
        "duplicates": sorted(duplicates),
        "skipped": sorted(skipped),
        "blockers": sorted(blockers),
        "warnings": sorted(warnings),
        "contradictions": sorted(contradictions),
    }
    index_digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    index = WorkItemLifecycleAttestationReviewDigestIndex(
        review_digest_index_id=f"wiardix_{index_digest[:16]}",
        review_digest_index_digest=index_digest,
        generated_from_count=len(request.review_digests),
        indexed_count=len(entries),
        verifier_report_count=len(request.review_digest_verifier_reports),
        skipped_count=len(skipped),
        duplicate_count=len(duplicates),
        index_status=status,
        aggregate_reviewer_posture=posture,
        entries=tuple(entries),
        duplicate_keys=tuple(sorted(duplicates)),
        skipped_inputs=tuple(sorted(skipped)),
        blocker_codes=tuple(sorted(blockers)),
        warning_codes=tuple(sorted(warnings)),
        contradiction_codes=tuple(sorted(contradictions)),
        unresolved_risks=tuple(sorted(set(blockers).union(warnings, contradictions))),
        matrix_report_status=matrix_status,
        artifact_references=("lifecycle_attestation_review_digests", "lifecycle_attestation_review_digest_verifier_reports"),
        artifact_digests=tuple(e.review_digest_digest for e in entries),
        explicit_non_authority_boundaries=tuple(EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    return WorkItemLifecycleAttestationReviewDigestIndexResult(status=status, index=index)


def write_work_item_lifecycle_attestation_review_digest_index(result: WorkItemLifecycleAttestationReviewDigestIndexResult, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
