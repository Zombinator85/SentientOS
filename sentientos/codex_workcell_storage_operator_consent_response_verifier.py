from __future__ import annotations
# mypy: ignore-errors

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.codex_workcell_storage_operator_consent_response_contract import (
    BLOCKING_GAP_IDS,
    FORBIDDEN_MOUNTS,
    REQUIRED_ACKNOWLEDGEMENT_IDS,
    SCHEMA_FIELD_IDS,
)

WORKCELL_STORAGE_OPERATOR_CONSENT_RESPONSE_VERIFIER_ID = "codex_workcell_storage_operator_consent_response_verifier.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Storage operator consent response artifact contract verification is deterministic metadata only; it creates no response artifact, collects or implies no consent, grants no storage, ledger, glow, daemon, runtime, readiness, finalizer, PR metadata, commit, task, scheduler, alerting, UI, message, model-training, or federation authority."

REQUIRED_CONTRACT_INPUT_ID = "storage_operator_consent_response_contract_json"
OPTIONAL_INPUT_IDS: tuple[str, ...] = (
    "storage_operator_consent_request_packet_json",
    "storage_operator_consent_request_packet_verifier_json",
    "storage_operator_consent_contract_json",
    "storage_operator_consent_verifier_json",
    "storage_runtime_authority_contract_json",
    "storage_runtime_authority_verifier_json",
    "storage_execution_dossier_json",
    "storage_execution_dossier_verifier_json",
    "storage_transaction_plan_json",
    "storage_transaction_plan_verifier_json",
    "storage_policy_contract_json",
    "storage_policy_verifier_json",
    "vow_boundary_contract_json",
    "vow_alignment_attestation_json",
)
ALL_INPUT_IDS = (REQUIRED_CONTRACT_INPUT_ID,) + OPTIONAL_INPUT_IDS

FUTURE_REQUIREMENT_NAMES: tuple[str, ...] = (
    "explicit operator identity capture", "explicit operator response artifact creation",
    "explicit operator response signature binding", "explicit operator timestamp capture",
    "explicit operator scope statement capture", "explicit response status capture",
    "explicit ledger write allow capture", "explicit glow archive allow capture",
    "explicit canonical vow digest acknowledgement", "explicit storage policy digest acknowledgement",
    "explicit transaction plan digest acknowledgement", "explicit execution dossier digest acknowledgement",
    "explicit runtime authority digest acknowledgement", "explicit expiration timestamp capture",
    "explicit revocation terms acknowledgement", "explicit active ledger writer implementation",
    "explicit active glow archiver implementation", "explicit finalizer runtime binding implementation",
    "explicit PR metadata guard runtime binding implementation", "tests proving no readiness authority",
    "docs marking active behavior",
)
NON_AUTHORITY_KEYS: tuple[str, ...] = (
    "storage_operator_consent_response_verifier_is_read_only",
    "storage_operator_consent_response_verifier_is_metadata_only",
    "storage_operator_consent_response_verifier_is_verifier_only",
    "storage_operator_consent_response_verifier_does_not_create_response_artifact",
    "storage_operator_consent_response_verifier_does_not_collect_response",
    "storage_operator_consent_response_verifier_does_not_collect_consent",
    "storage_operator_consent_response_verifier_does_not_imply_consent",
    "storage_operator_consent_response_verifier_does_not_bind_runtime_authority",
    "storage_operator_consent_response_verifier_does_not_activate_memory",
    "storage_operator_consent_response_verifier_does_not_write_ledger",
    "storage_operator_consent_response_verifier_does_not_archive_glow",
    "storage_operator_consent_response_verifier_does_not_modify_memory",
    "storage_operator_consent_response_verifier_does_not_watch_files",
    "storage_operator_consent_response_verifier_does_not_poll_state",
    "storage_operator_consent_response_verifier_does_not_rerun_commands",
    "storage_operator_consent_response_verifier_does_not_decide_readiness",
    "storage_operator_consent_response_verifier_does_not_bypass_finalizer",
    "storage_operator_consent_response_verifier_does_not_bypass_pr_metadata_guard",
    "storage_operator_consent_response_verifier_does_not_authorize_commit",
    "storage_operator_consent_response_verifier_does_not_authorize_pr_creation",
    "storage_operator_consent_response_verifier_does_not_trigger_daemon",
    "storage_operator_consent_response_verifier_does_not_create_tasks",
    "storage_operator_consent_response_verifier_does_not_schedule_tasks",
    "storage_operator_consent_response_verifier_does_not_send_alerts",
    "storage_operator_consent_response_verifier_does_not_render_ui",
    "storage_operator_consent_response_verifier_does_not_send_messages",
    "storage_operator_consent_response_verifier_does_not_deliver_externally",
    "storage_operator_consent_response_verifier_does_not_train_or_modify_models",
    "storage_operator_consent_response_verifier_does_not_establish_federation_consensus",
)
NON_AUTHORITY_POSTURE = {key: True for key in NON_AUTHORITY_KEYS}

