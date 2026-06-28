from __future__ import annotations

import copy
import hashlib
import json

import pytest

from sentientos.codex_workcell_storage_operator_consent_response_contract import (
    INPUT_SPECS,
    build_codex_workcell_storage_operator_consent_response_contract,
    omitted_input as contract_omitted_input,
)
from sentientos.codex_workcell_storage_operator_consent_response_verifier import (
    OPTIONAL_INPUT_IDS,
    REQUIRED_CONTRACT_INPUT_ID,
    WORKCELL_STORAGE_OPERATOR_CONSENT_RESPONSE_VERIFIER_ID,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_operator_consent_response_verifier_markdown,
    verify_codex_workcell_storage_operator_consent_response_contract,
)

pytestmark = pytest.mark.no_legacy_skip


def _contract() -> dict[str, object]:
    return build_codex_workcell_storage_operator_consent_response_contract(input_summaries={k: contract_omitted_input(k) for k in INPUT_SPECS})


def _report(contract: dict[str, object] | None = None) -> dict[str, object]:
    return verify_codex_workcell_storage_operator_consent_response_contract(
        response_contract=contract or _contract(),
        input_summaries={REQUIRED_CONTRACT_INPUT_ID: {"input_id": REQUIRED_CONTRACT_INPUT_ID, "provided": True, "path": "contract.json", "digest_algo": "sha256", "digest": "d", "byte_size": 1, "readable_json": True, "error": None}, **{k: omitted_input(k) for k in OPTIONAL_INPUT_IDS}},
    )


def _fails(mutator) -> None:
    c = copy.deepcopy(_contract())
    mutator(c)
    r = _report(c)
    assert r["verification_status"] != "storage_operator_consent_response_contract_verified"
    assert r["violation_summary"]["violation_count"] > 0


def test_valid_operator_consent_response_artifact_contract_verifies() -> None:
    r = _report()
    assert r["storage_operator_consent_response_verifier_id"] == WORKCELL_STORAGE_OPERATOR_CONSENT_RESPONSE_VERIFIER_ID
    assert r["verification_status"] == "storage_operator_consent_response_contract_verified"
    assert r["violation_summary"]["violation_count"] == 0
    assert r["response_artifact_schema_results"]["passed"] is True
    assert r["response_status_policy_results"]["passed"] is True
    assert r["explicit_allow_policy_results"]["passed"] is True
    assert r["digest_acknowledgement_policy_results"]["passed"] is True
    assert r["scope_acknowledgement_policy_results"]["passed"] is True
    assert r["expiration_policy_results"]["passed"] is True
    assert r["revocation_policy_results"]["passed"] is True
    assert r["denial_and_ambiguity_policy_results"]["passed"] is True
    assert r["response_authority_boundary_results"]["passed"] is True
    assert r["response_activation_gap_results"]["passed"] is True


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("metadata_only", None), ("response_contract_only", False), ("response_artifact_schema_only", False),
        ("response_artifact_not_created", False), ("operator_response_present", True), ("consent_not_collected", False),
        ("consent_not_implied", False), ("operator_consent_present", True), ("runtime_binding_not_performed", False),
        ("active_storage_allowed_now", True), ("writes_performed", True), ("archives_performed", True),
        ("memory_mutation_performed", True),
    ],
)
def test_top_level_boundary_mutations_fail(key: str, value: object) -> None:
    def mutate(c: dict[str, object]) -> None:
        if value is None:
            c.pop(key)
        else:
            c[key] = value
    _fails(mutate)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda c: c.pop("response_artifact_schema"),
        lambda c: c["response_artifact_schema"].pop(),
        lambda c: c["response_artifact_schema"][0].__setitem__("currently_satisfied", True),
        lambda c: c["response_artifact_schema"][0].__setitem__("future_only", False),
        lambda c: c["response_artifact_schema"][0].__setitem__("active", True),
        lambda c: c["response_status_policy"].__setitem__("current_response_status", "approved_for_scoped_storage"),
        lambda c: c["response_status_policy"].__setitem__("approved_status_not_present_here", False),
        lambda c: c["response_status_policy"].__setitem__("denied_status_blocks_storage", False),
        lambda c: c["explicit_allow_policy"].__setitem__("explicit_allow_ledger_write_present", True),
        lambda c: c["explicit_allow_policy"].__setitem__("allow_flags_not_collected", False),
        lambda c: c["digest_acknowledgement_policy"].__setitem__("required_acknowledgement_ids", []),
        lambda c: c["digest_acknowledgement_policy"].__setitem__("acknowledgements_not_collected", False),
        lambda c: c["digest_acknowledgement_policy"].__setitem__("supplied_acknowledgement_ids", ["x"]),
        lambda c: c["digest_acknowledgement_policy"].__setitem__("digest_algorithm", "sha512"),
        lambda c: c["scope_acknowledgement_policy"].__setitem__("allowed_mounts", ["/ledger"]),
        lambda c: c["scope_acknowledgement_policy"].__setitem__("forbidden_mounts", ["/vow"]),
        lambda c: c["scope_acknowledgement_policy"].__setitem__("mount_scope_acknowledgement_present", True),
        lambda c: c["expiration_policy"].__setitem__("expiration_timestamp_present", True),
        lambda c: c["expiration_policy"].__setitem__("lifetime_not_started", False),
        lambda c: c["revocation_policy"].__setitem__("revocation_terms_acknowledged", True),
        lambda c: c["revocation_policy"].__setitem__("revocation_not_performed", False),
        lambda c: c["denial_and_ambiguity_policy"].__setitem__("default_without_response", "allow"),
        lambda c: c["denial_and_ambiguity_policy"].__setitem__("remote_or_daemon_response_not_accepted", False),
        lambda c: c["response_authority_boundary"].__setitem__("supplied_evidence_does_not_imply_consent", False),
        lambda c: c["response_activation_gap_summary"].__setitem__("blocking_gap_ids", []),
        lambda c: c["non_authority_posture"].__setitem__(next(iter(c["non_authority_posture"])), False),
        lambda c: c["future_activation_requirements"][0].__setitem__("active", True),
    ],
)
def test_required_policy_and_boundary_mutations_fail(mutator) -> None:
    _fails(mutator)


