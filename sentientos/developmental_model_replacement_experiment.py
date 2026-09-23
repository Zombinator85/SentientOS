"""Controlled same-context cognitive-model replacement observations.

This module owns evidence, not model activation.  Callers supply two already
governed endpoints; the experiment never changes either endpoint or any memory.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, cast

from .local_model_authority import atomic_write_json, digest_payload

PURPOSE = "resident_developmental_model_replacement_experiment"
CONTEXT_SCHEMA = "sentientos.developmental_model_replacement_context:v1"
PROVENANCE_SCHEMA = "sentientos.model_development_provenance:v1"
PROTOCOL_SCHEMA = "sentientos.developmental_model_replacement_protocol:v1"
RUN_SCHEMA = "sentientos.developmental_model_replacement_run:v1"
CONDITION_ORDER = (
    "model_a_history_present", "model_a_history_withheld",
    "model_b_history_present", "model_b_history_withheld",
    "model_a_history_restored",
)
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
        payload = asdict(self); payload.pop("claim_id"); payload.pop("claim_digest")
        digest = _digest(payload)
        if self.claim_digest != digest or self.claim_id != "model-claim-" + digest[7:31]:
            raise DevelopmentalModelReplacementError("provenance_claim_digest_mismatch")
        if self.subject_identity_digest != subject.identity_digest:
            raise DevelopmentalModelReplacementError("provenance_subject_mismatch")
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
        payload = asdict(self); payload.pop("manifest_digest")
        if self.manifest_digest != _digest(payload) or self.grants_authority:
            raise DevelopmentalModelReplacementError("provenance_manifest_digest_mismatch")
        if self.subject_identity_digest != subject.identity_digest:
            raise DevelopmentalModelReplacementError("provenance_subject_mismatch")
        if not self.claims and self.availability != "unknown":
            raise DevelopmentalModelReplacementError("absent_provenance_must_be_unknown")
        for claim in self.claims:
            claim.verify(subject)


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
        history = {"record_ids": list(self.history_record_ids),
                   "record_digests": list(self.history_record_digests)}
        if self.history_record_set_digest != _digest(history):
            raise DevelopmentalModelReplacementError("history_record_set_digest_mismatch")
        if self.instruction_template_digest != _digest({"instruction": self.instruction_template}):
            raise DevelopmentalModelReplacementError("instruction_template_digest_mismatch")
        if self.generation_posture.get("temperature") != 0:
            raise DevelopmentalModelReplacementError("temperature_zero_required")


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
    def __init__(self, state_root: Path) -> None:
        self.root = Path(state_root) / "developmental_experiments" / "model_replacement"
        self.protocols = self.root / "protocols"
        self.provenance = self.root / "provenance"
        self.runs = self.root / "runs"

    @staticmethod
    def _write(path: Path, payload: Mapping[str, Any]) -> None:
        normalized = json.loads(json.dumps(dict(payload), sort_keys=True))
        if path.exists():
            try:
                prior = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise DevelopmentalModelReplacementError("artifact_tampered") from exc
            if prior != normalized:
                raise DevelopmentalModelReplacementError("artifact_identity_collision")
            return
        atomic_write_json(path, normalized)

    def persist_provenance(self, manifest: ModelDevelopmentProvenance) -> None:
        self._write(self.provenance / f"{manifest.manifest_digest[7:]}.json", asdict(manifest))

    def persist_protocol(self, protocol: ModelReplacementProtocol) -> None:
        protocol.verify()
        self._write(self.protocols / f"{protocol.protocol_id}.json", asdict(protocol))

    def verify_protocol_bytes(self, protocol: ModelReplacementProtocol) -> None:
        path = self.protocols / f"{protocol.protocol_id}.json"
        expected = json.loads(json.dumps(asdict(protocol), sort_keys=True))
        if not path.is_file() or json.loads(path.read_text(encoding="utf-8")) != expected:
            raise DevelopmentalModelReplacementError("protocol_custody_changed")

    def persist_run(self, semantic: Mapping[str, Any]) -> tuple[str, str]:
        payload = {**semantic, "schema_version": RUN_SCHEMA}
        digest = _digest(payload); run_id = "model-replacement-run-" + digest[7:31]
        self._write(self.runs / f"{run_id}.json", {**payload, "run_id": run_id, "run_digest": digest})
        return run_id, digest

    def load_verified_run(self, run_id: str, run_digest: str) -> dict[str, Any]:
        path = self.runs / f"{run_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DevelopmentalModelReplacementError("trial_run_artifact_unavailable") from exc
        semantic = {key: item for key, item in value.items() if key not in {"run_id", "run_digest"}}
        if (value.get("run_id") != run_id or value.get("run_digest") != run_digest
                or _digest(semantic) != run_digest
                or run_id != "model-replacement-run-" + run_digest[7:31]):
            raise DevelopmentalModelReplacementError("trial_run_artifact_tampered")
        return cast(dict[str, Any], value)


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
            raise DevelopmentalModelReplacementError("governed_inference_not_completed")
        actual = receipt.get("actual_generation_parameters")
        if not isinstance(actual, Mapping) or actual.get("temperature") != 0:
            raise DevelopmentalModelReplacementError("experiment_generation_configuration_drift")
        required = ("request_id", "request_digest", "inference_receipt_id",
                    "inference_receipt_digest", "output_digest")
        if not all(receipt.get(key) for key in required):
            raise DevelopmentalModelReplacementError("inference_receipt_incomplete")
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
        digest = _digest(semantic)
        return {**semantic, "observation_id": "model-replacement-observation-" + digest[7:31],
                "observation_digest": digest}

    def run(self, *, trial_id: str = DEFAULT_TRIAL_ID) -> dict[str, Any]:
        if (not isinstance(trial_id, str) or not trial_id or len(trial_id) > MAX_TRIAL_ID_LENGTH
                or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in trial_id)):
            raise DevelopmentalModelReplacementError("trial_id_invalid")
        # All metadata and the complete immutable protocol exist before inference one.
        self.store.persist_provenance(self.provenance_a)
        self.store.persist_provenance(self.provenance_b)
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
        observations = [self._observe(*item, trial_id) for item in plan]
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
                    "differences": differences, "classification": classification,
                    "claims_posture": "bounded_digest_level_observed_association_only",
                    "non_claims": list(NON_CLAIMS), "validity": "valid_controlled_observation"}
        run_id, run_digest = self.store.persist_run(semantic)
        return {**semantic, "run_id": run_id, "run_digest": run_digest}