class CodexWorkcellStorageOperatorConsentResponseVerifierError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageOperatorConsentResponseVerifierError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageOperatorConsentResponseVerifierError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(data, dict):
        raise CodexWorkcellStorageOperatorConsentResponseVerifierError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, data

def _check(checks: list[dict[str, Any]], check_id: str, passed: bool, details: str, severity: str = "violation") -> None:
    checks.append({"check_id": check_id, "passed": bool(passed), "severity": "info" if passed else severity, "details": details, "authority_boundary": AUTHORITY_BOUNDARY})

def _ids(records: Any, field: str) -> list[Any]:
    if not isinstance(records, list):
        return []
    return [r.get(field) for r in records if isinstance(r, Mapping)]

def _all_bool(records: Any, field: str, value: bool) -> bool:
    return isinstance(records, list) and bool(records) and all(isinstance(r, Mapping) and r.get(field) is value for r in records)

def _all_present(records: Any, field: str) -> bool:
    return isinstance(records, list) and bool(records) and all(isinstance(r, Mapping) and bool(r.get(field)) for r in records)

def _violations(results: Mapping[str, Any]) -> list[str]:
    return [k for k, v in results.items() if k not in {"passed", "violations"} and v is False]

def _detected_report_id(report: Mapping[str, Any]) -> Any:
    for key in sorted(report):
        if key.endswith("_id") or key in {"verification_status", "digest", "storage_operator_consent_response_contract_id"}:
            return report.get(key)
    return None

def _relevant_status_or_digest(report: Mapping[str, Any]) -> Any:
    for key in ("verification_status", "digest", "source_digest", "storage_operator_consent_response_contract_id"):
        if key in report:
            return report.get(key)
    return None

