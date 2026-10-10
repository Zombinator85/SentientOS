"""Controlled same-context cognitive-model replacement observations.

This module owns evidence, not model activation.  Callers supply two already
governed endpoints; the experiment never changes either endpoint or any memory.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, cast

from .local_model_authority import digest_payload

PURPOSE = "resident_developmental_model_replacement_experiment"
CONTEXT_SCHEMA = "sentientos.developmental_model_replacement_context:v1"
PROVENANCE_SCHEMA = "sentientos.model_development_provenance:v1"
PROTOCOL_SCHEMA = "sentientos.developmental_model_replacement_protocol:v1"
RUN_SCHEMA = "sentientos.developmental_model_replacement_run:v1"
MAX_PROVENANCE_ARTIFACT_BYTES = 262_144
MAX_PROVENANCE_CLAIMS = 128
MAX_PROTOCOL_ARTIFACT_BYTES = 1_048_576
MAX_RUN_ARTIFACT_BYTES = 4_194_304
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
    def __init__(self, state_root: Path, *, read_only: bool = False) -> None:
        self.state_root = Path(state_root).resolve()
        self.root = self.state_root / "developmental_experiments" / "model_replacement"
        self.protocols = self.root / "protocols"
        self.provenance = self.root / "provenance"
        self.runs = self.root / "runs"
        self.read_only = read_only

    def _write(self, path: Path, payload: Mapping[str, Any]) -> None:
        if self.read_only:
            raise DevelopmentalModelReplacementError("artifact_store_read_only")
        normalized = json.loads(json.dumps(dict(payload), sort_keys=True))
        limits = {"provenance": MAX_PROVENANCE_ARTIFACT_BYTES,
            "protocols": MAX_PROTOCOL_ARTIFACT_BYTES, "runs": MAX_RUN_ARTIFACT_BYTES}
        maximum = limits.get(path.parent.name)
        if maximum is None:
            raise DevelopmentalModelReplacementError("artifact_store_path_invalid")
        if (self.root.is_symlink() or self.root.parent.is_symlink() or path.parent.is_symlink()):
            raise DevelopmentalModelReplacementError("artifact_store_path_invalid")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.parent.is_symlink() or not path.parent.is_dir():
            raise DevelopmentalModelReplacementError("artifact_store_path_invalid")
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True).encode("utf-8")
        if len(encoded) > maximum:
            raise DevelopmentalModelReplacementError("artifact_size_limit_exceeded")
        try:
            path.lstat()
        except FileNotFoundError:
            prior = None
        else:
            prior = self._read_artifact_json(path, maximum_bytes=maximum,
                missing_code="artifact_missing", invalid_code="artifact_tampered")
        if prior is not None:
            if prior != normalized:
                raise DevelopmentalModelReplacementError("artifact_identity_collision")
            return
        descriptor, temporary = tempfile.mkstemp(prefix=".model-replacement-", suffix=".tmp",
            dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                prior = self._read_artifact_json(path, maximum_bytes=maximum,
                    missing_code="artifact_missing", invalid_code="artifact_tampered")
                if prior != normalized:
                    raise DevelopmentalModelReplacementError("artifact_identity_collision")
                return
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _read_artifact_json(self, path: Path, *, maximum_bytes: int,
                            missing_code: str, invalid_code: str) -> dict[str, Any]:
        descriptor: int | None = None
        try:
            if (self.root.is_symlink() or self.root.parent.is_symlink()
                    or path.parent.is_symlink()):
                raise DevelopmentalModelReplacementError(invalid_code)
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
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
        except (OSError, json.JSONDecodeError, DevelopmentalModelReplacementError) as exc:
            raise DevelopmentalModelReplacementError("trial_run_artifact_unavailable") from exc
        semantic = {key: item for key, item in value.items() if key not in {"run_id", "run_digest"}}
        if (value.get("run_id") != run_id or value.get("run_digest") != run_digest
                or _digest(semantic) != run_digest
                or run_id != "model-replacement-run-" + run_digest[7:31]):
            raise DevelopmentalModelReplacementError("trial_run_artifact_tampered")
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
            raw_observations = run.get("observations")
            if not isinstance(raw_observations, list) or len(raw_observations) != len(CONDITION_ORDER):
                raise DevelopmentalModelReplacementError("run_projection_observation_count_invalid")
            observations: list[dict[str, Any]] = []
            expected_models = (protocol.model_a_identity, protocol.model_a_identity,
                protocol.model_b_identity, protocol.model_b_identity, protocol.model_a_identity)
            expected_provenance_digests = (protocol.model_a_provenance.manifest_digest,
                protocol.model_a_provenance.manifest_digest, protocol.model_b_provenance.manifest_digest,
                protocol.model_b_provenance.manifest_digest, protocol.model_a_provenance.manifest_digest)
            expected_history = (True, False, True, False, True)
            for expected_condition, expected_model, expected_provenance_digest, with_history, raw in zip(
                    CONDITION_ORDER, expected_models, expected_provenance_digests,
                    expected_history, raw_observations):
                if not isinstance(raw, Mapping):
                    raise DevelopmentalModelReplacementError("run_projection_observation_invalid")
                semantic = {key: value for key, value in raw.items()
                    if key not in {"observation_id", "observation_digest"}}
                calculated = _digest(semantic)
                expected_history_ids = list(protocol.context.history_record_ids) if with_history else []
                expected_history_digests = list(protocol.context.history_record_digests) if with_history else []
                generation_parameters = raw.get("actual_generation_parameters")
                if (raw.get("condition_id") != expected_condition
                        or raw.get("observation_digest") != calculated
                        or raw.get("observation_id") != "model-replacement-observation-" + calculated[7:31]
                        or raw.get("protocol_id") != protocol.protocol_id
                        or raw.get("protocol_digest") != protocol.protocol_digest
                        or raw.get("causal_context_id") != protocol.context.context_id
                        or raw.get("causal_context_digest") != protocol.context.context_digest
                        or raw.get("model_identity_digest") != expected_model.identity_digest
                        or raw.get("model_provenance_manifest_digest") != expected_provenance_digest
                        or raw.get("current_projection_id") != protocol.context.current_projection_id
                        or raw.get("current_projection_digest") != protocol.context.current_projection_digest
                        or raw.get("history_withheld") is not (not with_history)
                        or raw.get("history_record_ids") != expected_history_ids
                        or raw.get("history_record_digests") != expected_history_digests
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
                    "inference_receipt_digest", "output_digest")})
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
            if run.get("differences") != differences or run.get("classification") != classification:
                raise DevelopmentalModelReplacementError("run_projection_comparison_binding_invalid")
            payload = {
                "run_id": run_id, "run_digest": run_digest,
                "protocol_id": protocol.protocol_id, "protocol_digest": protocol.protocol_digest,
                "causal_context_id": protocol.context.context_id,
                "causal_context_digest": protocol.context.context_digest,
                "software_generation_identity": protocol.context.repository_generation_identity,
                "model_a_id": protocol.model_a_identity.model_id,
                "model_a_identity_digest": protocol.model_a_identity.identity_digest,
                "model_b_id": protocol.model_b_identity.model_id,
                "model_b_identity_digest": protocol.model_b_identity.identity_digest,
                "model_a_provenance_digest": protocol.model_a_provenance.manifest_digest,
                "model_b_provenance_digest": protocol.model_b_provenance.manifest_digest,
                "observations": observations, "differences": differences,
                "classification": classification,
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
