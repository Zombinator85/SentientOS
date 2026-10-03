"""Lock-free, read-only diagnostics for fixed provisioning publication custody."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from .installation_state import InstallationStateError, InstallationStateHandle
from .production_chat_resource_provisioning import validate_resource_provisioning_id
from .production_chat_resource_provisioning_actuator import (
    ProductionChatResourceProvisioningActuatorError,
    load_provisioning_request,
    prepare_provisioning_intent,
)
from .production_chat_resource_provisioning_request_consumer import (
    ProductionChatResourceProvisioningRequestConsumerError,
    load_published_production_chat_resource_provisioning_request,
)

SCHEMA = "sentientos.production_chat_resource_provisioning_request_publication_doctor:v1"

NON_AUTHORITY_POSTURE: Mapping[str, bool] = {
    "doctor_is_read_only": True,
    "doctor_does_not_lock": True,
    "doctor_does_not_mutate_installation_state": True,
    "doctor_does_not_publish": True,
    "doctor_does_not_create_receipt": True,
    "doctor_does_not_delete": True,
    "doctor_does_not_cleanup": True,
    "doctor_does_not_repair": True,
    "doctor_does_not_retry": True,
    "doctor_does_not_overwrite": True,
    "doctor_does_not_allocate": True,
    "doctor_does_not_execute": True,
    "doctor_does_not_create_final_bundle": True,
    "doctor_does_not_authorize_republication": True,
    "doctor_does_not_authorize_create": True,
    "doctor_does_not_infer_terminal_failure": True,
}


class ProductionChatResourceProvisioningRequestDoctorError(ValueError):
    """A bounded doctor-input error."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ProductionChatResourceProvisioningRequestDoctorReport:
    value: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.value)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _request_evidence(raw: bytes, handle: InstallationStateHandle,
                      selected: str) -> dict[str, object]:
    evidence: dict[str, object] = {
        "request_verification_status": "invalid",
        "request_verification_reason_code": None,
        "request_digest": None,
        "intent_digest": None,
        "request_installation_identity": None,
        "request_installation_identity_matches": None,
        "request_resource_provisioning_id": None,
        "request_resource_provisioning_id_matches": None,
    }
    try:
        request = load_provisioning_request(raw)
        evidence.update({
            "request_verification_status": "valid",
            "request_digest": request.request_digest,
            "request_installation_identity": request.installation_identity,
            "request_installation_identity_matches": request.installation_identity == handle.identity.value,
            "request_resource_provisioning_id": request.resource_provisioning_id,
            "request_resource_provisioning_id_matches": request.resource_provisioning_id == selected,
        })
        try:
            evidence["intent_digest"] = prepare_provisioning_intent(raw).intent_digest
        except ProductionChatResourceProvisioningActuatorError as exc:
            evidence["request_verification_status"] = "invalid"
            evidence["request_verification_reason_code"] = exc.code
    except ProductionChatResourceProvisioningActuatorError as exc:
        evidence["request_verification_reason_code"] = exc.code
    return evidence


def _finish(payload: dict[str, Any]) -> ProductionChatResourceProvisioningRequestDoctorReport:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    payload["doctor_report_id"] = "publication-doctor-" + _sha(encoded)[:24]
    return ProductionChatResourceProvisioningRequestDoctorReport(payload)


