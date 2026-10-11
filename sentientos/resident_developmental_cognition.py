"""One-tick resident composition for bounded developmental history.

The owner has no cadence of its own.  ``sentientosd`` supplies an exact
World-State snapshot and tick identity.  History is non-authoritative context;
it is never canonical explicit-user retention.
"""
from __future__ import annotations

import json
import os
import stat
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, cast

from .codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from .governed_local_model_invocation import (
    LocalModelInvocationBudget, LocalModelInvoker, RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA,
)
from .canonical_memory import sentientos_memory_dir
from .developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore, make_protocol, summarize,
    PURPOSE as EXPERIMENT_PURPOSE,
)
from .local_model_authority import digest_payload
from .private_file_custody import PrivateFileCustodyError, open_private_directory, replace_private_bytes
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
from .world_state_board import WorldStateSnapshot, validate_snapshot


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
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (OverflowError, ValueError):
        return False
    return instant.tzinfo is not None and instant.utcoffset() is not None
from .windows_handle_custody import WindowsHandleCustodyError, read_explicit_file, read_regular_files

CONFIG_ENV = "SENTIENTOS_RESIDENT_DEVELOPMENTAL_COGNITION_CONFIG"
SCHEMA = "sentientos.resident_developmental_cognition:v1"
CONFIG_SCHEMA = "sentientos.resident_developmental_cognition_config:v1"
CONFIG_SCHEMA_V2 = "sentientos.resident_developmental_cognition_config:v2"
COGNITION_OBSERVATION_SCHEMA_V2 = "sentientos.resident_cognition_observation:v2"
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
MAX_FACTS = 16
MAX_HISTORY = 16
MAX_RECOVERED_TICKS = 4096
MAX_RECOVERED_FACT_IDS = 65_536
MAX_COMPOSITION_STATE_BYTES = 16_777_216
MAX_COGNITION_OBSERVATIONS = 12_288
MAX_COGNITION_OBSERVATION_BYTES = 65_536
MAX_COGNITION_OBSERVATION_ROOT_BYTES = 134_217_728
MAX_RESIDENT_COGNITION_CONFIG_BYTES = 65_536
MAX_RESIDENT_COGNITION_INPUT_CHARS = 16_000
MAX_COGNITION_CONCLUSION_BYTES = 4000
class ResidentDevelopmentalCognitionError(ValueError):
    """Fail-closed composition/configuration violation."""


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


def _history_context_packet(record: Mapping[str, Any]) -> dict[str, Any]:
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
    sources = candidate.get("selected_sources", ())
    if isinstance(sources, (list, tuple)):
        packet["source_bindings"] = [
            {key: source.get(key) for key in ("source_id", "kind", "digest")}
            for source in sources[:MAX_FACTS] if isinstance(source, Mapping)
        ]
    provenance = candidate.get("transformation_provenance")
    if isinstance(provenance, Mapping):
        packet["provenance_kind"] = provenance.get("kind")
        lesson = provenance.get("lesson_candidate")
        if isinstance(lesson, Mapping):
            packet["scope"] = lesson.get("scope")
            packet["applicability"] = lesson.get("applicability")
            packet["uncertainty_rationale"] = lesson.get("uncertainty_rationale")
            packet["evidence_dependencies"] = list(lesson.get("evidence_dependencies", ()))[:8]
            packet["possible_contradiction_ids"] = list(
                lesson.get("possible_contradiction_ids", ()))[:8]
    encoded = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > 12_000:
        raise ResidentDevelopmentalCognitionError("developmental_history_context_packet_unbounded")
    return packet


