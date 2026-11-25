"""Audit structural owner-state and receipt links for rootless history records.

This read-only audit verifies stored record/receipt integrity and the digest of
the resident composition checkpoint. It does not revalidate runtime admission
authority or Phase A query eligibility.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.local_model_authority import digest_payload  # noqa: E402
from sentientos.codex_task_authority_admission import (  # noqa: E402
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.resident_developmental_writeback import (  # noqa: E402
    DevelopmentalHistoryStore,
    DevelopmentalWritebackError,
    ResidentDevelopmentalWritebackController,
)
from sentientos.runtime_admission import (  # noqa: E402
    AdmissionLedger,
    RuntimeAdmissionVerifier,
)
from work.audit_semantic_retrieval_multi_root_capacity import (  # noqa: E402
    QUERY_SCHEMA_PATH,
    _minimum_query_count,
)


class _SingleRecordStore:
    """Read-only bounded view so one legacy failure cannot hide valid peers."""
    def __init__(self, record: Any, receipts: Sequence[Any]) -> None:
        self._record = record
        self._receipts = tuple(receipt for receipt in receipts
            if receipt.record_id == record.record_id)

    def records(self) -> tuple[Any, ...]:
        return (self._record,)

    def receipts(self) -> tuple[Any, ...]:
        return self._receipts

    def get_receipt(self, receipt_id: str) -> Any:
        matches = [receipt for receipt in self._receipts
            if receipt.receipt_id == receipt_id]
        if len(matches) != 1:
            raise DevelopmentalWritebackError("stored_payload_missing")
        return matches[0]


def _canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if (not isinstance(value, dict)
            or json.dumps(value, sort_keys=True, indent=2).encode("utf-8") + b"\n" != raw):
        raise ValueError("owner_lineage_noncanonical_json")
    return value


def _audit_cycle(cycle: Path) -> dict[str, Any]:
    history = cycle / "resident-cognition" / "history"
    state_root = cycle / "resident-cognition" / "state"
    state_path = state_root / "composition_state.json"
    ledger = AdmissionLedger(state_root / "runtime_admissions.json")
    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK:
        RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
    verifier = RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger)
    controller = ResidentDevelopmentalWritebackController(history_root=history,
        admission_verifier=verifier, current_sequence=ledger.current_sequence)
    store = DevelopmentalHistoryStore(history)
    records = store.records()
    receipts = store.receipts()
    record_by_id = {record.record_id: record for record in records}
    receipt_by_id = {receipt.receipt_id: receipt for receipt in receipts}
    if len(record_by_id) != len(records) or len(receipt_by_id) != len(receipts):
        raise ValueError("owner_lineage_duplicate_store_identity")

    # Use the official read-only recovery path on a one-record view. This keeps
    # a missing admission for one historical record from masking valid peers.
    admission_verified_ids: set[str] = set()
    admission_failures: dict[str, str] = {}
    for record in records:
        isolated = ResidentDevelopmentalWritebackController(
            history_root=history, admission_verifier=verifier,
            current_sequence=ledger.current_sequence)
        isolated.store = _SingleRecordStore(record, receipts)
        try:
            verified = isolated.inspect_completed_records()
            if len(verified) != 1 or verified[0][0].record_id != record.record_id:
                raise ValueError("owner_lineage_single_record_recovery_mismatch")
            admission_verified_ids.add(record.record_id)
        except (DevelopmentalWritebackError, ValueError) as exc:
            admission_failures[record.record_id] = str(exc)

    receipt_linked = 0
    for receipt in receipts:
        record = record_by_id.get(receipt.record_id)
        if (record is None or receipt.record_digest != record.record_digest
                or receipt.candidate_id != record.candidate.get("candidate_id")
                or receipt.candidate_digest != record.candidate.get("candidate_digest")
                or receipt.admission_id != record.admission_id
                or receipt.admission_binding_digest != record.admission_binding_digest
                or receipt.principal != record.principal
                or receipt.operation_id != record.operation_id):
            raise ValueError("owner_lineage_receipt_record_mismatch")
        receipt_linked += 1

    if not state_path.is_file():
        completed: list[dict[str, Any]] = []
        state_digest_verified = False
    else:
        state = _canonical_json(state_path)
        claimed = state.pop("state_digest", None)
        state_digest_verified = claimed == "sha256:" + digest_payload(state)
        if not state_digest_verified:
            raise ValueError("owner_lineage_composition_state_digest_mismatch")
        completed = state.get("completed_ticks", [])
        if not isinstance(completed, list) or any(not isinstance(row, dict) for row in completed):
            raise ValueError("owner_lineage_completed_ticks_invalid")

    referenced: set[str] = set()
    matched: set[str] = set()
    for row in completed:
        record_id = row.get("record_id")
        receipt_id = row.get("receipt_id")
        if not isinstance(record_id, str):
            continue
        if record_id in referenced:
            raise ValueError("owner_lineage_duplicate_completed_record")
        referenced.add(record_id)
        record = record_by_id.get(record_id)
        receipt = receipt_by_id.get(receipt_id) if isinstance(receipt_id, str) else None
        if (record is not None and receipt is not None
                and receipt.record_id == record_id
                and receipt.record_digest == record.record_digest):
            matched.add(record_id)

    return {
        "cycle_id": cycle.name,
        "record_count": len(records),
        "receipt_count": len(receipts),
        "receipt_record_lineage_count": receipt_linked,
        "runtime_admission_verified_record_count": len(admission_verified_ids),
        "runtime_admission_failed_record_count": len(admission_failures),
        "runtime_admission_status": ("verified" if not admission_failures
            else "partial" if admission_verified_ids else "rejected"),
        "runtime_admission_failure_reasons": dict(sorted(Counter(
            admission_failures.values()).items())),
        "composition_state_present": state_path.is_file(),
        "composition_state_digest_verified": state_digest_verified,
        "completed_state_record_reference_count": len(referenced),
        "completed_state_record_receipt_match_count": len(matched),
        "completed_state_unmatched_count": len(referenced - matched),
        "orphan_record_count": len(set(record_by_id) - matched),
        "_matched_record_identities": {record_id: record_by_id[record_id].record_digest
            for record_id in sorted(matched & admission_verified_ids)},
    }


def build_report(source_roots: Sequence[Path]) -> dict[str, Any]:
    if len(source_roots) < 2:
        raise ValueError("owner_lineage_source_root_count_invalid")
    cycles: dict[str, dict[str, Any]] = {}
    root_ids: set[str] = set()
    for value in source_roots:
        root = value.expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("owner_lineage_source_root_invalid")
        root_id = hashlib.sha256(root.as_posix().encode("utf-8")).hexdigest()
        if root_id in root_ids:
            raise ValueError("owner_lineage_source_root_duplicated")
        root_ids.add(root_id)
        for cycle in sorted(root.glob("rootless-cognition-cycle-*")):
            if not cycle.is_dir():
                continue
            history = cycle / "resident-cognition" / "history"
            if not history.is_dir():
                continue
            result = _audit_cycle(cycle)
            prior = cycles.get(cycle.name)
            identity = {key: value for key, value in result.items() if key != "cycle_id"}
            if prior is not None and prior["identity"] != identity:
                raise ValueError("owner_lineage_cycle_copy_conflict")
            cycles[cycle.name] = {"identity": identity, "root_ids": sorted(
                set(prior["root_ids"] if prior else []) | {root_id})}
    summaries = [{"cycle_id": key, **value["identity"],
        "source_root_ids": value["root_ids"]} for key, value in sorted(cycles.items())]
    matched_identities: dict[str, str] = {}
    verified_sources: dict[str, dict[str, Any]] = {}
    for cycle_id, value in cycles.items():
        for record_id, record_digest in value["identity"][
                "_matched_record_identities"].items():
            prior_digest = matched_identities.get(record_id)
            if prior_digest is not None and prior_digest != record_digest:
                raise ValueError("owner_lineage_record_identity_conflict")
            matched_identities[record_id] = record_digest
            source = verified_sources.setdefault(record_id, {
                "record_digest": record_digest, "cycle_ids": [],
                "source_root_ids": []})
            source["cycle_ids"].append(cycle_id)
            source["source_root_ids"].extend(value["root_ids"])
    for row in summaries:
        row.pop("_matched_record_identities", None)
    verified_record_refs = [{"record_id": record_id,
        "record_digest": source["record_digest"],
        "cycle_ids": sorted(set(source["cycle_ids"])),
        "source_root_ids": sorted(set(source["source_root_ids"]))}
        for record_id, source in sorted(verified_sources.items())]
    minimum_source_count = _minimum_query_count(QUERY_SCHEMA_PATH)
    return {
        "schema_version": "sentientos.semantic_retrieval_owner_lineage_audit:v1",
        "cycle_count": len(summaries),
        "record_count": sum(row["record_count"] for row in summaries),
        "receipt_record_lineage_count": sum(
            row["receipt_record_lineage_count"] for row in summaries),
        "runtime_admission_verified_record_count": sum(
            row["runtime_admission_verified_record_count"] for row in summaries),
        "runtime_admission_rejected_cycle_count": sum(
            row["runtime_admission_status"] == "rejected" for row in summaries),
        "runtime_admission_partial_cycle_count": sum(
            row["runtime_admission_status"] == "partial" for row in summaries),
        "completed_state_record_reference_count": sum(
            row["completed_state_record_reference_count"] for row in summaries),
        "completed_state_record_receipt_match_count": sum(
            row["completed_state_record_receipt_match_count"] for row in summaries),
        "unique_state_receipt_matched_record_count": len(matched_identities),
        "unique_fully_admitted_state_receipt_matched_record_count":
            len(matched_identities),
        "phase_a_minimum_distinct_source_ids": minimum_source_count,
        "phase_a_query_schema_sha256": hashlib.sha256(
            QUERY_SCHEMA_PATH.read_bytes()).hexdigest(),
        "structural_source_capacity_shortfall": max(
            0, minimum_source_count - len(verified_record_refs)),
        "verified_record_refs": verified_record_refs,
        "completed_state_unmatched_count": sum(
            row["completed_state_unmatched_count"] for row in summaries),
        "inference_performed": False,
        "runtime_admission_revalidated": True,
        "phase_a_eligibility_established": False,
        "authority": False,
        "cycles": summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.source_root)
    if args.output:
        if args.output.exists() or args.output.is_symlink() or args.output.parent.is_symlink():
            raise SystemExit("owner_lineage_output_exists")
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, sort_keys=True, indent=2)
            stream.write("\n")
    print(json.dumps({key: value for key, value in report.items()
        if key not in {"cycles", "verified_record_refs"}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, DevelopmentalWritebackError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}, sort_keys=True),
            file=sys.stderr)
        raise SystemExit(2) from exc
