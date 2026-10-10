"""Controlled same-context cognitive-model replacement observations.

This module owns evidence, not model activation.  Callers supply two already
governed endpoints; the experiment never changes either endpoint or any memory.
"""
from __future__ import annotations

import json
import os
import secrets
import stat
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, cast

from .local_model_authority import digest_payload

PURPOSE = "resident_developmental_model_replacement_experiment"
CONTEXT_SCHEMA = "sentientos.developmental_model_replacement_context:v1"
CONTEXT_BINDING_SCHEMA = "sentientos.developmental_model_replacement_context_binding:v1"
PROVENANCE_SCHEMA = "sentientos.model_development_provenance:v1"
PROTOCOL_SCHEMA = "sentientos.developmental_model_replacement_protocol:v1"
RUN_SCHEMA = "sentientos.developmental_model_replacement_run:v1"
CONDITION_START_SCHEMA = "sentientos.developmental_model_replacement_condition_start:v1"
CONDITION_RESULT_SCHEMA = "sentientos.developmental_model_replacement_condition_result:v1"
MAX_PROVENANCE_ARTIFACT_BYTES = 262_144
MAX_PROVENANCE_CLAIMS = 128
MAX_PROTOCOL_ARTIFACT_BYTES = 1_048_576
MAX_CONTEXT_ARTIFACT_BYTES = 2_097_152
MAX_RUN_ARTIFACT_BYTES = 4_194_304
MAX_CONDITION_ARTIFACT_BYTES = 1_048_576
MAX_WORLD_STATE_PROJECTION_RECORDS = 48
CONDITION_ORDER = (
    "model_a_history_present", "model_a_history_withheld",
    "model_b_history_present", "model_b_history_withheld",
    "model_a_history_restored",
)


