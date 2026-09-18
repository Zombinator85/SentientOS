from dataclasses import replace

import pytest

from sentientos.codex_task_authority_admission import TaskAuthorityDefinition
from sentientos.external_model_custody import digest
from sentientos.external_model_execution_custody import ExternalModelInferenceController, NullExternalModelTransport
from sentientos.runtime_admission import AdmissionError, AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from tests.test_external_model_execution_custody import fixture

pytestmark = pytest.mark.no_legacy_skip
CAPABILITY = "fixture.inert.external_model_review"
DEFINITION = TaskAuthorityDefinition(CAPABILITY, frozenset({"fixture"}), frozenset({"fixture_controller"}), frozenset({"bounded_external_model_network_egress"}), ("wildcard",), approval_requirements=("operator_fixture_approval",), purpose="Inert test definition")


def issued(tmp_path, **changes):
    ledger = AdmissionLedger(tmp_path / "admissions.json")
    authority = RuntimeAdmissionAuthority(definitions={CAPABILITY: DEFINITION}, ledger=ledger)
    values = dict(admission_id="a-1", capability_id=CAPABILITY, definition_version=1, subsystem_kind="fixture", principal_id="controller-a", principal_kind="fixture_controller", effects=("bounded_external_model_network_egress",), subject_id="service-a:endpoint-a", request_configuration_digest="sha256:binding", provenance="operator-reviewed-fixture", issued_sequence=2, valid_through_sequence=5, affirmative_preconditions=("operator_fixture_approval",))
    values.update(changes)
    return authority, RuntimeAdmissionVerifier(definitions={CAPABILITY: DEFINITION}, ledger=ledger), authority.issue(**values)


def verify(verifier, admission, **changes):
    values = dict(current_sequence=3, capability_id=CAPABILITY, principal_id="controller-a", effect="bounded_external_model_network_egress", subject_id="service-a:endpoint-a", request_configuration_digest="sha256:binding")
    values.update(changes); verifier.verify(admission, **values)


def test_exact_registered_admission_verifies_and_unknown_cannot_issue(tmp_path):
    authority, verifier, admission = issued(tmp_path); verify(verifier, admission)
    with pytest.raises(AdmissionError, match="unregistered"): issued(tmp_path / "other", capability_id="unknown")
    assert not hasattr(verifier, "issue") and not hasattr(ExternalModelInferenceController, "issue_admission")


@pytest.mark.parametrize("change", [
    {"principal_id": "other"}, {"effect": "other"}, {"subject_id": "other"},
    {"request_configuration_digest": "other"}, {"capability_id": "other"},
])
def test_exact_bindings_fail_closed(tmp_path, change):
    _, verifier, admission = issued(tmp_path)
    with pytest.raises(AdmissionError): verify(verifier, admission, **change)


def test_expiry_definition_change_and_tampering_fail(tmp_path):
    _, verifier, admission = issued(tmp_path)
    with pytest.raises(AdmissionError, match="expired"): verify(verifier, admission, current_sequence=6)
    with pytest.raises(AdmissionError, match="malformed"): verify(verifier, replace(admission, principal_id="model-output"))
    changed = replace(DEFINITION, purpose="changed")
    with pytest.raises(AdmissionError, match="definition"): RuntimeAdmissionVerifier(definitions={CAPABILITY: changed}, ledger=verifier._ledger).verify(admission, current_sequence=3, capability_id=CAPABILITY, principal_id="controller-a", effect=admission.effects[0], subject_id=admission.subject_id, request_configuration_digest=admission.request_configuration_digest)


def test_revocation_and_supersession_survive_restart(tmp_path):
    authority, verifier, first = issued(tmp_path)
    second = authority.issue(admission_id="a-2", capability_id=CAPABILITY, definition_version=1, subsystem_kind="fixture", principal_id="controller-a", principal_kind="fixture_controller", effects=first.effects, subject_id=first.subject_id, request_configuration_digest=first.request_configuration_digest, provenance="operator-reviewed-fixture", issued_sequence=4, valid_through_sequence=8, affirmative_preconditions=("operator_fixture_approval",), predecessor_admission_id=first.admission_id)
    with pytest.raises(AdmissionError, match="superseded"): verify(verifier, first, current_sequence=4)
    authority.revoke(second.admission_id, sequence=5, reason_category="operator_policy_change", provenance="operator-revocation-fixture")
    restarted = RuntimeAdmissionVerifier(definitions={CAPABILITY: DEFINITION}, ledger=AdmissionLedger(tmp_path / "admissions.json"))
    with pytest.raises(AdmissionError, match="revoked"): verify(restarted, second, current_sequence=5)


def test_corruption_fails_closed(tmp_path):
    _, verifier, admission = issued(tmp_path); verifier._ledger.path.write_text("{}", encoding="utf-8")
    with pytest.raises(AdmissionError, match="corrupt"): verify(verifier, admission)


def test_external_consumer_uses_generic_verifier_but_cannot_mint(tmp_path):
    entry, catalog, registry, request, handle, _, receipts = fixture(tmp_path)
    binding = digest({"request": request.binding_digest, "configuration": entry.configuration_digest})
    authority, verifier, admission = issued(tmp_path / "authority", request_configuration_digest=binding)
    controller = ExternalModelInferenceController(catalog=catalog, registry=registry, transport=NullExternalModelTransport(), receipts=receipts, admission_verifier=verifier, admission_capability_id=CAPABILITY)
    with pytest.raises(ValueError, match="transport_unavailable"): controller.execute(request, credential_handle=handle, admission=admission, current_sequence=3)
    assert receipts.load()[0].admission_evidence_ref == admission.admission_id
    authority.revoke(admission.admission_id, sequence=4, reason_category="operator_policy_change", provenance="fixture")
    with pytest.raises(ValueError, match="revoked"): controller.execute(request, credential_handle=handle, admission=admission, current_sequence=4)
    assert isinstance(controller.transport, NullExternalModelTransport)

