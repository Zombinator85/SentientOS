"""Durable, model-independent epistemic positions over explicit propositions.

Evidence is not belief, belief is not truth, and belief is not authority.  This
module owns records; a cognitive worker may only submit a candidate.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from .platform_fcntl import fcntl, require_flock
from .private_file_custody import (
    PrivateFileCustodyError, list_bounded_json_names_at, open_private_directory,
    publish_immutable_bytes, read_private_file_at,
)
from .windows_handle_custody import WindowsHandleCustodyError, read_regular_files

PROPOSITION_SCHEMA = "sentientos.epistemic_proposition:v1"
BINDING_SCHEMA = "sentientos.epistemic_evidence_binding:v1"
STATE_SCHEMA = "sentientos.epistemic_state:v1"
UPDATE_SCHEMA = "sentientos.epistemic_update_event:v1"
CANDIDATE_SCHEMA = "sentientos.epistemic_update_candidate:v2"
LEGACY_CANDIDATE_SCHEMA = "sentientos.epistemic_update_candidate:v1"
CALIBRATION_SCHEMA = "sentientos.epistemic_calibration_event:v1"
COGNITIVE_PROJECTION_SCHEMA_V2 = "sentientos.epistemic_cognitive_projection:v2"
COGNITIVE_PROJECTION_SCHEMA_V3 = "sentientos.epistemic_cognitive_projection:v3"
COGNITIVE_PACKET_SCHEMA = "sentientos.epistemic_cognitive_packet:v1"
MAX_COGNITIVE_PROJECTION_STATES = 128
MAX_COGNITIVE_PROJECTION_OMISSIONS = 16_384
PROPOSITION_CLASSES = frozenset({"descriptive", "predictive", "causal_hypothesis", "capability", "environmental", "relational", "system_hypothesis"})
RELATIONS = frozenset({"refines", "narrows", "broadens", "supersedes", "contradicts", "related_to"})
EVIDENCE_RELATIONS = frozenset({"supports", "contradicts", "undercuts", "contextualizes", "resolves", "predictive_outcome", "reliability_evidence"})
DEPENDENCIES = frozenset({"same_source_derivation", "shared_upstream_evidence", "repeated_observation", "independently_sourced_observation", "duplicate_alias", "unknown_dependency"})
STANCES = frozenset({"unknown", "suspended", "provisionally_supported", "supported", "contested", "provisionally_contradicted", "contradicted", "superseded"})
UPDATE_REASONS = frozenset({"initialization", "new_evidence", "evidence_withdrawal", "contradiction_arrival", "duplicate_evidence_correction", "dependency_correction", "source_reliability_revision", "proposition_refinement", "update_rule_correction", "calibration_outcome", "operator_error_correction"})
FALSE_AUTHORITY = {"policy": False, "goal": False, "permission": False, "effect_admission": False, "adoption": False, "memory_retention": False, "truth_oracle": False}
RECORD_COLLECTIONS = frozenset({"propositions", "bindings", "states", "updates", "relations", "calibrations", "transactions"})
MAX_EPISTEMIC_RECORD_BYTES = 1_048_576
MAX_EPISTEMIC_RECORDS_PER_COLLECTION = 65_536
MAX_EPISTEMIC_COLLECTION_BYTES = 67_108_864
MAX_EPISTEMIC_COGNITIVE_PROJECTION_BYTES = 4_194_304


class EpistemicStateError(ValueError):
    """Fail-closed identity, history, or admission error."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _identity(prefix: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    dg = digest(payload)
    return f"{prefix}:{dg[7:31]}", dg


def _valid_identity(value: Any, prefix: str) -> bool:
    marker = prefix + ":"
    return (isinstance(value, str) and len(value) == len(marker) + 24
            and value.startswith(marker)
            and all(character in "0123456789abcdef" for character in value[len(marker):]))


def _authority(value: Mapping[str, bool]) -> None:
    if dict(value) != FALSE_AUTHORITY:
        raise EpistemicStateError("epistemic_authority_must_be_all_false")


@dataclass(frozen=True)
class EpistemicProposition:
    proposition_id: str; proposition_digest: str; namespace: str; subject: str; predicate: str
    object_value: Any; polarity: str; qualifiers: Mapping[str, Any]; temporal_scope: Mapping[str, Any]
    context_scope: Mapping[str, Any]; proposition_class: str; statement: str | None = None
    schema_version: str = PROPOSITION_SCHEMA

    def semantic_key(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "namespace": self.namespace, "subject": self.subject,
                "predicate": self.predicate, "object_value": self.object_value, "polarity": self.polarity,
                "qualifiers": self.qualifiers, "temporal_scope": self.temporal_scope,
                "context_scope": self.context_scope, "proposition_class": self.proposition_class}


def make_proposition(**kwargs: Any) -> EpistemicProposition:
    raw = EpistemicProposition("", "", **kwargs)
    if raw.proposition_class not in PROPOSITION_CLASSES or raw.polarity not in {"positive", "negative"} or not all((raw.namespace, raw.subject, raw.predicate)):
        raise EpistemicStateError("proposition_shape_invalid")
    pid, dg = _identity("proposition", raw.semantic_key())
    return replace(raw, proposition_id=pid, proposition_digest=dg)


@dataclass(frozen=True)
class PropositionRelation:
    source_proposition_id: str; target_proposition_id: str; relation: str; recorded_at: str


@dataclass(frozen=True)
class EvidenceBinding:
    binding_id: str; binding_digest: str; proposition_id: str; source_artifact_id: str
    source_digest: str; source_schema: str; source_class: str; observation_time: str
    evidence_relation: str; dependency_kind: str; dependency_group: str | None
    upstream_binding_ids: tuple[str, ...]; freshness: str; reliability_posture: str
    withdrawn: bool = False; superseded_by: str | None = None; authority: Mapping[str, bool] = None  # type: ignore[assignment]
    schema_version: str = BINDING_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("binding_id"); value.pop("binding_digest"); return value


def make_evidence_binding(**kwargs: Any) -> EvidenceBinding:
    kwargs.setdefault("authority", dict(FALSE_AUTHORITY))
    raw = EvidenceBinding("", "", **kwargs)
    if raw.evidence_relation not in EVIDENCE_RELATIONS or raw.dependency_kind not in DEPENDENCIES or raw.freshness not in {"current", "stale", "unknown"}:
        raise EpistemicStateError("evidence_binding_shape_invalid")
    if (not isinstance(raw.upstream_binding_ids, (list, tuple))
            or any(not _valid_identity(item, "evidence") for item in raw.upstream_binding_ids)
            or len(raw.upstream_binding_ids) != len(set(raw.upstream_binding_ids))
            or raw.binding_id in raw.upstream_binding_ids):
        raise EpistemicStateError("evidence_binding_upstream_shape_invalid")
    if (raw.dependency_kind in {"same_source_derivation", "shared_upstream_evidence", "duplicate_alias"}
            and not raw.upstream_binding_ids):
        raise EpistemicStateError("evidence_dependency_missing_upstream")
    _authority(raw.authority)
    bid, dg = _identity("evidence", raw.payload())
    return replace(raw, binding_id=bid, binding_digest=dg)


def evidence_posture(bindings: Sequence[EvidenceBinding]) -> Mapping[str, Any]:
    active = [b for b in bindings if not b.withdrawn]
    support = [b for b in active if b.evidence_relation == "supports" or (b.evidence_relation == "predictive_outcome" and b.reliability_posture == "supports")]
    contradiction = [b for b in active if b.evidence_relation == "contradicts" or (b.evidence_relation == "predictive_outcome" and b.reliability_posture == "contradicts")]
    if not active: posture = "evidence_withdrawn" if bindings else "no_evidence"
    elif all(b.freshness == "stale" for b in active): posture = "all_evidence_stale"
    elif support and contradiction: posture = "mixed"
    elif support: posture = "support_only"
    elif contradiction: posture = "contradiction_only"
    else: posture = "context_only"
    unresolved = any(b.dependency_kind == "unknown_dependency" for b in active)
    independent = {b.dependency_group or b.binding_id for b in active if b.dependency_kind == "independently_sourced_observation"}
    return {"posture": posture, "dependency_unresolved": unresolved,
            "insufficient_independent_evidence": len(independent) < 2, "record_count": len(bindings),
            "active_count": len(active), "independent_group_count": len(independent)}


@dataclass(frozen=True)
class EpistemicState:
    state_id: str; state_digest: str; proposition_id: str; generation: int
    predecessor_state_digest: str | None; stance: str; confidence: Mapping[str, Any] | None
    evidence_set_digest: str; support_binding_ids: tuple[str, ...]; contradiction_binding_ids: tuple[str, ...]
    dependency_unresolved: bool; freshness: str; last_update_event_id: str | None
    update_rule_id: str; created_at: str; updated_at: str; authority: Mapping[str, bool]
    schema_version: str = STATE_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("state_id"); value.pop("state_digest"); return value


@dataclass(frozen=True)
class EpistemicCognitiveProjection:
    """Prior-only fourth substrate; never a World-State fact."""
    projection_id: str; projection_digest: str; source_tick: int
    proposition_ids: tuple[str, ...]; state_ids: tuple[str, ...]
    state_digests: tuple[str, ...]; generations: tuple[int, ...]
    evidence_set_digests: tuple[str, ...]; states: tuple[Mapping[str, Any], ...]
    evidence_only: bool = False; prior_position_only: bool = True
    current_truth: bool = False; authority: bool = False; policy: bool = False; goal: bool = False


@dataclass(frozen=True)
class MeaningBearingEpistemicCognitiveProjection(EpistemicCognitiveProjection):
    """Versioned prior projection with canonical definitions and evidence joins."""
    schema_version: str = COGNITIVE_PROJECTION_SCHEMA_V2
    current_tick: int = 0
    propositions: tuple[Mapping[str, Any], ...] = ()
    active_evidence_bindings: tuple[tuple[Mapping[str, Any], ...], ...] = ()
    removed_evidence_bindings: tuple[tuple[Mapping[str, Any], ...], ...] = ()
    update_events: tuple[tuple[Mapping[str, Any], ...], ...] = ()
    omission_manifest: Mapping[str, Any] | None = None


