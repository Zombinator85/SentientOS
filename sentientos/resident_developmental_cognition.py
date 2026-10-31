"""One-tick resident composition for bounded developmental history.

The owner has no cadence of its own.  ``sentientosd`` supplies an exact
World-State snapshot and tick identity.  History is non-authoritative context;
it is never canonical explicit-user retention.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator, Mapping, Sequence, cast

from .codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from .governed_local_model_invocation import (
    LocalModelInvocationBudget, LocalModelInvocationReceipt, LocalModelInvoker,
    RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA,
    RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA, validate_receipt,
)
from .canonical_memory import sentientos_memory_dir
from .developmental_history_intervention_experiment import (
    CONDITION_ORDER,
    DevelopmentalExperimentStore, DevelopmentalHistoryInterventionError,
    HISTORY_SELECTION_SCHEMA, OBJECTIVE_HISTORY_SELECTION_SCHEMA,
    OBJECTIVE_SCHEMA, OBJECTIVE_SCHEMAS, make_protocol, objective_task_contamination_assessment, summarize,
    summarize_objective_task,
    PURPOSE as EXPERIMENT_PURPOSE,
)
from .local_model_authority import digest_payload
from .private_file_custody import (PrivateFileCustodyError, list_bounded_json_names_at,
    open_private_directory, publish_immutable_bytes, read_private_file_at,
    replace_private_bytes)
from .platform_fcntl import fcntl, require_flock
from .longitudinal_self_model import CognitiveSelfModelProjection
from .persistent_epistemic_state import (EpistemicCognitiveProjection,
    MeaningBearingEpistemicCognitiveProjection, semantic_packets_for_projection,
    validate_cognitive_projection)
from .resident_developmental_writeback import (
    EFFECTS,
    PRINCIPAL,
    CognitionObservation,
    DevelopmentalHistoryProjection,
    DevelopmentalWritebackError,
    COGNITION_LESSON_PROVENANCE_KIND,
    ResidentDevelopmentalWritebackController,
    measure_changed_cognition,
    _open_store_directory,
    _read_store_file,
    _publish_store_json,
)
from .runtime_admission import RuntimeAdmissionAuthority
from .world_state_board import WorldStateSnapshot, digest as _world_state_digest, validate_snapshot


def _parse_cognition_lesson_output(text: str, consumed_ids: set[str]) -> Mapping[str, Any]:
    """Accept only a complete, exact-output lesson packet bound to consumed evidence."""
    if (not isinstance(text, str) or not text
            or len(text.encode("utf-8")) > MAX_COGNITION_CONCLUSION_BYTES):
        raise ValueError("cognition_lesson_output_unbounded")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("cognition_lesson_duplicate_key")
            result[key] = value
        return result

    payload = json.loads(text, object_pairs_hook=unique_object)
    if (not isinstance(payload, dict)
            or set(payload) != {"conclusion", "lesson_candidate"}
            or not isinstance(payload["conclusion"], str)
            or not payload["conclusion"].strip()
            or len(payload["conclusion"]) > 2500):
        raise ValueError("cognition_lesson_shape_invalid")
    lesson = payload["lesson_candidate"]
    if lesson is None:
        return payload
    expected = {"statement", "scope", "applicability", "uncertainty",
                "uncertainty_rationale", "evidence_dependencies",
                "possible_contradiction_ids"}
    if not isinstance(lesson, dict) or set(lesson) != expected:
        raise ValueError("cognition_lesson_shape_invalid")
    for key, maximum in (("statement", 1200), ("scope", 400),
                         ("applicability", 500), ("uncertainty_rationale", 500)):
        value = lesson.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError("cognition_lesson_text_invalid")
    if lesson.get("uncertainty") not in {"low", "medium", "high", "unknown"}:
        raise ValueError("cognition_lesson_uncertainty_invalid")
    dependencies = lesson.get("evidence_dependencies")
    contradictions = lesson.get("possible_contradiction_ids")
    if (not isinstance(dependencies, list) or not 1 <= len(dependencies) <= 8
            or len(set(dependencies)) != len(dependencies)
            or any(not isinstance(item, str) or not item or len(item) > 256 for item in dependencies)
            or not isinstance(contradictions, list) or len(contradictions) > 8
            or len(set(contradictions)) != len(contradictions)
            or any(not isinstance(item, str) or not item or len(item) > 256 for item in contradictions)
            or not set(dependencies).issubset(consumed_ids)
            or not set(contradictions).issubset(consumed_ids)):
        raise ValueError("cognition_lesson_evidence_binding_invalid")
    return payload


def _aware_event_time(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    # RFC 3339 -00:00 means the producer's UTC offset is unknown. Treating it
    # as UTC would make an uncertain cognition event appear chronologically
    # comparable to other observations.
    if value.endswith("-00:00"):
        return False
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (OverflowError, ValueError):
        return False
    return instant.tzinfo is not None and instant.utcoffset() is not None


def _resource_linkage_fields(receipt: Any) -> dict[str, Any]:
    """Return only receipt-authenticated resource identities; never infer usage."""
    allocation = getattr(receipt, "resource_allocation_digest", None)
    attempt = getattr(receipt, "resource_attempt_id", None)
    consumption = getattr(receipt, "resource_consumption_receipt_digests", ())
    linkage_digest = getattr(receipt, "resource_linkage_digest", None)
    if allocation is None and attempt is None and not consumption and linkage_digest is None:
        return {"resource_allocation_digest": None, "resource_attempt_id": None,
            "resource_consumption_receipt_digests": (), "resource_linkage_digest": None}
    if (not isinstance(allocation, str) or not allocation
            or not isinstance(attempt, str) or not attempt
            or not isinstance(consumption, (tuple, list)) or not 1 <= len(consumption) <= 8
            or any(not isinstance(item, str) or len(item) != 64
                or any(char not in "0123456789abcdef" for char in item) for item in consumption)
            or not isinstance(linkage_digest, str) or len(linkage_digest) != 64
            or any(char not in "0123456789abcdef" for char in linkage_digest)):
        raise ResidentDevelopmentalCognitionError("cognition_resource_linkage_incomplete")
    receipt_digest = getattr(receipt, "receipt_digest", None)
    expected = digest_payload({"receipt_digest": receipt_digest,
        "allocation_digest": allocation, "attempt_id": attempt,
        "consumption_receipt_digests": tuple(consumption)})
    if not isinstance(receipt_digest, str) or linkage_digest != expected:
        raise ResidentDevelopmentalCognitionError("cognition_resource_linkage_digest_mismatch")
    return {"resource_allocation_digest": allocation, "resource_attempt_id": attempt,
        "resource_consumption_receipt_digests": tuple(consumption),
        "resource_linkage_digest": linkage_digest}


def _validate_observation_resource_linkage(value: Mapping[str, Any]) -> None:
    fields = _resource_linkage_fields(SimpleNamespace(**{
        "resource_allocation_digest": value.get("resource_allocation_digest"),
        "resource_attempt_id": value.get("resource_attempt_id"),
        "resource_consumption_receipt_digests": value.get("resource_consumption_receipt_digests", ()),
        "resource_linkage_digest": value.get("resource_linkage_digest"),
        "receipt_digest": value.get("inference_receipt_digest")}))
    if (fields["resource_allocation_digest"] != value.get("resource_allocation_digest")
            or fields["resource_attempt_id"] != value.get("resource_attempt_id")
            or tuple(fields["resource_consumption_receipt_digests"])
                != tuple(value.get("resource_consumption_receipt_digests", ()))):
        raise ResidentDevelopmentalCognitionError("cognition_resource_linkage_binding_mismatch")
from .windows_handle_custody import WindowsHandleCustodyError, read_explicit_file, read_regular_files

CONFIG_ENV = "SENTIENTOS_RESIDENT_DEVELOPMENTAL_COGNITION_CONFIG"
SCHEMA = "sentientos.resident_developmental_cognition:v1"
CONFIG_SCHEMA = "sentientos.resident_developmental_cognition_config:v1"
CONFIG_SCHEMA_V2 = "sentientos.resident_developmental_cognition_config:v2"
COGNITION_OBSERVATION_SCHEMA_V2 = "sentientos.resident_cognition_observation:v2"
COGNITION_OBSERVATION_SCHEMA_V3 = "sentientos.resident_cognition_observation:v3"
COGNITION_OBSERVATION_SCHEMA_V4 = "sentientos.resident_cognition_observation:v4"
COGNITION_OBSERVATION_SCHEMA_V5 = "sentientos.resident_cognition_observation:v5"
COGNITION_OBSERVATION_SCHEMA_V6 = "sentientos.resident_cognition_observation:v6"
COGNITION_OBSERVATION_SCHEMA_V7 = "sentientos.resident_cognition_observation:v7"
STATE_SCHEMA = "sentientos.resident_developmental_cognition_state:v2"
LEGACY_STATE_SCHEMA = "sentientos.resident_developmental_cognition_state:v1"
COGNITION_PURPOSE = "resident_developmental_retrieval_cognition"
CURRENT_PROJECTION_POLICY = "succession_identity_then_resource_and_transition_evidence_then_source_id:v3"
EXPERIMENT_CONTEXT_INSTRUCTION = (
    "Reason over four separately typed, non-authoritative substrates. Current evidence is current external observation "
    "and outranks a conflicting prior epistemic position for current-condition reasoning. Prior self-model is earlier "
    "evidence-bound system representation. Prior epistemic state is the system's earlier position, not truth or evidence. "
    "Developmental history is earlier interpretation. Preserve contradictions; none is policy, goal, permission, admission, "
    "execution, adoption, or canonical user memory. Resource expenditure is not inherently good or bad and is not a "
    "reward signal. Historical prediction-outcome lineage records bind comparison identities and bounded field outcomes; "
    "they remain claims about their recorded sources, and contradiction is material for reconsideration rather than a "
    "command to believe or act. A missing or indeterminate field is not a satisfied prediction. "
    "Treat measured, estimated, predicted, and unknown quantities according to their source posture; "
    "never infer per-invocation CPU, GPU, energy, or token measurements from shared host use, call counts, output size, "
    "or latency."
)
SELF_MODEL_QUALIFIER_INSTRUCTION = (
    " Treat every prior self-model claim's category, lifecycle stage, temporal scope, status, freshness, "
    "source observation-time metadata, current_truth, interpretation, and authority map as binding qualifiers. "
    "Retained historical or unknown evidence stays historical or unknown; reconstruction does not refresh it."
)
MAX_FACTS = 16
MAX_HISTORY = 16
MAX_RECOVERED_TICKS = 4096
MAX_RECOVERED_FACT_IDS = 65_536
MAX_COMPOSITION_STATE_BYTES = 16_777_216
MAX_COGNITION_OBSERVATIONS = 12_288
MAX_COGNITION_OBSERVATION_BYTES = 65_536
MAX_COGNITION_OBSERVATION_ROOT_BYTES = 134_217_728
MAX_RESIDENT_COGNITION_CONFIG_BYTES = 65_536
MAX_RESIDENT_COGNITION_INPUT_CHARS = 48_000
MAX_COGNITION_CONCLUSION_BYTES = 4000
LEGACY_OBJECTIVE_REQUEST_SCHEMA = "sentientos.resident_objective_intervention_request:v1"
OBJECTIVE_REQUEST_SCHEMA = "sentientos.resident_objective_intervention_request:v2"
OBJECTIVE_REQUEST_FILENAME = "pending_objective_intervention.json"
MAX_OBJECTIVE_REQUEST_BYTES = 16_384
MAX_OBJECTIVE_REQUEST_ARCHIVE_FILES = 1024
class ResidentDevelopmentalCognitionError(ValueError):
    """Fail-closed composition/configuration violation."""


class _EpistemicRevisionProbePromptPreview(Exception):
    """Internal control flow that returns a composed prompt before any call."""

    def __init__(self, prompt: str) -> None:
        super().__init__("epistemic_revision_probe_prompt_preview")
        self.prompt = prompt


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _objective_task_from_specification(specification: Any,
        commitment_nonce: str | None = None) -> Any:
    """Reconstitute only the existing bounded objective-task contract."""
    from .developmental_model_replacement_experiment import ObjectivePredictionTask

    if not isinstance(specification, Mapping):
        raise ResidentDevelopmentalCognitionError("objective_request_task_invalid")
    schema = specification.get("schema_version")
    common = {"schema_version", "multiplier", "offset"}
    if schema == "sentientos.affine_prediction_task:v1":
        if set(specification) != common | {"probe_input", "oracle_scope"}:
            raise ResidentDevelopmentalCognitionError("objective_request_task_invalid")
        if specification.get("oracle_scope") != "deterministic_fixture_not_physical_measurement":
            raise ResidentDevelopmentalCognitionError("objective_request_task_invalid")
        if commitment_nonce is not None:
            task = ObjectivePredictionTask(specification["multiplier"], specification["offset"],
                specification["probe_input"], commitment_nonce=commitment_nonce)
        else:
            task = ObjectivePredictionTask(specification["multiplier"], specification["offset"],
                specification["probe_input"])
    elif schema in {"sentientos.affine_prediction_task_suite:v2",
            "sentientos.affine_prediction_task_family_suite:v3"}:
        fields = common | {"probe_inputs", "oracle_scope"}
        if schema == "sentientos.affine_prediction_task_family_suite:v3":
            fields |= {"task_family_id", "requires_task_family_history"}
        if set(specification) != fields:
            raise ResidentDevelopmentalCognitionError("objective_request_task_invalid")
        probes = specification.get("probe_inputs")
        if (specification.get("oracle_scope") != "deterministic_fixture_not_physical_measurement"
                or not isinstance(probes, list) or not probes):
            raise ResidentDevelopmentalCognitionError("objective_request_task_invalid")
        task = ObjectivePredictionTask(specification["multiplier"], specification["offset"],
            probes[0], tuple(probes[1:]), specification.get("task_family_id"),
            specification.get("requires_task_family_history", False),
            **({"commitment_nonce": commitment_nonce} if commitment_nonce is not None else {}))
    else:
        raise ResidentDevelopmentalCognitionError("objective_request_task_schema_unsupported")
    try:
        if task.specification() != dict(specification):
            raise ResidentDevelopmentalCognitionError("objective_request_task_noncanonical")
    except (TypeError, ValueError) as exc:
        raise ResidentDevelopmentalCognitionError("objective_request_task_invalid") from exc
    return task


def objective_request_payload(*, request_id: str, task: Any) -> dict[str, Any]:
    """Build the exact staged request body; this does not authorize model use."""
    if (not isinstance(request_id, str) or not request_id or len(request_id) > 128
            or any(not (character.isascii() and (character.isalnum() or character in "_.:-"))
                   for character in request_id)):
        raise ResidentDevelopmentalCognitionError("objective_request_identity_invalid")
    try:
        specification = task.specification()
        descriptor = task.public_descriptor()
    except (AttributeError, TypeError, ValueError) as exc:
        raise ResidentDevelopmentalCognitionError("objective_request_task_invalid") from exc
    # The request is private staging custody: retain the nonce there so its
    # salted public commitment can be reproduced after restart.
    reconstructed = _objective_task_from_specification(specification, task.commitment_nonce)
    if reconstructed.public_descriptor() != descriptor:
        raise ResidentDevelopmentalCognitionError("objective_request_descriptor_mismatch")
    semantic = {"schema_version": OBJECTIVE_REQUEST_SCHEMA, "request_id": request_id,
        "task": dict(specification), "task_commitment_nonce": task.commitment_nonce,
        "task_descriptor": dict(descriptor)}
    return {**semantic, "request_digest": _digest(semantic)}


def _legacy_objective_request_digest(*, request_id: str, task: Any) -> str:
    """Verify pending v1 requests without re-exposing their legacy plain hash."""
    semantic = {"schema_version": LEGACY_OBJECTIVE_REQUEST_SCHEMA,
        "request_id": request_id, "task": task.specification(),
        "task_descriptor": task.legacy_public_descriptor()}
    return _digest(semantic)


def _parse_objective_request_bytes(raw: bytes) -> Mapping[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object)
        expected_legacy = {"schema_version", "request_id", "task", "task_descriptor", "request_digest"}
        expected_current = expected_legacy | {"task_commitment_nonce"}
        if (not isinstance(value, dict) or set(value) not in (expected_legacy, expected_current)
                or json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n" != raw
                or value.get("schema_version") not in {LEGACY_OBJECTIVE_REQUEST_SCHEMA, OBJECTIVE_REQUEST_SCHEMA}
                or (value.get("schema_version") == OBJECTIVE_REQUEST_SCHEMA and set(value) != expected_current)
                or (value.get("schema_version") == LEGACY_OBJECTIVE_REQUEST_SCHEMA and set(value) != expected_legacy)):
            raise ValueError("shape")
        semantic = {key: item for key, item in value.items() if key != "request_digest"}
        if value.get("request_digest") != _digest(semantic):
            raise ValueError("digest")
        task = _objective_task_from_specification(value["task"], value.get("task_commitment_nonce"))
        if value.get("schema_version") == OBJECTIVE_REQUEST_SCHEMA:
            if objective_request_payload(request_id=value["request_id"], task=task) != value:
                raise ValueError("binding")
        else:
            legacy_descriptor = task.legacy_public_descriptor()
            if (legacy_descriptor != value.get("task_descriptor")
                    or set(semantic) != {"schema_version", "request_id", "task", "task_descriptor"}):
                raise ValueError("legacy_binding")
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        raise ResidentDevelopmentalCognitionError("objective_request_invalid") from exc
    return value


def load_objective_request(state_root: str | Path) -> Mapping[str, Any] | None:
    """Read one explicit, bounded request from the configured cognition state root."""
    path = Path(state_root) / OBJECTIVE_REQUEST_FILENAME
    try:
        raw = read_explicit_file(path, max_bytes=MAX_OBJECTIVE_REQUEST_BYTES)
    except WindowsHandleCustodyError as exc:
        if str(exc) == "explicit_file_missing":
            return None
        raise ResidentDevelopmentalCognitionError("objective_request_custody_invalid") from exc
    except OSError as exc:
        raise ResidentDevelopmentalCognitionError("objective_request_custody_invalid") from exc
    return _parse_objective_request_bytes(raw)


def load_objective_request_by_identity(state_root: str | Path, *, request_id: str,
        request_digest: str) -> Mapping[str, Any]:
    """Recover an exact active or archived request without directory discovery."""
    pending = load_objective_request(state_root)
    if pending is not None and pending.get("request_id") == request_id:
        if pending.get("request_digest") != request_digest:
            raise ResidentDevelopmentalCognitionError("objective_request_identity_conflict")
        return pending
    archive_name = hashlib.sha256(request_id.encode("utf-8")).hexdigest() + ".json"
    archive_path = Path(state_root) / "objective_intervention_request_archive" / archive_name
    try:
        raw = read_explicit_file(archive_path, max_bytes=MAX_OBJECTIVE_REQUEST_BYTES)
    except (WindowsHandleCustodyError, OSError) as exc:
        raise ResidentDevelopmentalCognitionError("objective_request_archive_unavailable") from exc
    recovered = _parse_objective_request_bytes(raw)
    if recovered.get("request_id") != request_id or recovered.get("request_digest") != request_digest:
        raise ResidentDevelopmentalCognitionError("objective_request_archive_identity_conflict")
    return recovered


def stored_objective_request_disposition(state_root: str | Path, *,
        request_id: str, request_digest: str) -> str:
    """Read one digest-sealed tick outcome without recovery mutation."""
    try:
        record = stored_objective_request_record(state_root, request_id=request_id,
            request_digest=request_digest)
    except ResidentDevelopmentalCognitionError as exc:
        if str(exc) == "objective_request_identity_conflict":
            return "identity_conflict"
        raise
    return str(record.get("disposition", "new"))


def stored_objective_request_record(state_root: str | Path, *,
        request_id: str, request_digest: str) -> Mapping[str, Any]:
    """Read the minimal exact request/tick/run lineage from custody, without repair."""
    path = Path(state_root) / "composition_state.json"
    try:
        raw = read_explicit_file(path, max_bytes=MAX_COMPOSITION_STATE_BYTES)
    except WindowsHandleCustodyError as exc:
        if str(exc) == "explicit_file_missing":
            return {"disposition": "new", "request_id": request_id,
                "request_digest": request_digest, "authority": False}
        raise ResidentDevelopmentalCognitionError("objective_request_state_custody_invalid") from exc
    try:
        state = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object)
        if (not isinstance(state, dict)
                or json.dumps(state, indent=2, sort_keys=True).encode("utf-8") + b"\n" != raw):
            raise ValueError("noncanonical")
        claimed = state.pop("state_digest")
        if (state.get("schema") not in {STATE_SCHEMA, LEGACY_STATE_SCHEMA}
                or claimed != _digest(state)):
            raise ValueError("digest")
        completed = state.get("completed_ticks")
        incomplete = state.get("incomplete_ticks", [])
        if (not isinstance(completed, list) or not isinstance(incomplete, list)
                or any(not isinstance(row, dict) for row in completed + incomplete)):
            raise ValueError("shape")
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        raise ResidentDevelopmentalCognitionError("objective_request_state_invalid") from exc
    if len(completed) + len(incomplete) > MAX_RECOVERED_TICKS:
        raise ResidentDevelopmentalCognitionError("objective_request_state_over_bound")
    matches = [("completed" if row in completed else "interrupted", row)
        for row in completed + incomplete if row.get("objective_request_id") == request_id]
    if not matches:
        return {"disposition": "new", "request_id": request_id,
            "request_digest": request_digest, "authority": False}
    if (len(matches) != 1 or matches[0][1].get("objective_request_digest") != request_digest
            or not isinstance(matches[0][1].get("tick_id"), str)):
        raise ResidentDevelopmentalCognitionError("objective_request_identity_conflict")
    disposition, row = matches[0]
    fields = ("tick_id", "objective_request_status", "measurement_id",
        "recovered_experiment_run_id", "recovered_experiment_run_digest")
    return {"disposition": disposition, "request_id": request_id,
        "request_digest": request_digest, **{key: row.get(key) for key in fields},
        "authority": False}


def inspect_checkpointed_history_record_refs(state_path: str | Path, *,
        writeback: ResidentDevelopmentalWritebackController,
        limit: int = MAX_HISTORY,
        required_task_family_id: str | None = None,
        required_task_probe_inputs: tuple[int, ...] = ()) -> tuple[tuple[str, str], ...]:
    """Return admitted history named by completed cognition ticks, without repair.

    A valid record/receipt pair that has not yet been committed into the
    composition checkpoint is not eligible for a staged history intervention.
    The ordinary resident owner's recovery path may reconcile it later; this
    operator-side inspection never does so.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_HISTORY:
        raise ResidentDevelopmentalCognitionError("checkpointed_history_limit_invalid")
    try:
        raw = read_explicit_file(Path(state_path), max_bytes=MAX_COMPOSITION_STATE_BYTES)
    except WindowsHandleCustodyError as exc:
        if str(exc) == "explicit_file_missing":
            return ()
        raise ResidentDevelopmentalCognitionError(
            "checkpointed_history_state_unavailable") from exc
    try:
        state = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object)
        if (not isinstance(state, dict)
                or json.dumps(state, indent=2, sort_keys=True).encode("utf-8") + b"\n" != raw):
            raise ValueError("noncanonical")
        semantic = dict(state)
        claimed = semantic.pop("state_digest")
        completed = semantic.get("completed_ticks")
        incomplete = semantic.get("incomplete_ticks", [])
        processed = semantic.get("processed_selection_ids")
        if (semantic.get("schema") not in {STATE_SCHEMA, LEGACY_STATE_SCHEMA}
                or claimed != _digest(semantic)
                or not isinstance(completed, list)
                or not isinstance(incomplete, list)
                or not isinstance(processed, list)
                or any(not isinstance(row, dict) for row in completed + incomplete)
                or any(not isinstance(item, str) for item in processed)
                or len(completed) + len(incomplete) > MAX_RECOVERED_TICKS
                or len(processed) > MAX_RECOVERED_FACT_IDS):
            raise ValueError("state binding")
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        raise ResidentDevelopmentalCognitionError(
            "checkpointed_history_state_invalid") from exc

    try:
        verified = writeback.inspect_completed_records()
    except Exception as exc:
        raise ResidentDevelopmentalCognitionError(
            "checkpointed_history_admission_unavailable") from exc
    verified_by_id = {record.record_id: (record, receipt)
        for record, receipt in verified}
    if len(verified_by_id) != len(verified):
        raise ResidentDevelopmentalCognitionError(
            "checkpointed_history_identity_conflict")
    refs: list[tuple[str, str]] = []
    relevance: dict[str, int] = {}
    seen: set[str] = set()
    seen_ticks: set[str] = set()
    for row in completed:
        record_id, receipt_id = row.get("record_id"), row.get("receipt_id")
        if record_id is None and receipt_id is None:
            continue
        tick_id = row.get("tick_id")
        if (not isinstance(record_id, str) or not record_id
                or not isinstance(receipt_id, str) or not receipt_id
                or not isinstance(tick_id, str) or not tick_id
                or record_id in seen or tick_id in seen_ticks):
            raise ResidentDevelopmentalCognitionError(
                "checkpointed_history_reference_invalid")
        pair = verified_by_id.get(record_id)
        if pair is None or pair[1].receipt_id != receipt_id:
            raise ResidentDevelopmentalCognitionError(
                "checkpointed_history_reference_unverified")
        candidate = pair[0].candidate
        expected_operation_id = (
            f"resident-developmental-writeback:{tick_id}:{candidate.get('candidate_id')}"
            if isinstance(candidate, Mapping) else None)
        if (not isinstance(candidate, Mapping)
                or row.get("snapshot_id") != candidate.get("snapshot_id")
                or row.get("snapshot_digest") != candidate.get("snapshot_digest")
                or pair[0].operation_id != expected_operation_id):
            raise ResidentDevelopmentalCognitionError(
                "checkpointed_history_tick_binding_invalid")
        if required_task_family_id is not None:
            selected_facts = candidate.get("selected_facts", ())
            family_matches = any(
                isinstance(fact, Mapping)
                and isinstance(fact.get("payload"), Mapping)
                and fact["payload"].get("objective_task_family") == required_task_family_id
                for fact in selected_facts)
            if family_matches:
                refs.append((record_id, pair[0].record_digest))
                examples = [fact.get("payload", {}).get("acquisition_examples", ())
                    for fact in selected_facts if isinstance(fact, Mapping)
                    and isinstance(fact.get("payload"), Mapping)
                    and fact["payload"].get("objective_task_family") == required_task_family_id]
                probes = set(required_task_probe_inputs)
                relevance[record_id] = len({item.get("probe_input") for rows in examples
                    if isinstance(rows, (list, tuple)) for item in rows
                    if isinstance(item, Mapping) and type(item.get("probe_input")) is int
                    and item.get("probe_input") in probes})
        else:
            refs.append((record_id, pair[0].record_digest))
        seen.add(record_id)
        seen_ticks.add(tick_id)
    if required_task_family_id is not None and not refs:
        raise ResidentDevelopmentalCognitionError(
            "checkpointed_history_relevant_experience_missing")
    if required_task_family_id is not None and required_task_probe_inputs:
        checkpoint_order = {record_id: index for index, (record_id, _) in enumerate(refs)}
        ranked = sorted(refs, key=lambda item: (
            relevance.get(item[0], -1), checkpoint_order[item[0]]), reverse=True)
        retained_ids = {record_id for record_id, _ in ranked[:limit]}
        refs = [item for item in refs if item[0] in retained_ids]
    return tuple(refs[-limit:])


def objective_task_for_request(request: Mapping[str, Any]) -> Any:
    """Return a task object only after validating the complete staged request."""
    request_id = request.get("request_id") if isinstance(request, Mapping) else None
    if not isinstance(request_id, str):
        raise ResidentDevelopmentalCognitionError("objective_request_invalid")
    task = _objective_task_from_specification(request.get("task"),
        request.get("task_commitment_nonce"))
    if request.get("schema_version") == LEGACY_OBJECTIVE_REQUEST_SCHEMA:
        semantic = {key: request.get(key) for key in
            ("schema_version", "request_id", "task", "task_descriptor")}
        valid = (task.legacy_public_descriptor() == request.get("task_descriptor")
            and request.get("request_digest") == _digest(semantic))
    else:
        valid = objective_request_payload(request_id=request_id, task=task) == dict(request)
    if not valid:
        raise ResidentDevelopmentalCognitionError("objective_request_invalid")
    return task


def stage_objective_request(state_root: str | Path, *, request_id: str,
        task: Any) -> Path:
    """Atomically stage one bounded request without invoking or authorizing a model."""
    payload = objective_request_payload(request_id=request_id, task=task)
    path = Path(state_root) / OBJECTIVE_REQUEST_FILENAME
    data = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    try:
        existing = read_explicit_file(path, max_bytes=MAX_OBJECTIVE_REQUEST_BYTES)
    except WindowsHandleCustodyError as exc:
        if str(exc) != "explicit_file_missing":
            raise ResidentDevelopmentalCognitionError("objective_request_custody_invalid") from exc
        existing = None
    if existing is not None:
        current = load_objective_request(state_root)
        assert current is not None
        if existing == data:
            return path
        if current.get("request_id") == request_id:
            raise ResidentDevelopmentalCognitionError("objective_request_identity_conflict")
        prior_disposition = stored_objective_request_disposition(state_root,
            request_id=str(current["request_id"]), request_digest=str(current["request_digest"]))
        if prior_disposition not in {"completed", "interrupted"}:
            raise ResidentDevelopmentalCognitionError("objective_request_slot_occupied")
        archive_root = Path(state_root) / "objective_intervention_request_archive"
        archive_name = hashlib.sha256(str(current["request_id"]).encode("utf-8")).hexdigest() + ".json"
        archive_path = archive_root / archive_name
        directory_fd: int | None = None
        try:
            directory_fd = open_private_directory(archive_root, create=True)
            names = list_bounded_json_names_at(directory_fd,
                max_entries=MAX_OBJECTIVE_REQUEST_ARCHIVE_FILES,
                max_directory_entries=MAX_OBJECTIVE_REQUEST_ARCHIVE_FILES * 2)
            if archive_name not in names and len(names) >= MAX_OBJECTIVE_REQUEST_ARCHIVE_FILES:
                raise ResidentDevelopmentalCognitionError("objective_request_archive_retention_limit")
            publish_immutable_bytes(archive_path, existing,
                max_bytes=MAX_OBJECTIVE_REQUEST_BYTES,
                collision_code="objective_request_archive_identity_conflict")
        except (PrivateFileCustodyError, OSError) as exc:
            raise ResidentDevelopmentalCognitionError("objective_request_archive_publication_failed") from exc
        finally:
            if directory_fd is not None:
                os.close(directory_fd)
    if stored_objective_request_disposition(state_root,
            request_id=request_id, request_digest=str(payload["request_digest"])) != "new":
        raise ResidentDevelopmentalCognitionError("objective_request_identity_reused")
    try:
        replace_private_bytes(path, data, max_bytes=MAX_OBJECTIVE_REQUEST_BYTES)
    except PrivateFileCustodyError as exc:
        raise ResidentDevelopmentalCognitionError("objective_request_publication_failed") from exc
    return path


def _resolved_owner_root(value: str | Path) -> Path:
    try:
        return Path(value).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ResidentDevelopmentalCognitionError("configuration_root_identity_invalid") from exc


def _validate_root_separation(history_root: Path, state_root: Path,
                              artifact_root: Path | None = None,
                              memory_root: Path | None = None) -> None:
    """Keep developmental custody disjoint from sibling owners and canonical memory."""
    roots = [_resolved_owner_root(history_root), _resolved_owner_root(state_root)]
    if artifact_root is not None:
        roots.append(_resolved_owner_root(artifact_root))
    for index, left in enumerate(roots):
        if any(left == right or left in right.parents or right in left.parents
               for right in roots[index + 1:]):
            raise ResidentDevelopmentalCognitionError("configuration_roots_must_be_separate")
    canonical_memory_root = _resolved_owner_root(
        memory_root if memory_root is not None else sentientos_memory_dir())
    if any(root == canonical_memory_root
               or canonical_memory_root in root.parents
               or root in canonical_memory_root.parents
               for root in roots):
        raise ResidentDevelopmentalCognitionError(
            "configuration_root_overlaps_canonical_memory")


