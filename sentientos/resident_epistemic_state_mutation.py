"""Separately admitted deterministic mutation of persistent epistemic custody."""
from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar

from .codex_task_authority_admission import RESIDENT_EPISTEMIC_STATE_MUTATION
from .persistent_epistemic_state import (
    DEPENDENCIES, EVIDENCE_RELATIONS, FALSE_AUTHORITY, STANCES, UPDATE_REASONS,
    EpistemicStateError, EpistemicUpdateCandidate, EvidenceBinding,
    PersistentEpistemicStateOwner, canonical_bytes, digest,
    make_epistemic_update_candidate, make_evidence_binding,
)
from .runtime_admission import AdmissionError, AdmissionEvidence, RuntimeAdmissionVerifier
from .windows_handle_custody import WindowsHandleCustodyError, read_regular_files

PRINCIPAL = "deterministic_resident_epistemic_state_controller"
EVIDENCE_BINDING_EFFECTS = tuple(sorted({
    "exact_epistemic_proposition_read", "exact_epistemic_evidence_source_artifact_read",
    "exact_epistemic_evidence_binding_validation", "bounded_epistemic_evidence_binding_append",
    "epistemic_mutation_receipt_write", "read_only_epistemic_post_mutation_verification",
}))
STATE_UPDATE_EFFECTS = tuple(sorted({
    "exact_epistemic_proposition_read", "exact_epistemic_current_state_read",
    "exact_epistemic_update_candidate_read", "deterministic_epistemic_update_candidate_validation",
    "exact_epistemic_predecessor_state_compare_and_swap", "bounded_epistemic_state_generation_append",
    "bounded_epistemic_update_event_append", "epistemic_mutation_receipt_write",
    "read_only_epistemic_post_mutation_verification",
}))
SOURCE_PROOF_SCHEMA = "sentientos.epistemic_evidence_source_proof:v1"
RECEIPT_SCHEMA = "sentientos.resident_epistemic_mutation_receipt:v1"
INTENT_SCHEMA = "sentientos.resident_epistemic_mutation_intent:v1"
MAX_MUTATION_CUSTODY_ENTRIES = 65_536
MAX_MUTATION_CUSTODY_FILE_BYTES = 1_048_576
MAX_MUTATION_CUSTODY_TOTAL_BYTES = 67_108_864
ReceiptT = TypeVar("ReceiptT", bound="EvidenceBindingMutationReceipt | EpistemicStateMutationReceipt")


class EpistemicMutationError(ValueError):
    """A fail-closed admission, identity, or custody failure."""