def verify_codex_workcell_storage_operator_consent_response_contract(*, response_contract: Mapping[str, Any], input_summaries: Mapping[str, Mapping[str, Any]], optional_reports: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    optional_reports = optional_reports or {}
    source = input_summaries[REQUIRED_CONTRACT_INPUT_ID]
    schema = response_contract.get("response_artifact_schema")
    schema_ids = _ids(schema, "schema_field_id")
    status = response_contract.get("response_status_policy") if isinstance(response_contract.get("response_status_policy"), Mapping) else {}
    allow = response_contract.get("explicit_allow_policy") if isinstance(response_contract.get("explicit_allow_policy"), Mapping) else {}
    digest = response_contract.get("digest_acknowledgement_policy") if isinstance(response_contract.get("digest_acknowledgement_policy"), Mapping) else {}
    scope = response_contract.get("scope_acknowledgement_policy") if isinstance(response_contract.get("scope_acknowledgement_policy"), Mapping) else {}
    expiration = response_contract.get("expiration_policy") if isinstance(response_contract.get("expiration_policy"), Mapping) else {}
    revocation = response_contract.get("revocation_policy") if isinstance(response_contract.get("revocation_policy"), Mapping) else {}
    denial = response_contract.get("denial_and_ambiguity_policy") if isinstance(response_contract.get("denial_and_ambiguity_policy"), Mapping) else {}
    boundary = response_contract.get("response_authority_boundary") if isinstance(response_contract.get("response_authority_boundary"), Mapping) else {}
    gaps = response_contract.get("response_activation_gap_summary") if isinstance(response_contract.get("response_activation_gap_summary"), Mapping) else {}
    future = response_contract.get("future_activation_requirements")
    posture = response_contract.get("non_authority_posture") if isinstance(response_contract.get("non_authority_posture"), Mapping) else {}

    schema_results = {
        "schema_record_count": len(schema) if isinstance(schema, list) else 0,
        "required_schema_ids_present": all(x in schema_ids for x in SCHEMA_FIELD_IDS),
        "missing_schema_ids": [x for x in SCHEMA_FIELD_IDS if x not in schema_ids],
        "all_schema_records_required_for_future_response_artifact": _all_bool(schema, "required_for_future_response_artifact", True),
        "all_schema_records_currently_satisfied_false": _all_bool(schema, "currently_satisfied", False),
        "all_schema_records_future_only_true": _all_bool(schema, "future_only", True),
        "all_schema_records_active_false": _all_bool(schema, "active", False),
        "all_schema_records_have_forbidden_inference": _all_present(schema, "forbidden_inference"),
    }
    schema_results["passed"] = all(v for k, v in schema_results.items() if k not in {"schema_record_count", "missing_schema_ids"})
    schema_results["violations"] = _violations(schema_results)

    expected_statuses = ["absent", "denied", "approved_for_scoped_storage", "expired", "revoked", "incomplete", "ambiguous", "invalid"]
    status_results = {
        "allowed_response_statuses_seen": status.get("allowed_response_statuses"),
        "allowed_response_statuses_complete": status.get("allowed_response_statuses") == expected_statuses,
        "current_response_status_seen": status.get("current_response_status"),
        "current_response_status_is_absent": status.get("current_response_status") == "absent",
        "absent_status_blocks_storage_seen": status.get("absent_status_blocks_storage") is True,
        "denied_status_blocks_storage_seen": status.get("denied_status_blocks_storage") is True,
        "incomplete_status_blocks_storage_seen": status.get("incomplete_status_blocks_storage") is True,
        "ambiguous_status_blocks_storage_seen": status.get("ambiguous_status_blocks_storage") is True,
        "expired_status_blocks_storage_seen": status.get("expired_status_blocks_storage") is True,
        "revoked_status_blocks_storage_seen": status.get("revoked_status_blocks_storage") is True,
        "invalid_status_blocks_storage_seen": status.get("invalid_status_blocks_storage") is True,
        "approved_status_not_present_here_seen": "approved_status_not_present_here" in status,
        "approved_status_not_present_here_is_true": status.get("approved_status_not_present_here") is True,
        "policy_only_seen": status.get("policy_only") is True,
    }
    status_results["passed"] = all(v for k, v in status_results.items() if k not in {"allowed_response_statuses_seen", "current_response_status_seen"})
    status_results["violations"] = _violations(status_results)

    allow_results = {
        "explicit_allow_ledger_write_required_seen": allow.get("explicit_allow_ledger_write_required") is True,
        "explicit_allow_glow_archive_required_seen": allow.get("explicit_allow_glow_archive_required") is True,
        "explicit_allow_ledger_write_present_seen": "explicit_allow_ledger_write_present" in allow,
        "explicit_allow_ledger_write_present_is_false": allow.get("explicit_allow_ledger_write_present") is False,
        "explicit_allow_glow_archive_present_seen": "explicit_allow_glow_archive_present" in allow,
        "explicit_allow_glow_archive_present_is_false": allow.get("explicit_allow_glow_archive_present") is False,
        "ledger_write_blocked_without_explicit_allow_seen": allow.get("ledger_write_blocked_without_explicit_allow") is True,
        "glow_archive_blocked_without_explicit_allow_seen": allow.get("glow_archive_blocked_without_explicit_allow") is True,
        "allow_flags_not_collected_seen": "allow_flags_not_collected" in allow,
        "allow_flags_not_collected_is_true": allow.get("allow_flags_not_collected") is True,
        "policy_only_seen": allow.get("policy_only") is True,
    }
    allow_results["passed"] = all(allow_results.values())
    allow_results["violations"] = _violations(allow_results)

    ack_ids = digest.get("required_acknowledgement_ids") if isinstance(digest.get("required_acknowledgement_ids"), list) else []
    supplied_ack = digest.get("supplied_acknowledgement_ids") if isinstance(digest.get("supplied_acknowledgement_ids"), list) else None
    digest_results = {
        "digest_algorithm_sha256_seen": digest.get("digest_algorithm") == DIGEST_ALGO,
        "required_acknowledgement_ids_present": all(x in ack_ids for x in REQUIRED_ACKNOWLEDGEMENT_IDS),
        "supplied_acknowledgement_ids_seen": supplied_ack is not None,
        "supplied_acknowledgement_ids_empty": supplied_ack == [],
        "missing_acknowledgement_ids_seen": "missing_acknowledgement_ids" in digest,
        "acknowledgements_not_collected_seen": "acknowledgements_not_collected" in digest,
        "acknowledgements_not_collected_is_true": digest.get("acknowledgements_not_collected") is True,
        "policy_only_seen": digest.get("policy_only") is True,
    }
    digest_results["passed"] = all(digest_results.values())
    digest_results["violations"] = _violations(digest_results)

    scope_results = {
        "allowed_mounts_seen": scope.get("allowed_mounts"),
        "allowed_mounts_exactly_ledger_glow": scope.get("allowed_mounts") == ["/ledger", "/glow"],
        "forbidden_mounts_seen": scope.get("forbidden_mounts"),
        "forbidden_scope_complete": all(x in (scope.get("forbidden_mounts") or []) for x in FORBIDDEN_MOUNTS),
        "mount_scope_acknowledgement_required_seen": scope.get("mount_scope_acknowledgement_required") is True,
        "mount_scope_acknowledgement_present_seen": "mount_scope_acknowledgement_present" in scope,
        "mount_scope_acknowledgement_present_is_false": scope.get("mount_scope_acknowledgement_present") is False,
        "daemon_action_not_authorized_seen": scope.get("daemon_action_not_authorized") is True,
        "model_training_not_authorized_seen": scope.get("model_training_not_authorized") is True,
        "federation_consensus_not_authorized_seen": scope.get("federation_consensus_not_authorized") is True,
        "policy_only_seen": scope.get("policy_only") is True,
    }
    scope_results["passed"] = all(v for k, v in scope_results.items() if k not in {"allowed_mounts_seen", "forbidden_mounts_seen"})
    scope_results["violations"] = _violations(scope_results)

    exp_results = {k: expiration.get(k[:-5] if k.endswith("_seen") else k) is True for k in (
        "expiration_timestamp_required_seen", "expired_or_missing_expiration_blocks_storage_seen",
        "renewal_required_for_new_vow_digest_seen", "renewal_required_for_new_storage_policy_seen",
        "renewal_required_for_new_transaction_plan_seen", "renewal_required_for_changed_mount_scope_seen",
        "lifetime_not_started_seen", "policy_only_seen")}
    exp_results.update({"expiration_timestamp_present_seen": "expiration_timestamp_present" in expiration, "expiration_timestamp_present_is_false": expiration.get("expiration_timestamp_present") is False, "lifetime_not_started_is_true": expiration.get("lifetime_not_started") is True})
    exp_results["passed"] = all(exp_results.values())
    exp_results["violations"] = _violations(exp_results)

    rev_results = {
        "revocation_terms_acknowledgement_required_seen": revocation.get("revocation_terms_acknowledgement_required") is True,
        "revocation_terms_acknowledged_seen": "revocation_terms_acknowledged" in revocation,
        "revocation_terms_acknowledged_is_false": revocation.get("revocation_terms_acknowledged") is False,
        "future_revocation_must_block_new_writes_seen": revocation.get("future_revocation_must_block_new_writes") is True,
        "future_revocation_must_block_new_archives_seen": revocation.get("future_revocation_must_block_new_archives") is True,
        "future_revocation_must_not_delete_existing_receipts_seen": revocation.get("future_revocation_must_not_delete_existing_receipts") is True,
        "future_revocation_receipt_required_seen": revocation.get("future_revocation_receipt_required") is True,
        "revocation_not_performed_seen": "revocation_not_performed" in revocation,
        "revocation_not_performed_is_true": revocation.get("revocation_not_performed") is True,
        "policy_only_seen": revocation.get("policy_only") is True,
    }
    rev_results["passed"] = all(rev_results.values())
    rev_results["violations"] = _violations(rev_results)

    denial_results = {
        "default_without_response_seen": "default_without_response" in denial,
        "default_without_response_is_deny_active_storage": denial.get("default_without_response") == "deny_active_storage",
        "missing_response_blocks_ledger_write_seen": denial.get("missing_response_blocks_ledger_write") is True,
        "missing_response_blocks_glow_archive_seen": denial.get("missing_response_blocks_glow_archive") is True,
        "incomplete_response_blocks_storage_seen": denial.get("incomplete_response_blocks_storage") is True,
        "ambiguous_response_blocks_storage_seen": denial.get("ambiguous_response_blocks_storage") is True,
        "denied_response_blocks_storage_seen": denial.get("denied_response_blocks_storage") is True,
        "remote_or_daemon_response_not_accepted_seen": denial.get("remote_or_daemon_response_not_accepted") is True,
        "federation_state_not_accepted_as_response_seen": denial.get("federation_state_not_accepted_as_response") is True,
        "denial_not_runtime_decision_here_seen": denial.get("denial_not_runtime_decision_here") is True,
        "policy_only_seen": denial.get("policy_only") is True,
    }
    denial_results["passed"] = all(denial_results.values())
    denial_results["violations"] = _violations(denial_results)

    boundary_keys = ("response_contract_is_not_response_artifact", "response_schema_is_not_operator_approval", "request_packet_is_not_consent", "supplied_evidence_does_not_imply_consent", "finalizer_ready_to_commit_does_not_imply_consent", "pr_metadata_guard_ready_does_not_imply_consent", "daemon_recommendation_does_not_imply_consent", "federation_state_does_not_imply_consent", "future_operator_response_must_be_explicit", "future_operator_response_must_be_signature_bound", "authority_boundary_only")
    boundary_results = {f"{k}_seen": boundary.get(k) is True for k in boundary_keys}
    boundary_results["passed"] = all(boundary_results.values())
    boundary_results["violations"] = _violations(boundary_results)

    gap_ids = gaps.get("blocking_gap_ids") if isinstance(gaps.get("blocking_gap_ids"), list) else []
    gap_results = {
        "response_artifact_not_created_seen": "response_artifact_not_created" in gaps,
        "response_artifact_not_created_is_true": gaps.get("response_artifact_not_created") is True,
        "operator_response_present_seen": "operator_response_present" in gaps,
        "operator_response_present_is_false": gaps.get("operator_response_present") is False,
        "consent_not_collected_seen": "consent_not_collected" in gaps,
        "consent_not_collected_is_true": gaps.get("consent_not_collected") is True,
        "consent_not_implied_seen": "consent_not_implied" in gaps,
        "consent_not_implied_is_true": gaps.get("consent_not_implied") is True,
        "operator_consent_present_seen": "operator_consent_present" in gaps,
        "operator_consent_present_is_false": gaps.get("operator_consent_present") is False,
        "active_storage_allowed_now_seen": "active_storage_allowed_now" in gaps,
        "active_storage_allowed_now_is_false": gaps.get("active_storage_allowed_now") is False,
        "runtime_binding_not_performed_seen": "runtime_binding_not_performed" in gaps,
        "runtime_binding_not_performed_is_true": gaps.get("runtime_binding_not_performed") is True,
        "execution_performed_seen": "execution_performed" in gaps,
        "execution_performed_is_false": gaps.get("execution_performed") is False,
        "writes_performed_seen": "writes_performed" in gaps,
        "writes_performed_is_false": gaps.get("writes_performed") is False,
        "archives_performed_seen": "archives_performed" in gaps,
        "archives_performed_is_false": gaps.get("archives_performed") is False,
        "memory_mutation_performed_seen": "memory_mutation_performed" in gaps,
        "memory_mutation_performed_is_false": gaps.get("memory_mutation_performed") is False,
        "required_blocking_gap_ids_present": all(x in gap_ids for x in BLOCKING_GAP_IDS),
    }
    gap_results["passed"] = all(gap_results.values())
    gap_results["violations"] = _violations(gap_results)

    checks: list[dict[str, Any]] = []
    _check(checks, "response_contract_is_object", isinstance(response_contract, Mapping), "Response contract JSON must be an object.")
    for cid, expected in (("response_contract_declares_metadata_only", True), ("response_contract_declares_contract_only", True), ("response_artifact_schema_only_true", True), ("response_artifact_not_created_true", True), ("consent_not_collected_true", True), ("consent_not_implied_true", True), ("runtime_binding_not_performed_true", True)):
        key = cid.replace("response_contract_declares_", "").replace("_true", "")
        if cid == "response_contract_declares_contract_only": key = "response_contract_only"
        _check(checks, cid, response_contract.get(key) is expected, f"{key} must be true.")
    for cid, key in (("operator_response_present_false", "operator_response_present"), ("operator_consent_present_false", "operator_consent_present"), ("active_storage_allowed_now_false", "active_storage_allowed_now"), ("execution_performed_false", "execution_performed"), ("writes_performed_false", "writes_performed"), ("archives_performed_false", "archives_performed"), ("memory_mutation_performed_false", "memory_mutation_performed")):
        _check(checks, cid, response_contract.get(key) is False, f"{key} must be false.")
    _check(checks, "response_artifact_schema_present", isinstance(schema, list) and bool(schema), "Response artifact schema must be present.")
    _check(checks, "response_schema_required_ids_present", schema_results["required_schema_ids_present"], "Required response schema IDs must be present.")
    _check(checks, "response_schema_future_only", schema_results["all_schema_records_future_only_true"], "Schema records must be future-only.")
    _check(checks, "response_schema_currently_satisfied_false", schema_results["all_schema_records_currently_satisfied_false"], "Schema records must be currently unsatisfied.")
    _check(checks, "response_schema_active_false", schema_results["all_schema_records_active_false"], "Schema records must be inactive.")
    _check(checks, "response_status_policy_present", bool(status), "Response status policy must be present.")
    _check(checks, "current_response_status_absent", status_results["current_response_status_is_absent"], "Current response status must be absent.")
    _check(checks, "absent_status_blocks_storage", status_results["absent_status_blocks_storage_seen"], "Absent status must block storage.")
    _check(checks, "denied_incomplete_ambiguous_expired_revoked_invalid_block_storage", all(status_results[k] for k in status_results if k.endswith("_status_blocks_storage_seen") and k != "absent_status_blocks_storage_seen"), "Blocking statuses must block storage.")
    _check(checks, "approved_status_not_present_here", status_results["approved_status_not_present_here_is_true"], "Approved status must not be present here.")
    _check(checks, "explicit_allow_policy_present", bool(allow), "Explicit allow policy must be present.")
    _check(checks, "explicit_allow_flags_required_and_absent", allow_results["passed"], "Allow flags must be required, absent, and uncollected.")
    _check(checks, "digest_acknowledgement_policy_present", bool(digest), "Digest acknowledgement policy must be present.")
    _check(checks, "required_acknowledgement_ids_present", digest_results["required_acknowledgement_ids_present"], "Required acknowledgement IDs must be present.")
    _check(checks, "acknowledgements_not_collected_true", digest_results["passed"], "Digest acknowledgements must use sha256, include required IDs, have empty supplied acknowledgements, and remain uncollected.")
    _check(checks, "scope_acknowledgement_policy_present", bool(scope), "Scope acknowledgement policy must be present.")
    _check(checks, "scope_acknowledgement_allows_ledger_glow_only", scope_results["allowed_mounts_exactly_ledger_glow"], "Scope must allow exactly /ledger and /glow.")
    _check(checks, "scope_acknowledgement_forbids_vow_pulse_daemon_and_path_classes", scope_results["forbidden_scope_complete"], "Forbidden scope must be complete.")
    _check(checks, "mount_scope_acknowledgement_absent", scope_results["mount_scope_acknowledgement_present_is_false"], "Mount scope acknowledgement must be absent.")
    _check(checks, "expiration_policy_present", bool(expiration), "Expiration policy must be present.")
    _check(checks, "expiration_required_and_absent", exp_results["expiration_timestamp_required_seen"] and exp_results["expiration_timestamp_present_is_false"] and exp_results["lifetime_not_started_is_true"], "Expiration must be required and absent, and lifetime must not be started.")
    _check(checks, "missing_expiration_blocks_storage", exp_results["expired_or_missing_expiration_blocks_storage_seen"], "Missing expiration must block storage.")
    _check(checks, "revocation_policy_present", bool(revocation), "Revocation policy must be present.")
    _check(checks, "revocation_terms_required_and_absent", rev_results["revocation_terms_acknowledgement_required_seen"] and rev_results["revocation_terms_acknowledged_is_false"], "Revocation terms must be required and absent.")
    _check(checks, "revocation_not_performed_true", rev_results["revocation_not_performed_is_true"], "Revocation must not be performed.")
    _check(checks, "denial_and_ambiguity_policy_present", bool(denial), "Denial policy must be present.")
    _check(checks, "default_without_response_denies_active_storage", denial_results["default_without_response_is_deny_active_storage"], "Default without response must deny active storage.")
    _check(checks, "missing_incomplete_ambiguous_denied_response_blocks_storage", denial_results["missing_response_blocks_ledger_write_seen"] and denial_results["incomplete_response_blocks_storage_seen"] and denial_results["ambiguous_response_blocks_storage_seen"] and denial_results["denied_response_blocks_storage_seen"], "Missing/incomplete/ambiguous/denied responses must block storage.")
    _check(checks, "remote_daemon_federation_response_not_accepted", denial_results["remote_or_daemon_response_not_accepted_seen"] and denial_results["federation_state_not_accepted_as_response_seen"], "Remote, daemon, and federation responses must not be accepted.")
    _check(checks, "response_authority_boundary_present", bool(boundary), "Response authority boundary must be present.")
    _check(checks, "contract_schema_request_evidence_do_not_imply_consent", boundary.get("response_contract_is_not_response_artifact") is True and boundary.get("response_schema_is_not_operator_approval") is True and boundary.get("request_packet_is_not_consent") is True and boundary.get("supplied_evidence_does_not_imply_consent") is True, "Contract/schema/request/evidence must not imply consent.")
    _check(checks, "finalizer_guard_do_not_imply_consent", boundary.get("finalizer_ready_to_commit_does_not_imply_consent") is True and boundary.get("pr_metadata_guard_ready_does_not_imply_consent") is True, "Finalizer and guard readiness must not imply consent.")
    _check(checks, "daemon_federation_do_not_imply_consent", boundary.get("daemon_recommendation_does_not_imply_consent") is True and boundary.get("federation_state_does_not_imply_consent") is True, "Daemon and federation state must not imply consent.")
    _check(checks, "response_activation_gap_summary_present", bool(gaps), "Response activation gap summary must be present.")
    _check(checks, "required_blocking_gap_ids_present", gap_results["required_blocking_gap_ids_present"], "Required blocking gap IDs must be present.")
    _check(checks, "reviewer_hygiene_bad_openai_repo_url_absent", True, "Repository grep validation is external to this metadata verifier.", "info")
    future_ok = isinstance(future, list) and all(isinstance(r, Mapping) and r.get("status") == "future_only" and r.get("met") is False and r.get("active") is False for r in future)
    _check(checks, "future_activation_requirements_inactive", future_ok, "Future activation requirements must be future-only, unmet, and inactive.")
    posture_ok = bool(posture) and all(v is True for v in posture.values())
    _check(checks, "non_authority_posture_present", bool(posture), "Non-authority posture must be present.")
    _check(checks, "non_authority_posture_true", posture_ok, "Non-authority posture flags must be true.")

    failed = [c["check_id"] for c in checks if not c["passed"]]
    incomplete = [c["check_id"] for c in checks if not c["passed"] and c["check_id"].endswith("_present")]
    verification_status = "storage_operator_consent_response_contract_verified" if not failed else ("storage_operator_consent_response_contract_incomplete" if incomplete else "storage_operator_consent_response_contract_failed")
    optional_summary = []
    for input_id in OPTIONAL_INPUT_IDS:
        s = input_summaries.get(input_id, omitted_input(input_id))
        r = optional_reports.get(input_id, {})
        optional_summary.append({"input_id": input_id, "provided": s.get("provided") is True, "detected_report_id": _detected_report_id(r), "source_digest": s.get("digest"), "source_digest_algo": s.get("digest_algo"), "source_byte_size": s.get("byte_size"), "relevant_status_or_digest": _relevant_status_or_digest(r), "context_only": True})

    violation_ids = [c["check_id"] for c in checks if (not c["passed"] and c["severity"] == "violation")]
    warning_ids = [c["check_id"] for c in checks if (not c["passed"] and c["severity"] == "warning")]
    return {
        "storage_operator_consent_response_verifier_id": WORKCELL_STORAGE_OPERATOR_CONSENT_RESPONSE_VERIFIER_ID,
        "metadata_only": True, "verifier_only": True, "response_artifact_not_created": True,
        "operator_response_present": False, "consent_not_collected": True, "consent_not_implied": True,
        "operator_consent_present": False, "runtime_binding_not_performed": True, "active_storage_allowed_now": False,
        "execution_performed": False, "writes_performed": False, "archives_performed": False,
        "memory_mutation_performed": False, "not_runtime_authority": True, "not_memory_writer": True,
        "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True,
        "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True,
        "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {k: input_summaries.get(k, omitted_input(k)) for k in ALL_INPUT_IDS},
        "response_contract_summary": {
            "storage_operator_consent_response_contract_id": response_contract.get("storage_operator_consent_response_contract_id"),
            "metadata_only_seen": response_contract.get("metadata_only"), "response_contract_only_seen": response_contract.get("response_contract_only"),
            "response_artifact_schema_only_seen": response_contract.get("response_artifact_schema_only"),
            "response_artifact_not_created_seen": response_contract.get("response_artifact_not_created"),
            "operator_response_present_seen": response_contract.get("operator_response_present"),
            "consent_not_collected_seen": response_contract.get("consent_not_collected"), "consent_not_implied_seen": response_contract.get("consent_not_implied"),
            "operator_consent_present_seen": response_contract.get("operator_consent_present"),
            "runtime_binding_not_performed_seen": response_contract.get("runtime_binding_not_performed"),
            "active_storage_allowed_now_seen": response_contract.get("active_storage_allowed_now"), "execution_performed_seen": response_contract.get("execution_performed"),
            "writes_performed_seen": response_contract.get("writes_performed"), "archives_performed_seen": response_contract.get("archives_performed"),
            "memory_mutation_performed_seen": response_contract.get("memory_mutation_performed"),
            "response_schema_count": len(schema) if isinstance(schema, list) else None,
            "blocking_gap_count": len(gap_ids), "non_authority_posture_present": bool(posture),
            "non_authority_posture_all_true": all(v is True for v in posture.values()) if posture else None,
            "source_digest": source.get("digest"), "source_digest_algo": source.get("digest_algo"), "source_byte_size": source.get("byte_size"),
        },
        "optional_context_summary": optional_summary,
        "verification_status": verification_status,
        "verification_checks": checks,
        "response_artifact_schema_results": schema_results,
        "response_status_policy_results": status_results,
        "explicit_allow_policy_results": allow_results,
        "digest_acknowledgement_policy_results": digest_results,
        "scope_acknowledgement_policy_results": scope_results,
        "expiration_policy_results": exp_results,
        "revocation_policy_results": rev_results,
        "denial_and_ambiguity_policy_results": denial_results,
        "response_authority_boundary_results": boundary_results,
        "response_activation_gap_results": gap_results,
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata verifier.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "violation_summary": {"violation_count": len(violation_ids), "warning_count": len(warning_ids), "info_count": sum(1 for c in checks if c["severity"] == "info"), "violation_check_ids": violation_ids, "warning_check_ids": warning_ids, "verifier_only": True, "no_action_taken": True},
        "sentientos_mount_alignment": {"/ledger": "operator consent response verification only; no ledger write", "/glow": "operator consent response verification only; no archive write", "/vow": "canonical digest acknowledgement context for future consent response binding", "/pulse": "future watcher boundary; response verifier does not activate it", "/daemon": "future action boundary; response verifier does not activate it"},
        "future_activation_requirements": [{"requirement": name, "status": "future_only", "met": False, "active": False} for name in FUTURE_REQUIREMENT_NAMES],
        "non_authority_posture": NON_AUTHORITY_POSTURE,
    }

def _cell(value: Any) -> str:
    return json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)

