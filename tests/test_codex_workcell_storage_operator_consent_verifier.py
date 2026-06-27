from __future__ import annotations

import copy
import hashlib
import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_operator_consent_contract import INPUT_SPECS, build_codex_workcell_storage_operator_consent_contract, omitted_input as contract_omitted
from sentientos.codex_workcell_storage_operator_consent_verifier import OPTIONAL_INPUT_IDS, omitted_input, read_json_input, render_codex_workcell_storage_operator_consent_verifier_markdown, verify_codex_workcell_storage_operator_consent_contract


def _contract() -> dict[str, object]:
    return build_codex_workcell_storage_operator_consent_contract(input_summaries={i: contract_omitted(i) for i in INPUT_SPECS})


def _verify(contract: dict[str, object]) -> dict[str, object]:
    return verify_codex_workcell_storage_operator_consent_contract(
        storage_operator_consent_contract=contract,
        storage_operator_consent_contract_summary={"digest": "abc", "byte_size": 3},
        optional_reports={},
        optional_summaries={i: omitted_input(i) for i in OPTIONAL_INPUT_IDS},
    )


def _failed(report: dict[str, object]) -> bool:
    return report["verification_status"] in {"storage_operator_consent_contract_failed", "storage_operator_consent_contract_incomplete"}


def test_valid_operator_consent_request_contract_verifies():
    report = _verify(_contract())
    assert report["verification_status"] == "storage_operator_consent_contract_verified"
    assert report["operator_consent_present"] is False
    assert report["consent_not_collected"] is True
    assert report["runtime_binding_not_performed"] is True
    assert report["writes_performed"] is False
    assert report["archives_performed"] is False
    assert report["memory_mutation_performed"] is False
    assert report["violation_summary"]["violation_count"] == 0


@pytest.mark.parametrize("key,bad", [
    ("metadata_only", None), ("consent_contract_only", False), ("consent_request_shape_only", False),
    ("consent_not_collected", False), ("operator_consent_present", True), ("runtime_binding_not_performed", False),
    ("active_storage_allowed_now", True), ("writes_performed", True), ("archives_performed", True), ("memory_mutation_performed", True),
])
def test_top_level_boundary_flags_fail(key: str, bad: object):
    c = _contract()
    if bad is None:
        c.pop(key)
    else:
        c[key] = bad
    assert _failed(_verify(c))


@pytest.mark.parametrize("mutator", [
    lambda c: c.pop("consent_request_schema"),
    lambda c: c["consent_request_schema"].pop(),
    lambda c: c["consent_request_schema"][0].__setitem__("currently_satisfied", True),
    lambda c: c["consent_request_schema"][0].__setitem__("future_only", False),
    lambda c: c["consent_request_schema"][0].__setitem__("active", True),
    lambda c: c["consent_request_schema"][0].pop("forbidden_inference"),
])
def test_schema_failures(mutator):
    c = _contract(); mutator(c)
    report = _verify(c)
    assert _failed(report)
    assert report["consent_schema_results"]["passed"] is False