def _replace_cognition_state(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically replace mutable cognition state through shared private custody."""
    data = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    try:
        replace_private_bytes(path, data, max_bytes=MAX_COMPOSITION_STATE_BYTES)
    except PrivateFileCustodyError as exc:
        raise ResidentDevelopmentalCognitionError(
            "composition_state_publication_failed") from exc


def _digest(value: Any) -> str:
    return "sha256:" + str(digest_payload(value))


def _valid_optional_lower_sha256(value: Any) -> bool:
    return (value is None or (type(value) is str and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)))


def _valid_lower_sha256(value: Any) -> bool:
    return (type(value) is str and len(value) == 64
        and all(character in "0123456789abcdef" for character in value))


def _valid_integrity_controller_gates(payload: Mapping[str, Any]) -> bool:
    gates = payload.get("gate_results")
    count = payload.get("gate_count")
    return (type(count) is int and 0 <= count <= 32
        and isinstance(gates, list) and len(gates) == count
        and all(isinstance(gate, Mapping)
            and isinstance(gate.get("name"), str)
            and 0 < len(gate["name"]) <= 64
            and gate.get("status") in {"ok", "warn", "fail", "skipped"}
            and isinstance(gate.get("reason"), str) and len(gate["reason"]) <= 160
            and isinstance(gate.get("checked_at"), str) and len(gate["checked_at"]) <= 64
            and _valid_optional_lower_sha256(gate.get("failed_record_sha256"))
            for gate in gates))


MAX_HISTORY_SECURITY_EVIDENCE_FACTS = 4
MAX_HISTORY_SECURITY_EVENT_CHARS = 384
MAX_HISTORY_CONTROLLER_GATES = 8


def _historical_security_evidence_context(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project only narrowly qualified owner observations into later cognition."""
    selected_ids = candidate.get("selected_fact_ids")
    selected_facts = candidate.get("selected_facts")
    if (not isinstance(selected_ids, (list, tuple))
            or len(selected_ids) > MAX_FACTS
            or not all(isinstance(item, str) and item for item in selected_ids)
            or not isinstance(selected_facts, (list, tuple))
            or len(selected_facts) > MAX_FACTS):
        return []
    selected = set(selected_ids)
    summaries: list[dict[str, Any]] = []
    for fact in selected_facts:
        if not isinstance(fact, Mapping) or fact.get("fact_id") not in selected:
            continue
        source, subject, payload = fact.get("source"), fact.get("subject"), fact.get("payload")
        if not all(isinstance(item, Mapping) for item in (source, subject, payload)):
            continue
        assert isinstance(source, Mapping) and isinstance(subject, Mapping) and isinstance(payload, Mapping)
        source_id, source_kind = source.get("source_id"), source.get("kind")
        subject_kind = subject.get("subject_kind")
        schema = payload.get("observation_schema")
        event_meaning = payload.get("event_meaning")
        if (source_kind == "resource_governor"
                and source_id == "governed_local_model_resource_consumption"
                and subject_kind == "causal_resource_consumption"):
            # Resource evidence has receipt event times and an observation
            # retrieval time, but is intentionally not a point-current host
            # observation. Preserve the exact historical process handoff only
            # after validating the writeback projection and its receipt joins.
            binding = payload.get("interpretation_projection")
            if not isinstance(binding, Mapping):
                continue
            binding_core = {key: binding.get(key) for key in (
                "schema_version", "source_fact_id", "source_payload_digest",
                "source_record_digest", "projected_payload_digest")}
            summary_payload = {key: value for key, value in payload.items()
                if key != "interpretation_projection"}
            binding_digest = binding.get("projection_digest")
            if (binding.get("schema_version") != "sentientos.resource_interpretation_projection:v1"
                    or binding.get("source_fact_id") != fact.get("fact_id")
                    or binding.get("source_record_digest") != source.get("digest")
                    or not _valid_lower_sha256(binding.get("source_payload_digest"))
                    or not _valid_lower_sha256(binding.get("projected_payload_digest"))
                    or binding.get("projected_payload_digest") != _world_state_digest(summary_payload)
                    or not _valid_lower_sha256(binding_digest)
                    or binding_digest != _world_state_digest(binding_core)
                    or fact.get("stage") != "observation"
                    or fact.get("disposition") not in {"recorded", "degraded"}
                    or payload.get("authority") is not False
                    or payload.get("current_truth") is not False
                    or payload.get("effect_proven") is not False
                    or payload.get("event_time_posture")
                        != "receipt_event_time_retained_as_historical"
                    or payload.get("event_meaning") != (
                        "governed resource consumption and historically bound chat process generation")
                    or payload.get("loaded_code_identity_posture")
                        != "not_independently_attested"
                    or payload.get("process_identity_scope")
                        != "installation_bound_launcher_handoff_process_identity"
                    or payload.get("lineage_posture") not in {"verified", "degraded"}
                    or payload.get("chat_process_generation_posture") not in {
                        "verified", "partial_legacy_or_unavailable",
                        "unknown_legacy_or_unavailable", "unknown_no_completed_invocations",
                        "invalid_or_unbound"}):
                continue
            invocations = payload.get("invocation_receipts")
            attributions = payload.get("verified_chat_process_generation_attributions")
            allocations = payload.get("allocations")
            attempts = payload.get("attempts")
            receipts = payload.get("consumption_receipts")
            if (not isinstance(invocations, (list, tuple)) or len(invocations) > 4
                    or any(not isinstance(item, Mapping) for item in invocations)
                    or not isinstance(attributions, (list, tuple)) or len(attributions) > 4
                    or any(not isinstance(item, Mapping) for item in attributions)
                    or not isinstance(allocations, (list, tuple)) or len(allocations) > 4
                    or any(not isinstance(item, Mapping) for item in allocations)
                    or not isinstance(attempts, (list, tuple)) or len(attempts) > 8
                    or any(not isinstance(item, Mapping) for item in attempts)
                    or not isinstance(receipts, (list, tuple)) or len(receipts) > 2
                    or any(not isinstance(item, Mapping) for item in receipts)):
                continue
            invocation_by_id: dict[str, Mapping[str, Any]] = {}
            invalid = False
            for invocation in invocations:
                receipt_id = invocation.get("receipt_id")
                if (not isinstance(receipt_id, str) or not receipt_id
                        or receipt_id in invocation_by_id
                        or not _valid_lower_sha256(invocation.get("receipt_digest"))
                        or not isinstance(invocation.get("request_id"), str)
                        or not _valid_lower_sha256(invocation.get("request_digest"))):
                    invalid = True
                    break
                invocation_by_id[receipt_id] = invocation
            projected_attributions: list[dict[str, Any]] = []
            seen_receipts: set[str] = set()
            for attribution in attributions:
                receipt_id = attribution.get("invocation_receipt_id")
                invocation = invocation_by_id.get(receipt_id) if isinstance(receipt_id, str) else None
                handoff = attribution.get("chat_process_handoff")
                if (set(attribution) != {"invocation_receipt_id", "invocation_receipt_digest",
                        "invocation_request_id", "invocation_request_digest", "chat_process_handoff",
                        "attribution_posture", "currentness_posture"}
                        or not isinstance(receipt_id, str) or receipt_id in seen_receipts
                        or not isinstance(invocation, Mapping)
                        or attribution.get("invocation_receipt_digest") != invocation.get("receipt_digest")
                        or attribution.get("invocation_request_id") != invocation.get("request_id")
                        or attribution.get("invocation_request_digest") != invocation.get("request_digest")
                        or attribution.get("attribution_posture")
                            != "invocation_receipt_and_historical_chat_handoff_verified"
                        or attribution.get("currentness_posture")
                            != "historical_process_identity_not_reobserved_during_recovery"
                        or not isinstance(handoff, Mapping)
                        or handoff.get("status") != "runtime_launcher_process_and_source_bound"
                        or any(not isinstance(handoff.get(key), str) or not handoff.get(key)
                            for key in ("software_generation_digest", "process_instance_id",
                                "handoff_id", "handoff_digest", "source_generation_scope"))):
                    invalid = True
                    break
                projected_attributions.append(dict(attribution))
                seen_receipts.add(receipt_id)
            if invalid:
                continue
            if payload.get("chat_process_generation_posture") == "verified":
                selected_completed = {receipt_id for receipt_id, invocation in invocation_by_id.items()
                    if invocation.get("status") == "admitted_completed"
                    and invocation.get("local_model_inference") is True}
                if selected_completed != seen_receipts:
                    continue
            lineage_context = {
                "schema": "sentientos.resource_generation_history_context:v1",
                "ledger_digest": payload.get("ledger_digest"),
                "lineage_posture": payload.get("lineage_posture"),
                "recovery_posture": payload.get("recovery_posture"),
                "resource_record_binding": [source.get("digest"),
                    binding.get("source_payload_digest"), binding_digest],
                "historical_consumption_times": [[item.get("receipt_id"),
                    item.get("observed_at")] for item in receipts],
                "chat_process_generation_posture": payload.get("chat_process_generation_posture"),
                "verified_chat_process_generation_attributions": [{
                    "invocation_id": item.get("invocation_receipt_id"),
                    "invocation_digest": item.get("invocation_receipt_digest"),
                    "request_id": item.get("invocation_request_id"),
                    "request_digest": item.get("invocation_request_digest"),
                    "handoff_status": item["chat_process_handoff"].get("status"),
                    "software_generation_digest": item["chat_process_handoff"].get(
                        "software_generation_digest"),
                    "process_instance_id": item["chat_process_handoff"].get("process_instance_id"),
                    "handoff_id": item["chat_process_handoff"].get("handoff_id"),
                    "handoff_digest": item["chat_process_handoff"].get("handoff_digest"),
                    "source_generation_scope": item["chat_process_handoff"].get(
                        "source_generation_scope"),
                    "currentness_posture": item.get("currentness_posture")}
                    for item in projected_attributions],
                "loaded_code_identity_posture": payload.get("loaded_code_identity_posture"),
                "process_identity_scope": payload.get("process_identity_scope"),
                "event_time_posture": payload.get("event_time_posture"),
                "shared_host_cpu_gpu_attribution": payload.get("shared_host_cpu_gpu_attribution"),
                "interpretation_projection_digest": binding_digest,
                "historical_only": True,
                "current_truth": False,
                "authority": False,
                "effect_proven": False,
            }
            context_bytes = json.dumps(lineage_context, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False).encode("utf-8")
            if len(context_bytes) > 6_000:
                continue
            summaries.append({
                "fact_id": fact["fact_id"],
                "source_binding": {"source_id": source_id, "kind": source_kind,
                    "digest": source["digest"]},
                "subject_kind": subject_kind,
                "disposition": fact.get("disposition"),
                "evidence_strength": fact.get("evidence_strength"),
                "observed_at": None,
                "event_time_posture": payload.get("event_time_posture"),
                "context": lineage_context,
                "historical_only": True,
                "current_truth": False,
                "authority": False,
                "policy": False,
                "effect_proven": False,
            })
            continue
        if not (isinstance(fact.get("fact_id"), str)
                and len(fact["fact_id"]) <= 128
                and isinstance(source_id, str) and 0 < len(source_id) <= 128
                and isinstance(source_kind, str) and 0 < len(source_kind) <= 64
                and isinstance(source.get("digest"), str)
                and 0 < len(source["digest"]) <= 128
                and isinstance(subject_kind, str) and 0 < len(subject_kind) <= 128
                and fact.get("stage") == "observation"
                and isinstance(fact.get("disposition"), str)
                and len(fact["disposition"]) <= 64
                and isinstance(fact.get("evidence_strength"), str)
                and len(fact["evidence_strength"]) <= 128
                and isinstance(event_meaning, str)
                and 0 < len(event_meaning) <= MAX_HISTORY_SECURITY_EVENT_CHARS
                and payload.get("authority") is False
                and payload.get("current_truth") is False
                and payload.get("effect_proven") is False):
            continue
        event_time_posture = payload.get("event_time_posture")
        if not isinstance(event_time_posture, str) or len(event_time_posture) > 96:
            continue
        context: dict[str, Any] | None = None
        if (source_kind == "quarantine"
                and source_id == "integrity-quarantine-custody:resident-daemon"
                and subject_kind == "quarantine_custody_observation"
                and schema == "sentientos.integrity_quarantine_custody_observation:v1"
                and event_time_posture == "daemon_tick_point_observation_of_owner_read"
                and payload.get("source_owner") == "sentientos.integrity_quarantine.load_state_with_status"
                and payload.get("custody_result") in {
                    "first_use_absent", "valid_v1", "invalid", "observer_unavailable"}
                and payload.get("attack_established") is False
                and payload.get("hostile_activity_established") is False
                and payload.get("effect_authority") is False
                and payload.get("read_only") is True
                and type(payload.get("cause_unknown")) is bool
                and type(payload.get("stored_state_present")) in {bool, type(None)}
                and type(payload.get("quarantine_active")) in {bool, type(None)}
                and (payload.get("custody_error_code") is None
                    or (isinstance(payload.get("custody_error_code"), str)
                        and len(payload["custody_error_code"]) <= 128))):
            context = {
                "custody_result": payload.get("custody_result"),
                "custody_error_code": payload.get("custody_error_code"),
                "quarantine_active": payload.get("quarantine_active"),
                "stored_state_present": payload.get("stored_state_present"),
                "event_meaning": event_meaning,
                "cause_unknown": payload.get("cause_unknown"),
            }
        elif (source_kind == "quarantine"
                and source_id == "integrity-quarantine-incident-custody:resident-daemon"
                and subject_kind == "quarantine_incident_custody_observation"
                and schema == "sentientos.integrity_quarantine_incident_custody_observation:v1"
                and event_time_posture == "historical_activation_reference_reconciled_at_observation"
                and payload.get("source_owner") == "sentientos.integrity_incident.inspect_quarantine_incident_custody"
                and payload.get("reconciliation_status") in {
                    "complete_local_custody", "incomplete", "conflict",
                    "incomplete_identity", "observer_unavailable"}
                and payload.get("feed_is_authenticated") is False
                and payload.get("attack_established") is False
                and payload.get("hostile_activity_established") is False
                and payload.get("defensive_consequence_established") is False
                and payload.get("cause_unknown") is True
                and payload.get("authority") is False
                and payload.get("effect_authority") is False
                and payload.get("read_only") is True
                and payload.get("artifact_status") in {"valid", "missing", "invalid", "conflict", "not_checked"}
                and payload.get("feed_status") in {"present_unverified", "missing", "invalid", "conflict", "not_checked"}
                and payload.get("catalog_status") in {"present_unverified", "missing", "incomplete", "invalid", "conflict", "unsupported", "unavailable"}
                and type(payload.get("catalog_duplicate_count")) is int
                and 0 <= payload["catalog_duplicate_count"] <= 8_192
                and payload.get("catalog_row_is_authenticated") is False
                and (payload.get("incident_id") is None
                    or (isinstance(payload.get("incident_id"), str)
                        and 0 < len(payload["incident_id"]) <= 128))
                and (payload.get("incident_activated_at") is None
                    or (isinstance(payload.get("incident_activated_at"), str)
                        and 0 < len(payload["incident_activated_at"]) <= 64))
                and _valid_optional_lower_sha256(payload.get("artifact_sha256"))
                and _valid_optional_lower_sha256(payload.get("feed_row_sha256"))):
            context = {
                "reconciliation_status": payload.get("reconciliation_status"),
                "incident_id": payload.get("incident_id"),
                "incident_activated_at": payload.get("incident_activated_at"),
                "artifact_status": payload.get("artifact_status"),
                "artifact_sha256": payload.get("artifact_sha256"),
                "feed_status": payload.get("feed_status"),
                "feed_row_sha256": payload.get("feed_row_sha256"),
                "catalog_status": payload.get("catalog_status"),
                "catalog_entry_sha256": payload.get("catalog_entry_sha256"),
                "catalog_duplicate_count": payload.get("catalog_duplicate_count"),
                "feed_is_authenticated": False,
                "catalog_row_is_authenticated": False,
                "event_meaning": event_meaning,
                "interpretation_limits": (
                    "The feed and catalog are unauthenticated indexes; local cross-record consistency does not establish attack or defensive consequence."
                ),
                "cause_unknown": True,
            }
        elif (source_kind == "audit_trust"
                and source_id == "attestation-snapshot-verification:resident-daemon"
                and subject_kind == "attestation_snapshot_verification_observation"
                and schema in {
                    "sentientos.attestation_snapshot_verification_observation:v1",
                    "sentientos.attestation_snapshot_verification_observation:v2",
                }
                and event_time_posture
                    == "daemon_tick_point_observation_of_bounded_verifier"
                and payload.get("source_owner")
                    == "sentientos.attestation_snapshot.verify_recent_snapshots"
                and payload.get("verification_result") in {"ok", "warn", "fail", "skipped", "unavailable"}
                and (type(payload.get("verification_ok")) is bool
                    or payload.get("verification_ok") is None)
                and (payload.get("verification_reason") is None
                    or (isinstance(payload.get("verification_reason"), str)
                        and len(payload["verification_reason"]) <= 128))
                and type(payload.get("checked_signature_count")) is int
                and 0 <= payload["checked_signature_count"] <= 64
                and _valid_optional_lower_sha256(
                    payload.get("failed_signature_record_sha256"))
                and payload.get("cause_unknown") is True
                and payload.get("attack_established") is False
                and payload.get("hostile_activity_established") is False
                and payload.get("compromise_established") is False
                and payload.get("independent_signature") is False
                and payload.get("effect_authority") is False
                and payload.get("read_only") is True):
            context = {
                "verification_result": payload.get("verification_result"),
                "verification_reason": payload.get("verification_reason"),
                "checked_signature_count": payload.get("checked_signature_count"),
                "failed_signature_record_sha256": payload.get(
                    "failed_signature_record_sha256"),
                "event_meaning": event_meaning,
                "cause_unknown": True,
            }
        elif (source_kind == "audit_trust"
                and source_id == "integrity-controller:resident-daemon"
                and subject_kind == "integrity_controller_observation"
                and schema in {
                    "sentientos.integrity_controller_observation:v1",
                    "sentientos.integrity_controller_observation:v2",
                }
                and event_time_posture
                    == "daemon_tick_point_observation_of_integrity_controller"
                and payload.get("source_owner")
                    == "sentientos.integrity_controller.evaluate_integrity"
                and payload.get("controller_posture") in {"ok", "warn", "fail", "unknown"}
                and _valid_integrity_controller_gates(payload)
                and payload.get("cause_unknown") is True
                and payload.get("attack_established") is False
                and payload.get("hostile_activity_established") is False
                and payload.get("compromise_established") is False
                and payload.get("effect_authority") is False
                and payload.get("independent_signature") is False
                and payload.get("read_only") is True):
            gates = payload["gate_results"]
            selected_gates = [{key: gate.get(key) for key in (
                "name", "status", "reason", "checked_at", "failed_record_sha256")}
                for gate in gates[:MAX_HISTORY_CONTROLLER_GATES]]
            omitted_gates = gates[MAX_HISTORY_CONTROLLER_GATES:]
            context = {
                "controller_posture": payload.get("controller_posture"),
                "gates": selected_gates,
                "omitted_gate_count": len(omitted_gates),
                "omitted_gates_digest": _digest(omitted_gates),
                "event_meaning": event_meaning,
                "cause_unknown": True,
            }
        if context is None:
            continue
        observed_at = fact.get("observed_at")
        if not isinstance(observed_at, str) or len(observed_at) > 64:
            observed_at = None
        summaries.append({
            "fact_id": fact["fact_id"],
            "source_binding": {"source_id": source_id, "kind": source_kind,
                "digest": source["digest"]},
            "subject_kind": subject_kind,
            "disposition": fact.get("disposition"),
            "evidence_strength": fact.get("evidence_strength"),
            "observed_at": observed_at,
            "event_time_posture": event_time_posture,
            "context": context,
            "historical_only": True,
            "current_truth": False,
            "authority": False,
            "policy": False,
            "attack_established": False,
            "hostile_activity_established": False,
            "compromise_established": False,
            "independent_signature": False,
            "effect_proven": False,
        })
    return sorted(summaries, key=lambda item: str(item["fact_id"]))


def _resource_condition_recommendation(condition_outcomes: Sequence[Mapping[str, Any]], *,
        minimum_correct_count: int, probe_count: int, task_digest: str) -> dict[str, Any]:
    """Choose among preregistered history treatments by scored quality, then measured cost."""
    evaluator = "resource_quality_then_measured_call_units:v1"
    condition_ids = ("history_present", "history_withheld", "history_restored")
    if (type(minimum_correct_count) is not int or type(probe_count) is not int
            or not 1 <= minimum_correct_count <= probe_count <= 16
            or not isinstance(task_digest, str) or len(task_digest) != 71
            or not task_digest.startswith("sha256:")
            or len(condition_outcomes) != len(condition_ids)):
        return {"schema_version": "sentientos.resource_strategy_recommendation:v1",
            "evaluator": evaluator, "posture": "incomparable_missing_preregistered_inputs",
            "recommendation": None, "authority": False, "current_truth": False}
    by_id = {str(item.get("condition_id")): item for item in condition_outcomes
        if isinstance(item, Mapping)}
    if set(by_id) != set(condition_ids):
        posture = "incomparable_missing_condition_evidence"
        candidates: list[dict[str, Any]] = []
    else:
        candidates = []
        posture = "comparable"
        for condition_id in condition_ids:
            item = by_id[condition_id]
            count, probes = item.get("correct_count"), item.get("probe_count")
            resource = item.get("resource_context")
            receipts = resource.get("resource_receipts") if isinstance(resource, Mapping) else None
            if (not isinstance(resource, Mapping) or type(count) is not int
                    or type(probes) is not int or probes != probe_count
                    or not 0 <= count <= probes
                    or not isinstance(receipts, list) or not receipts
                    or resource.get("posture") != "verified_ledger_receipt_values"
                    or not isinstance(item.get("inference_receipt_id"), str)
                    or not item.get("inference_receipt_id")
                    or not isinstance(item.get("inference_receipt_digest"), str)
                    or len(item["inference_receipt_digest"]) not in {64, 71}
                    or (len(item["inference_receipt_digest"]) == 71
                        and not item["inference_receipt_digest"].startswith("sha256:"))
                    or any(character not in "0123456789abcdef"
                        for character in (item["inference_receipt_digest"][7:]
                            if len(item["inference_receipt_digest"]) == 71
                            else item["inference_receipt_digest"]))
                    or not isinstance(item.get("score_digest"), str)
                    or len(item["score_digest"]) != 71
                    or not item["score_digest"].startswith("sha256:")
                    or any(character not in "0123456789abcdef"
                        for character in item["score_digest"][7:])
                    or item.get("evaluator") !=
                        "deterministic_exact_integer_suite_oracle_v2"):
                posture = "incomparable_missing_or_unbound_measurement"
                candidates = []
                break
            call_units = []
            receipt_bindings = []
            for receipt in receipts:
                receipt_id = receipt.get("receipt_id") if isinstance(receipt, Mapping) else None
                receipt_digest = receipt.get("receipt_digest") \
                    if isinstance(receipt, Mapping) else None
                values = receipt.get("measured_values") if isinstance(receipt, Mapping) else None
                value = values.get("call_units_consumed") if isinstance(values, Mapping) else None
                if (not isinstance(receipt_id, str) or not receipt_id
                        or not isinstance(receipt_digest, str) or len(receipt_digest) != 64
                        or any(character not in "0123456789abcdef"
                            for character in receipt_digest)
                        or type(value) is not int or value < 0):
                    posture = "incomparable_unknown_call_units"
                    candidates = []
                    break
                call_units.append(value)
                receipt_bindings.append({"receipt_id": receipt_id,
                    "receipt_digest": receipt_digest, "call_units_consumed": value})
            if not candidates and posture != "comparable":
                break
            candidates.append({"condition_id": condition_id,
                "inference_receipt_id": item.get("inference_receipt_id"),
                "inference_receipt_digest": item.get("inference_receipt_digest"),
                "score_digest": item.get("score_digest"),
                "correct_count": count, "probe_count": probes,
                "resource_receipts": receipt_bindings,
                "call_units_consumed": sum(call_units)})
    eligible = [item for item in candidates
        if item["correct_count"] >= minimum_correct_count]
    recommendation: dict[str, Any] | None = None
    if posture == "comparable" and eligible:
        best_quality = max(item["correct_count"] for item in eligible)
        best_quality_rows = [item for item in eligible if item["correct_count"] == best_quality]
        lowest_cost = min(item["call_units_consumed"] for item in best_quality_rows)
        best = [item for item in best_quality_rows
            if item["call_units_consumed"] == lowest_cost]
        if len(best) == 1:
            recommendation = best[0]
            posture = "bounded_recommendation"
        else:
            posture = "incomparable_equivalent_options"
    elif posture == "comparable":
        posture = "no_option_meets_preregistered_quality_requirement"
    body = {"schema_version": "sentientos.resource_strategy_recommendation:v1",
        "evaluator": evaluator, "posture": posture,
        "requirements": {"minimum_correct_count": minimum_correct_count,
            "probe_count": probe_count,
            "source": "frozen_task_descriptor_full_suite_correctness",
            "task_digest": task_digest},
        "candidate_conditions": candidates, "recommendation": recommendation,
        "condition_labels_used_as_quality": False,
        "authority": False, "current_truth": False, "historical_only": True}
    body["recommendation_digest"] = _digest(body)
    return body


def _compact_task_family_history_example(example: Mapping[str, Any]) -> dict[str, Any]:
    """Keep decision evidence and exact identities while removing repeated prompt fields."""
    retained = {key: example.get(key) for key in (
        "schema_version", "task_family_id", "task_family_posture", "source_fact_id",
        "source_binding", "source_run_id", "source_run_digest", "source_task_digest",
        "source_score_digest", "source_active_model_identity",
        "source_active_model_identity_digest", "model_identity_binding_posture",
        "target_active_model_identity_digest", "model_identity_relation",
        "applicability_posture", "evaluator", "event_scope", "examples",
        "independent_backend_observation", "execution_evidence_scope",
        "execution_evidence_posture", "historical_only", "current_truth", "authority")}
    resource_context = example.get("resource_context")
    if isinstance(resource_context, Mapping):
        retained_resource_context: dict[str, Any] = {key: resource_context.get(key) for key in (
            "posture", "source_fact_id", "source_binding", "shared_host_cpu_gpu",
            "historical_only", "current_truth", "authority") if key in resource_context}
        retained["resource_context"] = retained_resource_context
        # The per-condition projection below carries every measured receipt.
        # Keep a compact digest/count in this older aggregate slot to avoid
        # repeating the history_present measurement row.
        measurements = resource_context.get("measurements")
        if isinstance(measurements, (list, tuple)):
            refs = [{"receipt_id": item.get("receipt_id"),
                "receipt_digest": item.get("receipt_digest"),
                "measured_values": item.get("measured_values")}
                for item in measurements if isinstance(item, Mapping)]
            retained_resource_context["measurement_receipt_refs"] = refs
            retained_resource_context["omitted_measurement_count"] = (
                resource_context.get("omitted_measurement_count", 0))
    outcomes = example.get("condition_outcomes")
    if isinstance(outcomes, (list, tuple)):
        compact_outcomes = []
        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                continue
            row = {key: outcome.get(key) for key in (
                "condition_id", "inference_receipt_id", "inference_receipt_digest",
                "inference_event_time", "inference_event_time_posture", "score_digest",
                "evaluator", "score_status", "correct_count", "probe_count",
                "historical_only", "current_truth", "authority")}
            context = outcome.get("resource_context")
            if isinstance(context, Mapping):
                resource = {key: context.get(key) for key in (
                    "posture", "source_fact_id", "source_binding", "event_time",
                    "omitted_measurement_count") if key in context}
                receipts = context.get("resource_receipts")
                if isinstance(receipts, (list, tuple)):
                    resource["resource_receipts"] = [{
                        "receipt_id": item.get("receipt_id"),
                        "receipt_digest": item.get("receipt_digest"),
                        "measured_values": item.get("measured_values"),
                        "measurement_posture": item.get("measurement_posture"),
                    } for item in receipts if isinstance(item, Mapping)]
                if isinstance(context.get("unqualified_lineage"), (list, tuple)):
                    resource["unqualified_lineage"] = list(context["unqualified_lineage"][:4])
                row["resource_context"] = resource
            compact_outcomes.append(row)
        retained["condition_outcomes"] = compact_outcomes
    recommendation = example.get("resource_strategy_recommendation")
    if isinstance(recommendation, Mapping):
        compact_recommendation = {key: recommendation.get(key) for key in (
            "schema_version", "evaluator", "posture", "requirements",
            "condition_labels_used_as_quality", "authority", "current_truth",
            "historical_only", "recommendation_digest")}
        selected = recommendation.get("recommendation")
        if isinstance(selected, Mapping):
            compact_recommendation["recommendation"] = {key: selected.get(key) for key in (
                "condition_id", "inference_receipt_id", "inference_receipt_digest",
                "score_digest", "correct_count", "probe_count", "call_units_consumed",
                "resource_receipts")}
        retained["resource_strategy_recommendation"] = compact_recommendation
    evidence_conditions = example.get("execution_evidence_conditions")
    if isinstance(evidence_conditions, (list, tuple)):
        retained["execution_evidence_conditions"] = [{key: item.get(key) for key in (
            "condition_id", "receipt_identity_verified", "invocation_receipt_id",
            "invocation_receipt_digest", "posture")}
            for item in evidence_conditions if isinstance(item, Mapping)]
    return retained


def _task_family_model_applicability(example: Mapping[str, Any], *,
        target_model_identity: Mapping[str, Any] | None) -> dict[str, Any]:
    """Compare exact recorded identities while keeping task-family scope explicit."""
    source = example.get("source_active_model_identity")
    source_digest = example.get("source_active_model_identity_digest")
    target_digest = (_digest(dict(target_model_identity))
        if isinstance(target_model_identity, Mapping) and target_model_identity else None)
    source_bound = (isinstance(source, Mapping) and bool(source)
        and isinstance(source_digest, str) and source_digest == _digest(dict(source)))
    if not source_bound or target_digest is None:
        relation = "model_identity_unbound"
        posture = "model_identity_unbound_transfer_not_established"
    elif (isinstance(source, Mapping) and isinstance(target_model_identity, Mapping)
            and dict(source) == dict(target_model_identity)):
        relation = "same_active_model_identity"
        posture = "same_family_same_model_task_scope_unverified"
    else:
        relation = "different_active_model_identity"
        posture = "cross_model_transfer_not_established"
    return {"target_active_model_identity_digest": target_digest,
        "model_identity_relation": relation, "applicability_posture": posture}


def _observed_current_cognition_model_identity(invoker: Any) -> dict[str, Any] | None:
    """Use only the serving adapter's read-only current-session identity observation."""
    observe = getattr(invoker, "observed_current_model_identity", None)
    if not callable(observe):
        return None
    identity = observe()
    if not isinstance(identity, Mapping) or not identity:
        return None
    return dict(identity)


def _task_family_history_examples(candidate: Mapping[str, Any], *,
        task_family_id: str | None) -> list[dict[str, Any]]:
    """Project only admitted, score-bound examples matching the requested family."""
    if not isinstance(task_family_id, str) or not task_family_id:
        return []
    facts = candidate.get("selected_facts", ())
    sources = candidate.get("selected_sources", ())
    if not isinstance(facts, (list, tuple)) or not isinstance(sources, (list, tuple)):
        return []
    source_by_id = {str(source.get("source_id")): source for source in sources
        if isinstance(source, Mapping) and isinstance(source.get("source_id"), str)}
    projected: list[dict[str, Any]] = []
    for fact in facts[:MAX_FACTS]:
        if not isinstance(fact, Mapping):
            continue
        payload = fact.get("payload")
        subject = fact.get("subject")
        source = fact.get("source")
        if (not isinstance(payload, Mapping) or not isinstance(subject, Mapping)
                or not isinstance(source, Mapping)
                or subject.get("subject_kind")
                    != "developmental_history_intervention_experiment"
                or payload.get("objective_task_family") != task_family_id
                or payload.get("task_family_posture") != "operator_declared_protocol_bound"
                or payload.get("objective_task_commitment_posture")
                    != "salted_private_oracle_commitment:v1"):
            continue
        descriptor = payload.get("objective_task_descriptor")
        run_id, run_digest = payload.get("run_id"), payload.get("run_digest")
        source_id = source.get("source_id")
        source_digest = source.get("digest")
        if (not isinstance(descriptor, Mapping)
                or descriptor.get("task_family_id") != task_family_id
                or descriptor.get("task_digest_posture")
                    != "salted_private_oracle_commitment:v1"
                or not isinstance(descriptor.get("task_digest"), str)
                or len(descriptor["task_digest"]) != 71
                or not descriptor["task_digest"].startswith("sha256:")
                or not isinstance(run_id, str) or not run_id
                or not isinstance(run_digest, str) or not run_digest.startswith("sha256:")
                or source_id != "developmental-history-run:" + run_id
                or subject.get("subject_id") != run_id
                or source.get("kind") != "embodiment"
                or not isinstance(source_digest, str) or len(source_digest) != 64
                or any(character not in "0123456789abcdef" for character in source_digest)
                or source_by_id.get(str(source_id), {}).get("digest") != source_digest):
            continue
        score_rows = payload.get("objective_scores")
        examples = payload.get("acquisition_examples")
        if not isinstance(score_rows, (list, tuple)) or not isinstance(examples, (list, tuple)):
            continue
        score = next((item for item in score_rows if isinstance(item, Mapping)
            and item.get("condition_id") == "history_present"), None)
        active_model_identity = payload.get("active_model_identity")
        active_model_identity_digest = payload.get("active_model_identity_digest")
        model_identity_bound = (isinstance(active_model_identity, Mapping)
            and bool(active_model_identity)
            and isinstance(active_model_identity_digest, str)
            and active_model_identity_digest == _digest(dict(active_model_identity)))
        if (not isinstance(score, Mapping)
                or score.get("schema_version") != "sentientos.objective_task_score:v3"
                or score.get("task_digest") != descriptor.get("task_digest")
                or score.get("evaluator") != "deterministic_exact_integer_suite_oracle_v2"
                or not isinstance(score.get("score_digest"), str)
                or len(score["score_digest"]) != 71
                or not score["score_digest"].startswith("sha256:")
                or not 1 <= len(examples) <= 16):
            continue
        rows: list[dict[str, Any]] = []
        valid = True
        for example in examples:
            if (not isinstance(example, Mapping)
                    or set(example) != {"probe_input", "observed_answer", "evaluator_correct",
                        "source_score_digest", "source_condition"}
                    or type(example.get("probe_input")) is not int
                    or type(example.get("observed_answer")) is not int
                    or type(example.get("evaluator_correct")) is not bool
                    or example.get("source_score_digest") != score.get("score_digest")
                    or example.get("source_condition") != "history_present"):
                valid = False
                break
            rows.append({key: example[key] for key in (
                "probe_input", "observed_answer", "evaluator_correct")})
        if not valid:
            continue
        # Join resource evidence only when it names this exact experiment run,
        # score, condition, and inference receipt. Missing or mismatched joins
        # remain explicitly unknown; they never borrow measurements from a
        # neighboring task-family example.
        condition = next((item for item in payload.get("conditions", ())
            if isinstance(item, Mapping) and item.get("condition_id") == "history_present"), None)
        resource_context: dict[str, Any] = {
            "posture": "unknown_missing_or_unbound_lineage",
            "measurements": [], "historical_only": True,
            "current_truth": False, "authority": False,
        }
        if isinstance(condition, Mapping):
            for resource_fact in facts[:MAX_FACTS]:
                if not isinstance(resource_fact, Mapping):
                    continue
                resource_payload = resource_fact.get("payload")
                resource_subject = resource_fact.get("subject")
                resource_source = resource_fact.get("source")
                if (not isinstance(resource_payload, Mapping)
                        or not isinstance(resource_subject, Mapping)
                        or not isinstance(resource_source, Mapping)
                        or resource_subject.get("subject_kind")
                            != "developmental_history_invocation_resource_lineage"
                        or resource_fact.get("stage") != "observation"
                        or resource_fact.get("disposition") != "verified"
                        or resource_payload.get("lineage_findings") not in ([], ())
                        or resource_payload.get("resource_measurement_posture")
                            != "verified_ledger_receipt_values"
                        or resource_payload.get("developmental_history_run_id") != run_id
                        or resource_payload.get("developmental_history_run_digest") != run_digest
                        or resource_payload.get("developmental_history_source_record_id") != source_id
                        or resource_payload.get("developmental_history_source_record_digest")
                            != source_digest
                        or resource_payload.get("task_family_id") != task_family_id):
                    continue
                resource_source_id = resource_source.get("source_id")
                if (not isinstance(resource_source_id, str)
                        or source_by_id.get(resource_source_id, {}).get("digest")
                            != resource_source.get("digest")):
                    continue
                task_outcome = resource_payload.get("task_outcome")
                if (not isinstance(task_outcome, Mapping)
                        or task_outcome.get("posture") != "run_owner_score_bound_to_condition"
                        or task_outcome.get("condition_id") != "history_present"
                        or task_outcome.get("score_digest") != score.get("score_digest")
                        or task_outcome.get("inference_receipt_id")
                            != condition.get("inference_receipt_id")
                        or task_outcome.get("inference_receipt_digest")
                            != condition.get("inference_receipt_digest")):
                    continue
                evidence = resource_payload.get("resource_consumption_evidence")
                linkage = resource_payload.get("resource_linkage")
                linked_digests = (linkage.get("consumption_receipt_digests", ())
                    if isinstance(linkage, Mapping) else ())
                if (not isinstance(evidence, (list, tuple)) or not evidence
                        or not isinstance(linked_digests, (list, tuple))):
                    continue
                measurements: list[dict[str, Any]] = []
                valid_evidence = True
                for row in evidence[:8]:
                    if not isinstance(row, Mapping):
                        valid_evidence = False
                        break
                    receipt_id, receipt_digest = row.get("receipt_id"), row.get("receipt_digest")
                    values, posture = row.get("measured_values"), row.get("measurement_posture")
                    if (not isinstance(receipt_id, str) or not receipt_id
                            or not isinstance(receipt_digest, str)
                            or receipt_digest not in linked_digests
                            or not isinstance(values, Mapping) or not isinstance(posture, Mapping)):
                        valid_evidence = False
                        break
                    measurements.append({
                        "receipt_id": receipt_id, "receipt_digest": receipt_digest,
                        "measured_values": {key: value for key, value in values.items()
                            if key in {"generation_attempted", "call_units_consumed",
                                "generated_output_size_bytes", "returned_output_size_bytes",
                                "output_truncated", "latency_ms"}},
                        "measurement_posture": dict(posture),
                    })
                if valid_evidence and measurements:
                    resource_context = {
                        "posture": "verified_ledger_receipt_values",
                        "source_fact_id": resource_fact.get("fact_id"),
                        "source_binding": {key: resource_source.get(key)
                            for key in ("source_id", "kind", "digest")},
                        "measurements": measurements,
                        "omitted_measurement_count": max(0, len(evidence) - len(measurements)),
                        "shared_host_cpu_gpu": "unknown_without_independent_observation",
                        "historical_only": True, "current_truth": False, "authority": False,
                    }
                    break
        # Preserve the complete preregistered comparison set.  A score for one
        # condition never authorizes borrowing the resource receipt from that
        # (or any other) condition.  Missing joins stay explicitly unknown.
        condition_outcomes: list[dict[str, Any]] = []
        raw_conditions = payload.get("conditions")
        expected_condition_ids = ("history_present", "history_withheld", "history_restored")
        score_by_condition = {str(item.get("condition_id")): item
            for item in score_rows if isinstance(item, Mapping)}
        if (isinstance(raw_conditions, (list, tuple)) and len(raw_conditions) == 3
                and isinstance(score_rows, (list, tuple)) and len(score_rows) == 3
                and {str(item.get("condition_id")) for item in raw_conditions
                    if isinstance(item, Mapping)} == set(expected_condition_ids)
                and len(score_by_condition) == 3
                and set(score_by_condition) == set(expected_condition_ids)):
            for condition_id in expected_condition_ids:
                raw_condition = next((item for item in raw_conditions
                    if isinstance(item, Mapping) and item.get("condition_id") == condition_id), None)
                score_row = score_by_condition[condition_id]
                if (not isinstance(raw_condition, Mapping)
                        or score_row.get("schema_version", "sentientos.objective_task_score:v3")
                            != "sentientos.objective_task_score:v3"
                        or score_row.get("task_digest", descriptor.get("task_digest"))
                            != descriptor.get("task_digest")
                        or score_row.get("evaluator", score.get("evaluator"))
                            != "deterministic_exact_integer_suite_oracle_v2"
                        or not isinstance(score_row.get("score_digest"), str)
                        or len(score_row["score_digest"]) != 71
                        or not score_row["score_digest"].startswith("sha256:")
                        or any(character not in "0123456789abcdef"
                            for character in score_row["score_digest"][7:])
                        or type(score_row.get("correct_count")) is not int
                        or type(score_row.get("probe_count")) is not int
                        or not 0 <= score_row["correct_count"] <= score_row["probe_count"] <= 16
                        or not isinstance(raw_condition.get("inference_receipt_id"), str)
                        or not raw_condition.get("inference_receipt_id")
                        or not isinstance(raw_condition.get("inference_receipt_digest"), str)
                        or len(raw_condition["inference_receipt_digest"]) not in {64, 71}
                        or any(character not in "0123456789abcdef"
                            for character in (raw_condition["inference_receipt_digest"][7:]
                                if len(raw_condition["inference_receipt_digest"]) == 71
                                and raw_condition["inference_receipt_digest"].startswith("sha256:")
                                else raw_condition["inference_receipt_digest"]))
                        or len(raw_condition["inference_receipt_digest"]) == 71
                            and not raw_condition["inference_receipt_digest"].startswith("sha256:")):
                    condition_outcomes = []
                    break
                joined: list[dict[str, Any]] = []
                unqualified: list[dict[str, Any]] = []
                for resource_fact in facts[:MAX_FACTS]:
                    rp = resource_fact.get("payload") if isinstance(resource_fact, Mapping) else None
                    rs = resource_fact.get("source") if isinstance(resource_fact, Mapping) else None
                    rsub = resource_fact.get("subject") if isinstance(resource_fact, Mapping) else None
                    if (not isinstance(rp, Mapping) or not isinstance(rs, Mapping)
                            or not isinstance(rsub, Mapping)
                            or rsub.get("subject_kind") !=
                                "developmental_history_invocation_resource_lineage"
                            or resource_fact.get("stage") != "observation"
                            or rp.get("developmental_history_run_id") != run_id
                            or rp.get("developmental_history_run_digest") != run_digest
                            or rp.get("developmental_history_source_record_id") != source_id
                            or rp.get("developmental_history_source_record_digest") != source_digest
                            or rp.get("task_family_id") != task_family_id
                            or rp.get("developmental_history_condition") != condition_id
                            or source_by_id.get(str(rs.get("source_id")), {}).get("digest") !=
                                rs.get("digest")):
                        continue
                    outcome = rp.get("task_outcome")
                    if (not isinstance(outcome, Mapping)
                            or outcome.get("posture") != "run_owner_score_bound_to_condition"
                            or outcome.get("condition_id") != condition_id
                            or outcome.get("score_digest") != score_row.get("score_digest")
                            or outcome.get("inference_receipt_id") !=
                                raw_condition.get("inference_receipt_id")
                            or outcome.get("inference_receipt_digest") !=
                                raw_condition.get("inference_receipt_digest")):
                        continue
                    if (resource_fact.get("disposition") != "verified"
                            or rp.get("lineage_findings") not in ([], ())
                            or rp.get("resource_measurement_posture") !=
                                "verified_ledger_receipt_values"):
                        unqualified.append({"source_fact_id": resource_fact.get("fact_id"),
                            "source_binding": {key: rs.get(key) for key in
                                ("source_id", "kind", "digest")},
                            "disposition": resource_fact.get("disposition"),
                            "lineage_findings": list(rp.get("lineage_findings", ()))[:8],
                        })
                        continue
                    evidence = rp.get("resource_consumption_evidence")
                    linkage = rp.get("resource_linkage")
                    linked = linkage.get("consumption_receipt_digests", ()) \
                        if isinstance(linkage, Mapping) else ()
                    if not isinstance(evidence, (list, tuple)) or not isinstance(linked, (list, tuple)):
                        continue
                    measurements = []
                    valid = True
                    for measurement in evidence[:8]:
                        if (not isinstance(measurement, Mapping)
                                or not isinstance(measurement.get("receipt_id"), str)
                                or not measurement.get("receipt_id")
                                or not isinstance(measurement.get("receipt_digest"), str)
                                or len(measurement["receipt_digest"]) != 64
                                or any(character not in "0123456789abcdef"
                                    for character in measurement["receipt_digest"])
                                or measurement["receipt_digest"] not in linked
                                or not isinstance(measurement.get("measured_values"), Mapping)
                                or not isinstance(measurement.get("measurement_posture"), Mapping)):
                            valid = False
                            break
                        measurements.append({
                            "receipt_id": measurement["receipt_id"],
                            "receipt_digest": measurement["receipt_digest"],
                            "measured_values": {key: value for key, value in
                                measurement["measured_values"].items() if key in {
                                    "generation_attempted", "call_units_consumed",
                                    "generated_output_size_bytes", "returned_output_size_bytes",
                                    "output_truncated", "latency_ms"}},
                            "measurement_posture": {key: value for key, value in
                                measurement["measurement_posture"].items() if key in {
                                    "token_count", "shared_host_cpu_gpu"}},
                        })
                    if valid and measurements:
                        joined.append({
                            "source_fact_id": resource_fact.get("fact_id"),
                            "source_binding": {key: rs.get(key) for key in
                                ("source_id", "kind", "digest")},
                            "event_time": resource_fact.get("observed_at"),
                            "resource_receipts": measurements,
                            "omitted_measurement_count": max(0, len(evidence) - len(measurements)),
                            "posture": "verified_ledger_receipt_values",
                        })
                # Multiple matching lineage records are not summed or resolved
                # by recency: that would make an ambiguous comparison look measured.
                resource_match = joined[0] if len(joined) == 1 and not unqualified else None
                if len(joined) > 1:
                    resource_posture = "unknown_ambiguous_condition_lineage"
                elif unqualified:
                    resource_posture = "unknown_unqualified_condition_lineage"
                elif not joined:
                    resource_posture = "unknown_missing_or_unbound_lineage"
                else:
                    resource_posture = "verified_ledger_receipt_values"
                condition_outcomes.append({
                    "condition_id": condition_id,
                    "inference_receipt_id": raw_condition.get("inference_receipt_id"),
                    "inference_receipt_digest": raw_condition.get("inference_receipt_digest"),
                    "inference_event_time": raw_condition.get("observed_at"),
                    "inference_event_time_posture": raw_condition.get("event_time_posture"),
                    "score_digest": score_row.get("score_digest"),
                    "evaluator": score_row.get("evaluator", score.get("evaluator")),
                    "score_status": score_row.get("status"),
                    "correct_count": score_row.get("correct_count"),
                    "probe_count": score_row.get("probe_count"),
                    "resource_context": (resource_match if resource_match is not None else {
                        "posture": resource_posture,
                        **({"unqualified_lineage": unqualified[:4]} if unqualified else {})}),
                    "historical_only": True, "current_truth": False, "authority": False,
                })
        observed_probe_count = score.get("probe_count")
        resource_strategy_recommendation = _resource_condition_recommendation(
            condition_outcomes,
            minimum_correct_count=(observed_probe_count if type(observed_probe_count) is int else 0),
            probe_count=(observed_probe_count if type(observed_probe_count) is int else 0),
            task_digest=str(descriptor.get("task_digest", "")))
        # Keep the execution posture attached to the acquired examples when
        # they are retrieved later.  A deterministic task score establishes
        # correctness relative to its oracle; it does not independently prove
        # that a model backend ran.  Older admitted records predate this
        # projection, so retain their examples with an explicit unknown
        # posture rather than retroactively manufacturing execution evidence.
        execution_fields = {
            "execution_evidence_conditions", "execution_evidence_posture",
            "execution_evidence_scope", "independent_backend_observation",
        }
        present_execution_fields = execution_fields.intersection(payload)
        execution_conditions: list[dict[str, Any]] = []
        if not present_execution_fields:
            execution_scope = "historical_receipt_posture_not_retained"
            execution_posture = "execution_evidence_unavailable"
            independent_backend_observation: bool | None = None
        else:
            raw_conditions = payload.get("execution_evidence_conditions")
            receipt_conditions = payload.get("conditions")
            raw_posture = payload.get("execution_evidence_posture")
            if (present_execution_fields != execution_fields
                    or payload.get("execution_evidence_scope") != (
                        "authenticated_owner_receipt_not_independent_backend_observation")
                    or payload.get("independent_backend_observation") is not False
                    or not isinstance(raw_conditions, (list, tuple))
                    or len(raw_conditions) != 3
                    or not isinstance(receipt_conditions, (list, tuple))
                    or len(receipt_conditions) != 3):
                continue
            allowed_condition_postures = {
                "receipt_reports_simulation_or_no_backend_entry",
                "verified_owner_receipt_reports_backend_entry",
                "receipt_does_not_establish_backend_entry",
                "receipt_unbound_or_identity_mismatch",
            }
            expected_conditions = ("history_present", "history_withheld", "history_restored")
            for expected_condition, item, receipt_condition in zip(
                    expected_conditions, raw_conditions, receipt_conditions):
                if (not isinstance(item, Mapping)
                        or not isinstance(receipt_condition, Mapping)
                        or item.get("condition_id") != expected_condition
                        or receipt_condition.get("condition_id") != expected_condition
                        or type(item.get("receipt_identity_verified")) is not bool
                        or item.get("invocation_receipt_id")
                            != receipt_condition.get("inference_receipt_id")
                        or item.get("invocation_receipt_digest")
                            != receipt_condition.get("inference_receipt_digest")
                        or item.get("posture") not in allowed_condition_postures
                        or not isinstance(receipt_condition.get("inference_receipt_id"), str)
                        or not receipt_condition.get("inference_receipt_id")
                        or not isinstance(receipt_condition.get("inference_receipt_digest"), str)
                        or len(receipt_condition["inference_receipt_digest"]) not in {64, 71}
                        or (len(receipt_condition["inference_receipt_digest"]) == 71
                            and not receipt_condition["inference_receipt_digest"].startswith("sha256:"))
                        or any(character not in "0123456789abcdef"
                            for character in (receipt_condition["inference_receipt_digest"][7:]
                                if len(receipt_condition["inference_receipt_digest"]) == 71
                                else receipt_condition["inference_receipt_digest"]))
                        or (item.get("receipt_identity_verified") is True
                            and not isinstance(item.get("receipt_status"), str))
                        or (item.get("receipt_identity_verified") is False
                            and (item.get("posture") != "receipt_unbound_or_identity_mismatch"
                                or item.get("receipt_status") is not None
                                or item.get("local_model_inference_effect") is not None
                                or item.get("fallback_occurred") is not None))
                        or (item.get("receipt_identity_verified") is True
                            and item.get("posture") == "receipt_unbound_or_identity_mismatch")
                        or (item.get("local_model_inference_effect") is not None
                            and type(item.get("local_model_inference_effect")) is not bool)
                        or (item.get("fallback_occurred") is not None
                            and type(item.get("fallback_occurred")) is not bool)
                        or item.get("independent_backend_observation") is not False):
                    valid = False
                    break
                execution_conditions.append({
                    "condition_id": item.get("condition_id"),
                    "receipt_identity_verified": item.get("receipt_identity_verified"),
                    "invocation_receipt_id": receipt_condition.get("inference_receipt_id"),
                    "invocation_receipt_digest": receipt_condition.get("inference_receipt_digest"),
                    **{key: item.get(key) for key in (
                        "receipt_status", "local_model_inference_effect",
                        "fallback_occurred", "posture")}
                })
            if not valid:
                continue
            derived_posture = (
                "incomplete_or_unverified_condition_receipts"
                if any(item["receipt_identity_verified"] is not True
                    for item in execution_conditions)
                else
                "all_owner_receipts_report_backend_entry"
                if all(item["posture"] == "verified_owner_receipt_reports_backend_entry"
                    for item in execution_conditions)
                else "one_or_more_conditions_simulated_or_no_backend_entry"
                if any(item["posture"] == "receipt_reports_simulation_or_no_backend_entry"
                    for item in execution_conditions)
                else "one_or_more_receipts_do_not_establish_backend_entry")
            if raw_posture != derived_posture:
                continue
            execution_scope = str(payload["execution_evidence_scope"])
            execution_posture = derived_posture
            independent_backend_observation = False
        projected_example = {
            "schema_version": "sentientos.task_family_history_examples:v1",
            "task_family_id": task_family_id,
            "task_family_posture": "operator_declared_protocol_bound",
            "source_fact_id": fact.get("fact_id"),
            "source_binding": {key: source.get(key) for key in (
                "source_id", "kind", "digest")},
            "source_run_id": run_id, "source_run_digest": run_digest,
            "source_task_digest": descriptor["task_digest"],
            "source_score_digest": score["score_digest"],
            "source_active_model_identity": (dict(active_model_identity)
                if isinstance(active_model_identity, Mapping) else None),
            "source_active_model_identity_digest": (active_model_identity_digest
                if model_identity_bound else None),
            "model_identity_binding_posture": ("protocol_bound_source_identity"
                if model_identity_bound else "source_model_identity_unbound"),
            "applicability_posture": "target_model_identity_unbound",
            "evaluator": score["evaluator"],
            "event_scope": "scored_benchmark_outcome_not_external_environmental_event",
            "examples": rows,
            "resource_context": resource_context,
            "condition_outcomes": condition_outcomes,
            "execution_evidence_scope": execution_scope,
            "execution_evidence_posture": execution_posture,
            "execution_evidence_conditions": execution_conditions,
            "independent_backend_observation": independent_backend_observation,
            "historical_only": True, "current_truth": False, "authority": False,
        }
        if resource_strategy_recommendation.get("posture") in {
                "bounded_recommendation", "incomparable_equivalent_options",
                "no_option_meets_preregistered_quality_requirement"}:
            projected_example["resource_strategy_recommendation"] = (
                resource_strategy_recommendation)
        projected.append(projected_example)
        if len(projected) >= 4:
            break
    return projected


def _history_context_packet(record: Mapping[str, Any], *,
        include_source_evidence_context: bool = True,
        compact_for_input_budget: bool = False,
        task_family_id: str | None = None,
        target_model_identity: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Project a verified durable record to the bounded semantics cognition needs.

    Durable writeback retains the full source request/output for recovery and
    provenance verification. Re-sending that custody envelope to every later
    prompt wastes the inference budget and needlessly repeats source text. The
    prompt receives the admitted interpretation and its scope/dependencies,
    while exact record and candidate identities bind it to the full record.
    """
    candidate = record.get("candidate")
    if not isinstance(candidate, Mapping):
        raise ResidentDevelopmentalCognitionError("developmental_history_candidate_invalid")
    record_id, record_digest = record.get("record_id"), record.get("record_digest")
    candidate_id, candidate_digest = candidate.get("candidate_id"), candidate.get("candidate_digest")
    if not all(isinstance(value, str) and value for value in
            (record_id, record_digest, candidate_id, candidate_digest)):
        raise ResidentDevelopmentalCognitionError("developmental_history_identity_invalid")
    packet: dict[str, Any] = {
        "record_id": record_id, "record_digest": record_digest,
        "candidate_id": candidate_id, "candidate_digest": candidate_digest,
        "interpretation": candidate.get("interpretation"),
        "uncertainty": candidate.get("uncertainty"),
        "epistemic_status": candidate.get("epistemic_status"),
        "selected_fact_ids": list(candidate.get("selected_fact_ids", ()))[:MAX_FACTS],
        "created_at": record.get("created_at"),
        "epistemic_posture": record.get("epistemic_posture"),
        "current_truth": False, "authority": False, "policy": False,
    }
    task_examples = _task_family_history_examples(candidate,
        task_family_id=task_family_id)
    if task_examples:
        for item in task_examples:
            item.update(_task_family_model_applicability(item,
                target_model_identity=target_model_identity))
        eligible = [item for item in task_examples
            if item.get("model_identity_relation") == "same_active_model_identity"]
        omitted = [item for item in task_examples
            if item.get("model_identity_relation") != "same_active_model_identity"]
        if eligible:
            packet["task_relevant_experience"] = (
                [_compact_task_family_history_example(item) for item in eligible]
                if compact_for_input_budget else eligible)
        if omitted:
            omission_evidence = [{
                "source_fact_id": item.get("source_fact_id"),
                "source_binding": item.get("source_binding"),
                "source_run_id": item.get("source_run_id"),
                "source_run_digest": item.get("source_run_digest"),
                "source_task_digest": item.get("source_task_digest"),
                "source_score_digest": item.get("source_score_digest"),
                "source_active_model_identity_digest": item.get(
                    "source_active_model_identity_digest"),
                "target_active_model_identity_digest": item.get(
                    "target_active_model_identity_digest"),
                "model_identity_relation": item.get("model_identity_relation"),
                "historical_outcomes": [{key: outcome.get(key) for key in (
                    "condition_id", "score_digest", "correct_count", "probe_count")}
                    for outcome in item.get("condition_outcomes", ())
                    if isinstance(outcome, Mapping)],
            } for item in omitted]
            packet["task_relevant_experience_omission"] = {
                "posture": "identity_not_matched_examples_withheld_from_task_guidance",
                "omitted_example_count": len(omitted),
                "omitted_source_fact_ids": [item.get("source_fact_id") for item in omitted],
                "omitted_evidence_digest": _digest(omission_evidence),
                "omission_evidence": omission_evidence,
                "historical_only": True, "current_truth": False, "authority": False,
            }
    if compact_for_input_budget:
        interpretation = candidate.get("interpretation")
        if isinstance(interpretation, str) and len(interpretation) > 1200:
            packet["interpretation"] = interpretation[:1200]
            packet["interpretation_full_digest"] = _digest(interpretation)
            packet["interpretation_omitted_characters"] = len(interpretation) - 1200
    security_contexts = _historical_security_evidence_context(candidate)
    if security_contexts:
        if include_source_evidence_context:
            selected_contexts = security_contexts[:MAX_HISTORY_SECURITY_EVIDENCE_FACTS]
            packet["source_evidence_context"] = selected_contexts
            omitted_contexts = security_contexts[len(selected_contexts):]
            packet["source_evidence_context_digest"] = _digest(security_contexts)
            packet["source_evidence_context_omitted_count"] = len(omitted_contexts)
            packet["source_evidence_context_omitted_digest"] = _digest(omitted_contexts)
            packet["source_evidence_context_posture"] = (
                "complete" if not omitted_contexts else "bounded_incomplete")
        else:
            packet["source_evidence_context_digest"] = _digest(security_contexts)
            packet["source_evidence_context_omitted_count"] = len(security_contexts)
            packet["source_evidence_context_omitted_digest"] = _digest(security_contexts)
            packet["source_evidence_context_posture"] = "omitted_for_cognition_input_budget"
    sources = candidate.get("selected_sources", ())
    if isinstance(sources, (list, tuple)):
        if compact_for_input_budget:
            packet["source_bindings_digest"] = _digest(list(sources))
            packet["source_binding_count"] = len(sources)
        else:
            packet["source_bindings"] = [
                {key: source.get(key) for key in ("source_id", "kind", "digest")}
                for source in sources[:MAX_FACTS] if isinstance(source, Mapping)
            ]
    provenance = candidate.get("transformation_provenance")
    if isinstance(provenance, Mapping):
        packet["provenance_kind"] = provenance.get("kind")
        lesson = provenance.get("lesson_candidate")
        if isinstance(lesson, Mapping) and not compact_for_input_budget:
            packet["scope"] = lesson.get("scope")
            packet["applicability"] = lesson.get("applicability")
            packet["uncertainty_rationale"] = lesson.get("uncertainty_rationale")
            packet["evidence_dependencies"] = list(lesson.get("evidence_dependencies", ()))[:8]
            packet["possible_contradiction_ids"] = list(
                lesson.get("possible_contradiction_ids", ()))[:8]
    encoded = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > 32_000:
        raise ResidentDevelopmentalCognitionError("developmental_history_context_packet_unbounded")
    return packet


def _bind_history_and_epistemic_context(*, context: Mapping[str, Any],
        records: tuple[Mapping[str, Any], ...],
        projection: EpistemicCognitiveProjection | None,
        history_present: bool = True,
        ) -> tuple[dict[str, Any], dict[str, Any], str, tuple[str, ...], tuple[str, ...]]:
    """Fit whole recent history packets and epistemic packets to one input bound."""
    packet_modes = ((True, False), (False, False), (False, True))
    task_family_id = context.get("developmental_history_task_family_id")
    target_model_identity = context.get("developmental_history_target_model_identity")
    if not isinstance(target_model_identity, Mapping):
        target_model_identity = None
    packets_by_mode = {mode: tuple(_history_context_packet(record,
        include_source_evidence_context=mode[0], compact_for_input_budget=mode[1],
        task_family_id=task_family_id if isinstance(task_family_id, str) else None,
        target_model_identity=target_model_identity)
        for record in records) for mode in packet_modes}
    full_packets = packets_by_mode[packet_modes[0]]
    available = tuple({"record_id": packet["record_id"],
        "record_digest": packet["record_digest"]} for packet in full_packets)
    # Keep the largest recent complete suffix first. For a fixed suffix size,
    # prefer its richest evidence packet and degrade context only when needed
    # to keep that history available under the cognition input bound.
    counts = range(len(records), -1, -1) if history_present else (0,)
    for count in counts:
        for mode in packet_modes:
            packets = packets_by_mode[mode]
            selected = packets[len(packets) - count:] if count else ()
            omitted = packets[:len(packets) - count] if count else packets
            selected_refs = tuple({"record_id": packet["record_id"],
                "record_digest": packet["record_digest"]} for packet in selected)
            omitted_refs = tuple({"record_id": packet["record_id"],
                "record_digest": packet["record_digest"]} for packet in omitted)
            omission_reason = ("history_withheld_control" if omitted and not history_present else
                "inference_input_budget" if omitted else None)
            retrieval_policy = context.get("developmental_history_retrieval_policy_id",
                "completed_tick_recency_suffix:v1")
            custody_selection = {"schema_version": "sentientos.developmental_history_selection:v1",
                "policy": "most_recent_complete_record_suffix:v1",
                "retrieval_policy_id": retrieval_policy,
                "task_family_id": task_family_id,
                "treatment": "present" if history_present else "withheld",
                "available_records": list(available),
                "selected_records": list(selected_refs),
                "omitted_records": list(omitted_refs),
                "omitted_records_digest": _digest(list(omitted_refs)),
                "omission_reason": omission_reason}
            custody_selection["selection_digest"] = _digest(custody_selection)
            # The observation retains full omitted identities for recovery.
            # A withheld condition's model prompt receives no record IDs or
            # digests, so the control does not leak the withheld history set.
            prompt_available = list(available) if history_present else []
            prompt_omitted = list(omitted_refs) if history_present else []
            prompt_selection = {"schema_version": "sentientos.developmental_history_prompt_selection:v2",
                "policy": "most_recent_complete_record_suffix:v1",
                "retrieval_policy_id": retrieval_policy,
                "task_family_id": task_family_id,
                "treatment": "present" if history_present else "withheld",
                "available_records": prompt_available,
                "selected_records": list(selected_refs),
                "omitted_records": prompt_omitted,
                "omitted_records_digest": _digest(prompt_omitted),
                "omission_reason": ("inference_input_budget" if omitted else None)
                    if history_present else None}
            prompt_selection["selection_digest"] = _digest(prompt_selection)
            candidate = {**dict(context), "developmental_history": list(selected),
                "developmental_history_selection": prompt_selection}
            try:
                bound, metadata, prompt = _bind_epistemic_context(
                    context=candidate, projection=projection)
            except ResidentDevelopmentalCognitionError as exc:
                if str(exc) != "cognition_input_budget_exceeded":
                    raise
                continue
            # Do not let newly enriched task/resource history silently consume
            # the entire semantic epistemic allowance. Try a shorter or more
            # compact history suffix first; if no complete meaning packet can
            # fit, fail closed with omission evidence instead of sending an
            # identity-only epistemic projection as if it were useful context.
            if (metadata.get("epistemic_owner_packet_count", 0) > 0
                    and not metadata.get("epistemic_consumed_packet_ids")):
                continue
            ids = tuple(str(item["record_id"]) for item in selected_refs)
            digests = tuple(str(item["record_digest"]) for item in selected_refs)
            metadata = {**metadata,
                "developmental_history_selection": custody_selection}
            return bound, metadata, prompt, ids, digests
    raise ResidentDevelopmentalCognitionError("cognition_input_budget_exceeded")


def _bind_epistemic_context(*, context: Mapping[str, Any],
                            projection: EpistemicCognitiveProjection | None
                            ) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Select complete meaning packets that fit the actual inference input."""
    if projection is None:
        value = {**dict(context), "prior_epistemic_state": None}
        prompt = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if len(prompt) > MAX_RESIDENT_COGNITION_INPUT_CHARS:
            raise ResidentDevelopmentalCognitionError("cognition_input_budget_exceeded")
        metadata: dict[str, Any] = {"epistemic_projection_schema": None,
            "epistemic_semantic_status": "not_present", "epistemic_owner_packet_count": 0,
            "epistemic_consumed_packet_ids": [], "epistemic_consumed_packet_digests": [],
            "epistemic_omitted_packets": [], "epistemic_omitted_packets_digest": _digest([]),
            "epistemic_consumed_packets_digest": _digest([]),
            "epistemic_projection_context_digest": _digest(None),
            "epistemic_prompt_digest": _digest({"prompt": prompt})}
        metadata["epistemic_consumed_content_digest"] = _digest({
            "projection_id": None, "projection_digest": None,
            "prompt_digest": metadata["epistemic_prompt_digest"],
            "consumed_packet_digests": []})
        return value, metadata, prompt

    try:
        validate_cognitive_projection(projection)
    except (TypeError, ValueError, KeyError) as exc:
        raise ResidentDevelopmentalCognitionError("prior_epistemic_projection_invalid") from exc
    schema = getattr(projection, "schema_version", None)
    if not isinstance(projection, MeaningBearingEpistemicCognitiveProjection):
        # Preserve v1 identity verification while making its missing semantics explicit.
        prior = {"schema_version": "identifier_only_v1",
            "projection_id": projection.projection_id,
            "projection_digest": projection.projection_digest,
            "source_tick": projection.source_tick,
            "semantic_status": "canonical_definition_unavailable",
            "semantic_packets": []}
        value = {**dict(context), "prior_epistemic_state": prior}
        prompt = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if len(prompt) > MAX_RESIDENT_COGNITION_INPUT_CHARS:
            raise ResidentDevelopmentalCognitionError("cognition_input_budget_exceeded")
        metadata = {"epistemic_projection_schema": "identifier_only_v1",
            "epistemic_semantic_status": "canonical_definition_unavailable",
            "epistemic_owner_packet_count": 0,
            "epistemic_consumed_packet_ids": [], "epistemic_consumed_packet_digests": [],
            "epistemic_omitted_packets": [], "epistemic_omitted_packets_digest": _digest([]),
            "epistemic_consumed_packets_digest": _digest([]),
            "epistemic_projection_context_digest": _digest(prior),
            "epistemic_prompt_digest": _digest({"prompt": prompt})}
        metadata["epistemic_consumed_content_digest"] = _digest({
            "projection_id": projection.projection_id,
            "projection_digest": projection.projection_digest,
            "prompt_digest": metadata["epistemic_prompt_digest"],
            "consumed_packet_digests": []})
        return value, metadata, prompt

    try:
        packets = semantic_packets_for_projection(projection)
    except (TypeError, ValueError, KeyError) as exc:
        raise ResidentDevelopmentalCognitionError("prior_epistemic_semantics_invalid") from exc
    # When the inference bound cannot carry every complete meaning packet,
    # surface the most decision-relevant evidence first: withdrawn history,
    # then contradiction, then unresolved dependency. Stable packet identity
    # breaks ties; omitted packets remain explicitly digest-bound below.
    packets = tuple(sorted(packets, key=lambda packet: (
        0 if packet.get("removed_evidence_history") else 1,
        0 if packet.get("contradicting_evidence") else 1,
        0 if (isinstance(packet.get("evidence_posture"), Mapping)
            and packet["evidence_posture"].get("dependency_unresolved") is True) else 1,
        str(packet.get("packet_id", "")))))
    descriptors = tuple({"packet_id": packet["packet_id"],
        "packet_digest": packet["packet_digest"],
        "proposition_id": packet["proposition"]["proposition_id"],
        "state_id": packet["state"]["state_id"],
        "reason": "inference_input_budget"} for packet in packets)
    selected_count = -1
    selected_value: dict[str, Any] | None = None
    selected_omissions: tuple[Mapping[str, Any], ...] = ()
    for count in range(len(packets), -1, -1):
        consumed = packets[:count]
        omitted = descriptors[count:]
        prior = {"schema_version": schema,
            "projection_id": projection.projection_id,
            "projection_digest": projection.projection_digest,
            "source_tick": projection.source_tick,
            "current_tick_cutoff": projection.current_tick,
            "semantic_status": ("all_meanings_delivered" if not omitted else
                "complete_packets_selected_with_budget_omissions"),
            "owner_packet_count": len(packets),
            "semantic_packets": list(consumed),
            "omitted_packet_count": len(omitted),
            "omitted_packets_digest": _digest(list(omitted)),
            "omission_reason": "inference_input_budget" if omitted else None}
        # A v3 owner projection also identifies propositions omitted by the
        # projection's state bound. Keep that owner-level manifest in the
        # exact inference context; the prompt digest and projection digest
        # then bind both what the model received and what the owner withheld.
        if projection.omission_manifest is not None:
            prior["projection_omission_manifest"] = dict(projection.omission_manifest)
        candidate = {**dict(context), "prior_epistemic_state": prior}
        candidate_prompt = json.dumps(candidate, sort_keys=True, separators=(",", ":"))
        if len(candidate_prompt) <= MAX_RESIDENT_COGNITION_INPUT_CHARS:
            selected_count, selected_value, selected_omissions = count, candidate, omitted
            break
    if selected_value is None or selected_count < 0:
        raise ResidentDevelopmentalCognitionError("cognition_input_budget_exceeded")
    prior_context = selected_value["prior_epistemic_state"]
    consumed_packets = packets[:selected_count]
    consumed_ids = [str(packet["packet_id"]) for packet in consumed_packets]
    consumed_digests = [str(packet["packet_digest"]) for packet in consumed_packets]
    consumed_packet_digest = _digest(consumed_digests)
    prompt = json.dumps(selected_value, sort_keys=True, separators=(",", ":"))
    projection_context_digest = _digest(prior_context)
    prompt_digest = _digest({"prompt": prompt})
    metadata = {"epistemic_projection_schema": schema,
        "epistemic_semantic_status": prior_context["semantic_status"],
        "epistemic_owner_packet_count": len(packets),
        "epistemic_consumed_packet_ids": consumed_ids,
        "epistemic_consumed_packet_digests": consumed_digests,
        "epistemic_omitted_packets": [dict(item) for item in selected_omissions],
        "epistemic_omitted_packets_digest": _digest([dict(item) for item in selected_omissions]),
        "epistemic_consumed_packets_digest": consumed_packet_digest,
        "epistemic_projection_context_digest": projection_context_digest,
        "epistemic_prompt_digest": prompt_digest}
    metadata["epistemic_consumed_content_digest"] = _digest({
        "projection_id": projection.projection_id,
        "projection_digest": projection.projection_digest,
        "prompt_digest": prompt_digest,
        "consumed_packet_digests": consumed_digests})
    return selected_value, metadata, prompt


def _validate_epistemic_observation_binding(value: Mapping[str, Any]) -> None:
    ids = value.get("epistemic_consumed_packet_ids")
    digests = value.get("epistemic_consumed_packet_digests")
    omitted = value.get("epistemic_omitted_packets")
    if (not isinstance(ids, (list, tuple)) or not isinstance(digests, (list, tuple))
            or not isinstance(omitted, (list, tuple)) or len(ids) != len(digests)
            or len(ids) > 128 or len(omitted) > 128
            or len(set(ids)) != len(ids)
            or len({str(item.get("packet_id")) for item in omitted
                    if isinstance(item, Mapping)}) != len(omitted)
            or set(ids) & {str(item.get("packet_id")) for item in omitted
                    if isinstance(item, Mapping)}
            or any(not isinstance(item, str) or not item for item in ids)
            or any(not isinstance(item, str) or not item.startswith("sha256:") for item in digests)
            or any(not isinstance(item, Mapping) or set(item) != {
                "packet_id", "packet_digest", "proposition_id", "state_id", "reason"}
                or item.get("reason") != "inference_input_budget"
                or not all(isinstance(item.get(key), str) and item.get(key)
                    for key in ("packet_id", "packet_digest", "proposition_id", "state_id"))
                for item in omitted)
            or type(value.get("epistemic_owner_packet_count")) is not int
            or value["epistemic_owner_packet_count"] != len(ids) + len(omitted)
            or value.get("epistemic_consumed_packets_digest") != _digest(list(digests))
            or value.get("epistemic_omitted_packets_digest") != _digest([dict(row) for row in omitted])
            or value.get("epistemic_projection_context_digest") is None
            or not isinstance(value.get("epistemic_projection_context_digest"), str)
            or not value["epistemic_projection_context_digest"].startswith("sha256:")
            or not isinstance(value.get("epistemic_prompt_digest"), str)
            or not value["epistemic_prompt_digest"].startswith("sha256:")):
        raise ResidentDevelopmentalCognitionError("cognition_epistemic_consumption_binding_invalid")
    projection_id = value.get("epistemic_projection_id")
    projection_digest = value.get("epistemic_projection_digest")
    expected_content = _digest({"projection_id": projection_id,
        "projection_digest": projection_digest,
        "prompt_digest": value["epistemic_prompt_digest"],
        "consumed_packet_digests": list(digests)})
    if value.get("epistemic_consumed_content_digest") != expected_content:
        raise ResidentDevelopmentalCognitionError("cognition_epistemic_content_digest_mismatch")
    schema = value.get("epistemic_projection_schema")
    status = value.get("epistemic_semantic_status")
    if schema is None:
        if (value.get("epistemic_projection_present") is True
                or value.get("epistemic_projection_id") is not None
                or value.get("epistemic_projection_digest") is not None or ids or digests or omitted
                or value.get("epistemic_proposition_ids") or value.get("epistemic_state_ids")
                or value.get("epistemic_state_digests") or value.get("epistemic_generations")
                or value.get("epistemic_evidence_set_digests")
                or value["epistemic_owner_packet_count"] != 0 or status != "not_present"):
            raise ResidentDevelopmentalCognitionError("cognition_epistemic_absence_binding_invalid")
    elif schema == "identifier_only_v1":
        if (status != "canonical_definition_unavailable" or ids or digests or omitted
                or value.get("epistemic_projection_present") is not True):
            raise ResidentDevelopmentalCognitionError("cognition_epistemic_legacy_binding_invalid")
    elif schema in {"sentientos.epistemic_cognitive_projection:v2",
            "sentientos.epistemic_cognitive_projection:v3"}:
        if (status not in {"all_meanings_delivered",
                "complete_packets_selected_with_budget_omissions"}
                or (status == "all_meanings_delivered" and omitted)
                or (status == "complete_packets_selected_with_budget_omissions" and not omitted)
                or value.get("epistemic_projection_present") is not True
                or value.get("epistemic_projection_id") is None
                or value.get("epistemic_projection_digest") is None
                or len(value.get("epistemic_proposition_ids", ())) !=
                    value["epistemic_owner_packet_count"]
                or len(value.get("epistemic_state_ids", ())) !=
                    value["epistemic_owner_packet_count"]
                or len(value.get("epistemic_state_digests", ())) !=
                    value["epistemic_owner_packet_count"]
                or len(value.get("epistemic_generations", ())) !=
                    value["epistemic_owner_packet_count"]
                or len(value.get("epistemic_evidence_set_digests", ())) !=
                    value["epistemic_owner_packet_count"]):
            raise ResidentDevelopmentalCognitionError("cognition_epistemic_semantic_binding_invalid")
        if omitted:
            if value.get("epistemic_omitted_packets_digest") != _digest([dict(row) for row in omitted]):
                raise ResidentDevelopmentalCognitionError("cognition_epistemic_omission_digest_mismatch")
    else:
        raise ResidentDevelopmentalCognitionError("cognition_epistemic_schema_unsupported")


def _validate_developmental_history_selection(value: Mapping[str, Any]) -> None:
    """Validate the durable identity of selected and omitted history packets."""
    selection = value.get("developmental_history_selection")
    expected = {"schema_version", "policy", "retrieval_policy_id", "task_family_id",
        "treatment", "available_records", "selected_records", "omitted_records",
        "omitted_records_digest", "omission_reason", "selection_digest"}
    if not isinstance(selection, Mapping) or set(selection) != expected:
        raise ResidentDevelopmentalCognitionError("developmental_history_selection_invalid")
    semantic = dict(selection)
    claimed = semantic.pop("selection_digest")
    if (selection.get("schema_version") != "sentientos.developmental_history_selection:v1"
            or selection.get("policy") != "most_recent_complete_record_suffix:v1"
            or selection.get("retrieval_policy_id") not in {
                "completed_tick_recency_suffix:v1",
                "task_family_relevant_then_recency_fill:v1",
                "task_family_probe_overlap_then_recency_fill:v2"}
            or selection.get("treatment") not in {"present", "withheld"}
            or claimed != _digest(semantic)):
        raise ResidentDevelopmentalCognitionError("developmental_history_selection_identity_invalid")
    family = selection.get("task_family_id")
    if family is not None and (not isinstance(family, str) or not family or len(family) > 96):
        raise ResidentDevelopmentalCognitionError("developmental_history_selection_family_invalid")
    family_policy = selection.get("retrieval_policy_id") in {
        "task_family_relevant_then_recency_fill:v1",
        "task_family_probe_overlap_then_recency_fill:v2"}
    if family_policy != isinstance(family, str):
        raise ResidentDevelopmentalCognitionError(
            "developmental_history_selection_policy_family_mismatch")
    collections = []
    for field_name in ("available_records", "selected_records", "omitted_records"):
        rows = selection.get(field_name)
        if (not isinstance(rows, (list, tuple)) or len(rows) > MAX_HISTORY
                or any(not isinstance(row, Mapping) or set(row) != {"record_id", "record_digest"}
                    or not isinstance(row.get("record_id"), str) or not row.get("record_id")
                    or len(row["record_id"]) > 256
                    or not isinstance(row.get("record_digest"), str)
                    or len(row["record_digest"]) != 71
                    or not row["record_digest"].startswith("sha256:")
                    or any(character not in "0123456789abcdef"
                        for character in row["record_digest"][7:]) for row in rows)
                or len({row["record_id"] for row in rows}) != len(rows)):
            raise ResidentDevelopmentalCognitionError("developmental_history_selection_records_invalid")
        collections.append([dict(row) for row in rows])
    available, selected, omitted = collections
    if (omitted + selected != available
            or selection.get("omitted_records_digest") != _digest(omitted)
            or tuple(row["record_id"] for row in selected)
                != tuple(value.get("retrieved_record_ids", ()))
            or tuple(row["record_digest"] for row in selected)
                != tuple(value.get("retrieved_record_digests", ()))):
        raise ResidentDevelopmentalCognitionError("developmental_history_selection_binding_mismatch")
    reason = selection.get("omission_reason")
    if selection.get("treatment") == "withheld":
        valid_omission = (not selected and omitted == available
            and reason == ("history_withheld_control" if available else None))
    else:
        valid_omission = (reason in {None, "inference_input_budget"}
            and (reason == "inference_input_budget") == bool(omitted))
    if not valid_omission:
        raise ResidentDevelopmentalCognitionError("developmental_history_selection_omission_invalid")


@dataclass(frozen=True)
class ResidentDevelopmentalCognitionConfig:
    history_root: Path
    state_root: Path
    allowed_source_kinds: tuple[str, ...]
    max_selected_facts: int
    max_retrieved_records: int = 4
    comparison_enabled: bool = False
    enabled: bool = True
    model_replacement_artifact_root: Path | None = None


@dataclass(frozen=True)
class ResidentCognitionObservation:
    observation_id: str
    observation_digest: str
    condition_id: str
    tick_id: str
    correlation_id: str
    model_id: str
    model_artifact_digest: str | None
    request_id: str
    request_digest: str
    inference_receipt_id: str
    inference_receipt_digest: str
    output_digest: str
    authority_map_digest: str
    active_model_identity: Mapping[str, Any]
    generation_config: Mapping[str, Any]
    current_snapshot_id: str
    current_snapshot_digest: str
    current_projection_id: str
    current_projection_digest: str
    current_fact_ids: tuple[str, ...]
    retrieved_record_ids: tuple[str, ...]
    retrieved_record_digests: tuple[str, ...]
    developmental_projection_present: bool
    self_model_projection_present: bool = False
    self_model_projection_id: str | None = None
    self_model_projection_digest: str | None = None
    self_model_reconciliation_id: str | None = None
    self_model_reconciliation_digest: str | None = None
    self_model_reconciliation_generation: int | None = None
    self_model_source_tick: str | None = None
    self_model_claim_ids: tuple[str, ...] = ()
    self_model_claim_digests: tuple[str, ...] = ()
    prior_tick_proven: bool = False
    epistemic_projection_present: bool = False
    epistemic_projection_id: str | None = None
    epistemic_projection_digest: str | None = None
    epistemic_proposition_ids: tuple[str, ...] = ()
    epistemic_state_ids: tuple[str, ...] = ()
    epistemic_state_digests: tuple[str, ...] = ()
    epistemic_generations: tuple[int, ...] = ()
    epistemic_evidence_set_digests: tuple[str, ...] = ()
    historical_context_only: bool = True
    current_truth: bool = False
    authority: bool = False
    policy: bool = False
    canonical_explicit_user_retention: bool = False
    schema_version: str = COGNITION_OBSERVATION_SCHEMA_V4
    epistemic_projection_schema: str | None = None
    epistemic_semantic_status: str = "not_present"
    epistemic_owner_packet_count: int = 0
    epistemic_consumed_packet_ids: tuple[str, ...] = ()
    epistemic_consumed_packet_digests: tuple[str, ...] = ()
    epistemic_omitted_packets: tuple[Mapping[str, Any], ...] = ()
    epistemic_omitted_packets_digest: str | None = None
    epistemic_consumed_packets_digest: str | None = None
    epistemic_projection_context_digest: str | None = None
    epistemic_prompt_digest: str | None = None
    epistemic_consumed_content_digest: str | None = None
    developmental_history_selection: Mapping[str, Any] | None = None
    serving_session_id: str | None = None
    serving_session_binding: Mapping[str, Any] | None = None
    serving_session_receipt_id: str | None = None
    serving_session_receipt_digest: str | None = None
    observed_at: str | None = None
    resource_allocation_digest: str | None = None
    resource_attempt_id: str | None = None
    resource_consumption_receipt_digests: tuple[str, ...] = ()
    resource_linkage_digest: str | None = None


@dataclass(frozen=True)
class CurrentWorldStateCognitiveProjection:
    snapshot_id: str
    snapshot_digest: str
    facts: tuple[Mapping[str, Any], ...]
    sources: tuple[Mapping[str, Any], ...]
    conflicts: tuple[Mapping[str, Any], ...]
    fact_ids: tuple[str, ...]
    selection_policy: str = CURRENT_PROJECTION_POLICY
    read_only: bool = True
    evidence_only: bool = True
    current_truth: bool = False
    authority: bool = False
    policy: bool = False
    goal: bool = False
    canonical_explicit_user_retention: bool = False
    projection_id: str = ""
    projection_digest: str = ""

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("projection_id"); value.pop("projection_digest"); return value


@dataclass(frozen=True)
class ResidentDevelopmentalCycleResult:
    status: str
    tick_id: str
    snapshot_id: str
    selected_fact_ids: tuple[str, ...] = ()
    prior_record_ids: tuple[str, ...] = ()
    written_record_id: str | None = None
    writeback_receipt_id: str | None = None
    cognition_observation_ids: tuple[str, ...] = ()
    changed_cognition_measurement_id: str | None = None
    same_tick_history_excluded: bool = True
    canonical_explicit_user_retention_mutated: bool = False


@dataclass(frozen=True)
class VerifiedEpistemicRevisionProbeCapture:
    """Durable probe input and output reconciled to its owner observation and receipt."""

    observation_id: str
    observation_digest: str
    capture_digest: str
    prompt: str
    request: Mapping[str, Any]
    receipt: LocalModelInvocationReceipt


def verified_objective_measurement_summary(*, experiments: DevelopmentalExperimentStore,
        measurement_id: str, request: Mapping[str, Any],
        verify_observation: Callable[[Mapping[str, Any]], Mapping[str, Any] | None]) -> Mapping[str, Any]:
    """Verify and reduce a durable experiment without inference or custody writes."""
    try:
        task = objective_task_for_request(request)
    except ResidentDevelopmentalCognitionError as exc:
        raise ResidentDevelopmentalCognitionError("objective_outcome_request_invalid") from exc
    if objective_request_payload(request_id=str(request.get("request_id", "")),
            task=task) != dict(request):
        raise ResidentDevelopmentalCognitionError("objective_outcome_request_invalid")
    try:
        run = experiments.load_run(measurement_id)
        raw_protocol = run.get("protocol")
        if not isinstance(raw_protocol, Mapping):
            raise DevelopmentalHistoryInterventionError("objective_outcome_protocol_missing")
        protocol = experiments.load_protocol(str(raw_protocol.get("protocol_id", "")))
        plan = experiments.verify_objective_task_plan(protocol)
    except DevelopmentalHistoryInterventionError as exc:
        raise ResidentDevelopmentalCognitionError("objective_outcome_custody_invalid") from exc
    if (protocol.schema_version not in OBJECTIVE_SCHEMAS
            or plan.get("task_descriptor") != dict(request["task_descriptor"])):
        raise ResidentDevelopmentalCognitionError("objective_outcome_request_plan_mismatch")
    if (not isinstance(plan.get("task_descriptor"), Mapping)
            or plan["task_descriptor"].get("task_digest_posture")
                != "salted_private_oracle_commitment:v1"):
        raise ResidentDevelopmentalCognitionError(
            "objective_outcome_legacy_oracle_commitment_unavailable")
    conditions = run.get("conditions")
    score_rows = run.get("objective_scores")
    evaluation = run.get("objective_evaluation")
    if (not isinstance(conditions, list) or len(conditions) != len(CONDITION_ORDER)
            or not isinstance(score_rows, list) or len(score_rows) != len(CONDITION_ORDER)
            or not isinstance(evaluation, Mapping)):
        raise ResidentDevelopmentalCognitionError("objective_outcome_shape_invalid")
    condition_rows = {str(item.get("condition_id")): item for item in conditions
        if isinstance(item, Mapping)}
    score_by_condition = {str(item.get("condition_id")): item for item in score_rows
        if isinstance(item, Mapping)}
    if (tuple(condition_rows) != CONDITION_ORDER
            or tuple(score_by_condition) != CONDITION_ORDER):
        raise ResidentDevelopmentalCognitionError("objective_outcome_condition_set_invalid")
    outputs: list[dict[str, Any]] = []
    actual_inference = True
    requested_tokens = protocol.inference_budget.get("max_new_tokens")
    requested_output_chars = protocol.inference_budget.get("max_output_chars")
    for condition in CONDITION_ORDER:
        observation = condition_rows[condition]
        wrapper = score_by_condition[condition]
        receipt = verify_observation(observation)
        observed_generation = observation.get("generation_config")
        verified_generation = (receipt.get("generation_config")
            if isinstance(receipt, Mapping) else None)
        generation_binding_verified = (isinstance(observed_generation, Mapping)
            and isinstance(verified_generation, Mapping)
            and dict(observed_generation) == dict(verified_generation))
        actual_parameters = (verified_generation.get("actual_generation_parameters")
            if isinstance(verified_generation, Mapping) and generation_binding_verified else None)
        active_model_identity = observation.get("active_model_identity")
        model_profile = None
        if (generation_binding_verified and isinstance(active_model_identity, Mapping)
                and isinstance(observation.get("model_id"), str)
                and (observation.get("model_artifact_digest") is None
                    or isinstance(observation.get("model_artifact_digest"), str))):
            exact_profile = {"model_id": observation.get("model_id"),
                "model_artifact_digest": observation.get("model_artifact_digest"),
                "active_model_identity": dict(active_model_identity),
                "generation_config": dict(verified_generation)
                    if isinstance(verified_generation, Mapping) else {}}
            model_profile = {"model_id": exact_profile["model_id"],
                "model_artifact_digest": exact_profile["model_artifact_digest"],
                "active_model_identity": exact_profile["active_model_identity"],
                "generation_config_digest": _digest(exact_profile["generation_config"]),
                "profile_digest": _digest(exact_profile)}
        effective_tokens = (actual_parameters.get("max_new_tokens")
            if isinstance(actual_parameters, Mapping) else None)
        if type(effective_tokens) is int and type(requested_tokens) is int:
            budget_posture = ("effective_ceiling_matches_preregistered_request"
                if effective_tokens == requested_tokens else
                "effective_ceiling_reduced" if effective_tokens < requested_tokens else
                "effective_ceiling_exceeds_preregistered_request")
        else:
            budget_posture = "effective_ceiling_unverified"
        if budget_posture == "effective_ceiling_exceeds_preregistered_request":
            raise ResidentDevelopmentalCognitionError(
                "objective_outcome_generation_ceiling_conflict")
        if receipt is None:
            actual_inference = False
            receipt_status = "historical_invocation_unbound"
            execution_evidence_posture = "invocation_receipt_unbound"
        else:
            effects = receipt.get("effects")
            completed = (receipt.get("status") == "admitted_completed"
                and receipt.get("fallback_occurred") is False
                and isinstance(effects, Mapping)
                and effects.get("local_model_inference") is True
                and generation_binding_verified
                and budget_posture != "effective_ceiling_exceeds_preregistered_request")
            actual_inference = actual_inference and completed
            receipt_status = ("admitted_local_model_inference" if completed
                else "not_completed_or_generation_budget_unverified")
            if completed:
                execution_evidence_posture = (
                    "verified_owner_receipt_reports_backend_entry")
            elif (receipt.get("status") == "admitted_simulation"
                    or (isinstance(effects, Mapping)
                        and effects.get("local_model_inference") is False)):
                execution_evidence_posture = "receipt_reports_simulation_or_no_backend_entry"
            else:
                execution_evidence_posture = "receipt_does_not_establish_backend_entry"
        backend_completion = (receipt.get("backend_completion")
            if isinstance(receipt, Mapping)
            and isinstance(receipt.get("backend_completion"), Mapping) else None)
        output_size = (receipt.get("output_size_bytes") if isinstance(receipt, Mapping)
            and type(receipt.get("output_size_bytes")) is int
            and 0 <= receipt["output_size_bytes"] <= 1_048_576 else None)
        resource_fields = {
            "resource_allocation_digest": receipt.get("resource_allocation_digest")
                if isinstance(receipt, Mapping) else None,
            "resource_attempt_id": receipt.get("resource_attempt_id")
                if isinstance(receipt, Mapping) else None,
            "resource_consumption_receipt_digests": list(
                receipt.get("resource_consumption_receipt_digests") or ())
                if isinstance(receipt, Mapping) else [],
            "resource_linkage_digest": receipt.get("resource_linkage_digest")
                if isinstance(receipt, Mapping) else None,
        }
        has_resource_linkage = any((resource_fields["resource_allocation_digest"],
            resource_fields["resource_attempt_id"],
            resource_fields["resource_consumption_receipt_digests"],
            resource_fields["resource_linkage_digest"]))
        observed_resource_fields_present = any(key in observation for key in resource_fields)
        linkage_mismatch = False
        if observed_resource_fields_present:
            for key, value in resource_fields.items():
                observed_value = observation.get(key)
                if key == "resource_consumption_receipt_digests":
                    if (not isinstance(value, (list, tuple))
                            or not isinstance(observed_value, (list, tuple))
                            or tuple(observed_value) != tuple(value)):
                        linkage_mismatch = True
                        break
                elif observed_value != value:
                    linkage_mismatch = True
                    break
        if linkage_mismatch:
            raise ResidentDevelopmentalCognitionError(
                "objective_outcome_resource_linkage_mismatch")
        if has_resource_linkage and not observed_resource_fields_present:
            resource_posture = "receipt_linkage_not_bound_in_historical_observation"
            resource_fields = {"resource_allocation_digest": None,
                "resource_attempt_id": None,
                "resource_consumption_receipt_digests": [],
                "resource_linkage_digest": None}
        elif has_resource_linkage:
            resource_posture = (
                "invocation_receipt_linkage_verified_ledger_reconciliation_not_performed")
        else:
            resource_posture = ("unbound_historical_invocation" if receipt is None else
                "no_resource_linkage_in_invocation_receipt")
        score = wrapper.get("score")
        if not isinstance(score, Mapping):
            raise ResidentDevelopmentalCognitionError("objective_outcome_score_invalid")
        outputs.append({"condition_id": condition, "receipt_status": receipt_status,
            "execution_evidence_posture": execution_evidence_posture,
            "model_generation_profile": model_profile,
            "inference_receipt_id": observation.get("inference_receipt_id"),
            "inference_receipt_digest": observation.get("inference_receipt_digest"),
            "retrieved_record_ids": list(observation.get("retrieved_record_ids", ())),
            "retrieved_record_digests": list(observation.get("retrieved_record_digests", ())),
            "history_selection_digest": (
                observation.get("developmental_history_selection", {}).get("selection_digest")
                if isinstance(observation.get("developmental_history_selection"), Mapping) else None),
            "output_digest": observation.get("output_digest"),
            "score_digest": score.get("score_digest"),
            "score_status": score.get("status"), "correct": score.get("correct"),
            "correct_count": score.get("correct_count"),
            "output_truncated": wrapper.get("output_truncated", False),
            "backend_completion": (dict(backend_completion)
                if backend_completion is not None else None),
            "backend_completion_posture": ("receipt_bound_backend_report"
                if backend_completion is not None else
                "legacy_or_backend_completion_reason_unavailable"),
            "output_size_bytes": output_size,
            "output_size_posture": ("invocation_receipt_bound" if output_size is not None
                else "unknown_missing_or_invalid_receipt_value"),
            "generation_budget": {
                "preregistered_max_new_tokens": requested_tokens,
                "effective_max_new_tokens": effective_tokens,
                "posture": budget_posture,
                "preregistered_max_output_chars": requested_output_chars,
                "output_truncated": wrapper.get("output_truncated", False),
                "backend_completion_reason_verified": False,
            },
            "resource_linkage": {"posture": resource_posture,
                **resource_fields,
                "ledger_reconciliation_posture": "not_performed_by_objective_result_inspector",
                "cpu_time_ms": None, "gpu_time_ms": None,
                "energy_joules": None, "generated_token_count": None,
                "measurement_posture": "unknown_without_ledger_or_token_measurement"}})
    descriptor = dict(request["task_descriptor"])
    task_specification = dict(request["task"])
    task_family = None
    if task_specification.get("schema_version") == (
            "sentientos.affine_prediction_task_family_suite:v3"):
        task_family = {"task_family_id": descriptor.get("task_family_id"),
            "family_posture": descriptor.get("family_posture"),
            "probe_inputs": list(descriptor.get("probe_inputs", ())),
            "probe_count": descriptor.get("probe_count"),
            "task_digest": descriptor.get("task_digest"),
            "requires_task_family_history": descriptor.get("requires_task_family_history")}
    return {"status": "verified_objective_measurement", "measurement_id": measurement_id,
        "measurement_digest": run.get("run_digest"), "request_id": request["request_id"],
        "request_digest": request["request_digest"], "protocol_id": protocol.protocol_id,
        "protocol_digest": protocol.protocol_digest,
        "history_record_ids": list(protocol.record_ids),
        "history_record_digests": list(protocol.record_digests),
        "history_record_set_digest": protocol.record_set_digest,
        "objective_task_plan_digest": plan.get("plan_digest"),
        "task_family": task_family,
        "objective_evaluation": dict(evaluation), "conditions": outputs,
        "contamination_assessment": run.get("contamination_assessment", {
            "schema_version": "sentientos.objective_task_contamination_assessment:v1",
            "status": "legacy_not_recorded",
            "reason_code": "historical_run_predates_explicit_contamination_posture",
            "authority": False}),
        "actual_nonsynthetic_inference_verified": actual_inference,
        "execution_evidence_scope": (
            "authenticated_owner_receipt_and_serving_custody_not_independent_backend_observation"),
        "independent_backend_observation": False,
        "raw_prompt_output_and_oracle_retained_in_report": False,
        "authority": False, "canonical_explicit_user_retention": False}


def load_config(path: str | Path) -> ResidentDevelopmentalCognitionConfig:
    try:
        payload = json.loads(read_explicit_file(Path(path),
            max_bytes=MAX_RESIDENT_COGNITION_CONFIG_BYTES).decode("utf-8"))
    except (WindowsHandleCustodyError, UnicodeError, OSError, json.JSONDecodeError) as exc:
        raise ResidentDevelopmentalCognitionError("configuration_unreadable_or_invalid_json") from exc
    common = {"schema", "enabled", "history_root", "state_root", "allowed_source_kinds",
              "max_selected_facts", "max_retrieved_records", "comparison_enabled"}
    schema = payload.get("schema") if isinstance(payload, dict) else None
    expected = common if schema == CONFIG_SCHEMA else common | {"model_replacement_artifact_root"}
    if not isinstance(payload, dict) or set(payload) != expected or schema not in {CONFIG_SCHEMA, CONFIG_SCHEMA_V2}:
        raise ResidentDevelopmentalCognitionError("configuration_shape_invalid")
    kinds = payload.get("allowed_source_kinds")
    maximum = payload.get("max_selected_facts")
    history_maximum = payload.get("max_retrieved_records")
    if (not isinstance(payload.get("enabled"), bool) or not isinstance(payload.get("comparison_enabled"), bool)
            or not isinstance(kinds, list) or not kinds or any(not isinstance(x, str) or not x for x in kinds)
            or len(kinds) != len(set(kinds)) or not isinstance(maximum, int) or not 1 <= maximum <= MAX_FACTS
            or not isinstance(history_maximum, int) or not 1 <= history_maximum <= MAX_HISTORY
            or not isinstance(payload.get("history_root"), str) or not payload["history_root"]
            or not isinstance(payload.get("state_root"), str) or not payload["state_root"]):
        raise ResidentDevelopmentalCognitionError("configuration_values_invalid")
    provenance_root = payload.get("model_replacement_artifact_root")
    if schema == CONFIG_SCHEMA_V2 and (not isinstance(provenance_root, str) or not provenance_root):
        raise ResidentDevelopmentalCognitionError("configuration_values_invalid")
    history_root, state_root = Path(payload["history_root"]), Path(payload["state_root"])
    artifact_root = Path(provenance_root) if provenance_root is not None else None
    _validate_root_separation(history_root, state_root, artifact_root)
    return ResidentDevelopmentalCognitionConfig(history_root, state_root, tuple(sorted(kinds)), maximum,
        history_maximum, payload["comparison_enabled"], payload["enabled"],
        artifact_root)


def _unsafe_legacy_objective_cognition_fact(fact: Any) -> bool:
    """Identify historical oracle hashes that are verifiable but unsafe to republish."""
    if not isinstance(fact, Mapping):
        return False
    nested_payload = fact.get("payload")
    payload = nested_payload if isinstance(nested_payload, Mapping) else fact
    descriptor = payload.get("objective_task_descriptor")
    if (isinstance(descriptor, Mapping) and descriptor.get("task_digest")
            and descriptor.get("task_digest_posture")
                != "salted_private_oracle_commitment:v1"):
        return True
    if (isinstance(payload.get("objective_evaluation"), Mapping)
            and payload.get("objective_task_commitment_posture")
                != "salted_private_oracle_commitment:v1"):
        return True
    score_contract = payload.get("objective_score_contract")
    return (isinstance(score_contract, Mapping)
        and payload.get("objective_task_commitment_posture")
            != "salted_private_oracle_commitment:v1")


class ResidentDevelopmentalCognitionOwner:
    """Perform at most one deterministic developmental composition per call."""

    def __init__(self, *, config: ResidentDevelopmentalCognitionConfig,
                 writeback: ResidentDevelopmentalWritebackController,
                 admission_authority: RuntimeAdmissionAuthority,
                 invoker: LocalModelInvoker,
                 current_sequence: Callable[[], int],
                 objective_task: Any | None = None,
                 resource_context_owner: Any | None = None) -> None:
        _validate_root_separation(config.history_root, config.state_root,
            config.model_replacement_artifact_root)
        self.config = config
        self.writeback = writeback
        self.admission_authority = admission_authority
        self.invoker = invoker
        self.current_sequence = current_sequence
        if (resource_context_owner is not None
                and not callable(getattr(resource_context_owner, "next_context", None))):
            raise ResidentDevelopmentalCognitionError(
                "developmental_resource_context_owner_invalid")
        self.resource_context_owner = resource_context_owner
        if objective_task is not None and (not config.comparison_enabled
                or not callable(getattr(objective_task, "specification", None))
                or not callable(getattr(objective_task, "public_descriptor", None))):
            raise ResidentDevelopmentalCognitionError("objective_task_requires_history_comparison")
        self.objective_task = objective_task
        self.state_path = config.state_root / "composition_state.json"
        self.observations_root = config.state_root / "cognition_observations"
        self.epistemic_revision_probe_captures_root = (
            config.state_root / "epistemic_revision_probe_captures")
        self.measurements_root = config.state_root / "changed_cognition_measurements"
        self.experiments = DevelopmentalExperimentStore(config.state_root,
            invocation_verifier=self._verify_observation_invocation)
        # Exact output text is held only until its separately admitted candidate
        # is committed in the same tick. It is never written as a cognition receipt.
        self._pending_cognition_candidates: dict[str, tuple[Any, str, Mapping[str, Any]]] = {}
        self._pending_objective_scores: dict[str, Mapping[str, Any]] = {}

    @staticmethod
    def _recovered_record_order(record: Any, *, completed_order: Mapping[str, int],
                                recovery_intent_order: Mapping[str, int]) -> tuple[int, int, str]:
        """Order recovery by durable tick intent, retaining time as validation only."""
        try:
            created = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
            if created.tzinfo is None:
                raise ValueError("naive")
        except (AttributeError, TypeError, ValueError) as exc:
            raise ResidentDevelopmentalCognitionError("recovered_history_time_invalid") from exc
        suffix = ":resident-developmental-writeback"
        correlation = record.correlation_id
        if not isinstance(correlation, str) or not correlation.endswith(suffix):
            raise ResidentDevelopmentalCognitionError("recovered_tick_correlation_invalid")
        recovered_tick = correlation[:-len(suffix)]
        if recovered_tick in completed_order:
            return (0, completed_order[recovered_tick], record.record_id)
        if recovered_tick not in recovery_intent_order:
            raise ResidentDevelopmentalCognitionError("recovered_tick_intent_missing")
        # Wall-clock creation timestamps and content-addressed filenames cannot
        # establish transaction order after interrupted checkpoint publication.
        return (1, recovery_intent_order[recovered_tick], record.record_id)

    def _verify_recovered_cognition_candidate(
        self, record: Any, observations: Mapping[str, Mapping[str, Any]]
    ) -> None:
        candidate = record.candidate
        provenance = candidate.get("transformation_provenance")
        if (not isinstance(provenance, Mapping)
                or provenance.get("kind") != COGNITION_LESSON_PROVENANCE_KIND):
            return
        observation_id = provenance.get("observation_id")
        observation_digest = provenance.get("observation_digest")
        observation = observations.get(str(observation_id))
        source_text = provenance.get("source_output_text")
        context = provenance.get("consumed_context")
        if (not isinstance(context, Mapping)
                or not isinstance(observation, Mapping)
                or observation.get("observation_digest") != observation_digest
                or observation.get("condition_id") != "with-history"
                or observation.get("tick_id") != context.get("tick_id")
                or observation.get("output_digest") != candidate.get("output_digest")
                or observation.get("request_id") != candidate.get("request_id")
                or observation.get("request_digest") != candidate.get("request_digest")
                or observation.get("inference_receipt_id") != candidate.get("inference_receipt_id")
                or observation.get("inference_receipt_digest") != candidate.get("inference_receipt_digest")
                or observation.get("model_id") != candidate.get("model_id")
                or observation.get("model_artifact_digest") != candidate.get("model_artifact_digest")
                or provenance.get("model_id") != candidate.get("model_id")
                or provenance.get("model_artifact_digest") != candidate.get("model_artifact_digest")
                or provenance.get("active_model_identity") != observation.get("active_model_identity")
                or provenance.get("authority_map_digest") != observation.get("authority_map_digest")
                or list(candidate.get("selected_fact_ids", ())) != list(observation.get("current_fact_ids", ()))
                or not isinstance(source_text, str)
                or digest_payload({"output": source_text}) != observation.get("output_digest")):
            raise ResidentDevelopmentalCognitionError("recovered_cognition_candidate_source_mismatch")
        consumed = (set(observation.get("retrieved_record_ids", ()))
            | set(observation.get("current_fact_ids", ()))
            | set(observation.get("self_model_claim_ids", ()))
            | set(observation.get("epistemic_consumed_packet_ids", ())))
        try:
            parsed = _parse_cognition_lesson_output(source_text, consumed)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ResidentDevelopmentalCognitionError("recovered_cognition_candidate_output_invalid") from exc
        context = provenance.get("consumed_context")
        if (not isinstance(context, Mapping)
                or parsed.get("lesson_candidate") != provenance.get("lesson_candidate")
                or parsed.get("conclusion") != provenance.get("conclusion")
                or any(context.get(key) != observation.get(key) for key in (
                    "tick_id", "condition_id", "correlation_id", "current_snapshot_id",
                    "current_snapshot_digest", "current_projection_id", "current_projection_digest",
                    "current_fact_ids", "retrieved_record_ids", "retrieved_record_digests",
                    "self_model_projection_present", "self_model_projection_id",
                    "self_model_projection_digest", "self_model_reconciliation_id",
                    "self_model_reconciliation_digest", "self_model_reconciliation_generation",
                    "self_model_source_tick", "self_model_claim_ids", "self_model_claim_digests",
                    "epistemic_projection_present", "epistemic_projection_id",
                    "epistemic_projection_digest", "epistemic_proposition_ids",
                    "epistemic_state_ids", "epistemic_state_digests", "epistemic_generations",
                    "epistemic_evidence_set_digests", "epistemic_projection_schema",
                    "epistemic_semantic_status", "epistemic_owner_packet_count",
                    "epistemic_consumed_packet_ids", "epistemic_consumed_packet_digests",
                    "epistemic_omitted_packets", "epistemic_omitted_packets_digest",
                    "epistemic_consumed_packets_digest", "epistemic_projection_context_digest",
                    "epistemic_prompt_digest", "epistemic_consumed_content_digest",
                    "developmental_history_selection"))):
            raise ResidentDevelopmentalCognitionError("recovered_cognition_candidate_context_mismatch")

    def _state(self) -> dict[str, Any]:
        state_migrated = False
        state_bytes: bytes | None = None
        if os.name == "nt":
            try:
                self.state_path.parent.lstat()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise ResidentDevelopmentalCognitionError("composition_state_unavailable") from exc
            else:
                try:
                    entries = read_regular_files(self.state_path.parent,
                        max_entries=1, max_file_bytes=MAX_COMPOSITION_STATE_BYTES,
                        max_total_bytes=MAX_COMPOSITION_STATE_BYTES,
                        suffix=self.state_path.name)
                except WindowsHandleCustodyError as exc:
                    raise ResidentDevelopmentalCognitionError("composition_state_safe_read_failed") from exc
                if len(entries) > 1:
                    raise ResidentDevelopmentalCognitionError("composition_state_identity_ambiguous")
                if entries:
                    name, state_bytes = entries[0]
                    if name != self.state_path.name:
                        raise ResidentDevelopmentalCognitionError("composition_state_identity_ambiguous")
        else:
            try:
                root_fd = _open_store_directory(self.state_path.parent, create=False)
            except DevelopmentalWritebackError as exc:
                if str(exc) != "durable_store_root_missing":
                    raise ResidentDevelopmentalCognitionError("composition_state_root_invalid") from exc
            else:
                try:
                    try:
                        state_bytes = _read_store_file(root_fd, self.state_path.name, max_bytes=MAX_COMPOSITION_STATE_BYTES)
                    except DevelopmentalWritebackError as exc:
                        if str(exc) != "stored_payload_missing":
                            raise ResidentDevelopmentalCognitionError("composition_state_corrupt") from exc
                finally:
                    os.close(root_fd)
        state: dict[str, Any]
        if state_bytes is None:
            semantic = {"schema": STATE_SCHEMA, "processed_selection_ids": [], "completed_ticks": [],
                "incomplete_ticks": []}
            state = {**semantic, "state_digest": _digest(semantic)}
        else:
            try:
                value = json.loads(state_bytes.decode("utf-8"))
                if (not isinstance(value, dict)
                        or json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n" != state_bytes):
                    raise ResidentDevelopmentalCognitionError("composition_state_noncanonical")
                claimed = value.pop("state_digest")
            except (UnicodeError, json.JSONDecodeError, KeyError, AttributeError, TypeError) as exc:
                raise ResidentDevelopmentalCognitionError("composition_state_corrupt") from exc
            if value.get("schema") not in {STATE_SCHEMA, LEGACY_STATE_SCHEMA} or claimed != _digest(value):
                raise ResidentDevelopmentalCognitionError("composition_state_digest_mismatch")
            if (not isinstance(value.get("processed_selection_ids"), list)
                    or any(not isinstance(item, str) for item in value["processed_selection_ids"])
                    or not isinstance(value.get("completed_ticks"), list)
                    or any(not isinstance(item, dict) for item in value["completed_ticks"])):
                raise ResidentDevelopmentalCognitionError("composition_state_shape_invalid")
            if value.get("schema") == LEGACY_STATE_SCHEMA:
                value["schema"] = STATE_SCHEMA
                value["incomplete_ticks"] = []
                state_migrated = True
            elif (not isinstance(value.get("incomplete_ticks"), list)
                    or any(not isinstance(item, dict) for item in value["incomplete_ticks"])):
                raise ResidentDevelopmentalCognitionError("composition_state_shape_invalid")
            migrated = {key: item for key, item in value.items() if key != "state_digest"}
            claimed = _digest(migrated)
            state = {**migrated, "state_digest": claimed}
        if (len(state["processed_selection_ids"]) > MAX_RECOVERED_FACT_IDS
                or len(state["completed_ticks"]) + len(state["incomplete_ticks"]) > MAX_RECOVERED_TICKS):
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
        changed = state_migrated
        # The record and receipt are the commit point. Rebuild the checkpoint
        # if a process stopped after publication but before composition_state.
        try:
            recovered = self.writeback.recover_completed_records()
        except Exception as exc:
            raise ResidentDevelopmentalCognitionError("developmental_history_recovery_failed") from exc
        processed_ids: list[str] = list(state["processed_selection_ids"])
        completed_tick_rows: list[dict[str, Any]] = list(state["completed_ticks"])
        incomplete_tick_rows: list[dict[str, Any]] = list(state["incomplete_ticks"])
        processed = set(processed_ids)
        ticks: dict[str, dict[str, Any]] = {}
        for completed_row in completed_tick_rows:
            saved_tick = completed_row.get("tick_id")
            if not isinstance(saved_tick, str) or not saved_tick or saved_tick in ticks:
                raise ResidentDevelopmentalCognitionError("composition_tick_identity_ambiguous")
            ticks[saved_tick] = completed_row
        incomplete: dict[str, dict[str, Any]] = {}
        recovery_intent_order: dict[str, int] = {}
        for index, incomplete_row in enumerate(incomplete_tick_rows):
            saved_tick = incomplete_row.get("tick_id")
            if not isinstance(saved_tick, str) or not saved_tick or saved_tick in incomplete or saved_tick in ticks:
                raise ResidentDevelopmentalCognitionError("composition_tick_identity_ambiguous")
            if incomplete_row.get("status") == "in_progress":
                recovery_intent_order[saved_tick] = index
                # The durable marker is written before any cognition call. If
                # it is still present on the next owner entry, completion was
                # interrupted; preserve that fact and never retry this tick.
                incomplete_row["status"] = "interrupted_recovered"
                changed = True
            incomplete[saved_tick] = incomplete_row
        completed_order = {tick: index for index, tick in enumerate(ticks)}

        recovered = tuple(sorted(recovered, key=lambda item:
            self._recovered_record_order(item[0], completed_order=completed_order,
                recovery_intent_order=recovery_intent_order)))
        recovered_observations = self._recover_observation_ticks(include_records=True)
        if self._recover_interrupted_objective_runs(state, recovered_observations):
            changed = True
        for record, receipt in recovered:
            self._verify_recovered_cognition_candidate(record, recovered_observations)
            candidate = record.candidate
            fact_ids = candidate.get("selected_fact_ids", ())
            if not isinstance(fact_ids, (list, tuple)) or any(not isinstance(item, str) for item in fact_ids):
                raise ResidentDevelopmentalCognitionError("recovered_fact_identity_invalid")
            for fact_id in fact_ids:
                if fact_id not in processed:
                    processed_ids.append(fact_id)
                    processed.add(fact_id)
                    changed = True
            suffix = ":resident-developmental-writeback"
            correlation = record.correlation_id
            if not correlation.endswith(suffix):
                raise ResidentDevelopmentalCognitionError("recovered_tick_correlation_invalid")
            recovered_tick = correlation[:-len(suffix)]
            if not recovered_tick:
                raise ResidentDevelopmentalCognitionError("recovered_tick_correlation_invalid")
            expected_operation = "resident-developmental-writeback:" + recovered_tick + ":" + str(candidate.get("candidate_id"))
            if not recovered_tick or record.operation_id != expected_operation:
                raise ResidentDevelopmentalCognitionError("recovered_tick_operation_binding_invalid")
            existing = ticks.get(recovered_tick)
            checkpoint = {"tick_id": recovered_tick, "snapshot_id": candidate.get("snapshot_id"),
                "snapshot_digest": candidate.get("snapshot_digest"), "record_id": record.record_id,
                "receipt_id": receipt.receipt_id}
            if existing is None:
                completed_tick_rows.append(checkpoint)
                ticks[recovered_tick] = checkpoint
                changed = True
            elif existing.get("record_id") != record.record_id or existing.get("receipt_id") != receipt.receipt_id:
                raise ResidentDevelopmentalCognitionError("recovered_tick_record_conflict")
            if recovered_tick in incomplete:
                del incomplete[recovered_tick]
                incomplete_tick_rows = [saved_row for saved_row in incomplete_tick_rows
                    if saved_row.get("tick_id") != recovered_tick]
                changed = True
        # A durable cognition observation without its enclosing tick checkpoint
        # is an interrupted tick. Preserve it and reject same-tick replay.
        for recovered_tick, observation_ids in self._recover_observation_ticks().items():
            if not isinstance(recovered_tick, str) or not recovered_tick:
                raise ResidentDevelopmentalCognitionError("recovered_tick_identity_invalid")
            if recovered_tick in ticks or recovered_tick in incomplete:
                continue
            item = {"tick_id": recovered_tick, "observation_ids": list(observation_ids),
                "status": "incomplete_recovered"}
            incomplete_tick_rows.append(item)
            incomplete[recovered_tick] = item
            changed = True
        state["processed_selection_ids"] = processed_ids
        state["completed_ticks"] = completed_tick_rows
        state["incomplete_ticks"] = incomplete_tick_rows
        if (len(processed_ids) > MAX_RECOVERED_FACT_IDS
                or len(completed_tick_rows) + len(incomplete_tick_rows) > MAX_RECOVERED_TICKS):
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
        if changed:
            self._save_state(state)
        return state

    def _recover_interrupted_objective_runs(self, state: dict[str, Any],
            observations: Mapping[str, Mapping[str, Any]]) -> bool:
        """Finalize only fully receipted objective runs; never resume inference."""
        changed = False
        for intent in state["incomplete_ticks"]:
            protocol_id = intent.get("objective_protocol_id")
            if protocol_id is None:
                continue
            if (not isinstance(protocol_id, str)
                    or intent.get("status") != "interrupted_recovered"):
                raise ResidentDevelopmentalCognitionError(
                    "interrupted_objective_protocol_intent_invalid")
            try:
                protocol = self.experiments.load_protocol(protocol_id)
                plan = self.experiments.verify_objective_task_plan(protocol)
            except DevelopmentalHistoryInterventionError as exc:
                raise ResidentDevelopmentalCognitionError(
                    "interrupted_objective_protocol_recovery_failed") from exc
            if protocol.schema_version not in OBJECTIVE_SCHEMAS:
                raise ResidentDevelopmentalCognitionError(
                    "interrupted_objective_protocol_schema_mismatch")
            if (plan.get("plan_digest") != intent.get("objective_task_plan_digest")
                    or protocol.snapshot_id != intent.get("snapshot_id")
                    or protocol.snapshot_digest != intent.get("snapshot_digest")):
                raise ResidentDevelopmentalCognitionError(
                    "interrupted_objective_intent_binding_mismatch")
            by_condition: dict[str, Mapping[str, Any]] = {}
            for observation in observations.values():
                if observation.get("tick_id") != intent.get("tick_id"):
                    continue
                condition = observation.get("condition_id")
                if condition not in CONDITION_ORDER:
                    continue
                if condition in by_condition:
                    raise ResidentDevelopmentalCognitionError(
                        "interrupted_objective_condition_conflict")
                by_condition[str(condition)] = observation
            if set(by_condition) != set(CONDITION_ORDER):
                continue

            observation_values: list[ResidentCognitionObservation] = []
            score_values: list[dict[str, Any]] = []
            missing_checkpoint = False
            tuple_fields = ("current_fact_ids", "retrieved_record_ids", "retrieved_record_digests",
                "self_model_claim_ids", "self_model_claim_digests", "epistemic_proposition_ids",
                "epistemic_state_ids", "epistemic_state_digests", "epistemic_generations",
                "epistemic_evidence_set_digests", "epistemic_consumed_packet_ids",
                "epistemic_consumed_packet_digests", "epistemic_omitted_packets")
            for condition in CONDITION_ORDER:
                raw = by_condition[condition]
                value = dict(raw)
                for field in tuple_fields:
                    if field in value:
                        value[field] = tuple(value[field])
                try:
                    observation_values.append(ResidentCognitionObservation(**value))
                    checkpoint = self.experiments.load_objective_condition_score(
                        protocol, condition_id=condition, observation=raw)
                except DevelopmentalHistoryInterventionError as exc:
                    if str(exc) == "objective_condition_score_missing":
                        missing_checkpoint = True
                        break
                    raise ResidentDevelopmentalCognitionError(
                        "interrupted_objective_score_recovery_failed") from exc
                except (TypeError, ValueError) as exc:
                    raise ResidentDevelopmentalCognitionError(
                        "interrupted_objective_observation_invalid") from exc
                score_values.append({"condition_id": condition,
                    "inference_receipt_id": raw["inference_receipt_id"],
                    "inference_receipt_digest": raw["inference_receipt_digest"],
                    "invocation_output_digest": raw["output_digest"],
                    "output_truncated": checkpoint.get("output_truncated", False),
                    "score": dict(checkpoint["score"])})
            if missing_checkpoint:
                continue
            try:
                recovered_conditions: list[dict[str, Any]] = []
                for observation_value in observation_values:
                    payload = asdict(observation_value)
                    if observation_value.schema_version not in {
                            COGNITION_OBSERVATION_SCHEMA_V6, COGNITION_OBSERVATION_SCHEMA_V7}:
                        # Preserve the historical run digest/shape when
                        # rebuilding interrupted pre-v6 experiments.
                        payload.pop("developmental_history_selection", None)
                    if observation_value.schema_version != COGNITION_OBSERVATION_SCHEMA_V7:
                        for field in ("resource_allocation_digest", "resource_attempt_id",
                                "resource_consumption_receipt_digests", "resource_linkage_digest"):
                            payload.pop(field, None)
                    recovered_conditions.append(payload)
                summary = summarize(protocol, observation_values)
                evaluation = summarize_objective_task(plan, score_values)
                run_payload = {"protocol": asdict(protocol),
                    "conditions": recovered_conditions,
                    "summary": summary, "validity": "valid_controlled_observation",
                    "contamination_reasons": None, "objective_scores": score_values,
                    "objective_evaluation": evaluation,
                    "contamination_assessment": objective_task_contamination_assessment(protocol)}
                run_id = self.experiments.persist_run(run_payload)
                run = self.experiments.load_run(run_id)
            except (DevelopmentalHistoryInterventionError, TypeError, ValueError) as exc:
                raise ResidentDevelopmentalCognitionError(
                    "interrupted_objective_run_recovery_failed") from exc
            recovered_fields = {
                "recovered_experiment_run_id": run_id,
                "recovered_experiment_run_digest": str(run["run_digest"]),
                "experiment_recovery_posture":
                    "complete_scored_run_recovered_without_inference_replay",
            }
            if any(intent.get(key) != value for key, value in recovered_fields.items()):
                intent.update(recovered_fields)
                changed = True
        return changed

    def recovered_objective_experiment_run_refs(self) -> tuple[tuple[str, str], ...]:
        """Return explicitly selectable recovered run identities after validation."""
        state = self._state()
        refs: list[tuple[str, str]] = []
        for intent in state["incomplete_ticks"]:
            run_id = intent.get("recovered_experiment_run_id")
            run_digest = intent.get("recovered_experiment_run_digest")
            if run_id is None and run_digest is None:
                continue
            if not isinstance(run_id, str) or not isinstance(run_digest, str):
                raise ResidentDevelopmentalCognitionError(
                    "recovered_objective_run_reference_invalid")
            try:
                run = self.experiments.load_run(run_id)
            except DevelopmentalHistoryInterventionError as exc:
                raise ResidentDevelopmentalCognitionError(
                    "recovered_objective_run_reference_invalid") from exc
            if run.get("run_digest") != run_digest:
                raise ResidentDevelopmentalCognitionError(
                    "recovered_objective_run_reference_conflict")
            refs.append((run_id, run_digest))
        return tuple(refs)

    def inspect_completed_objective_experiment_run_refs(self, *,
            limit: int = 32) -> tuple[tuple[str, str], ...]:
        """Read completed, real-inference objective runs without repairing custody.

        This is the World-State observer path. It reads only the exact
        composition-state file and the request/run identities named by it;
        unlike ``_state()``, it never recovers ticks or publishes repairs.
        """
        if type(limit) is not int or not 1 <= limit <= 32:
            raise ResidentDevelopmentalCognitionError("objective_run_projection_limit_invalid")
        try:
            raw = read_explicit_file(self.state_path, max_bytes=MAX_COMPOSITION_STATE_BYTES)
        except WindowsHandleCustodyError as exc:
            if str(exc) == "explicit_file_missing":
                return ()
            raise ResidentDevelopmentalCognitionError("objective_run_projection_state_unavailable") from exc
        try:
            state = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object)
            if (not isinstance(state, dict)
                    or json.dumps(state, indent=2, sort_keys=True).encode("utf-8") + b"\n" != raw):
                raise ValueError("noncanonical")
            semantic = dict(state)
            claimed = semantic.pop("state_digest")
            completed, incomplete = semantic.get("completed_ticks"), semantic.get("incomplete_ticks", [])
            if (semantic.get("schema") not in {STATE_SCHEMA, LEGACY_STATE_SCHEMA}
                    or claimed != _digest(semantic)
                    or not isinstance(completed, list) or not isinstance(incomplete, list)
                    or any(not isinstance(row, dict) for row in completed + incomplete)
                    or len(completed) + len(incomplete) > MAX_RECOVERED_TICKS):
                raise ValueError("state")
            tick_ids = [row.get("tick_id") for row in completed + incomplete]
            if (any(not isinstance(value, str) or not value for value in tick_ids)
                    or len(tick_ids) != len(set(tick_ids))):
                raise ValueError("tick_identity")
        except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ResidentDevelopmentalCognitionError("objective_run_projection_state_invalid") from exc

        candidates: list[tuple[Mapping[str, Any], str, str | None]] = []
        for row in completed:
            if row.get("objective_request_status") != "completed":
                continue
            request_id, request_digest, run_id = (row.get("objective_request_id"),
                row.get("objective_request_digest"), row.get("measurement_id"))
            if not all(isinstance(value, str) and value for value in
                    (request_id, request_digest, run_id)):
                raise ResidentDevelopmentalCognitionError("objective_run_projection_reference_invalid")
            candidates.append((row, run_id, None))
        for row in incomplete:
            if row.get("experiment_recovery_posture") != (
                    "complete_scored_run_recovered_without_inference_replay"):
                continue
            # Ordinary configured comparisons have no one-shot request
            # identity. They remain available through their existing explicit
            # recovery interface but cannot enter this staged-request bridge.
            if row.get("objective_request_id") is None and row.get("objective_request_digest") is None:
                continue
            run_id, run_digest = (row.get("recovered_experiment_run_id"),
                row.get("recovered_experiment_run_digest"))
            if not isinstance(run_id, str) or not isinstance(run_digest, str):
                raise ResidentDevelopmentalCognitionError("objective_run_projection_reference_invalid")
            candidates.append((row, run_id, run_digest))

        refs: list[tuple[str, str]] = []
        identities: dict[str, str] = {}
        for row, run_id, expected_digest in candidates[-limit:]:
            request_id = row.get("objective_request_id")
            request_digest = row.get("objective_request_digest")
            if not isinstance(request_id, str) or not isinstance(request_digest, str):
                raise ResidentDevelopmentalCognitionError("objective_run_projection_request_missing")
            try:
                request = load_objective_request_by_identity(self.config.state_root,
                    request_id=request_id, request_digest=request_digest)
                summary = self.verified_objective_measurement_summary(
                    measurement_id=run_id, request=request)
            except (ResidentDevelopmentalCognitionError, DevelopmentalHistoryInterventionError) as exc:
                raise ResidentDevelopmentalCognitionError("objective_run_projection_verification_failed") from exc
            run_digest = summary.get("measurement_digest")
            if (summary.get("status") != "verified_objective_measurement"
                    or summary.get("actual_nonsynthetic_inference_verified") is not True
                    or not isinstance(run_digest, str)
                    or (expected_digest is not None and expected_digest != run_digest)):
                raise ResidentDevelopmentalCognitionError("objective_run_projection_not_verified_real_inference")
            prior = identities.get(run_id)
            if prior is not None and prior != run_digest:
                raise ResidentDevelopmentalCognitionError("objective_run_projection_identity_conflict")
            if prior is None:
                identities[run_id] = run_digest
                refs.append((run_id, run_digest))
        return tuple(refs)

    def verified_objective_measurement_summary(self, *, measurement_id: str,
            request: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return a bounded score summary only after revalidating its exact receipts."""
        return verified_objective_measurement_summary(experiments=self.experiments,
            measurement_id=measurement_id, request=request,
            verify_observation=self._verify_observation_invocation)

    def verified_objective_measurement_for_request(self, *, request_id: str,
            request_digest: str) -> Mapping[str, Any]:
        """Recover an exact request outcome and its score without replaying inference."""
        state = self._state()
        rows = [row for row in (*state["completed_ticks"], *state["incomplete_ticks"])
            if row.get("objective_request_id") == request_id]
        if not rows:
            return {"status": "objective_request_not_recorded", "request_id": request_id,
                "authority": False}
        if len(rows) != 1 or rows[0].get("objective_request_digest") != request_digest:
            raise ResidentDevelopmentalCognitionError("objective_request_identity_conflict")
        row = rows[0]
        completed = row in state["completed_ticks"]
        run_id = (row.get("measurement_id") if completed
            else row.get("recovered_experiment_run_id"))
        expected_run_digest = (row.get("recovered_experiment_run_digest")
            if not completed else None)
        if not isinstance(run_id, str) or not run_id:
            return {"status": row.get("objective_request_status",
                    "interrupted_without_complete_score"),
                "request_id": request_id, "request_digest": request_digest,
                "tick_id": row.get("tick_id"), "recovery_posture": (
                    "completed_request_without_score" if completed else
                    "interrupted_score_not_recoverable_without_replay"),
                "authority": False}
        request = load_objective_request_by_identity(self.config.state_root,
            request_id=request_id, request_digest=request_digest)
        try:
            run = self.experiments.load_run(run_id)
        except DevelopmentalHistoryInterventionError as exc:
            raise ResidentDevelopmentalCognitionError("objective_outcome_custody_invalid") from exc
        if (expected_run_digest is not None
                and run.get("run_digest") != expected_run_digest):
            raise ResidentDevelopmentalCognitionError("objective_outcome_recovered_run_digest_mismatch")
        result = dict(self.verified_objective_measurement_summary(
            measurement_id=run_id, request=request))
        result["tick_id"] = row.get("tick_id")
        result["recovery_posture"] = ("completed_run_loaded_without_inference_replay"
            if not completed else "completed_run_loaded")
        return result

    def verified_objective_task_family_progression(self, *,
            request_refs: Sequence[tuple[str, str]]) -> Mapping[str, Any]:
        """Build a bounded, read-only chronology from receipt-verified family runs.

        This path reads the checkpoint directly and never invokes tick recovery
        or publishes a custody repair. It describes scored episodes and exact
        execution controls; it is not a learning claim. Completed-tick journal
        order, not caller order or recovery wall time, defines chronology.
        """
        if (not isinstance(request_refs, Sequence) or isinstance(request_refs, (str, bytes))
                or not 1 <= len(request_refs) <= 16):
            raise ResidentDevelopmentalCognitionError(
                "objective_progression_episode_count_invalid")
        refs: dict[str, str] = {}
        for reference in request_refs:
            if (not isinstance(reference, (tuple, list)) or len(reference) != 2
                    or not all(isinstance(value, str) and value and len(value) <= 256
                        for value in reference)):
                raise ResidentDevelopmentalCognitionError(
                    "objective_progression_reference_invalid")
            request_id, request_digest = reference
            prior = refs.get(request_id)
            if prior is not None:
                raise ResidentDevelopmentalCognitionError(
                    "objective_progression_duplicate_request")
            refs[request_id] = request_digest

        try:
            raw_state = read_explicit_file(self.state_path,
                max_bytes=MAX_COMPOSITION_STATE_BYTES)
        except WindowsHandleCustodyError as exc:
            raise ResidentDevelopmentalCognitionError(
                "objective_progression_checkpoint_unavailable") from exc
        try:
            state_value = json.loads(raw_state.decode("utf-8"),
                object_pairs_hook=_unique_json_object)
            if (not isinstance(state_value, dict)
                    or json.dumps(state_value, indent=2, sort_keys=True).encode("utf-8")
                        + b"\n" != raw_state):
                raise ValueError("noncanonical")
            state = dict(state_value)
            claimed = state.pop("state_digest")
            completed = state.get("completed_ticks")
            incomplete = state.get("incomplete_ticks", [])
            processed = state.get("processed_selection_ids")
            if (state.get("schema") not in {STATE_SCHEMA, LEGACY_STATE_SCHEMA}
                    or claimed != _digest(state)
                    or not isinstance(completed, list) or not isinstance(incomplete, list)
                    or not isinstance(processed, list)
                    or any(not isinstance(row, dict) for row in completed + incomplete)
                    or any(not isinstance(item, str) for item in processed)
                    or len(completed) + len(incomplete) > MAX_RECOVERED_TICKS
                    or len(processed) > MAX_RECOVERED_FACT_IDS):
                raise ValueError("checkpoint")
            tick_ids = [row.get("tick_id") for row in completed + incomplete]
            if (any(not isinstance(item, str) or not item for item in tick_ids)
                    or len(set(tick_ids)) != len(tick_ids)):
                raise ValueError("tick identities")
        except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ResidentDevelopmentalCognitionError(
                "objective_progression_checkpoint_invalid") from exc
        rows_by_request: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
        for posture, rows in (("completed", completed), ("incomplete", incomplete)):
            for row in rows:
                request_id = row.get("objective_request_id")
                if request_id in refs:
                    rows_by_request.setdefault(str(request_id), []).append((posture, row))
        incomplete_episodes: list[dict[str, Any]] = []
        for request_id, expected_digest in refs.items():
            rows = rows_by_request.get(request_id, [])
            if len(rows) != 1 or rows[0][1].get("objective_request_digest") != expected_digest:
                raise ResidentDevelopmentalCognitionError(
                    "objective_progression_checkpoint_identity_conflict")
            if rows[0][0] != "completed":
                incomplete_episodes.append({"request_id": request_id,
                    "request_digest": expected_digest,
                    "tick_id": rows[0][1].get("tick_id"),
                    "recovery_posture": rows[0][1].get("status", "incomplete")})
        if incomplete_episodes:
            return {"schema_version": "sentientos.objective_task_family_progression:v1",
                "status": "incomplete_episode_present",
                "incomplete_episodes": incomplete_episodes,
                "inference_replayed": False, "authority": False}

        episodes: list[dict[str, Any]] = []
        durable_history: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] | None = None
        for row in completed:
            request_id = row.get("objective_request_id")
            if request_id not in refs:
                continue
            run_id = row.get("measurement_id")
            if not isinstance(run_id, str) or not run_id:
                raise ResidentDevelopmentalCognitionError(
                    "objective_progression_completed_run_missing")
            try:
                request = load_objective_request_by_identity(self.config.state_root,
                    request_id=str(request_id), request_digest=refs[str(request_id)])
                verified = self.verified_objective_measurement_summary(
                    measurement_id=run_id, request=request)
            except (ResidentDevelopmentalCognitionError, DevelopmentalHistoryInterventionError) as exc:
                raise ResidentDevelopmentalCognitionError(
                    "objective_progression_measurement_unverified") from exc
            if (verified.get("status") != "verified_objective_measurement"
                    or not isinstance(verified.get("measurement_digest"), str)):
                raise ResidentDevelopmentalCognitionError(
                    "objective_progression_measurement_unverified")
            family = verified.get("task_family")
            if (not isinstance(family, Mapping)
                    or not isinstance(family.get("task_family_id"), str)
                    or not isinstance(family.get("task_digest"), str)
                    or not isinstance(family.get("probe_inputs"), list)
                    or type(family.get("probe_count")) is not int
                    or family.get("probe_count") != len(family["probe_inputs"])):
                raise ResidentDevelopmentalCognitionError(
                    "objective_progression_task_family_required")
            history_ids = verified.get("history_record_ids", ())
            history_digests = verified.get("history_record_digests", ())
            if (not isinstance(history_ids, (list, tuple))
                    or not isinstance(history_digests, (list, tuple))
                    or len(history_ids) != len(history_digests)
                    or len(history_ids) > MAX_HISTORY
                    or any(not isinstance(value, str) or not value for value in history_ids)
                    or len(set(history_ids)) != len(history_ids)
                    or any(not isinstance(value, str) or not value.startswith("sha256:")
                        for value in history_digests)):
                raise ResidentDevelopmentalCognitionError(
                    "objective_progression_history_identity_invalid")
            if durable_history is None:
                try:
                    durable_history = {
                        record.record_id: (asdict(record), asdict(receipt))
                        for record, receipt in self.writeback.inspect_completed_records()}
                except DevelopmentalWritebackError as exc:
                    raise ResidentDevelopmentalCognitionError(
                        "objective_progression_history_recovery_failed") from exc
            family_history_ids: list[str] = []
            family_history_digests: list[str] = []
            for record_id, expected_digest in zip(history_ids, history_digests):
                stored = durable_history.get(record_id)
                if stored is None or stored[0].get("record_digest") != expected_digest:
                    raise ResidentDevelopmentalCognitionError(
                        "objective_progression_history_record_unverified")
                candidate = stored[0].get("candidate")
                facts = candidate.get("selected_facts", ()) if isinstance(candidate, Mapping) else ()
                if any(isinstance(fact, Mapping)
                        and isinstance(fact.get("payload"), Mapping)
                        and fact["payload"].get("objective_task_family")
                            == family.get("task_family_id")
                        for fact in facts):
                    family_history_ids.append(record_id)
                    family_history_digests.append(expected_digest)
            conditions = verified.get("conditions")
            if (not isinstance(conditions, list) or len(conditions) != len(CONDITION_ORDER)
                    or tuple(item.get("condition_id") for item in conditions
                        if isinstance(item, Mapping)) != CONDITION_ORDER):
                raise ResidentDevelopmentalCognitionError(
                    "objective_progression_condition_set_invalid")
            profiles = [item.get("model_generation_profile") for item in conditions]
            profile_digests = [profile.get("profile_digest")
                if isinstance(profile, Mapping) else None for profile in profiles]
            score_rows = []
            for item in conditions:
                assert isinstance(item, Mapping)
                retrieved_ids = item.get("retrieved_record_ids", ())
                retrieved_digests = item.get("retrieved_record_digests", ())
                if (not isinstance(retrieved_ids, (list, tuple))
                        or not isinstance(retrieved_digests, (list, tuple))
                        or len(retrieved_ids) != len(retrieved_digests)
                        or any(not isinstance(value, str) or not value
                            for value in retrieved_ids)
                        or len(set(retrieved_ids)) != len(retrieved_ids)):
                    raise ResidentDevelopmentalCognitionError(
                        "objective_progression_retrieval_identity_invalid")
                for retrieved_id, retrieved_digest in zip(retrieved_ids, retrieved_digests):
                    stored = durable_history.get(retrieved_id) if durable_history is not None else None
                    if (stored is None
                            or stored[0].get("record_digest") != retrieved_digest):
                        raise ResidentDevelopmentalCognitionError(
                            "objective_progression_retrieved_history_unverified")
                matching_retrieved = [record_id for record_id in family_history_ids
                    if record_id in retrieved_ids]
                count = item.get("correct_count")
                score_rows.append({"condition_id": item.get("condition_id"),
                    "correct_count": count if type(count) is int else None,
                    "probe_count": family["probe_count"],
                    "scoreable": type(count) is int,
                    "score_digest": item.get("score_digest"),
                    "output_digest": item.get("output_digest"),
                    "receipt_status": item.get("receipt_status"),
                    "execution_evidence_posture": item.get("execution_evidence_posture"),
                    "output_truncated": item.get("output_truncated"),
                    "output_size_bytes": item.get("output_size_bytes"),
                    "output_size_posture": item.get("output_size_posture"),
                    "backend_completion": (dict(item["backend_completion"])
                        if isinstance(item.get("backend_completion"), Mapping) else None),
                    "backend_completion_posture": item.get("backend_completion_posture"),
                    "generation_budget": dict(item.get("generation_budget", {})),
                    "resource_linkage": dict(item.get("resource_linkage", {})),
                    "inference_receipt_id": item.get("inference_receipt_id"),
                    "inference_receipt_digest": item.get("inference_receipt_digest"),
                    "retrieved_record_ids": list(item.get("retrieved_record_ids", ())),
                    "retrieved_record_digests": list(item.get(
                        "retrieved_record_digests", ())),
                    "task_family_retrieved_record_ids": matching_retrieved,
                    "task_family_retrieval_posture": (
                        "matching_admitted_task_family_history_retrieved"
                        if matching_retrieved else "no_matching_admitted_task_family_history_retrieved"),
                    "history_selection_digest": item.get("history_selection_digest")})
            correct_counts = {str(item["condition_id"]): item["correct_count"]
                for item in score_rows}
            present_count = correct_counts.get("history_present")
            withheld_count = correct_counts.get("history_withheld")
            restored_count = correct_counts.get("history_restored")
            contrasts_scoreable = all(type(value) is int for value in (
                present_count, withheld_count, restored_count))
            score_contrasts = {
                "schema_version": "sentientos.task_family_episode_score_contrast:v1",
                "probe_denominator": family["probe_count"],
                "history_present_minus_withheld_correct_count": (
                    present_count - withheld_count if type(present_count) is int
                        and type(withheld_count) is int else None),
                "history_restored_minus_present_correct_count": (
                    restored_count - present_count if type(restored_count) is int
                        and type(present_count) is int else None),
                "posture": ("score_count_difference_only" if contrasts_scoreable
                    else "unscoreable_condition_prevents_complete_contrast"),
                "learning_established": False,
                "performance_improvement_established": False,
            }
            semantic = {"request_id": request_id,
                "request_digest": refs[str(request_id)],
                "episode_ordinal": len(episodes) + 1,
                "tick_id": row.get("tick_id"),
                "measurement_id": verified.get("measurement_id"),
                "measurement_digest": verified.get("measurement_digest"),
                "task_family": dict(family),
                "history_record_ids": list(verified.get("history_record_ids", ())),
                "history_record_digests": list(verified.get("history_record_digests", ())),
                "history_record_set_digest": verified.get("history_record_set_digest"),
                "task_family_history_record_ids": family_history_ids,
                "task_family_history_record_digests": family_history_digests,
                "task_family_history_relevance_posture": (
                    "matching_admitted_task_family_history_available"
                    if family_history_ids else "no_matching_admitted_task_family_history"),
                "model_generation_profiles": [dict(profile)
                    if isinstance(profile, Mapping) else None for profile in profiles],
                "model_generation_profile_digests": profile_digests,
                "scoreable": all(item["scoreable"] for item in score_rows),
                "score_contrasts": score_contrasts,
                "conditions": score_rows,
                "actual_nonsynthetic_inference_verified":
                    verified.get("actual_nonsynthetic_inference_verified") is True,
                "execution_evidence_scope": verified.get("execution_evidence_scope"),
                "independent_backend_observation": (
                    verified.get("independent_backend_observation") is True)}
            episodes.append(semantic)
        if len(episodes) != len(refs):
            raise ResidentDevelopmentalCognitionError(
                "objective_progression_checkpoint_missing")
        family_ids = {episode["task_family"]["task_family_id"] for episode in episodes}
        task_digests = [episode["task_family"]["task_digest"] for episode in episodes]
        probe_keys = [_digest(episode["task_family"]["probe_inputs"]) for episode in episodes]
        profiles_comparable = all(
            episode["model_generation_profile_digests"]
                and None not in episode["model_generation_profile_digests"]
            for episode in episodes)
        profile_vectors = [tuple(episode["model_generation_profile_digests"])
            for episode in episodes]
        same_profile = profiles_comparable and len(set(profile_vectors)) == 1
        distinct_tasks = len(set(task_digests)) == len(task_digests)
        distinct_probes = len(set(probe_keys)) == len(probe_keys)
        scored = all(episode["scoreable"] for episode in episodes)
        condition_rows = [condition for episode in episodes
            for condition in episode["conditions"]]
        execution_cost_summary = {
            "condition_count": len(condition_rows),
            "invocation_receipt_identity_count": sum(bool(row.get("inference_receipt_id")
                and row.get("inference_receipt_digest")) for row in condition_rows),
            "verified_completed_inference_count": sum(row.get("receipt_status") ==
                "admitted_local_model_inference" for row in condition_rows),
            "scoreable_condition_count": sum(row.get("scoreable") is True
                for row in condition_rows),
            "truncated_output_count": sum(row.get("output_truncated") is True
                for row in condition_rows),
            "receipt_linked_resource_condition_count": sum(
                row.get("resource_linkage", {}).get("posture") ==
                "invocation_receipt_linkage_verified_ledger_reconciliation_not_performed"
                for row in condition_rows),
            "ledger_reconciled_consumption_count": None,
            "resource_measurement_posture": "not_reconciled_by_progression_inspector",
            "backend_completion_report_count": sum(
                isinstance(row.get("backend_completion"), Mapping)
                for row in condition_rows),
            "backend_completion_measurement_posture": (
                "receipt_bound_backend_report_not_independent_measurement"),
            "cpu_time_ms": None, "gpu_time_ms": None, "energy_joules": None,
            "generated_token_count": None,
            "output_size_observations": [{"condition_id": row.get("condition_id"),
                "output_size_bytes": row.get("output_size_bytes"),
                "posture": row.get("output_size_posture")} for row in condition_rows],
        }
        comparable = (len(episodes) >= 2 and len(family_ids) == 1 and distinct_tasks and distinct_probes
            and same_profile and scored)
        semantic = {"schema_version": "sentientos.objective_task_family_progression:v1",
            "status": "comparable_scored_episodes" if comparable else
                "insufficient_episode_count" if len(episodes) < 2 else
                "descriptive_episodes_not_comparable",
            "task_family_id": next(iter(family_ids)) if len(family_ids) == 1 else None,
            "episode_count": len(episodes), "episodes": episodes,
            "episodes_with_admitted_task_family_history": sum(
                bool(episode["task_family_history_record_ids"]) for episode in episodes),
            "matching_task_family_history_retrieved_for_all_episodes": bool(episodes) and all(
                bool(episode["task_family_history_record_ids"])
                and all(condition["task_family_retrieval_posture"]
                    == "matching_admitted_task_family_history_retrieved"
                    for condition in episode["conditions"]
                    if condition["condition_id"] in {"history_present", "history_restored"})
                and not any(condition["task_family_retrieved_record_ids"]
                    for condition in episode["conditions"]
                    if condition["condition_id"] == "history_withheld")
                for episode in episodes),
            "same_model_generation_controls": same_profile,
            "distinct_task_instances": distinct_tasks,
            "distinct_probe_sets": distinct_probes,
            "all_episodes_scoreable": scored,
            "execution_cost_summary": execution_cost_summary,
            "actual_nonsynthetic_inference_verified": all(
                episode["actual_nonsynthetic_inference_verified"] for episode in episodes),
            "execution_evidence_scope": (
                "authenticated_owner_receipts_not_independent_backend_observation"),
            "independent_backend_observation": False,
            "interpretation": "descriptive_task_correctness_only",
            "performance_improvement_established": False,
            "learning_established": False, "authority": False,
            "canonical_explicit_user_retention": False,
            "inference_replayed": False}
        return {**semantic, "progression_id": "objective-progression-" +
            _digest(semantic)[7:31], "progression_digest": _digest(semantic)}

    def _verify_observation_invocation(self, observation: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """Reconcile a session-bound cognition row to its exact governed receipt."""
        session_id = observation.get("serving_session_id")
        session_binding = observation.get("serving_session_binding")
        if session_id is None and session_binding is None:
            if (observation.get("schema_version") == COGNITION_OBSERVATION_SCHEMA_V7
                    and observation.get("resource_linkage_digest") is not None):
                raise ResidentDevelopmentalCognitionError(
                    "cognition_resource_linked_invocation_session_unbound")
            return None  # Historical v2 and non-session invocations remain explicitly unbound.
        verifier = getattr(self.invoker, "verify_persisted_invocation_receipt", None)
        if not callable(verifier) or not isinstance(session_binding, Mapping):
            raise ResidentDevelopmentalCognitionError("cognition_invocation_receipt_verifier_unavailable")
        try:
            receipt = verifier(
                str(observation.get("inference_receipt_id", "")),
                str(observation.get("inference_receipt_digest", "")),
                expected_request_id=str(observation.get("request_id", "")),
                expected_request_digest=str(observation.get("request_digest", "")),
                expected_session_id=str(session_id),
                expected_session_binding=dict(session_binding),
                expected_active_model_identity=dict(observation.get("active_model_identity", {})),
                **({"expected_session_receipt_id": observation["serving_session_receipt_id"],
                    "expected_session_receipt_digest": observation["serving_session_receipt_digest"]}
                    if observation.get("serving_session_receipt_id") is not None else {}))
        except Exception as exc:
            raise ResidentDevelopmentalCognitionError("cognition_invocation_receipt_reconciliation_failed") from exc
        request = receipt.get("request") if isinstance(receipt, Mapping) else None
        request_linkage = request.get("linkage") if isinstance(request, Mapping) else None
        serving = (request_linkage.get("resident_cognitive_serving")
            if isinstance(request_linkage, Mapping) else None)
        expected_serving = {"session_id": session_id, **dict(session_binding)}
        if observation.get("serving_session_receipt_id") is not None:
            expected_serving.update({"session_receipt_id": observation["serving_session_receipt_id"],
                "session_receipt_semantic_digest": observation["serving_session_receipt_digest"]})
        if (not isinstance(request, Mapping)
                or receipt.get("receipt_id") != observation.get("inference_receipt_id")
                or receipt.get("receipt_digest") != observation.get("inference_receipt_digest")
                or receipt.get("status") not in {"admitted_completed", "admitted_simulation"}
                or request.get("request_id") != observation.get("request_id")
                or request.get("request_digest") != observation.get("request_digest")
                or request.get("model_id") != observation.get("model_id")
                or request.get("model_artifact_digest") != observation.get("model_artifact_digest")
                or request.get("active_model_identity") != observation.get("active_model_identity")
                or receipt.get("output_digest") != observation.get("output_digest")
                or (observation.get("schema_version") in {
                        COGNITION_OBSERVATION_SCHEMA_V5, COGNITION_OBSERVATION_SCHEMA_V6,
                        COGNITION_OBSERVATION_SCHEMA_V7}
                    and receipt.get("observed_at") != observation.get("observed_at"))
                or not isinstance(serving, Mapping) or dict(serving) != expected_serving):
            raise ResidentDevelopmentalCognitionError("cognition_invocation_receipt_binding_mismatch")
        if observation.get("schema_version") == COGNITION_OBSERVATION_SCHEMA_V7:
            observed_consumption = observation.get("resource_consumption_receipt_digests", ())
            receipt_consumption = receipt.get("resource_consumption_receipt_digests", ())
            if (observation.get("resource_allocation_digest")
                    != receipt.get("resource_allocation_digest")
                    or observation.get("resource_attempt_id") != receipt.get("resource_attempt_id")
                    or tuple(observed_consumption or ()) != tuple(receipt_consumption or ())
                    or observation.get("resource_linkage_digest")
                        != receipt.get("resource_linkage_digest")):
                raise ResidentDevelopmentalCognitionError(
                    "cognition_resource_linkage_invocation_mismatch")
        if observation.get("schema_version") in {
                COGNITION_OBSERVATION_SCHEMA_V6, COGNITION_OBSERVATION_SCHEMA_V7}:
            upstream = request.get("upstream_evidence") if isinstance(request, Mapping) else None
            if (not isinstance(upstream, Mapping)
                    or upstream.get("developmental_history_selection")
                        != observation.get("developmental_history_selection")
                    or upstream.get("record_ids") != list(observation.get("retrieved_record_ids", ()))
                    or upstream.get("record_digests")
                        != list(observation.get("retrieved_record_digests", ()))):
                raise ResidentDevelopmentalCognitionError(
                    "cognition_history_selection_invocation_binding_mismatch")
        return cast(Mapping[str, Any], receipt)

    def _recover_observation_ticks(self, *, include_records: bool = False) -> Any:
        try:
            self.observations_root.lstat()
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise ResidentDevelopmentalCognitionError("cognition_observation_root_invalid") from exc
        entries: list[tuple[str, bytes]] = []
        if os.name == "nt":
            try:
                entries = read_regular_files(self.observations_root,
                    max_entries=MAX_COGNITION_OBSERVATIONS,
                    max_file_bytes=MAX_COGNITION_OBSERVATION_BYTES,
                    max_total_bytes=MAX_COGNITION_OBSERVATION_ROOT_BYTES)
            except WindowsHandleCustodyError as exc:
                raise ResidentDevelopmentalCognitionError("cognition_observation_windows_recovery_failed") from exc
            total_bytes = sum(len(raw) for _name, raw in entries)
            if total_bytes > MAX_COGNITION_OBSERVATION_ROOT_BYTES:
                raise ResidentDevelopmentalCognitionError("cognition_observation_retention_limit_exceeded")
        else:
            try:
                root_fd = _open_store_directory(self.observations_root, create=False)
            except DevelopmentalWritebackError as exc:
                if str(exc) == "durable_store_root_missing":
                    return {}
                raise ResidentDevelopmentalCognitionError("cognition_observation_root_invalid") from exc
            total_bytes = 0
            try:
                root_stat = os.fstat(root_fd)
                if (not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != os.geteuid()
                        or root_stat.st_mode & 0o022):
                    raise ResidentDevelopmentalCognitionError("cognition_observation_root_invalid")
                names = sorted(name for name in os.listdir(root_fd) if name.endswith(".json"))
                if len(names) > MAX_COGNITION_OBSERVATIONS:
                    raise ResidentDevelopmentalCognitionError("cognition_observation_retention_limit_exceeded")
                for name in names:
                    if not name or name in {".", ".."} or "/" in name or "\\" in name:
                        raise ResidentDevelopmentalCognitionError("cognition_observation_not_regular")
                    descriptor: int | None = None
                    try:
                        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                                             dir_fd=root_fd)
                        opened = os.fstat(descriptor)
                        if (not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_COGNITION_OBSERVATION_BYTES
                                or opened.st_nlink != 1 or opened.st_uid != os.geteuid()
                                or opened.st_mode & 0o077):
                            raise ResidentDevelopmentalCognitionError("cognition_observation_not_regular")
                        chunks: list[bytes] = []
                        remaining = MAX_COGNITION_OBSERVATION_BYTES + 1
                        while remaining:
                            chunk = os.read(descriptor, min(65_536, remaining))
                            if not chunk:
                                break
                            chunks.append(chunk)
                            remaining -= len(chunk)
                        raw = b"".join(chunks)
                        after = os.fstat(descriptor)
                        if (len(raw) > MAX_COGNITION_OBSERVATION_BYTES or len(raw) != opened.st_size
                                or after.st_size != opened.st_size or after.st_mtime_ns != opened.st_mtime_ns
                                or after.st_dev != opened.st_dev or after.st_ino != opened.st_ino):
                            raise ResidentDevelopmentalCognitionError("cognition_observation_corrupt")
                        total_bytes += len(raw)
                        if total_bytes > MAX_COGNITION_OBSERVATION_ROOT_BYTES:
                            raise ResidentDevelopmentalCognitionError("cognition_observation_retention_limit_exceeded")
                        entries.append((name, raw))
                    except ResidentDevelopmentalCognitionError:
                        raise
                    except OSError as exc:
                        raise ResidentDevelopmentalCognitionError("cognition_observation_corrupt") from exc
                    finally:
                        if descriptor is not None:
                            os.close(descriptor)
            finally:
                os.close(root_fd)
        by_tick: dict[str, list[str]] = {}
        verified_records: dict[str, dict[str, Any]] = {}
        contexts_by_tick: dict[str, tuple[set[str], tuple[Any | None, Any | None]]] = {}
        for name, raw in entries:
            try:
                value = json.loads(raw.decode("utf-8"))
                if (not isinstance(value, dict)
                        or json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n" != raw):
                    raise ResidentDevelopmentalCognitionError("cognition_observation_noncanonical")
                observation_id = value.pop("observation_id")
                observation_digest = value.pop("observation_digest")
            except (UnicodeError, json.JSONDecodeError, KeyError, AttributeError, TypeError) as exc:
                raise ResidentDevelopmentalCognitionError("cognition_observation_corrupt") from exc
            expected_fields = set(ResidentCognitionObservation.__dataclass_fields__) - {
                "observation_id", "observation_digest"}
            resource_linkage_fields = {"resource_allocation_digest", "resource_attempt_id",
                "resource_consumption_receipt_digests", "resource_linkage_digest"}
            semantic_fields = {"epistemic_projection_schema", "epistemic_semantic_status",
                "epistemic_owner_packet_count", "epistemic_consumed_packet_ids",
                "epistemic_consumed_packet_digests", "epistemic_omitted_packets",
                "epistemic_omitted_packets_digest",
                "epistemic_consumed_packets_digest", "epistemic_projection_context_digest",
                "epistemic_prompt_digest", "epistemic_consumed_content_digest", "schema_version"}
            history_selection_fields = {"developmental_history_selection"}
            session_fields = {"serving_session_id", "serving_session_binding"}
            session_receipt_fields = {"serving_session_receipt_id", "serving_session_receipt_digest"}
            legacy_fields = expected_fields - history_selection_fields - semantic_fields - session_fields - session_receipt_fields - resource_linkage_fields - {"observed_at"}
            v2_fields = expected_fields - history_selection_fields - session_fields - session_receipt_fields - resource_linkage_fields - {"observed_at"}
            v3_fields = expected_fields - history_selection_fields - session_receipt_fields - resource_linkage_fields - {"observed_at"}
            v4_fields = expected_fields - history_selection_fields - resource_linkage_fields - {"observed_at"}
            v5_fields = expected_fields - history_selection_fields - resource_linkage_fields
            v6_fields = expected_fields - resource_linkage_fields
            legacy_observation = isinstance(value, dict) and set(value) == legacy_fields
            versioned_v2_observation = (isinstance(value, dict) and set(value) == v2_fields
                and value.get("schema_version") == COGNITION_OBSERVATION_SCHEMA_V2)
            versioned_v3_observation = (isinstance(value, dict) and set(value) == v3_fields
                and value.get("schema_version") == COGNITION_OBSERVATION_SCHEMA_V3)
            versioned_v4_observation = (isinstance(value, dict) and set(value) == v4_fields
                and value.get("schema_version") == COGNITION_OBSERVATION_SCHEMA_V4)
            versioned_v5_observation = (isinstance(value, dict) and set(value) == v5_fields
                and value.get("schema_version") == COGNITION_OBSERVATION_SCHEMA_V5)
            versioned_v6_observation = (isinstance(value, dict) and set(value) == v6_fields
                and value.get("schema_version") == COGNITION_OBSERVATION_SCHEMA_V6)
            versioned_v7_observation = (isinstance(value, dict) and set(value) == expected_fields
                and value.get("schema_version") == COGNITION_OBSERVATION_SCHEMA_V7)
            versioned_observation = (versioned_v2_observation or versioned_v3_observation
                or versioned_v4_observation or versioned_v5_observation
                or versioned_v6_observation or versioned_v7_observation)
            if (not (legacy_observation or versioned_observation)
                    or not isinstance(value.get("tick_id"), str) or not value["tick_id"]
                    or observation_digest != _digest(value)
                    or observation_id != "devcog-" + observation_digest[7:31]
                    or name != observation_id + ".json"):
                raise ResidentDevelopmentalCognitionError("cognition_observation_digest_mismatch")
            if versioned_observation:
                _validate_epistemic_observation_binding(value)
            if versioned_v6_observation or versioned_v7_observation:
                _validate_developmental_history_selection(value)
            if versioned_v7_observation:
                _validate_observation_resource_linkage(value)
            if versioned_v3_observation or versioned_v4_observation or versioned_v5_observation or versioned_v6_observation or versioned_v7_observation:
                session_id, session_binding = value.get("serving_session_id"), value.get("serving_session_binding")
                absent = session_id is None and session_binding is None
                activation_digest = (session_binding.get("activation_state_semantic_digest")
                    if isinstance(session_binding, Mapping) else None)
                activation_digest_raw = (isinstance(activation_digest, str) and len(activation_digest) == 64
                    and all(ch in "0123456789abcdef" for ch in activation_digest))
                activation_digest_legacy = (isinstance(activation_digest, str) and len(activation_digest) == 71
                    and activation_digest.startswith("sha256:")
                    and all(ch in "0123456789abcdef" for ch in activation_digest[7:]))
                present = (isinstance(session_id, str) and 0 < len(session_id) <= 256
                    and isinstance(session_binding, Mapping)
                    and set(session_binding) == {"model_serving_admission_ref", "activation_state_semantic_digest"}
                    and isinstance(session_binding.get("model_serving_admission_ref"), str)
                    and bool(session_binding["model_serving_admission_ref"])
                    and (activation_digest_raw or (versioned_v3_observation and activation_digest_legacy)))
                if not (absent or present):
                    raise ResidentDevelopmentalCognitionError("cognition_observation_serving_session_binding_invalid")
                if versioned_v4_observation or versioned_v5_observation or versioned_v6_observation or versioned_v7_observation:
                    receipt_id, receipt_digest = (value.get("serving_session_receipt_id"),
                        value.get("serving_session_receipt_digest"))
                    receipt_absent = absent and receipt_id is None and receipt_digest is None
                    receipt_present = (present and isinstance(receipt_id, str)
                        and receipt_id.startswith("resident-serving-receipt-")
                        and len(receipt_id) == len("resident-serving-receipt-") + 24
                        and isinstance(receipt_digest, str) and len(receipt_digest) == 64
                        and all(ch in "0123456789abcdef" for ch in receipt_digest))
                    if not (receipt_absent or receipt_present):
                        raise ResidentDevelopmentalCognitionError("cognition_observation_serving_receipt_binding_invalid")
            tick = value["tick_id"]
            condition = value.get("condition_id")
            snapshot_binding = (value.get("current_snapshot_id"), value.get("current_snapshot_digest"))
            allowed_conditions = {"prior-context", "with-history", "history_present",
                "history_withheld", "history_restored"}
            if (not isinstance(condition, str) or condition not in allowed_conditions
                    or value.get("correlation_id") !=
                        f"{tick}:resident_developmental_cognition:{condition}"
                    or type(value.get("prior_tick_proven")) is not bool
                    or type(value.get("self_model_projection_present")) is not bool
                    or not all(isinstance(item, str) and item for item in snapshot_binding)
                    or (value.get("prior_tick_proven") is True and (
                        value.get("self_model_projection_present") is not True
                        or not isinstance(value.get("self_model_source_tick"), str)
                        or value.get("self_model_source_tick") == tick))
                    or (value.get("self_model_projection_present") is True
                        and value.get("prior_tick_proven") is not True)):
                raise ResidentDevelopmentalCognitionError("cognition_observation_lineage_invalid")
            prior_context = contexts_by_tick.get(tick)
            if prior_context is None:
                contexts_by_tick[tick] = ({str(condition)}, snapshot_binding)
            else:
                conditions, prior_snapshot = prior_context
                if condition in conditions or snapshot_binding != prior_snapshot:
                    raise ResidentDevelopmentalCognitionError("cognition_observation_tick_conflict")
                conditions.add(str(condition))
            by_tick.setdefault(value["tick_id"], []).append(observation_id)
            verified_observation = {
                **value, "observation_id": observation_id,
                "observation_digest": observation_digest}
            if versioned_v3_observation or versioned_v5_observation or versioned_v6_observation or versioned_v7_observation:
                self._verify_observation_invocation(verified_observation)
            verified_records[observation_id] = verified_observation
        if include_records:
            return verified_records
        return {tick: tuple(sorted(ids)) for tick, ids in by_tick.items()}

    def verified_cognition_observation(self, observation_id: str,
                                       observation_digest: str | None = None) -> Mapping[str, Any]:
        """Re-read one bounded, canonical cognition observation from configured custody."""
        if (not isinstance(observation_id, str) or not observation_id.startswith("devcog-")
                or (observation_digest is not None and (not isinstance(observation_digest, str) or not observation_digest.startswith("sha256:")))):
            raise ResidentDevelopmentalCognitionError("cognition_observation_identity_invalid")
        records = self._recover_observation_ticks(include_records=True)
        observation = records.get(observation_id)
        if (not isinstance(observation, Mapping)
                or (observation_digest is not None and observation.get("observation_digest") != observation_digest)):
            raise ResidentDevelopmentalCognitionError("cognition_observation_not_verified")
        return dict(observation)

    def verified_epistemic_revision_probe_capture(
            self, observation_id: str) -> VerifiedEpistemicRevisionProbeCapture:
        """Reopen one raw probe capture and bind it to its verified observation and receipt.

        This is read-only. It does not load or invoke a model, and does not accept a
        caller-supplied prompt, receipt, output, or answer key.
        """
        if (not isinstance(observation_id, str) or not observation_id.startswith("devcog-")
                or len(observation_id) != len("devcog-") + 24
                or any(char not in "0123456789abcdef" for char in observation_id[7:])):
            raise ResidentDevelopmentalCognitionError(
                "epistemic_revision_probe_capture_identity_invalid")
        filename = observation_id + ".json"
        try:
            if os.name == "nt":
                entries = read_regular_files(self.epistemic_revision_probe_captures_root,
                    max_entries=1, max_file_bytes=MAX_COMPOSITION_STATE_BYTES,
                    max_total_bytes=MAX_COMPOSITION_STATE_BYTES,
                    selected_names=(filename,))
                if len(entries) != 1 or entries[0][0] != filename:
                    raise ResidentDevelopmentalCognitionError(
                        "epistemic_revision_probe_capture_unavailable")
                raw = entries[0][1]
            else:
                root_fd = _open_store_directory(
                    self.epistemic_revision_probe_captures_root, create=False)
                try:
                    raw = read_private_file_at(root_fd, filename,
                        max_bytes=MAX_COMPOSITION_STATE_BYTES)
                finally:
                    os.close(root_fd)
        except ResidentDevelopmentalCognitionError:
            raise
        except (OSError, DevelopmentalWritebackError, PrivateFileCustodyError,
                WindowsHandleCustodyError) as exc:
            raise ResidentDevelopmentalCognitionError(
                "epistemic_revision_probe_capture_unavailable") from exc
        try:
            capture = json.loads(raw.decode("utf-8"))
            if (not isinstance(capture, dict)
                    or json.dumps(capture, indent=2, sort_keys=True).encode("utf-8") + b"\n" != raw
                    or set(capture) != {"schema_version", "observation_id",
                        "observation_digest", "prompt", "request", "receipt",
                        "answer_key_included", "capture_digest"}):
                raise ValueError("capture_shape")
            semantic = dict(capture)
            capture_digest = semantic.pop("capture_digest")
            if (capture.get("schema_version") !=
                    "sentientos.epistemic_revision_probe_capture:v1"
                    or capture.get("observation_id") != observation_id
                    or capture.get("answer_key_included") is not False
                    or not isinstance(capture_digest, str)
                    or capture_digest != _digest(semantic)
                    or not isinstance(capture.get("prompt"), str)
                    or not isinstance(capture.get("request"), Mapping)
                    or not isinstance(capture.get("receipt"), Mapping)):
                raise ValueError("capture_binding")
            receipt_payload = dict(capture["receipt"])
            valid, reasons = validate_receipt(receipt_payload)
            if not valid or "output_text" not in receipt_payload:
                raise ValueError("receipt_invalid:" + ",".join(reasons))
            receipt = LocalModelInvocationReceipt(
                request=receipt_payload["request"], status=receipt_payload["status"],
                reason_codes=tuple(receipt_payload["reason_codes"]),
                output_text=receipt_payload.get("output_text"),
                output_digest=receipt_payload["output_digest"],
                output_size_bytes=receipt_payload["output_size_bytes"],
                generation_config=receipt_payload["generation_config"],
                admission_decision_ref=receipt_payload["admission_decision_ref"],
                purpose=receipt_payload["purpose"],
                latency_ms=receipt_payload.get("latency_ms", 0),
                output_truncated=receipt_payload["output_truncated"],
                fallback_occurred=receipt_payload["fallback_occurred"],
                effects=receipt_payload["effects"],
                observed_at=receipt_payload["observed_at"],
                resource_allocation_digest=receipt_payload.get("resource_allocation_digest"),
                resource_attempt_id=receipt_payload.get("resource_attempt_id"),
                resource_consumption_receipt_digests=tuple(
                    receipt_payload.get("resource_consumption_receipt_digests", ())),
                resource_linkage_digest=receipt_payload.get("resource_linkage_digest"),
                schema_version=receipt_payload["schema_version"],
                backend_completion=receipt_payload.get("backend_completion"))
            if (receipt.purpose != "resident_developmental_retrieval_cognition"
                    or receipt.request.get("expected_output_format") != "json"
                    or receipt.request.get("structured_output_schema")
                        != RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA
                    or capture["request"] != dict(receipt.request)):
                raise ValueError("probe_request_mismatch")
            observation = self.verified_cognition_observation(observation_id,
                str(capture["observation_digest"]))
            persisted_receipt = self._verify_observation_invocation(observation)
            if (persisted_receipt is None
                    or persisted_receipt.get("receipt_id") != receipt.receipt_id
                    or persisted_receipt.get("receipt_digest") != receipt.receipt_digest
                    or persisted_receipt.get("request") != dict(receipt.request)
                    or persisted_receipt.get("status") != receipt.status
                    or persisted_receipt.get("output_digest") != receipt.output_digest
                    or persisted_receipt.get("output_size_bytes") != receipt.output_size_bytes
                    or persisted_receipt.get("output_truncated") != receipt.output_truncated
                    or persisted_receipt.get("generation_config")
                        != dict(receipt.generation_config)
                    or persisted_receipt.get("observed_at") != receipt.observed_at
                    or observation.get("epistemic_prompt_digest")
                        != "sha256:" + receipt.request.get("prompt_digest", "")
                    or receipt.request.get("prompt_digest")
                        != digest_payload({"prompt": capture["prompt"]})
                    or observation.get("inference_receipt_id") != receipt.receipt_id
                    or observation.get("inference_receipt_digest") != receipt.receipt_digest
                    or observation.get("output_digest") != receipt.output_digest):
                raise ValueError("capture_observation_receipt_mismatch")
            return VerifiedEpistemicRevisionProbeCapture(
                observation_id=observation_id,
                observation_digest=str(capture["observation_digest"]),
                capture_digest=capture_digest,
                prompt=capture["prompt"], request=dict(receipt.request), receipt=receipt)
        except ResidentDevelopmentalCognitionError:
            raise
        except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise ResidentDevelopmentalCognitionError(
                "epistemic_revision_probe_capture_invalid") from exc

    def verify_transition_observation(self, *, stage: str, evidence: Mapping[str, Any],
                                     expected_model_identity: Mapping[str, Any],
                                     expected_serving_session: Mapping[str, Any],
                                     expected_serving_session_receipt: Mapping[str, Any],
                                     b_epoch_evidence: Mapping[str, Any] | None = None) -> None:
        """Qualify A/B transition observations against durable history and invocation owners."""
        if stage not in {"b_epoch_observed", "post_restoration_observed"}:
            raise ResidentDevelopmentalCognitionError("transition_observation_stage_invalid")
        allowed_fields = ({"b_tick_id", "b_observation_id", "b_observation_digest",
            "b_record_id", "b_record_digest", "b_writeback_receipt_id",
            "b_writeback_receipt_digest", "operator_request"} if stage == "b_epoch_observed" else
            {"restored_a_tick_id", "restored_a_observation_id", "restored_a_observation_digest",
            "restored_a_inference_receipt_id", "restored_a_inference_receipt_digest",
            "retrieved_record_ids", "retrieved_record_digests", "operator_request"})
        if not isinstance(evidence, Mapping) or set(evidence) - allowed_fields:
            raise ResidentDevelopmentalCognitionError("transition_observation_evidence_shape_invalid")
        if not isinstance(expected_serving_session, Mapping):
            raise ResidentDevelopmentalCognitionError("transition_serving_session_missing")
        session_binding = expected_serving_session.get("binding")
        session_id = expected_serving_session.get("session_id")
        if (not isinstance(session_binding, Mapping) or not isinstance(session_id, str)
                or not session_id
                or not isinstance(session_binding.get("model_serving_admission_ref"), str)
                or not session_binding.get("model_serving_admission_ref")
                or not isinstance(session_binding.get("activation_state_semantic_digest"), str)
                or not session_binding.get("activation_state_semantic_digest")):
            raise ResidentDevelopmentalCognitionError("transition_serving_session_invalid")
        # Cognition observations intentionally retain the two stable session
        # binding fields, not the full serving receipt. Compare that exact
        # projection while the separately verified session receipt below binds
        # the complete serving record.
        observation_session_binding = {
            "model_serving_admission_ref": session_binding["model_serving_admission_ref"],
            "activation_state_semantic_digest": session_binding["activation_state_semantic_digest"],
        }
        if (not isinstance(expected_serving_session_receipt, Mapping)
                or set(expected_serving_session_receipt) != {"receipt_id", "receipt_semantic_digest"}
                or any(not isinstance(expected_serving_session_receipt.get(key), str)
                    or not expected_serving_session_receipt.get(key)
                    for key in ("receipt_id", "receipt_semantic_digest"))):
            raise ResidentDevelopmentalCognitionError("transition_serving_receipt_invalid")
        observation_id = evidence.get("b_observation_id") if stage == "b_epoch_observed" else evidence.get("restored_a_observation_id")
        observation_digest = evidence.get("b_observation_digest") if stage == "b_epoch_observed" else evidence.get("restored_a_observation_digest")
        observation = self.verified_cognition_observation(str(observation_id or ""), str(observation_digest or ""))
        tick_id = evidence.get("b_tick_id") if stage == "b_epoch_observed" else evidence.get("restored_a_tick_id")
        if (not isinstance(tick_id, str) or not tick_id or observation.get("tick_id") != tick_id
                or observation.get("active_model_identity") != dict(expected_model_identity)
                or observation.get("serving_session_id") != session_id
                or observation.get("serving_session_binding") != observation_session_binding
                or observation.get("serving_session_receipt_id")
                    != expected_serving_session_receipt.get("receipt_id")
                or observation.get("serving_session_receipt_digest")
                    != expected_serving_session_receipt.get("receipt_semantic_digest")):
            raise ResidentDevelopmentalCognitionError("transition_observation_model_or_tick_mismatch")
        verify_invocation = getattr(self.invoker, "verify_persisted_invocation_receipt", None)
        if not callable(verify_invocation):
            raise ResidentDevelopmentalCognitionError("transition_invocation_receipt_verifier_unavailable")

        def verify_observation_invocation() -> Mapping[str, Any]:
            receipt = verify_invocation(
                str(observation.get("inference_receipt_id", "")),
                str(observation.get("inference_receipt_digest", "")),
                expected_request_id=str(observation.get("request_id", "")),
                expected_request_digest=str(observation.get("request_digest", "")),
                expected_session_id=session_id,
                expected_session_binding=observation_session_binding,
                expected_active_model_identity=expected_model_identity,
                **({"expected_session_receipt_id": observation["serving_session_receipt_id"],
                    "expected_session_receipt_digest": observation["serving_session_receipt_digest"]}
                    if observation.get("serving_session_receipt_id") is not None else {}))
            if not isinstance(receipt, Mapping):
                raise ResidentDevelopmentalCognitionError("transition_invocation_receipt_invalid")
            request = receipt.get("request")
            if (not isinstance(request, Mapping)
                    or receipt.get("status") not in {"admitted_completed", "admitted_simulation"}
                    or not isinstance(receipt.get("output_digest"), str)
                    or request.get("model_id") != observation.get("model_id")
                    or request.get("model_artifact_digest") != observation.get("model_artifact_digest")
                    or receipt.get("output_digest") != observation.get("output_digest")):
                raise ResidentDevelopmentalCognitionError("transition_observation_invocation_model_mismatch")
            return receipt

        observed_invocation = verify_observation_invocation()
        if (stage == "post_restoration_observed"
                and (evidence.get("restored_a_inference_receipt_id") != observed_invocation.get("receipt_id")
                     or evidence.get("restored_a_inference_receipt_digest") != observed_invocation.get("receipt_digest"))):
            raise ResidentDevelopmentalCognitionError("transition_restoration_invocation_binding_mismatch")
        if stage == "b_epoch_observed":
            record_id = evidence.get("b_record_id")
            record_digest = evidence.get("b_record_digest")
            receipt_id = evidence.get("b_writeback_receipt_id")
            receipt_digest = evidence.get("b_writeback_receipt_digest")
            try:
                record = self.writeback.store.get(str(record_id))
                receipt = self.writeback.store.get_receipt(str(receipt_id))
            except Exception as exc:
                raise ResidentDevelopmentalCognitionError("transition_b_epoch_writeback_missing_or_invalid") from exc
            candidate = record.candidate
            if (record.record_digest != record_digest
                    or receipt.receipt_digest != receipt_digest
                    or receipt.record_id != record.record_id
                    or receipt.record_digest != record.record_digest
                    or receipt.candidate_id != candidate.get("candidate_id")
                    or receipt.candidate_digest != candidate.get("candidate_digest")
                    or receipt.storage_verified is not True
                    or record.correlation_id != tick_id + ":resident-developmental-writeback"
                    or record.operation_id != "resident-developmental-writeback:" + tick_id + ":" + str(candidate.get("candidate_id"))
                    or candidate.get("snapshot_id") != observation.get("current_snapshot_id")
                    or candidate.get("snapshot_digest") != observation.get("current_snapshot_digest")):
                raise ResidentDevelopmentalCognitionError("transition_b_epoch_writeback_lineage_mismatch")
            candidate_receipt = verify_invocation(
                str(candidate.get("inference_receipt_id", "")),
                str(candidate.get("inference_receipt_digest", "")),
                expected_request_id=str(candidate.get("request_id", "")),
                expected_request_digest=str(candidate.get("request_digest", "")),
                expected_session_id=session_id,
                expected_session_binding=observation_session_binding,
                expected_active_model_identity=expected_model_identity,
                expected_session_receipt_id=expected_serving_session_receipt["receipt_id"],
                expected_session_receipt_digest=expected_serving_session_receipt["receipt_semantic_digest"])
            candidate_request = candidate_receipt.get("request")
            if (not isinstance(candidate_request, Mapping)
                    or candidate_receipt.get("status") not in {"admitted_completed", "admitted_simulation"}
                    or candidate_request.get("purpose") != "resident_developmental_interpretation"
                    or candidate_request.get("correlation_id") != tick_id + ":resident_developmental_interpretation"
                    or candidate.get("model_id") != candidate_request.get("model_id")
                    or candidate.get("model_artifact_digest") != candidate_request.get("model_artifact_digest")
                    or candidate_receipt.get("output_digest") != candidate.get("output_digest")):
                raise ResidentDevelopmentalCognitionError("transition_b_epoch_candidate_invocation_mismatch")
            return
        if not isinstance(b_epoch_evidence, Mapping):
            raise ResidentDevelopmentalCognitionError("transition_b_epoch_evidence_missing")
        b_record_id = b_epoch_evidence.get("b_record_id")
        b_record_digest = b_epoch_evidence.get("b_record_digest")
        retrieved_ids = evidence.get("retrieved_record_ids")
        retrieved_digests = evidence.get("retrieved_record_digests")
        if (not isinstance(retrieved_ids, (list, tuple))
                or not isinstance(retrieved_digests, (list, tuple))
                or len(retrieved_ids) != len(retrieved_digests)
                or list(retrieved_ids) != list(observation.get("retrieved_record_ids", ()))
                or list(retrieved_digests) != list(observation.get("retrieved_record_digests", ()))
                or len(retrieved_ids) > MAX_HISTORY
                or len(set(retrieved_ids)) != len(retrieved_ids)
                or not all(isinstance(item, str) and item.startswith("sha256:") for item in retrieved_digests)
                or not any(record_id == b_record_id and record_digest == b_record_digest
                           for record_id, record_digest in zip(retrieved_ids, retrieved_digests))):
            raise ResidentDevelopmentalCognitionError("transition_restoration_history_binding_mismatch")
        for record_id, expected_digest in zip(retrieved_ids, retrieved_digests):
            try:
                record = self.writeback.store.get(str(record_id))
            except Exception as exc:
                raise ResidentDevelopmentalCognitionError("transition_retrieved_history_not_durable") from exc
            if record.record_digest != expected_digest:
                raise ResidentDevelopmentalCognitionError("transition_retrieved_history_digest_mismatch")

    def _save_state(self, state: Mapping[str, Any]) -> None:
        if os.name != "posix":
            raise ResidentDevelopmentalCognitionError("composition_state_publication_unsupported_platform")
        semantic = {k: v for k, v in state.items() if k != "state_digest"}
        if (len(semantic.get("processed_selection_ids", ())) > MAX_RECOVERED_FACT_IDS
                or len(semantic.get("completed_ticks", ())) + len(semantic.get("incomplete_ticks", ())) > MAX_RECOVERED_TICKS):
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
        if len(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode("utf-8")) > MAX_COMPOSITION_STATE_BYTES:
            raise ResidentDevelopmentalCognitionError("composition_state_unbounded")
        _replace_cognition_state(self.state_path, {**semantic, "state_digest": _digest(semantic)})

    def _prior_projection(self, state: Mapping[str, Any], tick_id: str, *,
            task_family_id: str | None = None,
            task_probe_inputs: tuple[int, ...] = ()) -> DevelopmentalHistoryProjection:
        # Tick identifiers are opaque at this owner boundary. The durable,
        # digest-verified completed-checkpoint sequence establishes which
        # developmental records were committed before this cycle; wall-clock
        # parsing is neither required nor a reliable substitute for that order.
        # The current tick is separately guarded against replay and has not
        # reached completed_ticks while this projection is captured.
        ids = [str(completed["record_id"]) for completed in state["completed_ticks"]
               if completed.get("tick_id") != tick_id and completed.get("record_id")]
        # Older admitted records remain durably verifiable, but a legacy
        # low-entropy oracle hash must not return through retained cognition.
        safe_ids: list[str] = []
        for record_id in ids:
            try:
                stored = self.writeback.store.get(record_id)
            except Exception as exc:
                raise ResidentDevelopmentalCognitionError(
                    "developmental_history_recovery_failed") from exc
            candidate = stored.candidate
            facts = candidate.get("selected_facts", ()) if isinstance(candidate, Mapping) else ()
            if not any(_unsafe_legacy_objective_cognition_fact(fact) for fact in facts):
                safe_ids.append(record_id)
        ids = safe_ids
        family = task_family_id or (self.objective_task.public_descriptor().get("task_family_id")
            if self.objective_task is not None else None)
        if isinstance(family, str):
            # The completed-tick checkpoint bounds this search to
            # MAX_RECOVERED_TICKS. Search newest-first across that complete
            # retained lineage so a valid older family example is not hidden
            # by unrelated recent history. Keep only the newest matching
            # records, then fill spare slots by recency. Family labels are
            # protocol-bound relevance metadata, not proof of correctness or
            # learning; the selected records retain their source qualifiers.
            relevant_newest_first: list[str] = []
            probe_set = set(task_probe_inputs)
            relevance: dict[str, int] = {}
            for record_id in reversed(ids):
                try:
                    record = self.writeback.store.get(record_id)
                except Exception as exc:
                    raise ResidentDevelopmentalCognitionError(
                        "task_relevant_history_recovery_failed") from exc
                candidate = record.candidate
                facts = candidate.get("selected_facts", ()) if isinstance(candidate, Mapping) else ()
                matching_facts = [fact for fact in facts if isinstance(fact, Mapping)
                        and isinstance(fact.get("payload"), Mapping)
                        and fact["payload"].get("objective_task_family") == family]
                if matching_facts:
                    relevant_newest_first.append(record_id)
                    overlap: set[int] = set()
                    for fact in matching_facts:
                        examples = fact["payload"].get("acquisition_examples", ())
                        if isinstance(examples, (list, tuple)):
                            for item in examples:
                                if isinstance(item, Mapping):
                                    probe_input = item.get("probe_input")
                                    if type(probe_input) is int and probe_input in probe_set:
                                        overlap.add(probe_input)
                    relevance[record_id] = len(overlap)
            # Exact public probe overlap ranks records; checkpoint order breaks ties.
            # Evaluator correctness is not a filter, so adverse examples survive.
            relevant_newest_first.sort(key=lambda record_id: (
                relevance[record_id], ids.index(record_id)), reverse=True)
            selected = list(relevant_newest_first[:self.config.max_retrieved_records])
            selected_set = set(selected)
            for record_id in reversed(ids):
                if len(selected) >= self.config.max_retrieved_records:
                    break
                if record_id not in selected_set:
                    selected.append(record_id)
                    selected_set.add(record_id)
            if probe_set:
                # The prompt binder admits a complete suffix as capacity shrinks.
                # Order the selected set from least to most relevant so that
                # every smaller suffix keeps the best probe-overlap records;
                # checkpoint order remains the stable tie-breaker.
                ids = sorted((record_id for record_id in ids
                    if record_id in selected_set), key=lambda record_id: (
                        relevance.get(record_id, -1), ids.index(record_id)))
            else:
                # Keep the established family-only order for legacy callers.
                ids = list(reversed(selected))
        ids = ids[-self.config.max_retrieved_records:]
        return self.writeback.retrieve(ids, limit=self.config.max_retrieved_records)

    def _select_fact_ids(self, snapshot: WorldStateSnapshot, processed: set[str]) -> tuple[str, ...]:
        allowed = set(self.config.allowed_source_kinds)
        source_kinds = {source.source_id: source.kind for source in snapshot.sources}
        candidates = sorted(
            (fact for fact in snapshot.facts
                if source_kinds.get(fact.source.source_id) in allowed
                and not _unsafe_legacy_objective_cognition_fact(fact.payload)),
            key=lambda fact: self._fact_selection_key(fact, source_kinds[fact.source.source_id]),
        )
        selected: list[str] = []
        for fact in candidates:
            trial = self.writeback.select_evidence(snapshot, fact_ids=(fact.fact_id,))
            # Fact IDs remain stable when the same immutable source is observed
            # in a later snapshot. Selection IDs include snapshot identity and
            # are accepted only for compatibility with pre-recovery state files.
            if fact.fact_id not in processed and trial.selection_id not in processed:
                selected.append(fact.fact_id)
            if len(selected) == self.config.max_selected_facts:
                break
        return tuple(selected)

    @staticmethod
    def _fact_selection_key(fact: Any, source_kind: str) -> tuple[Any, ...]:
        """Keep current identities and qualified causal evidence ahead of journal volume."""
        subject_kind = str(fact.subject.subject_kind)
        payload = fact.payload
        quarantine_result = payload.get("custody_result")
        quarantine_custody_observation = (
            source_kind == "quarantine"
            and subject_kind == "quarantine_custody_observation"
            and fact.stage == "observation"
            and payload.get("observation_schema")
                == "sentientos.integrity_quarantine_custody_observation:v1"
            and payload.get("source_owner")
                == "sentientos.integrity_quarantine.load_state_with_status"
            and quarantine_result in {"first_use_absent", "valid_v1", "invalid", "observer_unavailable"}
            and payload.get("event_time_posture")
                == "daemon_tick_point_observation_of_owner_read"
            and payload.get("independent_signature") is False
            and isinstance(payload.get("event_meaning"), str)
            and bool(payload.get("event_meaning"))
            and payload.get("attack_established") is False
            and payload.get("hostile_activity_established") is False
            and payload.get("effect_proven") is False
            and payload.get("effect_authority") is False
            and payload.get("authority") is False
            and payload.get("current_truth") is False
            and payload.get("read_only") is True
            and ((fact.disposition == "custody_invalid"
                    and fact.evidence_strength == "owner_validated_custody_failure"
                    and quarantine_result == "invalid")
                or (fact.disposition == "recorded"
                    and fact.evidence_strength == "owner_validated_custody_observation"
                    and quarantine_result in {"first_use_absent", "valid_v1"})
                or (fact.disposition == "observer_unavailable"
                    and fact.evidence_strength == "owner_observation_unavailable"
                    and quarantine_result == "observer_unavailable"))
            and type(payload.get("quarantine_active")) in {bool, type(None)}
            and fact.effect_claimed is False and fact.effect_proven is False
        )
        quarantine_incident_custody_observation = (
            source_kind == "quarantine"
            and fact.source.source_id == "integrity-quarantine-incident-custody:resident-daemon"
            and subject_kind == "quarantine_incident_custody_observation"
            and fact.stage == "observation"
            and fact.disposition in {"recorded", "degraded"}
            and fact.evidence_strength == "owner_observed_local_incident_custody_reconciliation"
            and payload.get("observation_schema")
                == "sentientos.integrity_quarantine_incident_custody_observation:v1"
            and payload.get("source_owner")
                == "sentientos.integrity_incident.inspect_quarantine_incident_custody"
            and payload.get("reconciliation_status") in {
                "complete_local_custody", "incomplete", "conflict",
                "incomplete_identity", "observer_unavailable"}
            and payload.get("event_time_posture")
                == "historical_activation_reference_reconciled_at_observation"
            and payload.get("feed_is_authenticated") is False
            and payload.get("attack_established") is False
            and payload.get("hostile_activity_established") is False
            and payload.get("defensive_consequence_established") is False
            and payload.get("cause_unknown") is True
            and payload.get("authority") is False
            and payload.get("current_truth") is False
            and payload.get("effect_proven") is False
            and payload.get("effect_authority") is False
            and payload.get("read_only") is True
            and payload.get("artifact_status") in {"valid", "missing", "invalid", "conflict", "not_checked"}
            and payload.get("feed_status") in {"present_unverified", "missing", "invalid", "conflict", "not_checked"}
            and payload.get("catalog_status") in {"present_unverified", "missing", "incomplete", "invalid", "conflict", "unsupported", "unavailable"}
            and type(payload.get("catalog_duplicate_count")) is int
            and 0 <= payload["catalog_duplicate_count"] <= 8_192
            and payload.get("catalog_row_is_authenticated") is False
            and (payload.get("incident_id") is None
                or (isinstance(payload.get("incident_id"), str)
                    and 0 < len(payload["incident_id"]) <= 128))
            and (payload.get("incident_activated_at") is None
                or (isinstance(payload.get("incident_activated_at"), str)
                    and 0 < len(payload["incident_activated_at"]) <= 64))
            and _valid_optional_lower_sha256(payload.get("artifact_sha256"))
            and _valid_optional_lower_sha256(payload.get("feed_row_sha256"))
            and _valid_optional_lower_sha256(payload.get("catalog_entry_sha256"))
            and fact.effect_claimed is False and fact.effect_proven is False
        )
        attestation_verification_failure = (
            source_kind == "audit_trust"
            and fact.source.source_id == "attestation-snapshot-verification:resident-daemon"
            and subject_kind == "attestation_snapshot_verification_observation"
            and fact.stage == "observation"
            and fact.disposition == "degraded"
            and fact.evidence_strength == "owner_observed_signature_chain_verification_failure"
            and payload.get("observation_schema") in {
                "sentientos.attestation_snapshot_verification_observation:v1",
                "sentientos.attestation_snapshot_verification_observation:v2",
            }
            and payload.get("source_owner")
                == "sentientos.attestation_snapshot.verify_recent_snapshots"
            and payload.get("event_time_posture")
                == "daemon_tick_point_observation_of_bounded_verifier"
            and payload.get("verification_result") in {"warn", "fail"}
            and payload.get("verification_ok") is False
            and isinstance(payload.get("verification_reason"), str)
            and type(payload.get("checked_signature_count")) is int
            and 0 <= payload["checked_signature_count"] <= 64
            and isinstance(payload.get("verification_reason"), str)
            and payload.get("cause_unknown") is True
            and payload.get("attack_established") is False
            and payload.get("hostile_activity_established") is False
            and payload.get("compromise_established") is False
            and payload.get("effect_proven") is False
            and payload.get("effect_authority") is False
            and payload.get("independent_signature") is False
            and payload.get("authority") is False
            and payload.get("current_truth") is False
            and payload.get("read_only") is True
            and payload.get("independent_signature") is False
            and payload.get("read_only") is True
            and fact.effect_claimed is False and fact.effect_proven is False
        )
        integrity_controller_context = (
            source_kind == "audit_trust"
            and fact.source.source_id == "integrity-controller:resident-daemon"
            and subject_kind == "integrity_controller_observation"
            and fact.stage == "observation"
            and fact.disposition in {"recorded", "degraded", "unavailable"}
            and fact.evidence_strength in {
                "source_integrity_status", "integrity_controller_observation_unavailable"}
            and payload.get("observation_schema") in {
                "sentientos.integrity_controller_observation:v1",
                "sentientos.integrity_controller_observation:v2",
            }
            and payload.get("source_owner")
                == "sentientos.integrity_controller.evaluate_integrity"
            and payload.get("event_time_posture")
                == "daemon_tick_point_observation_of_integrity_controller"
            and payload.get("controller_posture") in {"ok", "warn", "fail", "unknown"}
            and _valid_integrity_controller_gates(payload)
            and payload.get("cause_unknown") is True
            and payload.get("attack_established") is False
            and payload.get("hostile_activity_established") is False
            and payload.get("compromise_established") is False
            and payload.get("effect_proven") is False
            and payload.get("effect_authority") is False
            and payload.get("authority") is False
            and payload.get("current_truth") is False
            and payload.get("read_only") is True
            and fact.effect_claimed is False and fact.effect_proven is False
        )
        resource_lineage_verified = (
            source_kind == "resource_governor"
            and subject_kind == "causal_resource_consumption"
            and fact.disposition == "recorded"
            and payload.get("lineage_posture") == "verified"
            and payload.get("recovery_posture") == "reconciled_or_restored"
            and payload.get("attribution_posture") == "receipt_bound_only"
        )
        strategy_resource_lineage_verified = (
            source_kind == "resource_governor"
            and subject_kind in {"strategy_invocation_resource_lineage",
                "model_replacement_invocation_resource_lineage"}
            and fact.disposition == "verified"
            and isinstance(payload.get("resource_linkage"), Mapping)
            and bool(payload.get("principal_binding_digest"))
            and payload.get("lineage_findings") == []
        )
        chat_process_generation_verified = (
            source_kind == "resource_governor"
            and subject_kind == "chat_process_software_generation_invocation"
            and fact.disposition == "recorded"
            and payload.get("attribution_posture")
                == "invocation_receipt_and_historical_chat_handoff_verified"
            and isinstance(payload.get("chat_process_handoff"), Mapping)
            and payload.get("loaded_code_identity_posture") == "not_independently_attested"
            and _aware_event_time(fact.observed_at)
            and payload.get("software_generation")
                == payload.get("running_software_generation_observed")
            and payload.get("software_generation_scope")
                == payload["chat_process_handoff"].get("source_generation_scope")
            and isinstance(payload.get("invocation_receipt_digest"), str)
        )
        recovery_transition = payload.get("chat_process_recovery_transition")
        recovery_handoff = payload.get("chat_process_handoff")
        recovery_generation = payload.get("software_generation")
        recovery_generation_qualified = (
            recovery_generation is None
            or (
                isinstance(recovery_generation, str) and bool(recovery_generation)
                and recovery_generation == payload.get("running_software_generation_observed")
                and isinstance(recovery_handoff, Mapping)
                and isinstance(recovery_handoff.get("source_generation_scope"), str)
                and payload.get("software_generation_scope")
                    == recovery_handoff.get("source_generation_scope")
            )
        )
        chat_process_recovery_lineage = (
            source_kind == "runtime_supervisor"
            and subject_kind == "chat_process_recovery_transition"
            and isinstance(recovery_transition, Mapping)
            and recovery_transition.get("phase_evidence_posture")
                == "canonical_installation_custody_and_digest_chain_checked_not_independently_signed"
            and recovery_transition.get("effect_authority") is False
            and recovery_transition.get("inference_performed") is False
            and payload.get("loaded_code_identity_posture") == "not_independently_attested"
            and payload.get("process_identity_scope")
                == "installation_bound_handoff_and_digest_chained_recovery_receipts"
            and payload.get("source_generation_evidence_scope")
                == "source_bundle_handoff_identity_not_loaded_code_attestation"
            and recovery_generation_qualified
            and fact.stage == "observation"
            and fact.evidence_strength == "phase_chain_with_terminal_receipt"
            and fact.effect_claimed is False and fact.effect_proven is False
        )
        chat_process_runtime_observation = (
            source_kind == "runtime_supervisor"
            and subject_kind == "chat_process_runtime_generation_observation"
            and isinstance(payload.get("chat_process_runtime_observation"), Mapping)
            and payload["chat_process_runtime_observation"].get("currentness_posture")
                == "runtime_owner_observed_at_recorded_event_time"
            and payload.get("loaded_code_identity_posture") == "not_independently_attested"
            and payload.get("software_generation_scope")
                == payload["chat_process_runtime_observation"].get("source_generation_scope")
            and payload["chat_process_runtime_observation"].get("independent_signature") is False
            and payload["chat_process_runtime_observation"].get("effect_authority") is False
        )
        current_software_generation_verified = (
            source_kind == "runtime_supervisor"
            and subject_kind == "verified_current_running_software_generation"
            and fact.disposition == "observed"
            and payload.get("currentness_posture")
                == "owner_verified_process_and_source_at_observation"
            and payload.get("process_identity_scope")
                == "pid_startup_argv_executable_entrypoint_module_origin_and_environment"
            and payload.get("software_generation_scope")
                == "configured_manifest_and_clean_repository_state_at_observation"
            and payload.get("loaded_code_identity_posture") == "not_independently_attested"
            and fact.stage == "observation"
            and fact.evidence_strength == "owner_verified_current_process_and_clean_source"
            and payload.get("authority") is False
            and payload.get("effect_proven") is False
            and fact.effect_claimed is False and fact.effect_proven is False
            and isinstance(payload.get("process_instance_id"), str)
            and isinstance(payload.get("provenance_digest"), str)
        )
        observed_running_model_verified = (
            source_kind == "runtime_supervisor"
            and subject_kind == "observed_running_model"
            and fact.stage == "observation" and fact.disposition == "observed"
            and fact.evidence_strength in {
                "serving_session_observation", "current_serving_owner_session"}
            and isinstance(payload.get("running_model_identity_observed"), Mapping)
            and bool(payload.get("running_model_identity_observed"))
            and isinstance(payload.get("serving_session_id"), str)
            and bool(payload.get("serving_session_id"))
            and _aware_event_time(fact.observed_at)
            and payload.get("event_time_posture")
                == "serving_session_observation_time_not_model_load_time"
            and payload.get("authority") is False
            and payload.get("effect_proven") is False
            and fact.effect_claimed is False and fact.effect_proven is False
        )
        if (quarantine_custody_observation or quarantine_incident_custody_observation
                or attestation_verification_failure
                or integrity_controller_context
                or observed_running_model_verified
                or current_software_generation_verified):
            priority = 0
        elif payload.get("activated_model_identity") is not None or payload.get("serving_binding_digest"):
            priority = 1
        elif (isinstance(payload.get("proposed_successor_model_development_provenance"), Mapping)
                and payload["proposed_successor_model_development_provenance"].get("identity_binding_verified") is True):
            priority = 2
        elif resource_lineage_verified:
            priority = 3
        elif strategy_resource_lineage_verified or chat_process_generation_verified:
            priority = 3
        elif (source_kind == "runtime_supervisor"
                and subject_kind in {"resident_model_transition", "software_generation_transition"}
                and payload.get("stage_semantically_verified") is True):
            priority = 4
        elif chat_process_recovery_lineage or chat_process_runtime_observation:
            priority = 4
        elif subject_kind in {"resident_model_transition", "software_generation_transition",
                              "resident_model_transition_recovery", "software_generation_transition_recovery"}:
            priority = 6
        elif (source_kind == "embodiment"
                and subject_kind == "developmental_model_replacement_experiment"):
            priority = 4
        elif (source_kind == "embodiment" and subject_kind in {
                "embodied_consequence_chain", "embodied_consequence_attribution",
                "embodied_prediction_comparison"}):
            priority = 4
        elif subject_kind in {"embodied_strategy_proposal", "embodied_strategy_proposal_review",
                              "embodied_proposal_fulfillment_receipt"}:
            priority = 5
        else:
            priority = 6
        return priority, source_kind, fact.source.source_id, fact.fact_id

    def _current_projection(self, snapshot: WorldStateSnapshot) -> CurrentWorldStateCognitiveProjection:
        """Select current context independently of developmental-writeback deduplication."""
        allowed = set(self.config.allowed_source_kinds)
        source_kinds = {source.source_id: source.kind for source in snapshot.sources}
        facts = sorted((fact for fact in snapshot.facts
            if source_kinds.get(fact.source.source_id) in allowed
            and not _unsafe_legacy_objective_cognition_fact(fact.payload)),
                       key=lambda fact: self._fact_selection_key(fact, source_kinds[fact.source.source_id]))[:self.config.max_selected_facts]
        selected = (self.writeback.select_evidence(snapshot, fact_ids=tuple(f.fact_id for f in facts))
            if facts else self.writeback.empty_selection(snapshot_id=snapshot.snapshot_id,
                snapshot_digest=snapshot.digest))
        raw = CurrentWorldStateCognitiveProjection(snapshot.snapshot_id, snapshot.digest, selected.facts,
                                                    selected.sources, selected.conflicts,
                                                    tuple(str(x["fact_id"]) for x in selected.facts))
        digest = _digest(raw.semantic_payload())
        return replace(raw, projection_id="current-world-state-" + digest[7:31], projection_digest=digest)

    @staticmethod
    def _exclude_retained_task_facts(current: CurrentWorldStateCognitiveProjection,
            records: Sequence[Mapping[str, Any]], task_family_id: str) -> CurrentWorldStateCognitiveProjection:
        """Keep the acquired source outcome in history treatment, not current evidence.

        Only exact fact IDs retained by admitted records in this declared family
        are removed. Other current observations remain shared across conditions.
        """
        excluded: set[str] = set()
        for record in records:
            candidate = record.get("candidate")
            facts = candidate.get("selected_facts", ()) if isinstance(candidate, Mapping) else ()
            for fact in facts:
                if (isinstance(fact, Mapping)
                        and isinstance(fact.get("fact_id"), str)
                        and isinstance(fact.get("payload"), Mapping)
                        and fact["payload"].get("objective_task_family") == task_family_id):
                    excluded.add(str(fact["fact_id"]))
        # The same completed family may have multiple retained run facts in
        # current World-State. Remove all matching source observations from the
        # shared current channel so an unselected sibling cannot leak transfer.
        for fact in current.facts:
            payload = fact.get("payload") if isinstance(fact, Mapping) else None
            fact_id = fact.get("fact_id") if isinstance(fact, Mapping) else None
            if (isinstance(payload, Mapping)
                    and payload.get("objective_task_family") == task_family_id
                    and isinstance(fact_id, str)):
                excluded.add(fact_id)
        if not excluded:
            return current
        facts = tuple(fact for fact in current.facts
            if not isinstance(fact, Mapping) or fact.get("fact_id") not in excluded)
        remaining_ids = {str(fact.get("fact_id")) for fact in facts if isinstance(fact, Mapping)}
        used_sources = {str(fact.get("source", {}).get("source_id"))
            for fact in facts if isinstance(fact, Mapping)
            and isinstance(fact.get("source"), Mapping)}
        sources = tuple(source for source in current.sources
            if isinstance(source, Mapping) and str(source.get("source_id")) in used_sources)
        conflicts = []
        for conflict in current.conflicts:
            if not isinstance(conflict, Mapping):
                continue
            conflict_ids = set(conflict.get("fact_ids", ()))
            if conflict_ids & excluded:
                continue
            ids = [item for item in conflict.get("fact_ids", ()) if item in remaining_ids]
            if ids:
                conflicts.append({**dict(conflict), "fact_ids": ids})
        raw = replace(current, facts=facts, sources=sources,
            conflicts=tuple(conflicts), fact_ids=tuple(sorted(remaining_ids)),
            projection_id="", projection_digest="")
        digest = _digest(raw.semantic_payload())
        return replace(raw, projection_id="current-world-state-" + digest[7:31],
            projection_digest=digest)

    def _cognize(self, *, snapshot: WorldStateSnapshot, current: CurrentWorldStateCognitiveProjection, tick_id: str,
                  projection: DevelopmentalHistoryProjection, with_history: bool,
                  prior_self_model: CognitiveSelfModelProjection | None = None,
                  prior_epistemic_state: EpistemicCognitiveProjection | None = None,
                  condition_id: str, purpose: str = COGNITION_PURPOSE,
                  protocol: Any | None = None,
                  objective_plan: Mapping[str, Any] | None = None,
                  epistemic_revision_probe: bool = False,
                  epistemic_revision_probe_prompt_preview: bool = False,
                  epistemic_revision_probe_expected_prompt_digest: str | None = None
                  ) -> ResidentCognitionObservation:
        # Keep the full eligible set in custody metadata for withheld controls;
        # only the bounded selected suffix is put into the model prompt.
        records = projection.records
        record_ids = projection.requested_record_ids if with_history else ()
        record_digests = tuple(str(record["record_digest"]) for record in records)
        qualifies_for_lesson = (
            not epistemic_revision_probe and protocol is None and with_history and purpose == COGNITION_PURPOSE
            and condition_id == "with-history"
        )
        if epistemic_revision_probe and (purpose != COGNITION_PURPOSE or protocol is not None
                or objective_plan is not None):
            raise ResidentDevelopmentalCognitionError("epistemic_revision_probe_scope_invalid")
        if epistemic_revision_probe_prompt_preview and not epistemic_revision_probe:
            raise ResidentDevelopmentalCognitionError("epistemic_revision_probe_scope_invalid")
        invalid_quarantine_custody_context = any(
            isinstance(fact, Mapping)
            and isinstance(fact.get("source"), Mapping)
            and fact["source"].get("kind") == "quarantine"
            and isinstance(fact.get("subject"), Mapping)
            and fact["subject"].get("subject_kind") == "quarantine_custody_observation"
            and fact.get("disposition") == "custody_invalid"
            and fact.get("evidence_strength") == "owner_validated_custody_failure"
            and isinstance(fact.get("payload"), Mapping)
            and fact["payload"].get("observation_schema")
                == "sentientos.integrity_quarantine_custody_observation:v1"
            and fact["payload"].get("source_owner")
                == "sentientos.integrity_quarantine.load_state_with_status"
            and fact["payload"].get("custody_result") == "invalid"
            and fact["payload"].get("quarantine_active") is None
            and fact["payload"].get("attack_established") is False
            and fact["payload"].get("hostile_activity_established") is False
            and fact["payload"].get("effect_proven") is False
            and fact["payload"].get("authority") is False
            and fact["payload"].get("current_truth") is False
            and fact.get("effect_claimed") is False
            and fact.get("effect_proven") is False
            for fact in current.facts
        )
        attestation_verification_failure_context = any(
            isinstance(fact, Mapping)
            and isinstance(fact.get("source"), Mapping)
            and fact["source"].get("kind") == "audit_trust"
            and fact["source"].get("source_id")
                == "attestation-snapshot-verification:resident-daemon"
            and isinstance(fact.get("subject"), Mapping)
            and fact["subject"].get("subject_kind")
                == "attestation_snapshot_verification_observation"
            and fact.get("stage") == "observation"
            and fact.get("disposition") == "degraded"
            and fact.get("evidence_strength")
                == "owner_observed_signature_chain_verification_failure"
            and isinstance(fact.get("payload"), Mapping)
            and fact["payload"].get("observation_schema") in {
                "sentientos.attestation_snapshot_verification_observation:v1",
                "sentientos.attestation_snapshot_verification_observation:v2",
            }
            and fact["payload"].get("source_owner")
                == "sentientos.attestation_snapshot.verify_recent_snapshots"
            and fact["payload"].get("event_time_posture")
                == "daemon_tick_point_observation_of_bounded_verifier"
            and fact["payload"].get("verification_result") in {"warn", "fail"}
            and fact["payload"].get("verification_ok") is False
            and isinstance(fact["payload"].get("verification_reason"), str)
            and type(fact["payload"].get("checked_signature_count")) is int
            and 0 <= fact["payload"]["checked_signature_count"] <= 64
            and fact["payload"].get("cause_unknown") is True
            and fact["payload"].get("attack_established") is False
            and fact["payload"].get("hostile_activity_established") is False
            and fact["payload"].get("compromise_established") is False
            and fact["payload"].get("effect_proven") is False
            and fact["payload"].get("effect_authority") is False
            and fact["payload"].get("independent_signature") is False
            and fact["payload"].get("authority") is False
            and fact["payload"].get("current_truth") is False
            and fact["payload"].get("read_only") is True
            and fact.get("effect_claimed") is False
            and fact.get("effect_proven") is False
            for fact in current.facts
        )
        integrity_controller_context = any(
            isinstance(fact, Mapping)
            and isinstance(fact.get("source"), Mapping)
            and fact["source"].get("kind") == "audit_trust"
            and fact["source"].get("source_id") == "integrity-controller:resident-daemon"
            and isinstance(fact.get("subject"), Mapping)
            and fact["subject"].get("subject_kind") == "integrity_controller_observation"
            and fact.get("stage") == "observation"
            and fact.get("disposition") in {"recorded", "degraded", "unavailable"}
            and fact.get("evidence_strength") in {
                "source_integrity_status", "integrity_controller_observation_unavailable"}
            and isinstance(fact.get("payload"), Mapping)
            and fact["payload"].get("observation_schema") in {
                "sentientos.integrity_controller_observation:v1",
                "sentientos.integrity_controller_observation:v2",
            }
            and fact["payload"].get("source_owner")
                == "sentientos.integrity_controller.evaluate_integrity"
            and fact["payload"].get("event_time_posture")
                == "daemon_tick_point_observation_of_integrity_controller"
            and fact["payload"].get("controller_posture") in {"ok", "warn", "fail", "unknown"}
            and _valid_integrity_controller_gates(fact["payload"])
            and fact["payload"].get("cause_unknown") is True
            and fact["payload"].get("attack_established") is False
            and fact["payload"].get("hostile_activity_established") is False
            and fact["payload"].get("compromise_established") is False
            and fact["payload"].get("effect_proven") is False
            and fact["payload"].get("effect_authority") is False
            and fact["payload"].get("authority") is False
            and fact["payload"].get("current_truth") is False
            and fact["payload"].get("read_only") is True
            and fact.get("effect_claimed") is False
            and fact.get("effect_proven") is False
            for fact in current.facts
        )
        quarantine_uncertainty_instruction = (
            " The current evidence includes an owner-validated quarantine custody failure. "
            "Treat the stored protective posture as unknown; do not infer attack, hostile "
            "activity, intent, or cause. Any lesson may only describe the scoped interpretation "
            "and limits of this custody evidence; do not turn it into a protective procedure, "
            "policy, or authority."
            if invalid_quarantine_custody_context else "")
        incident_custody_context = any(
            isinstance(fact, Mapping)
            and isinstance(fact.get("source"), Mapping)
            and fact["source"].get("source_id")
                == "integrity-quarantine-incident-custody:resident-daemon"
            and isinstance(fact.get("subject"), Mapping)
            and fact["subject"].get("subject_kind")
                == "quarantine_incident_custody_observation"
            and isinstance(fact.get("payload"), Mapping)
            and fact["payload"].get("observation_schema")
                == "sentientos.integrity_quarantine_incident_custody_observation:v1"
            and fact["payload"].get("reconciliation_status") in {
                "complete_local_custody", "incomplete", "conflict",
                "incomplete_identity", "observer_unavailable"}
            and fact["payload"].get("feed_is_authenticated") is False
            and fact["payload"].get("catalog_row_is_authenticated") is False
            and fact["payload"].get("attack_established") is False
            and fact["payload"].get("defensive_consequence_established") is False
            for fact in current.facts
        )
        incident_custody_uncertainty_instruction = (
            " The incident-reference result describes only local artifact/feed consistency. "
            "The feed is unauthenticated; an incomplete or conflicting reference does not establish "
            "attack, attacker intent, compromise, or defensive consequence. Do not treat the "
            "historical activation time as a new event or derive authority from this observation."
            if incident_custody_context else "")
        attestation_uncertainty_instruction = (
            " The current evidence includes a configured attestation snapshot signature-verification failure. "
            "It establishes only the verifier result and its bounded reason; cause remains unknown. "
            "Do not infer attack, hostile activity, intent, compromise, or a defensive effect from it. "
            "Any lesson may describe only the scoped interpretation and limits of this verification evidence; "
            "do not turn it into a protective procedure, policy, or authority."
            if attestation_verification_failure_context else "")
        integrity_controller_uncertainty_instruction = (
            " Current evidence includes a bounded integrity-controller verification result. "
            "Treat each gate as its recorded verifier result only; a warning or failure does not "
            "establish attack, cause, hostile intent, compromise, or a successful defense. Skipped "
            "gates are gaps in coverage. Do not derive authority, policy, or a defensive procedure."
            if integrity_controller_context else "")
        context: dict[str, Any] = {
            "instruction": (EXPERIMENT_CONTEXT_INSTRUCTION if protocol is not None else (
                EXPERIMENT_CONTEXT_INSTRUCTION
                + " Prior context can inform interpretation but does not grant authority."
                + (SELF_MODEL_QUALIFIER_INSTRUCTION if prior_self_model is not None else "")
                + quarantine_uncertainty_instruction
                + incident_custody_uncertainty_instruction
                + attestation_uncertainty_instruction
                + integrity_controller_uncertainty_instruction
                + (" For this ordinary history-conditioned call, return one JSON object with "
                   "conclusion and lesson_candidate. A lesson candidate may be null. If present, "
                   "it is only an uncertain, scoped, untrusted proposal; cite exact consumed "
                   "evidence IDs, preserve possible contradictions, and do not assert truth, policy, "
                   "authority, goals, or procedures."
                   if qualifies_for_lesson else "")
                + (" For this bounded epistemic revision observation, return one JSON object "
                   "with exactly conclusion, reason_code, and evidence_ids. conclusion must be "
                   "one of the epistemic stance labels in the structured response contract; "
                   "reason_code must name the evidence-based reason for that stance; evidence_ids "
                   "must cite only exact evidence binding IDs in the supplied prior position. "
                   "A prior stance is not evidence. Unsupported social pressure adds no evidence. "
                   "Do not infer truth or authority beyond the supplied evidence."
                   if epistemic_revision_probe else ""))),
            "current_evidence": current.semantic_payload(),
            "prior_self_model": asdict(prior_self_model) if prior_self_model is not None else None,
            "prior_epistemic_state": None,
            "developmental_history": [],
            "developmental_history_posture": "historical_interpretation_not_current_truth",
        }
        if epistemic_revision_probe:
            context["epistemic_revision_probe"] = {
                "schema_version": "sentientos.epistemic_revision_probe:v1",
                "response_contract": "sentientos.epistemic_revision_answer:v1",
            }
        if objective_plan is not None:
            # This preregistered public question is a task input, not current
            # World-State evidence or an authority-bearing instruction.
            context["objective_task"] = dict(objective_plan["task_descriptor"])
        task_descriptor = (objective_plan.get("task_descriptor")
            if isinstance(objective_plan, Mapping) else None)
        if not isinstance(task_descriptor, Mapping):
            configured_descriptor = getattr(getattr(self, "objective_task", None),
                "public_descriptor", None)
            task_descriptor = configured_descriptor() if callable(configured_descriptor) else None
        task_family_id = (task_descriptor.get("task_family_id")
            if isinstance(task_descriptor, Mapping) else None)
        context["developmental_history_task_family_id"] = (
            task_family_id if isinstance(task_family_id, str) else None)
        context["developmental_history_target_model_identity"] = (
            _observed_current_cognition_model_identity(self.invoker))
        context["developmental_history_retrieval_policy_id"] = (
            "task_family_probe_overlap_then_recency_fill:v2"
            if isinstance(task_family_id, str) else "completed_tick_recency_suffix:v1")
        context, epistemic_metadata, prompt, record_ids, record_digests = (
            _bind_history_and_epistemic_context(context=context, records=records,
                projection=prior_epistemic_state, history_present=with_history))
        if with_history and not record_ids:
            raise ResidentDevelopmentalCognitionError("history_context_budget_exhausted")
        if epistemic_revision_probe_prompt_preview:
            raise _EpistemicRevisionProbePromptPreview(prompt)
        correlation = f"{tick_id}:resident_developmental_cognition:{condition_id}"
        upstream_evidence = {"snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
                               "current_projection_id": current.projection_id,
                               "current_projection_digest": current.projection_digest,
                               "current_fact_ids": list(current.fact_ids),
                               "self_model_projection_present": prior_self_model is not None,
                               "self_model_projection_id": prior_self_model.projection_id if prior_self_model else None,
                               "self_model_projection_digest": prior_self_model.projection_digest if prior_self_model else None,
                               "self_model_reconciliation_id": prior_self_model.source_reconciliation_id if prior_self_model else None,
                               "self_model_reconciliation_digest": prior_self_model.source_reconciliation_digest if prior_self_model else None,
                               "self_model_reconciliation_generation": prior_self_model.source_reconciliation_generation if prior_self_model else None,
                               "self_model_source_tick": prior_self_model.source_tick if prior_self_model else None,
                               "self_model_claim_ids": list(prior_self_model.selected_claim_ids) if prior_self_model else [],
                               "self_model_claim_digests": list(prior_self_model.selected_claim_digests) if prior_self_model else [],
                               "epistemic_projection_id": prior_epistemic_state.projection_id if prior_epistemic_state else None,
                               "epistemic_projection_digest": prior_epistemic_state.projection_digest if prior_epistemic_state else None,
                               "epistemic_proposition_ids": list(prior_epistemic_state.proposition_ids) if prior_epistemic_state else [],
                               "epistemic_state_ids": list(prior_epistemic_state.state_ids) if prior_epistemic_state else [],
                               "epistemic_state_digests": list(prior_epistemic_state.state_digests) if prior_epistemic_state else [],
                               "epistemic_generations": list(prior_epistemic_state.generations) if prior_epistemic_state else [],
                               "epistemic_evidence_set_digests": list(prior_epistemic_state.evidence_set_digests) if prior_epistemic_state else [],
                                "record_ids": list(record_ids), "record_digests": list(record_digests),
                                **epistemic_metadata}
        if objective_plan is not None:
            upstream_evidence.update({"objective_task_plan_digest": objective_plan["plan_digest"],
                "objective_task_digest": objective_plan["task_descriptor"]["task_digest"]})
            task_family_id = objective_plan["task_descriptor"].get("task_family_id")
            if isinstance(task_family_id, str) and protocol is not None:
                family_fact_ids: set[str] = set()
                for record_id in protocol.record_ids:
                    record = self.writeback.store.get(record_id)
                    candidate = record.candidate
                    source_facts = candidate.get("selected_facts", ()) if isinstance(candidate, Mapping) else ()
                    family_fact_ids.update(str(fact["fact_id"]) for fact in source_facts
                        if isinstance(fact, Mapping) and isinstance(fact.get("fact_id"), str)
                        and isinstance(fact.get("payload"), Mapping)
                        and fact["payload"].get("objective_task_family") == task_family_id)
                upstream_evidence.update({
                    "task_family_id": task_family_id,
                    "task_family_source_fact_ids": sorted(family_fact_ids),
                    "task_family_source_fact_ids_digest": _digest(sorted(family_fact_ids)),
                    "task_family_evidence_posture": "operator_declared_family_bound_to_admitted_source_facts"})
        if (epistemic_revision_probe_expected_prompt_digest is not None
                and _digest({"prompt": prompt})
                    != epistemic_revision_probe_expected_prompt_digest):
            raise ResidentDevelopmentalCognitionError(
                "epistemic_revision_probe_prompt_digest_mismatch")
        request = self.invoker.build_request(
            purpose=purpose, prompt=prompt, caller=PRINCIPAL,
            correlation_id=correlation,
            expected_output_format="json" if qualifies_for_lesson or objective_plan is not None
                or epistemic_revision_probe else "text",
            budget=LocalModelInvocationBudget(max_input_chars=MAX_RESIDENT_COGNITION_INPUT_CHARS, max_output_chars=4000, max_new_tokens=512,
                                              timeout_seconds=30, max_calls_per_correlation=1),
            structured_output_schema=(RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA
                if epistemic_revision_probe else RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA
                if qualifies_for_lesson else None),
            upstream_evidence=upstream_evidence,
            linkage={"condition_group": f"{tick_id}:retrieval-comparison", "condition_id": condition_id,
                     "history_present": with_history},
        )
        request_upstream = getattr(request, "upstream_evidence", None)
        if (not isinstance(request_upstream, Mapping)
                or any(request_upstream.get(key) != value
                    for key, value in epistemic_metadata.items())):
            raise ResidentDevelopmentalCognitionError("cognition_epistemic_request_binding_mismatch")
        if objective_plan is not None and (
                request_upstream.get("objective_task_plan_digest") != objective_plan.get("plan_digest")
                or request_upstream.get("objective_task_digest")
                    != objective_plan.get("task_descriptor", {}).get("task_digest")):
            raise ResidentDevelopmentalCognitionError("objective_task_request_binding_mismatch")
        if protocol is not None and (
            request.model_id != protocol.model_id
            or request.model_artifact_digest != protocol.model_artifact_digest
            or str(getattr(request, "authority_map_digest", "test-authority-map")) != protocol.authority_map_digest
            or dict(getattr(request, "active_model_identity", {})) != dict(protocol.active_model_identity)
            or request.budget.to_dict() != dict(protocol.inference_budget)
            or protocol.instruction_template_digest != _digest({"instruction": EXPERIMENT_CONTEXT_INSTRUCTION})
            or snapshot.snapshot_id != protocol.snapshot_id
            or snapshot.digest != protocol.snapshot_digest
            or current.projection_id != protocol.current_projection_id
            or current.projection_digest != protocol.current_projection_digest
            or tuple(current.fact_ids) != protocol.current_fact_ids
            or (prior_self_model.projection_id if prior_self_model else None) != protocol.self_model_projection_id
            or (prior_self_model.projection_digest if prior_self_model else None) != protocol.self_model_projection_digest
            or (prior_self_model.source_reconciliation_id if prior_self_model else None) != protocol.self_model_reconciliation_id
            or (prior_self_model.source_reconciliation_digest if prior_self_model else None) != protocol.self_model_reconciliation_digest
            or (prior_self_model.source_reconciliation_generation if prior_self_model else None) != protocol.self_model_reconciliation_generation
            or (prior_self_model.source_tick if prior_self_model else None) != protocol.self_model_source_tick
            or (prior_self_model.selected_claim_ids if prior_self_model else ()) != protocol.self_model_claim_ids
            or (prior_self_model.selected_claim_digests if prior_self_model else ()) != protocol.self_model_claim_digests
        ):
            raise ResidentDevelopmentalCognitionError("experiment_control_drift")
        if protocol is not None:
            expected_ids = protocol.record_ids if with_history else ()
            expected_digests = protocol.record_digests if with_history else ()
            if tuple(record_ids) != tuple(expected_ids) or tuple(record_digests) != tuple(expected_digests):
                raise ResidentDevelopmentalCognitionError("experiment_history_binding_drift")
        invocation_options: dict[str, Any] = {
            "persist": True,
            # Research probes retain the delivered response in the invocation
            # receipt for later independent qualification. Ordinary cognition
            # keeps the existing output-redaction default.
            "include_output_in_receipt": epistemic_revision_probe,
        }
        if self.resource_context_owner is not None:
            # Each preregistered condition consumes its own owner-issued
            # context. The governed invoker binds the resulting ledger receipt
            # to this exact inference receipt; the cognition owner never
            # estimates or fabricates resource measurements.
            invocation_options["resource_context"] = (
                self.resource_context_owner.next_context())
        receipt = self.invoker.invoke(request, **invocation_options)
        if receipt.status not in {"admitted_completed", "admitted_simulation"} or receipt.output_digest is None:
            raise ResidentDevelopmentalCognitionError("retrieval_cognition_not_completed")
        receipt_request = getattr(receipt, "request", None)
        if (not isinstance(receipt_request, Mapping)
                or dict(receipt_request) != request.to_receipt_request_dict()
                or receipt_request.get("upstream_evidence") != dict(request_upstream)):
            raise ResidentDevelopmentalCognitionError("cognition_epistemic_receipt_binding_mismatch")
        if protocol is not None and dict(receipt.generation_config).get("actual_generation_parameters", {}).get("temperature") != 0:
            raise ResidentDevelopmentalCognitionError("experiment_generation_configuration_drift")
        lesson_payload: Mapping[str, Any] | None = None
        source_output_text = receipt.output_text
        if (qualifies_for_lesson and receipt.status == "admitted_completed"
                and source_output_text is not None and not receipt.output_truncated
                and not receipt.fallback_occurred
                and receipt.effects.get("local_model_inference") is True
                and receipt.output_size_bytes == len(source_output_text.encode("utf-8"))
                and digest_payload({"output": source_output_text}) == receipt.output_digest):
            consumed_ids = set(record_ids) | set(current.fact_ids)
            consumed_ids.update(str(item) for item in epistemic_metadata.get(
                "epistemic_consumed_packet_ids", ()) if isinstance(item, str))
            if prior_self_model is not None:
                consumed_ids.update(prior_self_model.selected_claim_ids)
            try:
                lesson_payload = _parse_cognition_lesson_output(source_output_text, consumed_ids)
            except (TypeError, ValueError, json.JSONDecodeError):
                # A completed cognition remains an observation even when its
                # optional, scoped lesson packet is malformed or unavailable.
                lesson_payload = None
        req = dict(receipt.request)
        request_linkage = req.get("linkage")
        serving_session = (request_linkage.get("resident_cognitive_serving")
            if isinstance(request_linkage, Mapping) else None)
        serving_session_id = None
        serving_session_binding = None
        serving_session_receipt_id = None
        serving_session_receipt_digest = None
        if serving_session is not None:
            if (not isinstance(serving_session, Mapping)
                    or set(serving_session) != {"session_id", "model_serving_admission_ref",
                        "activation_state_semantic_digest", "session_receipt_id",
                        "session_receipt_semantic_digest"}
                    or not all(isinstance(serving_session.get(key), str) and serving_session.get(key)
                        for key in ("session_id", "model_serving_admission_ref",
                            "activation_state_semantic_digest", "session_receipt_id",
                            "session_receipt_semantic_digest"))):
                raise ResidentDevelopmentalCognitionError("cognition_invocation_session_binding_invalid")
            serving_session_id = str(serving_session["session_id"])
            serving_session_binding = {
                "model_serving_admission_ref": str(serving_session["model_serving_admission_ref"]),
                "activation_state_semantic_digest": str(serving_session["activation_state_semantic_digest"])}
            serving_session_receipt_id = str(serving_session["session_receipt_id"])
            serving_session_receipt_digest = str(serving_session["session_receipt_semantic_digest"])
        semantic = {
            "condition_id": condition_id, "tick_id": tick_id, "correlation_id": correlation,
            "model_id": str(req["model_id"]), "model_artifact_digest": req.get("model_artifact_digest"),
            "request_id": str(req["request_id"]), "request_digest": str(req["request_digest"]),
            "inference_receipt_id": receipt.receipt_id, "inference_receipt_digest": receipt.receipt_digest,
            "output_digest": receipt.output_digest,
            "authority_map_digest":str(getattr(request, "authority_map_digest", "test-authority-map")),
            "active_model_identity":dict(getattr(request, "active_model_identity", {})),
            "generation_config":dict(receipt.generation_config), "current_snapshot_id": snapshot.snapshot_id,
            "current_snapshot_digest": snapshot.digest, "current_projection_id":current.projection_id,
            "current_projection_digest":current.projection_digest, "current_fact_ids":current.fact_ids,
            "retrieved_record_ids": record_ids,
            "retrieved_record_digests": record_digests, "developmental_projection_present": with_history,
            "self_model_projection_present": prior_self_model is not None,
            "self_model_projection_id": prior_self_model.projection_id if prior_self_model else None,
            "self_model_projection_digest": prior_self_model.projection_digest if prior_self_model else None,
            "self_model_reconciliation_id": prior_self_model.source_reconciliation_id if prior_self_model else None,
            "self_model_reconciliation_digest": prior_self_model.source_reconciliation_digest if prior_self_model else None,
            "self_model_reconciliation_generation": prior_self_model.source_reconciliation_generation if prior_self_model else None,
            "self_model_source_tick": prior_self_model.source_tick if prior_self_model else None,
            "self_model_claim_ids": prior_self_model.selected_claim_ids if prior_self_model else (),
            "self_model_claim_digests": prior_self_model.selected_claim_digests if prior_self_model else (),
            "prior_tick_proven": prior_self_model is not None and prior_self_model.source_tick != tick_id,
            "epistemic_projection_present": prior_epistemic_state is not None,
            "epistemic_projection_id": prior_epistemic_state.projection_id if prior_epistemic_state else None,
            "epistemic_projection_digest": prior_epistemic_state.projection_digest if prior_epistemic_state else None,
            "epistemic_proposition_ids": prior_epistemic_state.proposition_ids if prior_epistemic_state else (),
            "epistemic_state_ids": prior_epistemic_state.state_ids if prior_epistemic_state else (),
            "epistemic_state_digests": prior_epistemic_state.state_digests if prior_epistemic_state else (),
            "epistemic_generations": prior_epistemic_state.generations if prior_epistemic_state else (),
            "epistemic_evidence_set_digests": prior_epistemic_state.evidence_set_digests if prior_epistemic_state else (),
            **epistemic_metadata,
            **_resource_linkage_fields(receipt),
            "schema_version": COGNITION_OBSERVATION_SCHEMA_V7,
            "serving_session_id": serving_session_id,
            "serving_session_binding": serving_session_binding,
            "serving_session_receipt_id": serving_session_receipt_id,
            "serving_session_receipt_digest": serving_session_receipt_digest,
            "observed_at": receipt.observed_at,
            "historical_context_only": True, "current_truth": False, "authority": False,
            "policy": False, "canonical_explicit_user_retention": False,
        }
        digest = _digest(semantic)
        observation = ResidentCognitionObservation(
            "devcog-" + digest[7:31], digest, condition_id, tick_id, correlation,
            str(req["model_id"]), req.get("model_artifact_digest"), str(req["request_id"]),
            str(req["request_digest"]), receipt.receipt_id, receipt.receipt_digest,
            receipt.output_digest, str(getattr(request, "authority_map_digest", "test-authority-map")),
            dict(getattr(request, "active_model_identity", {})), dict(receipt.generation_config),
            snapshot.snapshot_id, snapshot.digest, current.projection_id,
            current.projection_digest, current.fact_ids, record_ids,
            record_digests, with_history,
            prior_self_model is not None, prior_self_model.projection_id if prior_self_model else None,
            prior_self_model.projection_digest if prior_self_model else None,
            prior_self_model.source_reconciliation_id if prior_self_model else None,
            prior_self_model.source_reconciliation_digest if prior_self_model else None,
            prior_self_model.source_reconciliation_generation if prior_self_model else None,
            prior_self_model.source_tick if prior_self_model else None,
            prior_self_model.selected_claim_ids if prior_self_model else (),
            prior_self_model.selected_claim_digests if prior_self_model else (),
            prior_self_model is not None and prior_self_model.source_tick != tick_id,
            prior_epistemic_state is not None,
            prior_epistemic_state.projection_id if prior_epistemic_state else None,
            prior_epistemic_state.projection_digest if prior_epistemic_state else None,
            prior_epistemic_state.proposition_ids if prior_epistemic_state else (),
            prior_epistemic_state.state_ids if prior_epistemic_state else (),
            prior_epistemic_state.state_digests if prior_epistemic_state else (),
            prior_epistemic_state.generations if prior_epistemic_state else (),
            prior_epistemic_state.evidence_set_digests if prior_epistemic_state else (),
            schema_version=COGNITION_OBSERVATION_SCHEMA_V7,
            serving_session_id=serving_session_id,
            serving_session_binding=serving_session_binding,
            serving_session_receipt_id=serving_session_receipt_id,
            serving_session_receipt_digest=serving_session_receipt_digest,
            observed_at=receipt.observed_at,
            **_resource_linkage_fields(receipt),
            **epistemic_metadata,
        )
        if observation.schema_version == COGNITION_OBSERVATION_SCHEMA_V7:
            self._verify_observation_invocation(asdict(observation))
        if epistemic_revision_probe:
            capture: dict[str, Any] = {
                "schema_version": "sentientos.epistemic_revision_probe_capture:v1",
                "observation_id": observation.observation_id,
                "observation_digest": observation.observation_digest,
                "prompt": prompt,
                "request": request.to_receipt_request_dict(),
                "receipt": receipt.to_dict(include_output=True),
                "answer_key_included": False,
            }
            capture["capture_digest"] = _digest(capture)
            try:
                directory_fd = _open_store_directory(
                    self.epistemic_revision_probe_captures_root, create=True)
                os.close(directory_fd)
                _publish_store_json(
                    self.epistemic_revision_probe_captures_root
                        / f"{observation.observation_id}.json",
                    capture,
                    collision_error="epistemic_revision_probe_capture_identity_collision",
                    max_bytes=MAX_COMPOSITION_STATE_BYTES)
            except (OSError, DevelopmentalWritebackError) as exc:
                raise ResidentDevelopmentalCognitionError(
                    "epistemic_revision_probe_capture_publication_failed") from exc
        try:
            _publish_store_json(self.observations_root / f"{observation.observation_id}.json",
                asdict(observation), collision_error="cognition_observation_identity_collision")
        except DevelopmentalWritebackError as exc:
            raise ResidentDevelopmentalCognitionError(
                "cognition_observation_publication_failed") from exc
        if objective_plan is not None:
            if protocol is None:
                raise ResidentDevelopmentalCognitionError("objective_task_protocol_missing")
            try:
                checkpoint = self.experiments.persist_objective_condition_score(
                    protocol, objective_plan, condition_id=condition_id,
                    observation=asdict(observation), receipt=receipt)
                score = checkpoint["score"]
            except (DevelopmentalHistoryInterventionError, TypeError, ValueError) as exc:
                raise ResidentDevelopmentalCognitionError("objective_task_scoring_failed") from exc
            self._pending_objective_scores[observation.observation_id] = {
                "condition_id": condition_id,
                "inference_receipt_id": receipt.receipt_id,
                "inference_receipt_digest": receipt.receipt_digest,
                "invocation_output_digest": receipt.output_digest,
                "output_truncated": receipt.output_truncated,
                "score": score,
            }
        if (lesson_payload is not None and isinstance(lesson_payload.get("lesson_candidate"), Mapping)
                and source_output_text is not None):
            self._pending_cognition_candidates[observation.observation_id] = (
                receipt, source_output_text, lesson_payload)
        return observation

    @contextmanager
    def _composition_lock(self) -> Iterator[None]:
        """Serialize the complete durable tick across owner instances/processes."""
        if os.name != "posix":
            raise ResidentDevelopmentalCognitionError("composition_lock_unsupported_platform")
        directory_fd: int | None = None
        descriptor: int | None = None
        try:
            require_flock()
            directory_fd = open_private_directory(self.state_path.parent, create=True)
            descriptor = os.open(
                ".resident-developmental-cognition.lock",
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=directory_fd,
            )
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or opened.st_nlink != 1
                or opened.st_mode & 0o077
            ):
                raise ResidentDevelopmentalCognitionError("composition_lock_invalid")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except ResidentDevelopmentalCognitionError:
            if descriptor is not None:
                os.close(descriptor)
            if directory_fd is not None:
                os.close(directory_fd)
            raise
        except (OSError, PrivateFileCustodyError) as exc:
            if descriptor is not None:
                os.close(descriptor)
            if directory_fd is not None:
                os.close(directory_fd)
            raise ResidentDevelopmentalCognitionError("composition_lock_unavailable") from exc
        assert directory_fd is not None and descriptor is not None
        try:
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
                os.close(directory_fd)

    def run_tick(self, *, snapshot: WorldStateSnapshot, tick_id: str,
                 prior_self_model: CognitiveSelfModelProjection | None = None,
                 prior_epistemic_state: EpistemicCognitiveProjection | None = None) -> ResidentDevelopmentalCycleResult:
        return self._run_tick(snapshot=snapshot, tick_id=tick_id,
            prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state,
            objective_task=self.objective_task, objective_only=False,
            objective_request_id=None, objective_request_digest=None)

    def preview_epistemic_revision_probe_prompt(self, *, snapshot: WorldStateSnapshot,
            tick_id: str, prior_epistemic_state: EpistemicCognitiveProjection
            ) -> dict[str, Any]:
        """Compose the exact probe prompt without admission, invocation, or capture.

        This is the controller-side preparation step for sealing prompt digests.
        It shares the production prompt builder and deliberately stops before
        request construction, authority admission, model invocation, or probe
        observation publication. Reading owner state may perform the owner's
        normal verified recovery of an interrupted prior tick.
        """
        if (not self.config.enabled or self.config.comparison_enabled
                or self.objective_task is not None
                or not isinstance(prior_epistemic_state, EpistemicCognitiveProjection)
                or not isinstance(tick_id, str) or not tick_id or len(tick_id) > 256
                or not validate_snapshot(snapshot).valid):
            raise ResidentDevelopmentalCognitionError(
                "epistemic_revision_probe_configuration_invalid")
        with self._composition_lock():
            state = self._state()
            if (any(row.get("tick_id") == tick_id for row in state["completed_ticks"])
                    or any(row.get("tick_id") == tick_id for row in state["incomplete_ticks"])):
                raise ResidentDevelopmentalCognitionError("tick_already_completed")
            if (len(state["completed_ticks"]) + len(state["incomplete_ticks"])
                    >= MAX_RECOVERED_TICKS):
                raise ResidentDevelopmentalCognitionError(
                    "composition_state_retention_limit_exceeded")
            prior = self._prior_projection(state, tick_id)
            current = self._current_projection(snapshot)
            with_history = bool(prior.requested_record_ids)
            try:
                self._cognize(snapshot=snapshot, current=current, tick_id=tick_id,
                    projection=prior, with_history=with_history,
                    condition_id="with-history" if with_history else "prior-context",
                    prior_epistemic_state=prior_epistemic_state,
                    epistemic_revision_probe=True,
                    epistemic_revision_probe_prompt_preview=True)
            except _EpistemicRevisionProbePromptPreview as preview:
                return {"prompt": preview.prompt,
                    "prompt_digest": _digest({"prompt": preview.prompt}),
                    "model_identity": _observed_current_cognition_model_identity(self.invoker),
                    "model_invocation_performed": False,
                    "probe_observation_written": False}
        raise ResidentDevelopmentalCognitionError(
            "epistemic_revision_probe_prompt_preview_unavailable")

    def run_epistemic_revision_probe_once(self, *, snapshot: WorldStateSnapshot,
            tick_id: str, prior_epistemic_state: EpistemicCognitiveProjection,
            expected_prompt_digest: str | None = None
            ) -> ResidentDevelopmentalCycleResult:
        """Capture one bounded revision judgment through the governed cognition owner."""
        if (self.config.comparison_enabled or self.objective_task is not None
                or not isinstance(prior_epistemic_state, EpistemicCognitiveProjection)
                or (expected_prompt_digest is not None
                    and (not isinstance(expected_prompt_digest, str)
                        or len(expected_prompt_digest) != 71
                        or not expected_prompt_digest.startswith("sha256:")
                        or any(char not in "0123456789abcdef"
                            for char in expected_prompt_digest[7:])))):
            raise ResidentDevelopmentalCognitionError("epistemic_revision_probe_configuration_invalid")
        return self._run_tick(snapshot=snapshot, tick_id=tick_id,
            prior_self_model=None, prior_epistemic_state=prior_epistemic_state,
            objective_task=None, objective_only=False, objective_request_id=None,
            objective_request_digest=None, epistemic_revision_probe=True,
            epistemic_revision_probe_expected_prompt_digest=expected_prompt_digest)

    def objective_request_disposition(self, *, request_id: str,
            request_digest: str) -> str:
        """Return whether this bounded request is new, completed, or interrupted."""
        state = self._state()
        for row in (*state["completed_ticks"], *state["incomplete_ticks"]):
            if row.get("objective_request_id") != request_id:
                continue
            if row.get("objective_request_digest") != request_digest:
                return "identity_conflict"
            return "completed" if row in state["completed_ticks"] else "interrupted"
        return "new"

    def run_objective_intervention_once(self, *, snapshot: WorldStateSnapshot,
            tick_id: str, objective_task: Any, request_id: str,
            request_digest: str,
            prior_epistemic_state: EpistemicCognitiveProjection | None = None
            ) -> ResidentDevelopmentalCycleResult:
        """Run one explicit scored history intervention without developmental writeback."""
        if (self.objective_task is not None or not self.config.comparison_enabled
                or not callable(getattr(objective_task, "specification", None))
                or not callable(getattr(objective_task, "public_descriptor", None))):
            raise ResidentDevelopmentalCognitionError("objective_one_shot_not_configured")
        payload = objective_request_payload(request_id=request_id, task=objective_task)
        legacy_digest = _legacy_objective_request_digest(
            request_id=request_id, task=objective_task)
        if request_digest not in {payload.get("request_digest"), legacy_digest}:
            raise ResidentDevelopmentalCognitionError("objective_request_digest_mismatch")
        return self._run_tick(snapshot=snapshot, tick_id=tick_id,
            prior_self_model=None, prior_epistemic_state=prior_epistemic_state,
            objective_task=objective_task,
            objective_only=True, objective_request_id=request_id,
            objective_request_digest=request_digest)

    def _run_tick(self, *, snapshot: WorldStateSnapshot, tick_id: str,
                 prior_self_model: CognitiveSelfModelProjection | None,
                 prior_epistemic_state: EpistemicCognitiveProjection | None,
                 objective_task: Any | None, objective_only: bool,
                 objective_request_id: str | None,
                 objective_request_digest: str | None,
                 epistemic_revision_probe: bool = False,
                 epistemic_revision_probe_expected_prompt_digest: str | None = None
                 ) -> ResidentDevelopmentalCycleResult:
        if not self.config.enabled:
            return ResidentDevelopmentalCycleResult("disabled", tick_id, snapshot.snapshot_id)
        if os.name != "posix":
            return self._run_tick_locked(snapshot=snapshot, tick_id=tick_id,
                prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state,
                objective_task=objective_task, objective_only=objective_only,
                objective_request_id=objective_request_id,
                objective_request_digest=objective_request_digest,
                epistemic_revision_probe=epistemic_revision_probe,
                epistemic_revision_probe_expected_prompt_digest=(
                    epistemic_revision_probe_expected_prompt_digest))
        with self._composition_lock():
            return self._run_tick_locked(snapshot=snapshot, tick_id=tick_id,
                prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state,
                objective_task=objective_task, objective_only=objective_only,
                objective_request_id=objective_request_id,
                objective_request_digest=objective_request_digest,
                epistemic_revision_probe=epistemic_revision_probe,
                epistemic_revision_probe_expected_prompt_digest=(
                    epistemic_revision_probe_expected_prompt_digest))

    def _run_tick_locked(self, *, snapshot: WorldStateSnapshot, tick_id: str,
                 prior_self_model: CognitiveSelfModelProjection | None = None,
                 prior_epistemic_state: EpistemicCognitiveProjection | None = None,
                 objective_task: Any | None = None, objective_only: bool = False,
                 objective_request_id: str | None = None,
                 objective_request_digest: str | None = None,
                 epistemic_revision_probe: bool = False,
                 epistemic_revision_probe_expected_prompt_digest: str | None = None
                 ) -> ResidentDevelopmentalCycleResult:
        if not self.config.enabled:
            return ResidentDevelopmentalCycleResult("disabled", tick_id, snapshot.snapshot_id)
        if os.name != "posix":
            raise ResidentDevelopmentalCognitionError("composition_publication_unsupported_platform")
        if not isinstance(tick_id, str) or not tick_id or len(tick_id) > 256:
            raise ResidentDevelopmentalCognitionError("composition_tick_identity_invalid")
        validation = validate_snapshot(snapshot)
        if not validation.valid:
            raise ResidentDevelopmentalCognitionError("invalid_world_state_snapshot")
        self._pending_cognition_candidates.clear()
        self._pending_objective_scores.clear()
        state = self._state()
        if objective_only:
            if (not isinstance(objective_request_id, str) or not objective_request_id
                    or not isinstance(objective_request_digest, str)
                    or not objective_request_digest or len(objective_request_digest) > 80):
                raise ResidentDevelopmentalCognitionError("objective_request_identity_invalid")
            disposition = self.objective_request_disposition(request_id=objective_request_id,
                request_digest=objective_request_digest)
            if disposition != "new":
                raise ResidentDevelopmentalCognitionError("objective_request_" + disposition)
        if (any(row.get("tick_id") == tick_id for row in state["completed_ticks"])
                or any(row.get("tick_id") == tick_id for row in state["incomplete_ticks"])):
            raise ResidentDevelopmentalCognitionError("tick_already_completed")
        if len(state["completed_ticks"]) + len(state["incomplete_ticks"]) >= MAX_RECOVERED_TICKS:
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")

        # Capture prior history before the experiment intent. This permits a
        # staged one-shot request with no eligible history to be terminalized
        # without invoking a model or leaving an automatic retry behind.
        task_descriptor = (objective_task.public_descriptor()
            if objective_task is not None else {})
        family_id = task_descriptor.get("task_family_id") if isinstance(task_descriptor, Mapping) else None
        task_probe_inputs = (tuple(task_descriptor.get("probe_inputs", ()))
            if isinstance(task_descriptor, Mapping)
            and isinstance(task_descriptor.get("probe_inputs", ()), (list, tuple))
            and all(type(value) is int for value in task_descriptor.get("probe_inputs", ()))
            else ())
        prior = self._prior_projection(state, tick_id, task_family_id=family_id,
            task_probe_inputs=task_probe_inputs)
        if objective_only and not prior.requested_record_ids:
            assert objective_request_id is not None and objective_request_digest is not None
            state["completed_ticks"].append({"tick_id": tick_id,
                "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
                "record_id": None, "receipt_id": None,
                "objective_request_id": objective_request_id,
                "objective_request_digest": objective_request_digest,
                "objective_request_status": "blocked_no_eligible_history"})
            self._save_state(state)
            return ResidentDevelopmentalCycleResult("objective_blocked_no_eligible_history",
                tick_id, snapshot.snapshot_id)
        require_family = (objective_task.specification().get("requires_task_family_history") is True
            if objective_task is not None else False)
        if objective_only and isinstance(family_id, str) and require_family:
            family_records = [record for record in prior.records
                if any(isinstance(fact, Mapping)
                    and isinstance(fact.get("payload"), Mapping)
                    and fact["payload"].get("objective_task_family") == family_id
                    for fact in (record.get("candidate", {}).get("selected_facts", ())
                        if isinstance(record.get("candidate"), Mapping) else ())) ]
            if not family_records:
                assert objective_request_id is not None and objective_request_digest is not None
                state["completed_ticks"].append({"tick_id": tick_id,
                    "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
                    "record_id": None, "receipt_id": None,
                    "objective_request_id": objective_request_id,
                    "objective_request_digest": objective_request_digest,
                    "objective_request_status": "blocked_no_task_relevant_history"})
                self._save_state(state)
                return ResidentDevelopmentalCycleResult("objective_blocked_no_task_relevant_history",
                    tick_id, snapshot.snapshot_id)

        # Publish the exact snapshot/tick intent before any local-model call.
        # A crash before the first durable cognition observation must remain
        # distinguishable from a tick that never began, and the same tick may
        # not be replayed after restart. A future tick can continue normally.
        state["incomplete_ticks"].append({"tick_id": tick_id,
            "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
            "status": "in_progress",
            **({"objective_request_id": objective_request_id,
                "objective_request_digest": objective_request_digest}
                if objective_only else {})})
        self._save_state(state)

        current = self._current_projection(snapshot)
        if isinstance(family_id, str) and objective_only:
            current = self._exclude_retained_task_facts(current, prior.records, family_id)
        observations: list[ResidentCognitionObservation] = []
        measurement_id: str | None = None
        has_developmental_history = bool(prior.requested_record_ids)
        has_prior_self_model = prior_self_model is not None
        has_prior_epistemic_state = prior_epistemic_state is not None
        should_cognize = (has_developmental_history or has_prior_self_model
                          or has_prior_epistemic_state or epistemic_revision_probe)
        should_run_history_comparison = (self.config.comparison_enabled
                                         and has_developmental_history)
        if should_cognize:
            if not should_run_history_comparison:
                observations.append(self._cognize(snapshot=snapshot, current=current, tick_id=tick_id,
                                    projection=prior, with_history=has_developmental_history,
                                    condition_id="with-history" if has_developmental_history else "prior-context",
                                    prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state,
                                    epistemic_revision_probe=epistemic_revision_probe,
                                    epistemic_revision_probe_expected_prompt_digest=(
                                        epistemic_revision_probe_expected_prompt_digest)))
            else:
                # Freeze the exact history that fits the real inference context
                # before preregistering the comparison. Conditions rerun this
                # same deterministic binder over the full available set; their
                # selected suffix must equal the protocol's admitted history.
                task_descriptor_for_preflight = (objective_task.public_descriptor()
                    if objective_task is not None else
                    self.objective_task.public_descriptor()
                        if self.objective_task is not None else None)
                family_for_preflight = (task_descriptor_for_preflight.get("task_family_id")
                    if isinstance(task_descriptor_for_preflight, Mapping) else None)
                preflight_target_model_identity = (
                    _observed_current_cognition_model_identity(self.invoker))
                preflight_context: dict[str, Any] = {
                    "instruction": EXPERIMENT_CONTEXT_INSTRUCTION,
                    "current_evidence": current.semantic_payload(),
                    "prior_self_model": asdict(prior_self_model)
                        if prior_self_model is not None else None,
                    "prior_epistemic_state": None,
                    "developmental_history": [],
                    "developmental_history_posture": "historical_interpretation_not_current_truth",
                    "developmental_history_task_family_id": family_for_preflight,
                    "developmental_history_target_model_identity": preflight_target_model_identity,
                    "developmental_history_retrieval_policy_id": (
                        "task_family_probe_overlap_then_recency_fill:v2"
                        if isinstance(family_for_preflight, str)
                        else "completed_tick_recency_suffix:v1"),
                }
                if objective_task is not None and isinstance(task_descriptor_for_preflight, Mapping):
                    preflight_context["objective_task"] = dict(task_descriptor_for_preflight)
                _, preflight_metadata, _, protocol_record_ids, record_digests = (
                    _bind_history_and_epistemic_context(context=preflight_context,
                        records=prior.records, projection=prior_epistemic_state,
                        history_present=True))
                preflight_selection = preflight_metadata.get(
                    "developmental_history_selection")
                if not isinstance(preflight_selection, Mapping):
                    raise ResidentDevelopmentalCognitionError(
                        "history_preflight_selection_missing")
                if not protocol_record_ids:
                    raise ResidentDevelopmentalCognitionError("history_context_budget_exhausted")
                records = tuple(self.writeback.store.get(rid) for rid in protocol_record_ids)
                if tuple(record.record_digest for record in records) != tuple(record_digests):
                    raise ResidentDevelopmentalCognitionError("history_preflight_digest_mismatch")
                record_set_digest = _digest({"record_ids":list(protocol_record_ids),
                    "record_digests":list(record_digests)})
                budget = LocalModelInvocationBudget(max_input_chars=MAX_RESIDENT_COGNITION_INPUT_CHARS, max_output_chars=4000,
                    max_new_tokens=512, timeout_seconds=30, max_calls_per_correlation=1)
                probe = self.invoker.build_request(purpose=EXPERIMENT_PURPOSE, prompt="protocol-control-probe",
                    caller=PRINCIPAL, correlation_id=f"{tick_id}:developmental-experiment:protocol",
                    budget=budget, upstream_evidence={"control_probe":True}, linkage={"protocol_only":True})
                protocol = make_protocol(snapshot_id=snapshot.snapshot_id, snapshot_digest=snapshot.digest,
                    current_projection_id=current.projection_id, current_projection_digest=current.projection_digest,
                    current_fact_ids=current.fact_ids, record_ids=protocol_record_ids,
                    record_digests=record_digests, record_set_digest=record_set_digest, model_id=probe.model_id,
                    history_selection_digest=preflight_selection.get("selection_digest"),
                    history_available_records_digest=_digest(
                        preflight_selection.get("available_records")),
                    model_artifact_digest=probe.model_artifact_digest,
                    active_model_identity=dict(getattr(probe, "active_model_identity", {})),
                    active_model_identity_digest=_digest(dict(getattr(probe, "active_model_identity", {}))),
                    authority_map_digest=str(getattr(probe, "authority_map_digest", "test-authority-map")),
                    inference_budget=budget.to_dict(), generation_posture={"temperature":0, "hardware_determinism_claimed":False},
                    epistemic_projection_id=prior_epistemic_state.projection_id if prior_epistemic_state else None,
                    epistemic_projection_digest=prior_epistemic_state.projection_digest if prior_epistemic_state else None,
                    epistemic_state_digests=prior_epistemic_state.state_digests if prior_epistemic_state else (),
                    epistemic_evidence_set_digests=prior_epistemic_state.evidence_set_digests if prior_epistemic_state else (),
                    self_model_projection_id=prior_self_model.projection_id if prior_self_model else None,
                    self_model_projection_digest=prior_self_model.projection_digest if prior_self_model else None,
                    self_model_reconciliation_id=prior_self_model.source_reconciliation_id if prior_self_model else None,
                    self_model_reconciliation_digest=prior_self_model.source_reconciliation_digest if prior_self_model else None,
                    self_model_reconciliation_generation=prior_self_model.source_reconciliation_generation if prior_self_model else None,
                    self_model_source_tick=prior_self_model.source_tick if prior_self_model else None,
                    self_model_claim_ids=prior_self_model.selected_claim_ids if prior_self_model else (),
                    self_model_claim_digests=prior_self_model.selected_claim_digests if prior_self_model else (),
                    instruction_template_digest=_digest({"instruction":EXPERIMENT_CONTEXT_INSTRUCTION}),
                    **({"schema_version": OBJECTIVE_HISTORY_SELECTION_SCHEMA,
                        "objective_task_digest": objective_task.public_descriptor()["task_digest"],
                        "objective_task_descriptor": objective_task.public_descriptor()}
                        if objective_task is not None else {
                            "schema_version": HISTORY_SELECTION_SCHEMA}))
                self.experiments.persist_protocol(protocol)  # preregistration precedes the first inference
                objective_plan = (self.experiments.persist_objective_task_plan(
                    protocol, objective_task) if objective_task is not None else None)
                if objective_plan is not None:
                    intent = next((row for row in state["incomplete_ticks"]
                        if row.get("tick_id") == tick_id), None)
                    if intent is None:
                        raise ResidentDevelopmentalCognitionError(
                            "objective_experiment_tick_intent_missing")
                    intent["objective_protocol_id"] = protocol.protocol_id
                    intent["objective_task_plan_digest"] = objective_plan["plan_digest"]
                    self._save_state(state)
                present = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id, projection=prior,
                    with_history=True, condition_id="history_present", purpose=EXPERIMENT_PURPOSE, protocol=protocol,
                    prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state,
                    objective_plan=objective_plan)
                withheld = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id, projection=prior,
                    with_history=False, condition_id="history_withheld", purpose=EXPERIMENT_PURPOSE, protocol=protocol,
                    prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state,
                    objective_plan=objective_plan)
                restored_records = tuple(self.writeback.store.get(rid) for rid in protocol.record_ids)
                if tuple(r.record_digest for r in restored_records) != protocol.record_digests:
                    raise ResidentDevelopmentalCognitionError("restored_history_digest_mismatch")
                restored = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id,
                    projection=prior, with_history=True, condition_id="history_restored",
                    purpose=EXPERIMENT_PURPOSE, protocol=protocol, prior_self_model=prior_self_model,
                    prior_epistemic_state=prior_epistemic_state, objective_plan=objective_plan)
                observations.extend((present, withheld, restored))
                summary = summarize(protocol, observations)
                run_payload: dict[str, Any] = {"protocol":asdict(protocol),
                    "conditions":[asdict(x) for x in observations], "summary":summary,
                    "validity":"valid_controlled_observation", "contamination_reasons":[]}
                if objective_plan is not None:
                    run_payload["contamination_reasons"] = None
                    run_payload["contamination_assessment"] = (
                        objective_task_contamination_assessment(protocol))
                    objective_scores = [self._pending_objective_scores.pop(item.observation_id)
                        for item in observations]
                    run_payload["objective_scores"] = objective_scores
                    run_payload["objective_evaluation"] = summarize_objective_task(
                        objective_plan, objective_scores)
                measurement_id = self.experiments.persist_run(run_payload)

        if objective_only:
            if measurement_id is None:
                raise ResidentDevelopmentalCognitionError("objective_intervention_not_completed")
            assert objective_request_id is not None and objective_request_digest is not None
            state["incomplete_ticks"] = [row for row in state["incomplete_ticks"]
                if row.get("tick_id") != tick_id]
            state["completed_ticks"].append({"tick_id": tick_id,
                "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
                "record_id": None, "receipt_id": None,
                "objective_request_id": objective_request_id,
                "objective_request_digest": objective_request_digest,
                "objective_request_status": "completed",
                "measurement_id": measurement_id})
            self._save_state(state)
            return ResidentDevelopmentalCycleResult("objective_intervention_completed",
                tick_id, snapshot.snapshot_id, prior_record_ids=prior.requested_record_ids,
                cognition_observation_ids=tuple(item.observation_id for item in observations),
                changed_cognition_measurement_id=measurement_id,
                canonical_explicit_user_retention_mutated=False)

        if epistemic_revision_probe:
            state["incomplete_ticks"] = [row for row in state["incomplete_ticks"]
                if row.get("tick_id") != tick_id]
            state["completed_ticks"].append({"tick_id": tick_id,
                "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
                "record_id": None, "receipt_id": None,
                "epistemic_revision_probe": True})
            self._save_state(state)
            return ResidentDevelopmentalCycleResult("epistemic_revision_probe_completed",
                tick_id, snapshot.snapshot_id, prior_record_ids=prior.requested_record_ids,
                cognition_observation_ids=tuple(item.observation_id for item in observations),
                canonical_explicit_user_retention_mutated=False)

        fact_ids = self._select_fact_ids(snapshot, set(state["processed_selection_ids"]))
        if len(set(state["processed_selection_ids"]) | set(fact_ids)) > MAX_RECOVERED_FACT_IDS:
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
        record_id = receipt_id = None
        qualifying_observation = next((item for item in observations
            if item.condition_id == "with-history"), None)
        pending = (self._pending_cognition_candidates.pop(
            qualifying_observation.observation_id, None)
            if qualifying_observation is not None else None)
        candidate = None
        selection = None
        if pending is not None and qualifying_observation is not None:
            source_receipt, source_output_text, lesson_payload = pending
            if current.fact_ids:
                selection = self.writeback.select_evidence(
                    snapshot, fact_ids=current.fact_ids)
            else:
                selection = self.writeback.empty_selection(snapshot_id=snapshot.snapshot_id,
                    snapshot_digest=snapshot.digest)
            candidate = self.writeback.candidate_from_history_conditioned_cognition(
                selection, source_receipt, observation=asdict(qualifying_observation),
                source_output_text=source_output_text, lesson_payload=lesson_payload)
        elif fact_ids:
            selection = self.writeback.select_evidence(snapshot, fact_ids=fact_ids)
            if selection.selection_id not in set(state["processed_selection_ids"]):
                candidate = self.writeback.infer_candidate(
                    selection, invoker=self.invoker,
                    correlation_id=f"{tick_id}:resident_developmental_interpretation")
        if candidate is not None:
            operation_id = f"resident-developmental-writeback:{tick_id}:{candidate.candidate_id}"
            config_digest = self.writeback.admission_configuration_digest(candidate, operation_id=operation_id)
            admission = self.admission_authority.issue_next(
                admission_id_for_sequence=lambda sequence:
                    f"resident-admission-{candidate.candidate_id}-{sequence}",
                capability_id=RESIDENT_DEVELOPMENTAL_WRITEBACK, definition_version=1,
                subsystem_kind="memory_context_reflection", principal_id=PRINCIPAL,
                principal_kind=PRINCIPAL, effects=EFFECTS, subject_id=candidate.candidate_id,
                request_configuration_digest=config_digest,
                provenance=f"configured-resident-control-plane:{tick_id}",
                affirmative_preconditions=RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION.approval_requirements,
            )
            record, writeback_receipt = self.writeback.append(candidate, admission=admission,
                operation_id=operation_id,
                correlation_id=f"{tick_id}:resident-developmental-writeback")
            record_id, receipt_id = record.record_id, writeback_receipt.receipt_id
            # Persist each exact fact-evidence identity so changing the batch
            # bound cannot make an already interpreted fact eligible again.
            state["processed_selection_ids"].extend(fact_ids)
        state["incomplete_ticks"] = [row for row in state["incomplete_ticks"]
                                      if row.get("tick_id") != tick_id]
        state["completed_ticks"].append({"tick_id": tick_id, "snapshot_id": snapshot.snapshot_id,
                                         "snapshot_digest": snapshot.digest, "record_id": record_id,
                                         "receipt_id": receipt_id})
        self._save_state(state)
        return ResidentDevelopmentalCycleResult(
            "completed", tick_id, snapshot.snapshot_id, fact_ids, prior.requested_record_ids,
            record_id, receipt_id, tuple(item.observation_id for item in observations), measurement_id,
        )
