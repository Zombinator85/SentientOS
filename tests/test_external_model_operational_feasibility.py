from dataclasses import replace
import inspect

import pytest

from sentientos.codex_task_authority_admission import EXTERNAL_MODEL_INFERENCE_DEFINITION, authority_definition_digest
from sentientos.external_model_custody import digest
from sentientos.external_model_execution_custody import NullExternalModelTransport
from sentientos.external_model_material import UnavailableRequestMaterialSource
from sentientos.external_model_operational_feasibility import (
    CAPABILITY_ID, PRINCIPAL_KIND, REQUIRED_EFFECT, LocalReadiness,
    OperationalFeasibilityDecision, assess_external_model_operational_feasibility,
    observe_runtime_governor_posture, seal_local_readiness,
)
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority
from sentientos.runtime_governor import RuntimePosture
from sentientos.runtime_grant_policy import (
    OperatorGrantApproval, RuntimeGrantAuthority, RuntimeGrantError, RuntimeGrantLedger,
    RuntimeGrantPolicy, RuntimeGrantRequest, RuntimeOperatorGrant, approval_digest,
    grant_payload_digest,
)
from tests.test_external_model_execution_custody import fixture

pytestmark = pytest.mark.no_legacy_skip


def posture(block=False):
    return RuntimePosture("restricted" if block else "nominal", "test", "test", "none", block, [], {}, [])


def inputs(tmp_path, *, block=False):
    entry, catalog, _, request, *_ = fixture(tmp_path)
    configuration = digest({"request": request.binding_digest, "configuration": entry.configuration_digest})
    governor = observe_runtime_governor_posture(
        posture(block), principal_id=request.principal.principal_id,
        subject_id=f"{request.service_id}:{request.endpoint_id}",
        request_configuration_digest=configuration, sequence=5, policy_epoch=4,
    )
    transport = seal_local_readiness(LocalReadiness("transport", "synthetic-test-transport:v1", True, True, True, True))
    material = seal_local_readiness(LocalReadiness("request_material", "synthetic-test-material:v1", True, bounded_request_material=True))
    credential = seal_local_readiness(LocalReadiness("credential", "synthetic-test-credential:v1", True, structurally_configured=True))
    return entry, catalog, request, governor, transport, material, credential


def assess(tmp_path, **changes):
    _, catalog, request, governor, transport, material, credential = inputs(tmp_path)
    values = dict(request=request, catalog=catalog, transport_readiness=transport,
                  request_material_readiness=material, credential_readiness=credential,
                  governor_evidence=governor, current_sequence=5, current_policy_epoch=4)
    values.update(changes)
    return assess_external_model_operational_feasibility(**values)


def test_current_production_defaults_fail_closed_without_reading_material_or_network(tmp_path, monkeypatch):
    _, _, _, governor, _, _, credential = inputs(tmp_path)
    entry, catalog, _, request, *_ = fixture(tmp_path / "production")
    configuration = digest({"request": request.binding_digest, "configuration": entry.configuration_digest})
    governor = observe_runtime_governor_posture(posture(), principal_id=request.principal.principal_id,
        subject_id=f"{request.service_id}:{request.endpoint_id}", request_configuration_digest=configuration,
        sequence=5, policy_epoch=4)
    monkeypatch.setattr(UnavailableRequestMaterialSource, "read_for_invocation", lambda *_: pytest.fail("material read"))
    decision = assess_external_model_operational_feasibility(
        request=request, catalog=catalog,
        transport_readiness=NullExternalModelTransport().operational_readiness(),
        request_material_readiness=UnavailableRequestMaterialSource().operational_readiness(),
        credential_readiness=credential, governor_evidence=governor,
        current_sequence=5, current_policy_epoch=4)
    assert not decision.operationally_feasible
    assert {"transport_unavailable", "request_material_unavailable"}.issubset(decision.reason_codes)


def test_exact_positive_synthetic_feasibility_is_deterministic_and_non_authoritative(tmp_path):
    first = assess(tmp_path); second = assess(tmp_path)
    assert first == second and first.operationally_feasible
    assert not any(hasattr(first, name) for name in ("authorized", "grant_issued", "admission_issued"))
    assert authority_definition_digest(EXTERNAL_MODEL_INFERENCE_DEFINITION) == "539ff509bbeabe50cd2be17adf9ebbe58958e894b3cb6728a5c809a605db7b9c"


@pytest.mark.parametrize("change,reason", [
    ({"transport_readiness": None}, "missing_or_malformed_transport_readiness"),
    ({"request_material_readiness": None}, "missing_or_malformed_request_material_readiness"),
    ({"governor_evidence": None}, "missing_governor_evidence"),
    ({"capability_id": "other"}, "wrong_capability"),
    ({"principal_kind": "other"}, "wrong_principal"),
    ({"required_effect": "other"}, "wrong_effect"),
    ({"current_sequence": 6}, "stale_or_mismatched_governor_evidence"),
    ({"current_policy_epoch": 5}, "stale_or_mismatched_governor_evidence"),
])
def test_missing_wrong_and_stale_inputs_fail_closed(tmp_path, change, reason):
    assert reason in assess(tmp_path, **change).reason_codes