def _bind_history_and_epistemic_context(*, context: Mapping[str, Any],
        records: tuple[Mapping[str, Any], ...],
        projection: EpistemicCognitiveProjection | None
        ) -> tuple[dict[str, Any], dict[str, Any], str, tuple[str, ...], tuple[str, ...]]:
    """Fit whole recent history packets and epistemic packets to one input bound."""
    packets = tuple(_history_context_packet(record) for record in records)
    available = tuple({"record_id": packet["record_id"],
        "record_digest": packet["record_digest"]} for packet in packets)
    for count in range(len(packets), -1, -1):
        selected = packets[len(packets) - count:] if count else ()
        omitted = packets[:len(packets) - count] if count else packets
        selected_refs = tuple({"record_id": packet["record_id"],
            "record_digest": packet["record_digest"]} for packet in selected)
        omitted_refs = tuple({"record_id": packet["record_id"],
            "record_digest": packet["record_digest"]} for packet in omitted)
        selection = {"schema_version": "sentientos.developmental_history_prompt_selection:v1",
            "policy": "most_recent_complete_record_suffix:v1",
            "available_records": list(available), "selected_records": list(selected_refs),
            "omitted_records": list(omitted_refs),
            "omitted_records_digest": _digest(list(omitted_refs)),
            "omission_reason": "inference_input_budget" if omitted else None}
        candidate = {**dict(context), "developmental_history": list(selected),
            "developmental_history_selection": selection}
        try:
            bound, metadata, prompt = _bind_epistemic_context(
                context=candidate, projection=projection)
        except ResidentDevelopmentalCognitionError as exc:
            if str(exc) != "cognition_input_budget_exceeded":
                raise
            continue
        ids = tuple(str(item["record_id"]) for item in selected_refs)
        digests = tuple(str(item["record_digest"]) for item in selected_refs)
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
        metadata = {"epistemic_projection_schema": None,
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
    elif schema == "sentientos.epistemic_cognitive_projection:v2":
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
    schema_version: str = COGNITION_OBSERVATION_SCHEMA_V2
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


class ResidentDevelopmentalCognitionOwner:
    """Perform at most one deterministic developmental composition per call."""

    def __init__(self, *, config: ResidentDevelopmentalCognitionConfig,
                 writeback: ResidentDevelopmentalWritebackController,
                 admission_authority: RuntimeAdmissionAuthority,
                 invoker: LocalModelInvoker,
                 current_sequence: Callable[[], int]) -> None:
        _validate_root_separation(config.history_root, config.state_root,
            config.model_replacement_artifact_root)
        self.config = config
        self.writeback = writeback
        self.admission_authority = admission_authority
        self.invoker = invoker
        self.current_sequence = current_sequence
        self.state_path = config.state_root / "composition_state.json"
        self.observations_root = config.state_root / "cognition_observations"
        self.measurements_root = config.state_root / "changed_cognition_measurements"
        self.experiments = DevelopmentalExperimentStore(config.state_root)
        # Exact output text is held only until its separately admitted candidate
        # is committed in the same tick. It is never written as a cognition receipt.
        self._pending_cognition_candidates: dict[str, tuple[Any, str, Mapping[str, Any]]] = {}

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
                    "epistemic_prompt_digest", "epistemic_consumed_content_digest"))):
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
        processed = set(state["processed_selection_ids"])
        ticks: dict[str, dict[str, Any]] = {}
        for row in state["completed_ticks"]:
            saved_tick = row.get("tick_id")
            if not isinstance(saved_tick, str) or not saved_tick or saved_tick in ticks:
                raise ResidentDevelopmentalCognitionError("composition_tick_identity_ambiguous")
            ticks[saved_tick] = row
        incomplete: dict[str, dict[str, Any]] = {}
        recovery_intent_order: dict[str, int] = {}
        for index, row in enumerate(state["incomplete_ticks"]):
            saved_tick = row.get("tick_id")
            if not isinstance(saved_tick, str) or not saved_tick or saved_tick in incomplete or saved_tick in ticks:
                raise ResidentDevelopmentalCognitionError("composition_tick_identity_ambiguous")
            if row.get("status") == "in_progress":
                recovery_intent_order[saved_tick] = index
                # The durable marker is written before any cognition call. If
                # it is still present on the next owner entry, completion was
                # interrupted; preserve that fact and never retry this tick.
                row["status"] = "interrupted_recovered"
                changed = True
            incomplete[saved_tick] = row
        completed_order = {tick: index for index, tick in enumerate(ticks)}

        recovered = tuple(sorted(recovered, key=lambda item:
            self._recovered_record_order(item[0], completed_order=completed_order,
                recovery_intent_order=recovery_intent_order)))
        recovered_observations = self._recover_observation_ticks(include_records=True)
        for record, receipt in recovered:
            self._verify_recovered_cognition_candidate(record, recovered_observations)
            candidate = record.candidate
            fact_ids = candidate.get("selected_fact_ids", ())
            if not isinstance(fact_ids, (list, tuple)) or any(not isinstance(item, str) for item in fact_ids):
                raise ResidentDevelopmentalCognitionError("recovered_fact_identity_invalid")
            for fact_id in fact_ids:
                if fact_id not in processed:
                    state["processed_selection_ids"].append(fact_id)
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
                state["completed_ticks"].append(checkpoint)
                ticks[recovered_tick] = checkpoint
                changed = True
            elif existing.get("record_id") != record.record_id or existing.get("receipt_id") != receipt.receipt_id:
                raise ResidentDevelopmentalCognitionError("recovered_tick_record_conflict")
            if recovered_tick in incomplete:
                del incomplete[recovered_tick]
                state["incomplete_ticks"] = [row for row in state["incomplete_ticks"]
                    if row.get("tick_id") != recovered_tick]
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
            state["incomplete_ticks"].append(item)
            incomplete[recovered_tick] = item
            changed = True
        if (len(state["processed_selection_ids"]) > MAX_RECOVERED_FACT_IDS
                or len(state["completed_ticks"]) + len(state["incomplete_ticks"]) > MAX_RECOVERED_TICKS):
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
        if changed:
            self._save_state(state)
        return state

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
        contexts_by_tick: dict[str, tuple[set[str], tuple[str, str]]] = {}
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
            semantic_fields = {"epistemic_projection_schema", "epistemic_semantic_status",
                "epistemic_owner_packet_count", "epistemic_consumed_packet_ids",
                "epistemic_consumed_packet_digests", "epistemic_omitted_packets",
                "epistemic_omitted_packets_digest",
                "epistemic_consumed_packets_digest", "epistemic_projection_context_digest",
                "epistemic_prompt_digest", "epistemic_consumed_content_digest", "schema_version"}
            legacy_fields = expected_fields - semantic_fields
            legacy_observation = isinstance(value, dict) and set(value) == legacy_fields
            versioned_observation = (isinstance(value, dict) and set(value) == expected_fields
                and value.get("schema_version") == COGNITION_OBSERVATION_SCHEMA_V2)
            if (not (legacy_observation or versioned_observation)
                    or not isinstance(value.get("tick_id"), str) or not value["tick_id"]
                    or observation_digest != _digest(value)
                    or observation_id != "devcog-" + observation_digest[7:31]
                    or name != observation_id + ".json"):
                raise ResidentDevelopmentalCognitionError("cognition_observation_digest_mismatch")
            if versioned_observation:
                _validate_epistemic_observation_binding(value)
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
            verified_records[observation_id] = {
                **value, "observation_id": observation_id,
                "observation_digest": observation_digest}
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

    def verify_transition_observation(self, *, stage: str, evidence: Mapping[str, Any],
                                     expected_model_identity: Mapping[str, Any],
                                     expected_serving_session: Mapping[str, Any],
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
                or not session_id):
            raise ResidentDevelopmentalCognitionError("transition_serving_session_invalid")
        observation_id = evidence.get("b_observation_id") if stage == "b_epoch_observed" else evidence.get("restored_a_observation_id")
        observation_digest = evidence.get("b_observation_digest") if stage == "b_epoch_observed" else evidence.get("restored_a_observation_digest")
        observation = self.verified_cognition_observation(str(observation_id or ""), str(observation_digest or ""))
        tick_id = evidence.get("b_tick_id") if stage == "b_epoch_observed" else evidence.get("restored_a_tick_id")
        if (not isinstance(tick_id, str) or not tick_id or observation.get("tick_id") != tick_id
                or observation.get("active_model_identity") != dict(expected_model_identity)):
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
                expected_session_binding=session_binding,
                expected_active_model_identity=expected_model_identity)
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
                expected_active_model_identity=expected_model_identity)
            candidate_request = candidate_receipt.get("request")
            if (not isinstance(candidate_request, Mapping)
                    or candidate_receipt.get("status") not in {"admitted_completed", "admitted_simulation"}
                    or candidate_request.get("purpose") != "resident_developmental_interpretation"
                    or candidate_request.get("correlation_id") != tick_id + ":resident-developmental_interpretation"
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

    def _prior_projection(self, state: Mapping[str, Any], tick_id: str) -> DevelopmentalHistoryProjection:
        # Tick identifiers are opaque at this owner boundary. The durable,
        # digest-verified completed-checkpoint sequence establishes which
        # developmental records were committed before this cycle; wall-clock
        # parsing is neither required nor a reliable substitute for that order.
        # The current tick is separately guarded against replay and has not
        # reached completed_ticks while this projection is captured.
        ids = [str(completed["record_id"]) for completed in state["completed_ticks"]
               if completed.get("tick_id") != tick_id and completed.get("record_id")]
        ids = ids[-self.config.max_retrieved_records:]
        return self.writeback.retrieve(ids, limit=self.config.max_retrieved_records)

    def _select_fact_ids(self, snapshot: WorldStateSnapshot, processed: set[str]) -> tuple[str, ...]:
        allowed = set(self.config.allowed_source_kinds)
        source_kinds = {source.source_id: source.kind for source in snapshot.sources}
        candidates = sorted(
            (fact for fact in snapshot.facts if source_kinds.get(fact.source.source_id) in allowed),
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
        chat_process_recovery_lineage = (
            source_kind == "runtime_supervisor"
            and subject_kind == "chat_process_recovery_transition"
            and isinstance(payload.get("chat_process_recovery_transition"), Mapping)
            and payload["chat_process_recovery_transition"].get("phase_evidence_posture")
                == "canonical_installation_custody_and_digest_chain_checked_not_independently_signed"
            and payload["chat_process_recovery_transition"].get("effect_authority") is False
            and payload["chat_process_recovery_transition"].get("inference_performed") is False
            and payload.get("loaded_code_identity_posture") == "not_independently_attested"
            and payload.get("process_identity_scope")
                == "installation_bound_handoff_and_digest_chained_recovery_receipts"
            and payload.get("source_generation_evidence_scope")
                == "source_bundle_handoff_identity_not_loaded_code_attestation"
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
        if observed_running_model_verified or current_software_generation_verified:
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
        facts = sorted((fact for fact in snapshot.facts if source_kinds.get(fact.source.source_id) in allowed),
                       key=lambda fact: self._fact_selection_key(fact, source_kinds[fact.source.source_id]))[:self.config.max_selected_facts]
        selected = (self.writeback.select_evidence(snapshot, fact_ids=tuple(f.fact_id for f in facts))
            if facts else self.writeback.empty_selection(snapshot_id=snapshot.snapshot_id,
                snapshot_digest=snapshot.digest))
        raw = CurrentWorldStateCognitiveProjection(snapshot.snapshot_id, snapshot.digest, selected.facts,
                                                    selected.sources, selected.conflicts,
                                                    tuple(str(x["fact_id"]) for x in selected.facts))
        digest = _digest(raw.semantic_payload())
        return replace(raw, projection_id="current-world-state-" + digest[7:31], projection_digest=digest)

    def _cognize(self, *, snapshot: WorldStateSnapshot, current: CurrentWorldStateCognitiveProjection, tick_id: str,
                  projection: DevelopmentalHistoryProjection, with_history: bool,
                  prior_self_model: CognitiveSelfModelProjection | None = None,
                  prior_epistemic_state: EpistemicCognitiveProjection | None = None,
                  condition_id: str, purpose: str = COGNITION_PURPOSE,
                  protocol: Any | None = None) -> ResidentCognitionObservation:
        records = projection.records if with_history else ()
        record_ids = projection.requested_record_ids if with_history else ()
        record_digests = tuple(str(record["record_digest"]) for record in records)
        qualifies_for_lesson = (
            protocol is None and with_history and purpose == COGNITION_PURPOSE
            and condition_id == "with-history"
        )
        context = {
            "instruction": (EXPERIMENT_CONTEXT_INSTRUCTION if protocol is not None else (
                EXPERIMENT_CONTEXT_INSTRUCTION
                + " Prior context can inform interpretation but does not grant authority."
                + (" For this ordinary history-conditioned call, return one JSON object with "
                   "conclusion and lesson_candidate. A lesson candidate may be null. If present, "
                   "it is only an uncertain, scoped, untrusted proposal; cite exact consumed "
                   "evidence IDs, preserve possible contradictions, and do not assert truth, policy, "
                   "authority, goals, or procedures."
                   if qualifies_for_lesson else ""))),
            "current_evidence": current.semantic_payload(),
            "prior_self_model": asdict(prior_self_model) if prior_self_model is not None else None,
            "prior_epistemic_state": None,
            "developmental_history": [],
            "developmental_history_posture": "historical_interpretation_not_current_truth",
        }
        context, epistemic_metadata, prompt, record_ids, record_digests = (
            _bind_history_and_epistemic_context(context=context, records=records,
                projection=prior_epistemic_state))
        if with_history and not record_ids:
            raise ResidentDevelopmentalCognitionError("history_context_budget_exhausted")
        correlation = f"{tick_id}:resident_developmental_cognition:{condition_id}"
        request = self.invoker.build_request(
            purpose=purpose, prompt=prompt, caller=PRINCIPAL,
            correlation_id=correlation,
            expected_output_format="json" if qualifies_for_lesson else "text",
            budget=LocalModelInvocationBudget(max_input_chars=MAX_RESIDENT_COGNITION_INPUT_CHARS, max_output_chars=4000, max_new_tokens=512,
                                              timeout_seconds=30, max_calls_per_correlation=1),
            structured_output_schema=RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA if qualifies_for_lesson else None,
            upstream_evidence={"snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
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
                                **epistemic_metadata},
            linkage={"condition_group": f"{tick_id}:retrieval-comparison", "condition_id": condition_id,
                     "history_present": with_history},
        )
        request_upstream = getattr(request, "upstream_evidence", None)
        if (not isinstance(request_upstream, Mapping)
                or any(request_upstream.get(key) != value
                    for key, value in epistemic_metadata.items())):
            raise ResidentDevelopmentalCognitionError("cognition_epistemic_request_binding_mismatch")
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
        receipt = self.invoker.invoke(request, persist=True, include_output_in_receipt=False)
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
            "schema_version": COGNITION_OBSERVATION_SCHEMA_V2,
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
            **epistemic_metadata,
        )
        try:
            _publish_store_json(self.observations_root / f"{observation.observation_id}.json",
                asdict(observation), collision_error="cognition_observation_identity_collision")
        except DevelopmentalWritebackError as exc:
            raise ResidentDevelopmentalCognitionError(
                "cognition_observation_publication_failed") from exc
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
        if not self.config.enabled:
            return ResidentDevelopmentalCycleResult("disabled", tick_id, snapshot.snapshot_id)
        if os.name != "posix":
            return self._run_tick_locked(snapshot=snapshot, tick_id=tick_id,
                prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state)
        with self._composition_lock():
            return self._run_tick_locked(snapshot=snapshot, tick_id=tick_id,
                prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state)

    def _run_tick_locked(self, *, snapshot: WorldStateSnapshot, tick_id: str,
                 prior_self_model: CognitiveSelfModelProjection | None = None,
                 prior_epistemic_state: EpistemicCognitiveProjection | None = None) -> ResidentDevelopmentalCycleResult:
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
        state = self._state()
        if (any(row.get("tick_id") == tick_id for row in state["completed_ticks"])
                or any(row.get("tick_id") == tick_id for row in state["incomplete_ticks"])):
            raise ResidentDevelopmentalCognitionError("tick_already_completed")
        if len(state["completed_ticks"]) + len(state["incomplete_ticks"]) >= MAX_RECOVERED_TICKS:
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")

        # Publish the exact snapshot/tick intent before any local-model call.
        # A crash before the first durable cognition observation must remain
        # distinguishable from a tick that never began, and the same tick may
        # not be replayed after restart. A future tick can continue normally.
        state["incomplete_ticks"].append({"tick_id": tick_id,
            "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
            "status": "in_progress"})
        self._save_state(state)

        # Capture prior history before any candidate from this tick can exist.
        prior = self._prior_projection(state, tick_id)
        current = self._current_projection(snapshot)
        observations: list[ResidentCognitionObservation] = []
        measurement_id: str | None = None
        has_developmental_history = bool(prior.requested_record_ids)
        has_prior_self_model = prior_self_model is not None
        has_prior_epistemic_state = prior_epistemic_state is not None
        should_cognize = (has_developmental_history or has_prior_self_model
                          or has_prior_epistemic_state)
        should_run_history_comparison = (self.config.comparison_enabled
                                         and has_developmental_history)
        if should_cognize:
            if not should_run_history_comparison:
                observations.append(self._cognize(snapshot=snapshot, current=current, tick_id=tick_id,
                                    projection=prior, with_history=has_developmental_history,
                                    condition_id="with-history" if has_developmental_history else "prior-context",
                                    prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state))
            else:
                records = tuple(self.writeback.store.get(rid) for rid in prior.requested_record_ids)
                record_digests = tuple(r.record_digest for r in records)
                record_set_digest = _digest({"record_ids":list(prior.requested_record_ids), "record_digests":list(record_digests)})
                budget = LocalModelInvocationBudget(max_input_chars=16000, max_output_chars=4000,
                    max_new_tokens=512, timeout_seconds=30, max_calls_per_correlation=1)
                probe = self.invoker.build_request(purpose=EXPERIMENT_PURPOSE, prompt="protocol-control-probe",
                    caller=PRINCIPAL, correlation_id=f"{tick_id}:developmental-experiment:protocol",
                    budget=budget, upstream_evidence={"control_probe":True}, linkage={"protocol_only":True})
                protocol = make_protocol(snapshot_id=snapshot.snapshot_id, snapshot_digest=snapshot.digest,
                    current_projection_id=current.projection_id, current_projection_digest=current.projection_digest,
                    current_fact_ids=current.fact_ids, record_ids=prior.requested_record_ids,
                    record_digests=record_digests, record_set_digest=record_set_digest, model_id=probe.model_id,
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
                    instruction_template_digest=_digest({"instruction":EXPERIMENT_CONTEXT_INSTRUCTION}))
                self.experiments.persist_protocol(protocol)  # preregistration precedes the first inference
                present = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id, projection=prior,
                    with_history=True, condition_id="history_present", purpose=EXPERIMENT_PURPOSE, protocol=protocol,
                    prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state)
                withheld = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id, projection=prior,
                    with_history=False, condition_id="history_withheld", purpose=EXPERIMENT_PURPOSE, protocol=protocol,
                    prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state)
                restored_records = tuple(self.writeback.store.get(rid) for rid in protocol.record_ids)
                if tuple(r.record_digest for r in restored_records) != protocol.record_digests:
                    raise ResidentDevelopmentalCognitionError("restored_history_digest_mismatch")
                restored_projection = self.writeback.retrieve(protocol.record_ids, limit=self.config.max_retrieved_records)
                restored = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id,
                    projection=restored_projection, with_history=True, condition_id="history_restored",
                    purpose=EXPERIMENT_PURPOSE, protocol=protocol, prior_self_model=prior_self_model,
                    prior_epistemic_state=prior_epistemic_state)
                observations.extend((present, withheld, restored))
                summary = summarize(protocol, observations)
                measurement_id = self.experiments.persist_run({"protocol":asdict(protocol),
                    "conditions":[asdict(x) for x in observations], "summary":summary,
                    "validity":"valid_controlled_observation", "contamination_reasons":[]})

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
