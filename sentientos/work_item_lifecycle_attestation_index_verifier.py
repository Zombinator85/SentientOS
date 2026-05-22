from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES

PASS_STATUSES = {
    "lifecycle_attestation_index_verification_passed",
    "lifecycle_attestation_index_verification_passed_with_warnings",
    "lifecycle_attestation_index_verification_manual_review_required",
}

ENTRY_PASS_STATUSES = {"lifecycle_final_attestation_sealed", "lifecycle_final_attestation_sealed_with_warnings"}


@dataclass(frozen=True)
class WorkItemLifecycleAttestationIndexVerificationPolicy:
    allow_warning_index: bool = False
    allow_blocked_index_review: bool = False
    source_bundles_required: bool = False
    matrix_required: bool = False


@dataclass(frozen=True)
class WorkItemLifecycleAttestationIndexVerificationRequest:
    attestation_index: Mapping[str, Any]
    attestation_bundles: tuple[tuple[str, Mapping[str, Any]], ...] = ()
    matrix_report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class WorkItemLifecycleAttestationIndexVerificationFinding:
    finding_id: str
    severity: str
    code: str
    message: str
    evidence_refs: tuple[str, ...]
    entry_id: str | None = None
    work_item_id: str | None = None


@dataclass(frozen=True)
class WorkItemLifecycleAttestationIndexVerificationReport:
    index_verification_report_id: str
    index_verification_report_digest: str
    attestation_index_id: str
    attestation_index_digest: str
    verification_status: str
    indexed_count: int
    supplied_bundle_count: int
    checked_entry_count: int
    checked_bundle_count: int
    digest_alignment_results: tuple[str, ...]
    work_item_alignment_results: tuple[str, ...]
    duplicate_detection_results: tuple[str, ...]
    skipped_input_results: tuple[str, ...]
    attention_required_results: tuple[str, ...]
    deterministic_order_results: tuple[str, ...]
    matrix_report_status: str | None
    finding_count: int
    findings: tuple[WorkItemLifecycleAttestationIndexVerificationFinding, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    verified_index_statement: str | None
    explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = [asdict(f) for f in self.findings]
        return data


@dataclass(frozen=True)
class WorkItemLifecycleAttestationIndexVerificationResult:
    status: str
    report: WorkItemLifecycleAttestationIndexVerificationReport

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "report": self.report.to_dict()}