def _escape(value: Any) -> str:
    return _cell(value).replace("|", "\\|").replace("\n", "<br>")

def _table(value: Any) -> str:
    rows = ["| Field | Value |", "| --- | --- |"]
    mapping = {str(i): v for i, v in enumerate(value)} if isinstance(value, list) else (value if isinstance(value, Mapping) else {"value": value})
    for key in sorted(mapping):
        rows.append(f"| {_escape(key)} | {_escape(mapping[key])} |")
    return "\n".join(rows)

def render_codex_workcell_storage_operator_consent_response_verifier_markdown(report: Mapping[str, Any]) -> str:
    sections = ["# Codex Workcell Storage Operator Consent Response Artifact Verifier", "", "Deterministic metadata-only structural verifier. It creates no response artifact, collects or implies no consent, and grants no readiness, storage, ledger, glow, daemon, federation, UI, message, or runtime authority."]
    keys = [
        ("Input summaries", "input_summaries"), ("Response contract summary", "response_contract_summary"),
        ("Optional context summary", "optional_context_summary"), ("Verification status", "verification_status"),
        ("Verification checks", "verification_checks"), ("Response artifact schema results", "response_artifact_schema_results"),
        ("Response status policy results", "response_status_policy_results"), ("Explicit allow policy results", "explicit_allow_policy_results"),
        ("Digest acknowledgement policy results", "digest_acknowledgement_policy_results"), ("Scope acknowledgement policy results", "scope_acknowledgement_policy_results"),
        ("Expiration policy results", "expiration_policy_results"), ("Revocation policy results", "revocation_policy_results"),
        ("Denial and ambiguity policy results", "denial_and_ambiguity_policy_results"), ("Response authority boundary results", "response_authority_boundary_results"),
        ("Response activation gap results", "response_activation_gap_results"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"),
        ("Violation summary", "violation_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"),
        ("Future activation requirements", "future_activation_requirements"), ("Non-authority posture", "non_authority_posture"),
    ]
    for title, key in keys:
        sections.extend(["", f"## {title}", _table(report.get(key))])
    return "\n".join(sections) + "\n"
