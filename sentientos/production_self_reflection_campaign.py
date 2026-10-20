"""Fail-closed custody for the production self-reflection A -> B -> A experiment.

This module is deliberately a composer.  Commissioning, serving, activation,
transition, World-State, reconciliation, inference and scoring remain owned by
their existing implementations.  The composer binds their receipts and calls a
supplied live executor; it neither creates approvals nor provides a synthetic
fallback.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping, Sequence

from .local_model_authority import atomic_write_json, digest_payload
from .platform_fcntl import fcntl, require_flock
from .private_file_custody import (
    PrivateFileCustodyError,
    open_private_directory,
    publish_immutable_bytes,
    read_private_file_at,
)
from .resident_cognitive_model_transition_experiment import PHASES
from .self_model_intervention_experiment import CONDITION_ORDER, score_assessment

LEGACY_PROTOCOL_SCHEMA = "sentientos.production_self_reflection_protocol:v1"
PROTOCOL_SCHEMA = "sentientos.production_self_reflection_protocol:v2"
READINESS_SCHEMA = "sentientos.production_self_reflection_readiness:v1"
CAMPAIGN_SCHEMA = "sentientos.production_self_reflection_campaign_state:v1"
RECEIPT_SCHEMA = "sentientos.production_self_reflection_trial_receipt:v1"
VERIFIED_RECEIPT_SCHEMA = "sentientos.production_self_reflection_trial_receipt:v2"
REPORT_SCHEMA = "sentientos.production_self_reflection_campaign_report:v1"
SCORER = "deterministic_exact_evidence_key:v1"
MIN_TRIALS, MAX_TRIALS = 2, 32
MAX_IMMUTABLE_ARTIFACT_BYTES = 16 * 1024 * 1024
ALIASES = {"", "latest", "current", "default", "any", "*"}
COMPONENTS = ("commissioning", "artifact_custody", "runtime_workers", "approvals",
              "resident_serving", "activation", "inference", "world_state_inputs",
              "self_model_custody", "scorer", "live_transition_execution")
READINESS_CHECK_KEYS = frozenset({
    "authenticated_installation_custody", "longitudinal_self_model_custody",
    "developmental_history_custody", "active_resident_model", "model_a", "model_b",
    "commissioning", "model_artifacts", "runtime_backend", "activation_approvals",
    "serving_approvals", "inference_admission", "transition_protocol",
    "stable_serving_slot", "quiescence_gate", "required_roots", "assessment_protocol",
    "external_scorer", "campaign_state", "prior_trial_resolved", "transition_journal",
    "canonical_state",
})


class ProductionSelfReflectionError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _digest(value: Any) -> str:
    result: str = digest_payload(value)
    return "sha256:" + result


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _verified_stage_receipt_projection(
        value: Mapping[str, Any], *, protocol: ProductionSelfReflectionProtocol,
        trial_id: str, request_id: str) -> dict[str, Any]:
    """Check the transition owner's exact, minimized completed-stage projection."""
    required = {
        "schema_version", "request_id", "request_digest", "campaign_trial_id",
        "installation_identity", "protocol_id", "protocol_digest", "phase",
        "operator_receipt_digest", "attempt_entry_digest", "completed_entry_digest",
        "journal_head_observed", "operator_authentication", "read_only",
        "effect_performed", "grants_authority", "execution_allowed", "binding_digest",
    }
    if set(value) != required:
        raise ProductionSelfReflectionError("transition_stage_receipt_binding_invalid")
    projection = _json_value(value)
    claimed = projection.pop("binding_digest", None)
    observed = hashlib.sha256(
        (json.dumps(projection, sort_keys=True, separators=(",", ":"))
         + "\n").encode("utf-8")
    ).hexdigest()
    authentication = projection.get("operator_authentication")
    auth_fields = {
        "schema_version", "operator_identity", "signing_key_id",
        "request_claims_digest", "provenance_digest", "signed_at",
        "trust_catalog_version", "trust_catalog_digest",
    }
    if (
        claimed != observed
        or projection.get("schema_version")
            != "sentientos.resident_cognitive_transition_verified_stage_receipt:v3"
        or projection.get("request_id") != request_id
        or projection.get("campaign_trial_id") != trial_id
        or projection.get("installation_identity") != protocol.installation_identity
        or projection.get("protocol_id") != protocol.transition.get("protocol_id")
        or projection.get("protocol_digest") != protocol.transition.get("protocol_digest")
        or any(not isinstance(projection.get(key), str) or not projection.get(key)
               for key in ("request_digest", "phase", "operator_receipt_digest",
                           "attempt_entry_digest", "completed_entry_digest",
                           "journal_head_observed"))
        or projection.get("read_only") is not True
        or projection.get("effect_performed") is not False
        or projection.get("grants_authority") is not False
        or projection.get("execution_allowed") is not False
        or not isinstance(authentication, Mapping)
        or set(authentication) != auth_fields
        or authentication.get("schema_version")
            != "sentientos.resident_cognitive_transition_operator_authentication_binding:v1"
        or any(not isinstance(authentication.get(key), str)
               or not authentication.get(key)
               for key in ("operator_identity", "signing_key_id",
                           "request_claims_digest", "provenance_digest",
                           "signed_at", "trust_catalog_digest"))
        or re.fullmatch(r"[a-z0-9][a-z0-9._:/-]{0,127}",
                        str(authentication.get("operator_identity"))) is None
        or re.fullmatch(r"ed25519-sha256:[0-9a-f]{64}",
                        str(authentication.get("signing_key_id"))) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}",
                        str(authentication.get("request_claims_digest"))) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}",
                        str(authentication.get("provenance_digest"))) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}",
                        str(authentication.get("trust_catalog_digest"))) is None
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                        str(authentication.get("signed_at"))) is None
        or type(authentication.get("trust_catalog_version")) is not int
        or authentication.get("trust_catalog_version", 0) < 1
    ):
        raise ProductionSelfReflectionError("transition_stage_receipt_binding_invalid")
    projection["binding_digest"] = claimed
    return projection


def _exact(value: object, label: str) -> str:
    text = str(value)
    if text.casefold() in ALIASES or "*" in text or "/" in text or "\\" in text:
        raise ProductionSelfReflectionError(label + "_not_exact")
    return text