def _identity(prefix: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    value = digest(payload)
    return f"{prefix}:{value[7:31]}", value


@dataclass(frozen=True)
class EpistemicEvidenceSourceProof:
    proof_id: str; proof_digest: str; source_artifact_id: str; source_digest: str
    source_schema: str; source_class: str; recorded_at: str; adapter_id: str
    provenance_id: str; authority: Mapping[str, bool]; schema_version: str = SOURCE_PROOF_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("proof_id"); value.pop("proof_digest"); return value


def make_epistemic_evidence_source_proof(**kwargs: Any) -> EpistemicEvidenceSourceProof:
    kwargs.setdefault("authority", dict(FALSE_AUTHORITY))
    raw = EpistemicEvidenceSourceProof("", "", **kwargs)
    if (dict(raw.authority) != FALSE_AUTHORITY or not all((raw.source_artifact_id,
            raw.source_digest, raw.source_schema, raw.source_class, raw.recorded_at,
            raw.adapter_id, raw.provenance_id))):
        raise EpistemicMutationError("source_proof_shape_invalid")
    proof_id, proof_digest = _identity("epistemic-source", raw.payload())
    return replace(raw, proof_id=proof_id, proof_digest=proof_digest)


@dataclass(frozen=True)
class EvidenceBindingMutationReceipt:
    receipt_id: str; receipt_digest: str; stage: str; binding_id: str; binding_digest: str
    proposition_id: str; source_artifact_id: str; source_digest: str; admission_id: str
    admission_binding_digest: str; principal: str; operation_id: str; correlation_id: str
    storage_verified: bool = True; authority: bool = False; schema_version: str = RECEIPT_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("receipt_id"); value.pop("receipt_digest"); return value


@dataclass(frozen=True)
class EpistemicStateMutationReceipt:
    receipt_id: str; receipt_digest: str; stage: str; candidate_id: str; proposition_id: str
    predecessor_state_digest: str | None; successor_state_id: str; successor_state_digest: str
    update_event_id: str; update_event_digest: str; evidence_set_digest: str; generation: int
    admission_id: str; admission_binding_digest: str; principal: str; operation_id: str
    correlation_id: str; storage_verified: bool = True; authority: bool = False
    schema_version: str = RECEIPT_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("receipt_id"); value.pop("receipt_digest"); return value


class ResidentEpistemicStateMutationController:
    def __init__(self, *, owner: PersistentEpistemicStateOwner,
                 admission_verifier: RuntimeAdmissionVerifier,
                 current_sequence: Callable[[], int], receipt_root: str | Path) -> None:
        self.owner, self.admission_verifier = owner, admission_verifier
        self.current_sequence = current_sequence
        self.receipt_root = Path(receipt_root)
        if self.receipt_root.exists() and self.receipt_root.is_symlink():
            raise EpistemicMutationError("receipt_root_symlink_forbidden")
        for stage in ("evidence", "state"):
            path = self.receipt_root / "receipts" / stage
            path.mkdir(parents=True, exist_ok=True)
            if path.is_symlink(): raise EpistemicMutationError("receipt_path_symlink_forbidden")
        self.intent_root = self.receipt_root / "operations"
        if os.name == "posix":
            self.intent_root.mkdir(parents=True, exist_ok=True)
        if self.intent_root.exists() and (self.intent_root.is_symlink() or not self.intent_root.is_dir()):
            raise EpistemicMutationError("mutation_intent_root_invalid")
        self.verify_receipts()

    @staticmethod
    def evidence_configuration_digest(*, binding: EvidenceBinding, proposition_digest: str,
                                      operation_id: str) -> str:
        return digest({"stage":"evidence_binding_append", "principal":PRINCIPAL,
            "proposition_id":binding.proposition_id, "proposition_digest":proposition_digest,
            "binding_id":binding.binding_id, "binding_digest":binding.binding_digest,
            "source_artifact_id":binding.source_artifact_id, "source_digest":binding.source_digest,
            "operation_id":operation_id, "effects":EVIDENCE_BINDING_EFFECTS})

    @staticmethod
    def state_configuration_digest(*, candidate: EpistemicUpdateCandidate, operation_id: str) -> str:
        return digest({"stage":"epistemic_state_update", "principal":PRINCIPAL,
            "candidate_id":candidate.candidate_id, "proposition_id":candidate.proposition_id,
            "predecessor_state_digest":candidate.predecessor_state_digest,
            "proposed_stance":candidate.proposed_stance,
            "evidence_binding_ids":candidate.evidence_binding_ids, "reason":candidate.reason,
            "operation_id":operation_id, "effects":STATE_UPDATE_EFFECTS})

    def _admit(self, admission: AdmissionEvidence, *, effects: tuple[str, ...],
               subject_id: str, configuration_digest: str) -> None:
        if tuple(admission.effects) != effects:
            raise EpistemicMutationError("admission_effect_surface_not_exact")
        try:
            for effect in effects:
                self.admission_verifier.verify(admission, current_sequence=self.current_sequence(),
                    capability_id=RESIDENT_EPISTEMIC_STATE_MUTATION, principal_id=PRINCIPAL,
                    effect=effect, subject_id=subject_id,
                    request_configuration_digest=configuration_digest)
        except AdmissionError as exc:
            raise EpistemicMutationError(f"runtime_admission_rejected:{exc}") from exc

    def _write_receipt(self, stage: str, receipt: ReceiptT) -> ReceiptT:
        path = self.receipt_root / "receipts" / stage / f"{receipt.receipt_id}.json"
        raw = canonical_bytes(asdict(receipt)) + b"\n"
        self._publish_immutable(path, raw, collision="immutable_receipt_collision")
        return receipt

    @staticmethod
    def _read_bounded(path: Path, *, missing_ok: bool = False) -> bytes | None:
        descriptor: int | None = None
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0))
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_size > MAX_MUTATION_CUSTODY_FILE_BYTES):
                raise EpistemicMutationError("mutation_custody_file_invalid")
            chunks: list[bytes] = []; remaining = MAX_MUTATION_CUSTODY_FILE_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk: break
                chunks.append(chunk); remaining -= len(chunk)
            raw = b"".join(chunks); after = os.fstat(descriptor)
            if (len(raw) > MAX_MUTATION_CUSTODY_FILE_BYTES or len(raw) != before.st_size
                    or after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns
                    or after.st_dev != before.st_dev or after.st_ino != before.st_ino):
                raise EpistemicMutationError("mutation_custody_file_changed")
            return raw
        except FileNotFoundError:
            if missing_ok: return None
            raise EpistemicMutationError("mutation_custody_file_missing")
        except EpistemicMutationError:
            raise
        except OSError as exc:
            raise EpistemicMutationError("mutation_custody_file_unavailable") from exc
        finally:
            if descriptor is not None: os.close(descriptor)

    @staticmethod
    def _publish_immutable(path: Path, raw: bytes, *, collision: str) -> bool:
        if os.name != "posix":
            raise EpistemicMutationError("mutation_custody_publication_unsupported_platform")
        if len(raw) > MAX_MUTATION_CUSTODY_FILE_BYTES:
            raise EpistemicMutationError("mutation_custody_file_unbounded")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.parent.is_symlink() or not path.parent.is_dir():
            raise EpistemicMutationError("mutation_custody_parent_invalid")
        descriptor, temporary = tempfile.mkstemp(prefix=".epistemic-mutation-", suffix=".tmp",
            dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                if ResidentEpistemicStateMutationController._read_bounded(path) != raw:
                    raise EpistemicMutationError(collision)
                return False
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try: os.fsync(directory)
            finally: os.close(directory)
            return True
        except EpistemicMutationError:
            raise
        except OSError as exc:
            raise EpistemicMutationError("mutation_custody_publication_failed") from exc
        finally:
            try: os.unlink(temporary)
            except FileNotFoundError: pass

    def _write_state_intent(self, *, candidate: EpistemicUpdateCandidate,
                            admission: AdmissionEvidence, operation_id: str,
                            correlation_id: str) -> None:
        semantic = {"schema": INTENT_SCHEMA, "stage": "state", "candidate": asdict(candidate),
            "admission_id": admission.admission_id,
            "admission_binding_digest": admission.binding_digest,
            "operation_id": operation_id, "correlation_id": correlation_id}
        intent_id, intent_digest = _identity("epistemic-intent", semantic)
        payload = {**semantic, "intent_id": intent_id, "intent_digest": intent_digest}
        filename = intent_id.split(":", 1)[1] + ".json"
        published = self._publish_immutable(self.intent_root / filename,
            canonical_bytes(payload) + b"\n", collision="mutation_intent_identity_collision")
        if not published:
            raise EpistemicMutationError("mutation_intent_replay_blocked")

    def _write_evidence_intent(self, *, binding: EvidenceBinding,
                               admission: AdmissionEvidence, operation_id: str,
                               correlation_id: str) -> None:
        semantic = {"schema": INTENT_SCHEMA, "stage": "evidence", "binding": asdict(binding),
            "admission_id": admission.admission_id,
            "admission_binding_digest": admission.binding_digest,
            "operation_id": operation_id, "correlation_id": correlation_id}
        intent_id, intent_digest = _identity("epistemic-intent", semantic)
        payload = {**semantic, "intent_id": intent_id, "intent_digest": intent_digest}
        filename = intent_id.split(":", 1)[1] + ".json"
        published = self._publish_immutable(self.intent_root / filename,
            canonical_bytes(payload) + b"\n", collision="mutation_intent_identity_collision")
        if not published:
            raise EpistemicMutationError("mutation_intent_replay_blocked")

    def _recover_state_receipts(self) -> None:
        if not self.intent_root.exists():
            return
        self.owner.verify()
        try:
            if os.name == "nt":
                entries = read_regular_files(self.intent_root,
                    max_entries=MAX_MUTATION_CUSTODY_ENTRIES,
                    max_file_bytes=MAX_MUTATION_CUSTODY_FILE_BYTES,
                    max_total_bytes=MAX_MUTATION_CUSTODY_TOTAL_BYTES)
            else:
                if self.intent_root.is_symlink() or not self.intent_root.is_dir():
                    raise EpistemicMutationError("mutation_intent_root_invalid")
                paths = sorted(self.intent_root.glob("*.json"))
                if len(paths) > MAX_MUTATION_CUSTODY_ENTRIES:
                    raise EpistemicMutationError("mutation_intent_retention_limit_exceeded")
                entries = tuple((path.name, self._read_bounded(path)) for path in paths)
                if sum(len(raw or b"") for _, raw in entries) > MAX_MUTATION_CUSTODY_TOTAL_BYTES:
                    raise EpistemicMutationError("mutation_intent_retention_limit_exceeded")
        except WindowsHandleCustodyError as exc:
            raise EpistemicMutationError("mutation_intent_windows_recovery_failed") from exc
        states = {value.get("state_digest"): value for value in self.owner._read("states")}
        events = {value.get("event_id"): value for value in self.owner._read("updates")}
        transactions = self.owner._read("transactions")
        completed_event_intents: dict[str, tuple[str, str, str]] = {}
        recovered_receipts: list[EvidenceBindingMutationReceipt | EpistemicStateMutationReceipt] = []
        for name, raw in entries:
            if raw is None: raise EpistemicMutationError("mutation_intent_missing")
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
                raise EpistemicMutationError("mutation_intent_corrupt") from exc
            stage = value.get("stage") if isinstance(value, dict) else None
            payload_field = "binding" if stage == "evidence" else "candidate" if stage == "state" else None
            expected_fields = {"schema", "stage", payload_field, "admission_id",
                "admission_binding_digest", "operation_id", "correlation_id", "intent_id", "intent_digest"}
            if (not isinstance(value, dict) or set(value) != expected_fields
                    or canonical_bytes(value) + b"\n" != raw
                    or value.get("schema") != INTENT_SCHEMA or payload_field is None):
                raise EpistemicMutationError("mutation_intent_shape_invalid")
            semantic = {key: value[key] for key in expected_fields - {"intent_id", "intent_digest"}}
            intent_id, intent_digest = _identity("epistemic-intent", semantic)
            if (value.get("intent_id"), value.get("intent_digest"), name) != (
                    intent_id, intent_digest, intent_id.split(":", 1)[1] + ".json"):
                raise EpistemicMutationError("mutation_intent_identity_mismatch")
            if any(not isinstance(value.get(field), str) or not value[field]
                    for field in ("admission_id", "admission_binding_digest", "operation_id", "correlation_id")):
                raise EpistemicMutationError("mutation_intent_binding_invalid")
            try:
                admission = self.admission_verifier.recorded_admission(str(value["admission_id"]))
            except AdmissionError as exc:
                raise EpistemicMutationError("mutation_intent_admission_missing") from exc
            if admission.binding_digest != value["admission_binding_digest"]:
                raise EpistemicMutationError("mutation_intent_admission_mismatch")
            operation_id, correlation_id = str(value["operation_id"]), str(value["correlation_id"])
            if stage == "evidence":
                try:
                    binding_raw = dict(value["binding"])
                    binding_raw["upstream_binding_ids"] = tuple(binding_raw["upstream_binding_ids"])
                    binding = EvidenceBinding(**binding_raw)
                    expected_binding = make_evidence_binding(**{
                        key: item for key, item in asdict(binding).items()
                        if key not in {"binding_id", "binding_digest", "schema_version"}})
                    proposition = self.owner.proposition(binding.proposition_id)
                except (KeyError, TypeError, ValueError, EpistemicStateError) as exc:
                    raise EpistemicMutationError("mutation_intent_binding_invalid") from exc
                if binding != expected_binding or dict(binding.authority) != FALSE_AUTHORITY:
                    raise EpistemicMutationError("mutation_intent_binding_digest_mismatch")
                configuration = self.evidence_configuration_digest(binding=binding,
                    proposition_digest=proposition.proposition_digest, operation_id=operation_id)
                try:
                    for effect in EVIDENCE_BINDING_EFFECTS:
                        self.admission_verifier.verify(admission, current_sequence=admission.issued_sequence,
                            capability_id=RESIDENT_EPISTEMIC_STATE_MUTATION, principal_id=PRINCIPAL,
                            effect=effect, subject_id=binding.binding_id,
                            request_configuration_digest=configuration)
                except AdmissionError as exc:
                    raise EpistemicMutationError("mutation_intent_admission_recovery_rejected") from exc
                stored = [item for item in self.owner.bindings(binding.proposition_id)
                          if item.binding_id == binding.binding_id]
                if not stored:
                    continue  # Interrupted before append; never replay the mutation.
                if stored != [binding]:
                    raise EpistemicMutationError("mutation_intent_binding_conflict")
                raw_receipt = EvidenceBindingMutationReceipt("", "", "evidence_binding_append",
                    binding.binding_id, binding.binding_digest, binding.proposition_id,
                    binding.source_artifact_id, binding.source_digest, admission.admission_id,
                    admission.binding_digest, PRINCIPAL, operation_id, correlation_id)
                receipt_id, receipt_digest = _identity("epistemic-mutation-receipt", raw_receipt.payload())
                recovered_receipts.append(replace(raw_receipt, receipt_id=receipt_id,
                                                  receipt_digest=receipt_digest))
                continue
            try:
                candidate_raw = dict(value["candidate"])
                candidate_raw["evidence_binding_ids"] = tuple(candidate_raw["evidence_binding_ids"])
                candidate = EpistemicUpdateCandidate(**candidate_raw)
                expected_candidate = make_epistemic_update_candidate(**{
                    key: item for key, item in asdict(candidate).items() if key != "candidate_id"})
            except (KeyError, TypeError, ValueError, EpistemicStateError) as exc:
                raise EpistemicMutationError("mutation_intent_candidate_invalid") from exc
            if candidate != expected_candidate:
                raise EpistemicMutationError("mutation_intent_candidate_digest_mismatch")
            configuration = self.state_configuration_digest(candidate=candidate, operation_id=operation_id)
            try:
                for effect in STATE_UPDATE_EFFECTS:
                    self.admission_verifier.verify(admission, current_sequence=admission.issued_sequence,
                        capability_id=RESIDENT_EPISTEMIC_STATE_MUTATION, principal_id=PRINCIPAL,
                        effect=effect, subject_id=candidate.candidate_id,
                        request_configuration_digest=configuration)
            except AdmissionError as exc:
                raise EpistemicMutationError("mutation_intent_admission_recovery_rejected") from exc
            matching_events = [event for event in events.values()
                if event.get("candidate_id") == candidate.candidate_id
                and event.get("correlation_id") == correlation_id
                and event.get("proposition_id") == candidate.proposition_id]
            if not matching_events:
                continue  # Interrupted before state commit; preserve, never replay.
            if len(matching_events) != 1:
                raise EpistemicMutationError("mutation_intent_event_ambiguous")
            event = matching_events[0]
            event_binding = (str(value["admission_id"]), operation_id, correlation_id)
            previous_intent = completed_event_intents.get(str(event["event_id"]))
            if previous_intent is not None and previous_intent != event_binding:
                raise EpistemicMutationError("mutation_intent_event_conflict")
            completed_event_intents[str(event["event_id"])] = event_binding
            state = states.get(event.get("successor_state_digest"))
            if (state is None or event.get("prior_state_digest") != candidate.predecessor_state_digest
                    or event.get("reason") != candidate.reason
                    or state.get("generation") != event.get("generation")
                    or state.get("predecessor_state_digest") != candidate.predecessor_state_digest
                    or state.get("stance") != candidate.proposed_stance
                    or state.get("evidence_set_digest") != digest(sorted(candidate.evidence_binding_ids))):
                raise EpistemicMutationError("mutation_intent_state_lineage_mismatch")
            matching_transactions = [transaction for transaction in transactions
                if isinstance(transaction.get("state"), Mapping)
                and isinstance(transaction.get("event"), Mapping)
                and transaction["state"].get("state_digest") == state.get("state_digest")
                and transaction["event"].get("event_id") == event.get("event_id")]
            expected_mutation_binding = {"candidate_id": candidate.candidate_id,
                "candidate_digest": candidate.candidate_digest, "admission_id": admission.admission_id,
                "admission_binding_digest": admission.binding_digest,
                "operation_id": operation_id, "correlation_id": correlation_id}
            if not matching_transactions:
                continue  # Legacy/direct update lacks an authenticated admission handoff.
            if (len(matching_transactions) != 1
                    or matching_transactions[0].get("mutation_binding") != expected_mutation_binding):
                raise EpistemicMutationError("mutation_intent_transaction_binding_mismatch")
            raw_receipt = EpistemicStateMutationReceipt("", "", "epistemic_state_update",
                candidate.candidate_id, candidate.proposition_id, candidate.predecessor_state_digest,
                str(state["state_id"]), str(state["state_digest"]), str(event["event_id"]),
                str(event["event_digest"]), str(state["evidence_set_digest"]), int(state["generation"]),
                admission.admission_id, admission.binding_digest, PRINCIPAL, operation_id, correlation_id)
            receipt_id, receipt_digest = _identity("epistemic-mutation-receipt", raw_receipt.payload())
            recovered_receipts.append(replace(raw_receipt, receipt_id=receipt_id,
                                               receipt_digest=receipt_digest))
        for receipt in recovered_receipts:
            if type(receipt) is EvidenceBindingMutationReceipt:
                receipt_stage = "evidence"
            elif type(receipt) is EpistemicStateMutationReceipt:
                receipt_stage = "state"
            else:
                raise EpistemicMutationError("mutation_receipt_recovery_type_invalid")
            if os.name == "nt":
                # Windows recovery is deliberately read-only. Accept only an
                # already published byte-identical receipt; never repair custody
                # by writing from this inspection path.
                directory = self.receipt_root / "receipts" / receipt_stage
                try:
                    published = dict(read_regular_files(directory,
                        max_entries=MAX_MUTATION_CUSTODY_ENTRIES,
                        max_file_bytes=MAX_MUTATION_CUSTODY_FILE_BYTES,
                        max_total_bytes=MAX_MUTATION_CUSTODY_TOTAL_BYTES))
                except WindowsHandleCustodyError as exc:
                    raise EpistemicMutationError("mutation_receipt_windows_recovery_failed") from exc
                name = f"{receipt.receipt_id}.json"
                expected = canonical_bytes(asdict(receipt)) + b"\n"
                if published.get(name) != expected:
                    raise EpistemicMutationError("mutation_receipt_recovery_publication_unsupported")
            else:
                self._write_receipt(receipt_stage, receipt)

    def verify_receipts(self) -> None:
        self._recover_state_receipts()
        for stage, cls in (("evidence", EvidenceBindingMutationReceipt), ("state", EpistemicStateMutationReceipt)):
            directory = self.receipt_root / "receipts" / stage
            if os.name == "nt":
                try:
                    entries = read_regular_files(directory, max_entries=MAX_MUTATION_CUSTODY_ENTRIES,
                        max_file_bytes=MAX_MUTATION_CUSTODY_FILE_BYTES,
                        max_total_bytes=MAX_MUTATION_CUSTODY_TOTAL_BYTES)
                except WindowsHandleCustodyError as exc:
                    raise EpistemicMutationError("mutation_receipt_windows_recovery_failed") from exc
            else:
                if directory.is_symlink() or not directory.is_dir():
                    raise EpistemicMutationError("receipt_path_symlink_forbidden")
                paths = sorted(directory.glob("*.json"))
                if len(paths) > MAX_MUTATION_CUSTODY_ENTRIES:
                    raise EpistemicMutationError("mutation_receipt_retention_limit_exceeded")
                entries = tuple((path.name, self._read_bounded(path)) for path in paths)
                if sum(len(raw or b"") for _, raw in entries) > MAX_MUTATION_CUSTODY_TOTAL_BYTES:
                    raise EpistemicMutationError("mutation_receipt_retention_limit_exceeded")
            for name, raw in entries:
                if raw is None: raise EpistemicMutationError("mutation_receipt_missing")
                try:
                    value = json.loads(raw.decode("utf-8"))
                    if canonical_bytes(value) + b"\n" != raw:
                        raise EpistemicMutationError("mutation_receipt_noncanonical")
                    receipt = cls(**value)
                except (UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise EpistemicMutationError("mutation_receipt_corrupt") from exc
                rid, rdigest = _identity("epistemic-mutation-receipt", receipt.payload())
                if ((receipt.receipt_id, receipt.receipt_digest) != (rid, rdigest)
                        or receipt.authority is not False or receipt.storage_verified is not True
                        or receipt.principal != PRINCIPAL
                        or receipt.stage != ("evidence_binding_append" if stage == "evidence"
                                             else "epistemic_state_update")
                        or name != rid + ".json"):
                    raise EpistemicMutationError("mutation_receipt_identity_mismatch")

    def append_evidence_binding(self, *, binding: EvidenceBinding,
                                source_proof: EpistemicEvidenceSourceProof,
                                admission: AdmissionEvidence, operation_id: str,
                                correlation_id: str) -> EvidenceBindingMutationReceipt:
        self.owner.verify(); proposition = self.owner.proposition(binding.proposition_id)
        expected = make_evidence_binding(**{k:v for k,v in asdict(binding).items()
                                            if k not in {"binding_id","binding_digest","schema_version"}})
        expected_proof = make_epistemic_evidence_source_proof(**{k:v for k,v in asdict(source_proof).items()
                                            if k not in {"proof_id","proof_digest","schema_version"}})
        if expected != binding: raise EpistemicMutationError("evidence_binding_identity_mismatch")
        if expected_proof != source_proof: raise EpistemicMutationError("source_proof_identity_mismatch")
        if dict(binding.authority) != FALSE_AUTHORITY: raise EpistemicMutationError("evidence_authority_widened")
        source_fields = (binding.source_artifact_id, binding.source_digest, binding.source_schema,
                         binding.source_class, binding.observation_time)
        proof_fields = (source_proof.source_artifact_id, source_proof.source_digest,
                        source_proof.source_schema, source_proof.source_class, source_proof.recorded_at)
        if source_fields != proof_fields: raise EpistemicMutationError("source_proof_binding_mismatch")
        if binding.evidence_relation not in EVIDENCE_RELATIONS or binding.dependency_kind not in DEPENDENCIES:
            raise EpistemicMutationError("evidence_binding_vocabulary_invalid")
        configuration = self.evidence_configuration_digest(binding=binding,
            proposition_digest=proposition.proposition_digest, operation_id=operation_id)
        self._admit(admission, effects=EVIDENCE_BINDING_EFFECTS,
                    subject_id=binding.binding_id, configuration_digest=configuration)
        self._write_evidence_intent(binding=binding, admission=admission,
            operation_id=operation_id, correlation_id=correlation_id)
        self.owner.bind_evidence(binding); self.owner.verify()
        matches = [item for item in self.owner.bindings(binding.proposition_id) if item.binding_id == binding.binding_id]
        if matches != [binding] or dict(matches[0].authority) != FALSE_AUTHORITY:
            raise EpistemicMutationError("evidence_post_write_verification_failed")
        raw = EvidenceBindingMutationReceipt("", "", "evidence_binding_append", binding.binding_id,
            binding.binding_digest, binding.proposition_id, binding.source_artifact_id, binding.source_digest,
            admission.admission_id, admission.binding_digest, PRINCIPAL, operation_id, correlation_id)
        rid, rdigest = _identity("epistemic-mutation-receipt", raw.payload())
        return self._write_receipt("evidence", replace(raw, receipt_id=rid, receipt_digest=rdigest))

    def commit_update_candidate(self, *, candidate: EpistemicUpdateCandidate,
                                admission: AdmissionEvidence, operation_id: str,
                                correlation_id: str, tick: int,
                                recorded_at: str) -> EpistemicStateMutationReceipt:
        self.owner.verify(); self.owner.proposition(candidate.proposition_id)
        try:
            expected = make_epistemic_update_candidate(**{k:v for k,v in asdict(candidate).items()
                                                           if k != "candidate_id"})
        except EpistemicStateError as exc:
            raise EpistemicMutationError(f"candidate_invalid:{exc}") from exc
        if expected != candidate: raise EpistemicMutationError("candidate_identity_mismatch")
        if candidate.proposed_stance not in STANCES or candidate.reason not in UPDATE_REASONS:
            raise EpistemicMutationError("candidate_vocabulary_invalid")
        prior = self.owner.current_state(candidate.proposition_id)
        if candidate.predecessor_state_digest != (prior.state_digest if prior else None):
            raise EpistemicMutationError("epistemic_state_compare_and_swap_failed")
        known = {item.binding_id:item for item in self.owner.bindings(candidate.proposition_id)}
        if any(item not in known or known[item].withdrawn for item in candidate.evidence_binding_ids):
            raise EpistemicMutationError("candidate_evidence_missing_foreign_or_withdrawn")
        # A binding receipt is evidence of append only; its admission may never authorize this stage.
        evidence_receipt_paths = sorted((self.receipt_root / "receipts" / "evidence").glob("*.json"))
        if len(evidence_receipt_paths) > MAX_MUTATION_CUSTODY_ENTRIES:
            raise EpistemicMutationError("mutation_receipt_retention_limit_exceeded")
        used_evidence_admissions: set[str] = set()
        for path in evidence_receipt_paths:
            raw_bytes = self._read_bounded(path)
            try:
                raw_receipt = json.loads((raw_bytes or b"").decode("utf-8"))
                if canonical_bytes(raw_receipt) + b"\n" != raw_bytes:
                    raise EpistemicMutationError("mutation_receipt_noncanonical")
                stored_receipt = EvidenceBindingMutationReceipt(**raw_receipt)
            except (UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise EpistemicMutationError("mutation_receipt_corrupt") from exc
            stored_id, stored_digest = _identity("epistemic-mutation-receipt", stored_receipt.payload())
            if ((stored_receipt.receipt_id, stored_receipt.receipt_digest) != (stored_id, stored_digest)
                    or path.name != stored_id + ".json" or stored_receipt.stage != "evidence_binding_append"
                    or stored_receipt.principal != PRINCIPAL or stored_receipt.authority is not False
                    or not stored_receipt.storage_verified):
                raise EpistemicMutationError("mutation_receipt_identity_mismatch")
            used_evidence_admissions.add(stored_receipt.admission_id)
        if admission.admission_id in used_evidence_admissions:
            raise EpistemicMutationError("separate_stage_admission_required")
        configuration = self.state_configuration_digest(candidate=candidate, operation_id=operation_id)
        self._admit(admission, effects=STATE_UPDATE_EFFECTS, subject_id=candidate.candidate_id,
                    configuration_digest=configuration)
        previous_ids = set(self.owner.active_binding_ids(candidate.proposition_id))
        active_ids = set(candidate.evidence_binding_ids)
        self._write_state_intent(candidate=candidate, admission=admission,
            operation_id=operation_id, correlation_id=correlation_id)
        state, event = self.owner.commit_update(proposition_id=candidate.proposition_id,
            expected_predecessor_digest=candidate.predecessor_state_digest,
            stance=candidate.proposed_stance, reason=candidate.reason,
            active_binding_ids=tuple(sorted(active_ids)),
            added_binding_ids=tuple(sorted(active_ids - previous_ids)),
            removed_binding_ids=tuple(sorted(previous_ids - active_ids)), candidate=candidate,
            correlation_id=correlation_id, tick=tick, recorded_at=recorded_at,
            mutation_binding={"candidate_id": candidate.candidate_id,
                "candidate_digest": candidate.candidate_digest,
                "admission_id": admission.admission_id,
                "admission_binding_digest": admission.binding_digest,
                "operation_id": operation_id, "correlation_id": correlation_id})
        self.owner.verify(); current = self.owner.current_state(candidate.proposition_id)
        events = self.owner.update_events(candidate.proposition_id)
        paired = [item for item in events if item.event_id == event.event_id]
        if (current != state or paired != [event] or event.candidate_id != candidate.candidate_id
                or event.prior_state_digest != candidate.predecessor_state_digest
                or event.successor_state_digest != state.state_digest
                or state.evidence_set_digest != digest(sorted(active_ids))
                or state.generation != (prior.generation + 1 if prior else 0)
                or dict(state.authority) != FALSE_AUTHORITY or dict(event.authority) != FALSE_AUTHORITY):
            raise EpistemicMutationError("state_post_write_verification_failed")
        raw = EpistemicStateMutationReceipt("", "", "epistemic_state_update", candidate.candidate_id,
            candidate.proposition_id, candidate.predecessor_state_digest, state.state_id, state.state_digest,
            event.event_id, event.event_digest, state.evidence_set_digest, state.generation,
            admission.admission_id, admission.binding_digest, PRINCIPAL, operation_id, correlation_id)
        rid, rdigest = _identity("epistemic-mutation-receipt", raw.payload())
        return self._write_receipt("state", replace(raw, receipt_id=rid, receipt_digest=rdigest))