def test_malformed_tampered_readiness_and_decision_fail_closed(tmp_path):
    _, _, _, _, transport, _, _ = inputs(tmp_path)
    assert "missing_or_malformed_transport_readiness" in assess(
        tmp_path, transport_readiness=replace(transport, implementation_id="tampered")).reason_codes
    decision = assess(tmp_path)
    assert replace(decision, service_id="other").binding_digest == decision.binding_digest


def test_configuration_subject_endpoint_and_governor_block_fail_closed(tmp_path):
    _, catalog, request, *_ = inputs(tmp_path)
    wrong = replace(request, endpoint_id="other")
    assert "configuration_unavailable_or_mismatched" in assess(tmp_path, request=wrong).reason_codes
    _, _, _, blocked, *_ = inputs(tmp_path, block=True)
    assert "runtime_governor_block" in assess(tmp_path, governor_evidence=blocked).reason_codes


def test_required_credential_path_must_be_structurally_ready(tmp_path):
    decision = assess(tmp_path, credential_readiness=None)
    assert "credential_path_unavailable" in decision.reason_codes


def policy_parts(tmp_path):
    entry, catalog, request, governor, transport, material, credential = inputs(tmp_path)
    definitions = {CAPABILITY_ID: EXTERNAL_MODEL_INFERENCE_DEFINITION}
    grant_ledger = RuntimeGrantLedger(tmp_path / "grants.json")
    grant_authority = RuntimeGrantAuthority(definitions=definitions, ledger=grant_ledger)
    admission_authority = RuntimeAdmissionAuthority(definitions=definitions, ledger=AdmissionLedger(tmp_path / "admissions.json"))
    policy = RuntimeGrantPolicy(definitions=definitions, ledger=grant_ledger, admission_authority=admission_authority)
    configuration = digest({"request": request.binding_digest, "configuration": entry.configuration_digest})
    grant = RuntimeOperatorGrant("grant", "operator:test", CAPABILITY_ID,
        authority_definition_digest(EXTERNAL_MODEL_INFERENCE_DEFINITION), 1, CAPABILITY_ID,
        request.principal.principal_id, PRINCIPAL_KIND, (REQUIRED_EFFECT,),
        (f"{request.service_id}:{request.endpoint_id}",), (configuration,), 2, 9, 4, "test", 1)
    approval = OperatorGrantApproval("approval", "operator:test", "approved", "grant", grant_payload_digest(grant), "test")
    approval = replace(approval, evidence_digest=approval_digest(approval))
    stored = grant_authority.record(grant, approval)
    req = RuntimeGrantRequest("admission", CAPABILITY_ID, 1, CAPABILITY_ID,
        request.principal.principal_id, PRINCIPAL_KIND, (REQUIRED_EFFECT,),
        f"{request.service_id}:{request.endpoint_id}", configuration, 5, 7, 4, "test",
        EXTERNAL_MODEL_INFERENCE_DEFINITION.approval_requirements)
    feasibility = assess_external_model_operational_feasibility(request=request, catalog=catalog,
        transport_readiness=transport, request_material_readiness=material,
        credential_readiness=credential, governor_evidence=governor,
        current_sequence=5, current_policy_epoch=4)
    return grant_authority, policy, stored, req, feasibility


def test_grant_policy_refuses_missing_negative_stale_and_tampered_feasibility(tmp_path):
    _, policy, stored, req, feasible = policy_parts(tmp_path)
    for evidence in (None, replace(feasible, status="infeasible"),
                     replace(feasible, sequence=4), replace(feasible, endpoint_id="tampered")):
        assert policy.evaluate(stored.grant_id, req, current_sequence=5, current_policy_epoch=4,
                               operational_feasibility=evidence).reason == "operational_feasibility_required"


def test_exact_grant_policy_feasibility_path_issues_admission_but_feasibility_cannot(tmp_path):
    _, policy, stored, req, feasible = policy_parts(tmp_path)
    admission = policy.issue(stored.grant_id, req, current_sequence=5, current_policy_epoch=4,
                             operational_feasibility=feasible)
    assert admission.originating_grant_id == stored.grant_id
    assert not hasattr(feasible, "issue") and not hasattr(feasible, "grant")


def test_revoked_expired_and_policy_unavailable_still_precede_positive_feasibility(tmp_path):
    authority, policy, stored, req, feasible = policy_parts(tmp_path)
    assert policy.evaluate(stored.grant_id, req, current_sequence=5, current_policy_epoch=4,
        policy_available=False, operational_feasibility=feasible).reason == "policy_unavailable"
    authority.revoke(stored.grant_id, sequence=5, operator_identity_label="operator:test", reason_category="test", provenance="test")
    assert policy.evaluate(stored.grant_id, req, current_sequence=5, current_policy_epoch=4,
        operational_feasibility=feasible).reason == "revoked_grant"


def test_no_live_effect_surface():
    source = inspect.getsource(__import__("sentientos.external_model_operational_feasibility", fromlist=["*"]))
    for forbidden in ("import socket", "import requests", "import httpx", "urlopen", "read_exact(", "read_for_invocation("):
        assert forbidden not in source