def _immutable(path: Path, value: Mapping[str, Any]) -> None:
    encoded = (json.dumps(dict(value), indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        publish_immutable_bytes(
            path,
            encoded,
            max_bytes=MAX_IMMUTABLE_ARTIFACT_BYTES,
            collision_code="immutable_artifact_collision",
        )
    except PrivateFileCustodyError as exc:
        code = "immutable_artifact_collision" if exc.code == "immutable_artifact_collision" else "immutable_artifact_tampered"
        raise ProductionSelfReflectionError(code) from exc


@dataclass(frozen=True)
class ProductionSelfReflectionProtocol:
    protocol_id: str
    protocol_digest: str
    installation_identity: str
    software_generation: str
    runtime_configuration: Mapping[str, Any]
    requested_evidence_posture: str
    model_a: Mapping[str, Any]
    model_b: Mapping[str, Any]
    persistent_state: Mapping[str, Any]
    assessment: Mapping[str, Any]
    transition: Mapping[str, Any]
    campaign_policy: Mapping[str, Any]
    schema_version: str = PROTOCOL_SCHEMA
    grants_authority: bool = False

    @classmethod
    def create(cls, *, installation_identity: str, software_generation: str,
               runtime_configuration: Mapping[str, Any], model_a: Mapping[str, Any],
               model_b: Mapping[str, Any], persistent_state: Mapping[str, Any],
               assessment: Mapping[str, Any], transition: Mapping[str, Any],
               trial_ids: Sequence[str], requested_evidence_posture: str = "production") -> "ProductionSelfReflectionProtocol":
        ids = tuple(_exact(x, "trial_id") for x in trial_ids)
        if not MIN_TRIALS <= len(ids) <= MAX_TRIALS or len(set(ids)) != len(ids):
            raise ProductionSelfReflectionError("trial_inventory_invalid")
        policy = {"planned_trial_count": len(ids), "trial_ids": ids, "silent_retries": False,
                  "trial_replacement": False, "cherry_picking": False,
                  "retain_negative_null_unstable_interrupted": True, "autonomous_repetition": False,
                  "require_verified_transition_stage_receipts": True}
        raw = cls("", "", _exact(installation_identity, "installation_identity"),
                  _exact(software_generation, "software_generation"), dict(runtime_configuration),
                  requested_evidence_posture, dict(model_a), dict(model_b), dict(persistent_state),
                  dict(assessment), dict(transition), policy)
        raw._validate_bindings()
        semantic = asdict(raw); semantic.pop("protocol_id"); semantic.pop("protocol_digest")
        digest = _digest(semantic)
        return replace(raw, protocol_id="production-self-reflection-" + digest[7:31], protocol_digest=digest)

    def _validate_bindings(self) -> None:
        if not isinstance(self.campaign_policy, Mapping):
            raise ProductionSelfReflectionError("transition_stage_receipt_policy_invalid")
        if self.schema_version not in {LEGACY_PROTOCOL_SCHEMA, PROTOCOL_SCHEMA}:
            raise ProductionSelfReflectionError("protocol_schema_version_invalid")
        has_receipt_policy = (
            "require_verified_transition_stage_receipts" in self.campaign_policy)
        require_stage_receipts = self.campaign_policy.get(
            "require_verified_transition_stage_receipts", False)
        if (type(require_stage_receipts) is not bool
                or (self.schema_version == PROTOCOL_SCHEMA and require_stage_receipts is not True)
                or (self.schema_version == LEGACY_PROTOCOL_SCHEMA and has_receipt_policy
                    and require_stage_receipts is not True)):
            raise ProductionSelfReflectionError("transition_stage_receipt_policy_invalid")
        required_model = {"commissioning_receipt_id", "commissioning_receipt_digest", "cognitive_identity",
            "artifact_digest", "artifact_size", "development_provenance_digest", "serving_configuration_digest",
            "activation_approval_id", "serving_approval_id", "inference_authority_map_id"}
        for role, model in (("model_a", self.model_a), ("model_b", self.model_b)):
            if not required_model <= set(model): raise ProductionSelfReflectionError(role + "_binding_incomplete")
            for key in required_model - {"artifact_size"}: _exact(model[key], role + "_" + key)
            if not isinstance(model["artifact_size"], int) or model["artifact_size"] < 1:
                raise ProductionSelfReflectionError(role + "_artifact_size_invalid")
        if self.model_a["cognitive_identity"] == self.model_b["cognitive_identity"]:
            raise ProductionSelfReflectionError("cognitive_identities_not_distinct")
        required_state = {"developmental_history_boundary_digest", "composition_state_digest",
            "initial_reconciliation_id", "initial_reconciliation_digest", "projection_policy",
            "assessment_claim_inventory_digest", "world_state_id", "world_state_digest"}
        if not required_state <= set(self.persistent_state): raise ProductionSelfReflectionError("persistent_state_binding_incomplete")
        required_assessment = {"question_set_digest", "answer_key_digest", "scorer_version", "scorer_digest",
            "projection_id", "projection_digest", "prompt_construction_digest", "inference_budget",
            "generation_parameters", "abstention_format", "citation_format", "condition_order"}
        if not required_assessment <= set(self.assessment): raise ProductionSelfReflectionError("assessment_binding_incomplete")
        if tuple(self.assessment["condition_order"]) != CONDITION_ORDER or self.assessment["scorer_version"] != SCORER:
            raise ProductionSelfReflectionError("assessment_contract_mismatch")
        if tuple(self.transition.get("phase_order", ())) != PHASES:
            raise ProductionSelfReflectionError("transition_protocol_mismatch")
        for key in ("protocol_id", "protocol_digest", "journal_custody", "journal_identity",
                    "installation_relative_custody", "quiescence_semantics", "failure_posture"):
            if key not in self.transition: raise ProductionSelfReflectionError("transition_binding_incomplete")
        if self.requested_evidence_posture != "production":
            raise ProductionSelfReflectionError("production_posture_required")

    def verify(self) -> None:
        self._validate_bindings()
        semantic = asdict(self); semantic.pop("protocol_id"); semantic.pop("protocol_digest")
        digest = _digest(semantic)
        if self.schema_version not in {LEGACY_PROTOCOL_SCHEMA, PROTOCOL_SCHEMA} or self.grants_authority or self.protocol_digest != digest \
                or self.protocol_id != "production-self-reflection-" + digest[7:31]:
            raise ProductionSelfReflectionError("protocol_tampered")


def reconstruct_protocol(value: Mapping[str, Any]) -> ProductionSelfReflectionProtocol:
    try:
        protocol = ProductionSelfReflectionProtocol(**dict(value)); protocol.verify(); return protocol
    except (KeyError, TypeError, ProductionSelfReflectionError) as exc:
        raise ProductionSelfReflectionError("protocol_tampered") from exc


def derive_evidence_posture(components: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    synthetic = tuple(name for name in COMPONENTS if components.get(name) != "nonsynthetic")
    return ("production_experimental_evidence", ()) if not synthetic else ("synthetic_or_rehearsal", synthetic)


def verify_production_readiness(protocol: ProductionSelfReflectionProtocol, observed: Mapping[str, Any],
                                *, artifact_path: Path | None = None) -> Mapping[str, Any]:
    """Mechanically classify supplied observations; the artifact grants no authority."""
    protocol.verify()
    checks = {
        "authenticated_installation_custody": observed.get("installation_identity") == protocol.installation_identity,
        "longitudinal_self_model_custody": observed.get("reconciliation_digest") == protocol.persistent_state["initial_reconciliation_digest"],
        "developmental_history_custody": observed.get("developmental_history_boundary_digest") == protocol.persistent_state["developmental_history_boundary_digest"],
        "active_resident_model": observed.get("resident_cognitive_identity") == protocol.model_a["cognitive_identity"],
        "model_a": observed.get("model_a_available") is True,
        "model_b": observed.get("model_b_available") is True,
        "commissioning": observed.get("commissioning_valid") is True,
        "model_artifacts": observed.get("model_artifacts_valid") is True,
        "runtime_backend": observed.get("runtime_backend_available") is True,
        "activation_approvals": observed.get("activation_approvals_valid") is True,
        "serving_approvals": observed.get("serving_approvals_valid") is True,
        "inference_admission": observed.get("inference_admission_valid") is True,
        "transition_protocol": observed.get("transition_protocol_digest") == protocol.transition["protocol_digest"],
        "stable_serving_slot": observed.get("stable_serving_slot_valid") is True,
        "quiescence_gate": observed.get("live_quiescence_gate") is True,
        "required_roots": observed.get("required_roots_available") is True,
        "assessment_protocol": observed.get("assessment_protocol_valid") is True,
        "external_scorer": observed.get("scorer_digest") == protocol.assessment["scorer_digest"],
        "campaign_state": observed.get("campaign_state_valid") is True,
        "prior_trial_resolved": observed.get("prior_trial_interrupted") is False,
        "transition_journal": observed.get("transition_journal_interrupted") is False,
        "canonical_state": observed.get("canonical_state_conflict") is False,
    }
    raw_components = observed.get("evidence_components", {})
    components = raw_components if isinstance(raw_components, Mapping) else {}
    posture, seams = derive_evidence_posture(components)
    classes: list[str] = []
    ordered = (("model_a", "missing_model_a"), ("model_b", "missing_model_b"),
        ("commissioning", "commissioning_invalid"), ("activation_approvals", "approval_missing"),
        ("serving_approvals", "approval_missing"), ("transition_protocol", "transition_protocol_mismatch"),
        ("longitudinal_self_model_custody", "self_model_custody_invalid"),
        ("developmental_history_custody", "developmental_history_boundary_changed"),
        ("runtime_backend", "runtime_backend_unavailable"), ("prior_trial_resolved", "prior_trial_interrupted"),
        ("transition_journal", "transition_journal_interrupted"), ("canonical_state", "canonical_state_conflict"))
    for check, classification in ordered:
        if not checks[check] and classification not in classes: classes.append(classification)
    if seams: classes.append("synthetic_component_detected")
    for key, passed in checks.items():
        if (not passed and not any(key == pair[0] for pair in ordered)
                and "insufficient_execution_environment" not in classes):
            classes.append("insufficient_execution_environment")
    ready = all(checks.values()) and not seams
    body: dict[str, Any] = {"schema_version": READINESS_SCHEMA, "protocol_id": protocol.protocol_id,
        "protocol_digest": protocol.protocol_digest, "status": "production_trial_ready" if ready else "production_trial_not_ready",
        "classifications": ["production_trial_ready"] if ready else classes, "checks": checks,
        "derived_evidence_posture": posture, "synthetic_components": seams,
        "grants_authority": False, "effect_performed": False}
    body["readiness_id"] = "production-readiness-" + _digest(body)[7:31]
    body["readiness_digest"] = _digest(body)
    if artifact_path is not None: _immutable(artifact_path, body)
    return MappingProxyType(body)


def _verify_readiness_binding(protocol: ProductionSelfReflectionProtocol, readiness: Mapping[str, Any]) -> None:
    value = dict(readiness)
    claimed_digest = value.pop("readiness_digest", None)
    readiness_id = value.get("readiness_id")
    if value.get("schema_version") != READINESS_SCHEMA or not isinstance(readiness_id, str):
        raise ProductionSelfReflectionError("readiness_tampered")
    id_body = dict(value)
    id_body.pop("readiness_id", None)
    if readiness_id != "production-readiness-" + _digest(id_body)[7:31] or claimed_digest != _digest(value):
        raise ProductionSelfReflectionError("readiness_tampered")
    if (value.get("protocol_id") != protocol.protocol_id
            or value.get("protocol_digest") != protocol.protocol_digest):
        raise ProductionSelfReflectionError("readiness_protocol_mismatch")
    if value.get("status") != "production_trial_ready":
        raise ProductionSelfReflectionError("production_trial_not_ready")
    checks = value.get("checks")
    if (not isinstance(checks, Mapping) or set(checks) != READINESS_CHECK_KEYS
            or any(checks.get(key) is not True for key in READINESS_CHECK_KEYS)
            or value.get("derived_evidence_posture") != "production_experimental_evidence"
            or value.get("synthetic_components") not in ([], ())
            or value.get("grants_authority") is not False
            or value.get("effect_performed") is not False):
        raise ProductionSelfReflectionError("readiness_not_complete")


class ProductionSelfReflectionCampaign:
    """Immutable protocol plus mutable digest-bound progress; interruption is terminal."""
    def __init__(self, root: Path, protocol: ProductionSelfReflectionProtocol):
        protocol.verify()
        self.root, self.protocol = Path(root), protocol
        # Keep an independently verified deep copy so caller mutation cannot
        # race a state check and alter the protocol used by the executor.
        self._protocol_snapshot = reconstruct_protocol(asdict(protocol))
        self.protocol_path = self.root / "protocol.json"; self.state_path = self.root / "state.json"

    @contextmanager
    def _campaign_lock(self, *, blocking: bool = True, create: bool = True) -> Iterator[None]:
        """Serialize campaign access, optionally refusing to wait or create custody."""
        if os.name != "posix":
            raise ProductionSelfReflectionError("campaign_lock_unsupported_platform")
        directory_fd: int | None = None
        descriptor: int | None = None
        try:
            require_flock()
            directory_fd = open_private_directory(self.root, create=create)
            flags = os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
            if create:
                flags |= os.O_CREAT
            descriptor = os.open(
                ".production-self-reflection-campaign.lock",
                flags,
                0o600,
                dir_fd=directory_fd,
            )
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                    or metadata.st_nlink != 1 or metadata.st_mode & 0o077):
                raise ProductionSelfReflectionError("campaign_lock_invalid")
            lock_flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
            fcntl.flock(descriptor, lock_flags)
        except BlockingIOError as exc:
            if descriptor is not None:
                os.close(descriptor)
            if directory_fd is not None:
                os.close(directory_fd)
            raise ProductionSelfReflectionError("campaign_busy") from exc
        except ProductionSelfReflectionError:
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
            raise ProductionSelfReflectionError("campaign_lock_unavailable") from exc
        assert directory_fd is not None and descriptor is not None
        try:
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
                os.close(directory_fd)

    @classmethod
    def create(cls, root: Path, protocol: ProductionSelfReflectionProtocol) -> "ProductionSelfReflectionCampaign":
        protocol.verify(); campaign = cls(root, protocol)
        protocol = campaign._protocol_snapshot
        with campaign._campaign_lock():
            protocol_exists = campaign.protocol_path.exists()
            state_exists = campaign.state_path.exists()
            if protocol_exists or state_exists:
                if not protocol_exists:
                    raise ProductionSelfReflectionError("campaign_protocol_unavailable")
                if not state_exists:
                    raise ProductionSelfReflectionError("campaign_state_unavailable")
                _immutable(campaign.protocol_path, asdict(protocol))
                state = campaign.state()
                campaign._verify_progress(state)
                if state["in_progress_trial_id"] and state["validity"] != "invalid_interrupted":
                    campaign._write({**state, "validity": "invalid_interrupted", "failure_reason": "prior_trial_interrupted"})
                    _immutable(campaign.root / "failures" / f"{state['in_progress_trial_id']}.json",
                               {"trial_id": state["in_progress_trial_id"], "classification": "prior_trial_interrupted", "retry_permitted": False})
                    raise ProductionSelfReflectionError("prior_trial_interrupted")
                return campaign
            _immutable(campaign.protocol_path, asdict(protocol))
            campaign._write({"completed_trials": [], "next_trial_id": protocol.campaign_policy["trial_ids"][0],
                             "in_progress_trial_id": None, "validity": "valid_incomplete", "failure_reason": None})
            return campaign

    @classmethod
    def open_for_read_only_inspection(cls, root: Path) -> "ProductionSelfReflectionCampaign":
        """Open existing private campaign custody without recovery or creation."""
        directory_fd: int | None = None
        try:
            directory_fd = open_private_directory(Path(root), create=False)
            encoded = read_private_file_at(
                directory_fd, "protocol.json", max_bytes=MAX_IMMUTABLE_ARTIFACT_BYTES)
            value = json.loads(encoded.decode("utf-8"))
            if not isinstance(value, Mapping):
                raise ProductionSelfReflectionError("campaign_protocol_unavailable")
            protocol = reconstruct_protocol(value)
        except ProductionSelfReflectionError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError,
                PrivateFileCustodyError) as exc:
            raise ProductionSelfReflectionError("campaign_protocol_unavailable") from exc
        finally:
            if directory_fd is not None:
                os.close(directory_fd)
        campaign = cls(Path(root), protocol)
        with campaign._campaign_lock(blocking=False, create=False):
            state = campaign.state()
            campaign._verify_progress(state)
        return campaign

    @classmethod
    def reconstruct(cls, root: Path) -> "ProductionSelfReflectionCampaign":
        try: protocol = reconstruct_protocol(json.loads((Path(root) / "protocol.json").read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc: raise ProductionSelfReflectionError("campaign_protocol_unavailable") from exc
        campaign = cls(root, protocol)
        with campaign._campaign_lock():
            state = campaign.state()
            campaign._verify_progress(state)
            if state["in_progress_trial_id"]:
                campaign._write({**state, "validity": "invalid_interrupted", "failure_reason": "prior_trial_interrupted"})
                _immutable(campaign.root / "failures" / f"{state['in_progress_trial_id']}.json",
                           {"trial_id": state["in_progress_trial_id"], "classification": "prior_trial_interrupted", "retry_permitted": False})
                raise ProductionSelfReflectionError("prior_trial_interrupted")
            return campaign

    def _write(self, value: Mapping[str, Any]) -> Mapping[str, Any]:
        body = {"schema_version": CAMPAIGN_SCHEMA, "protocol_id": self._protocol_snapshot.protocol_id,
                "protocol_digest": self._protocol_snapshot.protocol_digest, **dict(value)}
        body.pop("state_digest", None); body["state_digest"] = _digest(body)
        self.state_path.parent.mkdir(parents=True, exist_ok=True); atomic_write_json(self.state_path, body); return body

    def state(self) -> Mapping[str, Any]:
        # frozen dataclasses do not freeze nested mappings; re-bind every
        # observed progress snapshot to the protocol before trusting it.
        self.protocol.verify()
        self._protocol_snapshot.verify()
        directory_fd: int | None = None
        try:
            directory_fd = open_private_directory(self.root, create=False)
            encoded = read_private_file_at(
                directory_fd, "state.json", max_bytes=MAX_IMMUTABLE_ARTIFACT_BYTES)
            value = json.loads(encoded.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError,
                PrivateFileCustodyError) as exc:
            raise ProductionSelfReflectionError("campaign_state_unavailable") from exc
        finally:
            if directory_fd is not None:
                os.close(directory_fd)
        if not isinstance(value, dict):
            raise ProductionSelfReflectionError("campaign_state_tampered")
        claimed = value.pop("state_digest", None)
        if (claimed != _digest(value) or value.get("schema_version") != CAMPAIGN_SCHEMA
                or value.get("protocol_id") != self._protocol_snapshot.protocol_id
                or value.get("protocol_digest") != self._protocol_snapshot.protocol_digest):
            raise ProductionSelfReflectionError("campaign_state_tampered")
        return MappingProxyType({**value, "state_digest": claimed})

    def _verify_progress(self, state: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
        self.protocol.verify()
        self._protocol_snapshot.verify()
        trial_ids = tuple(self._protocol_snapshot.campaign_policy["trial_ids"])
        completed = state.get("completed_trials")
        if not isinstance(completed, list) or len(completed) > len(trial_ids):
            raise ProductionSelfReflectionError("campaign_state_tampered")
        verified_receipts: list[Mapping[str, Any]] = []
        for index, row in enumerate(completed):
            if not isinstance(row, Mapping) or row.get("trial_id") != trial_ids[index]:
                raise ProductionSelfReflectionError("campaign_state_tampered")
            receipt_directory_fd: int | None = None
            try:
                receipt_directory_fd = open_private_directory(self.root / "receipts", create=False)
                encoded_receipt = read_private_file_at(
                    receipt_directory_fd, f"{trial_ids[index]}.json",
                    max_bytes=MAX_IMMUTABLE_ARTIFACT_BYTES)
                raw_receipt = json.loads(encoded_receipt.decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError,
                    PrivateFileCustodyError) as exc:
                raise ProductionSelfReflectionError("campaign_receipt_unavailable") from exc
            finally:
                if receipt_directory_fd is not None:
                    os.close(receipt_directory_fd)
            if not isinstance(raw_receipt, Mapping):
                raise ProductionSelfReflectionError("trial_receipt_tampered")
            receipt = verify_trial_receipt(raw_receipt)
            if (row.get("receipt_id") != receipt.get("receipt_id")
                    or row.get("receipt_digest") != receipt.get("receipt_digest")
                    or receipt.get("trial_id") != trial_ids[index]
                    or receipt.get("protocol_id") != self._protocol_snapshot.protocol_id
                    or receipt.get("protocol_digest") != self._protocol_snapshot.protocol_digest):
                raise ProductionSelfReflectionError("campaign_receipt_mismatch")
            verified_receipts.append(receipt)

        in_progress = state.get("in_progress_trial_id")
        validity = state.get("validity")
        expected_next = trial_ids[len(completed)] if len(completed) < len(trial_ids) else None
        if state.get("next_trial_id") != expected_next:
            raise ProductionSelfReflectionError("campaign_state_tampered")
        if in_progress is not None and in_progress != expected_next:
            raise ProductionSelfReflectionError("campaign_state_tampered")
        if validity == "valid_incomplete":
            valid = len(completed) < len(trial_ids) and state.get("failure_reason") is None
        elif validity == "valid_complete":
            valid = len(completed) == len(trial_ids) and in_progress is None and state.get("failure_reason") is None
        elif validity == "invalid_interrupted":
            valid = in_progress in trial_ids and state.get("failure_reason") in {
                "prior_trial_interrupted", "trial_interrupted_no_retry"
            }
        else:
            valid = False
        if not valid:
            raise ProductionSelfReflectionError("campaign_state_tampered")
        return tuple(verified_receipts)

    def bind_verified_transition_plan_to_active_trial(
            self, plan: Mapping[str, Any], *, request_id: str, trial_id: str,
            transition_owner: Any) -> Mapping[str, Any]:
        """Bind a verified stage plan to the campaign's live active trial, without authority.

        The transition receipt alone does not identify a campaign trial. This
        canonical campaign owner adds that binding only when the exact trial is
        active in its digest-verified progress state. The returned snapshot is
        informational; stage approval and live owner admission remain separate.
        """
        if (not isinstance(plan, Mapping) or not isinstance(request_id, str)
                or not request_id or not isinstance(trial_id, str) or not trial_id):
            raise ProductionSelfReflectionError("transition_stage_plan_invalid")
        supplied_plan = dict(plan)
        try:
            canonical_plan = dict(
                ProductionSelfReflectionTransitionBindingObserver(
                    self, transition_owner
                ).plan_next_stage(request_id)
            )
        except ProductionSelfReflectionError:
            raise
        except Exception as exc:
            raise ProductionSelfReflectionError(
                "transition_stage_plan_unavailable"
            ) from exc
        if supplied_plan != canonical_plan:
            raise ProductionSelfReflectionError("transition_stage_plan_tampered_or_stale")
        if (
            canonical_plan.get("status") != "next_stage_planned"
            or canonical_plan.get("receipt_request_id") != request_id
            or canonical_plan.get("campaign_next_trial_id") != trial_id
            or canonical_plan.get("transition_request_trial_id") != trial_id
            or canonical_plan.get("campaign_trial_in_progress") is not True
        ):
            raise ProductionSelfReflectionError("transition_stage_plan_not_for_active_trial")

        with self._campaign_lock(blocking=False, create=False):
            state = self.state()
            self._verify_progress(state)
            if (
                state.get("validity") != "valid_incomplete"
                or state.get("failure_reason") is not None
                or state.get("in_progress_trial_id") != trial_id
                or state.get("next_trial_id") != trial_id
            ):
                raise ProductionSelfReflectionError("campaign_trial_binding_not_active")
            if state.get("state_digest") != canonical_plan.get("campaign_state_digest"):
                raise ProductionSelfReflectionError("campaign_trial_binding_state_stale")

        binding: dict[str, Any] = {
            "schema_version": "sentientos.production_self_reflection_active_trial_stage_binding:v1",
            "status": "active_trial_stage_bound",
            "campaign_trial_binding": "established_by_canonical_campaign_owner",
            "campaign_protocol_id": self._protocol_snapshot.protocol_id,
            "campaign_protocol_digest": self._protocol_snapshot.protocol_digest,
            "campaign_trial_id": trial_id,
            "campaign_state_digest": state.get("state_digest"),
            "transition_plan_digest": canonical_plan.get("plan_digest"),
            "operator_authentication": dict(canonical_plan["operator_authentication"]),
            "receipt_request_id": request_id,
            "prior_stage": canonical_plan.get("prior_stage"),
            "next_stage": canonical_plan.get("next_stage"),
            "next_stage_requires_separately_supplied_approval": True,
            "live_transition_owner_revalidation_required": True,
            "read_only": True,
            "effect_performed": False,
            "campaign_advanced": False,
            "grants_authority": False,
            "execution_allowed": False,
        }
        binding["binding_digest"] = _digest(binding)
        binding["operator_authentication"] = MappingProxyType(binding["operator_authentication"])
        return MappingProxyType(binding)

    def bind_verified_transition_stage_receipt_to_active_trial(
            self, *, request_id: str, trial_id: str,
            transition_owner: Any) -> Mapping[str, Any]:
        """Bind one owner's verified completed-stage receipt to the active trial.

        This is an evidence projection only. It revalidates the live plan and
        campaign state, then carries the minimized journal and authenticated
        operator provenance needed by a later immutable outcome receipt. It
        never processes a transition request or grants stage authority.
        """
        if (not isinstance(request_id, str) or not request_id
                or not isinstance(trial_id, str) or not trial_id):
            raise ProductionSelfReflectionError("transition_stage_receipt_binding_invalid")
        try:
            observer = ProductionSelfReflectionTransitionBindingObserver(
                self, transition_owner)
            plan = dict(observer.plan_next_stage(request_id))
            if plan.get("status") not in {
                    "next_stage_planned", "transition_sequence_complete"}:
                raise ProductionSelfReflectionError(
                    "transition_stage_receipt_binding_plan_unavailable")
            if (plan.get("receipt_request_id") != request_id
                    or plan.get("transition_request_trial_id") != trial_id
                    or plan.get("campaign_next_trial_id") != trial_id
                    or plan.get("campaign_trial_in_progress") is not True):
                raise ProductionSelfReflectionError(
                    "transition_stage_receipt_binding_not_for_active_trial")
            if plan["status"] == "next_stage_planned":
                active_binding = dict(self.bind_verified_transition_plan_to_active_trial(
                    plan, request_id=request_id, trial_id=trial_id,
                    transition_owner=transition_owner))
            else:
                with self._campaign_lock(blocking=False, create=False):
                    terminal_state = self.state()
                    self._verify_progress(terminal_state)
                    if (terminal_state.get("validity") != "valid_incomplete"
                            or terminal_state.get("failure_reason") is not None
                            or terminal_state.get("in_progress_trial_id") != trial_id
                            or terminal_state.get("next_trial_id") != trial_id
                            or terminal_state.get("state_digest")
                                != plan.get("campaign_state_digest")):
                        raise ProductionSelfReflectionError(
                            "transition_stage_receipt_binding_campaign_state_stale")
                active_binding = {
                    "campaign_state_digest": terminal_state.get("state_digest"),
                    "transition_plan_digest": plan.get("plan_digest"),
                }
            projection = dict(transition_owner.inspect_verified_stage_receipt(request_id))
            with self._campaign_lock(blocking=False, create=False):
                current_state = self.state()
                self._verify_progress(current_state)
                status = dict(transition_owner.status())
        except ProductionSelfReflectionError:
            raise
        except Exception as exc:
            raise ProductionSelfReflectionError(
                "transition_stage_receipt_binding_unavailable") from exc

        body = dict(projection)
        claimed_receipt_binding = body.pop("binding_digest", None)
        observed_receipt_binding = hashlib.sha256(
            (json.dumps(_json_value(body), sort_keys=True, separators=(",", ":"))
             + "\n").encode("utf-8")
        ).hexdigest()
        phase = projection.get("phase")
        if (
            claimed_receipt_binding != observed_receipt_binding
            or projection.get("schema_version")
                != "sentientos.resident_cognitive_transition_verified_stage_receipt:v3"
            or projection.get("request_id") != request_id
            or projection.get("campaign_trial_id") != trial_id
            or projection.get("installation_identity")
                != self._protocol_snapshot.installation_identity
            or projection.get("protocol_id")
                != self._protocol_snapshot.transition.get("protocol_id")
            or projection.get("protocol_digest")
                != self._protocol_snapshot.transition.get("protocol_digest")
            or phase != plan.get("prior_stage")
            or projection.get("completed_entry_digest")
                != plan.get("completed_entry_digest")
            or projection.get("operator_authentication")
                != plan.get("operator_authentication")
            or projection.get("binding_digest") != plan.get("receipt_binding_digest")
            or active_binding.get("campaign_state_digest")
                != current_state.get("state_digest")
            or current_state.get("validity") != "valid_incomplete"
            or current_state.get("in_progress_trial_id") != trial_id
            or current_state.get("next_trial_id") != trial_id
            or current_state.get("failure_reason") is not None
            or status.get("protocol_id")
                != self._protocol_snapshot.transition.get("protocol_id")
            or status.get("protocol_digest")
                != self._protocol_snapshot.transition.get("protocol_digest")
            or status.get("current_phase") != phase
            or status.get("current_journal_head")
                != projection.get("journal_head_observed")
            or status.get("interrupted") is not False
            or status.get("outstanding_stage") is not None
            or status.get("replay_forbidden") is not False
            or not isinstance(status.get("semantically_verified_stage_entry_digests"),
                               (list, tuple))
            or projection.get("completed_entry_digest") not in
                status.get("semantically_verified_stage_entry_digests", ())
        ):
            raise ProductionSelfReflectionError(
                "transition_stage_receipt_binding_stale_or_unbound")

        binding: dict[str, Any] = {
            "schema_version":
                "sentientos.production_self_reflection_active_trial_stage_receipt_binding:v1",
            "status": "active_trial_stage_receipt_bound",
            "campaign_protocol_id": self._protocol_snapshot.protocol_id,
            "campaign_protocol_digest": self._protocol_snapshot.protocol_digest,
            "campaign_trial_id": trial_id,
            "campaign_state_digest": current_state.get("state_digest"),
            "transition_plan_digest": active_binding.get("transition_plan_digest"),
            "receipt_request_id": request_id,
            "receipt_binding_digest": claimed_receipt_binding,
            "operator_receipt_digest": projection.get("operator_receipt_digest"),
            "attempt_entry_digest": projection.get("attempt_entry_digest"),
            "completed_entry_digest": projection.get("completed_entry_digest"),
            "phase": phase,
            "operator_authentication": dict(projection["operator_authentication"]),
            "live_transition_owner_revalidation_required": True,
            "read_only": True,
            "effect_performed": False,
            "campaign_advanced": False,
            "grants_authority": False,
            "execution_allowed": False,
        }
        binding["binding_digest"] = _digest(binding)
        binding["operator_authentication"] = MappingProxyType(
            binding["operator_authentication"])
        return MappingProxyType(binding)

    def _verified_transition_stage_outcome(
            self, *, trial_id: str, transition_owner: Any,
            submitted_receipts: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if (not isinstance(submitted_receipts, (list, tuple))
                or len(submitted_receipts) != len(PHASES) - 1):
            raise ProductionSelfReflectionError("transition_stage_receipt_inventory_invalid")
        protocol = self._protocol_snapshot
        transition = protocol.transition
        try:
            config = transition_owner.config
            owner_protocol = transition_owner.controller.protocol.value
        except Exception as exc:
            raise ProductionSelfReflectionError(
                "transition_stage_receipt_owner_unavailable") from exc
        if (
            config.installation_identity != protocol.installation_identity
            or config.protocol_id != transition.get("protocol_id")
            or config.protocol_digest != transition.get("protocol_digest")
            or config.journal_identity != transition.get("journal_identity")
            or owner_protocol.get("installation_identity") != protocol.installation_identity
            or owner_protocol.get("protocol_id") != transition.get("protocol_id")
            or owner_protocol.get("protocol_digest") != transition.get("protocol_digest")
            or owner_protocol.get("journal_identity") != transition.get("journal_identity")
            or tuple(owner_protocol.get("phase_order", ())) != PHASES
        ):
            raise ProductionSelfReflectionError(
                "transition_stage_receipt_owner_binding_mismatch")

        projections: list[dict[str, Any]] = []
        request_ids: set[str] = set()
        attempt_entry_digests: set[str] = set()
        completed_entry_digests: set[str] = set()
        for expected_phase, submitted in zip(PHASES[1:], submitted_receipts):
            if not isinstance(submitted, Mapping):
                raise ProductionSelfReflectionError(
                    "transition_stage_receipt_inventory_invalid")
            request_id = submitted.get("request_id")
            if (not isinstance(request_id, str) or not request_id
                    or request_id.casefold() in ALIASES
                    or "*" in request_id or "/" in request_id or "\\" in request_id
                    or request_id in request_ids
                    or submitted.get("phase") != expected_phase):
                raise ProductionSelfReflectionError(
                    "transition_stage_receipt_inventory_invalid")
            request_ids.add(request_id)
            try:
                raw = transition_owner.inspect_verified_stage_receipt(request_id)
            except Exception as exc:
                raise ProductionSelfReflectionError(
                    "transition_stage_receipt_owner_verification_failed") from exc
            projection = _verified_stage_receipt_projection(
                raw, protocol=protocol, trial_id=trial_id, request_id=request_id)
            if projection.get("phase") != expected_phase:
                raise ProductionSelfReflectionError(
                    "transition_stage_receipt_phase_mismatch")
            attempt_entry_digest = projection["attempt_entry_digest"]
            completed_entry_digest = projection["completed_entry_digest"]
            if (attempt_entry_digest in attempt_entry_digests
                    or completed_entry_digest in completed_entry_digests):
                raise ProductionSelfReflectionError(
                    "transition_stage_receipt_journal_entry_reused")
            attempt_entry_digests.add(attempt_entry_digest)
            completed_entry_digests.add(completed_entry_digest)
            projections.append(projection)

        try:
            status = dict(transition_owner.status())
        except Exception as exc:
            raise ProductionSelfReflectionError(
                "transition_stage_receipt_owner_status_unavailable") from exc
        semantic_entries = status.get("semantically_verified_stage_entry_digests")
        if (
            status.get("protocol_id") != transition.get("protocol_id")
            or status.get("protocol_digest") != transition.get("protocol_digest")
            or status.get("current_phase") != PHASES[-1]
            or not isinstance(status.get("current_journal_head"), str)
            or not status.get("current_journal_head")
            or status.get("interrupted") is not False
            or status.get("outstanding_stage") is not None
            or status.get("replay_forbidden") is not False
            or not isinstance(semantic_entries, (list, tuple))
            or any(projection.get("journal_head_observed")
                   != status.get("current_journal_head")
                   or projection.get("completed_entry_digest") not in semantic_entries
                   for projection in projections)
        ):
            raise ProductionSelfReflectionError(
                "transition_stage_receipt_owner_state_stale")

        state = self.state()
        self._verify_progress(state)
        if (state.get("validity") != "valid_incomplete"
                or state.get("failure_reason") is not None
                or state.get("in_progress_trial_id") != trial_id
                or state.get("next_trial_id") != trial_id):
            raise ProductionSelfReflectionError(
                "transition_stage_receipt_campaign_trial_not_active")
        rows = [{
            "request_id": projection["request_id"],
            "request_digest": projection["request_digest"],
            "phase": projection["phase"],
            "operator_receipt_digest": projection["operator_receipt_digest"],
            "attempt_entry_digest": projection["attempt_entry_digest"],
            "completed_entry_digest": projection["completed_entry_digest"],
            "journal_head_observed": projection["journal_head_observed"],
            "operator_authentication": projection["operator_authentication"],
            "receipt_binding_digest": projection["binding_digest"],
        } for projection in projections]
        binding: dict[str, Any] = {
            "schema_version":
                "sentientos.production_self_reflection_transition_stage_outcome_binding:v1",
            "status": "verified_transition_stages_bound_to_trial_outcome",
            "campaign_protocol_id": protocol.protocol_id,
            "campaign_protocol_digest": protocol.protocol_digest,
            "campaign_trial_id": trial_id,
            "campaign_state_digest": state.get("state_digest"),
            "transition_protocol_id": transition.get("protocol_id"),
            "transition_protocol_digest": transition.get("protocol_digest"),
            "transition_journal_identity": transition.get("journal_identity"),
            "stage_receipts": rows,
            "phase_order": list(PHASES[1:]),
            "live_transition_owner_revalidated": True,
            "read_only": True,
            "effect_performed": False,
            "campaign_advanced": False,
            "grants_authority": False,
            "execution_allowed": False,
        }
        binding["binding_digest"] = _digest(binding)
        return projections, binding

    def run_one(self, readiness: Mapping[str, Any], executor: Callable[[str, ProductionSelfReflectionProtocol], Mapping[str, Any]],
                *, transition_owner: Any | None = None) -> Mapping[str, Any]:
        with self._campaign_lock():
            state = self.state()
            self._verify_progress(state)
            _verify_readiness_binding(self._protocol_snapshot, readiness)
            if state["validity"] != "valid_incomplete" or state["in_progress_trial_id"] or not state["next_trial_id"]:
                raise ProductionSelfReflectionError("campaign_not_runnable")
            if (self._protocol_snapshot.campaign_policy.get(
                    "require_verified_transition_stage_receipts", False)
                    and transition_owner is None):
                raise ProductionSelfReflectionError("transition_stage_receipt_owner_required")
            trial_id = str(state["next_trial_id"]); self._write({**state, "in_progress_trial_id": trial_id})
            try:
                self._protocol_snapshot.verify()
                execution_protocol = reconstruct_protocol(asdict(self._protocol_snapshot))
                evidence = dict(executor(trial_id, execution_protocol))
                execution_protocol.verify()
                if transition_owner is not None:
                    projections, binding = self._verified_transition_stage_outcome(
                        trial_id=trial_id, transition_owner=transition_owner,
                        submitted_receipts=evidence.get("transition_stage_receipts"))
                    evidence["transition_stage_receipts"] = projections
                    evidence["transition_stage_receipt_binding"] = binding
                receipt = make_trial_receipt(self._protocol_snapshot, trial_id, evidence)
            except Exception:
                self._write({**self.state(), "validity": "invalid_interrupted", "failure_reason": "trial_interrupted_no_retry"})
                raise
            _immutable(self.root / "receipts" / f"{trial_id}.json", receipt)
            completed = list(state["completed_trials"]) + [{"trial_id": trial_id, "receipt_id": receipt["receipt_id"], "receipt_digest": receipt["receipt_digest"]}]
            ids = list(self._protocol_snapshot.campaign_policy["trial_ids"]); index = len(completed)
            self._write({"completed_trials": completed, "next_trial_id": ids[index] if index < len(ids) else None,
                         "in_progress_trial_id": None, "validity": "valid_complete" if index == len(ids) else "valid_incomplete",
                         "failure_reason": None})
            return MappingProxyType(receipt)

    def report(self) -> Mapping[str, Any]:
        with self._campaign_lock():
            state = self.state()
            receipts = self._verify_progress(state)
            if state["validity"] != "valid_complete": raise ProductionSelfReflectionError("campaign_incomplete")
            scores = {condition: [r["condition_scores"][condition]["counts"] for r in receipts] for condition in CONDITION_ORDER}
            body: dict[str, Any] = {"schema_version": REPORT_SCHEMA, "protocol_id": self._protocol_snapshot.protocol_id,
                "planned_trial_count": len(receipts), "valid_completed_trials": len(receipts), "interrupted_trials": 0,
                "condition_scores": scores, "restoration_results": [r["restoration_result"] for r in receipts],
                "descriptive_only": True, "negative_null_unstable_retained": True,
                "unsupported_inferences": ["consciousness", "identity", "learning", "sentience", "guaranteed_improvement"]}
            body["report_digest"] = _digest(body); _immutable(self.root / "report.json", body); return MappingProxyType(body)


def _verify_transition_stage_outcome_binding_record(
        binding: Mapping[str, Any], *, protocol_id: str, protocol_digest: str,
        trial_id: str, projections: Any) -> None:
    body = _json_value(binding)
    claimed = body.pop("binding_digest", None)
    phase_order = list(PHASES[1:])
    rows = binding.get("stage_receipts")
    if (
        claimed != _digest(body)
        or binding.get("schema_version")
            != "sentientos.production_self_reflection_transition_stage_outcome_binding:v1"
        or binding.get("status") != "verified_transition_stages_bound_to_trial_outcome"
        or binding.get("campaign_protocol_id") != protocol_id
        or binding.get("campaign_protocol_digest") != protocol_digest
        or binding.get("campaign_trial_id") != trial_id
        or any(not isinstance(binding.get(key), str) or not binding.get(key)
               for key in ("campaign_state_digest", "transition_protocol_id",
                           "transition_protocol_digest", "transition_journal_identity"))
        or binding.get("phase_order") != phase_order
        or not isinstance(rows, list) or len(rows) != len(phase_order)
        or not isinstance(projections, (list, tuple))
        or len(projections) != len(phase_order)
        or binding.get("live_transition_owner_revalidated") is not True
        or binding.get("read_only") is not True
        or binding.get("effect_performed") is not False
        or binding.get("campaign_advanced") is not False
        or binding.get("grants_authority") is not False
        or binding.get("execution_allowed") is not False
    ):
        raise ProductionSelfReflectionError("transition_stage_outcome_binding_invalid")
    request_ids: set[str] = set()
    attempt_entry_digests: set[str] = set()
    completed_entry_digests: set[str] = set()
    for phase, row, raw_projection in zip(phase_order, rows, projections):
        if not isinstance(row, Mapping) or not isinstance(raw_projection, Mapping):
            raise ProductionSelfReflectionError("transition_stage_outcome_binding_invalid")
        projection = _json_value(raw_projection)
        projection_digest = projection.pop("binding_digest", None)
        request_id = raw_projection.get("request_id")
        attempt_entry_digest = raw_projection.get("attempt_entry_digest")
        completed_entry_digest = raw_projection.get("completed_entry_digest")
        if (
            projection_digest != hashlib.sha256(
                (json.dumps(projection, sort_keys=True, separators=(",", ":"))
                 + "\n").encode("utf-8")).hexdigest()
            or any(not isinstance(value, str) or not value for value in (
                request_id, attempt_entry_digest, completed_entry_digest))
            or request_id in request_ids
            or attempt_entry_digest in attempt_entry_digests
            or completed_entry_digest in completed_entry_digests
            or raw_projection.get("phase") != phase
            or raw_projection.get("campaign_trial_id") != trial_id
            or row.get("phase") != phase
            or row.get("request_id") != raw_projection.get("request_id")
            or row.get("request_digest") != raw_projection.get("request_digest")
            or row.get("operator_receipt_digest")
                != raw_projection.get("operator_receipt_digest")
            or row.get("attempt_entry_digest") != raw_projection.get("attempt_entry_digest")
            or row.get("completed_entry_digest")
                != raw_projection.get("completed_entry_digest")
            or row.get("journal_head_observed")
                != raw_projection.get("journal_head_observed")
            or row.get("operator_authentication")
                != raw_projection.get("operator_authentication")
            or row.get("receipt_binding_digest")
                != raw_projection.get("binding_digest")
        ):
            raise ProductionSelfReflectionError("transition_stage_outcome_binding_invalid")
        assert isinstance(request_id, str)
        assert isinstance(attempt_entry_digest, str)
        assert isinstance(completed_entry_digest, str)
        request_ids.add(request_id)
        attempt_entry_digests.add(attempt_entry_digest)
        completed_entry_digests.add(completed_entry_digest)


def make_trial_receipt(protocol: ProductionSelfReflectionProtocol, trial_id: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    required = {"installation_identity", "software_generation_before", "software_generation_after", "transition_stage_receipts",
        "transition_journal_identity", "world_state_identities", "self_model_reconciliations", "self_model_projections",
        "developmental_history_boundary_digest", "condition_inference_receipts", "condition_answers", "pre_resident_identity",
        "post_resident_identity", "pre_self_model_generation", "post_self_model_generation", "restoration_result", "evidence_components"}
    if not required <= set(evidence): raise ProductionSelfReflectionError("trial_evidence_incomplete")
    posture, seams = derive_evidence_posture(evidence["evidence_components"])
    if posture != "production_experimental_evidence": raise ProductionSelfReflectionError("synthetic_component_detected")
    if evidence["pre_resident_identity"] != protocol.model_a["cognitive_identity"] or evidence["post_resident_identity"] != protocol.model_a["cognitive_identity"]:
        raise ProductionSelfReflectionError("restored_a_identity_mismatch")
    stages = tuple(x["phase"] for x in evidence["transition_stage_receipts"])
    if stages != PHASES[1:]: raise ProductionSelfReflectionError("transition_stage_order_mismatch")
    outcome_binding = evidence.get("transition_stage_receipt_binding")
    if (protocol.campaign_policy.get("require_verified_transition_stage_receipts", False)
            and outcome_binding is None):
        raise ProductionSelfReflectionError("transition_stage_receipt_owner_required")
    if outcome_binding is not None:
        if not isinstance(outcome_binding, Mapping):
            raise ProductionSelfReflectionError("transition_stage_outcome_binding_invalid")
        _verify_transition_stage_outcome_binding_record(
            outcome_binding, protocol_id=protocol.protocol_id,
            protocol_digest=protocol.protocol_digest, trial_id=trial_id,
            projections=evidence["transition_stage_receipts"])
    projections = evidence["self_model_projections"]
    if any(not item.get("prior_tick_proven") for item in projections): raise ProductionSelfReflectionError("prior_tick_firewall_breached")
    answer_key = evidence.get("answer_key")
    if not isinstance(answer_key, Mapping) or _digest(answer_key) != protocol.assessment["answer_key_digest"]:
        raise ProductionSelfReflectionError("external_scorer_custody_mismatch")
    scores = {condition: score_assessment(answer_key=answer_key, answers=evidence["condition_answers"][condition]) for condition in CONDITION_ORDER}
    body: dict[str, Any] = {"schema_version": VERIFIED_RECEIPT_SCHEMA if outcome_binding is not None else RECEIPT_SCHEMA, "protocol_id": protocol.protocol_id,
        "protocol_digest": protocol.protocol_digest, "trial_id": trial_id, "installation_identity": evidence["installation_identity"],
        "software_generation_before": evidence["software_generation_before"], "software_generation_after": evidence["software_generation_after"],
        "model_a_commissioning": {k: protocol.model_a[k] for k in ("commissioning_receipt_id", "commissioning_receipt_digest")},
        "model_b_commissioning": {k: protocol.model_b[k] for k in ("commissioning_receipt_id", "commissioning_receipt_digest")},
        "transition_stage_receipts": evidence["transition_stage_receipts"], "transition_journal_identity": evidence["transition_journal_identity"],
        "world_state_identities": evidence["world_state_identities"], "self_model_reconciliations": evidence["self_model_reconciliations"],
        "self_model_projections": projections, "developmental_history_boundary_digest": evidence["developmental_history_boundary_digest"],
        "condition_inference_receipts": evidence["condition_inference_receipts"], "condition_answer_digests": {k: _digest(v) for k, v in evidence["condition_answers"].items()},
        "condition_scores": scores, "pre_resident_identity": evidence["pre_resident_identity"], "post_resident_identity": evidence["post_resident_identity"],
        "pre_self_model_generation": evidence["pre_self_model_generation"], "post_self_model_generation": evidence["post_self_model_generation"],
        "restoration_result": evidence["restoration_result"], "evidence_posture": posture, "synthetic_components": seams,
        "status": "completed", "production_evidence_collected": True, "failure_or_interruption": None,
        "autonomous_repetition_performed": False, "model_output_has_scoring_authority": False}
    if outcome_binding is not None:
        body["transition_stage_receipt_binding"] = outcome_binding
    body["receipt_id"] = "production-self-reflection-trial-" + _digest(body)[7:31]
    body["receipt_digest"] = _digest(body); return body


def verify_trial_receipt(value: Mapping[str, Any]) -> Mapping[str, Any]:
    body = dict(value); claimed = body.pop("receipt_digest", None)
    if (body.get("schema_version") not in {RECEIPT_SCHEMA, VERIFIED_RECEIPT_SCHEMA}
            or claimed != _digest(body)
            or body.get("evidence_posture") != "production_experimental_evidence"):
        raise ProductionSelfReflectionError("trial_receipt_tampered")
    if body.get("schema_version") == VERIFIED_RECEIPT_SCHEMA:
        try:
            _verify_transition_stage_outcome_binding_record(
                body["transition_stage_receipt_binding"],
                protocol_id=str(body["protocol_id"]),
                protocol_digest=str(body["protocol_digest"]),
                trial_id=str(body["trial_id"]),
                projections=body["transition_stage_receipts"])
        except ProductionSelfReflectionError as exc:
            raise ProductionSelfReflectionError("trial_receipt_tampered") from exc
        except (KeyError, TypeError) as exc:
            raise ProductionSelfReflectionError("trial_receipt_tampered") from exc
    return MappingProxyType(dict(value))


__all__ = ["COMPONENTS", "ProductionSelfReflectionCampaign", "ProductionSelfReflectionError",
           "ProductionSelfReflectionProtocol", "ProductionSelfReflectionTransitionBindingObserver",
           "derive_evidence_posture", "make_trial_receipt",
           "reconstruct_protocol", "verify_production_readiness", "verify_trial_receipt"]


class ProductionSelfReflectionTransitionBindingObserver:
    """Read-only binding check between a durable campaign and its live daemon owner.

    This observer never processes operator requests, advances campaign state, or grants
    execution authority. It reports whether the exact transition owner is bound to the
    campaign protocol so a later in-process executor can make its own admission decision.
    """

    def __init__(self, campaign: ProductionSelfReflectionCampaign, transition_owner: Any):
        self.campaign = campaign
        self.transition_owner = transition_owner

    def inspect(self) -> Mapping[str, Any]:
        from .resident_cognitive_model_transition_experiment import PHASES

        protocol = self.campaign._protocol_snapshot
        protocol.verify()
        transition = protocol.transition
        with self.campaign._campaign_lock(blocking=False, create=False):
            state = self.campaign.state()
            self.campaign._verify_progress(state)
            owner_status = dict(self.transition_owner.status())
            custody = dict(self.transition_owner.inspect_custody())
            config = self.transition_owner.config
            owner_protocol = self.transition_owner.controller.protocol.value
            checks = {
                "campaign_transition_protocol_id": (
                    transition.get("protocol_id") == config.protocol_id
                    == owner_status.get("protocol_id") == owner_protocol.get("protocol_id")
                ),
                "campaign_transition_protocol_digest": (
                    transition.get("protocol_digest") == config.protocol_digest
                    == owner_status.get("protocol_digest") == owner_protocol.get("protocol_digest")
                ),
                "installation_identity": (
                    protocol.installation_identity == config.installation_identity
                    == owner_protocol.get("installation_identity")
                ),
                "journal_identity": (
                    transition.get("journal_identity") == config.journal_identity
                    == owner_protocol.get("journal_identity")
                ),
                "phase_order": (
                    tuple(transition.get("phase_order", ())) == PHASES
                    == tuple(owner_protocol.get("phase_order", ()))
                ),
                "campaign_progress_valid": state.get("validity") in {"valid_incomplete", "valid_complete"},
                "campaign_trial_not_in_progress": state.get("in_progress_trial_id") is None,
                "transition_at_predecessor_boundary": owner_status.get("current_phase") == PHASES[0],
                "transition_not_interrupted": owner_status.get("interrupted") is False,
                "transition_has_no_outstanding_stage": owner_status.get("outstanding_stage") is None,
                "transition_replay_not_forbidden": owner_status.get("replay_forbidden") is False,
                "operator_custody_read_only": custody.get("read_only") is True,
                "operator_custody_effect_free": custody.get("effect_performed") is False,
            }
        bound = all(checks.values())
        body: dict[str, Any] = {
            "schema_version": "sentientos.production_self_reflection_transition_binding:v1",
            "protocol_id": protocol.protocol_id,
            "protocol_digest": protocol.protocol_digest,
            "campaign_state_digest": state.get("state_digest"),
            "transition_journal_head": owner_status.get("current_journal_head"),
            "operator_request_count": custody.get("request_count"),
            "status": "transition_binding_verified" if bound else "transition_binding_unverified",
            "checks": checks,
            "effect_performed": False,
            "campaign_advanced": False,
            "grants_authority": False,
            "execution_allowed": False,
        }
        body["binding_digest"] = _digest(body)
        return MappingProxyType(body)

    def plan_next_stage(self, request_id: str) -> Mapping[str, Any]:
        """Project the canonical next stage from one exact verified receipt.

        Planning is read-only: this method neither processes an operator request,
        changes campaign progress, selects approval artifacts, nor grants execution
        permission. A consumer must obtain each stage's independent approval and
        submit a separate operator request through the existing live owner.
        """
        if not isinstance(request_id, str) or not request_id:
            raise ProductionSelfReflectionError("transition_stage_receipt_request_id_invalid")
        protocol = self.campaign._protocol_snapshot
        protocol.verify()
        transition = protocol.transition
        owner = self.transition_owner
        try:
            with self.campaign._campaign_lock(blocking=False, create=False):
                state = self.campaign.state()
                self.campaign._verify_progress(state)
                projection = dict(owner.inspect_verified_stage_receipt(request_id))
                owner_status = dict(owner.status())
                owner_config = owner.config
                owner_protocol = owner.controller.protocol.value
        except Exception as exc:
            raise ProductionSelfReflectionError(
                "transition_stage_receipt_unavailable"
            ) from exc

        required = {
            "schema_version", "request_id", "request_digest", "campaign_trial_id",
            "installation_identity",
            "protocol_id", "protocol_digest", "phase", "operator_receipt_digest",
            "attempt_entry_digest", "completed_entry_digest", "journal_head_observed",
            "operator_authentication",
            "read_only", "effect_performed", "grants_authority", "execution_allowed",
            "binding_digest",
        }
        body = dict(projection)
        claimed_binding = body.pop("binding_digest", None)
        observed_binding = hashlib.sha256(
            (json.dumps(_json_value(body), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        ).hexdigest()
        if (
            set(projection) != required
            or claimed_binding != observed_binding
            or projection.get("schema_version")
                != "sentientos.resident_cognitive_transition_verified_stage_receipt:v3"
            or (projection.get("campaign_trial_id") is not None
                and (not isinstance(projection.get("campaign_trial_id"), str)
                     or not projection.get("campaign_trial_id")))
            or projection.get("request_id") != request_id
            or any(not isinstance(projection.get(key), str) or not projection.get(key)
                for key in (
                    "request_digest", "installation_identity", "protocol_id",
                    "protocol_digest", "operator_receipt_digest", "attempt_entry_digest",
                    "completed_entry_digest", "journal_head_observed",
                ))
            or projection.get("read_only") is not True
            or projection.get("effect_performed") is not False
            or projection.get("grants_authority") is not False
            or projection.get("execution_allowed") is not False
        ):
            raise ProductionSelfReflectionError("transition_stage_receipt_binding_invalid")

        operator_authentication = projection.get("operator_authentication")
        if (
            not isinstance(operator_authentication, Mapping)
            or set(operator_authentication) != {
                "schema_version", "operator_identity", "signing_key_id",
                "request_claims_digest", "provenance_digest", "signed_at",
                "trust_catalog_version", "trust_catalog_digest",
            }
            or operator_authentication.get("schema_version")
                != "sentientos.resident_cognitive_transition_operator_authentication_binding:v1"
            or any(
                not isinstance(operator_authentication.get(key), str)
                or not operator_authentication.get(key)
                for key in ("operator_identity", "signing_key_id", "request_claims_digest",
                            "provenance_digest", "signed_at", "trust_catalog_digest")
            )
            or re.fullmatch(r"[a-z0-9][a-z0-9._:/-]{0,127}",
                            str(operator_authentication.get("operator_identity"))) is None
            or re.fullmatch(r"ed25519-sha256:[0-9a-f]{64}",
                            str(operator_authentication.get("signing_key_id"))) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}",
                            str(operator_authentication.get("request_claims_digest"))) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}",
                            str(operator_authentication.get("provenance_digest"))) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}",
                            str(operator_authentication.get("trust_catalog_digest"))) is None
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                            str(operator_authentication.get("signed_at"))) is None
            or type(operator_authentication.get("trust_catalog_version")) is not int
            or operator_authentication.get("trust_catalog_version", 0) < 1
        ):
            raise ProductionSelfReflectionError("transition_stage_receipt_authentication_invalid")
        operator_authentication = MappingProxyType(dict(operator_authentication))

        phase = projection["phase"]
        phase_order = tuple(transition.get("phase_order", ()))
        semantic_entries = owner_status.get("semantically_verified_stage_entry_digests", ())
        if (
            not isinstance(phase, str)
            or not isinstance(semantic_entries, (list, tuple))
            or projection.get("installation_identity") != protocol.installation_identity
            or projection.get("protocol_id") != transition.get("protocol_id")
            or projection.get("protocol_digest") != transition.get("protocol_digest")
            or owner_config.installation_identity != protocol.installation_identity
            or owner_config.protocol_id != transition.get("protocol_id")
            or owner_config.protocol_digest != transition.get("protocol_digest")
            or owner_config.journal_identity != transition.get("journal_identity")
            or owner_protocol.get("installation_identity") != protocol.installation_identity
            or owner_protocol.get("protocol_id") != transition.get("protocol_id")
            or owner_protocol.get("protocol_digest") != transition.get("protocol_digest")
            or owner_protocol.get("journal_identity") != transition.get("journal_identity")
            or tuple(owner_protocol.get("phase_order", ())) != phase_order
            or phase_order != PHASES
            or phase not in phase_order[1:]
            or owner_status.get("protocol_id") != transition.get("protocol_id")
            or owner_status.get("protocol_digest") != transition.get("protocol_digest")
            or owner_status.get("current_phase") != phase
            or owner_status.get("current_journal_head") != projection.get("journal_head_observed")
            or owner_status.get("interrupted") is not False
            or owner_status.get("outstanding_stage") is not None
            or owner_status.get("replay_forbidden") is not False
            or projection.get("completed_entry_digest") not in semantic_entries
        ):
            raise ProductionSelfReflectionError("transition_stage_receipt_stale_or_unbound")

        phase_index = phase_order.index(phase)
        next_stage = phase_order[phase_index + 1] if phase_index + 1 < len(phase_order) else None
        plan: dict[str, Any] = {
            "schema_version": "sentientos.production_self_reflection_transition_stage_plan:v1",
            "status": "next_stage_planned" if next_stage is not None else "transition_sequence_complete",
            "protocol_id": protocol.protocol_id,
            "protocol_digest": protocol.protocol_digest,
            "campaign_state_digest": state.get("state_digest"),
            "campaign_trial_binding": "not_established_by_transition_receipt",
            "transition_request_trial_id": projection.get("campaign_trial_id"),
            "campaign_next_trial_id": state.get("next_trial_id"),
            "campaign_trial_in_progress": state.get("in_progress_trial_id") is not None,
            "prior_stage": phase,
            "next_stage": next_stage,
            "receipt_request_id": request_id,
            "receipt_binding_digest": claimed_binding,
            "operator_authentication": operator_authentication,
            "completed_entry_digest": projection["completed_entry_digest"],
            "next_stage_requires_separately_supplied_approval": next_stage is not None,
            "read_only": True,
            "effect_performed": False,
            "campaign_advanced": False,
            "grants_authority": False,
            "execution_allowed": False,
        }
        plan["plan_digest"] = _digest(_json_value(plan))
        return MappingProxyType(plan)