def make_cognitive_projection(states: Sequence[EpistemicState], *, source_tick: int, current_tick: int,
                              propositions: Sequence[Mapping[str, Any]] | None = None,
                              active_evidence_bindings: Sequence[Sequence[Mapping[str, Any]]] | None = None,
                              removed_evidence_bindings: Sequence[Sequence[Mapping[str, Any]]] | None = None,
                              update_events: Sequence[Sequence[Mapping[str, Any]]] | None = None,
                              omission_manifest: Mapping[str, Any] | None = None,
                              ) -> EpistemicCognitiveProjection:
    if source_tick >= current_tick: raise EpistemicStateError("same_tick_epistemic_state_forbidden")
    ordered=tuple(sorted(states,key=lambda x:x.proposition_id)); payload={"source_tick":source_tick,
        "proposition_ids":tuple(x.proposition_id for x in ordered),"state_ids":tuple(x.state_id for x in ordered),
        "state_digests":tuple(x.state_digest for x in ordered),"generations":tuple(x.generation for x in ordered),
        "evidence_set_digests":tuple(x.evidence_set_digest for x in ordered),"states":tuple(asdict(x) for x in ordered),
        "evidence_only":False,"prior_position_only":True,"current_truth":False,"authority":False,"policy":False,"goal":False}
    pid,pdg=_identity("epistemic-projection",payload)
    proposition_ids = tuple(x.proposition_id for x in ordered)
    state_ids = tuple(x.state_id for x in ordered)
    state_digests = tuple(x.state_digest for x in ordered)
    generations = tuple(x.generation for x in ordered)
    evidence_set_digests = tuple(x.evidence_set_digest for x in ordered)
    state_rows: tuple[Mapping[str, Any], ...] = tuple(asdict(x) for x in ordered)
    if all(value is None for value in (propositions, active_evidence_bindings,
            removed_evidence_bindings, update_events)):
        return EpistemicCognitiveProjection(projection_id=pid, projection_digest=pdg,
            source_tick=source_tick, proposition_ids=proposition_ids,
            state_ids=state_ids, state_digests=state_digests,
            generations=generations, evidence_set_digests=evidence_set_digests,
            states=state_rows)
    if any(value is None for value in (propositions, active_evidence_bindings,
            removed_evidence_bindings, update_events)):
        raise EpistemicStateError("epistemic_semantic_projection_incomplete")
    semantic_rows = tuple(dict(item) for item in propositions or ())
    active_rows = tuple(tuple(dict(item) for item in rows)
        for rows in active_evidence_bindings or ())
    removed_rows = tuple(tuple(dict(item) for item in rows)
        for rows in removed_evidence_bindings or ())
    event_rows = tuple(tuple(dict(item) for item in rows) for rows in update_events or ())
    if any(len(rows) != len(ordered) for rows in
            (semantic_rows, active_rows, removed_rows, event_rows)):
        raise EpistemicStateError("epistemic_semantic_projection_pairing_invalid")
    schema = (COGNITIVE_PROJECTION_SCHEMA_V3 if omission_manifest is not None
        else COGNITIVE_PROJECTION_SCHEMA_V2)
    semantic_payload = {**payload, "schema_version": schema,
        "current_tick": current_tick, "propositions": semantic_rows,
        "active_evidence_bindings": active_rows,
        "removed_evidence_bindings": removed_rows, "update_events": event_rows}
    if omission_manifest is not None:
        semantic_payload["omission_manifest"] = dict(omission_manifest)
    if len(canonical_bytes(semantic_payload)) > MAX_EPISTEMIC_COGNITIVE_PROJECTION_BYTES:
        raise EpistemicStateError("epistemic_projection_size_limit_exceeded")
    semantic_id, semantic_digest = _identity("epistemic-projection", semantic_payload)
    projection = MeaningBearingEpistemicCognitiveProjection(
        projection_id=semantic_id, projection_digest=semantic_digest, source_tick=source_tick,
        proposition_ids=proposition_ids, state_ids=state_ids,
        state_digests=state_digests, generations=generations,
        evidence_set_digests=evidence_set_digests, states=state_rows,
        current_tick=current_tick, propositions=semantic_rows,
        active_evidence_bindings=active_rows, removed_evidence_bindings=removed_rows,
        update_events=event_rows, schema_version=schema,
        omission_manifest=(dict(omission_manifest) if omission_manifest is not None else None))
    validate_cognitive_projection(projection, require_meaning=True)
    return projection


def _normalize_state_record(raw: Mapping[str, Any]) -> EpistemicState:
    value = dict(raw)
    value["support_binding_ids"] = tuple(value["support_binding_ids"])
    value["contradiction_binding_ids"] = tuple(value["contradiction_binding_ids"])
    return EpistemicState(**value)


def _normalize_binding_record(raw: Mapping[str, Any]) -> EvidenceBinding:
    value = dict(raw)
    value["upstream_binding_ids"] = tuple(value["upstream_binding_ids"])
    return EvidenceBinding(**value)


def _normalize_update_record(raw: Mapping[str, Any]) -> EpistemicUpdateEvent:
    value = dict(raw)
    value["added_binding_ids"] = tuple(value["added_binding_ids"])
    value["removed_binding_ids"] = tuple(value["removed_binding_ids"])
    return EpistemicUpdateEvent(**value)


