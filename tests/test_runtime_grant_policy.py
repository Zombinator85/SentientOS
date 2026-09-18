from dataclasses import replace

import pytest

from sentientos.codex_task_authority_admission import TaskAuthorityDefinition, authority_definition_digest
from sentientos.runtime_admission import AdmissionError, AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from sentientos.external_model_custody import digest
from sentientos.external_model_execution_custody import ExternalModelInferenceController, NullExternalModelTransport
from tests.test_external_model_execution_custody import fixture
from sentientos.runtime_grant_policy import (OperatorGrantApproval, RuntimeGrantAuthority, RuntimeGrantError,
    RuntimeGrantLedger, RuntimeGrantPolicy, RuntimeGrantRequest, RuntimeOperatorGrant, approval_digest, grant_payload_digest)

pytestmark = pytest.mark.no_legacy_skip
CAPABILITY = "fixture.inert.runtime_review"
DEFINITION = TaskAuthorityDefinition(CAPABILITY, frozenset({"fixture"}), frozenset({"fixture_principal"}), frozenset({"read_metadata", "write_report", "bounded_external_model_network_egress"}), (), (), ("operator_runtime_approval",), "Inert policy fixture")


def setup(tmp_path):
    definitions = {CAPABILITY: DEFINITION}; grants = RuntimeGrantLedger(tmp_path / "grants.json")
    grant_authority = RuntimeGrantAuthority(definitions=definitions, ledger=grants)
    admission_ledger = AdmissionLedger(tmp_path / "admissions.json")
    issuer = RuntimeAdmissionAuthority(definitions=definitions, ledger=admission_ledger)
    policy = RuntimeGrantPolicy(definitions=definitions, ledger=grants, admission_authority=issuer)
    verifier = RuntimeAdmissionVerifier(definitions=definitions, ledger=admission_ledger)
    grant = RuntimeOperatorGrant("grant-1", "operator:test", CAPABILITY, authority_definition_digest(DEFINITION), 1, "fixture", "principal-1", "fixture_principal", ("read_metadata",), ("subject-1",), ("sha256:config",), 2, 10, 4, "operator-console:event-1", 1)
    approval = OperatorGrantApproval("operator-event-1", "operator:test", "approved", grant.grant_id, grant_payload_digest(grant), "operator-console")
    approval = replace(approval, evidence_digest=approval_digest(approval))
    return grant_authority, policy, verifier, grant, approval


def request(**changes):
    values = dict(admission_id="admission-1", capability_id=CAPABILITY, definition_version=1, subsystem_kind="fixture", principal_id="principal-1", principal_kind="fixture_principal", effects=("read_metadata",), subject_id="subject-1", request_configuration_digest="sha256:config", issued_sequence=5, valid_through_sequence=8, policy_epoch=4, provenance="grant-policy:grant-1", affirmative_preconditions=("operator_runtime_approval",))
    values.update(changes); return RuntimeGrantRequest(**values)


def test_bounded_grant_policy_issues_digest_bound_admission(tmp_path):
    authority, policy, verifier, grant, approval = setup(tmp_path)
    stored = authority.record(grant, approval)
    assert policy.evaluate(stored.grant_id, request(), current_sequence=5, current_policy_epoch=4).status == "allowed"
    admission = policy.issue(stored.grant_id, request(), current_sequence=5, current_policy_epoch=4)
    assert (admission.originating_grant_id, admission.originating_grant_digest) == (stored.grant_id, stored.binding_digest)
    verifier.verify(admission, current_sequence=5, capability_id=CAPABILITY, principal_id="principal-1", effect="read_metadata", subject_id="subject-1", request_configuration_digest="sha256:config")


def test_definition_or_grant_alone_cannot_issue_and_bad_origin_fails(tmp_path):
    authority, policy, _, grant, approval = setup(tmp_path)
    assert policy.evaluate("missing", request(), current_sequence=5, current_policy_epoch=4).reason == "missing_grant"
    bad = replace(approval, operator_identity_label="caller:model")
    with pytest.raises(RuntimeGrantError, match="invalid_operator_provenance"): authority.record(grant, bad)
    authority.record(grant, approval)
    assert not hasattr(policy, "admission_authority")


@pytest.mark.parametrize(("change", "reason"), [
    ({"principal_id": "other"}, "wrong_principal"), ({"effects": ("write_report",)}, "effect_scope_broadened"),
    ({"subject_id": "other"}, "wrong_subject"), ({"request_configuration_digest": "other"}, "request_configuration_mismatch"),
    ({"subsystem_kind": "other"}, "wrong_subsystem"), ({"capability_id": "unknown"}, "unknown_capability"),
    ({"policy_epoch": 3}, "stale_grant"),
])
def test_scope_and_governance_denials(tmp_path, change, reason):
    authority, policy, _, grant, approval = setup(tmp_path); stored = authority.record(grant, approval)
    assert policy.evaluate(stored.grant_id, request(**change), current_sequence=5, current_policy_epoch=4).reason == reason


