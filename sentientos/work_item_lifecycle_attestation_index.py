from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, cast

from sentientos.work_item_intake import EXPLICIT_NON_AUTHORITY_BOUNDARIES

PASS_STATUSES = {
    "lifecycle_attestation_index_ready",
    "lifecycle_attestation_index_ready_with_warnings",
    "lifecycle_attestation_index_manual_review_required",
}

@dataclass(frozen=True)
class WorkItemLifecycleAttestationIndexPolicy:
    allow_skipped_inputs: bool = False
    allow_duplicate_work_items: bool = False
    require_sealed: bool = True
    matrix_required: bool = False

@dataclass(frozen=True)
class WorkItemLifecycleAttestationIndexRequest:
    attestation_bundles: tuple[tuple[str, Mapping[str, Any]], ...]
    matrix_report: Mapping[str, Any] | None = None

@dataclass(frozen=True)
class WorkItemLifecycleAttestationIndexEntry:
    entry_id: str; source_path_or_ref: str; final_attestation_bundle_id: str; final_attestation_bundle_digest: str; work_item_id: str
    source_kind: str | None; source_ref: str | None; attestation_status: str
    completion_dossier_id: str | None; completion_dossier_digest: str | None; verification_report_id: str | None; verification_report_digest: str | None
    proposal_id: str | None; proposal_digest: str | None; stage_count: int | None; matrix_report_status: str | None; proof_bundle_status: str | None
    blocker_codes: tuple[str, ...]; warning_codes: tuple[str, ...]; contradiction_codes: tuple[str, ...]; unresolved_risks: tuple[str, ...]
    artifact_refs: tuple[str, ...]; attention_required: bool; sort_key: str

@dataclass(frozen=True)
class WorkItemLifecycleAttestationIndex:
    attestation_index_id: str; attestation_index_digest: str; generated_from_count: int; indexed_count: int; skipped_count: int; duplicate_count: int; index_status: str
    entries: tuple[WorkItemLifecycleAttestationIndexEntry, ...]; duplicate_keys: tuple[str, ...]; skipped_inputs: tuple[str, ...]
    blocker_codes: tuple[str, ...]; warning_codes: tuple[str, ...]; contradiction_codes: tuple[str, ...]; matrix_report_status: str | None
    artifact_references: tuple[str, ...]; artifact_digests: tuple[str, ...]; explicit_non_authority_boundaries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["entries"] = [asdict(e) for e in self.entries]
        return data

@dataclass(frozen=True)
class WorkItemLifecycleAttestationIndexResult:
    status: str; index: WorkItemLifecycleAttestationIndex
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "index": self.index.to_dict()}


def _codes(value: Any) -> tuple[str, ...]:
    return tuple(sorted(str(v) for v in value if v)) if isinstance(value, list) else ()