def test_input_summaries_optional_hygiene_markdown_and_no_authority(tmp_path) -> None:
    payload = json.dumps(_contract(), sort_keys=True).encode()
    path = tmp_path / "contract.json"
    path.write_bytes(payload)
    summary, contract = read_json_input(str(path), REQUIRED_CONTRACT_INPUT_ID)
    r = verify_codex_workcell_storage_operator_consent_response_contract(response_contract=contract, input_summaries={REQUIRED_CONTRACT_INPUT_ID: summary, **{k: omitted_input(k) for k in OPTIONAL_INPUT_IDS}})
    assert r["input_summaries"][REQUIRED_CONTRACT_INPUT_ID]["digest"] == hashlib.sha256(payload).hexdigest()
    assert r["input_summaries"][REQUIRED_CONTRACT_INPUT_ID]["byte_size"] == len(payload)
    assert all(x["provided"] is False for x in r["optional_context_summary"])
    assert r["reviewer_hygiene_summary"]["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    assert r["reviewer_hygiene_summary"]["bad_repo_url"] == "https://github.com/" + "OpenAI/" + "SentientOS.git"
    for key in ["response_artifact_not_created", "consent_not_collected", "consent_not_implied", "runtime_binding_not_performed", "not_ledger_writer", "not_glow_archiver", "not_daemon_action"]:
        assert r[key] is True
    for key in ["operator_response_present", "operator_consent_present", "active_storage_allowed_now", "writes_performed", "archives_performed", "memory_mutation_performed"]:
        assert r[key] is False
    md1 = render_codex_workcell_storage_operator_consent_response_verifier_markdown({**r, "verification_status": "a|b\nc"})
    md2 = render_codex_workcell_storage_operator_consent_response_verifier_markdown({**r, "verification_status": "a|b\nc"})
    assert md1 == md2
    assert "a\\|b<br>c" in md1
