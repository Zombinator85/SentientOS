"""Offline, non-authoritative operational feasibility for external-model calls.

The evidence in this module can only close an admission path.  It neither grants
authority nor proves network reachability, authentication, execution, or trust.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Protocol

from sentientos.codex_task_authority_admission import (
    EXTERNAL_MODEL_INFERENCE_DEFINITION, authority_definition_digest,
)
from sentientos.external_model_custody import InvocationRequestEnvelope, digest
from sentientos.external_model_execution_custody import ExternalModelServiceCatalog
from sentientos.runtime_governor import RuntimePosture

CAPABILITY_ID = "external_model_inference"
PRINCIPAL_KIND = "deterministic_external_model_inference_controller"
REQUIRED_EFFECT = "bounded_external_model_network_egress"
DECISION_SCHEMA = "sentientos.external_model_operational_feasibility:v1"
GOVERNOR_SCHEMA = "sentientos.external_model_governor_posture:v1"


@dataclass(frozen=True)
class LocalReadiness:
    """A bounded local declaration; never authority or remote-health proof."""
    component_kind: str
    implementation_id: str
    implementation_available: bool
    exact_endpoint_enforcement: bool = False
    bounded_request_material: bool = False
    response_material_custody: bool = False
    structurally_configured: bool = False
    evidence_digest: str = ""


def seal_local_readiness(value: LocalReadiness) -> LocalReadiness:
    payload = asdict(value); payload.pop("evidence_digest")
    return replace(value, evidence_digest=digest(payload))


class LocalReadinessProvider(Protocol):
    def operational_readiness(self) -> LocalReadiness: ...


@dataclass(frozen=True)
class GovernorPostureEvidence:
    capability_id: str
    principal_id: str
    subject_id: str
    request_configuration_digest: str
    sequence: int
    policy_epoch: int
    effective_posture: str
    enforce_block: bool
    posture_digest: str
    evidence_digest: str = ""


def observe_runtime_governor_posture(
    posture: RuntimePosture, *, principal_id: str, subject_id: str,
    request_configuration_digest: str, sequence: int, policy_epoch: int,
) -> GovernorPostureEvidence:
    """Bind a concrete governor posture without asking it to perform an effect."""
    posture_digest = digest({"schema": GOVERNOR_SCHEMA, "posture": posture.to_dict()})
    evidence = GovernorPostureEvidence(
        CAPABILITY_ID, principal_id, subject_id, request_configuration_digest,
        sequence, policy_epoch, posture.effective_posture, posture.enforce_block,
        posture_digest,
    )
    payload = asdict(evidence); payload.pop("evidence_digest")
    return replace(evidence, evidence_digest=digest(payload))


@dataclass(frozen=True)
class OperationalFeasibilityDecision:
    schema: str
    status: str
    reason_codes: tuple[str, ...]
    capability_id: str
    authority_definition_digest: str
    definition_version: int
    principal_id: str
    principal_kind: str
    required_effect: str
    service_id: str
    endpoint_id: str
    model_id: str
    subject_id: str
    request_binding_digest: str
    configured_service_digest: str
    request_configuration_digest: str
    sequence: int
    policy_epoch: int
    governor_evidence_digest: str
    transport_readiness_digest: str
    request_material_readiness_digest: str
    credential_readiness_digest: str | None
    binding_digest: str = ""

    @property
    def operationally_feasible(self) -> bool:
        return self.status == "feasible"


def _decision_digest(value: OperationalFeasibilityDecision) -> str:
    payload = asdict(value); payload.pop("binding_digest")
    return digest(payload)


def _valid_readiness(value: Any, kind: str) -> bool:
    if not isinstance(value, LocalReadiness) or value.component_kind != kind:
        return False
    if not value.implementation_id or value.evidence_digest == "":
        return False
    payload = asdict(value); claimed = payload.pop("evidence_digest")
    return isinstance(claimed, str) and claimed == digest(payload)


def assess_external_model_operational_feasibility(
    *, request: InvocationRequestEnvelope, catalog: ExternalModelServiceCatalog,
    transport_readiness: LocalReadiness | None,
    request_material_readiness: LocalReadiness | None,
    credential_readiness: LocalReadiness | None,
    governor_evidence: GovernorPostureEvidence | None,
    current_sequence: int, current_policy_epoch: int,
    capability_id: str = CAPABILITY_ID, definition_version: int = 1,
    principal_kind: str = PRINCIPAL_KIND, required_effect: str = REQUIRED_EFFECT,
) -> OperationalFeasibilityDecision:
    reasons: list[str] = []
    entry = None
    try:
        entry = catalog.resolve(request)
    except (TypeError, ValueError):
        reasons.append("configuration_unavailable_or_mismatched")
    service_digest = entry.configuration_digest if entry is not None else "unavailable"
    subject = f"{request.service_id}:{request.endpoint_id}"
    request_configuration = digest({"request": request.binding_digest, "configuration": service_digest})
    if capability_id != CAPABILITY_ID: reasons.append("wrong_capability")
    if principal_kind != PRINCIPAL_KIND or request.principal.principal_id == "": reasons.append("wrong_principal")
    if required_effect != REQUIRED_EFFECT or request.required_effect.effect_kind != required_effect: reasons.append("wrong_effect")
    if request.required_effect.service_id != request.service_id or request.required_effect.endpoint_id != request.endpoint_id: reasons.append("wrong_effect_binding")
    if current_sequence < 1 or current_policy_epoch < 1: reasons.append("invalid_freshness_boundary")
    transport_ok = _valid_readiness(transport_readiness, "transport")
    if not transport_ok or not isinstance(transport_readiness, LocalReadiness): reasons.append("missing_or_malformed_transport_readiness")
    elif not (transport_readiness.implementation_available and transport_readiness.exact_endpoint_enforcement and transport_readiness.bounded_request_material and transport_readiness.response_material_custody): reasons.append("transport_unavailable")
    material_ok = _valid_readiness(request_material_readiness, "request_material")
    if not material_ok or not isinstance(request_material_readiness, LocalReadiness): reasons.append("missing_or_malformed_request_material_readiness")
    elif not (request_material_readiness.implementation_available and request_material_readiness.bounded_request_material): reasons.append("request_material_unavailable")
    credential_digest = credential_readiness.evidence_digest if isinstance(credential_readiness, LocalReadiness) else None
    if entry is not None and entry.credential_ref is not None:
        if not isinstance(credential_readiness, LocalReadiness) or not _valid_readiness(credential_readiness, "credential") or not credential_readiness.implementation_available or not credential_readiness.structurally_configured:
            reasons.append("credential_path_unavailable")
    governor_digest = governor_evidence.evidence_digest if isinstance(governor_evidence, GovernorPostureEvidence) else "unavailable"
    if not isinstance(governor_evidence, GovernorPostureEvidence):
        reasons.append("missing_governor_evidence")
    else:
        gp = asdict(governor_evidence); claimed = gp.pop("evidence_digest")
        expected = (CAPABILITY_ID, request.principal.principal_id, subject, request_configuration, current_sequence, current_policy_epoch)
        actual = (governor_evidence.capability_id, governor_evidence.principal_id, governor_evidence.subject_id, governor_evidence.request_configuration_digest, governor_evidence.sequence, governor_evidence.policy_epoch)
        if claimed != digest(gp) or not governor_evidence.posture_digest.startswith("sha256:"): reasons.append("malformed_governor_evidence")
        if actual != expected: reasons.append("stale_or_mismatched_governor_evidence")
        if governor_evidence.enforce_block: reasons.append("runtime_governor_block")
    decision = OperationalFeasibilityDecision(
        DECISION_SCHEMA, "feasible" if not reasons else "infeasible", tuple(sorted(set(reasons))),
        capability_id, authority_definition_digest(EXTERNAL_MODEL_INFERENCE_DEFINITION), definition_version,
        request.principal.principal_id, principal_kind, required_effect, request.service_id,
        request.endpoint_id, request.model_id, subject, request.binding_digest, service_digest,
        request_configuration, current_sequence, current_policy_epoch, governor_digest,
        transport_readiness.evidence_digest if isinstance(transport_readiness, LocalReadiness) else "unavailable",
        request_material_readiness.evidence_digest if isinstance(request_material_readiness, LocalReadiness) else "unavailable",
        credential_digest,
    )
    return replace(decision, binding_digest=_decision_digest(decision))


def verify_operational_feasibility(
    decision: object, *, capability_id: str, principal_id: str, principal_kind: str,
    effects: tuple[str, ...], subject_id: str, request_configuration_digest: str,
    current_sequence: int, current_policy_epoch: int, definition_version: int,
) -> bool:
    if not isinstance(decision, OperationalFeasibilityDecision): return False
    if decision.binding_digest != _decision_digest(decision) or decision.status != "feasible" or decision.reason_codes: return False
    return (
        decision.schema == DECISION_SCHEMA
        and decision.capability_id == capability_id == CAPABILITY_ID
        and decision.principal_id == principal_id and decision.principal_kind == principal_kind == PRINCIPAL_KIND
        and decision.required_effect in effects and effects == (REQUIRED_EFFECT,)
        and decision.subject_id == subject_id
        and decision.request_configuration_digest == request_configuration_digest
        and decision.sequence == current_sequence and decision.policy_epoch == current_policy_epoch
        and decision.definition_version == definition_version
        and decision.authority_definition_digest == authority_definition_digest(EXTERNAL_MODEL_INFERENCE_DEFINITION)
    )