def diagnose_production_chat_resource_provisioning_request_publication(
    installation_handle: InstallationStateHandle,
    resource_provisioning_id: str,
) -> ProductionChatResourceProvisioningRequestDoctorReport:
    """Observe two fixed custody objects without locking or changing installation state."""
    if type(installation_handle) is not InstallationStateHandle:
        raise TypeError("authenticated_installation_state_handle_required")
    try:
        selected = validate_resource_provisioning_id(resource_provisioning_id)
    except (TypeError, ValueError) as exc:
        raise ProductionChatResourceProvisioningRequestDoctorError(
            "invalid_resource_provisioning_id") from exc

    prefix = f"local-model/resource-provisioning-requests/{selected}"
    request_raw: bytes | None = None
    receipt_raw: bytes | None = None
    unavailable_reason: str | None = None
    try:
        request_raw = installation_handle.read_optional_regular(
            installation_handle.fixed_object(prefix + "/request.json"))
        receipt_raw = installation_handle.read_optional_regular(
            installation_handle.fixed_object(prefix + "/publication-receipt.json"))
    except (InstallationStateError, OSError):
        unavailable_reason = "authenticated_custody_inspection_unavailable"

    base: dict[str, Any] = {
        "schema_version": SCHEMA,
        "installation_identity": installation_handle.identity.value,
        "resource_provisioning_id": selected,
        "overall_doctor_status": "publication_doctor_unavailable",
        "custody_shape": "custody_unavailable",
        "request_present": None if unavailable_reason else request_raw is not None,
        "receipt_present": None if unavailable_reason else receipt_raw is not None,
        "request_storage_sha256": _sha(request_raw) if request_raw is not None else None,
        "request_storage_bytes": len(request_raw) if request_raw is not None else None,
        "receipt_storage_sha256": _sha(receipt_raw) if receipt_raw is not None else None,
        "receipt_storage_bytes": len(receipt_raw) if receipt_raw is not None else None,
        "completed_publication_verification_status": "not_applicable",
        "verification_reason_code": unavailable_reason,
        "request_verification_status": "not_applicable",
        "request_verification_reason_code": None,
        "request_digest": None,
        "intent_digest": None,
        "request_installation_identity": None,
        "request_installation_identity_matches": None,
        "request_resource_provisioning_id": None,
        "request_resource_provisioning_id_matches": None,
        "publication_complete": False,
        "snapshot_is_lock_free": True,
        "concurrent_publication_excluded": False,
        "terminal_failure_inferred": False,
        "existing_object_forbids_automatic_same_id_retry": None,
        "next_inspection_guidance": "inspect_authenticated_custody_availability",
        "non_authority_posture": dict(NON_AUTHORITY_POSTURE),
    }
    if unavailable_reason:
        return _finish(base)

    if request_raw is not None and receipt_raw is not None:
        base.update({"custody_shape": "complete_pair",
                     "existing_object_forbids_automatic_same_id_retry": True,
                     "next_inspection_guidance": "separately_governed_recovery_review_required"})
        try:
            verified = load_published_production_chat_resource_provisioning_request(
                installation_handle, selected)
            base.update({"overall_doctor_status": "publication_doctor_complete",
                         "completed_publication_verification_status": "verified",
                         "publication_complete": True})
            base.update(_request_evidence(verified, installation_handle, selected))
        except ProductionChatResourceProvisioningRequestConsumerError as exc:
            base.update({"overall_doctor_status": "publication_doctor_invalid",
                         "completed_publication_verification_status": "invalid",
                         "verification_reason_code": exc.code})
        return _finish(base)

    if request_raw is not None:
        base.update({
            "overall_doctor_status": "publication_doctor_incomplete",
            "custody_shape": "bare_request",
            "verification_reason_code": "unpublished_incomplete_custody_at_observation_time",
            "existing_object_forbids_automatic_same_id_retry": True,
            "next_inspection_guidance": "separately_governed_recovery_review_required",
        })
        base.update(_request_evidence(request_raw, installation_handle, selected))
    elif receipt_raw is not None:
        base.update({
            "overall_doctor_status": "publication_doctor_contradictory",
            "custody_shape": "orphan_receipt",
            "verification_reason_code": "receipt_without_request",
            "existing_object_forbids_automatic_same_id_retry": True,
            "next_inspection_guidance": "separately_governed_recovery_review_required",
        })
    else:
        base.update({
            "overall_doctor_status": "publication_doctor_absent",
            "custody_shape": "empty_existing_destination",
            "verification_reason_code": "fixed_objects_genuinely_absent",
            "existing_object_forbids_automatic_same_id_retry": False,
            "next_inspection_guidance": "no_publication_authority_inferred",
        })
    return _finish(base)


__all__ = [
    "NON_AUTHORITY_POSTURE", "SCHEMA",
    "ProductionChatResourceProvisioningRequestDoctorError",
    "ProductionChatResourceProvisioningRequestDoctorReport",
    "diagnose_production_chat_resource_provisioning_request_publication",
]
