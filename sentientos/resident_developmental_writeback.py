"""Bounded, separately admitted resident developmental-history writeback.

Records produced here are historical interpretations.  They are never current
World-State truth, policy, authority, goals, or canonical explicit user memory.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

from .codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from .governed_local_model_invocation import (
    GovernedLocalModelInvoker,
    LocalModelInvocationBudget,
    LocalModelInvocationReceipt,
)
from .local_model_authority import atomic_write_json, digest_payload
from .runtime_admission import AdmissionError, AdmissionEvidence, RuntimeAdmissionVerifier
from .world_state_board import WorldStateSnapshot, to_dict, validate_snapshot

SCHEMA_VERSION = "sentientos.resident_developmental_writeback:v1"
PRINCIPAL = "deterministic_resident_developmental_writeback_controller"
EFFECTS = tuple(sorted(RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION.required_effects))
PURPOSE = "resident_developmental_interpretation"
MAX_SELECTED_FACTS = 16
MAX_RETRIEVAL_RECORDS = 16
MAX_INTERPRETATION_CHARS = 4000


class DevelopmentalWritebackError(ValueError):
    """Fail-closed runtime boundary violation."""


def _digest(value: Any) -> str:
    return "sha256:" + cast(str, digest_payload(value))


def _identity(prefix: str, payload: Any) -> tuple[str, str]:
    digest = _digest(payload)
    return f"{prefix}-{digest.removeprefix('sha256:')[:24]}", digest


@dataclass(frozen=True)
class SelectedEvidence:
    snapshot_id: str
    snapshot_digest: str
    facts: tuple[Mapping[str, Any], ...]
    sources: tuple[Mapping[str, Any], ...]
    conflicts: tuple[Mapping[str, Any], ...]
    selection_id: str = ""
    selection_digest: str = ""

    def semantic_payload(self) -> dict[str, Any]:
        return {"snapshot_id": self.snapshot_id, "snapshot_digest": self.snapshot_digest,
                "facts": [dict(x) for x in self.facts], "sources": [dict(x) for x in self.sources],
                "conflicts": [dict(x) for x in self.conflicts]}


@dataclass(frozen=True)
class DevelopmentalCandidate:
    interpretation: str
    uncertainty: str
    epistemic_status: str
    snapshot_id: str
    snapshot_digest: str
    selection_id: str
    selection_digest: str
    selected_fact_ids: tuple[str, ...]
    selected_sources: tuple[Mapping[str, Any], ...]
    model_id: str
    model_artifact_digest: str | None
    request_id: str
    request_digest: str
    inference_receipt_id: str
    inference_receipt_digest: str
    output_digest: str
    transformation_provenance: Mapping[str, Any]
    candidate_id: str = ""
    candidate_digest: str = ""

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("candidate_id"); value.pop("candidate_digest")
        return value


@dataclass(frozen=True)
class DevelopmentalRecord:
    record_id: str
    record_digest: str
    candidate: Mapping[str, Any]
    admission_id: str
    admission_binding_digest: str
    principal: str
    operation_id: str
    correlation_id: str
    created_at: str
    epistemic_posture: str = "historical_interpretation_not_current_truth"
    current_truth: bool = False
    authority: bool = False
    policy: bool = False
    canonical_explicit_user_retention: bool = False
    schema_version: str = SCHEMA_VERSION

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("record_id"); value.pop("record_digest")
        return value


@dataclass(frozen=True)
class WritebackReceipt:
    receipt_id: str
    receipt_digest: str
    record_id: str
    record_digest: str
    candidate_id: str
    candidate_digest: str
    admission_id: str
    admission_binding_digest: str
    principal: str
    operation_id: str
    storage_verified: bool
    grants_authority: bool = False
    schema_version: str = SCHEMA_VERSION

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("receipt_id"); value.pop("receipt_digest")
        return value


@dataclass(frozen=True)
class DevelopmentalHistoryProjection:
    records: tuple[Mapping[str, Any], ...]
    requested_record_ids: tuple[str, ...]
    read_only: bool = True
    epistemic_posture: str = "historical_interpretation_not_current_truth"
    current_truth: bool = False
    authority: bool = False
    policy: bool = False
    canonical_explicit_user_retention: bool = False


@dataclass(frozen=True)
class CognitionObservation:
    condition_id: str
    downstream_cognition_id: str
    downstream_cognition_digest: str
    retrieved_record_ids: tuple[str, ...]


@dataclass(frozen=True)
class ChangedCognitionMeasurement:
    measurement_id: str
    measurement_digest: str
    with_record_condition: Mapping[str, Any]
    without_record_condition: Mapping[str, Any]
    compared_fields: tuple[str, ...]
    observable_difference: bool
    interpretation: str = "difference_only_not_improvement_learning_or_correctness"


class DevelopmentalHistoryStore:
    """Content-addressed immutable store, physically separate from canonical memory."""
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.records_root = self.root / "records"
        self.receipts_root = self.root / "receipts"

    def append(self, record: DevelopmentalRecord) -> DevelopmentalRecord:
        self._verify_record(record)
        path = self.records_root / f"{record.record_id}.json"
        payload = asdict(record)
        if path.exists():
            if digest_payload(self._read_json(path)) != digest_payload(payload):
                raise DevelopmentalWritebackError("record_identity_collision")
            return record
        atomic_write_json(path, payload)
        if self.get(record.record_id).record_digest != record.record_digest:
            raise DevelopmentalWritebackError("durable_record_verification_failed")
        return record

    def get(self, record_id: str) -> DevelopmentalRecord:
        path = self.records_root / f"{record_id}.json"
        try: record = DevelopmentalRecord(**self._read_json(path))
        except (OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise DevelopmentalWritebackError("record_missing_or_corrupt") from exc
        self._verify_record(record)
        return record

    def write_receipt(self, receipt: WritebackReceipt) -> WritebackReceipt:
        self._verify_receipt(receipt)
        if self.get(receipt.record_id).record_digest != receipt.record_digest:
            raise DevelopmentalWritebackError("receipt_record_not_durable")
        path = self.receipts_root / f"{receipt.receipt_id}.json"
        payload = asdict(receipt)
        if path.exists() and digest_payload(self._read_json(path)) != digest_payload(payload):
            raise DevelopmentalWritebackError("receipt_identity_collision")
        if not path.exists(): atomic_write_json(path, payload)
        if self.get_receipt(receipt.receipt_id).receipt_digest != receipt.receipt_digest:
            raise DevelopmentalWritebackError("durable_receipt_verification_failed")
        return receipt

    def get_receipt(self, receipt_id: str) -> WritebackReceipt:
        try: receipt = WritebackReceipt(**self._read_json(self.receipts_root / f"{receipt_id}.json"))
        except (OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise DevelopmentalWritebackError("receipt_missing_or_corrupt") from exc
        self._verify_receipt(receipt); return receipt

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict): raise DevelopmentalWritebackError("stored_payload_not_object")
        return value

    @staticmethod
    def _verify_record(record: DevelopmentalRecord) -> None:
        rid, digest = _identity("devrec", record.semantic_payload())
        if (record.record_id, record.record_digest) != (rid, digest):
            raise DevelopmentalWritebackError("record_digest_mismatch")
        if record.current_truth or record.authority or record.policy or record.canonical_explicit_user_retention:
            raise DevelopmentalWritebackError("historical_posture_violation")

    @staticmethod
    def _verify_receipt(receipt: WritebackReceipt) -> None:
        rid, digest = _identity("devreceipt", receipt.semantic_payload())
        if (receipt.receipt_id, receipt.receipt_digest) != (rid, digest) or not receipt.storage_verified or receipt.grants_authority:
            raise DevelopmentalWritebackError("receipt_digest_or_posture_mismatch")


class ResidentDevelopmentalWritebackController:
    def __init__(self, *, history_root: Path, admission_verifier: RuntimeAdmissionVerifier,
                 current_sequence: Callable[[], int]) -> None:
        self.store = DevelopmentalHistoryStore(history_root)
        self.admission_verifier = admission_verifier
        self.current_sequence = current_sequence

    def select_evidence(self, snapshot: WorldStateSnapshot, *, fact_ids: Sequence[str]) -> SelectedEvidence:
        validation = validate_snapshot(snapshot)
        if not validation.valid: raise DevelopmentalWritebackError("invalid_world_state_snapshot:" + ",".join(validation.findings))
        requested = tuple(fact_ids)
        if not requested or len(requested) > MAX_SELECTED_FACTS or len(set(requested)) != len(requested):
            raise DevelopmentalWritebackError("selected_fact_bounds_invalid")
        facts_by_id = {fact.fact_id: fact for fact in snapshot.facts}
        if any(fid not in facts_by_id for fid in requested): raise DevelopmentalWritebackError("selected_fact_not_in_snapshot")
        facts = tuple(to_dict(facts_by_id[fid]) for fid in sorted(requested))
        source_ids = {str(fact["source"]["source_id"]) for fact in facts}
        sources_by_id = {source.source_id: source for source in snapshot.sources}
        if any(sid not in sources_by_id for sid in source_ids): raise DevelopmentalWritebackError("selected_source_not_in_snapshot")
        sources = tuple(to_dict(sources_by_id[sid]) for sid in sorted(source_ids))
        for fact in facts:
            source = sources_by_id[str(fact["source"]["source_id"])]
            if fact["source"] != to_dict(source): raise DevelopmentalWritebackError("selected_source_provenance_mismatch")
        conflicts = tuple(to_dict(c) for c in snapshot.conflicts if set(c.fact_ids) & set(requested))
        raw = SelectedEvidence(snapshot.snapshot_id, snapshot.digest, facts, sources, conflicts)
        sid, digest = _identity("devsel", raw.semantic_payload())
        return replace(raw, selection_id=sid, selection_digest=digest)

    @staticmethod
    def infer_candidate(selection: SelectedEvidence, *, invoker: GovernedLocalModelInvoker,
                        correlation_id: str, budget: LocalModelInvocationBudget | None = None) -> DevelopmentalCandidate:
        bounded = budget or LocalModelInvocationBudget(max_input_chars=8000, max_output_chars=4000, max_new_tokens=512, timeout_seconds=30, max_calls_per_correlation=1)
        if bounded.max_calls_per_correlation != 1 or bounded.max_input_chars > 8000 or bounded.max_output_chars > 4000 or bounded.max_new_tokens > 512 or bounded.timeout_seconds > 30:
            raise DevelopmentalWritebackError("developmental_inference_budget_unbounded")
        schema = {"type":"object", "required":["interpretation","uncertainty"], "additionalProperties":False,
                  "properties":{"interpretation":{"type":"string","maxLength":MAX_INTERPRETATION_CHARS},
                                "uncertainty":{"type":"string","enum":["low","medium","high","unknown"]}}}
        request = invoker.build_request(purpose=PURPOSE, prompt=json.dumps({"instruction":"Interpret selected historical evidence without asserting truth, authority, policy, goals, or storage.", "selection":selection.semantic_payload()}, sort_keys=True), caller=PRINCIPAL, correlation_id=correlation_id, expected_output_format="json", budget=bounded, upstream_evidence={"selection_id":selection.selection_id,"selection_digest":selection.selection_digest,"snapshot_id":selection.snapshot_id,"snapshot_digest":selection.snapshot_digest}, linkage={"transformation":"selected_world_state_to_historical_interpretation"}, structured_output_schema=schema)
        receipt = invoker.invoke(request, persist=True, include_output_in_receipt=False)
        return ResidentDevelopmentalWritebackController.candidate_from_receipt(selection, receipt)

    @staticmethod
    def candidate_from_receipt(selection: SelectedEvidence, receipt: LocalModelInvocationReceipt) -> DevelopmentalCandidate:
        if receipt.status not in {"admitted_completed", "admitted_simulation"} or receipt.purpose != PURPOSE or receipt.output_text is None or receipt.output_digest is None:
            raise DevelopmentalWritebackError("developmental_inference_not_completed")
        try: output = json.loads(receipt.output_text)
        except json.JSONDecodeError as exc: raise DevelopmentalWritebackError("malformed_developmental_output") from exc
        if not isinstance(output, dict) or set(output) != {"interpretation", "uncertainty"} or not isinstance(output["interpretation"], str) or not output["interpretation"].strip() or len(output["interpretation"]) > MAX_INTERPRETATION_CHARS or output["uncertainty"] not in {"low","medium","high","unknown"}:
            raise DevelopmentalWritebackError("malformed_developmental_output")
        req = dict(receipt.request)
        if req.get("purpose") != PURPOSE or req.get("upstream_evidence") != {"selection_id":selection.selection_id,"selection_digest":selection.selection_digest,"snapshot_id":selection.snapshot_id,"snapshot_digest":selection.snapshot_digest}:
            raise DevelopmentalWritebackError("inference_evidence_binding_mismatch")
        raw = DevelopmentalCandidate(output["interpretation"], output["uncertainty"], "untrusted_historical_interpretation_candidate", selection.snapshot_id, selection.snapshot_digest, selection.selection_id, selection.selection_digest, tuple(str(f["fact_id"]) for f in selection.facts), selection.sources, str(req["model_id"]), req.get("model_artifact_digest"), str(req["request_id"]), str(req["request_digest"]), receipt.receipt_id, receipt.receipt_digest, receipt.output_digest, {"kind":"governed_local_model_transformation", "purpose":PURPOSE, "selected_evidence_digest":selection.selection_digest})
        cid, digest = _identity("devcand", raw.semantic_payload())
        return replace(raw, candidate_id=cid, candidate_digest=digest)

    @staticmethod
    def admission_configuration_digest(candidate: DevelopmentalCandidate, *, operation_id: str) -> str:
        return _digest({"candidate_id":candidate.candidate_id,"candidate_digest":candidate.candidate_digest,"operation_id":operation_id,"principal":PRINCIPAL,"effects":list(EFFECTS)})

    def append(self, candidate: DevelopmentalCandidate, *, admission: AdmissionEvidence,
               operation_id: str, correlation_id: str, created_at: str | None = None) -> tuple[DevelopmentalRecord, WritebackReceipt]:
        cid, cdigest = _identity("devcand", candidate.semantic_payload())
        if (candidate.candidate_id, candidate.candidate_digest) != (cid, cdigest): raise DevelopmentalWritebackError("candidate_digest_mismatch")
        config = self.admission_configuration_digest(candidate, operation_id=operation_id)
        if tuple(admission.effects) != EFFECTS: raise DevelopmentalWritebackError("admission_effect_surface_not_exact")
        try:
            for effect in EFFECTS:
                self.admission_verifier.verify(admission, current_sequence=self.current_sequence(), capability_id=RESIDENT_DEVELOPMENTAL_WRITEBACK, principal_id=PRINCIPAL, effect=effect, subject_id=candidate.candidate_id, request_configuration_digest=config)
        except AdmissionError as exc: raise DevelopmentalWritebackError(f"runtime_admission_rejected:{exc}") from exc
        raw = DevelopmentalRecord("", "", asdict(candidate), admission.admission_id, admission.binding_digest, PRINCIPAL, operation_id, correlation_id, created_at or datetime.now(timezone.utc).isoformat())
        rid, rdigest = _identity("devrec", raw.semantic_payload()); record = replace(raw, record_id=rid, record_digest=rdigest)
        record = self.store.append(record)
        receipt_raw = WritebackReceipt("", "", record.record_id, record.record_digest, candidate.candidate_id, candidate.candidate_digest, admission.admission_id, admission.binding_digest, PRINCIPAL, operation_id, True)
        receipt_id, receipt_digest = _identity("devreceipt", receipt_raw.semantic_payload())
        receipt = self.store.write_receipt(replace(receipt_raw, receipt_id=receipt_id, receipt_digest=receipt_digest))
        return record, receipt

    def retrieve(self, record_ids: Sequence[str], *, limit: int = MAX_RETRIEVAL_RECORDS) -> DevelopmentalHistoryProjection:
        ids = tuple(record_ids)
        if limit < 1 or limit > MAX_RETRIEVAL_RECORDS or len(ids) > limit or len(set(ids)) != len(ids): raise DevelopmentalWritebackError("retrieval_bounds_invalid")
        records = tuple(asdict(self.store.get(rid)) for rid in ids)
        return DevelopmentalHistoryProjection(records, ids)


def measure_changed_cognition(*, with_record: CognitionObservation, without_record: CognitionObservation,
                              expected_record_ids: Sequence[str]) -> ChangedCognitionMeasurement:
    expected = tuple(expected_record_ids)
    if not expected or with_record.retrieved_record_ids != expected or without_record.retrieved_record_ids or with_record.condition_id == without_record.condition_id:
        raise DevelopmentalWritebackError("controlled_measurement_conditions_invalid")
    payload = {"with_record":asdict(with_record),"without_record":asdict(without_record),"compared_fields":["downstream_cognition_id","downstream_cognition_digest"],"observable_difference":with_record.downstream_cognition_digest != without_record.downstream_cognition_digest}
    mid, digest = _identity("devmeasure", payload)
    return ChangedCognitionMeasurement(mid, digest, asdict(with_record), asdict(without_record), ("downstream_cognition_id","downstream_cognition_digest"), bool(payload["observable_difference"]))