def validate_cognitive_projection(projection: EpistemicCognitiveProjection | Mapping[str, Any], *,
                                  require_meaning: bool = False) -> None:
    """Verify projection identity and every canonical position/evidence join."""
    raw = asdict(projection) if not isinstance(projection, Mapping) else dict(projection)
    try:
        if len(canonical_bytes(raw)) > MAX_EPISTEMIC_COGNITIVE_PROJECTION_BYTES + 4096:
            raise EpistemicStateError("epistemic_projection_size_limit_exceeded")
    except (TypeError, ValueError) as exc:
        raise EpistemicStateError("epistemic_projection_shape_invalid") from exc
    schema = raw.get("schema_version")
    legacy_payload = {"source_tick": raw.get("source_tick"),
        "proposition_ids": raw.get("proposition_ids"), "state_ids": raw.get("state_ids"),
        "state_digests": raw.get("state_digests"), "generations": raw.get("generations"),
        "evidence_set_digests": raw.get("evidence_set_digests"), "states": raw.get("states"),
        "evidence_only": False, "prior_position_only": True, "current_truth": False,
        "authority": False, "policy": False, "goal": False}
    if schema is None:
        if require_meaning:
            raise EpistemicStateError("epistemic_semantic_projection_required")
        calculated = _identity("epistemic-projection", legacy_payload)
        if (raw.get("projection_id") != calculated[0]
                or raw.get("projection_digest") != calculated[1]):
            raise EpistemicStateError("epistemic_projection_identity_mismatch")
        states = raw.get("states")
        ids = raw.get("proposition_ids")
        if not isinstance(states, (list, tuple)) or not isinstance(ids, (list, tuple)):
            raise EpistemicStateError("epistemic_projection_shape_invalid")
        normalized = tuple(_normalize_state_record(item) for item in states)
        if (tuple(ids) != tuple(item.proposition_id for item in normalized)
                or len(set(ids)) != len(ids)
                or tuple(raw.get("state_ids", ())) != tuple(item.state_id for item in normalized)
                or tuple(raw.get("state_digests", ())) != tuple(item.state_digest for item in normalized)
                or tuple(raw.get("generations", ())) != tuple(item.generation for item in normalized)
                or tuple(raw.get("evidence_set_digests", ())) != tuple(
                    item.evidence_set_digest for item in normalized)
                or raw.get("evidence_only") is not False
                or raw.get("prior_position_only") is not True
                or raw.get("current_truth") is not False
                or any(raw.get(key) is not False for key in ("authority", "policy", "goal"))):
            raise EpistemicStateError("epistemic_projection_pairing_ambiguous")
        for state in normalized:
            if (dict(state.authority) != FALSE_AUTHORITY
                    or _identity("epistemic-state", state.payload()) !=
                        (state.state_id, state.state_digest)):
                raise EpistemicStateError("epistemic_state_digest_mismatch")
        return
    if schema not in {COGNITIVE_PROJECTION_SCHEMA_V2, COGNITIVE_PROJECTION_SCHEMA_V3}:
        raise EpistemicStateError("epistemic_projection_schema_unsupported")
    omission_manifest = raw.get("omission_manifest")
    if schema == COGNITIVE_PROJECTION_SCHEMA_V2 and omission_manifest is not None:
        raise EpistemicStateError("epistemic_projection_omission_manifest_unexpected")
    states_raw = raw.get("states")
    props_raw = raw.get("propositions")
    active_raw = raw.get("active_evidence_bindings")
    removed_raw = raw.get("removed_evidence_bindings")
    events_raw = raw.get("update_events")
    if (not all(isinstance(value, (list, tuple)) for value in
                (states_raw, props_raw, active_raw, removed_raw, events_raw))):
        raise EpistemicStateError("epistemic_semantic_projection_shape_invalid")
    assert isinstance(states_raw, (list, tuple))
    assert isinstance(props_raw, (list, tuple))
    assert isinstance(active_raw, (list, tuple))
    assert isinstance(removed_raw, (list, tuple))
    assert isinstance(events_raw, (list, tuple))
    if (type(raw.get("current_tick")) is not int or type(raw.get("source_tick")) is not int
            or raw["source_tick"] >= raw["current_tick"]
            or len(states_raw) > MAX_COGNITIVE_PROJECTION_STATES or not states_raw
            or any(len(value) != len(states_raw) for value in
                (props_raw, active_raw, removed_raw, events_raw))):
        raise EpistemicStateError("epistemic_semantic_projection_shape_invalid")
    if (any(not isinstance(row, (list, tuple)) or not row for row in events_raw)
            or sum(len(row) for row in events_raw) > MAX_EPISTEMIC_RECORDS_PER_COLLECTION):
        raise EpistemicStateError("epistemic_semantic_event_history_bound_invalid")
    normalized_states = tuple(_normalize_state_record(item) for item in states_raw)
    if tuple(item.proposition_id for item in normalized_states) != tuple(raw.get("proposition_ids", ())):
        raise EpistemicStateError("epistemic_projection_pairing_ambiguous")
    if len({item.proposition_id for item in normalized_states}) != len(normalized_states):
        raise EpistemicStateError("epistemic_projection_pairing_ambiguous")
    if schema == COGNITIVE_PROJECTION_SCHEMA_V3:
        required_manifest_fields = {"schema_version", "selection_policy",
            "selection_limit", "available_prior_state_count", "selected_state_count",
            "omitted_state_count", "omitted_identity_digest", "omitted_state_identities"}
        if (not isinstance(omission_manifest, Mapping)
                or set(omission_manifest) != required_manifest_fields
                or omission_manifest.get("schema_version") !=
                    "sentientos.epistemic_projection_omission_manifest:v1"
                or omission_manifest.get("selection_policy") !=
                    "latest_prior_state_by_proposition_id_ascending"
                or type(omission_manifest.get("selection_limit")) is not int
                or not 1 <= omission_manifest["selection_limit"] <=
                    MAX_COGNITIVE_PROJECTION_STATES
                or type(omission_manifest.get("available_prior_state_count")) is not int
                or omission_manifest["available_prior_state_count"] < len(normalized_states)
                or type(omission_manifest.get("selected_state_count")) is not int
                or omission_manifest["selected_state_count"] != len(normalized_states)
                or type(omission_manifest.get("omitted_state_count")) is not int
                or omission_manifest["omitted_state_count"] < 1
                or not isinstance(omission_manifest.get("omitted_state_identities"), (list, tuple))):
            raise EpistemicStateError("epistemic_projection_omission_manifest_invalid")
        omitted_rows = tuple(omission_manifest["omitted_state_identities"])
        if (len(omitted_rows) != omission_manifest["omitted_state_count"]
                or len(omitted_rows) > MAX_COGNITIVE_PROJECTION_OMISSIONS
                or omission_manifest["available_prior_state_count"] !=
                    len(normalized_states) + len(omitted_rows)
                or len(normalized_states) != min(omission_manifest["selection_limit"],
                    omission_manifest["available_prior_state_count"])):
            raise EpistemicStateError("epistemic_projection_omission_manifest_count_invalid")
        omitted_ids: list[str] = []
        for row in omitted_rows:
            expected_fields = {"proposition_id", "state_id", "state_digest", "generation",
                "update_event_id", "update_tick", "stance", "dependency_unresolved",
                "freshness", "updated_at", "omission_reason"}
            if (not isinstance(row, Mapping) or set(row) != expected_fields
                    or not _valid_identity(row.get("proposition_id"), "proposition")
                    or not _valid_identity(row.get("state_id"), "epistemic-state")
                    or not isinstance(row.get("state_digest"), str)
                    or len(row["state_digest"]) != 71
                    or not row["state_digest"].startswith("sha256:")
                    or any(character not in "0123456789abcdef" for character in row["state_digest"][7:])
                    or type(row.get("generation")) is not int or row["generation"] < 0
                    or not _valid_identity(row.get("update_event_id"), "epistemic-update")
                    or type(row.get("update_tick")) is not int or row["update_tick"] < 0
                    or row["update_tick"] >= raw.get("current_tick", 0)
                    or row.get("stance") not in STANCES
                    or type(row.get("dependency_unresolved")) is not bool
                    or row.get("freshness") not in {"current", "stale", "unknown"}
                    or not isinstance(row.get("updated_at"), str)
                    or row.get("omission_reason") != "projection_state_bound"):
                raise EpistemicStateError("epistemic_projection_omitted_state_identity_invalid")
            PersistentEpistemicStateOwner.validate_update_timestamp(
                tick=row["update_tick"], recorded_at=row["updated_at"])
            omitted_ids.append(str(row["proposition_id"]))
        if (omitted_ids != sorted(omitted_ids)
                or len(omitted_ids) != len(set(omitted_ids))
                or set(omitted_ids) & {item.proposition_id for item in normalized_states}
                or tuple(item.proposition_id for item in normalized_states) != tuple(
                    sorted([item.proposition_id for item in normalized_states] + omitted_ids)[
                        :omission_manifest["selection_limit"]])
                or tuple(omitted_ids) != tuple(sorted(
                    [item.proposition_id for item in normalized_states] + omitted_ids)[
                        omission_manifest["selection_limit"]:])
                or omission_manifest.get("omitted_identity_digest") != digest(list(omitted_rows))):
            raise EpistemicStateError("epistemic_projection_omission_identity_mismatch")
    elif omission_manifest is not None:
        raise EpistemicStateError("epistemic_projection_omission_manifest_unexpected")
    event_ticks: list[int] = []
    for i, (state, proposition_raw, active_values, removed_values, event_history_raw) in enumerate(
            zip(normalized_states, props_raw, active_raw, removed_raw, events_raw)):
        proposition = EpistemicProposition(**dict(proposition_raw))
        expected_proposition = make_proposition(**{key: value for key, value in
            asdict(proposition).items() if key not in {"proposition_id", "proposition_digest", "schema_version"}})
        if (proposition != expected_proposition or proposition.proposition_id != state.proposition_id
                or dict(state.authority) != FALSE_AUTHORITY
                or raw["state_ids"][i] != state.state_id
                or raw["state_digests"][i] != state.state_digest
                or raw["generations"][i] != state.generation
                or raw["evidence_set_digests"][i] != state.evidence_set_digest):
            raise EpistemicStateError("epistemic_semantic_proposition_state_join_invalid")
        state_id, state_digest = _identity("epistemic-state", state.payload())
        if (state_id, state_digest) != (state.state_id, state.state_digest):
            raise EpistemicStateError("epistemic_state_digest_mismatch")
        active = tuple(_normalize_binding_record(item) for item in active_values)
        removed = tuple(_normalize_binding_record(item) for item in removed_values)
        for binding in (*active, *removed):
            expected_binding = make_evidence_binding(**{key: value for key, value in
                asdict(binding).items() if key not in {"binding_id", "binding_digest", "schema_version"}})
            if binding != expected_binding or binding.proposition_id != state.proposition_id:
                raise EpistemicStateError("epistemic_semantic_evidence_join_invalid")
        all_binding_rows: dict[str, EvidenceBinding] = {}
        for binding in (*active, *removed):
            existing = all_binding_rows.get(binding.binding_id)
            if existing is not None and existing != binding:
                raise EpistemicStateError("epistemic_semantic_evidence_identity_conflict")
            all_binding_rows[binding.binding_id] = binding
        active_ids = tuple(sorted(binding.binding_id for binding in active))
        if len(active_ids) != len(set(active_ids)):
            raise EpistemicStateError("epistemic_semantic_evidence_posture_mismatch")
        events = tuple(_normalize_update_record(item) for item in event_history_raw)
        if (len(events) != state.generation + 1 or state.update_rule_id == ""
                or not state.created_at or not state.updated_at):
            raise EpistemicStateError("epistemic_semantic_state_scope_invalid")
        reconstructed_active: set[str] = set()
        historically_removed: set[str] = set()
        predecessor_digest: str | None = None
        for generation, event in enumerate(events):
            event_ticks.append(event.tick)
            event_id, event_digest = _identity("epistemic-update", event.identity_payload())
            added, removed_ids = set(event.added_binding_ids), set(event.removed_binding_ids)
            if (event.event_id != event_id or event.event_digest != event_digest
                    or dict(event.authority) != FALSE_AUTHORITY
                    or event.proposition_id != state.proposition_id
                    or event.generation != generation
                    or event.prior_state_digest != predecessor_digest
                    or event.tick >= raw["current_tick"]
                    or event.tick > raw["source_tick"]
                    or added & removed_ids or added & reconstructed_active
                    or not removed_ids <= reconstructed_active
                    or not (added | removed_ids) <= set(all_binding_rows)
                    or (event.update_rule_revision is not None
                        and not isinstance(event.update_rule_revision, str))):
                raise EpistemicStateError("epistemic_semantic_update_join_invalid")
            reconstructed_active.difference_update(removed_ids)
            reconstructed_active.update(added)
            historically_removed.update(removed_ids)
            predecessor_digest = event.successor_state_digest
        event = events[-1]
        active_freshness = {binding.freshness for binding in active if not binding.withdrawn}
        expected_freshness = ("current" if "current" in active_freshness else
            "stale" if "stale" in active_freshness else "unknown")
        if (digest(sorted(reconstructed_active)) != state.evidence_set_digest
                or tuple(sorted(reconstructed_active)) != active_ids
                or tuple(sorted(historically_removed)) != tuple(sorted(
                    binding.binding_id for binding in removed))
                or tuple(sorted(state.support_binding_ids)) != tuple(sorted(
                    binding.binding_id for binding in active if binding.evidence_relation == "supports"
                    or binding.reliability_posture == "supports"))
                or tuple(sorted(state.contradiction_binding_ids)) != tuple(sorted(
                    binding.binding_id for binding in active if binding.evidence_relation == "contradicts"
                    or binding.reliability_posture == "contradicts"))
                or state.dependency_unresolved != any(binding.dependency_kind == "unknown_dependency"
                    for binding in active)
                or state.freshness != expected_freshness
                or event.successor_state_digest != state.state_digest
                or event.prior_state_digest != state.predecessor_state_digest
                or state.last_update_event_id != event.event_id):
            raise EpistemicStateError("epistemic_semantic_evidence_posture_mismatch")
        PersistentEpistemicStateOwner.validate_update_timestamp(
            tick=event.tick, recorded_at=state.updated_at)
    source_ticks = list(event_ticks)
    if schema == COGNITIVE_PROJECTION_SCHEMA_V3:
        source_ticks.extend(row["update_tick"] for row in
            omission_manifest["omitted_state_identities"])
    if max(source_ticks) != raw["source_tick"]:
        raise EpistemicStateError("epistemic_semantic_source_tick_mismatch")
    if (raw.get("evidence_only") is not False or raw.get("prior_position_only") is not True
            or raw.get("current_truth") is not False
            or any(raw.get(key) is not False for key in ("authority", "policy", "goal"))):
        raise EpistemicStateError("epistemic_projection_authority_invalid")
    payload = {key: raw[key] for key in ("source_tick", "proposition_ids", "state_ids",
        "state_digests", "generations", "evidence_set_digests", "states")}
    payload.update({"schema_version": schema, "current_tick": raw["current_tick"],
        "propositions": props_raw, "active_evidence_bindings": active_raw,
        "removed_evidence_bindings": removed_raw, "update_events": events_raw,
        "evidence_only": False, "prior_position_only": True, "current_truth": False,
        "authority": False, "policy": False, "goal": False})
    if schema == COGNITIVE_PROJECTION_SCHEMA_V3:
        payload["omission_manifest"] = dict(omission_manifest)
    identity = _identity("epistemic-projection", payload)
    if (identity[0], identity[1]) != (raw.get("projection_id"), raw.get("projection_digest")):
        raise EpistemicStateError("epistemic_semantic_projection_digest_mismatch")