def test_expiry_definition_drift_and_policy_unavailability_fail_closed(tmp_path):
    authority, policy, _, grant, approval = setup(tmp_path); stored = authority.record(grant, approval)
    assert policy.evaluate(stored.grant_id, request(issued_sequence=11, valid_through_sequence=11), current_sequence=11, current_policy_epoch=4).reason == "expired_grant"
    assert policy.evaluate(stored.grant_id, request(), current_sequence=5, current_policy_epoch=4, policy_available=False).reason == "policy_unavailable"
    changed = replace(DEFINITION, purpose="drift")
    drift_policy = RuntimeGrantPolicy(definitions={CAPABILITY: changed}, ledger=policy._ledger, admission_authority=policy._RuntimeGrantPolicy__admission_authority)
    assert drift_policy.evaluate(stored.grant_id, request(), current_sequence=5, current_policy_epoch=4).reason == "definition_binding_mismatch"


def test_revocation_blocks_new_issuance_but_existing_admission_retains_own_lifecycle(tmp_path):
    authority, policy, verifier, grant, approval = setup(tmp_path); stored = authority.record(grant, approval)
    admission = policy.issue(stored.grant_id, request(), current_sequence=5, current_policy_epoch=4)
    authority.revoke(stored.grant_id, sequence=6, operator_identity_label="operator:test", reason_category="policy_change", provenance="operator-console")
    restarted = RuntimeGrantPolicy(definitions={CAPABILITY: DEFINITION}, ledger=RuntimeGrantLedger(tmp_path / "grants.json"), admission_authority=policy._RuntimeGrantPolicy__admission_authority)
    assert restarted.evaluate(stored.grant_id, request(admission_id="admission-2", issued_sequence=6), current_sequence=6, current_policy_epoch=4).reason == "revoked_grant"
    verifier.verify(admission, current_sequence=6, capability_id=CAPABILITY, principal_id="principal-1", effect="read_metadata", subject_id="subject-1", request_configuration_digest="sha256:config")


def test_duplicate_and_corrupt_grant_state_fail_closed(tmp_path):
    authority, policy, _, grant, approval = setup(tmp_path); authority.record(grant, approval)
    with pytest.raises(RuntimeGrantError, match="duplicate_grant_id"): authority.record(grant, approval)
    policy._ledger.path.write_text("{}", encoding="utf-8")
    assert policy.evaluate(grant.grant_id, request(), current_sequence=5, current_policy_epoch=4).status == "invalid"


def test_grant_cannot_broaden_definition_or_admission_outlive_grant(tmp_path):
    authority, policy, _, grant, approval = setup(tmp_path)
    broad = replace(grant, effects=("read_metadata", "unknown")); broad_approval = replace(approval, grant_payload_digest=grant_payload_digest(broad), evidence_digest="")
    broad_approval = replace(broad_approval, evidence_digest=approval_digest(broad_approval))
    with pytest.raises(RuntimeGrantError, match="broadens"): authority.record(broad, broad_approval)
    stored = authority.record(grant, approval)
    assert policy.evaluate(stored.grant_id, request(valid_through_sequence=11), current_sequence=5, current_policy_epoch=4).reason == "admission_outlives_grant"


def test_external_controller_consumes_full_inert_policy_chain_with_null_transport(tmp_path):
    entry, catalog, registry, invocation, handle, _, receipts = fixture(tmp_path)
    authority, policy, _, grant, approval = setup(tmp_path / "policy")
    binding = digest({"request": invocation.binding_digest, "configuration": entry.configuration_digest})
    grant = replace(grant, principal_id=invocation.principal.principal_id, effects=(invocation.required_effect.effect_kind,), subject_ids=(f"{invocation.service_id}:{invocation.endpoint_id}",), request_configuration_digests=(binding,))
    approval = replace(approval, grant_payload_digest=grant_payload_digest(grant), evidence_digest="")
    approval = replace(approval, evidence_digest=approval_digest(approval))
    stored = authority.record(grant, approval)
    req = request(principal_id=invocation.principal.principal_id, effects=grant.effects, subject_id=grant.subject_ids[0], request_configuration_digest=binding)
    admission = policy.issue(stored.grant_id, req, current_sequence=5, current_policy_epoch=4)
    controller = ExternalModelInferenceController(catalog=catalog, registry=registry, transport=NullExternalModelTransport(), receipts=receipts, admission_verifier=RuntimeAdmissionVerifier(definitions={CAPABILITY: DEFINITION}, ledger=AdmissionLedger(tmp_path / "policy" / "admissions.json")), admission_capability_id=CAPABILITY)
    with pytest.raises(ValueError, match="transport_unavailable"):
        controller.execute(invocation, credential_handle=handle, admission=admission, current_sequence=5)
    assert receipts.load()[0].effect_occurred is False
    assert not hasattr(controller, "issue") and not hasattr(controller, "record")