def _prior_cognition_bindings(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and expose exact prior cognitive projections frozen in context."""
    self_model = payload.get("prior_self_model")
    epistemic = payload.get("prior_epistemic_state")
    tick_id, current_tick = payload.get("tick_id"), payload.get("current_tick")
    if self_model is not None or epistemic is not None:
        if (not isinstance(tick_id, str) or not tick_id or type(current_tick) is not int
                or current_tick < 0):
            raise DevelopmentalModelReplacementError("prior_cognition_tick_binding_invalid")
    result: dict[str, Any] = {
        "prior_self_model_projection_id": None,
        "prior_self_model_projection_digest": None,
        "prior_self_model_source_tick": None,
        "prior_epistemic_projection_id": None,
        "prior_epistemic_projection_digest": None,
        "prior_epistemic_source_tick": None,
        "prior_epistemic_state_ids": [],
        "prior_epistemic_state_digests": [],
        "prior_cognitive_context_posture": "not_bound",
    }
    bound = 0
    if self_model is not None:
        if not isinstance(self_model, Mapping):
            raise DevelopmentalModelReplacementError("prior_self_model_binding_invalid")
        semantic = {key: value for key, value in self_model.items()
            if key not in {"projection_id", "projection_digest"}}
        claims = self_model.get("selected_claims")
        claim_ids, claim_digests = self_model.get("selected_claim_ids"), self_model.get("selected_claim_digests")
        authority = self_model.get("authority")
        calculated = _digest(semantic)
        if (self_model.get("projection_digest") != calculated
                or self_model.get("projection_id") != "cognitive-self-model-" + calculated[7:31]
                or not isinstance(self_model.get("source_tick"), str)
                or self_model.get("source_tick") == tick_id
                or not isinstance(claims, (list, tuple)) or len(claims) > 64
                or any(not isinstance(item, Mapping) for item in claims)
                or not isinstance(claim_ids, (list, tuple))
                or not isinstance(claim_digests, (list, tuple)) or len(claim_ids) > 64
                or len(claim_ids) != len(claim_digests)
                or tuple(claim_ids) != tuple(str(item.get("claim_id", "")) for item in claims)
                or tuple(claim_digests) != tuple(str(item.get("semantic_digest", "")) for item in claims)
                or not isinstance(authority, Mapping) or any(authority.values())
                or self_model.get("current_truth") is not False
                or self_model.get("read_only") is not True
                or self_model.get("derived_evidence") is not True
                or self_model.get("interpretation") is not False):
            raise DevelopmentalModelReplacementError("prior_self_model_binding_invalid")
        result.update({"prior_self_model_projection_id": self_model["projection_id"],
            "prior_self_model_projection_digest": self_model["projection_digest"],
            "prior_self_model_source_tick": self_model["source_tick"]})
        bound += 1
    if epistemic is not None:
        if not isinstance(epistemic, Mapping):
            raise DevelopmentalModelReplacementError("prior_epistemic_state_binding_invalid")
        states = epistemic.get("states")
        if (type(epistemic.get("source_tick")) is not int or epistemic["source_tick"] >= current_tick
                or not isinstance(states, (list, tuple)) or len(states) > 64):
            raise DevelopmentalModelReplacementError("prior_epistemic_state_binding_invalid")
        state_ids, state_digests = [], []
        for state in states:
            if not isinstance(state, Mapping):
                raise DevelopmentalModelReplacementError("prior_epistemic_state_binding_invalid")
            state_semantic = {key: value for key, value in state.items()
                if key not in {"state_id", "state_digest"}}
            state_digest = _digest(state_semantic)
            authority = state.get("authority")
            if (state.get("state_digest") != state_digest
                    or state.get("state_id") != "epistemic-state:" + state_digest[7:31]
                    or type(state.get("generation")) is not int
                    or not isinstance(authority, Mapping) or any(authority.values())):
                raise DevelopmentalModelReplacementError("prior_epistemic_state_binding_invalid")
            state_ids.append(state["state_id"])
            state_digests.append(state["state_digest"])
        bindings = {"source_tick": epistemic["source_tick"],
            "proposition_ids": epistemic.get("proposition_ids"),
            "state_ids": epistemic.get("state_ids"),
            "state_digests": epistemic.get("state_digests"),
            "generations": epistemic.get("generations"),
            "evidence_set_digests": epistemic.get("evidence_set_digests"),
            "states": states, "evidence_only": False, "prior_position_only": True,
            "current_truth": False, "authority": False, "policy": False, "goal": False}
        calculated = _digest(bindings)
        if (epistemic.get("projection_digest") != calculated
                or epistemic.get("projection_id") != "epistemic-projection:" + calculated[7:31]
                or epistemic.get("evidence_only") is not False
                or epistemic.get("prior_position_only") is not True
                or epistemic.get("current_truth") is not False
                or epistemic.get("authority") is not False
                or epistemic.get("policy") is not False
                or epistemic.get("goal") is not False
                or tuple(epistemic.get("proposition_ids", ())) != tuple(
                    str(state.get("proposition_id", "")) for state in states)
                or tuple(epistemic.get("state_ids", ())) != tuple(state_ids)
                or tuple(epistemic.get("state_digests", ())) != tuple(state_digests)
                or tuple(epistemic.get("generations", ())) != tuple(
                    int(state.get("generation", -1)) for state in states)
                or tuple(epistemic.get("evidence_set_digests", ())) != tuple(
                    str(state.get("evidence_set_digest", "")) for state in states)):
            raise DevelopmentalModelReplacementError("prior_epistemic_state_binding_invalid")
        result.update({"prior_epistemic_projection_id": epistemic["projection_id"],
            "prior_epistemic_projection_digest": epistemic["projection_digest"],
            "prior_epistemic_source_tick": epistemic["source_tick"],
            "prior_epistemic_state_ids": list(state_ids),
            "prior_epistemic_state_digests": list(state_digests)})
        bound += 1
    result["prior_cognitive_context_posture"] = (
        "verified_prior_self_and_epistemic_projections" if bound == 2 else
        "verified_partial_prior_cognitive_context" if bound == 1 else "not_bound")
    return result


def _validate_prior_binding_manifest(value: Mapping[str, Any]) -> None:
    expected_keys = {"prior_self_model_projection_id", "prior_self_model_projection_digest",
        "prior_self_model_source_tick", "prior_epistemic_projection_id",
        "prior_epistemic_projection_digest", "prior_epistemic_source_tick",
        "prior_epistemic_state_ids", "prior_epistemic_state_digests",
        "prior_cognitive_context_posture"}
    if set(value) != expected_keys:
        raise DevelopmentalModelReplacementError("context_prior_binding_shape_invalid")
    self_bound = value.get("prior_self_model_projection_id") is not None
    epistemic_bound = value.get("prior_epistemic_projection_id") is not None
    for stem, bound in (("prior_self_model", self_bound), ("prior_epistemic", epistemic_bound)):
        identity, identity_digest, source_tick = (value.get(stem + suffix) for suffix in
            ("_projection_id", "_projection_digest", "_source_tick"))
        source_valid = (type(source_tick) is int and source_tick >= 0 if stem == "prior_epistemic"
            else isinstance(source_tick, str) and bool(source_tick))
        if bound != (isinstance(identity, str) and bool(identity)
                and isinstance(identity_digest, str) and bool(identity_digest) and source_valid):
            raise DevelopmentalModelReplacementError("context_prior_binding_identity_invalid")
    state_ids, state_digests = value.get("prior_epistemic_state_ids"), value.get("prior_epistemic_state_digests")
    if (not isinstance(state_ids, list) or not isinstance(state_digests, list)
            or len(state_ids) != len(state_digests) or len(state_ids) > 64
            or any(not isinstance(item, str) or not item for item in (*state_ids, *state_digests))
            or (not epistemic_bound and (state_ids or state_digests))):
        raise DevelopmentalModelReplacementError("context_prior_binding_state_lineage_invalid")
    posture = ("verified_prior_self_and_epistemic_projections" if self_bound and epistemic_bound else
        "verified_partial_prior_cognitive_context" if self_bound or epistemic_bound else "not_bound")
    if value.get("prior_cognitive_context_posture") != posture:
        raise DevelopmentalModelReplacementError("context_prior_binding_posture_invalid")


def _resource_receipt_binding(receipt: Mapping[str, Any]) -> dict[str, Any]:
    allocation = receipt.get("resource_allocation_digest")
    attempt = receipt.get("resource_attempt_id")
    consumption = receipt.get("resource_consumption_receipt_digests", ())
    linkage = receipt.get("resource_linkage_digest")
    if not isinstance(consumption, (list, tuple)):
        raise DevelopmentalModelReplacementError("inference_resource_linkage_invalid")
    values = tuple(consumption)
    if allocation is None and attempt is None and not values and linkage is None:
        return {"resource_allocation_digest": None, "resource_attempt_id": None,
            "resource_consumption_receipt_digests": [], "resource_linkage_digest": None,
            "resource_attribution_posture": "no_resource_linkage_supplied"}
    if (not isinstance(allocation, str) or len(allocation) != 64
            or any(character not in "0123456789abcdef" for character in allocation)
            or not isinstance(attempt, str) or not attempt.startswith("lmattempt-")
            or len(attempt) > 128
            or not values or any(not isinstance(item, str) or len(item) != 64
                or any(character not in "0123456789abcdef" for character in item)
                for item in values)
            or not isinstance(receipt.get("inference_receipt_digest"), str)
            or len(receipt["inference_receipt_digest"]) != 64
            or any(character not in "0123456789abcdef" for character in receipt["inference_receipt_digest"])
            or not isinstance(linkage, str)
            or len(linkage) != 64
            or any(character not in "0123456789abcdef" for character in linkage)
            or linkage != digest_payload({"receipt_digest": receipt.get("inference_receipt_digest"),
                "allocation_digest": allocation, "attempt_id": attempt,
                "consumption_receipt_digests": values})):
        raise DevelopmentalModelReplacementError("inference_resource_linkage_invalid")
    return {"resource_allocation_digest": allocation, "resource_attempt_id": attempt,
        "resource_consumption_receipt_digests": list(values),
        "resource_linkage_digest": linkage,
        "resource_attribution_posture": "linkage_digest_bound_ledger_reconciliation_pending"}


def _inference_failure_evidence(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Keep bounded receipt identities from a failed call, never generated text."""
    value: dict[str, Any] = {"status": "failed_or_incomplete_inference_receipt"}
    for key in ("status", "fallback_occurred", "request_id", "request_digest",
            "inference_receipt_id", "inference_receipt_digest", "output_digest",
            "resource_allocation_digest", "resource_attempt_id", "resource_linkage_digest"):
        item = receipt.get(key)
        if isinstance(item, (str, bool)) and (not isinstance(item, str) or len(item) <= 256):
            value[key] = item
    consumption = receipt.get("resource_consumption_receipt_digests")
    if isinstance(consumption, (tuple, list)) and len(consumption) <= 16:
        if all(isinstance(item, str) and len(item) <= 128 for item in consumption):
            value["resource_consumption_receipt_digests"] = list(consumption)
    return value
COMPARISONS = (
    "history_effect_model_a", "history_effect_model_b",
    "model_difference_with_history", "model_difference_without_history",
    "model_a_restoration",
)
NON_CLAIMS = (
    "model_independent_identity", "persistent_individuality", "sentience",
    "consciousness", "selfhood", "learning", "causal_closure",
)
DEFAULT_TRIAL_ID = "single-trial"
MAX_TRIAL_ID_LENGTH = 128
EPISTEMIC_POSTURES = frozenset({
    "locally_observed_identity", "source_bound_reported_claim",
    "operator_attested_claim", "cryptographically_bound_attestation", "unknown",
})


class DevelopmentalModelReplacementError(ValueError):
    """A fail-closed experimental-control or custody violation."""

    def __init__(self, code: str, *, evidence: Mapping[str, Any] | None = None) -> None:
        self.evidence = dict(evidence) if evidence is not None else None
        super().__init__(code)


def _digest(value: Any) -> str:
    return "sha256:" + cast(str, digest_payload(value))


def _identity_payload(identity: "CognitiveModelIdentity") -> dict[str, Any]:
    value = asdict(identity)
    value.pop("identity_digest", None)
    return value


@dataclass(frozen=True)
class CognitiveModelIdentity:
    model_id: str
    semantic_artifact_identity: str
    model_content_sha256: str
    artifact_size_bytes: int | None
    sidecar_metadata_digest: str | None
    configuration_digest: str
    engine_runtime_family: str
    candidate_index: int | None
    active_production: bool
    fallback: bool
    authority_record_id: str
    authority_record_digest: str
    active_model_identity: Mapping[str, Any]
    active_model_identity_digest: str
    identity_digest: str = ""

    @classmethod
    def create(cls, **kwargs: Any) -> "CognitiveModelIdentity":
        raw = cls(**kwargs)
        return replace(raw, identity_digest=_digest(_identity_payload(raw)))

    def verify(self) -> None:
        required = (self.model_id, self.semantic_artifact_identity,
                    self.model_content_sha256, self.configuration_digest,
                    self.engine_runtime_family, self.authority_record_id,
                    self.authority_record_digest, self.active_model_identity_digest)
        if not all(required) or not self.active_production or self.fallback:
            raise DevelopmentalModelReplacementError("model_identity_not_production_eligible")
        if self.active_model_identity_digest != _digest(dict(self.active_model_identity)):
            raise DevelopmentalModelReplacementError("active_model_identity_digest_mismatch")
        observed = self.active_model_identity
        identity_bindings = {
            "semantic_artifact_identity": self.semantic_artifact_identity,
            "model_content_sha256": self.model_content_sha256,
            "artifact_size_bytes": self.artifact_size_bytes,
            "sidecar_metadata_digest": self.sidecar_metadata_digest,
            "configuration_digest": self.configuration_digest,
            "engine": self.engine_runtime_family,
            "candidate_index": self.candidate_index,
        }
        if (not isinstance(observed, Mapping)
                or any(observed.get(key) != value for key, value in identity_bindings.items())
                or observed.get("posture") != "production"
                or observed.get("fallback") is not False):
            raise DevelopmentalModelReplacementError("model_identity_active_observation_mismatch")
        if self.identity_digest != _digest(_identity_payload(self)):
            raise DevelopmentalModelReplacementError("model_identity_digest_mismatch")

    def semantic_key(self) -> tuple[str, str, str]:
        return (self.semantic_artifact_identity, self.model_content_sha256,
                self.configuration_digest)


@dataclass(frozen=True)
class ModelDevelopmentClaim:
    claim_id: str
    claim_digest: str
    subject_identity_digest: str
    relation_type: str
    claimed_parent_or_teacher: str | None
    evidence_kind: str
    source_reference: str | None
    evidence_digest: str | None
    epistemic_posture: str

    @classmethod
    def create(cls, **kwargs: Any) -> "ModelDevelopmentClaim":
        raw = cls("", "", **kwargs)
        payload = asdict(raw); payload.pop("claim_id"); payload.pop("claim_digest")
        digest = _digest(payload)
        return replace(raw, claim_id="model-claim-" + digest[7:31], claim_digest=digest)

    def verify(self, subject: CognitiveModelIdentity) -> None:
        subject.verify()
        self.verify_subject_digest(subject.identity_digest)

    def verify_subject_digest(self, subject_identity_digest: str) -> None:
        payload = asdict(self); payload.pop("claim_id"); payload.pop("claim_digest")
        digest = _digest(payload)
        if self.claim_digest != digest or self.claim_id != "model-claim-" + digest[7:31]:
            raise DevelopmentalModelReplacementError("provenance_claim_digest_mismatch")
        if self.subject_identity_digest != subject_identity_digest:
            raise DevelopmentalModelReplacementError("provenance_subject_mismatch")
        string_values = (self.claim_id, self.subject_identity_digest, self.relation_type,
                         self.evidence_kind, self.epistemic_posture)
        if (any(not isinstance(value, str) or not value or len(value) > 512 for value in string_values)
                or (self.claimed_parent_or_teacher is not None and
                    (not isinstance(self.claimed_parent_or_teacher, str) or len(self.claimed_parent_or_teacher) > 2048))
                or (self.source_reference is not None and
                    (not isinstance(self.source_reference, str) or len(self.source_reference) > 2048))
                or (self.evidence_digest is not None and
                    (not isinstance(self.evidence_digest, str) or len(self.evidence_digest) > 256))):
            raise DevelopmentalModelReplacementError("provenance_claim_fields_invalid")
        if self.epistemic_posture not in EPISTEMIC_POSTURES:
            raise DevelopmentalModelReplacementError("provenance_posture_invalid")


@dataclass(frozen=True)
class ModelDevelopmentProvenance:
    subject_identity_digest: str
    claims: tuple[ModelDevelopmentClaim, ...]
    availability: str
    grants_authority: bool
    manifest_digest: str
    schema_version: str = PROVENANCE_SCHEMA

    @classmethod
    def create(cls, subject: CognitiveModelIdentity,
               claims: Sequence[ModelDevelopmentClaim] = ()) -> "ModelDevelopmentProvenance":
        availability = "source_bound_evidence_available" if claims else "unknown"
        raw = cls(subject.identity_digest, tuple(claims), availability, False, "")
        payload = asdict(raw); payload.pop("manifest_digest")
        return replace(raw, manifest_digest=_digest(payload))

    def verify(self, subject: CognitiveModelIdentity) -> None:
        subject.verify()
        payload = asdict(self); payload.pop("manifest_digest")
        if self.manifest_digest != _digest(payload) or self.grants_authority:
            raise DevelopmentalModelReplacementError("provenance_manifest_digest_mismatch")
        if self.subject_identity_digest != subject.identity_digest:
            raise DevelopmentalModelReplacementError("provenance_subject_mismatch")
        if (len(self.claims) > MAX_PROVENANCE_CLAIMS
                or self.availability not in {"source_bound_evidence_available", "unknown"}
                or (not self.claims and self.availability != "unknown")
                or (self.claims and self.availability != "source_bound_evidence_available")):
            raise DevelopmentalModelReplacementError("provenance_availability_or_bounds_invalid")
        for claim in self.claims:
            claim.verify_subject_digest(subject.identity_digest)


@dataclass(frozen=True)
class FrozenCausalContext:
    context_id: str
    context_digest: str
    snapshot_id: str
    snapshot_digest: str
    current_projection_id: str
    current_projection_digest: str
    current_fact_ids: tuple[str, ...]
    projected_content_digest: str
    current_projection_payload: Mapping[str, Any]
    history_record_ids: tuple[str, ...]
    history_record_digests: tuple[str, ...]
    history_record_set_digest: str
    history_projection_payload: tuple[Mapping[str, Any], ...]
    instruction_template: str
    instruction_template_digest: str
    inference_budget: Mapping[str, Any]
    generation_posture: Mapping[str, Any]
    repository_generation_identity: str | None
    schema_version: str = CONTEXT_SCHEMA

    @classmethod
    def create(cls, **kwargs: Any) -> "FrozenCausalContext":
        raw = cls("", "", **kwargs)
        payload = asdict(raw); payload.pop("context_id"); payload.pop("context_digest")
        digest = _digest(payload)
        return replace(raw, context_id="model-replacement-context-" + digest[7:31], context_digest=digest)

    def verify(self) -> None:
        payload = asdict(self); payload.pop("context_id"); payload.pop("context_digest")
        digest = _digest(payload)
        if self.context_digest != digest or self.context_id != "model-replacement-context-" + digest[7:31]:
            raise DevelopmentalModelReplacementError("causal_context_digest_mismatch")
        if self.projected_content_digest != _digest(dict(self.current_projection_payload)):
            raise DevelopmentalModelReplacementError("current_projection_content_mismatch")
        if (len(self.current_fact_ids) > 64 or len(set(self.current_fact_ids)) != len(self.current_fact_ids)
                or len(self.history_record_ids) > 64
                or len(self.history_record_ids) != len(self.history_record_digests)
                or len(self.history_record_ids) != len(self.history_projection_payload)
                or any(not isinstance(item, str) or not item for item in self.history_record_ids)
                or any(not isinstance(item, str) or not item.startswith("sha256:")
                    for item in self.history_record_digests)):
            raise DevelopmentalModelReplacementError("causal_context_evidence_bounds_invalid")
        history = {"record_ids": list(self.history_record_ids),
                   "record_digests": list(self.history_record_digests)}
        if self.history_record_set_digest != _digest(history):
            raise DevelopmentalModelReplacementError("history_record_set_digest_mismatch")
        if self.instruction_template_digest != _digest({"instruction": self.instruction_template}):
            raise DevelopmentalModelReplacementError("instruction_template_digest_mismatch")
        if self.generation_posture.get("temperature") != 0:
            raise DevelopmentalModelReplacementError("temperature_zero_required")
        _prior_cognition_bindings(self.current_projection_payload)

    def identity_manifest(self) -> dict[str, Any]:
        self.verify()
        semantic = {"schema_version": CONTEXT_BINDING_SCHEMA,
            "context_id": self.context_id, "context_digest": self.context_digest,
            "snapshot_id": self.snapshot_id, "snapshot_digest": self.snapshot_digest,
            "current_projection_id": self.current_projection_id,
            "current_projection_digest": self.current_projection_digest,
            "current_fact_ids": list(self.current_fact_ids),
            "projected_content_digest": self.projected_content_digest,
            "history_record_ids": list(self.history_record_ids),
            "history_record_digests": list(self.history_record_digests),
            "history_record_set_digest": self.history_record_set_digest,
            "instruction_template_digest": self.instruction_template_digest,
            "inference_budget": dict(self.inference_budget),
            "generation_posture": dict(self.generation_posture),
            "repository_generation_identity": self.repository_generation_identity,
            "prior_cognition_bindings": _prior_cognition_bindings(self.current_projection_payload),
            "authority": False}
        return {**semantic, "context_manifest_digest": _digest(semantic)}


@dataclass(frozen=True)
class ModelReplacementProtocol:
    protocol_id: str
    protocol_digest: str
    causal_context_id: str
    causal_context_digest: str
    model_a_identity: CognitiveModelIdentity
    model_b_identity: CognitiveModelIdentity
    model_a_provenance_digest: str
    model_b_provenance_digest: str
    inference_purpose: str
    inference_budget: Mapping[str, Any]
    generation_posture: Mapping[str, Any]
    instruction_template_digest: str
    condition_order: tuple[str, ...] = CONDITION_ORDER
    planned_comparisons: tuple[str, ...] = COMPARISONS
    non_claims: tuple[str, ...] = NON_CLAIMS
    grants_authority: bool = False
    schema_version: str = PROTOCOL_SCHEMA

    @classmethod
    def create(cls, context: FrozenCausalContext, model_a: CognitiveModelIdentity,
               model_b: CognitiveModelIdentity, provenance_a: ModelDevelopmentProvenance,
               provenance_b: ModelDevelopmentProvenance) -> "ModelReplacementProtocol":
        raw = cls("", "", context.context_id, context.context_digest, model_a, model_b,
                  provenance_a.manifest_digest, provenance_b.manifest_digest, PURPOSE,
                  dict(context.inference_budget), dict(context.generation_posture),
                  context.instruction_template_digest)
        payload = asdict(raw); payload.pop("protocol_id"); payload.pop("protocol_digest")
        digest = _digest(payload)
        return replace(raw, protocol_id="model-replacement-protocol-" + digest[7:31], protocol_digest=digest)

    def verify(self) -> None:
        payload = asdict(self); payload.pop("protocol_id"); payload.pop("protocol_digest")
        digest = _digest(payload)
        if self.protocol_digest != digest or self.protocol_id != "model-replacement-protocol-" + digest[7:31]:
            raise DevelopmentalModelReplacementError("protocol_digest_mismatch")
        self.model_a_identity.verify(); self.model_b_identity.verify()
        if self.model_a_identity.semantic_key() == self.model_b_identity.semantic_key():
            raise DevelopmentalModelReplacementError("experimental_models_not_distinct")
        if (self.condition_order != CONDITION_ORDER or self.planned_comparisons != COMPARISONS
                or self.inference_purpose != PURPOSE or self.grants_authority):
            raise DevelopmentalModelReplacementError("protocol_control_invalid")


class GovernedCognitiveEndpoint(Protocol):
    def current_identity(self) -> CognitiveModelIdentity: ...
    def infer(self, *, purpose: str, prompt: str, correlation_id: str,
              budget: Mapping[str, Any], generation_posture: Mapping[str, Any],
              upstream_evidence: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ModelReplacementArtifactStore:
    def __init__(self, state_root: Path, *, read_only: bool = False) -> None:
        selected_root = Path(state_root)
        if selected_root.is_symlink() or any(parent.is_symlink() for parent in selected_root.parents):
            raise DevelopmentalModelReplacementError("artifact_store_state_root_symlink")
        self.state_root = selected_root.resolve()
        self.root = self.state_root / "developmental_experiments" / "model_replacement"
        self.protocols = self.root / "protocols"
        self.contexts = self.root / "contexts"
        self.provenance = self.root / "provenance"
        self.runs = self.root / "runs"
        self.condition_starts = self.root / "condition-starts"
        self.condition_results = self.root / "condition-results"
        self.read_only = read_only

    @staticmethod
    def _require_descriptor_storage() -> None:
        required = (os.open, os.mkdir, os.link, os.unlink)
        if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
                or any(function not in os.supports_dir_fd for function in required)):
            raise DevelopmentalModelReplacementError("artifact_store_unsupported_platform")

    def _open_kind_directory(self, kind: str, *, create: bool) -> int:
        if kind not in {"provenance", "protocols", "contexts", "runs", "condition-starts", "condition-results"}:
            raise DevelopmentalModelReplacementError("artifact_store_path_invalid")
        self._require_descriptor_storage()
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
        try:
            descriptor = os.open(os.sep, flags)
            components = (*self.state_root.parts[1:], "developmental_experiments",
                "model_replacement", kind)
            for component in components:
                if create:
                    try:
                        os.mkdir(component, 0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
                metadata = os.fstat(next_descriptor)
                if not stat.S_ISDIR(metadata.st_mode):
                    os.close(next_descriptor)
                    raise DevelopmentalModelReplacementError("artifact_store_path_invalid")
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except DevelopmentalModelReplacementError:
            if "descriptor" in locals():
                os.close(descriptor)
            raise
        except OSError as exc:
            if "descriptor" in locals():
                os.close(descriptor)
            if isinstance(exc, FileNotFoundError):
                raise
            raise DevelopmentalModelReplacementError("artifact_store_path_invalid") from exc

    def _artifact_location(self, path: Path) -> tuple[str, str]:
        try:
            relative = path.relative_to(self.root)
        except ValueError as exc:
            raise DevelopmentalModelReplacementError("artifact_store_path_invalid") from exc
        if len(relative.parts) != 2 or relative.parts[0] not in {"provenance", "protocols", "contexts", "runs",
                "condition-starts", "condition-results"}:
            raise DevelopmentalModelReplacementError("artifact_store_path_invalid")
        if not relative.parts[1] or relative.parts[1] in {".", ".."}:
            raise DevelopmentalModelReplacementError("artifact_store_path_invalid")
        return relative.parts[0], relative.parts[1]

    def _write(self, path: Path, payload: Mapping[str, Any]) -> bool:
        if self.read_only:
            raise DevelopmentalModelReplacementError("artifact_store_read_only")
        normalized = json.loads(json.dumps(dict(payload), sort_keys=True))
        limits = {"provenance": MAX_PROVENANCE_ARTIFACT_BYTES,
            "protocols": MAX_PROTOCOL_ARTIFACT_BYTES, "contexts": MAX_CONTEXT_ARTIFACT_BYTES,
            "runs": MAX_RUN_ARTIFACT_BYTES,
            "condition-starts": MAX_CONDITION_ARTIFACT_BYTES,
            "condition-results": MAX_CONDITION_ARTIFACT_BYTES}
        kind, filename = self._artifact_location(path)
        maximum = limits[kind]
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True).encode("utf-8")
        if len(encoded) > maximum:
            raise DevelopmentalModelReplacementError("artifact_size_limit_exceeded")
        directory_fd = self._open_kind_directory(kind, create=True)
        temporary_name: str | None = None
        try:
            try:
                existing_fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            except FileNotFoundError:
                existing_fd = None
            except OSError as exc:
                raise DevelopmentalModelReplacementError("artifact_tampered") from exc
            if existing_fd is None:
                prior = None
            else:
                os.close(existing_fd)
                prior = self._read_artifact_json(path, maximum_bytes=maximum,
                    missing_code="artifact_missing", invalid_code="artifact_tampered")
            if prior is not None:
                if prior != normalized:
                    raise DevelopmentalModelReplacementError("artifact_identity_collision")
                return False
            temporary_name = ".model-replacement-" + secrets.token_hex(16) + ".tmp"
            descriptor = os.open(temporary_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600, dir_fd=directory_fd)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary_name, filename, src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd, follow_symlinks=False)
            except FileExistsError:
                prior = self._read_artifact_json(path, maximum_bytes=maximum,
                    missing_code="artifact_missing", invalid_code="artifact_tampered")
                if prior != normalized:
                    raise DevelopmentalModelReplacementError("artifact_identity_collision")
                return False
            os.fsync(directory_fd)
            return True
        except OSError as exc:
            raise DevelopmentalModelReplacementError("artifact_publication_failed") from exc
        finally:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name, dir_fd=directory_fd)
                    os.fsync(directory_fd)
                except FileNotFoundError:
                    pass
            os.close(directory_fd)

    def _read_artifact_json(self, path: Path, *, maximum_bytes: int,
                            missing_code: str, invalid_code: str) -> dict[str, Any]:
        kind, filename = self._artifact_location(path)
        descriptor: int | None = None
        directory_fd: int | None = None
        try:
            directory_fd = self._open_kind_directory(kind, create=False)
            descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum_bytes:
                raise DevelopmentalModelReplacementError(invalid_code)
            chunks: list[bytes] = []
            remaining = metadata.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 65536))
                if not chunk:
                    raise DevelopmentalModelReplacementError(invalid_code)
                chunks.append(chunk)
                remaining -= len(chunk)
            value = json.loads(b"".join(chunks).decode("utf-8"))
            if not isinstance(value, dict):
                raise DevelopmentalModelReplacementError(invalid_code)
            return value
        except FileNotFoundError as exc:
            raise DevelopmentalModelReplacementError(missing_code) from exc
        except DevelopmentalModelReplacementError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise DevelopmentalModelReplacementError(invalid_code) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory_fd is not None:
                os.close(directory_fd)

    def persist_provenance(self, manifest: ModelDevelopmentProvenance) -> None:
        payload = asdict(manifest)
        claimed_digest = payload.pop("manifest_digest", None)
        if (manifest.schema_version != PROVENANCE_SCHEMA or manifest.grants_authority is not False
                or not isinstance(claimed_digest, str) or len(claimed_digest) != 71
                or not claimed_digest.startswith("sha256:")
                or any(character not in "0123456789abcdef" for character in claimed_digest[7:])
                or claimed_digest != _digest(payload)
                or not isinstance(manifest.subject_identity_digest, str)
                or not manifest.subject_identity_digest.startswith("sha256:")
                or len(manifest.subject_identity_digest) != 71
                or any(character not in "0123456789abcdef"
                    for character in manifest.subject_identity_digest[7:])
                or not isinstance(manifest.claims, tuple)
                or len(manifest.claims) > MAX_PROVENANCE_CLAIMS
                or not isinstance(manifest.availability, str)
                or manifest.availability not in {"source_bound_evidence_available", "unknown"}
                or (not manifest.claims and manifest.availability != "unknown")
                or (manifest.claims and manifest.availability != "source_bound_evidence_available")
                or any(not isinstance(claim, ModelDevelopmentClaim)
                    for claim in manifest.claims)):
            raise DevelopmentalModelReplacementError("provenance_manifest_invalid")
        for claim in manifest.claims:
            claim.verify_subject_digest(manifest.subject_identity_digest)
        self._write(self.provenance / f"{manifest.manifest_digest[7:]}.json", asdict(manifest))

    def load_verified_provenance(self, manifest_digest: str,
                                 subject: CognitiveModelIdentity) -> ModelDevelopmentProvenance:
        """Load one exact, content-addressed manifest and verify its model subject.

        A digest identifies stored bytes; ``verify`` checks the manifest and
        each claim against the supplied independently verified model identity.
        This method does not treat a manifest as evidence that a model is
        installed, active, or running.
        """
        subject.verify()
        if (not isinstance(manifest_digest, str) or not manifest_digest.startswith("sha256:")
                or len(manifest_digest) != 71
                or any(character not in "0123456789abcdef" for character in manifest_digest[7:])):
            raise DevelopmentalModelReplacementError("provenance_manifest_reference_invalid")
        path = self.provenance / f"{manifest_digest[7:]}.json"
        value = self._read_artifact_json(path, maximum_bytes=MAX_PROVENANCE_ARTIFACT_BYTES,
            missing_code="provenance_manifest_unavailable",
            invalid_code="provenance_manifest_unbounded_or_not_regular")
        raw_claims = value.get("claims")
        if not isinstance(raw_claims, list) or len(raw_claims) > MAX_PROVENANCE_CLAIMS:
            raise DevelopmentalModelReplacementError("provenance_claim_retention_limit_exceeded")
        try:
            value["claims"] = tuple(ModelDevelopmentClaim(**row) for row in raw_claims)
            manifest = ModelDevelopmentProvenance(**value)
        except (KeyError, TypeError, ValueError) as exc:
            raise DevelopmentalModelReplacementError("provenance_manifest_invalid") from exc
        if (path.stem != manifest_digest[7:]
                or manifest.manifest_digest != manifest_digest
                or manifest.subject_identity_digest != subject.identity_digest):
            raise DevelopmentalModelReplacementError("provenance_manifest_subject_or_path_mismatch")
        manifest.verify(subject)
        return manifest

    def load_verified_protocol_provenance(self, protocol_id: str, protocol_digest: str,
                                          *, model_role: str) -> tuple[ModelReplacementProtocol,
                                                                       CognitiveModelIdentity,
                                                                       ModelDevelopmentProvenance]:
        """Load a preregistered model identity and its exact provenance manifest."""
        if model_role not in {"model_a", "model_b"}:
            raise DevelopmentalModelReplacementError("provenance_model_role_invalid")
        protocol = self.load_verified_protocol(protocol_id, protocol_digest)
        identity = protocol.model_a_identity if model_role == "model_a" else protocol.model_b_identity
        manifest_digest = (protocol.model_a_provenance_digest if model_role == "model_a"
                           else protocol.model_b_provenance_digest)
        provenance = self.load_verified_provenance(manifest_digest, identity)
        return protocol, identity, provenance

    def persist_protocol(self, protocol: ModelReplacementProtocol) -> None:
        protocol.verify()
        self._write(self.protocols / f"{protocol.protocol_id}.json", asdict(protocol))

    def persist_context(self, context: FrozenCausalContext) -> None:
        manifest = context.identity_manifest()
        self._write(self.contexts / f"{context.context_id}.json", manifest)

    def load_verified_context(self, context_id: str, context_digest: str) -> dict[str, Any]:
        prefix = "model-replacement-context-"
        if (not isinstance(context_id, str) or len(context_id) != len(prefix) + 24
                or not context_id.startswith(prefix)
                or any(character not in "0123456789abcdef" for character in context_id[len(prefix):])
                or not isinstance(context_digest, str) or len(context_digest) != 71
                or not context_digest.startswith("sha256:")
                or any(character not in "0123456789abcdef" for character in context_digest[7:])):
            raise DevelopmentalModelReplacementError("context_artifact_identity_invalid")
        path = self.contexts / f"{context_id}.json"
        try:
            value = self._read_artifact_json(path, maximum_bytes=MAX_CONTEXT_ARTIFACT_BYTES,
                missing_code="context_artifact_unavailable", invalid_code="context_artifact_invalid")
            manifest_digest = value.get("context_manifest_digest")
            semantic = {key: item for key, item in value.items()
                if key != "context_manifest_digest"}
            history_ids = value.get("history_record_ids")
            history_digests = value.get("history_record_digests")
            current_fact_ids = value.get("current_fact_ids")
            prior_bindings = value.get("prior_cognition_bindings")
            if (value.get("schema_version") != CONTEXT_BINDING_SCHEMA
                    or manifest_digest != _digest(semantic)
                    or value.get("context_id") != context_id
                    or value.get("context_digest") != context_digest
                    or value.get("authority") is not False
                    or not all(isinstance(value.get(key), str) and value.get(key) for key in (
                        "snapshot_id", "snapshot_digest", "current_projection_id",
                        "current_projection_digest", "projected_content_digest",
                        "instruction_template_digest"))
                    or any(len(value.get(key, "")) != 71 or not value[key].startswith("sha256:")
                        or any(character not in "0123456789abcdef" for character in value[key][7:])
                        for key in ("snapshot_digest", "current_projection_digest",
                            "projected_content_digest", "instruction_template_digest"))
                    or not isinstance(value.get("inference_budget"), Mapping)
                    or not isinstance(value.get("generation_posture"), Mapping)
                    or value.get("generation_posture", {}).get("temperature") != 0
                    or not isinstance(history_ids, list) or not isinstance(history_digests, list)
                    or len(history_ids) != len(history_digests) or len(history_ids) > 64
                    or len(set(history_ids)) != len(history_ids)
                    or any(not isinstance(item, str) or not item for item in history_ids)
                    or any(not isinstance(item, str) or len(item) != 71 or not item.startswith("sha256:")
                        or any(character not in "0123456789abcdef" for character in item[7:])
                        for item in history_digests)
                    or value.get("history_record_set_digest") != _digest({
                        "record_ids": history_ids, "record_digests": history_digests})
                    or not isinstance(current_fact_ids, list) or len(current_fact_ids) > 64
                    or any(not isinstance(item, str) or not item for item in current_fact_ids)
                    or len(set(current_fact_ids)) != len(current_fact_ids)
                    or not isinstance(prior_bindings, Mapping)
                    or prior_bindings.get("prior_cognitive_context_posture") not in {
                        "not_bound", "verified_partial_prior_cognitive_context",
                        "verified_prior_self_and_epistemic_projections"}):
                raise DevelopmentalModelReplacementError("context_artifact_invalid")
            _validate_prior_binding_manifest(prior_bindings)
        except DevelopmentalModelReplacementError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise DevelopmentalModelReplacementError("context_artifact_invalid") from exc
        if context_id != "model-replacement-context-" + context_digest[7:31]:
            raise DevelopmentalModelReplacementError("context_artifact_identity_mismatch")
        return value

    def verify_protocol_bytes(self, protocol: ModelReplacementProtocol) -> None:
        path = self.protocols / f"{protocol.protocol_id}.json"
        expected = json.loads(json.dumps(asdict(protocol), sort_keys=True))
        stored = self._read_artifact_json(path, maximum_bytes=MAX_PROTOCOL_ARTIFACT_BYTES,
            missing_code="preregistered_protocol_unavailable", invalid_code="protocol_artifact_invalid")
        if stored != expected:
            raise DevelopmentalModelReplacementError("protocol_custody_changed")

    def load_verified_protocol(self, protocol_id: str, protocol_digest: str) -> ModelReplacementProtocol:
        """Load an already-persisted protocol; never construct or repair one."""
        protocol_prefix = "model-replacement-protocol-"
        if (not isinstance(protocol_id, str) or len(protocol_id) != len(protocol_prefix) + 24
                or not protocol_id.startswith(protocol_prefix)
                or any(character not in "0123456789abcdef" for character in protocol_id[len(protocol_prefix):])
                or not isinstance(protocol_digest, str) or len(protocol_digest) != 71
                or not protocol_digest.startswith("sha256:")
                or any(character not in "0123456789abcdef" for character in protocol_digest[7:])):
            raise DevelopmentalModelReplacementError("protocol_identity_invalid")
        path = self.protocols / f"{protocol_id}.json"
        try:
            value = self._read_artifact_json(path, maximum_bytes=MAX_PROTOCOL_ARTIFACT_BYTES,
                missing_code="preregistered_protocol_unavailable", invalid_code="protocol_artifact_invalid")
            for role in ("model_a_identity", "model_b_identity"):
                value[role] = CognitiveModelIdentity(**value[role])
            value["condition_order"] = tuple(value["condition_order"])
            value["planned_comparisons"] = tuple(value["planned_comparisons"])
            value["non_claims"] = tuple(value["non_claims"])
            protocol = ModelReplacementProtocol(**value)
        except DevelopmentalModelReplacementError:
            raise
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise DevelopmentalModelReplacementError("protocol_artifact_invalid") from exc
        if protocol.protocol_id != protocol_id or protocol.protocol_digest != protocol_digest:
            raise DevelopmentalModelReplacementError("protocol_identity_mismatch")
        protocol.verify()
        self.verify_protocol_bytes(protocol)
        return protocol

    @staticmethod
    def condition_artifact_id(*, protocol_id: str, trial_id: str,
                              condition: str) -> str:
        if (condition not in CONDITION_ORDER or not isinstance(protocol_id, str)
                or not protocol_id or not isinstance(trial_id, str) or not trial_id):
            raise DevelopmentalModelReplacementError("condition_artifact_selector_invalid")
        material = {"protocol_id": protocol_id, "trial_id": trial_id,
            "condition": condition}
        return "model-replacement-condition-" + _digest(material)[7:31]

    def begin_condition(self, *, protocol_id: str, protocol_digest: str,
                        trial_id: str, condition: str, input_digest: str,
                        correlation_id: str) -> tuple[bool, dict[str, Any]]:
        condition_id = self.condition_artifact_id(protocol_id=protocol_id,
            trial_id=trial_id, condition=condition)
        semantic = {"schema_version": CONDITION_START_SCHEMA,
            "condition_id": condition_id, "protocol_id": protocol_id,
            "protocol_digest": protocol_digest, "trial_id": trial_id,
            "condition": condition, "input_digest": input_digest,
            "correlation_id": correlation_id, "authority": False}
        record = {**semantic, "condition_start_digest": _digest(semantic)}
        created = self._write(self.condition_starts / f"{condition_id}.json", record)
        return created, record

    def finish_condition(self, *, start: Mapping[str, Any], status: str,
                         observation: Mapping[str, Any] | None,
                         failure_posture: str | None = None,
                         failure_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if status not in {"completed", "incomplete", "contradictory"}:
            raise DevelopmentalModelReplacementError("condition_terminal_status_invalid")
        if (status == "completed" and (failure_evidence is not None or failure_posture is not None)
                or (failure_evidence is not None and len(json.dumps(dict(failure_evidence),
                    sort_keys=True, separators=(",", ":")).encode()) > 16_384)):
            raise DevelopmentalModelReplacementError("condition_failure_evidence_invalid")
        condition_id = str(start.get("condition_id") or "")
        verified_start, existing = self.read_condition(condition_id=condition_id,
            expected_input_digest=str(start.get("input_digest") or ""))
        if verified_start != dict(start):
            raise DevelopmentalModelReplacementError("condition_start_binding_conflict")
        if existing is not None:
            expected = {"status": status,
                "observation": dict(observation) if observation is not None else None,
                "failure_posture": failure_posture,
                "failure_evidence": dict(failure_evidence) if failure_evidence is not None else None}
            if any(existing.get(key) != value for key, value in expected.items()):
                raise DevelopmentalModelReplacementError("condition_terminal_conflict")
            return existing
        semantic = {"schema_version": CONDITION_RESULT_SCHEMA,
            "condition_id": condition_id, "protocol_id": start["protocol_id"],
            "protocol_digest": start["protocol_digest"], "trial_id": start["trial_id"],
            "condition": start["condition"], "input_digest": start["input_digest"],
            "correlation_id": start["correlation_id"],
            "condition_start_digest": start["condition_start_digest"],
            "status": status,
            "observation": dict(observation) if observation is not None else None,
            "failure_posture": failure_posture,
            "failure_evidence": dict(failure_evidence) if failure_evidence is not None else None,
            "authority": False}
        record = {**semantic, "condition_result_digest": _digest(semantic)}
        self._write(self.condition_results / f"{condition_id}.json", record)
        return record

    def read_condition(self, *, condition_id: str,
                       expected_input_digest: str) -> tuple[dict[str, Any] | None,
                                                           dict[str, Any] | None]:
        start_path = self.condition_starts / f"{condition_id}.json"
        try:
            start = self._read_artifact_json(start_path, maximum_bytes=MAX_CONDITION_ARTIFACT_BYTES,
                missing_code="condition_start_missing", invalid_code="condition_start_invalid")
        except DevelopmentalModelReplacementError as exc:
            if str(exc) == "condition_start_missing":
                return None, None
            raise
        start_semantic = {key: item for key, item in start.items() if key != "condition_start_digest"}
        expected_id = self.condition_artifact_id(protocol_id=str(start.get("protocol_id") or ""),
            trial_id=str(start.get("trial_id") or ""), condition=str(start.get("condition") or ""))
        if (start.get("schema_version") != CONDITION_START_SCHEMA
                or start.get("condition_id") != condition_id or expected_id != condition_id
                or start.get("input_digest") != expected_input_digest or start.get("authority") is not False
                or start.get("condition_start_digest") != _digest(start_semantic)
                or start.get("correlation_id") != f"{start['protocol_id']}:{start['trial_id']}:{start['condition']}" ):
            raise DevelopmentalModelReplacementError("condition_start_digest_or_context_invalid")
        result_path = self.condition_results / f"{condition_id}.json"
        try:
            result = self._read_artifact_json(result_path, maximum_bytes=MAX_CONDITION_ARTIFACT_BYTES,
                missing_code="condition_result_missing", invalid_code="condition_result_invalid")
        except DevelopmentalModelReplacementError as exc:
            if str(exc) == "condition_result_missing":
                return start, None
            raise
        result_semantic = {key: item for key, item in result.items() if key != "condition_result_digest"}
        if (result.get("schema_version") != CONDITION_RESULT_SCHEMA
                or result.get("condition_id") != condition_id
                or result.get("protocol_id") != start.get("protocol_id")
                or result.get("protocol_digest") != start.get("protocol_digest")
                or result.get("trial_id") != start.get("trial_id")
                or result.get("condition") != start.get("condition")
                or result.get("input_digest") != start.get("input_digest")
                or result.get("correlation_id") != start.get("correlation_id")
                or result.get("condition_start_digest") != start.get("condition_start_digest")
                or result.get("authority") is not False
                or result.get("condition_result_digest") != _digest(result_semantic)
                or result.get("status") not in {"completed", "incomplete", "contradictory"}
                or (result.get("status") == "completed" and not isinstance(result.get("observation"), Mapping))
                or (result.get("status") == "incomplete" and result.get("observation") is not None)
                or (result.get("status") == "completed" and result.get("failure_evidence") is not None)
                or (result.get("status") == "completed" and result.get("failure_posture") is not None)
                or (result.get("failure_evidence") is not None
                    and (not isinstance(result.get("failure_evidence"), Mapping)
                        or len(json.dumps(result["failure_evidence"], sort_keys=True,
                            separators=(",", ":")).encode()) > 16_384))):
            raise DevelopmentalModelReplacementError("condition_terminal_lineage_invalid")
        return start, result

    def persist_run(self, semantic: Mapping[str, Any]) -> tuple[str, str]:
        payload = {**semantic, "schema_version": RUN_SCHEMA}
        digest = _digest(payload); run_id = "model-replacement-run-" + digest[7:31]
        self._write(self.runs / f"{run_id}.json", {**payload, "run_id": run_id, "run_digest": digest})
        return run_id, digest

    def load_verified_run(self, run_id: str, run_digest: str) -> dict[str, Any]:
        run_prefix = "model-replacement-run-"
        if (not isinstance(run_id, str) or len(run_id) != len(run_prefix) + 24
                or not run_id.startswith(run_prefix)
                or any(character not in "0123456789abcdef" for character in run_id[len(run_prefix):])
                or not isinstance(run_digest, str) or len(run_digest) != 71
                or not run_digest.startswith("sha256:")
                or any(character not in "0123456789abcdef" for character in run_digest[7:])
                or run_id != run_prefix + run_digest[7:31]):
            raise DevelopmentalModelReplacementError("trial_run_identity_invalid")
        path = self.runs / f"{run_id}.json"
        try:
            value = self._read_artifact_json(path, maximum_bytes=MAX_RUN_ARTIFACT_BYTES,
                missing_code="trial_run_artifact_unavailable", invalid_code="trial_run_artifact_invalid")
        except DevelopmentalModelReplacementError as exc:
            if str(exc) == "trial_run_artifact_invalid":
                raise DevelopmentalModelReplacementError("trial_run_artifact_tampered") from exc
            raise DevelopmentalModelReplacementError("trial_run_artifact_unavailable") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise DevelopmentalModelReplacementError("trial_run_artifact_unavailable") from exc
        semantic = {key: item for key, item in value.items() if key not in {"run_id", "run_digest"}}
        if (value.get("run_id") != run_id or value.get("run_digest") != run_digest
                or _digest(semantic) != run_digest
                or run_id != "model-replacement-run-" + run_digest[7:31]):
            raise DevelopmentalModelReplacementError("trial_run_artifact_tampered")
        condition_statuses = value.get("condition_statuses")
        context_lineage_posture = value.get("context_lineage_posture")
        if (context_lineage_posture not in {None, "legacy_context_not_persisted",
                "verified_persisted_frozen_context"}
                or (context_lineage_posture == "verified_persisted_frozen_context"
                    and condition_statuses is None)):
            raise DevelopmentalModelReplacementError("trial_context_lineage_posture_invalid")
        if condition_statuses is not None:
            protocol = value.get("protocol")
            trial_id = value.get("trial_id")
            observations = value.get("observations")
            completion = value.get("experiment_completion_posture")
            if (not isinstance(protocol, Mapping) or not isinstance(trial_id, str)
                    or not isinstance(condition_statuses, list) or not 1 <= len(condition_statuses) <= len(CONDITION_ORDER)
                    or not isinstance(observations, list) or len(observations) > len(CONDITION_ORDER)
                    or completion not in {"completed", "incomplete", "contradictory"}):
                raise DevelopmentalModelReplacementError("trial_condition_lineage_incomplete")
            protocol_id = str(protocol.get("protocol_id") or "")
            frozen_context: dict[str, Any] | None = None
            prior_bindings: dict[str, Any] | None = None
            context_lineage_posture = value.get("context_lineage_posture")
            if context_lineage_posture == "verified_persisted_frozen_context":
                protocol_object = self.load_verified_protocol(protocol_id,
                    str(protocol.get("protocol_digest") or ""))
                frozen_context = self.load_verified_context(protocol_object.causal_context_id,
                    protocol_object.causal_context_digest)
                prior_bindings = dict(frozen_context["prior_cognition_bindings"])
            elif context_lineage_posture not in {None, "legacy_context_not_persisted"}:
                raise DevelopmentalModelReplacementError("trial_context_lineage_posture_invalid")
            completed_observations: list[Mapping[str, Any]] = []
            saw_terminal_status = False
            for index, (condition, status) in enumerate(zip(CONDITION_ORDER, condition_statuses)):
                if not isinstance(status, Mapping):
                    raise DevelopmentalModelReplacementError("trial_condition_lineage_invalid")
                condition_id = self.condition_artifact_id(protocol_id=protocol_id,
                    trial_id=trial_id, condition=condition)
                status_value = status.get("status")
                if (saw_terminal_status or status.get("condition") != condition
                        or status.get("condition_id") != condition_id
                        or status_value not in {"completed", "incomplete", "contradictory"}
                        or not isinstance(status.get("condition_input_digest"), str)):
                    raise DevelopmentalModelReplacementError("trial_condition_lineage_invalid")
                start, terminal = self.read_condition(condition_id=condition_id,
                    expected_input_digest=status["condition_input_digest"])
                if (start is None or status.get("condition_start_digest") != start.get("condition_start_digest")):
                    raise DevelopmentalModelReplacementError("trial_condition_lineage_conflict")
                if status_value == "completed":
                    if (terminal is None or terminal.get("status") != "completed"
                            or status.get("condition_result_digest") != terminal.get("condition_result_digest")
                            or len(completed_observations) >= len(observations)
                            or terminal.get("observation") != observations[len(completed_observations)]):
                        raise DevelopmentalModelReplacementError("trial_condition_lineage_conflict")
                    if prior_bindings is not None and frozen_context is not None:
                        if any(key in terminal["observation"] for key in prior_bindings):
                            for key, expected_value in prior_bindings.items():
                                if terminal["observation"].get(key) != expected_value:
                                    raise DevelopmentalModelReplacementError("trial_prior_cognition_binding_conflict")
                        if (terminal["observation"].get("current_projection_id") != frozen_context["current_projection_id"]
                                or terminal["observation"].get("current_projection_digest") != frozen_context["current_projection_digest"]):
                            raise DevelopmentalModelReplacementError("trial_current_projection_binding_conflict")
                    if context_lineage_posture == "verified_persisted_frozen_context":
                        resource_fields = {"resource_allocation_digest", "resource_attempt_id",
                            "resource_consumption_receipt_digests", "resource_linkage_digest",
                            "resource_attribution_posture"}
                        if resource_fields.intersection(terminal["observation"]):
                            resource_binding = _resource_receipt_binding(terminal["observation"])
                            if any(terminal["observation"].get(key) != expected_value
                                    for key, expected_value in resource_binding.items()):
                                raise DevelopmentalModelReplacementError("trial_resource_linkage_binding_conflict")
                    completed_observations.append(cast(Mapping[str, Any], terminal["observation"]))
                else:
                    saw_terminal_status = True
                    if (status_value == "incomplete" and terminal is not None
                            and terminal.get("status") != "incomplete"
                            or status_value == "contradictory" and (terminal is None
                                or terminal.get("status") != "contradictory")
                            or status.get("condition_result_digest") != (terminal.get("condition_result_digest")
                                if terminal is not None else None)
                            or status.get("failure_evidence") != (terminal.get("failure_evidence")
                                if terminal is not None else None)
                            or status_value == "contradictory"
                                and status.get("contradictory_observation_digest") != (
                                    terminal.get("observation", {}).get("observation_digest")
                                    if terminal is not None and isinstance(terminal.get("observation"), Mapping)
                                    else None)
                            or status_value == "incomplete" and status.get("contradictory_observation_digest") is not None):
                        raise DevelopmentalModelReplacementError("trial_condition_terminal_conflict")
            if (len(completed_observations) != len(observations)
                    or (completion == "completed" and (saw_terminal_status
                        or len(condition_statuses) != len(CONDITION_ORDER)
                        or len(observations) != len(CONDITION_ORDER)))
                    or (completion in {"incomplete", "contradictory"}
                        and (not saw_terminal_status
                            or condition_statuses[-1].get("status") != completion))):
                raise DevelopmentalModelReplacementError("trial_condition_completion_posture_conflict")
        return cast(dict[str, Any], value)

    def world_state_records(self, *, run_refs: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
        """Project explicitly selected immutable A/B runs as undated evidence."""
        from .world_state_board import record_digest

        references = tuple(run_refs)
        if (len(references) > 32 or any(not isinstance(item, tuple) or len(item) != 2
                or any(not isinstance(value, str) for value in item) for item in references)
                or len({item[0] for item in references}) != len(references)):
            raise DevelopmentalModelReplacementError("run_projection_selection_invalid")
        records: list[dict[str, Any]] = []
        for run_id, run_digest in references:
            run = self.load_verified_run(run_id, run_digest)
            if run.get("schema_version") != RUN_SCHEMA:
                raise DevelopmentalModelReplacementError("run_projection_schema_invalid")
            protocol_value = run.get("protocol")
            if not isinstance(protocol_value, Mapping):
                raise DevelopmentalModelReplacementError("run_projection_protocol_missing")
            protocol = self.load_verified_protocol(str(protocol_value.get("protocol_id") or ""),
                str(protocol_value.get("protocol_digest") or ""))
            normalized_protocol = json.loads(json.dumps(asdict(protocol), sort_keys=True))
            if normalized_protocol != dict(protocol_value):
                raise DevelopmentalModelReplacementError("run_projection_protocol_binding_mismatch")
            if run.get("context_lineage_posture") == "verified_persisted_frozen_context":
                projection_context = self.load_verified_context(protocol.causal_context_id,
                    protocol.causal_context_digest)
                prior_cognition_context_posture = projection_context["prior_cognition_bindings"][
                    "prior_cognitive_context_posture"]
            else:
                prior_cognition_context_posture = "legacy_context_not_persisted"
            provenance_a = self.load_verified_provenance(protocol.model_a_provenance_digest,
                protocol.model_a_identity)
            provenance_b = self.load_verified_provenance(protocol.model_b_provenance_digest,
                protocol.model_b_identity)
            raw_observations = run.get("observations")
            completion = run.get("experiment_completion_posture", "completed")
            if (not isinstance(raw_observations, list)
                    or completion not in {"completed", "incomplete", "contradictory"}
                    or (completion == "completed" and len(raw_observations) != len(CONDITION_ORDER))
                    or (completion != "completed" and len(raw_observations) >= len(CONDITION_ORDER))):
                raise DevelopmentalModelReplacementError("run_projection_observation_count_invalid")
            observations: list[dict[str, Any]] = []
            expected_models = (protocol.model_a_identity, protocol.model_a_identity,
                protocol.model_b_identity, protocol.model_b_identity, protocol.model_a_identity)
            expected_provenance_digests = (protocol.model_a_provenance_digest,
                protocol.model_a_provenance_digest, protocol.model_b_provenance_digest,
                protocol.model_b_provenance_digest, protocol.model_a_provenance_digest)
            expected_history = (True, False, True, False, True)
            for expected_condition, expected_model, expected_provenance_digest, with_history, raw in zip(
                    CONDITION_ORDER, expected_models, expected_provenance_digests,
                    expected_history, raw_observations):
                if not isinstance(raw, Mapping):
                    raise DevelopmentalModelReplacementError("run_projection_observation_invalid")
                semantic = {key: value for key, value in raw.items()
                    if key not in {"observation_id", "observation_digest"}}
                calculated = _digest(semantic)
                history_ids = raw.get("history_record_ids")
                history_digests = raw.get("history_record_digests")
                generation_parameters = raw.get("actual_generation_parameters")
                if (raw.get("condition_id") != expected_condition
                        or raw.get("observation_digest") != calculated
                        or raw.get("observation_id") != "model-replacement-observation-" + calculated[7:31]
                        or raw.get("protocol_id") != protocol.protocol_id
                        or raw.get("protocol_digest") != protocol.protocol_digest
                        or raw.get("causal_context_id") != protocol.causal_context_id
                        or raw.get("causal_context_digest") != protocol.causal_context_digest
                        or raw.get("model_identity_digest") != expected_model.identity_digest
                        or raw.get("model_provenance_manifest_digest") != expected_provenance_digest
                        or not isinstance(history_ids, list) or not isinstance(history_digests, list)
                        or len(history_ids) != len(history_digests)
                        or (not with_history and (history_ids or history_digests))
                        or (with_history and any(not isinstance(item, str) or not item
                            for item in (*history_ids, *history_digests)))
                        or raw.get("history_withheld") is not (not with_history)
                        or not all(isinstance(raw.get(key), str) and raw.get(key) for key in (
                            "current_projection_id", "current_projection_digest"))
                        or not all(isinstance(raw.get(key), str) and raw.get(key) for key in (
                            "inference_receipt_id", "inference_receipt_digest", "output_digest",
                            "request_id", "request_digest", "correlation_id"))
                        or raw.get("correlation_id") != f"{protocol.protocol_id}:{run.get('trial_id')}:{expected_condition}"
                        or not isinstance(generation_parameters, Mapping)
                        or generation_parameters.get("temperature") != 0):
                    raise DevelopmentalModelReplacementError("run_projection_observation_binding_invalid")
                observations.append({key: raw.get(key) for key in (
                    "condition_id", "observation_id", "observation_digest", "model_identity_digest",
                    "model_provenance_manifest_digest", "causal_context_id", "causal_context_digest",
                    "current_projection_id", "current_projection_digest", "history_withheld",
                    "history_record_ids", "history_record_digests", "inference_receipt_id",
                    "inference_receipt_digest", "output_digest",
                    "prior_self_model_projection_id", "prior_self_model_projection_digest",
                    "prior_self_model_source_tick", "prior_epistemic_projection_id",
                    "prior_epistemic_projection_digest", "prior_epistemic_source_tick",
                    "prior_epistemic_state_ids", "prior_epistemic_state_digests",
                    "prior_cognitive_context_posture", "resource_allocation_digest",
                    "resource_attempt_id", "resource_consumption_receipt_digests",
                    "resource_linkage_digest", "resource_attribution_posture")})
            if completion == "completed":
                if (observations[0].get("history_record_ids") != observations[2].get("history_record_ids")
                        or observations[0].get("history_record_digests") != observations[2].get("history_record_digests")
                        or observations[0].get("history_record_ids") != observations[4].get("history_record_ids")
                        or observations[0].get("history_record_digests") != observations[4].get("history_record_digests")
                        or len({(item.get("current_projection_id"), item.get("current_projection_digest"))
                                for item in observations}) != 1):
                    raise DevelopmentalModelReplacementError("run_projection_frozen_context_conflict")
                outputs = [str(item.get("output_digest") or "") for item in observations]
                differences = {"history_effect_model_a": outputs[0] != outputs[1],
                    "history_effect_model_b": outputs[2] != outputs[3],
                    "model_difference_with_history": outputs[0] != outputs[2],
                    "model_difference_without_history": outputs[1] != outputs[3],
                    "model_a_restoration": outputs[0] == outputs[4]}
                classification = ("model_a_restoration_unstable" if not differences["model_a_restoration"] else
                    "history_association_observed_under_both_cognitive_models"
                    if differences["history_effect_model_a"] and differences["history_effect_model_b"] else
                    "history_association_observed_model_a_only" if differences["history_effect_model_a"] else
                    "history_association_observed_model_b_only" if differences["history_effect_model_b"] else
                    "no_observable_history_effect_either_model")
            else:
                differences = None
                classification = "experiment_contradictory" if completion == "contradictory" else "experiment_incomplete"
            if run.get("differences") != differences or run.get("classification") != classification:
                raise DevelopmentalModelReplacementError("run_projection_comparison_binding_invalid")
            payload = {
                "run_id": run_id, "run_digest": run_digest,
                "protocol_id": protocol.protocol_id, "protocol_digest": protocol.protocol_digest,
                "causal_context_id": protocol.causal_context_id,
                "causal_context_digest": protocol.causal_context_digest,
                "software_generation_identity": None,
                "software_generation_posture": "not_bound_by_selected_protocol",
                "model_a_id": protocol.model_a_identity.model_id,
                "model_a_identity_digest": protocol.model_a_identity.identity_digest,
                "model_b_id": protocol.model_b_identity.model_id,
                "model_b_identity_digest": protocol.model_b_identity.identity_digest,
                "model_a_provenance_digest": protocol.model_a_provenance_digest,
                "model_a_provenance_availability": provenance_a.availability,
                "model_a_provenance_claim_count": len(provenance_a.claims),
                "model_b_provenance_digest": protocol.model_b_provenance_digest,
                "model_b_provenance_availability": provenance_b.availability,
                "model_b_provenance_claim_count": len(provenance_b.claims),
                "observations": observations, "differences": differences,
                "prior_cognitive_context_posture": prior_cognition_context_posture,
                "classification": classification,
                "experiment_completion_posture": run.get("experiment_completion_posture", "completed"),
                "condition_statuses": run.get("condition_statuses"),
                "condition_lineage_posture": ("verified_durable_condition_journal"
                    if run.get("condition_statuses") is not None else "legacy_run_without_condition_journal"),
                "claims_posture": run.get("claims_posture"),
                "non_claims": run.get("non_claims"), "current_truth": False,
                "authority": False,
            }
            if (run.get("claims_posture") != "bounded_digest_level_observed_association_only"
                    or run.get("non_claims") != list(NON_CLAIMS)
                    or len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()) > 32_768):
                raise DevelopmentalModelReplacementError("run_projection_claim_or_size_invalid")
            record: dict[str, Any] = {"source_kind": "embodiment", "source_id": run_id,
                "schema_version": RUN_SCHEMA, "subject_id": run_id,
                "subject_kind": "developmental_model_replacement_experiment",
                "stage": "observation", "disposition": str(run.get("classification") or "unknown"),
                "evidence_strength": "digest_bound_model_comparison_artifact", "payload": payload,
                "effect_claimed": False, "effect_proven": False}
            record["digest"] = record_digest(record)
            records.append(record)
        if len(records) > MAX_WORLD_STATE_PROJECTION_RECORDS:
            raise DevelopmentalModelReplacementError("run_projection_record_budget_exceeded")
        return records


class DevelopmentalModelReplacementExperiment:
    """Explicit five-condition experiment over two pre-governed endpoints."""

    def __init__(self, *, context: FrozenCausalContext, model_a: GovernedCognitiveEndpoint,
                 model_b: GovernedCognitiveEndpoint, artifact_root: Path,
                 model_a_provenance: ModelDevelopmentProvenance | None = None,
                 model_b_provenance: ModelDevelopmentProvenance | None = None) -> None:
        context.verify()
        self.context, self.model_a, self.model_b = context, model_a, model_b
        identity_a, identity_b = model_a.current_identity(), model_b.current_identity()
        identity_a.verify(); identity_b.verify()
        self.provenance_a = model_a_provenance or ModelDevelopmentProvenance.create(identity_a)
        self.provenance_b = model_b_provenance or ModelDevelopmentProvenance.create(identity_b)
        self.provenance_a.verify(identity_a); self.provenance_b.verify(identity_b)
        self.protocol = ModelReplacementProtocol.create(context, identity_a, identity_b,
                                                        self.provenance_a, self.provenance_b)
        self.protocol.verify()
        self.store = ModelReplacementArtifactStore(artifact_root)

    def _prompt(self, with_history: bool) -> str:
        body = {"instruction": self.context.instruction_template,
                "current_evidence": self.context.current_projection_payload,
                "developmental_history": list(self.context.history_projection_payload) if with_history else [],
                "developmental_history_posture": "historical_interpretation_not_current_truth"}
        return json.dumps(body, sort_keys=True, separators=(",", ":"))

    def _observe(self, condition: str, endpoint: GovernedCognitiveEndpoint,
                 expected: CognitiveModelIdentity, provenance_digest: str,
                 with_history: bool, trial_id: str) -> dict[str, Any]:
        self.context.verify(); self.protocol.verify(); self.store.verify_protocol_bytes(self.protocol)
        verified_provenance = self.store.load_verified_provenance(provenance_digest, expected)
        if verified_provenance.manifest_digest != provenance_digest:
            raise DevelopmentalModelReplacementError("model_provenance_artifact_drift")
        if endpoint.current_identity() != expected:
            raise DevelopmentalModelReplacementError("model_identity_drift")
        prompt = self._prompt(with_history)
        correlation = f"{self.protocol.protocol_id}:{trial_id}:{condition}"
        evidence = {"causal_context_id": self.context.context_id,
                    "causal_context_digest": self.context.context_digest,
                    "current_projection_id": self.context.current_projection_id,
                    "current_projection_digest": self.context.current_projection_digest,
                    "record_ids": list(self.context.history_record_ids) if with_history else [],
                    "record_digests": list(self.context.history_record_digests) if with_history else []}
        receipt = dict(endpoint.infer(purpose=PURPOSE, prompt=prompt, correlation_id=correlation,
                                     budget=self.context.inference_budget,
                                     generation_posture=self.context.generation_posture,
                                     upstream_evidence=evidence))
        if endpoint.current_identity() != expected:
            raise DevelopmentalModelReplacementError("model_identity_drift")
        if receipt.get("status") != "admitted_completed" or receipt.get("fallback_occurred"):
            raise DevelopmentalModelReplacementError("governed_inference_not_completed",
                evidence=_inference_failure_evidence(receipt))
        actual = receipt.get("actual_generation_parameters")
        if not isinstance(actual, Mapping) or actual.get("temperature") != 0:
            raise DevelopmentalModelReplacementError("experiment_generation_configuration_drift",
                evidence=_inference_failure_evidence(receipt))
        required = ("request_id", "request_digest", "inference_receipt_id",
                    "inference_receipt_digest", "output_digest")
        if not all(receipt.get(key) for key in required):
            raise DevelopmentalModelReplacementError("inference_receipt_incomplete",
                evidence=_inference_failure_evidence(receipt))
        semantic = {"condition_id": condition, "trial_id": trial_id,
                    "protocol_id": self.protocol.protocol_id,
                    "protocol_digest": self.protocol.protocol_digest,
                    "causal_context_id": self.context.context_id,
                    "causal_context_digest": self.context.context_digest,
                    "model_identity_digest": expected.identity_digest,
                    "model_provenance_manifest_digest": provenance_digest,
                    "current_projection_id": self.context.current_projection_id,
                    "current_projection_digest": self.context.current_projection_digest,
                    "history_withheld": not with_history,
                    "history_record_ids": list(self.context.history_record_ids) if with_history else [],
                    "history_record_digests": list(self.context.history_record_digests) if with_history else [],
                    "prompt_digest": _digest({"prompt": prompt}), "request_id": receipt["request_id"],
                    "request_digest": receipt["request_digest"],
                    "inference_receipt_id": receipt["inference_receipt_id"],
                    "inference_receipt_digest": receipt["inference_receipt_digest"],
                    "output_digest": receipt["output_digest"],
                    "actual_generation_parameters": dict(actual),
                    "authority_record_digest": expected.authority_record_digest,
                    "correlation_id": correlation}
        semantic.update(_resource_receipt_binding(receipt))
        semantic.update(_prior_cognition_bindings(self.context.current_projection_payload))
        digest = _digest(semantic)
        return {**semantic, "observation_id": "model-replacement-observation-" + digest[7:31],
                "observation_digest": digest}

    def _verify_observation(self, value: Mapping[str, Any], *, condition: str,
                            provenance_digest: str, with_history: bool,
                            trial_id: str) -> dict[str, Any]:
        semantic = {key: item for key, item in value.items()
            if key not in {"observation_id", "observation_digest"}}
        calculated = _digest(semantic)
        expected = self.protocol.model_a_identity if condition.startswith("model_a") else self.protocol.model_b_identity
        prompt_digest = _digest({"prompt": self._prompt(with_history)})
        history_ids = list(self.context.history_record_ids) if with_history else []
        history_digests = list(self.context.history_record_digests) if with_history else []
        correlation = f"{self.protocol.protocol_id}:{trial_id}:{condition}"
        generation = value.get("actual_generation_parameters")
        prior_bindings = _prior_cognition_bindings(self.context.current_projection_payload)
        resource_fields = {"resource_allocation_digest", "resource_attempt_id",
            "resource_consumption_receipt_digests", "resource_linkage_digest",
            "resource_attribution_posture"}
        resource_binding = (_resource_receipt_binding(value)
            if resource_fields.intersection(value) else None)
        has_prior_bindings = any(key in value for key in prior_bindings)
        if (value.get("observation_digest") != calculated
                or value.get("observation_id") != "model-replacement-observation-" + calculated[7:31]
                or value.get("condition_id") != condition or value.get("trial_id") != trial_id
                or value.get("protocol_id") != self.protocol.protocol_id
                or value.get("protocol_digest") != self.protocol.protocol_digest
                or value.get("causal_context_id") != self.context.context_id
                or value.get("causal_context_digest") != self.context.context_digest
                or value.get("model_identity_digest") != expected.identity_digest
                or value.get("model_provenance_manifest_digest") != provenance_digest
                or value.get("current_projection_id") != self.context.current_projection_id
                or value.get("current_projection_digest") != self.context.current_projection_digest
                or value.get("history_record_ids") != history_ids
                or value.get("history_record_digests") != history_digests
                or value.get("history_withheld") is not (not with_history)
                or (resource_binding is not None and any(value.get(key) != expected_value
                    for key, expected_value in resource_binding.items()))
                or (has_prior_bindings and any(value.get(key) != expected_value
                    for key, expected_value in prior_bindings.items()))
                or value.get("prompt_digest") != prompt_digest
                or value.get("correlation_id") != correlation
                or not all(isinstance(value.get(key), str) and value.get(key) for key in (
                    "request_id", "request_digest", "inference_receipt_id",
                    "inference_receipt_digest", "output_digest"))
                or not isinstance(generation, Mapping) or generation.get("temperature") != 0):
            raise DevelopmentalModelReplacementError("condition_observation_binding_invalid")
        return dict(value)

    def _persist_partial_run(self, *, trial_id: str,
                             observations: Sequence[Mapping[str, Any]],
                             condition_statuses: Sequence[Mapping[str, Any]],
                             failure_posture: str) -> dict[str, Any]:
        completion = next((str(row.get("status")) for row in condition_statuses
            if row.get("status") in {"incomplete", "contradictory"}), "incomplete")
        semantic = {"trial_id": trial_id, "protocol": asdict(self.protocol),
            "observations": [dict(item) for item in observations],
            "condition_statuses": [dict(item) for item in condition_statuses],
            "experiment_completion_posture": completion,
            "context_lineage_posture": "verified_persisted_frozen_context",
            "differences": None,
            "classification": "experiment_contradictory" if completion == "contradictory"
                else "experiment_incomplete",
            "claims_posture": "bounded_digest_level_observed_association_only",
            "non_claims": list(NON_CLAIMS), "validity": "execution_incomplete",
            "failure_posture": failure_posture, "authority": False}
        run_id, run_digest = self.store.persist_run(semantic)
        return {**semantic, "run_id": run_id, "run_digest": run_digest}

    def run(self, *, trial_id: str = DEFAULT_TRIAL_ID) -> dict[str, Any]:
        if (not isinstance(trial_id, str) or not trial_id or len(trial_id) > MAX_TRIAL_ID_LENGTH
                or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in trial_id)):
            raise DevelopmentalModelReplacementError("trial_id_invalid")
        # All metadata and the complete immutable protocol exist before inference one.
        self.store.persist_provenance(self.provenance_a)
        self.store.persist_provenance(self.provenance_b)
        self.store.persist_context(self.context)
        self.store.persist_protocol(self.protocol)
        plan = ((CONDITION_ORDER[0], self.model_a, self.protocol.model_a_identity,
                 self.provenance_a.manifest_digest, True),
                (CONDITION_ORDER[1], self.model_a, self.protocol.model_a_identity,
                 self.provenance_a.manifest_digest, False),
                (CONDITION_ORDER[2], self.model_b, self.protocol.model_b_identity,
                 self.provenance_b.manifest_digest, True),
                (CONDITION_ORDER[3], self.model_b, self.protocol.model_b_identity,
                 self.provenance_b.manifest_digest, False),
                (CONDITION_ORDER[4], self.model_a, self.protocol.model_a_identity,
                 self.provenance_a.manifest_digest, True))
        observations: list[dict[str, Any]] = []
        condition_statuses: list[dict[str, Any]] = []
        for condition, endpoint, expected, provenance_digest, with_history in plan:
            correlation = f"{self.protocol.protocol_id}:{trial_id}:{condition}"
            input_digest = _digest({"protocol_id": self.protocol.protocol_id,
                "protocol_digest": self.protocol.protocol_digest, "trial_id": trial_id,
                "condition": condition, "causal_context_id": self.context.context_id,
                "causal_context_digest": self.context.context_digest,
                "model_identity_digest": expected.identity_digest,
                "model_provenance_digest": provenance_digest,
                "current_projection_id": self.context.current_projection_id,
                "current_projection_digest": self.context.current_projection_digest,
                "history_record_ids": list(self.context.history_record_ids) if with_history else [],
                "history_record_digests": list(self.context.history_record_digests) if with_history else [],
                "prompt_digest": _digest({"prompt": self._prompt(with_history)}),
                "correlation_id": correlation})
            condition_id = self.store.condition_artifact_id(protocol_id=self.protocol.protocol_id,
                trial_id=trial_id, condition=condition)
            start, terminal = self.store.read_condition(condition_id=condition_id,
                expected_input_digest=input_digest)
            if terminal is not None:
                status = str(terminal["status"])
                row = {"condition": condition, "condition_id": condition_id,
                    "condition_input_digest": terminal["input_digest"],
                    "status": status, "condition_start_digest": terminal["condition_start_digest"],
                    "condition_result_digest": terminal["condition_result_digest"],
                    "failure_evidence": terminal.get("failure_evidence")}
                condition_statuses.append(row)
                if status != "completed":
                    return self._persist_partial_run(trial_id=trial_id, observations=observations,
                        condition_statuses=condition_statuses,
                        failure_posture=str(terminal.get("failure_posture") or status))
                observation = self._verify_observation(terminal["observation"],
                    condition=condition, provenance_digest=provenance_digest,
                    with_history=with_history, trial_id=trial_id)
                observations.append(observation)
                continue
            if start is not None:
                condition_statuses.append({"condition": condition, "condition_id": condition_id,
                    "condition_input_digest": start["input_digest"],
                    "status": "incomplete", "condition_start_digest": start["condition_start_digest"],
                    "condition_result_digest": None,
                    "failure_posture": "started_without_terminal_no_replay"})
                return self._persist_partial_run(trial_id=trial_id, observations=observations,
                    condition_statuses=condition_statuses,
                    failure_posture="started_without_terminal_no_replay")
            created, start = self.store.begin_condition(protocol_id=self.protocol.protocol_id,
                protocol_digest=self.protocol.protocol_digest, trial_id=trial_id,
                condition=condition, input_digest=input_digest, correlation_id=correlation)
            if not created:
                # Another process claimed the unique condition first. Never
                # infer from our read that it is safe to make the same call.
                _, raced_terminal = self.store.read_condition(condition_id=condition_id,
                    expected_input_digest=input_digest)
                if raced_terminal is not None and raced_terminal.get("status") == "completed":
                    observation = self._verify_observation(raced_terminal["observation"],
                        condition=condition, provenance_digest=provenance_digest,
                        with_history=with_history, trial_id=trial_id)
                    observations.append(observation)
                    condition_statuses.append({"condition": condition,
                        "condition_id": condition_id,
                        "condition_input_digest": raced_terminal["input_digest"],
                        "status": "completed",
                        "condition_start_digest": raced_terminal["condition_start_digest"],
                        "condition_result_digest": raced_terminal["condition_result_digest"]})
                    continue
                condition_statuses.append({"condition": condition, "condition_id": condition_id,
                    "condition_input_digest": start["input_digest"],
                    "status": "incomplete", "condition_start_digest": start["condition_start_digest"],
                    "condition_result_digest": None,
                    "failure_posture": "concurrent_condition_claim_no_replay"})
                return self._persist_partial_run(trial_id=trial_id, observations=observations,
                    condition_statuses=condition_statuses,
                    failure_posture="concurrent_condition_claim_no_replay")
            raw_observation: dict[str, Any] | None = None
            try:
                raw_observation = self._observe(condition, endpoint, expected,
                    provenance_digest, with_history, trial_id)
                observation = self._verify_observation(raw_observation, condition=condition,
                    provenance_digest=provenance_digest, with_history=with_history,
                    trial_id=trial_id)
            except Exception as exc:
                reason = str(exc).lower()
                contradictory = any(marker in reason for marker in (
                    "mismatch", "invalid", "contradictory", "binding", "digest", "drift"))
                failure_posture = ("contradictory_execution_evidence" if contradictory
                    else "inference_interrupted_or_failed")
                terminal = self.store.finish_condition(start=start,
                    status="contradictory" if contradictory else "incomplete",
                    observation=raw_observation if contradictory else None,
                    failure_posture=failure_posture,
                    failure_evidence=getattr(exc, "evidence", None))
                condition_statuses.append({"condition": condition, "condition_id": condition_id,
                    "condition_input_digest": terminal["input_digest"],
                    "status": terminal["status"],
                    "condition_start_digest": terminal["condition_start_digest"],
                    "condition_result_digest": terminal["condition_result_digest"],
                    "failure_evidence": terminal.get("failure_evidence"),
                    "contradictory_observation_digest": (raw_observation.get("observation_digest")
                        if contradictory and isinstance(raw_observation, Mapping) else None),
                    "failure_posture": failure_posture})
                return self._persist_partial_run(trial_id=trial_id, observations=observations,
                    condition_statuses=condition_statuses, failure_posture=failure_posture)
            terminal = self.store.finish_condition(start=start, status="completed",
                observation=observation)
            observations.append(observation)
            condition_statuses.append({"condition": condition, "condition_id": condition_id,
                "condition_input_digest": terminal["input_digest"],
                "status": "completed", "condition_start_digest": terminal["condition_start_digest"],
                "condition_result_digest": terminal["condition_result_digest"]})
        outputs = [str(item["output_digest"]) for item in observations]
        differences = {"history_effect_model_a": outputs[0] != outputs[1],
                       "history_effect_model_b": outputs[2] != outputs[3],
                       "model_difference_with_history": outputs[0] != outputs[2],
                       "model_difference_without_history": outputs[1] != outputs[3],
                       "model_a_restoration": outputs[0] == outputs[4]}
        if not differences["model_a_restoration"]:
            classification = "model_a_restoration_unstable"
        elif differences["history_effect_model_a"] and differences["history_effect_model_b"]:
            classification = "history_association_observed_under_both_cognitive_models"
        elif differences["history_effect_model_a"]:
            classification = "history_association_observed_model_a_only"
        elif differences["history_effect_model_b"]:
            classification = "history_association_observed_model_b_only"
        else:
            classification = "no_observable_history_effect_either_model"
        semantic = {"trial_id": trial_id, "protocol": asdict(self.protocol), "observations": observations,
                    "condition_statuses": condition_statuses,
                    "context_lineage_posture": "verified_persisted_frozen_context",
                    "experiment_completion_posture": "completed",
                    "differences": differences, "classification": classification,
                    "claims_posture": "bounded_digest_level_observed_association_only",
                    "non_claims": list(NON_CLAIMS), "validity": "valid_controlled_observation"}
        run_id, run_digest = self.store.persist_run(semantic)
        return {**semantic, "run_id": run_id, "run_digest": run_digest}