def semantic_packets_for_projection(projection: EpistemicCognitiveProjection) -> tuple[dict[str, Any], ...]:
    """Return exact canonical packets; callers may select only whole packets."""
    validate_cognitive_projection(projection, require_meaning=True)
    assert isinstance(projection, MeaningBearingEpistemicCognitiveProjection)
    packets = []
    for proposition, state, bindings, removed, event_history in zip(projection.propositions,
            projection.states, projection.active_evidence_bindings,
            projection.removed_evidence_bindings, projection.update_events):
        support_ids = set(state["support_binding_ids"])
        contradiction_ids = set(state["contradiction_binding_ids"])
        packet = {"schema_version": COGNITIVE_PACKET_SCHEMA,
            "proposition": dict(proposition), "state": dict(state),
            "statement_posture": "display_wording_not_proposition_identity",
            "active_evidence_bindings": [dict(item) for item in bindings],
            "evidence_posture": dict(evidence_posture(tuple(
                _normalize_binding_record(item) for item in bindings))),
            "supporting_evidence": [item["binding_id"] for item in bindings
                if item["binding_id"] in support_ids],
            "contradicting_evidence": [item["binding_id"] for item in bindings
                if item["binding_id"] in contradiction_ids],
            "removed_evidence_history": [dict(item) for item in removed],
            "update_event_history": [dict(item) for item in event_history],
            "last_update_event": dict(event_history[-1]),
            "applicability": {"temporal_scope": proposition["temporal_scope"],
                "context_scope": proposition["context_scope"],
                "source_update_tick": event_history[-1]["tick"],
                "current_tick_cutoff": projection.current_tick},
            "interpretation_posture": "canonical_prior_position_not_current_truth",
            "authority": False, "policy": False, "goal": False}
        packet_identity = _identity("epistemic-packet", packet)
        packets.append({**packet, "packet_id": packet_identity[0],
            "packet_digest": packet_identity[1]})
    return tuple(packets)


@dataclass(frozen=True)
class EpistemicUpdateCandidate:
    candidate_id: str; proposition_id: str; predecessor_state_digest: str | None; proposed_stance: str
    evidence_binding_ids: tuple[str, ...]; reason: str; rationale: str; uncertainty: str
    model_id: str | None; authority: Mapping[str, bool]; schema_version: str = CANDIDATE_SCHEMA
    proposer_kind: str | None = None; proposer_id: str | None = None

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("candidate_id"); return value

    @property
    def candidate_digest(self) -> str:
        return _identity("epistemic-candidate", self.payload())[1]


def make_epistemic_update_candidate(**kwargs: Any) -> EpistemicUpdateCandidate:
    """Construct a proposal identity without conferring runtime authority."""
    kwargs.setdefault("authority", dict(FALSE_AUTHORITY))
    if "schema_version" not in kwargs and kwargs.get("model_id"):
        kwargs["schema_version"] = LEGACY_CANDIDATE_SCHEMA
    raw = EpistemicUpdateCandidate("", **kwargs)
    if (raw.proposed_stance not in STANCES or raw.reason not in UPDATE_REASONS
            or raw.uncertainty not in {"low", "medium", "high", "unknown"}
            or not raw.rationale.strip() or len(raw.rationale) > 4000
            or raw.schema_version not in {CANDIDATE_SCHEMA, LEGACY_CANDIDATE_SCHEMA}
            or len(raw.evidence_binding_ids) != len(set(raw.evidence_binding_ids))):
        raise EpistemicStateError("epistemic_candidate_shape_invalid")
    if raw.schema_version == LEGACY_CANDIDATE_SCHEMA:
        if not raw.model_id or not raw.model_id.strip() or len(raw.model_id) > 256 or raw.proposer_kind or raw.proposer_id:
            raise EpistemicStateError("epistemic_candidate_shape_invalid")
    elif (raw.model_id is not None or raw.proposer_kind != "deterministic_rule"
          or not raw.proposer_id or len(raw.proposer_id) > 256):
        raise EpistemicStateError("epistemic_candidate_shape_invalid")
    if raw.reason != "initialization" and not raw.evidence_binding_ids:
        raise EpistemicStateError("epistemic_candidate_evidence_required")
    _authority(raw.authority)
    candidate_id, _ = _identity("epistemic-candidate", raw.payload())
    return replace(raw, candidate_id=candidate_id)


@dataclass(frozen=True)
class EpistemicUpdateEvent:
    event_id: str; event_digest: str; proposition_id: str; prior_state_digest: str | None
    successor_state_digest: str; reason: str; added_binding_ids: tuple[str, ...]
    removed_binding_ids: tuple[str, ...]; dependency_changes: Mapping[str, str]
    reliability_changes: Mapping[str, str]; update_rule_revision: str | None
    candidate_id: str | None; validation_result: str; correlation_id: str; tick: int
    generation: int; authority: Mapping[str, bool]; schema_version: str = UPDATE_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("event_id"); value.pop("event_digest"); return value

    def identity_payload(self) -> dict[str, Any]:
        """Break the state/event mutual reference while retaining the successor field."""
        value = self.payload(); value.pop("successor_state_digest"); return value


@dataclass(frozen=True)
class EpistemicCalibrationEvent:
    calibration_id: str; calibration_digest: str; proposition_id: str; forecast_artifact_id: str
    forecast_state_digest: str; observed_outcome_id: str; comparison_result: str
    source_binding_ids: tuple[str, ...]; resolved_at: str; authority: Mapping[str, bool]
    schema_version: str = CALIBRATION_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("calibration_id"); value.pop("calibration_digest"); return value


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    if os.name == "nt":
        raise EpistemicStateError("epistemic_publication_unsupported_platform")
    data = canonical_bytes(value) + b"\n"
    if len(data) > MAX_EPISTEMIC_RECORD_BYTES:
        raise EpistemicStateError("epistemic_record_size_limit_exceeded")
    try:
        publish_immutable_bytes(
            path, data, max_bytes=MAX_EPISTEMIC_RECORD_BYTES,
            collision_code="immutable_record_collision")
    except PrivateFileCustodyError as exc:
        if exc.code == "publication_unsupported":
            raise EpistemicStateError("epistemic_publication_unsupported_platform") from exc
        if exc.code == "payload_size_limit_exceeded":
            raise EpistemicStateError("epistemic_record_size_limit_exceeded") from exc
        if exc.code == "immutable_record_collision":
            raise EpistemicStateError("immutable_record_collision") from exc
        raise EpistemicStateError("epistemic_custody_root_invalid") from exc


def _read_record_bytes(path: Path) -> bytes:
    if os.name == "nt":
        try:
            entries = read_regular_files(path.parent,
                max_entries=1, max_file_bytes=MAX_EPISTEMIC_RECORD_BYTES,
                max_total_bytes=MAX_EPISTEMIC_RECORD_BYTES, selected_names=(path.name,))
        except WindowsHandleCustodyError as exc:
            raise EpistemicStateError("epistemic_record_windows_recovery_failed") from exc
        if len(entries) != 1 or entries[0][0] != path.name:
            raise FileNotFoundError(path)
        return entries[0][1]
    directory_fd: int | None = None
    try:
        directory_fd = open_private_directory(path.parent, create=False)
        return read_private_file_at(
            directory_fd, path.name, max_bytes=MAX_EPISTEMIC_RECORD_BYTES,
            require_private_mode=True)
    except PrivateFileCustodyError as exc:
        if exc.code == "file_missing":
            raise FileNotFoundError(path) from exc
        if exc.code == "file_unbounded_or_not_private":
            raise EpistemicStateError("epistemic_record_unbounded_or_not_regular") from exc
        raise EpistemicStateError("epistemic_record_custody_invalid") from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