def evaluate_work_item_lifecycle_attestation_index(request: WorkItemLifecycleAttestationIndexRequest, *, policy: WorkItemLifecycleAttestationIndexPolicy | None = None) -> WorkItemLifecycleAttestationIndexResult:
    policy = policy or WorkItemLifecycleAttestationIndexPolicy()
    blockers: set[str] = set(); warnings: set[str] = set(); contradictions: set[str] = set()
    entries: list[WorkItemLifecycleAttestationIndexEntry] = []; skipped: list[str] = []; duplicates: set[str] = set()
    seen_digest: set[str] = set(); seen_work: set[str] = set(); refs: set[str] = set(); digests: set[str] = set()

    for src, raw in sorted(request.attestation_bundles, key=lambda x: x[0]):
        b = raw.get("bundle") if isinstance(raw.get("bundle"), Mapping) else raw
        if not isinstance(b, Mapping): skipped.append(src); continue
        bid = str(b.get("final_attestation_bundle_id") or ""); bdg = str(b.get("final_attestation_bundle_digest") or ""); wid = str(b.get("work_item_id") or "")
        ast = str(b.get("attestation_status") or "")
        if not (bid and bdg and wid and ast): skipped.append(src); continue
        if bdg in seen_digest: duplicates.add(f"bundle_digest:{bdg}")
        seen_digest.add(bdg)
        if wid in seen_work: duplicates.add(f"work_item_id:{wid}")
        seen_work.add(wid)
        bl = _codes(b.get("blocker_codes")); wn = _codes(b.get("warning_codes")); ct = _codes(b.get("contradiction_codes"))
        ars = tuple(sorted(str(v) for v in (b.get("artifact_references") or []) if v)) if isinstance(b.get("artifact_references"), list) else ()
        for r in ars: refs.add(r)
        if isinstance(b.get("artifact_digests"), list):
            for d in b["artifact_digests"]: digests.add(str(d))
        attention = bool(bl or wn or ct or ast not in {"lifecycle_final_attestation_sealed", "lifecycle_final_attestation_sealed_with_warnings"})
        if policy.require_sealed and ast not in {"lifecycle_final_attestation_sealed", "lifecycle_final_attestation_sealed_with_warnings"}:
            warnings.add("non_sealed_attestation_status")
        eid = hashlib.sha256(f"{src}|{bdg}|{wid}".encode()).hexdigest()[:16]
        entries.append(WorkItemLifecycleAttestationIndexEntry(
            entry_id=f"wiax_entry_{eid}", source_path_or_ref=src, final_attestation_bundle_id=bid, final_attestation_bundle_digest=bdg, work_item_id=wid,
            source_kind=str(b.get("source_kind") or "") or None, source_ref=str(b.get("source_ref") or "") or None, attestation_status=ast,
            completion_dossier_id=str(b.get("completion_dossier_id") or "") or None, completion_dossier_digest=str(b.get("completion_dossier_digest") or "") or None,
            verification_report_id=str(b.get("verification_report_id") or "") or None, verification_report_digest=str(b.get("verification_report_digest") or "") or None,
            proposal_id=str(b.get("proposal_id") or "") or None, proposal_digest=str(b.get("proposal_digest") or "") or None,
            stage_count=cast(int, b.get("stage_count")) if isinstance(b.get("stage_count"), int) else None,
            matrix_report_status=str(b.get("matrix_report_status") or "") or None, proof_bundle_status=str(b.get("proof_bundle_status") or "") or None,
            blocker_codes=bl, warning_codes=wn, contradiction_codes=ct, unresolved_risks=_codes(b.get("unresolved_risks")), artifact_refs=ars,
            attention_required=attention, sort_key=f"{wid}|{bdg}|{src}",
        ))
        blockers.update(bl); warnings.update(wn); contradictions.update(ct)

    if not entries: blockers.add("no_valid_attestation_bundle_inputs")
    if skipped and not policy.allow_skipped_inputs: blockers.add("skipped_input_present")
    if duplicates:
        if policy.allow_duplicate_work_items: warnings.add("duplicate_inputs_detected")
        else: contradictions.add("duplicate_work_item_or_bundle_digest")
    matrix_status = str((request.matrix_report or {}).get("status") or "") or None
    if policy.matrix_required and matrix_status != "passed": blockers.add("matrix_required_not_passed")

    sorted_entries = tuple(sorted(entries, key=lambda e: e.sort_key))
    if contradictions: status = "lifecycle_attestation_index_contradicted"
    elif blockers: status = "lifecycle_attestation_index_insufficient_evidence" if any("no_valid" in b or "missing" in b for b in blockers) else "lifecycle_attestation_index_blocked"
    elif warnings: status = "lifecycle_attestation_index_manual_review_required" if "non_sealed_attestation_status" in warnings else "lifecycle_attestation_index_ready_with_warnings"
    else: status = "lifecycle_attestation_index_ready"
    payload = {"entries": [asdict(e) for e in sorted_entries], "status": status, "duplicates": sorted(duplicates), "skipped": sorted(skipped), "matrix": matrix_status}
    dg = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    idx = WorkItemLifecycleAttestationIndex(
        attestation_index_id=f"wiax_{dg[:16]}", attestation_index_digest=dg, generated_from_count=len(request.attestation_bundles), indexed_count=len(sorted_entries), skipped_count=len(skipped), duplicate_count=len(duplicates), index_status=status,
        entries=sorted_entries, duplicate_keys=tuple(sorted(duplicates)), skipped_inputs=tuple(sorted(skipped)), blocker_codes=tuple(sorted(blockers)), warning_codes=tuple(sorted(warnings)), contradiction_codes=tuple(sorted(contradictions)), matrix_report_status=matrix_status,
        artifact_references=tuple(sorted(refs)), artifact_digests=tuple(sorted(digests)), explicit_non_authority_boundaries=tuple(EXPLICIT_NON_AUTHORITY_BOUNDARIES),
    )
    return WorkItemLifecycleAttestationIndexResult(status=status, index=idx)


def write_work_item_lifecycle_attestation_index(result: WorkItemLifecycleAttestationIndexResult, path: str | Path) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
