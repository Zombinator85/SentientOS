"""Bounded, separately admitted resident developmental-history writeback.

Records produced here are historical interpretations.  They are never current
World-State truth, policy, authority, goals, or canonical explicit user memory.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

from .codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from .governed_local_model_invocation import (
    LocalModelInvoker,
    LocalModelInvocationBudget,
    LocalModelInvocationReceipt,
)
from .local_model_authority import atomic_write_json, digest_payload
from .runtime_admission import AdmissionError, AdmissionEvidence, RuntimeAdmissionVerifier
from .world_state_board import WorldStateSnapshot, digest, to_dict, validate_snapshot
from .windows_handle_custody import WindowsHandleCustodyError, read_regular_files

SCHEMA_VERSION = "sentientos.resident_developmental_writeback:v1"
PRINCIPAL = "deterministic_resident_developmental_writeback_controller"
EFFECTS = tuple(sorted(RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION.required_effects))
PURPOSE = "resident_developmental_interpretation"
MAX_SELECTED_FACTS = 16
MAX_SELECTED_EVIDENCE_BYTES = 6000
MAX_RETRIEVAL_RECORDS = 16
MAX_INTERPRETATION_CHARS = 4000
MAX_DURABLE_RECORDS = 4096
MAX_DURABLE_RECORD_BYTES = 1_048_576
MAX_DURABLE_RECORD_ROOT_BYTES = 134_217_728


class DevelopmentalWritebackError(ValueError):
    """Fail-closed runtime boundary violation."""


def _valid_store_identity(value: Any, prefix: str) -> bool:
    marker = prefix + ":"
    return (isinstance(value, str) and len(value) == len(marker) + 24
            and value.startswith(marker)
            and all(character in "0123456789abcdef" for character in value[len(marker):]))


def _digest(value: Any) -> str:
    return "sha256:" + cast(str, digest_payload(value))


def _identity(prefix: str, payload: Any) -> tuple[str, str]:
    digest = _digest(payload)
    return f"{prefix}-{digest.removeprefix('sha256:')[:24]}", digest


def _runtime_history_projection(fact: Mapping[str, Any]) -> dict[str, Any] | None:
    """Retain compact process/serving lineage while binding it to the full source row."""
    source = fact.get("source")
    subject = fact.get("subject")
    original = fact.get("payload")
    if (not isinstance(source, Mapping) or source.get("kind") != "runtime_supervisor"
            or not isinstance(subject, Mapping) or not isinstance(original, Mapping)):
        return None
    kind = subject.get("subject_kind")
    summary: dict[str, Any]
    if kind == "chat_process_runtime_generation_observation":
        observation = original.get("chat_process_runtime_observation")
        links = original.get("linked_invocation_receipts", ())
        if not isinstance(observation, Mapping) or not isinstance(links, (list, tuple)):
            return None
        serving_receipt = observation.get("serving_receipt")
        serving = None
        if isinstance(serving_receipt, Mapping):
            serving_binding = serving_receipt.get("binding")
            serving = {key: serving_receipt.get(key) for key in (
                "receipt_id", "receipt_semantic_digest", "session_id")}
            if isinstance(serving_binding, Mapping):
                serving.update({key: serving_binding.get(key) for key in (
                    "serving_operation_id", "activation_state_semantic_digest",
                    "activation_generation", "model_id")})
        selected_links: list[dict[str, Any]] = []
        for item in links[:4]:
            if not isinstance(item, Mapping):
                return None
            model_identity = item.get("active_model_identity_at_invocation")
            selected_link = {key: item.get(key) for key in (
                "invocation_receipt_id", "invocation_receipt_digest",
                "invocation_request_id", "invocation_request_digest",
                "serving_receipt_id", "serving_receipt_semantic_digest",
                "serving_operation_attempt_id", "serving_operation_attempt_semantic_digest",
                "serving_operation_id", "serving_session_id",
                "resource_allocation_digest", "resource_attempt_id",
                "resource_effect_receipt_digest", "model_id", "model_artifact_digest",
                "linkage_posture", "current_model_claimed")}
            consumption_digests = item.get("resource_consumption_receipt_digests", ())
            if isinstance(consumption_digests, (list, tuple)):
                selected_link["resource_consumption_receipt_digests"] = list(consumption_digests[:8])
                selected_link["resource_consumption_receipt_digests_digest"] = digest(
                    list(consumption_digests))
                selected_link["resource_consumption_receipt_digests_omitted"] = max(
                    0, len(consumption_digests) - 8)
            else:
                return None
            selected_links.append(selected_link)
            if isinstance(model_identity, Mapping):
                selected_links[-1]["active_model_identity_digest"] = digest(dict(model_identity))
        summary = {
            "event_time": original.get("event_time"),
            "event_time_posture": original.get("event_time_posture"),
            "runtime_observation": {key: observation.get(key) for key in (
                "observation_semantic_digest", "runtime_supervisor_generation", "observed_at",
                "runtime_status", "handoff_id", "handoff_digest", "process_instance_id",
                "process_id", "parent_process_id", "software_generation_digest",
                "source_generation_scope", "configured_serving_operation_id",
                "configured_serving_receipt_posture", "independent_signature",
                "effect_authority")},
            "serving_receipt_at_observation": serving,
            "invocation_linkage_posture": original.get("invocation_linkage_posture"),
            "linked_invocation_receipts": selected_links,
            "linked_invocation_receipts_digest": digest(list(links)),
            "linked_invocation_receipts_total": len(links),
            "linked_invocation_receipts_omitted": max(0, len(links) - len(selected_links)),
            "projection_posture": "complete" if len(links) <= len(selected_links)
                else "bounded_tail_incomplete",
            "historical_only": True, "current_truth": False, "authority": False,
            "effect_proven": False,
        }
    elif kind == "chat_process_recovery_transition":
        transition = original.get("chat_process_recovery_transition")
        times = original.get("phase_event_times")
        if not isinstance(transition, Mapping):
            return None
        def handoff_summary(value: Any) -> dict[str, Any] | None:
            if not isinstance(value, Mapping):
                return None
            return {key: value.get(key) for key in (
                "handoff_id", "handoff_digest", "process_instance_id",
                "software_generation_digest", "configured_serving_operation_id",
                "source_generation_scope")}
        summary = {
            "transition": {key: transition.get(key) for key in (
                "request_id", "request_semantic_digest", "intent_id", "intent_semantic_digest",
                "approval_id", "approval_semantic_digest", "runtime_supervisor_generation",
                "prior_serving_operation_id", "replacement_serving_operation_id",
                "prior_serving_receipt_id", "prior_serving_receipt_semantic_digest",
                "attempt_phase_digest", "readiness_phase_digest", "completion_phase_digest",
                "advanced_snapshot_digest", "decision_posture", "phase_posture",
                "phase_evidence_posture", "runtime_currentness", "terminal_receipt_digest",
                "terminal_status", "successor_serving_receipt_id",
                "successor_serving_receipt_semantic_digest", "successor_serving_session_id",
                "successor_serving_receipt_posture", "predecessor_serving_operation_binding_posture",
                "successor_serving_operation_binding_posture", "successor_configured_serving_operation_id",
                "effect_authority", "inference_performed")},
            "predecessor_handoff": handoff_summary(transition.get("predecessor_chat_process_handoff")),
            "successor_handoff": handoff_summary(transition.get("successor_chat_process_handoff")),
            "phase_event_times": dict(times) if isinstance(times, Mapping) else {},
            "historical_only": True, "current_truth": False, "authority": False,
            "effect_proven": False,
        }
    elif kind == "serving_operation_history":
        summary = {
            "serving_history_status": original.get("serving_history_status"),
            "serving_operation_id": original.get("serving_operation_id"),
            "attempt_id": original.get("attempt_id"),
            "attempt_semantic_digest": original.get("attempt_semantic_digest"),
            "receipt_id": original.get("receipt_id"),
            "receipt_semantic_digest": original.get("receipt_semantic_digest"),
            "serving_session_id": original.get("serving_session_id"),
            "activation_state_semantic_digest": original.get("activation_state_semantic_digest"),
            "activation_generation": original.get("activation_generation"),
            "model_id": original.get("model_id"), "artifact_id": original.get("artifact_id"),
            "runtime_id": original.get("runtime_id"),
            "event_time": original.get("event_time"),
            "event_time_posture": original.get("event_time_posture"),
            "observed_loaded_model_identity_digest": (
                digest(dict(original["observed_loaded_model_identity"]))
                if isinstance(original.get("observed_loaded_model_identity"), Mapping) else None),
            "historical_only": True, "current_truth": False, "authority": False,
            "effect_proven": False,
        }
    else:
        return None
    projection_binding = {
        "schema_version": "sentientos.runtime_history_projection:v1",
        "source_fact_id": str(fact.get("fact_id", "")),
        "source_payload_digest": digest(dict(original)),
        "source_record_digest": str(source.get("digest", "")),
        "projected_payload_digest": digest(summary),
    }
    projection_binding["projection_digest"] = digest(projection_binding)
    summary["interpretation_projection"] = projection_binding
    projected = dict(fact)
    projected["payload"] = summary
    return projected


def _resource_interpretation_projection(fact: Mapping[str, Any]) -> dict[str, Any]:
    """Keep resource interpretation bounded while binding it to the full source fact."""
    source = fact.get("source")
    subject = fact.get("subject")
    original = fact.get("payload")
    runtime_projection = _runtime_history_projection(fact)
    if runtime_projection is not None:
        return runtime_projection
    if (not isinstance(source, Mapping) or source.get("kind") != "resource_governor"
            or not isinstance(subject, Mapping) or not isinstance(original, Mapping)):
        return dict(fact)
    if subject.get("subject_kind") in {
            "strategy_invocation_resource_lineage",
            "model_replacement_invocation_resource_lineage"}:
        # Joined attribution records can carry a sizeable frozen-history
        # context. The writeback request has a smaller independent byte bound,
        # so retain exact causal identities and a digest of the unabridged
        # source payload while bounding optional context lists here.
        linkage = original.get("resource_linkage")
        if not isinstance(linkage, Mapping):
            return dict(fact)
        request_context = original.get("task_context")
        context = dict(request_context) if isinstance(request_context, Mapping) else {}
        history_ids = context.get("history_record_ids")
        omitted_history_count = 0
        if isinstance(history_ids, (list, tuple)):
            full_history_digest = digest(list(history_ids))
            omitted_history_count = max(0, len(history_ids) - 32)
            context["history_record_ids"] = list(history_ids[:32])
            if omitted_history_count:
                context["history_record_ids_digest"] = full_history_digest
                context["history_record_ids_omitted"] = omitted_history_count
        history_digests = context.get("history_record_digests")
        omitted_history_digest_count = 0
        if isinstance(history_digests, (list, tuple)):
            if isinstance(history_ids, (list, tuple)) and len(history_digests) != len(history_ids):
                context["history_lineage_posture"] = "source_record_identity_pairs_incomplete"
            context["history_record_digests"] = list(history_digests[:32])
            if len(history_digests) > 32:
                omitted_history_digest_count = len(history_digests) - 32
                context["history_record_digests_digest"] = digest(list(history_digests))
                context["history_record_digests_omitted"] = omitted_history_digest_count
        compact_linkage = {key: linkage.get(key) for key in (
            "request_id", "request_digest", "purpose", "model_id", "model_artifact_digest",
            "allocation_digest", "attempt_id", "consumption_receipt_digests",
            "linkage_digest", "effect_receipt_id", "effect_receipt_digest") if key in linkage}
        receipt_digests = compact_linkage.get("consumption_receipt_digests")
        omitted_receipt_count = 0
        if isinstance(receipt_digests, (list, tuple)):
            full_receipt_digest = digest(list(receipt_digests))
            omitted_receipt_count = max(0, len(receipt_digests) - 16)
            compact_linkage["consumption_receipt_digests"] = list(receipt_digests[:16])
            if omitted_receipt_count:
                compact_linkage["consumption_receipt_digests_digest"] = full_receipt_digest
                compact_linkage["consumption_receipt_digests_omitted"] = omitted_receipt_count
        raw_event_times = original.get("event_times", ())
        event_times = raw_event_times if isinstance(raw_event_times, (list, tuple)) else ()
        selected_times = list(event_times[-16:])
        projection_posture = "complete" if not omitted_history_count and not omitted_history_digest_count \
            and not omitted_receipt_count \
            and context.get("history_lineage_posture") != "source_record_identity_pairs_incomplete" \
            and len(event_times) <= 16 else "bounded_context_incomplete"
        summary = {
            "resource_linkage": compact_linkage,
            "resource_record": original.get("resource_record"),
            "allocation_identity": original.get("allocation_identity"),
            "invocation_receipt_id": original.get("invocation_receipt_id"),
            "invocation_receipt_digest": original.get("invocation_receipt_digest"),
            "principal_id": original.get("principal_id"),
            "principal_binding_digest": original.get("principal_binding_digest"),
            "model_attribution": original.get("model_attribution"),
            "software_attribution": original.get("software_attribution"),
            "model_replacement_run_id": original.get("model_replacement_run_id"),
            "model_replacement_run_digest": original.get("model_replacement_run_digest"),
            "model_replacement_source_record_id": original.get("model_replacement_source_record_id"),
            "model_replacement_source_record_digest": original.get(
                "model_replacement_source_record_digest"),
            "model_replacement_condition": original.get("model_replacement_condition"),
            "model_identity_digest": original.get("model_identity_digest"),
            "model_provenance_manifest_digest": original.get("model_provenance_manifest_digest"),
            "causal_context_id": original.get("causal_context_id"),
            "causal_context_digest": original.get("causal_context_digest"),
            "task_context": context,
            "event_times": selected_times,
            "lineage_findings": list(original.get("lineage_findings", ()))[:16],
            "shared_host_cpu_gpu_attribution": original.get("shared_host_cpu_gpu_attribution"),
            "interpretation": original.get("interpretation"),
            "current_truth": False, "authority": False,
            "lineage_projection_posture": projection_posture,
        }
        projection_binding = {"schema_version": "sentientos.resource_interpretation_projection:v1",
            "source_fact_id": str(fact.get("fact_id", "")),
            "source_payload_digest": digest(dict(original)),
            "source_record_digest": str(source.get("digest", "")),
            "projected_payload_digest": digest(summary)}
        projection_binding["projection_digest"] = digest(projection_binding)
        summary["interpretation_projection"] = projection_binding
        projected = dict(fact)
        projected["payload"] = summary
        return projected
    if (subject.get("subject_kind") != "causal_resource_consumption"
            or not isinstance(original.get("ledger_digest"), str)):
        return dict(fact)
    allocations = tuple(item for item in original.get("allocations", ()) if isinstance(item, Mapping))
    attempts = tuple(item for item in original.get("attempts", ()) if isinstance(item, Mapping))
    receipts = tuple(item for item in original.get("consumption_receipts", ()) if isinstance(item, Mapping))
    invocations = tuple(item for item in original.get("invocation_receipts", ()) if isinstance(item, Mapping))
    selected_receipts = receipts[-4:]
    selected_invocations = invocations[-4:]
    selected_attempts = attempts[-8:]
    compact_allocations = tuple({key: item.get(key) for key in
        ("allocation_id", "allocation_digest", "principal_id", "principal_binding_digest",
         "resource_kind", "resource_specific_bounds", "policy_digest", "epoch") if key in item}
        for item in allocations[:4])
    compact_attempts = tuple({"attempt_id": item.get("attempt_id"),
        "allocation_id": item.get("allocation_id"), "status": item.get("status")}
        for item in selected_attempts)
    compact_receipts = tuple({key: item.get(key) for key in
        ("receipt_id", "receipt_digest", "allocation_digest", "principal_binding_digest", "attempt_id",
         "state", "observed_at", "previous_receipt_digest", "effect_receipt_digest",
         "resource_specific_measurement", "measurement_posture") if key in item}
        for item in selected_receipts)
    compact_invocations = tuple({key: item.get(key) for key in
        ("receipt_id", "receipt_digest", "request_id", "request_digest", "status", "purpose",
         "model_id", "model_artifact_digest", "observed_at", "resource_allocation_digest",
         "resource_attempt_id", "resource_consumption_receipt_digests") if key in item}
        for item in selected_invocations)
    summary = {"ledger_schema": original.get("ledger_schema"),
        "ledger_digest": original.get("ledger_digest"),
        "source_identity": original.get("source_identity", {}),
        "allocations": compact_allocations, "allocation_count": len(allocations),
        "attempts": compact_attempts, "attempt_count": len(attempts),
        "consumption_receipts": compact_receipts, "consumption_receipt_count": len(receipts),
        "invocation_receipts": compact_invocations, "invocation_receipt_count": len(invocations),
        "attribution_posture": original.get("attribution_posture"),
        "shared_host_usage_attribution": original.get("shared_host_usage_attribution"),
        "lineage_posture": original.get("lineage_posture"),
        "lineage_findings": tuple(original.get("lineage_findings", ()))[:16],
        "lineage_finding_count": int(original.get("lineage_finding_count", len(original.get("lineage_findings", ())))),
        "recovery_posture": original.get("recovery_posture"),
        "incomplete_attempt_ids": tuple(original.get("incomplete_attempt_ids", ()))[:16],
        "incomplete_attempt_count": int(original.get("incomplete_attempt_count",
            len(original.get("incomplete_attempt_ids", ())))),
        "retention_posture": original.get("retention_posture"),
        "interpretation_projection_posture": ("complete" if len(allocations) <= 4 and len(attempts) <= 8
            and len(receipts) <= 4 and len(invocations) <= 4
            and int(original.get("lineage_finding_count", len(original.get("lineage_findings", ())))) <= 16
            and int(original.get("incomplete_attempt_count", len(original.get("incomplete_attempt_ids", ())))) <= 16
            else "bounded_tail_incomplete")}
    projection_binding={"schema_version":"sentientos.resource_interpretation_projection:v1",
        "source_fact_id":str(fact.get("fact_id", "")),
        "source_payload_digest":digest(dict(original)),
        "source_record_digest":str(source.get("digest", "")),
        "projected_payload_digest":digest(summary)}
    projection_binding["projection_digest"]=digest(projection_binding)
    summary["interpretation_projection"]=projection_binding
    projected = dict(fact)
    projected["payload"] = summary
    return projected


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
    selected_facts: tuple[Mapping[str, Any], ...] = ()
    candidate_id: str = ""
    candidate_digest: str = ""

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("candidate_id"); value.pop("candidate_digest")
        # Historical candidates predate payload retention. Preserve their
        # content identities while new records carry exact selected evidence.
        if not self.selected_facts:
            value.pop("selected_facts", None)
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
        try:
            existing = self._read_json(path)
        except DevelopmentalWritebackError as exc:
            if str(exc) != "stored_payload_missing":
                raise
            existing = None
        if existing is not None:
            if digest_payload(existing) != digest_payload(payload):
                raise DevelopmentalWritebackError("record_identity_collision")
            return record
        if os.name != "posix":
            raise DevelopmentalWritebackError("durable_record_publication_unsupported_platform")
        atomic_write_json(path, payload)
        if self.get(record.record_id).record_digest != record.record_digest:
            raise DevelopmentalWritebackError("durable_record_verification_failed")
        return record

    def get(self, record_id: str) -> DevelopmentalRecord:
        if not _valid_store_identity(record_id, "devrec"):
            raise DevelopmentalWritebackError("record_identity_invalid")
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
        try:
            existing = self._read_json(path)
        except DevelopmentalWritebackError as exc:
            if str(exc) != "stored_payload_missing":
                raise
            existing = None
        if existing is not None and digest_payload(existing) != digest_payload(payload):
            raise DevelopmentalWritebackError("receipt_identity_collision")
        if existing is None:
            if os.name != "posix":
                raise DevelopmentalWritebackError("durable_receipt_publication_unsupported_platform")
            atomic_write_json(path, payload)
        if self.get_receipt(receipt.receipt_id).receipt_digest != receipt.receipt_digest:
            raise DevelopmentalWritebackError("durable_receipt_verification_failed")
        return receipt

    def get_receipt(self, receipt_id: str) -> WritebackReceipt:
        if not _valid_store_identity(receipt_id, "devreceipt"):
            raise DevelopmentalWritebackError("receipt_identity_invalid")
        try: receipt = WritebackReceipt(**self._read_json(self.receipts_root / f"{receipt_id}.json"))
        except (OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise DevelopmentalWritebackError("receipt_missing_or_corrupt") from exc
        self._verify_receipt(receipt); return receipt

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if os.name == "nt":
            try:
                entries = read_regular_files(path.parent, max_entries=1,
                    max_file_bytes=MAX_DURABLE_RECORD_BYTES, max_total_bytes=MAX_DURABLE_RECORD_BYTES,
                    selected_names=(path.name,))
            except WindowsHandleCustodyError as exc:
                if str(exc) == "explicit_file_missing":
                    raise DevelopmentalWritebackError("stored_payload_missing") from exc
                raise DevelopmentalWritebackError("stored_payload_windows_recovery_failed") from exc
            if len(entries) != 1 or entries[0][0] != path.name:
                raise DevelopmentalWritebackError("stored_payload_missing")
            data = entries[0][1]
        else:
            descriptor: int | None = None
            try:
                descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                                     | getattr(os, "O_NONBLOCK", 0))
                before = os.fstat(descriptor)
                if (not stat.S_ISREG(before.st_mode) or before.st_size > MAX_DURABLE_RECORD_BYTES
                        or before.st_nlink != 1):
                    raise DevelopmentalWritebackError("stored_payload_unbounded_or_not_regular")
                chunks: list[bytes] = []
                remaining = MAX_DURABLE_RECORD_BYTES + 1
                while remaining:
                    chunk = os.read(descriptor, min(65_536, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk); remaining -= len(chunk)
                data = b"".join(chunks)
                after = os.fstat(descriptor)
                if (len(data) != before.st_size or after.st_size != before.st_size
                        or after.st_mtime_ns != before.st_mtime_ns
                        or after.st_dev != before.st_dev or after.st_ino != before.st_ino):
                    raise DevelopmentalWritebackError("stored_payload_changed_during_read")
            except OSError as exc:
                if isinstance(exc, FileNotFoundError):
                    raise DevelopmentalWritebackError("stored_payload_missing") from exc
                raise DevelopmentalWritebackError("stored_payload_unavailable") from exc
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        value = json.loads(data.decode("utf-8"))
        if not isinstance(value, dict): raise DevelopmentalWritebackError("stored_payload_not_object")
        if json.dumps(value, sort_keys=True, indent=2).encode("utf-8") + b"\n" != data:
            raise DevelopmentalWritebackError("stored_payload_noncanonical")
        return value

    def records(self) -> tuple[DevelopmentalRecord, ...]:
        if not self.records_root.exists():
            return ()
        if self.records_root.is_symlink() or not self.records_root.is_dir():
            raise DevelopmentalWritebackError("durable_record_root_invalid")
        if os.name == "nt":
            try:
                entries = read_regular_files(self.records_root,
                    max_entries=MAX_DURABLE_RECORDS, max_file_bytes=MAX_DURABLE_RECORD_BYTES,
                    max_total_bytes=MAX_DURABLE_RECORD_ROOT_BYTES)
            except WindowsHandleCustodyError as exc:
                raise DevelopmentalWritebackError("durable_record_windows_recovery_failed") from exc
            recovered: list[DevelopmentalRecord] = []
            for name, data in entries:
                try:
                    payload = json.loads(data.decode("utf-8"))
                    if (not isinstance(payload, dict)
                            or json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n" != data):
                        raise DevelopmentalWritebackError("stored_payload_noncanonical")
                    record = DevelopmentalRecord(**payload)
                except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
                    raise DevelopmentalWritebackError("record_missing_or_corrupt") from exc
                self._verify_record(record)
                if name != record.record_id + ".json":
                    raise DevelopmentalWritebackError("durable_record_path_identity_mismatch")
                recovered.append(record)
            return tuple(recovered)
        paths = sorted(self.records_root.glob("*.json"))
        if len(paths) > MAX_DURABLE_RECORDS:
            raise DevelopmentalWritebackError("durable_record_limit_exceeded")
        records = tuple(self.get(path.stem) for path in paths)
        total_bytes = sum(len(json.dumps(asdict(record), sort_keys=True, indent=2).encode("utf-8") + b"\n")
                          for record in records)
        if total_bytes > MAX_DURABLE_RECORD_ROOT_BYTES:
            raise DevelopmentalWritebackError("durable_record_root_size_limit_exceeded")
        if any(path.stem != record.record_id for path, record in zip(paths, records)):
            raise DevelopmentalWritebackError("durable_record_path_identity_mismatch")
        return records

    def receipts(self) -> tuple[WritebackReceipt, ...]:
        """Recover the bounded receipt collection without creating or repairing custody."""
        if not self.receipts_root.exists():
            return ()
        if self.receipts_root.is_symlink() or not self.receipts_root.is_dir():
            raise DevelopmentalWritebackError("durable_receipt_root_invalid")
        if os.name == "nt":
            try:
                entries = read_regular_files(self.receipts_root,
                    max_entries=MAX_DURABLE_RECORDS, max_file_bytes=MAX_DURABLE_RECORD_BYTES,
                    max_total_bytes=MAX_DURABLE_RECORD_ROOT_BYTES)
            except WindowsHandleCustodyError as exc:
                raise DevelopmentalWritebackError("durable_receipt_windows_recovery_failed") from exc
            recovered: list[WritebackReceipt] = []
            for name, data in entries:
                try:
                    payload = json.loads(data.decode("utf-8"))
                    if (not isinstance(payload, dict)
                            or json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n" != data):
                        raise DevelopmentalWritebackError("stored_payload_noncanonical")
                    receipt = WritebackReceipt(**payload)
                except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
                    raise DevelopmentalWritebackError("receipt_missing_or_corrupt") from exc
                self._verify_receipt(receipt)
                if name != receipt.receipt_id + ".json":
                    raise DevelopmentalWritebackError("durable_receipt_path_identity_mismatch")
                recovered.append(receipt)
            return tuple(recovered)
        paths = sorted(self.receipts_root.glob("*.json"))
        if len(paths) > MAX_DURABLE_RECORDS:
            raise DevelopmentalWritebackError("durable_receipt_limit_exceeded")
        receipts = tuple(self.get_receipt(path.stem) for path in paths)
        total_bytes = sum(len(json.dumps(asdict(receipt), sort_keys=True, indent=2).encode("utf-8") + b"\n")
                          for receipt in receipts)
        if total_bytes > MAX_DURABLE_RECORD_ROOT_BYTES:
            raise DevelopmentalWritebackError("durable_receipt_root_size_limit_exceeded")
        if any(path.stem != receipt.receipt_id for path, receipt in zip(paths, receipts)):
            raise DevelopmentalWritebackError("durable_receipt_path_identity_mismatch")
        return receipts

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
        facts = tuple(_resource_interpretation_projection(to_dict(facts_by_id[fid]))
                      for fid in sorted(requested))
        source_ids = {str(fact["source"]["source_id"]) for fact in facts}
        sources_by_id = {source.source_id: source for source in snapshot.sources}
        if any(sid not in sources_by_id for sid in source_ids): raise DevelopmentalWritebackError("selected_source_not_in_snapshot")
        sources = tuple(to_dict(sources_by_id[sid]) for sid in sorted(source_ids))
        for fact in facts:
            source = sources_by_id[str(fact["source"]["source_id"])]
            if fact["source"] != to_dict(source): raise DevelopmentalWritebackError("selected_source_provenance_mismatch")
        conflicts = tuple(to_dict(c) for c in snapshot.conflicts if set(c.fact_ids) & set(requested))
        raw = SelectedEvidence(snapshot.snapshot_id, snapshot.digest, facts, sources, conflicts)
        encoded_size = len(json.dumps(raw.semantic_payload(), sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        if encoded_size > MAX_SELECTED_EVIDENCE_BYTES:
            raise DevelopmentalWritebackError("selected_evidence_unbounded")
        sid, digest = _identity("devsel", raw.semantic_payload())
        return replace(raw, selection_id=sid, selection_digest=digest)

    @staticmethod
    def infer_candidate(selection: SelectedEvidence, *, invoker: LocalModelInvoker,
                        correlation_id: str, budget: LocalModelInvocationBudget | None = None) -> DevelopmentalCandidate:
        bounded = budget or LocalModelInvocationBudget(max_input_chars=8000, max_output_chars=4000, max_new_tokens=512, timeout_seconds=30, max_calls_per_correlation=1)
        if bounded.max_calls_per_correlation != 1 or bounded.max_input_chars > 8000 or bounded.max_output_chars > 4000 or bounded.max_new_tokens > 512 or bounded.timeout_seconds > 30:
            raise DevelopmentalWritebackError("developmental_inference_budget_unbounded")
        schema = {"type":"object", "required":["interpretation","uncertainty"], "additionalProperties":False,
                  "properties":{"interpretation":{"type":"string","maxLength":MAX_INTERPRETATION_CHARS},
                                "uncertainty":{"type":"string","enum":["low","medium","high","unknown"]}}}
        request = invoker.build_request(purpose=PURPOSE, prompt=json.dumps({"instruction":("Interpret selected historical evidence without asserting truth, authority, policy, goals, or storage. "
            "Keep provenance and uncertainty attached to each interpretation. For resource evidence, distinguish measured, "
            "estimated, predicted, and unknown values by their source posture; shared host usage is not invocation attribution. "
            "Resource expenditure is not inherently good or bad and must not become a reward, penalty, or objective."),
            "selection":selection.semantic_payload()}, sort_keys=True), caller=PRINCIPAL, correlation_id=correlation_id, expected_output_format="json", budget=bounded, upstream_evidence={"selection_id":selection.selection_id,"selection_digest":selection.selection_digest,"snapshot_id":selection.snapshot_id,"snapshot_digest":selection.snapshot_digest}, linkage={"transformation":"selected_world_state_to_historical_interpretation"}, structured_output_schema=schema)
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
        raw = DevelopmentalCandidate(output["interpretation"], output["uncertainty"], "untrusted_historical_interpretation_candidate", selection.snapshot_id, selection.snapshot_digest, selection.selection_id, selection.selection_digest, tuple(str(f["fact_id"]) for f in selection.facts), selection.sources, str(req["model_id"]), req.get("model_artifact_digest"), str(req["request_id"]), str(req["request_digest"]), receipt.receipt_id, receipt.receipt_digest, receipt.output_digest, {"kind":"governed_local_model_transformation", "purpose":PURPOSE, "selected_evidence_digest":selection.selection_digest}, tuple(selection.facts))
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

    def recover_completed_records(self) -> tuple[tuple[DevelopmentalRecord, WritebackReceipt], ...]:
        """Verify durable records and restore only their deterministic receipt metadata."""
        recovered: list[tuple[DevelopmentalRecord, WritebackReceipt]] = []
        for record in self.store.records():
            try:
                candidate_payload = dict(record.candidate)
                candidate_payload["selected_fact_ids"] = tuple(candidate_payload["selected_fact_ids"])
                candidate_payload["selected_sources"] = tuple(candidate_payload["selected_sources"])
                candidate_payload["selected_facts"] = tuple(candidate_payload.get("selected_facts", ()))
                candidate = DevelopmentalCandidate(**candidate_payload)
            except (KeyError, TypeError, ValueError) as exc:
                raise DevelopmentalWritebackError("durable_candidate_reconstruction_failed") from exc
            candidate_id, candidate_digest = _identity("devcand", candidate.semantic_payload())
            if (candidate.candidate_id, candidate.candidate_digest) != (candidate_id, candidate_digest):
                raise DevelopmentalWritebackError("durable_candidate_digest_mismatch")
            if (not candidate.selected_fact_ids or len(candidate.selected_fact_ids) > MAX_SELECTED_FACTS
                    or len(set(candidate.selected_fact_ids)) != len(candidate.selected_fact_ids)
                    or any(not isinstance(item, str) or not item for item in candidate.selected_fact_ids)):
                raise DevelopmentalWritebackError("durable_candidate_fact_bounds_invalid")
            if candidate.selected_facts:
                if (len(candidate.selected_facts) != len(candidate.selected_fact_ids)
                        or any(not isinstance(fact, Mapping) for fact in candidate.selected_facts)
                        or any(not isinstance(source, Mapping) for source in candidate.selected_sources)
                        or tuple(str(fact.get("fact_id", "")) for fact in candidate.selected_facts)
                            != candidate.selected_fact_ids
                        or len(json.dumps([dict(fact) for fact in candidate.selected_facts], sort_keys=True,
                            separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
                            > MAX_SELECTED_EVIDENCE_BYTES):
                    raise DevelopmentalWritebackError("durable_candidate_fact_payload_invalid")
                selected_sources = {str(source.get("source_id", "")): dict(source)
                                    for source in candidate.selected_sources}
                for fact in candidate.selected_facts:
                    source = fact.get("source")
                    subject = fact.get("subject")
                    if (set(fact) != {"fact_id", "subject", "stage", "disposition", "evidence_strength",
                                      "source", "payload", "effect_claimed", "effect_proven", "observed_at"}
                            or not isinstance(source, Mapping) or not isinstance(subject, Mapping)
                            or set(subject) != {"subject_id", "subject_kind", "labels"}
                            or not isinstance(subject.get("subject_id"), str)
                            or not isinstance(subject.get("subject_kind"), str)
                            or not isinstance(subject.get("labels"), list)
                            or not isinstance(fact.get("stage"), str)
                            or not isinstance(fact.get("disposition"), str)
                            or not isinstance(fact.get("evidence_strength"), str)
                            or type(fact.get("effect_claimed")) is not bool
                            or type(fact.get("effect_proven")) is not bool
                            or selected_sources.get(str(source.get("source_id", ""))) != dict(source)
                            or not isinstance(fact.get("payload"), Mapping)
                            or not isinstance(source.get("source_id"), str)
                            or not isinstance(source.get("digest"), str)
                            or len(source["digest"]) != 64
                            or any(character not in "0123456789abcdef" for character in source["digest"])):
                        raise DevelopmentalWritebackError("durable_candidate_fact_source_mismatch")
                    payload_value = dict(fact["payload"])
                    projection = payload_value.pop("interpretation_projection", None)
                    if projection is None:
                        expected_id = "fact-" + digest((dict(subject), fact.get("stage"),
                            fact.get("disposition"), source.get("digest"), dict(fact["payload"]),
                            fact.get("effect_claimed"), fact.get("effect_proven")))[:16]
                        if fact.get("fact_id") != expected_id:
                            raise DevelopmentalWritebackError("durable_candidate_fact_identity_mismatch")
                    else:
                        if (not isinstance(projection, Mapping)
                                or set(projection) != {"schema_version", "source_fact_id", "source_payload_digest",
                                    "source_record_digest", "projected_payload_digest", "projection_digest"}
                                or projection.get("schema_version") not in {
                                    "sentientos.resource_interpretation_projection:v1",
                                    "sentientos.runtime_history_projection:v1"}
                                or (projection.get("schema_version")
                                    == "sentientos.runtime_history_projection:v1"
                                    and source.get("kind") != "runtime_supervisor")
                                or projection.get("source_fact_id") != fact.get("fact_id")
                                or projection.get("source_record_digest") != source.get("digest")
                                or projection.get("projected_payload_digest") != digest(payload_value)):
                            raise DevelopmentalWritebackError("durable_resource_projection_binding_invalid")
                        projection_semantic = dict(projection); claimed_projection = projection_semantic.pop("projection_digest")
                        if claimed_projection != digest(projection_semantic):
                            raise DevelopmentalWritebackError("durable_resource_projection_digest_mismatch")
                        source_payload_digest = str(projection.get("source_payload_digest", ""))
                        if (len(source_payload_digest) != 64
                                or any(character not in "0123456789abcdef" for character in source_payload_digest)):
                            raise DevelopmentalWritebackError("durable_resource_source_payload_digest_invalid")
            admission = self.admission_verifier.recorded_admission(record.admission_id)
            if (admission.binding_digest != record.admission_binding_digest
                    or admission.effects != EFFECTS or record.principal != PRINCIPAL
                    or admission.principal_id != PRINCIPAL
                    or admission.subject_id != candidate.candidate_id
                    or record.operation_id != "resident-developmental-writeback:" +
                        record.correlation_id.removesuffix(":resident-developmental-writeback") + ":" + candidate.candidate_id):
                raise DevelopmentalWritebackError("durable_admission_binding_mismatch")
            request_digest = self.admission_configuration_digest(candidate, operation_id=record.operation_id)
            try:
                for effect in EFFECTS:
                    self.admission_verifier.verify(admission, current_sequence=admission.issued_sequence,
                        capability_id=RESIDENT_DEVELOPMENTAL_WRITEBACK, principal_id=PRINCIPAL,
                        effect=effect, subject_id=candidate.candidate_id,
                        request_configuration_digest=request_digest)
            except AdmissionError as exc:
                raise DevelopmentalWritebackError("durable_admission_recovery_rejected") from exc
            raw = WritebackReceipt("", "", record.record_id, record.record_digest,
                candidate.candidate_id, candidate.candidate_digest, record.admission_id,
                record.admission_binding_digest, record.principal, record.operation_id, True)
            receipt_id, receipt_digest = _identity("devreceipt", raw.semantic_payload())
            receipt = self.store.write_receipt(replace(raw, receipt_id=receipt_id, receipt_digest=receipt_digest))
            recovered.append((record, receipt))
        return tuple(recovered)


def measure_changed_cognition(*, with_record: CognitionObservation, without_record: CognitionObservation,
                              expected_record_ids: Sequence[str]) -> ChangedCognitionMeasurement:
    expected = tuple(expected_record_ids)
    if not expected or with_record.retrieved_record_ids != expected or without_record.retrieved_record_ids or with_record.condition_id == without_record.condition_id:
        raise DevelopmentalWritebackError("controlled_measurement_conditions_invalid")
    payload = {"with_record":asdict(with_record),"without_record":asdict(without_record),"compared_fields":["downstream_cognition_id","downstream_cognition_digest"],"observable_difference":with_record.downstream_cognition_digest != without_record.downstream_cognition_digest}
    mid, digest = _identity("devmeasure", payload)
    return ChangedCognitionMeasurement(mid, digest, asdict(with_record), asdict(without_record), ("downstream_cognition_id","downstream_cognition_digest"), bool(payload["observable_difference"]))
