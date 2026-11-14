"""Read-only resident observation of installation-scoped production-chat custody.

The chat process remains the sole mutable ledger owner. This observer opens only
fixed authenticated installation objects and validates one atomically replaced
ledger image; it never constructs an allocator or ledger writer.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import re
from typing import Any, Mapping

from .causal_resource_principal import CausalResourcePrincipal
from .causal_resource_principal_authentication import (
    RootIssuerProvenanceVerifier,
    RootPrincipalIssuerProvenance,
)
from .causal_resource_principal_currentness import (
    PrincipalCurrentnessVerifier,
    ReadOnlyPrincipalRevocationRegistry,
)
from .causal_resource_principal_ed25519 import CryptographyEd25519RootIssuerSignatureVerifier
from .causal_resource_principal_trust_catalog import ReadOnlyTrustedIssuerCatalog
from .governed_local_model_invocation import (
    MAX_INVOCATION_RECEIPT_BYTES, MAX_INVOCATION_RECEIPTS, validate_receipt,
)
from .chat_process_generation import (
    ChatProcessGenerationError,
    read_stored_chat_process_runtime_observation,
    verify_stored_chat_process_handoff,
)
from .conversation_session import compact_runtime_generation_attribution
from .runtime.local_model_chat_recovery import (
    LocalModelChatRecoveryError,
    inspect_chat_recovery_phase_custody,
)
from .governed_local_model_resource_allocation import (
    MAX_LEDGER_BYTES,
    GovernedLocalModelResourceAllocation,
    GovernedLocalModelResourceLedger,
    GovernedLocalModelResourceLedgerObservation,
    GovernedLocalModelResourcePolicy,
)
from .installation_state import (
    InstallationStateError, InstallationStateReadOnlyView, WindowsInstallationStateReadOnlyView,
)
from .local_model_production_serving import (
    ProductionServingError, read_serving_operation_attempts, read_serving_operation_history,
)
from .production_chat_resource_provisioning import (
    _NAMES,
    _manifest,
    _mapping,
    validate_resource_provisioning_id,
)

_RECEIPT_NAME = re.compile(r"lmrec-[0-9a-f]{24}\.json\Z")
_RECEIPT_TEMP_NAME = re.compile(r"\.lmrec-[0-9a-f]{24}\.json\.[A-Za-z0-9_-]{1,64}\.tmp\Z")
_REQUEST_NAME = re.compile(r"lmreq-[0-9a-f]{24}\Z")
_RESOURCE_ADMISSION_BINDING_SCHEMA = (
    "sentientos.governed_local_model_resource_allocation_admission_context:v1")
_RESOURCE_ADMISSION_WITNESS_SCHEMA = (
    "sentientos.resource_bound_inference_admission_witness:v3")
_RESOURCE_ADMISSION_WITNESS_SCHEMA_V2 = (
    "sentientos.resource_bound_inference_admission_witness:v2")
_RESOURCE_HOST_OBSERVATION_BINDING_SCHEMA = (
    "sentientos.resource_admission_host_observation_binding:v1")
_RESOURCE_RELEASE_RECEIPT_SCHEMA_V2 = (
    "sentientos.production_chat_resource_release_receipt:v2")
_RESOURCE_RELEASE_RECEIPT_SCHEMA_V3 = (
    "sentientos.production_chat_resource_release_receipt:v3")
_RESOURCE_RELEASE_RECEIPT_SCHEMA_V4 = (
    "sentientos.production_chat_resource_release_receipt:v4")
_RESOURCE_RELEASE_RECEIPT_SCHEMA_V5 = (
    "sentientos.production_chat_resource_release_receipt:v5")
_RESOURCE_RELEASE_NAME = re.compile(
    r"serving-resource-release-[0-9a-f]{24}\.json\Z")
_MAX_RESOURCE_RELEASE_RECEIPTS = 256


def _resource_release_reason_codes_valid(value: object) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) > 64:
        return False
    return all(isinstance(reason, str) and reason and len(reason) <= 128
        for reason in value)


def _resource_release_checks_valid(value: object) -> bool:
    return (isinstance(value, (list, tuple))
        and len(value) <= 128
        and all(isinstance(check, str) and check and len(check) <= 128
            for check in value))


class ProductionChatResourceObservationError(ValueError):
    """A selected installation source is absent or cannot be verified."""

    def __init__(self, code: str, *, status: str = "invalid") -> None:
        self.code = code
        self.status = status
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ProductionChatResourceObservation:
    installation_identity: str
    provisioning_id: str
    manifest_digest: str
    ledger: GovernedLocalModelResourceLedgerObservation
    invocation_receipts: tuple[Mapping[str, Any], ...]
    invocation_receipt_posture: str
    chat_process_generation_attributions: tuple[Mapping[str, Any], ...] = ()
    chat_process_generation_posture: str = "unknown"
    chat_process_recovery_transitions: tuple[Mapping[str, Any], ...] = ()
    chat_process_recovery_posture: str = "unknown"
    chat_process_runtime_observation: Mapping[str, Any] | None = None
    chat_process_runtime_observation_posture: str = "unknown"
    serving_operation_attempts: tuple[Mapping[str, Any], ...] = ()
    serving_operation_attempt_posture: str = "unknown"
    serving_operation_history: tuple[Mapping[str, Any], ...] = ()
    predecessor_invocation_receipts: tuple[Mapping[str, Any], ...] = ()
    predecessor_invocation_receipt_posture: str = "unknown"
    verified_inference_admission_decisions: tuple[Mapping[str, Any], ...] = ()
    inference_admission_decision_posture: str = "unknown"
    verified_resource_release_receipts: tuple[Mapping[str, Any], ...] = ()
    resource_release_receipt_posture: str = "unknown"


class ProductionChatResourceObservationOwner:
    """Explicit read-only selector for one preconfigured installation bundle."""

    __slots__ = ("_handle", "_provisioning_id")

    def __init__(self,
                 handle: InstallationStateReadOnlyView | WindowsInstallationStateReadOnlyView,
                 provisioning_id: str) -> None:
        if type(handle) not in (InstallationStateReadOnlyView, WindowsInstallationStateReadOnlyView):
            raise TypeError("read_only_installation_state_view_required")
        self._handle = handle
        self._provisioning_id = validate_resource_provisioning_id(provisioning_id)

    def observe(self) -> ProductionChatResourceObservation:
        prefix = f"local-model/resource-provisioning/{self._provisioning_id}/"

        def read(name: str, *, bound: int = 256 * 1024) -> bytes:
            try:
                value = self._handle.read_optional_regular_bounded(
                    prefix + _NAMES[name], max_bytes=bound)
            except InstallationStateError as exc:
                if exc.code == "state_parent_missing":
                    raise ProductionChatResourceObservationError("resource_bundle_missing", status="missing") from exc
                raise ProductionChatResourceObservationError(exc.code) from exc
            if value is None:
                raise ProductionChatResourceObservationError("resource_bundle_missing", status="missing")
            return value

        manifest = _manifest(read("manifest"), provisioning_id=self._provisioning_id,
                             installation_identity=self._handle.identity.value)
        principal = CausalResourcePrincipal.from_mapping(_mapping(read("principal"), "principal_json_invalid"))
        if (principal.principal_id != manifest["principal_id"]
                or principal.binding_digest != manifest["principal_binding_digest"]):
            raise ProductionChatResourceObservationError("manifest_principal_mismatch")
        provenance = RootPrincipalIssuerProvenance.from_mapping(
            _mapping(read("provenance"), "provenance_json_invalid"))
        if provenance.provenance_digest != manifest["provenance_digest"]:
            raise ProductionChatResourceObservationError("manifest_provenance_mismatch")
        catalog_version = manifest.get("trusted_issuer_catalog_version")
        registry_version = manifest.get("revocation_registry_version")
        if (type(catalog_version) is not int or type(registry_version) is not int):
            raise ProductionChatResourceObservationError("resource_manifest_version_invalid")
        catalog = ReadOnlyTrustedIssuerCatalog.from_bytes(
            read("catalog"), expected_catalog_version=catalog_version,
            expected_catalog_digest=str(manifest["trusted_issuer_catalog_digest"]))
        registry = ReadOnlyPrincipalRevocationRegistry.from_bytes(
            read("registry"), expected_registry_version=registry_version,
            expected_registry_digest=str(manifest["revocation_registry_digest"]))
        # Reuse these immutable validated views for historical provenance and
        # currentness checks below. Keeping them local grants no mutation or
        # allocation authority to this observer.
        policy = GovernedLocalModelResourcePolicy.from_mapping(_mapping(read("policy"), "policy_json_invalid"))
        if policy.policy_digest != manifest["resource_policy_digest"]:
            raise ProductionChatResourceObservationError("manifest_policy_mismatch")
        try:
            ledger_bytes = self._handle.read_optional_regular_bounded(
                prefix + _NAMES["ledger"], max_bytes=MAX_LEDGER_BYTES)
        except InstallationStateError as exc:
            raise ProductionChatResourceObservationError(exc.code) from exc
        if ledger_bytes is None:
            raise ProductionChatResourceObservationError("resource_ledger_missing", status="missing")
        try:
            ledger = GovernedLocalModelResourceLedger.read_only_snapshot(ledger_bytes, max_bytes=MAX_LEDGER_BYTES)
        except ValueError as exc:
            raise ProductionChatResourceObservationError("resource_ledger_invalid") from exc
        snapshot = ledger.observation_snapshot()
        allocation_rows = snapshot.get("allocations")
        if not isinstance(allocation_rows, (list, tuple)) or len(allocation_rows) != 1:
            raise ProductionChatResourceObservationError("resource_bundle_allocation_count_mismatch")
        allocation_row = allocation_rows[0]
        if not isinstance(allocation_row, Mapping):
            raise ProductionChatResourceObservationError("resource_bundle_allocation_count_mismatch")
        allocation = (GovernedLocalModelResourceAllocation.from_mapping(allocation_row)
            if allocation_row.get("allocation_id") == manifest["allocation_id"] else None)
        if allocation is None:
            raise ProductionChatResourceObservationError("manifest_allocation_missing")
        bindings = (
            (allocation.allocation_digest, manifest["allocation_digest"]),
            (allocation.resource_kind, manifest["resource_kind"]),
            (allocation.allocator_id, manifest["allocator_id"]),
            (allocation.principal_id, manifest["principal_id"]),
            (allocation.principal_binding_digest, manifest["principal_binding_digest"]),
            (allocation.policy_digest, manifest["resource_policy_digest"]),
        )
        if any(actual != expected for actual, expected in bindings):
            raise ProductionChatResourceObservationError("manifest_allocation_mismatch")
        try:
            authenticated = RootIssuerProvenanceVerifier(
                trust_store=catalog,
                signature_verifier=CryptographyEd25519RootIssuerSignatureVerifier(),
            ).verify(principal, provenance,
                     current_time=allocation.validity.principal_currentness_checked_at)
            PrincipalCurrentnessVerifier().verify(
                principal, authenticated, registry,
                current_time=allocation.validity.principal_currentness_checked_at)
        except (TypeError, ValueError) as exc:
            raise ProductionChatResourceObservationError("historical_principal_binding_invalid") from exc
        (invocation_receipts, receipt_posture, generation_attributions,
         predecessor_receipts, predecessor_receipt_posture, admission_witnesses,
         admission_posture) = self._invocation_receipts(
            allocation)
        completed_invocations = tuple(item for item in invocation_receipts
            if item.get("status") == "admitted_completed"
            and isinstance(item.get("effects"), Mapping)
            and item["effects"].get("local_model_inference") is True)
        if not completed_invocations:
            generation_posture = "unknown_no_completed_invocations"
        elif len(generation_attributions) == len(completed_invocations):
            generation_posture = "verified"
        elif generation_attributions:
            generation_posture = "partial_legacy_or_unavailable"
        else:
            generation_posture = "unknown_legacy_or_unavailable"
        try:
            recovery_transitions = inspect_chat_recovery_phase_custody(self._handle, max_records=256)
            recovery_posture = ("verified_phase_custody" if recovery_transitions
                else "unknown_no_phase_custody")
        except LocalModelChatRecoveryError as exc:
            # The Windows view intentionally exposes only held-handle reads;
            # its directory API cannot distinguish an absent optional phase
            # directory from an unreadable one. Do not turn that ambiguity into
            # a claim that there were no recovery transitions.
            if os.name == "nt" and "directory" in exc.code:
                recovery_transitions = ()
                recovery_posture = "unknown_windows_read_only_phase_enumeration_unavailable"
            else:
                raise ProductionChatResourceObservationError(
                    "chat_process_recovery_custody_invalid:" + exc.code) from exc
        try:
            runtime_observation = read_stored_chat_process_runtime_observation(self._handle)
        except ChatProcessGenerationError as exc:
            raise ProductionChatResourceObservationError(
                "chat_process_runtime_observation_invalid:" + str(exc)) from exc
        if runtime_observation is None:
            runtime_observation_posture = "unknown_missing"
        elif runtime_observation.get("runtime_status") == "running_observed":
            runtime_observation_posture = "historically_observed_running"
        else:
            runtime_observation_posture = "historically_not_verified"
        try:
            serving_attempts = read_serving_operation_attempts(self._handle, maximum=256)
        except ProductionServingError as exc:
            raise ProductionChatResourceObservationError(
                "serving_operation_attempt_custody_invalid:" + str(exc)) from exc
        serving_attempt_posture = (
            "verified_attempts_present" if serving_attempts else "verified_no_attempts")
        try:
            serving_operation_history = read_serving_operation_history(self._handle, maximum=256)
        except ProductionServingError as exc:
            raise ProductionChatResourceObservationError(
                "serving_operation_history_invalid:" + str(exc)) from exc
        resource_release_receipts, resource_release_posture = (
            self._resource_release_receipts(serving_operation_history,
                invocation_receipts))
        return ProductionChatResourceObservation(
            self._handle.identity.value, self._provisioning_id,
            str(manifest["manifest_digest"]), ledger, invocation_receipts, receipt_posture,
            generation_attributions, generation_posture, recovery_transitions, recovery_posture,
            runtime_observation, runtime_observation_posture,
            serving_attempts, serving_attempt_posture, serving_operation_history,
            predecessor_receipts, predecessor_receipt_posture,
            admission_witnesses, admission_posture,
            resource_release_receipts, resource_release_posture)

    def _resource_release_receipts(
            self, serving_operation_history: tuple[Mapping[str, Any], ...],
            invocation_receipts: tuple[Mapping[str, Any], ...]
            ) -> tuple[tuple[Mapping[str, Any], ...], str]:
        serving_by_session: dict[str, tuple[str, str, str]] = {}
        for history in serving_operation_history:
            serving_receipt = history.get("receipt")
            binding = (serving_receipt.get("binding")
                if isinstance(serving_receipt, Mapping) else None)
            if not isinstance(serving_receipt, Mapping) or not isinstance(binding, Mapping):
                continue
            session_id = serving_receipt.get("session_id")
            operation_id = binding.get("serving_operation_id")
            serving_receipt_id = serving_receipt.get("receipt_id")
            serving_receipt_digest = history.get("receipt_semantic_digest")
            if (isinstance(session_id, str) and session_id
                    and isinstance(operation_id, str) and operation_id
                    and isinstance(serving_receipt_id, str) and serving_receipt_id
                    and isinstance(serving_receipt_digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", serving_receipt_digest)):
                candidate = (operation_id, serving_receipt_id, serving_receipt_digest)
                prior = serving_by_session.get(session_id)
                if prior is not None and prior != candidate:
                    raise ProductionChatResourceObservationError(
                        "resource_release_serving_history_collision")
                serving_by_session[session_id] = candidate
        try:
            names = self._handle.list_regular_names(
                "local-model/serving/resource-release-receipts",
                max_entries=_MAX_RESOURCE_RELEASE_RECEIPTS)
        except InstallationStateError as exc:
            if exc.code == "state_directory_missing":
                return (), "verified_no_release_receipts"
            raise ProductionChatResourceObservationError(
                "resource_release_receipt_directory_invalid") from exc
        receipts: list[Mapping[str, Any]] = []
        seen_ids: set[str] = set()
        for name in names:
            if _RESOURCE_RELEASE_NAME.fullmatch(name) is None:
                raise ProductionChatResourceObservationError(
                    "resource_release_receipt_name_invalid")
            try:
                raw = self._handle.read_regular_bounded(
                    "local-model/serving/resource-release-receipts/" + name,
                    max_bytes=262_144)
            except InstallationStateError as exc:
                raise ProductionChatResourceObservationError(
                    "resource_release_receipt_read_invalid") from exc
            try:
                value = _mapping(raw, "resource_release_receipt_json_invalid")
            except ValueError as exc:
                raise ProductionChatResourceObservationError(
                    "resource_release_receipt_json_invalid") from exc
            receipt_id = value.get("receipt_id")
            semantic_digest = value.get("receipt_semantic_digest")
            body = dict(value)
            body.pop("receipt_semantic_digest", None)
            claimed_body = dict(body)
            claimed_body.pop("receipt_id", None)
            try:
                actual_semantic_digest = hashlib.sha256(json.dumps(
                    body, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
                actual_receipt_id = "serving-resource-release-" + hashlib.sha256(
                    json.dumps(claimed_body, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
            except (TypeError, ValueError) as exc:
                raise ProductionChatResourceObservationError(
                    "resource_release_receipt_canonicalization_invalid") from exc
            release_correlation = value.get("release_correlation_id")
            resource_observation = value.get("resource_observation")
            if (not isinstance(receipt_id, str) or receipt_id != name[:-5]
                    or receipt_id in seen_ids
                    or value.get("schema_version") not in {
                        _RESOURCE_RELEASE_RECEIPT_SCHEMA_V2,
                        _RESOURCE_RELEASE_RECEIPT_SCHEMA_V3,
                        _RESOURCE_RELEASE_RECEIPT_SCHEMA_V4,
                        _RESOURCE_RELEASE_RECEIPT_SCHEMA_V5}
                    or (value.get("status") == "admission_unrecorded"
                        and value.get("schema_version")
                            not in {_RESOURCE_RELEASE_RECEIPT_SCHEMA_V4,
                                _RESOURCE_RELEASE_RECEIPT_SCHEMA_V5})
                    or semantic_digest != actual_semantic_digest
                    or receipt_id != actual_receipt_id
                    or value.get("status") not in {
                        "worker_closed", "release_effect_unconfirmed", "denied",
                        "admission_unrecorded"}
                    or not isinstance(value.get("trigger_kind"), str)
                    or not value.get("trigger_kind")
                    or not isinstance(release_correlation, str)
                    or not release_correlation
                    or value.get("release_admission_decision_ref")
                        != f"kernel_decision:{release_correlation}"
                    or not isinstance(value.get("serving_session_id"), str)
                    or not isinstance(value.get("model_identity_digest"), str)
                    or not isinstance(resource_observation, Mapping)
                    or value.get("inference_performed") is not False
                    or value.get("host_mutation_performed") is not False):
                raise ProductionChatResourceObservationError(
                    "resource_release_receipt_binding_invalid")
            session_id = value.get("serving_session_id")
            operation_id = value.get("serving_operation_id")
            serving_binding = serving_by_session.get(str(session_id))
            if (serving_binding is None
                    or serving_binding[0] != operation_id):
                raise ProductionChatResourceObservationError(
                    "resource_release_serving_operation_linkage_invalid")
            release_outcome = value.get("release_admission_outcome")
            release_status = value.get("status")
            if ((release_status in {"worker_closed", "release_effect_unconfirmed"}
                    and release_outcome != "allow")
                    or (release_status == "admission_unrecorded"
                        and release_outcome != "allow")
                    or (release_status == "denied"
                        and release_outcome not in {"deny", "defer", "quarantine"})):
                raise ProductionChatResourceObservationError(
                    "resource_release_admission_outcome_status_mismatch")
            if value.get("schema_version") in {
                    _RESOURCE_RELEASE_RECEIPT_SCHEMA_V4,
                    _RESOURCE_RELEASE_RECEIPT_SCHEMA_V5}:
                witness = value.get("release_admission_witness")
                witness_fields = {
                    "schema_version", "outcome", "reason_codes", "current_phase",
                    "requested_phase", "authority_class", "action_kind", "actor",
                    "target_subsystem", "correlation_id", "admission_decision_ref"}
                if (not isinstance(witness, Mapping)
                        or set(witness) != witness_fields
                        or witness.get("schema_version")
                            != "sentientos.resource_release_admission_witness:v1"
                        or witness.get("outcome") != value.get("release_admission_outcome")
                        or witness.get("outcome") not in {
                            "allow", "deny", "defer", "quarantine"}
                        or witness.get("reason_codes") != value.get("release_reason_codes")
                        or witness.get("authority_class") != "local_model_resource_release"
                        or witness.get("action_kind") != "local_model_resource_release"
                        or witness.get("actor") not in {
                            "production_chat_host_resource_governor",
                            "production_chat_workload_resource_governor",
                            "production_chat_game_resource_governor"}
                        or witness.get("target_subsystem") != "production_chat"
                        or witness.get("correlation_id") != release_correlation
                        or not isinstance(witness.get("correlation_id"), str)
                        or len(witness["correlation_id"]) > 256
                        or witness.get("admission_decision_ref")
                            != value.get("release_admission_decision_ref")
                        or witness.get("admission_decision_ref")
                            != f"kernel_decision:{release_correlation}"
                        or witness.get("current_phase") not in {
                            "bootstrap", "runtime", "maintenance", "shutdown"}
                        or witness.get("requested_phase") != "runtime"
                        or not _resource_release_reason_codes_valid(
                            witness.get("reason_codes"))):
                    raise ProductionChatResourceObservationError(
                        "resource_release_admission_witness_invalid")
            if value.get("schema_version") == _RESOURCE_RELEASE_RECEIPT_SCHEMA_V5:
                host_measurement_binding_posture: str | None = None
                witness = value.get("release_admission_witness")
                if not isinstance(witness, Mapping):
                    raise ProductionChatResourceObservationError(
                        "resource_release_admission_witness_invalid")
                admission_record = value.get("release_admission_record")
                expected_record_fields = {
                    "event_type", "timestamp", "final_disposition", "outcome",
                    "reason_codes", "delegate_checks_consulted", "lifecycle_phase",
                    "current_phase", "requested_phase", "authority_class", "action_kind",
                    "actor_source", "actor", "execution_owner", "target_subsystem",
                    "delegated_outcomes", "federation_context", "proof_budget_context",
                    "protected_mutation_intent", "correlation_id", "admission_decision_ref"}
                if admission_record is None:
                    if release_status in {"worker_closed", "release_effect_unconfirmed"}:
                        raise ProductionChatResourceObservationError(
                            "resource_release_admission_record_missing")
                elif (not isinstance(admission_record, Mapping)
                        or release_status == "admission_unrecorded"
                        or set(admission_record) != expected_record_fields
                        or admission_record.get("event_type") != "control_plane_decision"
                        or not isinstance(admission_record.get("timestamp"), str)
                        or not admission_record.get("timestamp")
                        or admission_record.get("final_disposition")
                            != value.get("release_admission_outcome")
                        or admission_record.get("outcome")
                            != value.get("release_admission_outcome")
                        or admission_record.get("reason_codes")
                            != value.get("release_reason_codes")
                        or admission_record.get("authority_class")
                            != "local_model_resource_release"
                        or admission_record.get("action_kind")
                            != "local_model_resource_release"
                        or admission_record.get("actor")
                            != witness.get("actor")
                        or admission_record.get("actor_source")
                            != admission_record.get("actor")
                        or admission_record.get("execution_owner")
                            != admission_record.get("actor")
                        or admission_record.get("target_subsystem")
                            != "production_chat"
                        or admission_record.get("current_phase")
                            != witness.get("current_phase")
                        or admission_record.get("lifecycle_phase")
                            != admission_record.get("current_phase")
                        or admission_record.get("requested_phase") != "runtime"
                        or admission_record.get("correlation_id") != release_correlation
                        or admission_record.get("admission_decision_ref")
                            != value.get("release_admission_decision_ref")
                        or not _resource_release_checks_valid(
                            admission_record.get("delegate_checks_consulted"))
                        or not isinstance(admission_record.get("delegated_outcomes"), Mapping)):
                    raise ProductionChatResourceObservationError(
                        "resource_release_admission_record_invalid")
                receipt_observation = value.get("resource_observation")
                if (isinstance(receipt_observation, Mapping)
                        and receipt_observation.get(
                            "host_telemetry_used_for_admission") is True):
                    delegated = (admission_record.get("delegated_outcomes")
                        if isinstance(admission_record, Mapping) else None)
                    runtime_governor = (delegated.get("runtime_governor")
                        if isinstance(delegated, Mapping) else None)
                    evidence_refs = (runtime_governor.get("evidence_refs")
                        if isinstance(runtime_governor, Mapping) else None)
                    evidence = (evidence_refs.get("resource_observation_evidence")
                        if isinstance(evidence_refs, Mapping) else None)
                    if admission_record is None:
                        host_measurement_binding_posture = (
                            "admission_unrecorded" if release_status == "admission_unrecorded"
                            else "admission_record_missing")
                    elif release_status == "denied":
                        host_measurement_binding_posture = "admission_denied"
                    elif isinstance(evidence, Mapping):
                        if (evidence.get("status") != "current"
                                or evidence.get("observation_correlation_id")
                                    != receipt_observation.get(
                                        "observation_correlation_id")
                                or evidence.get("host_report_id")
                                    != receipt_observation.get("host_report_id")
                                or evidence.get("pressure_labels")
                                    != receipt_observation.get("pressure_labels")):
                            raise ProductionChatResourceObservationError(
                                "resource_release_host_observation_admission_mismatch")
                        evidence_digest = evidence.get("host_report_digest")
                        digest_bound = (isinstance(evidence_digest, str)
                            and re.fullmatch(r"[0-9a-f]{64}", evidence_digest) is not None
                            and evidence_digest == receipt_observation.get(
                                "host_report_digest"))
                        if ("host_report_digest" in evidence and not digest_bound):
                            raise ProductionChatResourceObservationError(
                                "resource_release_host_observation_admission_mismatch")
                        game_message_id = receipt_observation.get(
                            "game_workload_message_id")
                        if (game_message_id is not None
                                and evidence.get("game_workload_message_id")
                                    != game_message_id):
                            raise ProductionChatResourceObservationError(
                                "resource_release_host_observation_admission_mismatch")
                        if ("active_inference_preemption_requested" in evidence
                                and evidence.get("active_inference_preemption_requested")
                                    != value.get(
                                        "active_inference_preemption_requested")):
                            raise ProductionChatResourceObservationError(
                                "resource_release_host_observation_admission_mismatch")
                        measurement_fields = tuple(field for field in (
                            "gpu_utilization_percent", "vram_utilization_percent",
                            "ram_utilization_percent")
                            if field in receipt_observation)
                        recorded_measurement_fields = set(measurement_fields).intersection(
                            evidence)
                        for field in recorded_measurement_fields:
                            if evidence.get(field) != receipt_observation.get(field):
                                raise ProductionChatResourceObservationError(
                                    "resource_release_host_observation_admission_mismatch")
                        if game_message_id is not None:
                            game_measurement_fields = {
                                "gpu_utilization_percent", "vram_utilization_percent"}
                            game_evidence_v2 = evidence.get("schema_version") == (
                                "sentientos.production_game_host_resource_release_evidence:v2")
                            if ((recorded_measurement_fields and
                                    (recorded_measurement_fields != game_measurement_fields
                                    or not game_evidence_v2))
                                    or (game_evidence_v2 and
                                        recorded_measurement_fields != game_measurement_fields)):
                                raise ProductionChatResourceObservationError(
                                    "resource_release_host_observation_admission_mismatch")
                        fully_bound = (digest_bound and bool(measurement_fields)
                            and recorded_measurement_fields == set(measurement_fields)
                            and (game_message_id is None or bool(recorded_measurement_fields)))
                        host_measurement_binding_posture = (
                            "verified" if fully_bound else
                            "legacy_report_bound_measurements_unbound")
                    else:
                        raise ProductionChatResourceObservationError(
                            "resource_release_host_observation_admission_mismatch")
                if (value.get("active_inference_cancellation_confirmed") is True
                        and isinstance(admission_record, Mapping)):
                    delegated = admission_record.get("delegated_outcomes")
                    runtime_governor = (delegated.get("runtime_governor")
                        if isinstance(delegated, Mapping) else None)
                    evidence_refs = (runtime_governor.get("evidence_refs")
                        if isinstance(runtime_governor, Mapping) else None)
                    request_reference = value.get("active_inference_request_reference")
                    resource_evidence = (evidence_refs.get(
                        "resource_observation_evidence")
                        if isinstance(evidence_refs, Mapping) else None)
                    if (not isinstance(request_reference, Mapping)
                            or not isinstance(evidence_refs, Mapping)
                            or evidence_refs.get("active_inference_request_reference")
                                != request_reference
                            or not isinstance(resource_evidence, Mapping)
                            or resource_evidence.get(
                                "active_inference_preemption_requested") is not True):
                        raise ProductionChatResourceObservationError(
                            "resource_release_cancelled_invocation_admission_evidence_mismatch")
            seen_ids.add(receipt_id)
            verified_value = dict(value)
            verified_value["serving_receipt_linkage_posture"] = "verified"
            verified_value["serving_receipt_id"] = serving_binding[1]
            verified_value["serving_receipt_semantic_digest"] = serving_binding[2]
            if (value.get("schema_version") == _RESOURCE_RELEASE_RECEIPT_SCHEMA_V5
                    and host_measurement_binding_posture is not None):
                verified_value["host_measurement_binding_posture"] = (
                    host_measurement_binding_posture)
            if value.get("schema_version") in {
                    _RESOURCE_RELEASE_RECEIPT_SCHEMA_V3,
                    _RESOURCE_RELEASE_RECEIPT_SCHEMA_V4,
                    _RESOURCE_RELEASE_RECEIPT_SCHEMA_V5}:
                request_reference = value.get("active_inference_request_reference")
                cancellation_confirmed = (
                    value.get("active_inference_cancellation_confirmed") is True)
                if cancellation_confirmed:
                    if (not isinstance(request_reference, Mapping)
                            or set(request_reference) != {
                                "request_id", "request_digest", "correlation_id"}
                            or not all(isinstance(request_reference.get(key), str)
                                and request_reference.get(key)
                                for key in ("request_id", "request_digest", "correlation_id"))):
                        raise ProductionChatResourceObservationError(
                            "resource_release_cancelled_invocation_reference_invalid")
                    matched_invocations = []
                    for invocation in invocation_receipts:
                        request = invocation.get("request")
                        if (isinstance(request, Mapping)
                                and request.get("request_id")
                                    == request_reference.get("request_id")
                                and request.get("request_digest")
                                    == request_reference.get("request_digest")
                                and request.get("correlation_id")
                                    == request_reference.get("correlation_id")):
                            matched_invocations.append(invocation)
                    if len(matched_invocations) > 1:
                        raise ProductionChatResourceObservationError(
                            "resource_release_invocation_identity_collision")
                    if not matched_invocations:
                        verified_value["invocation_linkage_posture"] = (
                            "pending_invocation_receipt")
                    else:
                        invocation = matched_invocations[0]
                        reasons = invocation.get("reason_codes")
                        if (invocation.get("status") != "cancelled"
                                or not isinstance(reasons, (list, tuple))
                                or "cancelled_for_workload_transition" not in reasons
                                or invocation.get("cancellation_admission_decision_ref")
                                    != value.get("release_admission_decision_ref")):
                            raise ProductionChatResourceObservationError(
                                "resource_release_cancelled_invocation_binding_invalid")
                        if (invocation.get("schema_version") in {
                                "sentientos.local_model_invocation_receipt:v7",
                                "sentientos.local_model_invocation_receipt:v8",
                                "sentientos.local_model_invocation_receipt:v9",
                                "sentientos.local_model_invocation_receipt:v10"}
                                and (not isinstance(value.get("release_admission_record"), Mapping)
                                    or invocation.get("cancellation_admission_record")
                                        != value.get("release_admission_record"))):
                            raise ProductionChatResourceObservationError(
                                "resource_release_cancelled_invocation_admission_record_mismatch")
                        verified_value["invocation_linkage_posture"] = "verified"
                        verified_value["cancelled_invocation_receipt_id"] = (
                            invocation.get("receipt_id"))
                        verified_value["cancelled_invocation_receipt_digest"] = (
                            invocation.get("receipt_digest"))
                        if (invocation.get("schema_version") ==
                                "sentientos.local_model_invocation_receipt:v10"
                                and isinstance(invocation.get(
                                    "cancellation_preemption_ref"), Mapping)):
                            verified_value[
                                "cancelled_invocation_preemption_ref"] = dict(
                                    invocation["cancellation_preemption_ref"])
                else:
                    verified_value["invocation_linkage_posture"] = "not_required"
            elif value.get("active_inference_cancellation_confirmed") is True:
                verified_value["invocation_linkage_posture"] = "legacy_unlinked"
            else:
                verified_value["invocation_linkage_posture"] = "not_required"
            receipts.append(verified_value)
        receipts.sort(key=lambda item: str(item.get("receipt_id", "")))
        if not receipts:
            posture = "verified_no_release_receipts"
        elif any(item.get("status") == "admission_unrecorded" for item in receipts):
            posture = "admission_unrecorded"
        elif any(item.get("invocation_linkage_posture") ==
                "pending_invocation_receipt" for item in receipts):
            posture = "pending_invocation_receipts"
        elif any(item.get("invocation_linkage_posture") == "legacy_unlinked"
                for item in receipts):
            posture = "partial_legacy_unlinked"
        else:
            posture = "verified"
        return tuple(receipts), posture

    def _resource_admission_witness(self, invocation: Mapping[str, Any],
                                    allocation: GovernedLocalModelResourceAllocation
                                    ) -> Mapping[str, Any]:
        raw_request = invocation.get("request")
        if not isinstance(raw_request, Mapping):
            raise ProductionChatResourceObservationError(
                "resource_invocation_request_identity_invalid")
        request = raw_request
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or _REQUEST_NAME.fullmatch(request_id) is None:
            raise ProductionChatResourceObservationError(
                "resource_invocation_request_identity_invalid")
        try:
            raw = self._handle.read_regular_bounded(
                f"local-model/inference/decisions/{request_id}.json",
                max_bytes=262_144)
        except InstallationStateError as exc:
            raise ProductionChatResourceObservationError(
                "resource_inference_admission_decision_unavailable") from exc
        try:
            decision = _mapping(raw, "resource_inference_admission_decision_json_invalid")
        except ValueError as exc:
            raise ProductionChatResourceObservationError(
                "resource_inference_admission_decision_json_invalid") from exc
        expected_decision_fields = {
            "event_type", "timestamp", "final_disposition", "outcome", "reason_codes",
            "delegate_checks_consulted", "lifecycle_phase", "current_phase",
            "requested_phase", "authority_class", "action_kind", "actor_source", "actor",
            "execution_owner", "target_subsystem", "delegated_outcomes", "federation_context",
            "proof_budget_context", "protected_mutation_intent", "correlation_id",
            "admission_decision_ref",
        }
        correlation_id = request.get("correlation_id")
        expected_binding = {
            "schema_version": _RESOURCE_ADMISSION_BINDING_SCHEMA,
            "allocation_id": allocation.allocation_id,
            "allocation_digest": allocation.allocation_digest,
            "allocator_id": allocation.allocator_id,
            "resource_kind": allocation.resource_kind,
            "policy_digest": allocation.policy_digest,
            "policy_epoch": allocation.epoch,
            "principal_binding_digest": allocation.principal_binding_digest,
        }
        request_linkage = request.get("linkage")
        host_observation = (request_linkage.get("host_resource_observation")
            if isinstance(request_linkage, Mapping) else None)
        delegated = decision.get("delegated_outcomes")
        runtime = delegated.get("runtime_governor") if isinstance(delegated, Mapping) else None
        evidence = runtime.get("evidence_refs") if isinstance(runtime, Mapping) else None
        binding = evidence.get("resource_allocation_binding") if isinstance(evidence, Mapping) else None
        host_evidence = (evidence.get("host_resource_evidence")
            if isinstance(evidence, Mapping) else None)
        host_observation_binding = None
        if isinstance(host_observation, Mapping) and host_observation.get("status") == "current":
            host_fields = (
                "evaluation_id", "semantic_digest", "epoch_id", "snapshot_id",
                "report_id", "report_digest", "observation_correlation_id",
                "observed_at", "pressure_labels", "cpu_utilization_percent",
                "ram_utilization_percent", "gpu_utilization_percent",
                "vram_utilization_percent", "thermal_zone_temperatures_c",
                "gpu_telemetry_available", "gpu_telemetry_complete",
                "gpu_telemetry_sources")
            host_values = {key: host_observation.get(key) for key in host_fields}

            def normalized_labels(value: object) -> tuple[str, ...]:
                if (not isinstance(value, (list, tuple))
                        or not all(isinstance(label, str) for label in value)):
                    raise ProductionChatResourceObservationError(
                        "resource_inference_host_observation_binding_invalid")
                return tuple(sorted(set(value)))

            def normalized_sources(value: object) -> tuple[Mapping[str, str], ...]:
                source_fields = {"collector_id", "status", "source"}
                if not isinstance(value, (list, tuple)):
                    raise ProductionChatResourceObservationError(
                        "resource_inference_host_observation_binding_invalid")
                normalized: list[Mapping[str, str]] = []
                for source in value:
                    if (not isinstance(source, Mapping)
                            or set(source) != source_fields
                            or not all(isinstance(source.get(key), str)
                                and source.get(key) and len(source[key]) <= 128
                                for key in source_fields)):
                        raise ProductionChatResourceObservationError(
                            "resource_inference_host_observation_binding_invalid")
                    normalized.append({key: source[key] for key in (
                        "collector_id", "status", "source")})
                return tuple(normalized)

            host_values["pressure_labels"] = normalized_labels(
                host_values.get("pressure_labels"))
            host_values["gpu_telemetry_sources"] = normalized_sources(
                host_values.get("gpu_telemetry_sources"))
            if (not isinstance(host_evidence, Mapping)
                    or host_evidence.get("status") != "current"
                    or host_observation.get("no_effect_authority") is not True
                    or host_evidence.get("pressure_labels") is None):
                raise ProductionChatResourceObservationError(
                    "resource_inference_host_observation_binding_invalid")
            evidence_values = {key: host_evidence.get(key) for key in host_fields}
            evidence_values["pressure_labels"] = normalized_labels(
                evidence_values.get("pressure_labels"))
            evidence_values["gpu_telemetry_sources"] = normalized_sources(
                evidence_values.get("gpu_telemetry_sources"))
            if evidence_values != host_values:
                raise ProductionChatResourceObservationError(
                    "resource_inference_host_observation_binding_mismatch")
            host_observation_binding = {
                "schema_version": _RESOURCE_HOST_OBSERVATION_BINDING_SCHEMA,
                "status": "current",
                **host_values,
            }
        if (set(decision) != expected_decision_fields
                or decision.get("event_type") != "control_plane_decision"
                or not isinstance(decision.get("timestamp"), str)
                or decision.get("final_disposition") != "allow"
                or decision.get("outcome") != "allow"
                or decision.get("authority_class") != "local_model_inference"
                or decision.get("action_kind") != "local_model_inference"
                or decision.get("target_subsystem") != "governed_local_model_invocation"
                or not isinstance(correlation_id, str)
                or decision.get("correlation_id") != correlation_id
                or decision.get("admission_decision_ref") != invocation.get(
                    "admission_decision_ref")
                or decision.get("admission_decision_ref") != f"kernel_decision:{correlation_id}"
                or decision.get("actor") != request.get("caller")
                or decision.get("actor_source") != request.get("caller")
                or decision.get("execution_owner") != request.get("caller")
                or not isinstance(binding, Mapping)
                or dict(binding) != expected_binding):
            raise ProductionChatResourceObservationError(
                "resource_inference_admission_binding_invalid")
        if (invocation.get("schema_version") in {
                "sentientos.local_model_invocation_receipt:v8",
                "sentientos.local_model_invocation_receipt:v9",
                "sentientos.local_model_invocation_receipt:v10"}
                and decision != invocation.get("admission_decision_record")):
            raise ProductionChatResourceObservationError(
                "resource_inference_admission_record_mismatch")
        return {
            "schema_version": (_RESOURCE_ADMISSION_WITNESS_SCHEMA
                if invocation.get("schema_version") in {
                    "sentientos.local_model_invocation_receipt:v8",
                    "sentientos.local_model_invocation_receipt:v9",
                    "sentientos.local_model_invocation_receipt:v10"}
                else _RESOURCE_ADMISSION_WITNESS_SCHEMA_V2),
            "invocation_receipt_id": invocation.get("receipt_id"),
            "invocation_receipt_digest": invocation.get("receipt_digest"),
            "request_id": request_id,
            "request_digest": request.get("request_digest"),
            "admission_decision_ref": decision["admission_decision_ref"],
            "correlation_id": correlation_id,
            "resource_allocation_binding": expected_binding,
            "host_resource_observation_binding": host_observation_binding,
            **({"admission_decision_record": dict(decision)}
                if invocation.get("schema_version") in {
                    "sentientos.local_model_invocation_receipt:v8",
                    "sentientos.local_model_invocation_receipt:v9",
                    "sentientos.local_model_invocation_receipt:v10"} else {}),
        }

    def _invocation_receipts(self, allocation: GovernedLocalModelResourceAllocation
            ) -> tuple[tuple[Mapping[str, Any], ...], str, tuple[Mapping[str, Any], ...],
                       tuple[Mapping[str, Any], ...], str,
                       tuple[Mapping[str, Any], ...], str]:
        try:
            names = self._handle.list_regular_names(
                "local-model/inference/receipts", max_entries=MAX_INVOCATION_RECEIPTS)
        except InstallationStateError as exc:
            if exc.code == "state_directory_missing":
                return (), "degraded_missing_receipt_directory", (), (), "degraded_missing_receipt_directory", (), "degraded_missing_admission_decisions"
            raise ProductionChatResourceObservationError("invocation_receipt_directory_invalid") from exc
        receipts: list[Mapping[str, Any]] = []
        generation_attributions: list[Mapping[str, Any]] = []
        admission_witnesses: list[Mapping[str, Any]] = []
        verified_receipts_by_id: dict[str, Mapping[str, Any]] = {}
        for name in names:
            if _RECEIPT_TEMP_NAME.fullmatch(name) is not None:
                continue  # Incomplete atomic-write staging is never receipt evidence.
            if _RECEIPT_NAME.fullmatch(name) is None:
                raise ProductionChatResourceObservationError("invocation_receipt_name_invalid")
            try:
                raw = self._handle.read_regular_bounded(
                    f"local-model/inference/receipts/{name}", max_bytes=MAX_INVOCATION_RECEIPT_BYTES)
            except InstallationStateError as exc:
                raise ProductionChatResourceObservationError("invocation_receipt_read_invalid") from exc
            try:
                value = _mapping(raw, "invocation_receipt_json_invalid")
            except ValueError as exc:
                raise ProductionChatResourceObservationError("invocation_receipt_json_invalid") from exc
            if value.get("receipt_id") != name[:-5]:
                raise ProductionChatResourceObservationError("invocation_receipt_filename_mismatch")
            valid, findings = validate_receipt(value)
            if not valid:
                raise ProductionChatResourceObservationError("invocation_receipt_invalid:" + findings[0])
            receipt_id = str(value["receipt_id"])
            prior = verified_receipts_by_id.get(receipt_id)
            if prior is not None:
                if dict(prior) != dict(value):
                    raise ProductionChatResourceObservationError("invocation_receipt_identity_conflict")
                raise ProductionChatResourceObservationError("invocation_receipt_duplicate_identity")
            verified_receipts_by_id[receipt_id] = dict(value)
            request = value.get("request")
            linkage = request.get("linkage") if isinstance(request, Mapping) else None
            software = linkage.get("software_generation_attribution") if isinstance(linkage, Mapping) else None
            verified_software = None
            if software is not None:
                legacy_unavailable = {
                    "status": "unavailable",
                    "reason_code": "authenticated_chat_process_generation_issuer_not_composed",
                    "generation_identity": None,
                    "process_instance_id": None,
                }
                if software == legacy_unavailable:
                    verified_software = None
                elif (not isinstance(software, Mapping)
                        or software.get("status") != "runtime_launcher_process_and_source_bound"
                        or not isinstance(software.get("handoff_id"), str)
                        or not isinstance(software.get("handoff_digest"), str)):
                    raise ProductionChatResourceObservationError(
                        "invocation_software_generation_attribution_invalid")
                else:
                    try:
                        historical = verify_stored_chat_process_handoff(
                            handle=self._handle,
                            handoff_id=str(software["handoff_id"]),
                            expected_digest=str(software["handoff_digest"]))
                    except ChatProcessGenerationError as exc:
                        raise ProductionChatResourceObservationError(
                            "invocation_software_generation_handoff_invalid") from exc
                    if dict(software) != dict(historical):
                        raise ProductionChatResourceObservationError(
                            "invocation_software_generation_handoff_mismatch")
                    verified_software = dict(historical)
            if value.get("resource_allocation_digest") == allocation.allocation_digest:
                receipts.append(dict(value))
                admission_witnesses.append(self._resource_admission_witness(
                    value, allocation))
                request = value.get("request")
                effects = value.get("effects")
                if (verified_software is not None
                        and isinstance(request, Mapping)
                        and value.get("status") == "admitted_completed"
                        and isinstance(effects, Mapping)
                        and effects.get("local_model_inference") is True
                        and isinstance(value.get("output_digest"), str)):
                    compact_handoff = compact_runtime_generation_attribution(verified_software)
                    generation_attributions.append({
                        "invocation_receipt_id": value["receipt_id"],
                        "invocation_receipt_digest": value["receipt_digest"],
                        "invocation_request_id": request.get("request_id"),
                        "invocation_request_digest": request.get("request_digest"),
                        "chat_process_handoff": compact_handoff,
                        "attribution_posture": "invocation_receipt_and_historical_chat_handoff_verified",
                        "currentness_posture": "historical_process_identity_not_reobserved_during_recovery",
                    })
        receipts.sort(key=lambda item: (str(item.get("observed_at", "")), str(item.get("receipt_id", ""))))
        generation_attributions.sort(key=lambda item: (
            str(item.get("invocation_receipt_id", "")), str(item.get("invocation_receipt_digest", ""))))

        # Parent receipts corroborate only the digest-bound caller reference of
        # a selected invocation. They stay separate from allocation-scoped
        # invocation evidence and cannot add another resource consequence.
        referenced_parent_ids: set[str] = set()
        missing_parent = False
        for invocation in receipts:
            request = invocation.get("request")
            linkage = request.get("linkage") if isinstance(request, Mapping) else None
            caller = linkage.get("caller_context") if isinstance(linkage, Mapping) else None
            reference = (caller.get("verified_predecessor_invocation")
                if isinstance(caller, Mapping) else None)
            if reference is None:
                continue
            if not isinstance(reference, Mapping) or not isinstance(reference.get("receipt_id"), str):
                raise ProductionChatResourceObservationError(
                    "invocation_predecessor_reference_invalid")
            parent_id = str(reference["receipt_id"])
            if parent_id == invocation.get("receipt_id"):
                raise ProductionChatResourceObservationError(
                    "invocation_predecessor_self_reference")
            if parent_id not in verified_receipts_by_id:
                missing_parent = True
                continue
            referenced_parent_ids.add(parent_id)
        predecessor_receipts = tuple(
            dict(verified_receipts_by_id[parent_id])
            for parent_id in sorted(referenced_parent_ids))
        if len(predecessor_receipts) > MAX_INVOCATION_RECEIPTS:
            raise ProductionChatResourceObservationError(
                "invocation_predecessor_receipt_bound_exceeded")
        if missing_parent:
            predecessor_posture = "degraded_missing_direct_parent_receipt"
        elif predecessor_receipts:
            predecessor_posture = "verified_direct_parent_receipts_present"
        else:
            predecessor_posture = "verified_no_direct_parent_reference"
        admission_witnesses.sort(key=lambda item: (
            str(item.get("invocation_receipt_id", "")),
            str(item.get("invocation_receipt_digest", ""))))
        return (tuple(receipts),
            "verified" if receipts else "degraded_no_resource_invocation_receipts",
            tuple(generation_attributions), predecessor_receipts, predecessor_posture,
            tuple(admission_witnesses),
            "verified" if len(admission_witnesses) == len(receipts)
            else "degraded_inference_admission_decision_linkage")


__all__ = [
    "ProductionChatResourceObservation", "ProductionChatResourceObservationError",
    "ProductionChatResourceObservationOwner",
]
