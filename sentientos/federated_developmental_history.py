"""Read-only, admission-verified view over explicitly selected history stores.

This view preserves each source store's checkpoint and runtime-admission
ledger. It does not merge ledgers or publish a synthetic owner state.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from contextlib import nullcontext
from copy import copy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from .local_model_authority import digest_payload
from .resident_developmental_writeback import (
    DevelopmentalHistoryProjection,
    DevelopmentalHistoryStore,
    DevelopmentalRecord,
    DevelopmentalWritebackError,
    ResidentDevelopmentalWritebackController,
    WritebackReceipt,
)
from .runtime_admission import (
    AdmissionError,
    AdmissionLedger,
    RuntimeAdmissionVerifier,
)

_CYCLE_ID = re.compile(r"rootless-cognition-cycle-[0-9a-f]{20}")


class FederatedHistoryError(ValueError):
    """A selected federated history source failed its read-only checks."""


class _SingleRecordStore:
    def __init__(self, record: DevelopmentalRecord,
            receipts: Sequence[WritebackReceipt]) -> None:
        self.record = record
        self.receipt_rows = tuple(row for row in receipts
            if row.record_id == record.record_id)

    def records(self) -> tuple[DevelopmentalRecord, ...]:
        return (self.record,)

    def receipts(self) -> tuple[WritebackReceipt, ...]:
        return self.receipt_rows

    def get_receipt(self, receipt_id: str) -> WritebackReceipt:
        matches = [row for row in self.receipt_rows
            if row.receipt_id == receipt_id]
        if len(matches) != 1:
            raise DevelopmentalWritebackError("stored_payload_missing")
        return matches[0]


def _reject_symlink_path(path: Path) -> Path:
    candidate = Path(os.path.abspath(path))
    for part in (candidate, *candidate.parents):
        try:
            if part.is_symlink():
                raise FederatedHistoryError("federated_history_symlink_path")
        except OSError as exc:
            raise FederatedHistoryError("federated_history_path_unavailable") from exc
    return candidate


def _read_composition_state(path: Path) -> tuple[dict[str, Any], str]:
    safe_path = _reject_symlink_path(path)
    try:
        raw = safe_path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FederatedHistoryError("federated_history_composition_state_invalid") from exc
    if (not isinstance(value, dict)
            or json.dumps(value, sort_keys=True, indent=2).encode("utf-8")
                + b"\n" != raw):
        raise FederatedHistoryError("federated_history_composition_state_noncanonical")
    semantic = dict(value)
    claimed = semantic.pop("state_digest", None)
    if claimed != "sha256:" + digest_payload(semantic):
        raise FederatedHistoryError("federated_history_composition_state_digest_mismatch")
    completed = semantic.get("completed_ticks")
    if not isinstance(completed, list) or any(not isinstance(row, dict)
            for row in completed):
        raise FederatedHistoryError("federated_history_completed_ticks_invalid")
    return value, hashlib.sha256(raw).hexdigest()


class FederatedDevelopmentalHistoryReadView:
    """Deduplicated verified records from exact resident-cognition cycle roots.

    `cycle_roots` must name cycle directories containing
    `resident-cognition/history` and `resident-cognition/state`. At least two
    distinct roots are required so this cannot silently degrade to a local
    single-store read.
    """

    def __init__(self, cycle_roots: Sequence[Path]) -> None:
        if not isinstance(cycle_roots, (list, tuple)) or len(cycle_roots) < 2:
            raise FederatedHistoryError("federated_history_source_count_invalid")
        roots = [_reject_symlink_path(path) for path in cycle_roots]
        roots = [path.resolve(strict=True) for path in roots]
        if len(set(roots)) != len(roots) or any(not path.is_dir()
                or _CYCLE_ID.fullmatch(path.name) is None for path in roots):
            raise FederatedHistoryError("federated_history_source_roots_invalid")
        self._records: dict[str, DevelopmentalRecord] = {}
        self._receipts: dict[str, WritebackReceipt] = {}
        self._provenance: dict[str, dict[str, Any]] = {}
        self._source_state_hashes: dict[str, str] = {}
        self._source_inventory: dict[str, dict[str, Any]] = {}
        self._rejected_record_count = 0
        self._excluded_source_count = 0
        for cycle in sorted(roots, key=lambda path: path.as_posix()):
            self._load_cycle(cycle)
        if not self._records:
            raise FederatedHistoryError("federated_history_empty")
        self._record_refs = [{"record_id": record_id,
            "record_digest": self._records[record_id].record_digest,
            "receipt_id": self._receipts[record_id].receipt_id,
            "receipt_digest": self._receipts[record_id].receipt_digest}
            for record_id in sorted(self._records)]
        self._history_state_digest = "sha256:" + digest_payload({
            "schema_version": "sentientos.resident_history_state_digest:v1",
            "records": self._record_refs, "authority": False})

    def _load_cycle(self, cycle: Path) -> None:
        resident = cycle / "resident-cognition"
        history_root = _reject_symlink_path(resident / "history")
        state_root = _reject_symlink_path(resident / "state")
        state_path = _reject_symlink_path(state_root / "composition_state.json")
        if not state_path.is_file():
            self._excluded_source_count += 1
            return
        state, state_file_hash = _read_composition_state(state_path)
        ledger = AdmissionLedger(state_root / "runtime_admissions.json")
        ledger_path = _reject_symlink_path(
            state_root / "runtime_admissions.json")
        initial_ledger_hash = (hashlib.sha256(ledger_path.read_bytes()).hexdigest()
            if ledger_path.exists() else None)
        ledger.load()
        verifier = RuntimeAdmissionVerifier(definitions={
            RESIDENT_DEVELOPMENTAL_WRITEBACK:
                RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}, ledger=ledger)
        controller = ResidentDevelopmentalWritebackController(
            history_root=history_root, admission_verifier=verifier,
            current_sequence=ledger.current_sequence)
        store = DevelopmentalHistoryStore(history_root)
        records = store.records()
        receipts = store.receipts()
        records_by_id = {record.record_id: record for record in records}
        receipts_by_id = {receipt.receipt_id: receipt for receipt in receipts}
        if len(records_by_id) != len(records) or len(receipts_by_id) != len(receipts):
            raise FederatedHistoryError("federated_history_store_identity_duplicated")
        for receipt in receipts:
            record = records_by_id.get(receipt.record_id)
            if (record is None or receipt.record_digest != record.record_digest
                    or receipt.candidate_id != record.candidate.get("candidate_id")
                    or receipt.candidate_digest != record.candidate.get("candidate_digest")
                    or receipt.admission_id != record.admission_id
                    or receipt.admission_binding_digest != record.admission_binding_digest
                    or receipt.principal != record.principal
                    or receipt.operation_id != record.operation_id):
                raise FederatedHistoryError("federated_history_orphan_or_mismatched_receipt")

        refs: dict[str, str] = {}
        for row in state["completed_ticks"]:
            record_id, receipt_id = row.get("record_id"), row.get("receipt_id")
            if not isinstance(record_id, str) or not isinstance(receipt_id, str):
                continue
            if record_id in refs:
                raise FederatedHistoryError("federated_history_checkpoint_reference_duplicated")
            refs[record_id] = receipt_id

        root_id = hashlib.sha256(cycle.parent.as_posix().encode("utf-8")).hexdigest()
        cycle_id = cycle.name
        for record_id, receipt_id in refs.items():
            record = records_by_id.get(record_id)
            receipt = receipts_by_id.get(receipt_id)
            if (record is None or receipt is None
                    or receipt.record_id != record_id
                    or receipt.record_digest != record.record_digest):
                raise FederatedHistoryError("federated_history_checkpoint_receipt_mismatch")
            isolated = ResidentDevelopmentalWritebackController(
                history_root=history_root, admission_verifier=verifier,
                current_sequence=ledger.current_sequence)
            isolated.store = _SingleRecordStore(record, receipts)  # type: ignore[assignment]
            try:
                recovered = isolated.inspect_completed_records()
            except (DevelopmentalWritebackError, AdmissionError, ValueError):
                self._rejected_record_count += 1
                continue
            if (len(recovered) != 1 or recovered[0][0].record_id != record_id
                    or recovered[0][1].receipt_id != receipt_id):
                raise FederatedHistoryError("federated_history_record_recovery_mismatch")

            previous = self._records.get(record_id)
            if previous is not None and (previous.record_digest != record.record_digest
                    or asdict(previous) != asdict(record)):
                raise FederatedHistoryError("federated_history_cross_root_identity_conflict")
            prior_receipt = self._receipts.get(record_id)
            if prior_receipt is not None and asdict(prior_receipt) != asdict(receipt):
                raise FederatedHistoryError("federated_history_cross_root_receipt_conflict")
            self._records[record_id] = record
            self._receipts[record_id] = receipt
            provenance = self._provenance.setdefault(record_id, {
                "record_digest": record.record_digest,
                "cycle_ids": [], "source_root_ids": []})
            provenance["cycle_ids"].append(cycle_id)
            provenance["source_root_ids"].append(root_id)

        # Fail closed if any source changed while it was being read.
        if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_file_hash:
            raise FederatedHistoryError("federated_history_state_changed_during_read")
        reread_records = store.records()
        reread_receipts = store.receipts()
        if ([(row.record_id, row.record_digest) for row in reread_records]
                != [(row.record_id, row.record_digest) for row in records]
                or [(row.receipt_id, row.receipt_digest) for row in reread_receipts]
                != [(row.receipt_id, row.receipt_digest) for row in receipts]):
            raise FederatedHistoryError("federated_history_store_changed_during_read")
        source_key = root_id + ":" + cycle_id
        ledger_hash = (hashlib.sha256(ledger_path.read_bytes()).hexdigest()
            if ledger_path.exists() else None)
        if ledger_hash != initial_ledger_hash:
            raise FederatedHistoryError("federated_history_ledger_changed_during_read")
        self._source_state_hashes[source_key] = state_file_hash
        self._source_inventory[source_key] = {
            "state_path": state_path,
            "history_root": history_root,
            "ledger_path": ledger_path,
            "ledger_hash": ledger_hash,
            "record_rows": tuple((row.record_id, row.record_digest)
                for row in records),
            "receipt_rows": tuple((row.receipt_id, row.receipt_digest)
                for row in receipts),
        }

    def get(self, record_id: str) -> DevelopmentalRecord:
        try:
            return self._records[record_id]
        except (KeyError, TypeError) as exc:
            raise DevelopmentalWritebackError("record_missing_or_corrupt") from exc

    def get_receipt(self, receipt_id: str) -> WritebackReceipt:
        matches = [receipt for receipt in self._receipts.values()
            if receipt.receipt_id == receipt_id]
        if len(matches) != 1:
            raise DevelopmentalWritebackError("stored_payload_missing")
        return matches[0]

    def retrieve(self, record_ids: Sequence[str], *,
            limit: int = 16) -> DevelopmentalHistoryProjection:
        ids = tuple(record_ids)
        if (type(limit) is not int or not 1 <= limit <= 16
                or len(ids) > limit or len(set(ids)) != len(ids)
                or any(record_id not in self._records for record_id in ids)):
            raise DevelopmentalWritebackError("retrieval_bounds_invalid")
        return DevelopmentalHistoryProjection(
            tuple(asdict(self._records[record_id]) for record_id in ids), ids)

    def inspect_completed_records(self) -> tuple[
            tuple[DevelopmentalRecord, WritebackReceipt], ...]:
        self.verify_sources_unchanged()
        return tuple((self._records[row["record_id"]],
            self._receipts[row["record_id"]]) for row in self._record_refs)

    def verify_sources_unchanged(self) -> None:
        """Recheck every explicit source before/after a federated comparison."""
        for source_key, source in self._source_inventory.items():
            try:
                state_hash = hashlib.sha256(
                    _reject_symlink_path(Path(source["state_path"])).read_bytes()).hexdigest()
                ledger_path = Path(source["ledger_path"])
                ledger_hash = (hashlib.sha256(_reject_symlink_path(
                    ledger_path).read_bytes()).hexdigest()
                    if ledger_path.exists() else None)
                AdmissionLedger(ledger_path).load()
                store = DevelopmentalHistoryStore(Path(source["history_root"]))
                record_rows = tuple((row.record_id, row.record_digest)
                    for row in store.records())
                receipt_rows = tuple((row.receipt_id, row.receipt_digest)
                    for row in store.receipts())
            except (OSError, DevelopmentalWritebackError) as exc:
                raise FederatedHistoryError(
                    "federated_history_source_revalidation_failed") from exc
            if (state_hash != self._source_state_hashes[source_key]
                    or ledger_hash != source["ledger_hash"]
                    or record_rows != source["record_rows"]
                    or receipt_rows != source["receipt_rows"]):
                raise FederatedHistoryError(
                    "federated_history_source_changed_during_experiment")

    @property
    def record_refs(self) -> tuple[dict[str, str], ...]:
        return tuple({"record_id": row["record_id"],
            "record_digest": row["record_digest"]} for row in self._record_refs)

    @property
    def history_state_digest(self) -> str:
        return self._history_state_digest

    @property
    def source_provenance(self) -> dict[str, dict[str, Any]]:
        return {record_id: {"record_digest": value["record_digest"],
            "cycle_ids": sorted(set(value["cycle_ids"])),
            "source_root_ids": sorted(set(value["source_root_ids"]))}
            for record_id, value in sorted(self._provenance.items())}

    @property
    def source_snapshots(self) -> tuple[dict[str, Any], ...]:
        snapshots = []
        for source_key, source in sorted(self._source_inventory.items()):
            root_id, cycle_id = source_key.split(":", 1)
            snapshots.append({
                "source_root_id": root_id,
                "cycle_id": cycle_id,
                "composition_state_sha256": self._source_state_hashes[source_key],
                "runtime_admission_ledger_sha256": source["ledger_hash"],
                "record_inventory_digest": "sha256:" + digest_payload(
                    list(source["record_rows"])),
                "receipt_inventory_digest": "sha256:" + digest_payload(
                    list(source["receipt_rows"])),
            })
        return tuple(snapshots)

    @property
    def completed_ticks(self) -> tuple[dict[str, str], ...]:
        """Stable identity order; it does not claim chronology across sources."""
        return tuple({"tick_id": "federated-history:" + row["record_id"],
            "record_id": row["record_id"],
            "receipt_id": row["receipt_id"]} for row in self._record_refs)

    def state_snapshot(self) -> dict[str, Any]:
        return {"schema_version": "sentientos.resident_history_state_snapshot:v1",
            "history_state_digest": self._history_state_digest,
            "record_refs": [dict(row) for row in self._record_refs],
            "authority": False}

    def ordinary_chat_developmental_history_corpus_manifest(self
            ) -> dict[str, Any]:
        """Export the same eligible subset as the resident cognition owner."""
        from .resident_developmental_cognition import (
            _unsafe_legacy_objective_cognition_fact,
        )
        from .semantic_history_retrieval_evaluation import (
            make_retrieval_corpus_manifest,
        )

        records: list[dict[str, str]] = []
        for record, _receipt in self.inspect_completed_records():
            candidate = record.candidate
            facts = (candidate.get("selected_facts", ())
                if isinstance(candidate, Mapping) else ())
            if any(_unsafe_legacy_objective_cognition_fact(fact)
                    for fact in facts):
                continue
            records.append({"record_id": record.record_id,
                "record_digest": record.record_digest})
        return make_retrieval_corpus_manifest(
            history_state_digest=self._history_state_digest,
            records=records)

    @property
    def rejected_record_count(self) -> int:
        return self._rejected_record_count

    @property
    def excluded_source_count(self) -> int:
        return self._excluded_source_count

    def bind_comparison_owner(self, owner: Any) -> "FederatedComparisonOwner":
        """Return an isolated copy of a cognition owner bound to this read view."""
        return FederatedComparisonOwner(owner, self)


class _FederatedWritebackFacade:
    def __init__(self, view: FederatedDevelopmentalHistoryReadView) -> None:
        self.store = view
        self._view = view

    def retrieve(self, record_ids: Sequence[str], *, limit: int = 16
            ) -> DevelopmentalHistoryProjection:
        self._view.verify_sources_unchanged()
        return self._view.retrieve(record_ids, limit=limit)

    def inspect_completed_records(self) -> tuple[
            tuple[DevelopmentalRecord, WritebackReceipt], ...]:
        return self._view.inspect_completed_records()


class FederatedComparisonOwner:
    """Comparison-only adapter that reuses owner retrieval policy unchanged."""
    def __init__(self, template_owner: Any,
            view: FederatedDevelopmentalHistoryReadView) -> None:
        if (not callable(getattr(template_owner,
                    "compare_ordinary_chat_developmental_history_retrieval", None))
                or not hasattr(template_owner, "config")):
            raise FederatedHistoryError("federated_comparison_template_owner_invalid")
        core = copy(template_owner)
        core.writeback = _FederatedWritebackFacade(view)
        core._state = lambda: {"completed_ticks": list(view.completed_ticks),
            "incomplete_ticks": []}
        core._composition_lock = lambda: nullcontext()
        core._ordinary_chat_developmental_history_state_snapshot_locked = (
            lambda: view.state_snapshot())
        core._semantic_history_index_lock = threading.Lock()
        core._semantic_history_indexes = {}
        self._core = core
        self.config = core.config
        self.view = view

    def __getattr__(self, name: str) -> Any:
        return getattr(self._core, name)