class PersistentEpistemicStateOwner:
    """Explicit-root immutable custody with verified reconstruction and CAS."""
    def __init__(self, root: str | Path, *, allowed_namespaces: Sequence[str]) -> None:
        self.root = Path(root); self.allowed_namespaces = frozenset(allowed_namespaces)
        self._published_mutation_bound_state_digests: set[str] = set()
        self._verified_mutation_bound_state_digests: set[str] = set()
        self._incomplete_admission_bound_transactions = 0
        if not self.allowed_namespaces: raise EpistemicStateError("allowed_namespaces_required")
        if self.root.is_symlink(): raise EpistemicStateError("epistemic_custody_root_invalid")
        if os.name == "nt":
            # Existing records remain reconstructable through held Windows
            # handles. Do not manufacture empty custody directories or permit
            # publication until a matching atomic Windows writer exists.
            self.verify()
            return
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or not self.root.is_dir(): raise EpistemicStateError("epistemic_custody_root_invalid")
        for part in RECORD_COLLECTIONS:
            directory = self.root / part
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if directory.is_symlink() or not directory.is_dir(): raise EpistemicStateError("epistemic_collection_invalid")
        self.verify()

    def _read(self, kind: str) -> list[dict[str, Any]]:
        values = []
        for filename, data in self._collection_bytes(kind):
            try:
                value = json.loads(data.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
                raise EpistemicStateError("epistemic_history_corrupt") from exc
            if not isinstance(value, dict):
                raise EpistemicStateError("epistemic_history_corrupt")
            if canonical_bytes(value) + b"\n" != data:
                raise EpistemicStateError("epistemic_record_noncanonical")
            if not self._collection_identity_matches(kind, value, filename):
                raise EpistemicStateError("epistemic_record_path_identity_mismatch")
            values.append(value)
        return values

    @staticmethod
    def _collection_identity_matches(kind: str, value: Mapping[str, Any], filename: str) -> bool:
        if kind == "propositions":
            identity = value.get("proposition_id")
            if not _valid_identity(identity, "proposition"): return False
            expected = f"{identity}.json"
        elif kind == "bindings":
            identity = value.get("binding_id")
            if not _valid_identity(identity, "evidence"): return False
            expected = f"{identity}.json"
        elif kind == "states":
            generation, identity = value.get("generation"), value.get("state_id")
            if (not isinstance(generation, int) or isinstance(generation, bool) or generation < 0
                    or not _valid_identity(identity, "epistemic-state")):
                return False
            expected = f"{generation:012d}-{identity}.json"
        elif kind == "updates":
            generation, identity = value.get("generation"), value.get("event_id")
            if (not isinstance(generation, int) or isinstance(generation, bool) or generation < 0
                    or not _valid_identity(identity, "epistemic-update")):
                return False
            expected = f"{generation:012d}-{identity}.json"
        elif kind == "relations":
            expected = f"{digest(value)[7:]}.json"
        elif kind == "calibrations":
            identity = value.get("calibration_id")
            if not _valid_identity(identity, "epistemic-calibration"): return False
            expected = f"{identity}.json"
        elif kind == "transactions":
            transaction_keys = ("state", "event", "mutation_binding") if "mutation_binding" in value else ("state", "event")
            transaction_semantic = {key: value.get(key) for key in transaction_keys}
            identity, transaction_digest = _identity("epistemic-transaction", transaction_semantic)
            if (value.get("transaction_id") != identity
                    or value.get("transaction_digest") != transaction_digest):
                return False
            expected = f"{identity.split(':', 1)[1]}.json"
        else:
            return False
        return filename == expected

    def _collection_bytes(self, kind: str) -> tuple[tuple[str, bytes], ...]:
        if kind not in RECORD_COLLECTIONS or self.root.is_symlink():
            raise EpistemicStateError("epistemic_custody_root_invalid")
        directory = self.root / kind
        try:
            entries_mode = directory.lstat()
            if not stat.S_ISDIR(entries_mode.st_mode):
                raise EpistemicStateError("epistemic_collection_invalid")
        except FileNotFoundError:
            return ()
        except OSError as exc:
            raise EpistemicStateError("epistemic_collection_invalid") from exc
        if os.name == "nt":
            try:
                return tuple(read_regular_files(directory,
                    max_entries=MAX_EPISTEMIC_RECORDS_PER_COLLECTION,
                    max_file_bytes=MAX_EPISTEMIC_RECORD_BYTES,
                    max_total_bytes=MAX_EPISTEMIC_COLLECTION_BYTES))
            except WindowsHandleCustodyError as exc:
                raise EpistemicStateError("epistemic_collection_windows_recovery_failed") from exc

        directory_fd: int | None = None
        try:
            directory_fd = open_private_directory(directory, create=False)
            opened = os.fstat(directory_fd)
            if (not stat.S_ISDIR(opened.st_mode) or opened.st_ino != entries_mode.st_ino
                    or opened.st_dev != entries_mode.st_dev):
                raise EpistemicStateError("epistemic_collection_changed_during_read")
            names = list_bounded_json_names_at(
                directory_fd, max_entries=MAX_EPISTEMIC_RECORDS_PER_COLLECTION,
                max_directory_entries=MAX_EPISTEMIC_RECORDS_PER_COLLECTION + 1024)

            records: list[tuple[str, bytes]] = []
            total = 0
            for name in names:
                try:
                    data = read_private_file_at(
                        directory_fd, name, max_bytes=MAX_EPISTEMIC_RECORD_BYTES,
                        require_private_mode=True)
                except PrivateFileCustodyError as exc:
                    if exc.code == "file_unbounded_or_not_private":
                        raise EpistemicStateError("epistemic_record_unbounded_or_not_regular") from exc
                    raise EpistemicStateError("epistemic_collection_changed_during_read") from exc
                total += len(data)
                if total > MAX_EPISTEMIC_COLLECTION_BYTES:
                    raise EpistemicStateError("epistemic_collection_size_limit_exceeded")
                records.append((name, data))
            after = os.fstat(directory_fd)
            if (after.st_ino != opened.st_ino or after.st_dev != opened.st_dev
                    or after.st_mtime_ns != opened.st_mtime_ns
                    or after.st_ctime_ns != opened.st_ctime_ns):
                raise EpistemicStateError("epistemic_collection_changed_during_read")
            return tuple(records)
        except EpistemicStateError:
            raise
        except PrivateFileCustodyError as exc:
            if exc.code in {"directory_entry_limit_exceeded", "directory_file_count_limit_exceeded"}:
                raise EpistemicStateError("epistemic_record_count_limit_exceeded") from exc
            raise EpistemicStateError("epistemic_collection_custody_invalid") from exc
        except OSError as exc:
            raise EpistemicStateError("epistemic_collection_unavailable") from exc
        finally:
            if directory_fd is not None:
                os.close(directory_fd)

    def _recover_transactions(self) -> int:
        """Recover storage-only pairs and count admitted pairs still awaiting owner validation."""
        incomplete_admission_bound = 0
        published_mutation_bound_state_digests: set[str] = set()
        prepared: list[tuple[EpistemicState, EpistemicUpdateEvent]] = []
        generation_bindings: dict[tuple[str, int], tuple[str, str, str]] = {}
        admission_bound_state_digests: set[str] = set()
        for raw in self._read("transactions"):
            expected_transaction_fields = {"transaction_id", "transaction_digest", "state", "event"}
            if "mutation_binding" in raw:
                expected_transaction_fields.add("mutation_binding")
            if set(raw) != expected_transaction_fields:
                raise EpistemicStateError("epistemic_transaction_shape_invalid")
            state_raw, event_raw = raw.get("state"), raw.get("event")
            if not isinstance(state_raw, dict) or not isinstance(event_raw, dict):
                raise EpistemicStateError("epistemic_transaction_shape_invalid")
            semantic: dict[str, Any] = {"state": state_raw, "event": event_raw}
            if "mutation_binding" in raw:
                semantic["mutation_binding"] = raw.get("mutation_binding")
            transaction_id, transaction_digest = _identity("epistemic-transaction", semantic)
            if (raw.get("transaction_id"), raw.get("transaction_digest")) != (
                    transaction_id, transaction_digest):
                raise EpistemicStateError("epistemic_transaction_digest_mismatch")
            try:
                normalized_state = dict(state_raw)
                normalized_state["support_binding_ids"] = tuple(normalized_state["support_binding_ids"])
                normalized_state["contradiction_binding_ids"] = tuple(normalized_state["contradiction_binding_ids"])
                normalized_event = dict(event_raw)
                normalized_event["added_binding_ids"] = tuple(normalized_event["added_binding_ids"])
                normalized_event["removed_binding_ids"] = tuple(normalized_event["removed_binding_ids"])
                state = EpistemicState(**normalized_state)
                event = EpistemicUpdateEvent(**normalized_event)
            except (KeyError, TypeError, ValueError) as exc:
                raise EpistemicStateError("epistemic_transaction_record_invalid") from exc
            expected_state = _identity("epistemic-state", state.payload())
            expected_event = _identity("epistemic-update", event.identity_payload())
            if ((state.state_id, state.state_digest) != expected_state
                    or (event.event_id, event.event_digest) != expected_event
                    or state.proposition_id != event.proposition_id
                    or state.generation != event.generation
                    or state.predecessor_state_digest != event.prior_state_digest
                    or state.state_digest != event.successor_state_digest
                    or state.last_update_event_id != event.event_id
                    or not isinstance(event.tick, int) or isinstance(event.tick, bool) or event.tick < 0):
                raise EpistemicStateError("epistemic_transaction_lineage_invalid")
            mutation_binding = raw.get("mutation_binding")
            if mutation_binding is not None:
                if (not isinstance(mutation_binding, Mapping)
                        or set(mutation_binding) != {"candidate_id", "candidate_digest", "admission_id",
                            "admission_binding_digest", "operation_id", "correlation_id"}
                        or mutation_binding.get("candidate_id") != event.candidate_id
                        or mutation_binding.get("correlation_id") != event.correlation_id
                        or any(not isinstance(mutation_binding.get(key), str) or not mutation_binding[key]
                            for key in ("candidate_id", "candidate_digest", "admission_id",
                                "admission_binding_digest", "operation_id", "correlation_id"))):
                    raise EpistemicStateError("epistemic_transaction_mutation_binding_invalid")
            generation = (state.proposition_id, state.generation)
            pair = (state.state_digest, event.event_digest,
                    digest(mutation_binding) if mutation_binding is not None else digest(None))
            previous = generation_bindings.get(generation)
            if previous is not None and previous != pair:
                raise EpistemicStateError("epistemic_transaction_generation_conflict")
            generation_bindings[generation] = pair
            if mutation_binding is not None:
                admission_bound_state_digests.add(state.state_digest)
            prepared.append((state, event))
        for state, event in sorted(prepared, key=lambda pair: (
                pair[0].proposition_id, pair[0].generation, pair[0].state_id)):
            state_path = self.root / "states" / f"{state.generation:012d}-{state.state_id}.json"
            event_path = self.root / "updates" / f"{event.generation:012d}-{event.event_id}.json"
            if os.name == "posix":
                if state.state_digest in admission_bound_state_digests:
                    # Admission-bound transactions are not storage-only repair
                    # intents. Leave a missing pair incomplete for the mutation
                    # controller to classify; never publish state before it
                    # authenticates the separately held admission intent.
                    try:
                        existing_state = _read_record_bytes(state_path)
                        existing_event = _read_record_bytes(event_path)
                    except FileNotFoundError:
                        incomplete_admission_bound += 1
                        continue
                    if (existing_state != canonical_bytes(asdict(state)) + b"\n"
                            or existing_event != canonical_bytes(asdict(event)) + b"\n"):
                        raise EpistemicStateError("epistemic_transaction_record_conflict")
                    published_mutation_bound_state_digests.add(state.state_digest)
                    continue
                _write_new(state_path, asdict(state))
                _write_new(event_path, asdict(event))
                continue
            # Windows remains read-only for epistemic mutation. It can inspect
            # a completely published pair, but cannot synthesize a missing
            # member without the equivalent atomic publisher.
            try:
                existing_state = _read_record_bytes(state_path)
                existing_event = _read_record_bytes(event_path)
            except FileNotFoundError as exc:
                raise EpistemicStateError("epistemic_transaction_recovery_unsupported_platform") from exc
            if (existing_state != canonical_bytes(asdict(state)) + b"\n"
                    or existing_event != canonical_bytes(asdict(event)) + b"\n"):
                raise EpistemicStateError("epistemic_transaction_record_conflict")
            if state.state_digest in admission_bound_state_digests:
                published_mutation_bound_state_digests.add(state.state_digest)
        self._published_mutation_bound_state_digests = published_mutation_bound_state_digests
        self._verified_mutation_bound_state_digests.intersection_update(
            published_mutation_bound_state_digests)
        self._incomplete_admission_bound_transactions = incomplete_admission_bound
        return incomplete_admission_bound

    def register_proposition(self, proposition: EpistemicProposition) -> None:
        expected = make_proposition(**{k:v for k,v in asdict(proposition).items() if k not in {"proposition_id","proposition_digest","schema_version"}})
        if expected != proposition: raise EpistemicStateError("proposition_identity_mismatch")
        if proposition.namespace not in self.allowed_namespaces: raise EpistemicStateError("proposition_namespace_not_allowed")
        _write_new(self.root / "propositions" / f"{proposition.proposition_id}.json", asdict(proposition))

    def add_relation(self, relation: PropositionRelation) -> None:
        if relation.relation not in RELATIONS or relation.source_proposition_id == relation.target_proposition_id: raise EpistemicStateError("proposition_relation_invalid")
        self.proposition(relation.source_proposition_id); self.proposition(relation.target_proposition_id)
        _write_new(self.root / "relations" / f"{digest(asdict(relation))[7:]}.json", asdict(relation))

    def proposition(self, proposition_id: str) -> EpistemicProposition:
        if not _valid_identity(proposition_id, "proposition"):
            raise EpistemicStateError("proposition_identity_invalid")
        path=self.root/"propositions"/f"{proposition_id}.json"
        try:
            raw = json.loads(_read_record_bytes(path).decode("utf-8"))
        except FileNotFoundError as exc:
            raise EpistemicStateError("proposition_not_found") from exc
        except (UnicodeError, json.JSONDecodeError, TypeError, KeyError) as exc:
            raise EpistemicStateError("proposition_record_corrupt") from exc
        if not isinstance(raw, dict) or not self._collection_identity_matches("propositions", raw, path.name):
            raise EpistemicStateError("proposition_record_identity_mismatch")
        value=EpistemicProposition(**raw); expected=make_proposition(**{k:v for k,v in asdict(value).items() if k not in {"proposition_id","proposition_digest","schema_version"}})
        if value != expected: raise EpistemicStateError("proposition_identity_mismatch")
        return value

    def bind_evidence(self, binding: EvidenceBinding) -> None:
        self.proposition(binding.proposition_id)
        expected=make_evidence_binding(**{k:v for k,v in asdict(binding).items() if k not in {"binding_id","binding_digest","schema_version"}})
        if expected != binding: raise EpistemicStateError("evidence_binding_digest_mismatch")
        if binding.dependency_kind in {"same_source_derivation","shared_upstream_evidence","duplicate_alias"} and not binding.upstream_binding_ids: raise EpistemicStateError("evidence_dependency_missing_upstream")
        known_bindings = {value.get("binding_id"): value for value in self._read("bindings")}
        for upstream in binding.upstream_binding_ids:
            if not _valid_identity(upstream, "evidence"):
                raise EpistemicStateError("evidence_upstream_identity_invalid")
            predecessor = known_bindings.get(upstream)
            if predecessor is None: raise EpistemicStateError("evidence_upstream_not_found")
            if predecessor.get("proposition_id") != binding.proposition_id:
                raise EpistemicStateError("evidence_upstream_proposition_mismatch")
        _write_new(self.root/"bindings"/f"{binding.binding_id}.json", asdict(binding))

    def bindings(self, proposition_id: str) -> tuple[EvidenceBinding, ...]:
        return tuple(EvidenceBinding(**{**v, "upstream_binding_ids": tuple(v["upstream_binding_ids"])})
                     for v in self._read("bindings") if v["proposition_id"] == proposition_id)

    def current_state(self, proposition_id: str) -> EpistemicState | None:
        states=[EpistemicState(**{**v, "support_binding_ids": tuple(v["support_binding_ids"]),
                "contradiction_binding_ids": tuple(v["contradiction_binding_ids"])})
                for v in self._read("states") if v["proposition_id"] == proposition_id]
        return max(states, key=lambda x:x.generation) if states else None

    @contextmanager
    def _mutation_lock(self) -> Iterator[None]:
        """Serialize state-generation compare-and-swap through private custody."""
        if os.name != "posix":
            raise EpistemicStateError("epistemic_mutation_unsupported_platform")
        directory_fd: int | None = None
        descriptor: int | None = None
        try:
            require_flock()
            directory_fd = open_private_directory(self.root, create=False)
            descriptor = os.open(
                ".epistemic-mutation.lock",
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
                raise EpistemicStateError("epistemic_mutation_lock_invalid")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except EpistemicStateError:
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
            raise EpistemicStateError("epistemic_mutation_lock_unavailable") from exc
        assert directory_fd is not None and descriptor is not None
        try:
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
                os.close(directory_fd)

    def update_events(self, proposition_id: str) -> tuple[EpistemicUpdateEvent, ...]:
        return tuple(sorted((EpistemicUpdateEvent(**{**v,
                            "added_binding_ids": tuple(v["added_binding_ids"]),
                            "removed_binding_ids": tuple(v["removed_binding_ids"])}) for v in self._read("updates")
                            if v["proposition_id"] == proposition_id), key=lambda item: item.generation))

    def active_binding_ids(self, proposition_id: str) -> tuple[str, ...]:
        """Reconstruct explicit membership from attributable add/remove lineage."""
        active: set[str] = set()
        for event in self.update_events(proposition_id):
            active.difference_update(event.removed_binding_ids)
            active.update(event.added_binding_ids)
        state = self.current_state(proposition_id)
        if state is not None and digest(sorted(active)) != state.evidence_set_digest:
            raise EpistemicStateError("epistemic_active_evidence_lineage_mismatch")
        return tuple(sorted(active))

    def _accept_mutation_lineage_verification(self, state_digests: Sequence[str]) -> None:
        verified = set(state_digests)
        if (len(verified) != len(state_digests)
                or verified != self._published_mutation_bound_state_digests):
            raise EpistemicStateError("epistemic_mutation_lineage_verification_mismatch")
        self._verified_mutation_bound_state_digests = verified

    def cognitive_projection(self, *, max_states: int,
                             current_tick: int | None = None) -> EpistemicCognitiveProjection | None:
        """Capture a verified, bounded prior projection without changing custody.

        The update files visible in the first inventory are the chronology boundary:
        only their paired states are eligible.  A second inventory makes concurrent
        custody advancement fail closed rather than accidentally becoming same-cycle
        prior state.  Update ticks order generations *inside* that captured epoch;
        daemon tick strings are deliberately not interpreted as epistemic time.
        """
        if (not isinstance(max_states, int) or isinstance(max_states, bool)
                or not 1 <= max_states <= MAX_COGNITIVE_PROJECTION_STATES):
            raise EpistemicStateError("epistemic_projection_bound_invalid")
        if current_tick is not None and (not isinstance(current_tick, int)
                or isinstance(current_tick, bool) or current_tick < 0):
            raise EpistemicStateError("epistemic_projection_tick_invalid")
        self.verify()
        if (self._published_mutation_bound_state_digests
                - self._verified_mutation_bound_state_digests):
            raise EpistemicStateError("epistemic_mutation_lineage_unverified")
        update_bytes = self._collection_bytes("updates")
        state_bytes = self._collection_bytes("states")
        proposition_bytes = self._collection_bytes("propositions")
        binding_bytes = self._collection_bytes("bindings")
        if (update_bytes != self._collection_bytes("updates")
                or state_bytes != self._collection_bytes("states")
                or proposition_bytes != self._collection_bytes("propositions")
                or binding_bytes != self._collection_bytes("bindings")):
            raise EpistemicStateError("epistemic_projection_boundary_changed")
        events = [EpistemicUpdateEvent(**json.loads(raw)) for _, raw in update_bytes]
        states = [EpistemicState(**json.loads(raw)) for _, raw in state_bytes]
        propositions = [EpistemicProposition(**json.loads(raw)) for _, raw in proposition_bytes]
        bindings = [EvidenceBinding(**{**json.loads(raw),
            "upstream_binding_ids": tuple(json.loads(raw)["upstream_binding_ids"])})
            for _, raw in binding_bytes]
        proposition_by_id = {item.proposition_id: item for item in propositions
            if item.namespace in self.allowed_namespaces}
        binding_by_id = {item.binding_id: item for item in bindings}
        allowed_propositions = set(proposition_by_id)
        paired = {event.successor_state_digest: event for event in events}
        if len(paired) != len(events) or any(state.state_digest not in paired for state in states):
            raise EpistemicStateError("epistemic_projection_pairing_ambiguous")
        latest: dict[str, EpistemicState] = {}
        for state in states:
            if state.proposition_id not in allowed_propositions:
                continue
            previous = latest.get(state.proposition_id)
            if previous is None or state.generation > previous.generation:
                latest[state.proposition_id] = state
        # Select the actual latest generation first. If it was written at or
        # after this cognition tick, omit that proposition entirely rather
        # than falling back to an older generation and presenting stale state
        # as the current prior position. This remains effective after restart,
        # because the cutoff is compared with the authenticated update event's
        # persisted tick, not process-local ordering.
        events_by_proposition: dict[str, list[EpistemicUpdateEvent]] = {}
        for event in events:
            events_by_proposition.setdefault(event.proposition_id, []).append(event)
        if current_tick is not None:
            latest = {proposition_id: state for proposition_id, state in latest.items()
                if all(event.tick < current_tick for event in
                    events_by_proposition.get(proposition_id, ()))}
        ordered_latest = tuple(sorted(latest.values(), key=lambda item: item.proposition_id))
        selected = ordered_latest[:max_states]
        if not selected:
            return None
        omitted_states = ordered_latest[max_states:]
        if len(omitted_states) > MAX_COGNITIVE_PROJECTION_OMISSIONS:
            raise EpistemicStateError("epistemic_projection_omission_bound_exceeded")
        omission_manifest: dict[str, Any] | None = None
        if omitted_states:
            events_by_id = {event.event_id: event for event in events}
            omitted_rows: list[dict[str, Any]] = []
            for state in omitted_states:
                event = events_by_id.get(str(state.last_update_event_id))
                if event is None or event.successor_state_digest != state.state_digest:
                    raise EpistemicStateError("epistemic_projection_omitted_state_event_missing")
                omitted_rows.append({
                    "proposition_id": state.proposition_id,
                    "state_id": state.state_id,
                    "state_digest": state.state_digest,
                    "generation": state.generation,
                    "update_event_id": event.event_id,
                    "update_tick": event.tick,
                    "stance": state.stance,
                    "dependency_unresolved": state.dependency_unresolved,
                    "freshness": state.freshness,
                    "updated_at": state.updated_at,
                    "omission_reason": "projection_state_bound",
                })
            omission_manifest = {
                "schema_version": "sentientos.epistemic_projection_omission_manifest:v1",
                "selection_policy": "latest_prior_state_by_proposition_id_ascending",
                "selection_limit": max_states,
                "available_prior_state_count": len(ordered_latest),
                "selected_state_count": len(selected),
                "omitted_state_count": len(omitted_rows),
                "omitted_identity_digest": digest(omitted_rows),
                "omitted_state_identities": tuple(omitted_rows),
            }
        event_histories_by_state = {state.proposition_id: tuple(sorted((item for item in
            events_by_proposition.get(state.proposition_id, ()) if item.generation <= state.generation),
            key=lambda item: item.generation)) for state in selected}
        selected_events = tuple(history[-1] for history in
            (event_histories_by_state[state.proposition_id] for state in selected))
        source_tick = max([event.tick for history in event_histories_by_state.values()
            for event in history] + [row["update_tick"] for row in
                (omission_manifest or {}).get("omitted_state_identities", ())])
        projection_tick = current_tick if current_tick is not None else source_tick + 1
        active_by_proposition: dict[str, set[str]] = {}
        for event in sorted(events, key=lambda item: (item.proposition_id, item.generation)):
            active = active_by_proposition.setdefault(event.proposition_id, set())
            active.difference_update(event.removed_binding_ids)
            active.update(event.added_binding_ids)
        active_records: list[tuple[Mapping[str, Any], ...]] = []
        removed_records: list[tuple[Mapping[str, Any], ...]] = []
        event_histories: list[tuple[Mapping[str, Any], ...]] = []
        for state in selected:
            active_ids = tuple(sorted(active_by_proposition.get(state.proposition_id, set())))
            history = event_histories_by_state[state.proposition_id]
            if len(history) != state.generation + 1:
                raise EpistemicStateError("epistemic_projection_update_history_incomplete")
            removed_ids = tuple(sorted({binding_id for item in history
                for binding_id in item.removed_binding_ids}))
            if any(binding_id not in binding_by_id for binding_id in active_ids):
                raise EpistemicStateError("epistemic_projection_binding_missing")
            if digest(list(active_ids)) != state.evidence_set_digest:
                raise EpistemicStateError("epistemic_active_evidence_lineage_mismatch")
            if any(binding_id not in binding_by_id for binding_id in removed_ids):
                raise EpistemicStateError("epistemic_projection_removed_binding_missing")
            active_records.append(tuple(asdict(binding_by_id[binding_id])
                for binding_id in active_ids))
            removed_records.append(tuple(asdict(binding_by_id[binding_id])
                for binding_id in removed_ids))
            event_histories.append(tuple(asdict(item) for item in history))
        return make_cognitive_projection(selected, source_tick=source_tick,
            current_tick=projection_tick,
            propositions=tuple(asdict(proposition_by_id[state.proposition_id]) for state in selected),
            active_evidence_bindings=tuple(active_records),
            removed_evidence_bindings=tuple(removed_records),
            update_events=tuple(event_histories),
            omission_manifest=omission_manifest)

    @staticmethod
    def validate_update_timestamp(*, tick: int, recorded_at: str) -> None:
        """Validate persisted chronology inputs before any mutation intent is written."""
        if not isinstance(tick, int) or isinstance(tick, bool) or tick < 0:
            raise EpistemicStateError("epistemic_update_tick_invalid")
        if not isinstance(recorded_at, str) or not recorded_at or len(recorded_at) > 128:
            raise EpistemicStateError("epistemic_recorded_at_invalid")
        try:
            recorded_instant = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EpistemicStateError("epistemic_recorded_at_invalid") from exc
        if recorded_instant.tzinfo is None or recorded_instant.utcoffset() is None:
            raise EpistemicStateError("epistemic_recorded_at_invalid")

    def commit_update(self, *, proposition_id: str, expected_predecessor_digest: str | None, stance: str,
                      reason: str, active_binding_ids: Sequence[str], added_binding_ids: Sequence[str] = (),
                      removed_binding_ids: Sequence[str] = (), dependency_changes: Mapping[str,str] = {},
                      reliability_changes: Mapping[str,str] = {}, update_rule_id: str = "qualitative_explicit:v1",
                      update_rule_revision: str | None = None, candidate: EpistemicUpdateCandidate | None = None,
                      correlation_id: str, tick: int, recorded_at: str, confidence: Mapping[str,Any] | None = None,
                      mutation_binding: Mapping[str, Any] | None = None) -> tuple[EpistemicState, EpistemicUpdateEvent]:
        with self._mutation_lock():
            return self._commit_update_locked(proposition_id=proposition_id,
                expected_predecessor_digest=expected_predecessor_digest, stance=stance, reason=reason,
                active_binding_ids=active_binding_ids, added_binding_ids=added_binding_ids,
                removed_binding_ids=removed_binding_ids, dependency_changes=dependency_changes,
                reliability_changes=reliability_changes, update_rule_id=update_rule_id,
                update_rule_revision=update_rule_revision, candidate=candidate,
                correlation_id=correlation_id, tick=tick, recorded_at=recorded_at, confidence=confidence,
                mutation_binding=mutation_binding)

    def _commit_update_locked(self, *, proposition_id: str, expected_predecessor_digest: str | None, stance: str,
                      reason: str, active_binding_ids: Sequence[str], added_binding_ids: Sequence[str] = (),
                      removed_binding_ids: Sequence[str] = (), dependency_changes: Mapping[str,str] = {},
                      reliability_changes: Mapping[str,str] = {}, update_rule_id: str = "qualitative_explicit:v1",
                      update_rule_revision: str | None = None, candidate: EpistemicUpdateCandidate | None = None,
                      correlation_id: str, tick: int, recorded_at: str, confidence: Mapping[str,Any] | None = None,
                      mutation_binding: Mapping[str, Any] | None = None) -> tuple[EpistemicState, EpistemicUpdateEvent]:
        self.validate_update_timestamp(tick=tick, recorded_at=recorded_at)
        self.verify(); self.proposition(proposition_id); prior=self.current_state(proposition_id)
        actual=prior.state_digest if prior else None
        if actual != expected_predecessor_digest: raise EpistemicStateError("epistemic_state_compare_and_swap_failed")
        if stance not in STANCES or reason not in UPDATE_REASONS: raise EpistemicStateError("epistemic_update_vocabulary_invalid")
        if candidate:
            expected_candidate = make_epistemic_update_candidate(**{k:v for k,v in asdict(candidate).items() if k != "candidate_id"})
            if (candidate != expected_candidate or candidate.proposition_id != proposition_id or candidate.predecessor_state_digest != expected_predecessor_digest or candidate.proposed_stance != stance or candidate.reason != reason or dict(candidate.authority) != FALSE_AUTHORITY): raise EpistemicStateError("epistemic_candidate_validation_failed")
        sequences = (active_binding_ids, added_binding_ids, removed_binding_ids)
        if (any(not isinstance(values, (list, tuple)) for values in sequences)
                or any(not _valid_identity(item, "evidence") for values in sequences for item in values)):
            raise EpistemicStateError("epistemic_evidence_delta_invalid")
        active_set, added_set, removed_set = map(set, sequences)
        if (len(active_set) != len(active_binding_ids) or len(added_set) != len(added_binding_ids)
                or len(removed_set) != len(removed_binding_ids) or added_set & removed_set):
            raise EpistemicStateError("epistemic_evidence_delta_invalid")
        known={b.binding_id:b for b in self.bindings(proposition_id)}
        if (active_set | added_set | removed_set) - set(known): raise EpistemicStateError("epistemic_evidence_not_found")
        prior_active = set(self.active_binding_ids(proposition_id))
        if (not removed_set <= prior_active or added_set & prior_active
                or active_set != ((prior_active - removed_set) | added_set)):
            raise EpistemicStateError("epistemic_evidence_delta_mismatch")
        if any(known[binding_id].withdrawn for binding_id in active_set):
            raise EpistemicStateError("epistemic_withdrawn_evidence_active")
        selected=[known[x] for x in active_binding_ids]
        posture=evidence_posture(selected); support=tuple(sorted(b.binding_id for b in selected if b.evidence_relation=="supports" or b.reliability_posture=="supports")); contradiction=tuple(sorted(b.binding_id for b in selected if b.evidence_relation=="contradicts" or b.reliability_posture=="contradicts"))
        generation=(prior.generation+1 if prior else 0)
        active_freshness = {b.freshness for b in selected if not b.withdrawn}
        # Unknown evidence must not be promoted to current merely because it
        # is present.  A current observation keeps a mixed set current; when
        # no current observation exists, preserve stale or unknown posture.
        freshness = ("current" if "current" in active_freshness else
                     "stale" if "stale" in active_freshness else "unknown")
        state_payload={"proposition_id":proposition_id,"generation":generation,"predecessor_state_digest":actual,"stance":stance,"confidence":confidence,"evidence_set_digest":digest(sorted(active_binding_ids)),"support_binding_ids":support,"contradiction_binding_ids":contradiction,"dependency_unresolved":posture["dependency_unresolved"],"freshness":freshness,"last_update_event_id":None,"update_rule_id":update_rule_id,"created_at":prior.created_at if prior else recorded_at,"updated_at":recorded_at,"authority":dict(FALSE_AUTHORITY),"schema_version":STATE_SCHEMA}
        # Event/state circularity is avoided by binding event id into state after deriving an event commitment to successor semantics without that id.
        event_payload={"proposition_id":proposition_id,"prior_state_digest":actual,"successor_state_digest":"","reason":reason,"added_binding_ids":tuple(sorted(added_binding_ids)),"removed_binding_ids":tuple(sorted(removed_binding_ids)),"dependency_changes":dict(dependency_changes),"reliability_changes":dict(reliability_changes),"update_rule_revision":update_rule_revision,"candidate_id":candidate.candidate_id if candidate else None,"validation_result":"deterministically_validated","correlation_id":correlation_id,"tick":tick,"generation":generation,"authority":dict(FALSE_AUTHORITY),"schema_version":UPDATE_SCHEMA}
        identity_payload=dict(event_payload); identity_payload.pop("successor_state_digest")
        eid,edg=_identity("epistemic-update",identity_payload); state_payload["last_update_event_id"]=eid
        sid,sdg=_identity("epistemic-state",state_payload); event_payload["successor_state_digest"]=sdg
        state=EpistemicState(sid,sdg,proposition_id,generation,actual,stance,confidence,
            str(state_payload["evidence_set_digest"]),support,contradiction,bool(posture["dependency_unresolved"]),
            str(state_payload["freshness"]),eid,update_rule_id,prior.created_at if prior else recorded_at,
            recorded_at,dict(FALSE_AUTHORITY))
        event=EpistemicUpdateEvent(eid,edg,proposition_id,actual,sdg,reason,tuple(sorted(added_binding_ids)),
            tuple(sorted(removed_binding_ids)),dict(dependency_changes),dict(reliability_changes),update_rule_revision,
            candidate.candidate_id if candidate else None,"deterministically_validated",correlation_id,tick,generation,dict(FALSE_AUTHORITY))
        transaction_semantic = {"state": asdict(state), "event": asdict(event),
                                "mutation_binding": dict(mutation_binding) if mutation_binding is not None else None}
        transaction_id, transaction_digest = _identity("epistemic-transaction", transaction_semantic)
        transaction = {**transaction_semantic, "transaction_id": transaction_id,
                       "transaction_digest": transaction_digest}
        transaction_filename = transaction_id.split(":", 1)[1] + ".json"
        _write_new(self.root / "transactions" / transaction_filename, transaction)
        _write_new(self.root/"states"/f"{generation:012d}-{sid}.json",asdict(state))
        _write_new(self.root/"updates"/f"{generation:012d}-{eid}.json",asdict(event))
        return state,event

    def record_calibration(self, **kwargs: Any) -> EpistemicCalibrationEvent:
        raw=EpistemicCalibrationEvent("","",authority=dict(FALSE_AUTHORITY),**kwargs); self.proposition(raw.proposition_id)
        states=[EpistemicState(**v) for v in self._read("states")]
        forecast=next((s for s in states if s.state_digest == raw.forecast_state_digest),None)
        if forecast is None: raise EpistemicStateError("calibration_forecast_state_missing")
        if forecast.proposition_id != raw.proposition_id: raise EpistemicStateError("calibration_forecast_proposition_mismatch")
        if raw.resolved_at <= forecast.updated_at: raise EpistemicStateError("calibration_outcome_not_after_forecast")
        bindings={b.binding_id:b for b in self.bindings(raw.proposition_id)}
        if not raw.source_binding_ids: raise EpistemicStateError("calibration_source_bindings_required")
        if set(raw.source_binding_ids)-set(bindings): raise EpistemicStateError("calibration_source_binding_missing_or_foreign")
        cid,dg=_identity("epistemic-calibration",raw.payload()); value=replace(raw,calibration_id=cid,calibration_digest=dg)
        _write_new(self.root/"calibrations"/f"{cid}.json",asdict(value)); return value

    def verify(self) -> Mapping[str,int]:
        incomplete_admission_bound = self._recover_transactions()
        propositions={}
        for raw in self._read("propositions"):
            proposition_value=EpistemicProposition(**raw); expected_proposition=make_proposition(**{k:v for k,v in raw.items() if k not in {"proposition_id","proposition_digest","schema_version"}})
            if proposition_value != expected_proposition: raise EpistemicStateError("proposition_identity_mismatch")
            propositions[proposition_value.proposition_id]=proposition_value
        bindings={}
        for raw in self._read("bindings"):
            binding_value=EvidenceBinding(**raw)
            if binding_value.proposition_id not in propositions: raise EpistemicStateError("evidence_proposition_missing")
            expected_binding=make_evidence_binding(**{k:v for k,v in raw.items() if k not in {"binding_id","binding_digest","schema_version"}})
            if binding_value != expected_binding: raise EpistemicStateError("evidence_binding_digest_mismatch")
            bindings[binding_value.binding_id]=binding_value
        for raw in self._read("relations"):
            try:
                relation = PropositionRelation(**raw)
            except (TypeError, KeyError) as exc:
                raise EpistemicStateError("proposition_relation_invalid") from exc
            if (not _valid_identity(relation.source_proposition_id, "proposition")
                    or not _valid_identity(relation.target_proposition_id, "proposition")
                    or not isinstance(relation.relation, str) or relation.relation not in RELATIONS
                    or relation.source_proposition_id == relation.target_proposition_id
                    or relation.source_proposition_id not in propositions
                    or relation.target_proposition_id not in propositions):
                raise EpistemicStateError("proposition_relation_invalid")
        children: dict[str, list[str]] = {binding_id: [] for binding_id in bindings}
        indegree: dict[str, int] = {}
        for binding in bindings.values():
            indegree[binding.binding_id] = len(binding.upstream_binding_ids)
            for upstream in binding.upstream_binding_ids:
                predecessor = bindings.get(upstream)
                if predecessor is None:
                    raise EpistemicStateError("evidence_upstream_not_found")
                if predecessor.proposition_id != binding.proposition_id:
                    raise EpistemicStateError("evidence_upstream_proposition_mismatch")
                children[upstream].append(binding.binding_id)
        ready = [binding_id for binding_id, count in indegree.items() if count == 0]
        visited = 0
        while ready:
            binding_id = ready.pop(); visited += 1
            for child in children[binding_id]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if visited != len(bindings):
            raise EpistemicStateError("evidence_dependency_cycle")
        states=[EpistemicState(**v) for v in self._read("states")]; events=[EpistemicUpdateEvent(**v) for v in self._read("updates")]
        event_by_generation={(e.proposition_id,e.generation):e for e in events}
        state_by_generation={(state.proposition_id,state.generation):state for state in states}
        if (len(event_by_generation) != len(events) or len(state_by_generation) != len(states)
                or len(states) != len(events)):
            raise EpistemicStateError("epistemic_update_state_pairing_ambiguous")
        for event in events:
            state = state_by_generation.get((event.proposition_id, event.generation))
            if (state is None or event.prior_state_digest != state.predecessor_state_digest
                    or event.successor_state_digest != state.state_digest
                    or event.event_id != state.last_update_event_id):
                raise EpistemicStateError("epistemic_update_state_pairing_invalid")
        active_by_proposition: dict[str, set[str]] = {}
        for event in sorted(events, key=lambda item: (item.proposition_id, item.generation)):
            state = state_by_generation[(event.proposition_id, event.generation)]
            if (not isinstance(event.added_binding_ids, (list, tuple))
                    or not isinstance(event.removed_binding_ids, (list, tuple))
                    or any(not _valid_identity(item, "evidence")
                        for item in (*event.added_binding_ids, *event.removed_binding_ids))):
                raise EpistemicStateError("epistemic_evidence_delta_invalid")
            added = set(event.added_binding_ids); removed = set(event.removed_binding_ids)
            active = active_by_proposition.setdefault(event.proposition_id, set())
            if (len(added) != len(event.added_binding_ids)
                    or len(removed) != len(event.removed_binding_ids)
                    or added & removed or not removed <= active or added & active):
                raise EpistemicStateError("epistemic_evidence_delta_invalid")
            for binding_id in added | removed:
                validated_binding = bindings.get(binding_id)
                if validated_binding is None:
                    raise EpistemicStateError("epistemic_update_binding_missing")
                if validated_binding.proposition_id != event.proposition_id:
                    raise EpistemicStateError("epistemic_update_binding_foreign")
            active.difference_update(removed)
            active.update(added)
            if any(bindings[binding_id].withdrawn for binding_id in active):
                raise EpistemicStateError("epistemic_withdrawn_evidence_active")
            if digest(sorted(active)) != state.evidence_set_digest:
                raise EpistemicStateError("epistemic_active_evidence_lineage_mismatch")
        previous: dict[str, tuple[int, str]] = {}
        for state in sorted(states,key=lambda x:(x.proposition_id,x.generation)):
            if state.proposition_id not in propositions or state.stance not in STANCES or dict(state.authority)!=FALSE_AUTHORITY: raise EpistemicStateError("epistemic_state_invalid")
            sid,sdg=_identity("epistemic-state",state.payload())
            if (sid,sdg)!=(state.state_id,state.state_digest): raise EpistemicStateError("epistemic_state_digest_mismatch")
            prior = previous.get(state.proposition_id)
            expected_generation = prior[0] + 1 if prior is not None else 0
            expected_predecessor = prior[1] if prior is not None else None
            if (state.generation != expected_generation
                    or state.predecessor_state_digest != expected_predecessor):
                raise EpistemicStateError("epistemic_predecessor_missing_or_mismatch")
            validated_event=event_by_generation.get((state.proposition_id,state.generation))
            if validated_event is None or validated_event.prior_state_digest != state.predecessor_state_digest or validated_event.successor_state_digest != state.state_digest or validated_event.event_id != state.last_update_event_id: raise EpistemicStateError("epistemic_update_event_missing_or_mismatch")
            previous[state.proposition_id]=(state.generation,state.state_digest)
        for event in events:
            eid,edg=_identity("epistemic-update",event.identity_payload())
            if (eid,edg)!=(event.event_id,event.event_digest) or event.reason not in UPDATE_REASONS or dict(event.authority)!=FALSE_AUTHORITY: raise EpistemicStateError("epistemic_update_event_invalid")
        state_by_digest={s.state_digest:s for s in states}
        for raw in self._read("calibrations"):
            calibration=EpistemicCalibrationEvent(**raw)
            source_binding_ids = calibration.source_binding_ids
            if (not _valid_identity(calibration.proposition_id, "proposition")
                    or not isinstance(calibration.forecast_state_digest, str)
                    or not isinstance(calibration.resolved_at, str)
                    or not isinstance(source_binding_ids, (tuple, list))
                    or any(not _valid_identity(binding_id, "evidence") for binding_id in source_binding_ids)
                    or len(source_binding_ids) != len(set(source_binding_ids))):
                raise EpistemicStateError("epistemic_calibration_invalid")
            forecast=state_by_digest.get(calibration.forecast_state_digest)
            cid,cdg=_identity("epistemic-calibration",calibration.payload())
            if ((cid,cdg)!=(calibration.calibration_id,calibration.calibration_digest) or
                    calibration.proposition_id not in propositions or forecast is None or
                    forecast.proposition_id != calibration.proposition_id or
                    calibration.resolved_at <= forecast.updated_at or not calibration.source_binding_ids or
                    calibration.schema_version != CALIBRATION_SCHEMA
                    or calibration.authority != FALSE_AUTHORITY
                    or any(binding_id not in bindings or bindings[binding_id].proposition_id != calibration.proposition_id
                        for binding_id in calibration.source_binding_ids)):
                raise EpistemicStateError("epistemic_calibration_invalid")
        return {"propositions":len(propositions),"bindings":len(bindings),"states":len(states),"updates":len(events),"calibrations":len(self._read("calibrations")),"incomplete_admission_bound_transactions":incomplete_admission_bound}


def embodied_prediction_binding(*, proposition_id: str, expectation: Any, comparison: Any, attribution: Any, observation: Any) -> EvidenceBinding:
    """Preserve an observation without treating its self-declared issuer as verified.

    The current observation contract binds content, but does not authenticate an
    observer.  Keep the historical event time and exact content identity while
    leaving currentness, independence, and consequence relation unresolved.
    """
    if observation is None:
        raise EpistemicStateError("independent_observation_required")
    try:
        from .embodied_consequence import verify_independent_observation
        verify_independent_observation(observation)
    except Exception as exc:
        raise EpistemicStateError("embodied_observation_identity_unverified") from exc
    return make_evidence_binding(
        proposition_id=proposition_id,
        source_artifact_id=observation.observation_id,
        source_digest=observation.observation_digest,
        source_schema=observation.schema_version,
        source_class=observation.observation_source_class,
        observation_time=observation.observed_at,
        evidence_relation="contextualizes",
        dependency_kind="unknown_dependency",
        dependency_group=None,
        upstream_binding_ids=(),
        freshness="unknown",
        reliability_posture="observer_identity_unverified",
    )


__all__ = [name for name in tuple(globals()) if name.startswith("Epistemic") or name in {"PersistentEpistemicStateOwner","PropositionRelation","EvidenceBinding","make_proposition","make_evidence_binding","make_epistemic_update_candidate","evidence_posture","embodied_prediction_binding","FALSE_AUTHORITY"}]