@pytest.mark.parametrize("mutator,result_key", [
    (lambda c: c["required_consent_evidence"]["required_evidence_ids"].pop(), "consent_evidence_results"),
    (lambda c: c["required_consent_evidence"].__setitem__("evidence_collection_not_performed", False), "consent_evidence_results"),
    (lambda c: c["consent_scope_policy"].__setitem__("allowed_mounts", ["/ledger"]), "consent_scope_results"),
    (lambda c: c["consent_scope_policy"]["forbidden_mounts"].remove("/vow"), "consent_scope_results"),
    (lambda c: c["consent_scope_policy"]["forbidden_mounts"].remove("/pulse"), "consent_scope_results"),
    (lambda c: c["consent_scope_policy"]["forbidden_mounts"].remove("/daemon"), "consent_scope_results"),
    (lambda c: c["consent_scope_policy"]["forbidden_mounts"].remove("host_absolute_paths"), "consent_scope_results"),
    (lambda c: c["consent_scope_policy"]["forbidden_mounts"].remove("network_paths"), "consent_scope_results"),
    (lambda c: c["consent_scope_policy"]["forbidden_mounts"].remove("temp_paths_as_canonical"), "consent_scope_results"),
    (lambda c: c["consent_scope_policy"]["forbidden_mounts"].remove("hidden_backdoor_paths"), "consent_scope_results"),
    (lambda c: c["consent_digest_binding_policy"].__setitem__("digest_binding_not_performed", False), "consent_digest_binding_results"),
    (lambda c: c["consent_digest_binding_policy"].__setitem__("digest_algorithm", "sha512"), "consent_digest_binding_results"),
    (lambda c: c["consent_lifetime_policy"].__setitem__("expiration_required", False), "consent_lifetime_results"),
    (lambda c: c["consent_lifetime_policy"].__setitem__("revocation_required", False), "consent_lifetime_results"),
    (lambda c: c["consent_lifetime_policy"].__setitem__("renewal_required_for_new_vow_digest", False), "consent_lifetime_results"),
    (lambda c: c["consent_revocation_policy"].__setitem__("revocation_must_not_delete_existing_receipts", False), "consent_revocation_results"),
    (lambda c: c["consent_denial_policy"].__setitem__("default_without_consent", "allow"), "consent_denial_results"),
    (lambda c: c["consent_denial_policy"].__setitem__("remote_or_daemon_consent_not_accepted", False), "consent_denial_results"),
    (lambda c: c["consent_authority_boundary"].__setitem__("consent_contract_is_not_consent", False), "consent_authority_boundary_results"),
    (lambda c: c["consent_authority_boundary"].__setitem__("consent_schema_is_not_operator_approval", False), "consent_authority_boundary_results"),
    (lambda c: c["consent_authority_boundary"].__setitem__("supplied_reports_do_not_imply_consent", False), "consent_authority_boundary_results"),
    (lambda c: c["consent_authority_boundary"].__setitem__("finalizer_ready_to_commit_does_not_imply_consent", False), "consent_authority_boundary_results"),
    (lambda c: c["consent_authority_boundary"].__setitem__("pr_metadata_guard_ready_does_not_imply_consent", False), "consent_authority_boundary_results"),
    (lambda c: c["consent_authority_boundary"].__setitem__("daemon_recommendation_does_not_imply_consent", False), "consent_authority_boundary_results"),
    (lambda c: c["consent_authority_boundary"].__setitem__("federation_state_does_not_imply_consent", False), "consent_authority_boundary_results"),
    (lambda c: c["consent_activation_gap_summary"]["blocking_gap_ids"].pop(), "consent_activation_gap_results"),
])
def test_policy_group_failures(mutator, result_key: str):
    c = _contract(); mutator(c)
    report = _verify(c)
    assert _failed(report)
    assert report[result_key]["passed"] is False


def test_non_authority_future_omitted_context_hygiene_and_mounts():
    report = _verify(_contract())
    assert all(report["non_authority_posture"].values())
    assert all(r["status"] == "future_only" and r["met"] is False and r["active"] is False for r in report["future_activation_requirements"])
    assert all(s["provided"] is False for s in report["optional_context_summary"])
    hygiene = report["reviewer_hygiene_summary"]
    assert hygiene["bad_repo_url"] == "https://github.com/" + "OpenAI/" + "SentientOS.git"
    assert hygiene["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    assert "no ledger write" in report["sentientos_mount_alignment"]["/ledger"]
    for key in ("storage_operator_consent_verifier_does_not_decide_readiness", "storage_operator_consent_verifier_does_not_collect_consent", "storage_operator_consent_verifier_does_not_bind_runtime_authority", "storage_operator_consent_verifier_does_not_write_ledger", "storage_operator_consent_verifier_does_not_archive_glow", "storage_operator_consent_verifier_does_not_modify_memory", "storage_operator_consent_verifier_does_not_trigger_daemon", "storage_operator_consent_verifier_does_not_create_tasks", "storage_operator_consent_verifier_does_not_schedule_tasks"):
        assert report["non_authority_posture"][key] is True


def test_input_digest_optional_context_and_deterministic_markdown_escape(tmp_path):
    raw = b'{"x": "pipe | and\\nnewline"}\n'
    p = tmp_path / "optional.json"; p.write_bytes(raw)
    summary, data = read_json_input(str(p), "storage_policy_contract_json")
    summaries = {i: omitted_input(i) for i in OPTIONAL_INPUT_IDS}; summaries["storage_policy_contract_json"] = summary
    summary_with_escapes = dict(summary); summary_with_escapes["path"] = "pipe|path\nline"
    report1 = verify_codex_workcell_storage_operator_consent_contract(storage_operator_consent_contract=_contract(), storage_operator_consent_contract_summary=summary_with_escapes, optional_reports={"storage_policy_contract_json": data}, optional_summaries=summaries)
    report2 = verify_codex_workcell_storage_operator_consent_contract(storage_operator_consent_contract=_contract(), storage_operator_consent_contract_summary=summary_with_escapes, optional_reports={"storage_policy_contract_json": data}, optional_summaries=summaries)
    assert json.dumps(report1, sort_keys=True) == json.dumps(report2, sort_keys=True)
    assert report1["input_summaries"]["storage_operator_consent_contract_json"]["digest"] == hashlib.sha256(raw).hexdigest()
    assert report1["input_summaries"]["storage_operator_consent_contract_json"]["byte_size"] == len(raw)
    md1 = render_codex_workcell_storage_operator_consent_verifier_markdown(report1)
    md2 = render_codex_workcell_storage_operator_consent_verifier_markdown(report2)
    assert md1 == md2
    assert "\\|" in md1 or "<br>" in md1