def _extract(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    inner = raw.get(key)
    return dict(inner) if isinstance(inner, Mapping) else dict(raw)


def evaluate_work_item_lifecycle_attestation_index_verification(request: WorkItemLifecycleAttestationIndexVerificationRequest, *, policy: WorkItemLifecycleAttestationIndexVerificationPolicy | None = None) -> WorkItemLifecycleAttestationIndexVerificationResult:
    policy = policy or WorkItemLifecycleAttestationIndexVerificationPolicy()
    index = _extract(request.attestation_index, "index")
    blockers: set[str] = set()
    warnings: set[str] = set()
    contradictions: set[str] = set()
    findings: list[WorkItemLifecycleAttestationIndexVerificationFinding] = []
    digest_results: list[str] = []
    work_results: list[str] = []
    duplicate_results: list[str] = []
    skipped_results: list[str] = []
    attention_results: list[str] = []
    order_results: list[str] = []

    def add(severity: str, code: str, message: str, refs: tuple[str, ...] = (), entry_id: str | None = None, work_item_id: str | None = None) -> None:
        fid = hashlib.sha256(f"{severity}|{code}|{message}|{entry_id or ''}|{work_item_id or ''}|{'|'.join(refs)}".encode()).hexdigest()[:16]
        findings.append(WorkItemLifecycleAttestationIndexVerificationFinding(finding_id=f"wiaxv_{fid}", severity=severity, code=code, message=message, evidence_refs=refs, entry_id=entry_id, work_item_id=work_item_id))

    idx_id = str(index.get("attestation_index_id") or "")
    idx_digest = str(index.get("attestation_index_digest") or "")
    idx_status = str(index.get("index_status") or "")
    entries = tuple(e for e in index.get("entries") or () if isinstance(e, Mapping))
    indexed_count = int(index.get("indexed_count") or 0)

    if not idx_id or not idx_digest:
        blockers.add("index_id_digest_required")
        add("blocker", "index_id_digest_required", "attestation index id/digest required")
    if indexed_count != len(entries):
        contradictions.add("indexed_count_mismatch")
        add("contradiction", "indexed_count_mismatch", "indexed_count must match entries length")

    expected_order = sorted(entries, key=lambda e: f"{str(e.get('sort_key') or '')}|{str(e.get('entry_id') or '')}")
    if list(entries) != expected_order:
        contradictions.add("non_deterministic_entry_order")
        order_results.append("entry_order_mismatch")
        add("contradiction", "non_deterministic_entry_order", "entry order is not deterministic")
    else:
        order_results.append("entry_order_verified")

    dup_keys = tuple(sorted(str(v) for v in (index.get("duplicate_keys") or ()) if v))
    if int(index.get("duplicate_count") or 0) != len(dup_keys):
        contradictions.add("duplicate_count_mismatch")
        add("contradiction", "duplicate_count_mismatch", "duplicate_count and duplicate_keys mismatch")
    duplicate_results.append("duplicate_structure_verified" if int(index.get("duplicate_count") or 0) == len(dup_keys) else "duplicate_structure_mismatch")

    skipped = tuple(sorted(str(v) for v in (index.get("skipped_inputs") or ()) if v))
    if int(index.get("skipped_count") or 0) != len(skipped):
        contradictions.add("skipped_count_mismatch")
        add("contradiction", "skipped_count_mismatch", "skipped_count and skipped_inputs mismatch")
    skipped_results.append("skipped_structure_verified" if int(index.get("skipped_count") or 0) == len(skipped) else "skipped_structure_mismatch")

    bundles: dict[str, Mapping[str, Any]] = {}
    for src, raw in sorted(request.attestation_bundles, key=lambda x: x[0]):
        bundle = _extract(raw, "bundle")
        bid = str(bundle.get("final_attestation_bundle_id") or "")
        if bid:
            bundles[bid] = bundle

    checked_entries = 0
    checked_bundles = 0
    for entry in entries:
        eid = str(entry.get("entry_id") or "") or None
        wid = str(entry.get("work_item_id") or "") or None
        checked_entries += 1
        expected_attention = bool((entry.get("warning_codes") or ()) or (entry.get("blocker_codes") or ()) or (entry.get("contradiction_codes") or ()) or str(entry.get("attestation_status") or "") not in ENTRY_PASS_STATUSES)
        if bool(entry.get("attention_required")) != expected_attention:
            contradictions.add("attention_required_mismatch")
            attention_results.append("attention_mismatch")
            add("contradiction", "attention_required_mismatch", "attention_required does not match entry signals", entry_id=eid, work_item_id=wid)
        if str(entry.get("final_attestation_bundle_id") or "") in bundles:
            checked_bundles += 1
            b = bundles[str(entry.get("final_attestation_bundle_id") or "")]
            if str(entry.get("final_attestation_bundle_digest") or "") != str(b.get("final_attestation_bundle_digest") or ""):
                contradictions.add("bundle_digest_mismatch")
                digest_results.append("bundle_digest_mismatch")
                add("contradiction", "bundle_digest_mismatch", "bundle digest mismatch", entry_id=eid, work_item_id=wid)
            if str(entry.get("work_item_id") or "") != str(b.get("work_item_id") or ""):
                contradictions.add("bundle_work_item_mismatch")
                work_results.append("bundle_work_item_mismatch")
                add("contradiction", "bundle_work_item_mismatch", "bundle work_item_id mismatch", entry_id=eid, work_item_id=wid)

    if policy.source_bundles_required and not bundles:
        blockers.add("source_bundles_required")
        add("blocker", "source_bundles_required", "source bundles required but none supplied")
    if policy.source_bundles_required and checked_entries != checked_bundles:
        blockers.add("source_bundle_coverage_incomplete")
        add("blocker", "source_bundle_coverage_incomplete", "every index entry must align with supplied source bundle")

    if policy.matrix_required:
        matrix_status: str | None = str((request.matrix_report or {}).get("status") or "")
        if matrix_status != "passed":
            blockers.add("matrix_required_not_passed")
            add("blocker", "matrix_required_not_passed", "matrix report required and must be passing")
    matrix_status = str((request.matrix_report or {}).get("status") or index.get("matrix_report_status") or "") or None

    if idx_status == "lifecycle_attestation_index_ready":
        pass
    elif idx_status == "lifecycle_attestation_index_ready_with_warnings" and policy.allow_warning_index:
        warnings.add("index_ready_with_warnings_allowed")
    elif idx_status == "lifecycle_attestation_index_ready_with_warnings":
        blockers.add("warning_index_not_allowed")
    elif idx_status == "lifecycle_attestation_index_blocked":
        blockers.add("index_blocked")
    elif idx_status == "lifecycle_attestation_index_contradicted":
        contradictions.add("index_contradicted")
    elif idx_status:
        blockers.add("index_status_not_ready")
    else:
        blockers.add("index_status_missing")

    contradiction_codes = tuple(sorted(contradictions))
    blocker_codes = tuple(sorted(blockers))
    warning_codes = tuple(sorted(warnings))

    if contradiction_codes:
        status = "lifecycle_attestation_index_verification_contradicted"
    elif blocker_codes and policy.allow_blocked_index_review and "index_blocked" in blocker_codes:
        status = "lifecycle_attestation_index_verification_manual_review_required"
    elif blocker_codes:
        status = "lifecycle_attestation_index_verification_insufficient_evidence" if any("required" in c or "missing" in c for c in blocker_codes) else "lifecycle_attestation_index_verification_blocked"
    elif warning_codes:
        status = "lifecycle_attestation_index_verification_passed_with_warnings"
    elif idx_id and idx_digest:
        status = "lifecycle_attestation_index_verification_passed"
    else:
        status = "lifecycle_attestation_index_verification_failed"

    findings = sorted(findings, key=lambda f: (f.severity, f.code, f.finding_id))
    payload = {
        "status": status,
        "attestation_index_id": idx_id,
        "attestation_index_digest": idx_digest,
        "contradiction_codes": contradiction_codes,
        "blocker_codes": blocker_codes,
        "warning_codes": warning_codes,
        "finding_codes": [f.code for f in findings],
    }
    dg = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    report = WorkItemLifecycleAttestationIndexVerificationReport(
        index_verification_report_id=f"wiaxv_{dg[:16]}",
        index_verification_report_digest=dg,
        attestation_index_id=idx_id,
        attestation_index_digest=idx_digest,
        verification_status=status,
        indexed_count=indexed_count,
        supplied_bundle_count=len(request.attestation_bundles),
        checked_entry_count=checked_entries,
        checked_bundle_count=checked_bundles,
        digest_alignment_results=tuple(sorted(set(digest_results) or {"no_digest_contradictions"})),
        work_item_alignment_results=tuple(sorted(set(work_results) or {"no_work_item_contradictions"})),
        duplicate_detection_results=tuple(duplicate_results),
        skipped_input_results=tuple(skipped_results),
        attention_required_results=tuple(attention_results or ["attention_flags_verified"]),
        deterministic_order_results=tuple(order_results),
        matrix_report_status=matrix_status,
        finding_count=len(findings),
        findings=tuple(findings),
        blocker_codes=blocker_codes,
        warning_codes=warning_codes,
        contradiction_codes=contradiction_codes,
        verified_index_statement=(f"Lifecycle attestation index {idx_id} verified as internally coherent and metadata-only." if status in PASS_STATUSES else None),
        explicit_non_authority_boundaries=tuple(EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    return WorkItemLifecycleAttestationIndexVerificationResult(status=status, report=report)


def write_work_item_lifecycle_attestation_index_verification_report(result: WorkItemLifecycleAttestationIndexVerificationResult, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
