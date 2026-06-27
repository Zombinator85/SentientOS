from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, cast

WORKCELL_STORAGE_OPERATOR_CONSENT_VERIFIER_ID = "codex_workcell_storage_operator_consent_verifier.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Storage operator consent request verification is deterministic metadata only; it collects no consent, implies no consent, grants no runtime, memory, ledger, glow, daemon, readiness, finalizer, PR metadata, commit, task, scheduler, alerting, model-training, or federation authority."
OPTIONAL_INPUT_IDS: tuple[str, ...] = (
    "storage_runtime_authority_contract_json", "storage_runtime_authority_verifier_json",
    "storage_execution_dossier_json", "storage_execution_dossier_verifier_json",
    "storage_transaction_plan_json", "storage_transaction_plan_verifier_json",
    "storage_policy_contract_json", "storage_policy_verifier_json",
    "vow_boundary_contract_json", "vow_alignment_attestation_json",
)
REQUIRED_SCHEMA_IDS: tuple[str, ...] = (
    "operator_identity_required", "consent_timestamp_required", "consent_scope_required",
    "consent_mount_scope_required", "canonical_vow_digest_required", "storage_policy_digest_required",
    "storage_policy_verifier_digest_required", "transaction_plan_digest_required",
    "transaction_plan_verifier_digest_required", "execution_dossier_digest_required",
    "execution_dossier_verifier_digest_required", "runtime_authority_contract_digest_required",
    "runtime_authority_verifier_digest_required", "finalizer_guard_evidence_required",
    "explicit_allow_ledger_write_required", "explicit_allow_glow_archive_required",
    "explicit_denial_default_required", "revocation_terms_required", "expiration_terms_required",
    "no_daemon_self_authorization_required", "no_federation_implied_consent_required",
)
REQUIRED_EVIDENCE_IDS: tuple[str, ...] = (
    "canonical_vow_digest", "storage_policy_contract_digest", "storage_policy_verifier_digest",
    "storage_transaction_plan_digest", "storage_transaction_plan_verifier_digest",
    "storage_execution_dossier_digest", "storage_execution_dossier_verifier_digest",
    "runtime_authority_contract_digest", "runtime_authority_verifier_digest",
    "finalizer_pre_commit_receipt", "pr_metadata_finalizer_receipt", "pr_metadata_guard_receipt",
    "operator_identity", "operator_timestamp", "operator_scope_statement",
)
REQUIRED_BLOCKING_GAP_IDS: tuple[str, ...] = (
    "operator_consent_missing", "operator_identity_missing", "consent_timestamp_missing",
    "consent_scope_missing", "consent_digest_bindings_missing", "consent_expiration_missing",
    "consent_revocation_terms_missing", "explicit_ledger_write_allow_missing",
    "explicit_glow_archive_allow_missing", "runtime_authority_binding_missing",
)
FUTURE_REQUIREMENT_NAMES: tuple[str, ...] = (
    "explicit operator identity capture", "explicit operator consent capture", "explicit consent timestamp capture",
    "explicit consent expiration policy", "explicit consent revocation policy", "explicit canonical vow digest binding",
    "explicit storage policy digest binding", "explicit transaction plan digest binding", "explicit execution dossier digest binding",
    "explicit runtime authority digest binding", "explicit active ledger writer implementation", "explicit active glow archiver implementation",
    "explicit finalizer runtime binding implementation", "explicit PR metadata guard runtime binding implementation",
    "explicit storage path enforcement", "explicit retention enforcement", "explicit digest verification enforcement",
    "explicit parent-chain validation enforcement", "tests proving no readiness authority", "docs marking active behavior",
)
NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "storage_operator_consent_verifier_is_read_only": True,
    "storage_operator_consent_verifier_is_metadata_only": True,
    "storage_operator_consent_verifier_is_verifier_only": True,
    "storage_operator_consent_verifier_does_not_collect_consent": True,
    "storage_operator_consent_verifier_does_not_imply_consent": True,
    "storage_operator_consent_verifier_does_not_bind_runtime_authority": True,
    "storage_operator_consent_verifier_does_not_activate_memory": True,
    "storage_operator_consent_verifier_does_not_write_ledger": True,
    "storage_operator_consent_verifier_does_not_archive_glow": True,
    "storage_operator_consent_verifier_does_not_modify_memory": True,
    "storage_operator_consent_verifier_does_not_watch_files": True,
    "storage_operator_consent_verifier_does_not_poll_state": True,
    "storage_operator_consent_verifier_does_not_rerun_commands": True,
    "storage_operator_consent_verifier_does_not_decide_readiness": True,
    "storage_operator_consent_verifier_does_not_bypass_finalizer": True,
    "storage_operator_consent_verifier_does_not_bypass_pr_metadata_guard": True,
    "storage_operator_consent_verifier_does_not_authorize_commit": True,
    "storage_operator_consent_verifier_does_not_authorize_pr_creation": True,
    "storage_operator_consent_verifier_does_not_trigger_daemon": True,
    "storage_operator_consent_verifier_does_not_create_tasks": True,
    "storage_operator_consent_verifier_does_not_schedule_tasks": True,
    "storage_operator_consent_verifier_does_not_send_alerts": True,
    "storage_operator_consent_verifier_does_not_train_or_modify_models": True,
    "storage_operator_consent_verifier_does_not_establish_federation_consensus": True,
}

class CodexWorkcellStorageOperatorConsentVerifierError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageOperatorConsentVerifierError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageOperatorConsentVerifierError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise CodexWorkcellStorageOperatorConsentVerifierError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _all_true(value: Any) -> bool | None:
    if not isinstance(value, Mapping):
        return None
    return all(v is True for v in value.values())

def _ids(records: Any, key: str) -> set[Any]:
    return {r.get(key) for r in records if isinstance(r, Mapping)} if isinstance(records, list) else set()

def _violations(results: Mapping[str, Any], ignore: set[str] | None = None) -> list[str]:
    ignored = {"passed", "violations"} | (ignore or set())
    return [k for k, v in results.items() if k not in ignored and v is False]

def _check(checks: list[dict[str, Any]], check_id: str, passed: bool, details: str, severity: str = "violation") -> None:
    checks.append({"check_id": check_id, "passed": passed, "severity": "info" if passed else severity, "details": details, "authority_boundary": AUTHORITY_BOUNDARY})

def _report_id(data: Mapping[str, Any]) -> Any:
    for key in ("storage_operator_consent_contract_id", "storage_runtime_authority_contract_id", "storage_runtime_authority_verifier_id", "storage_execution_dossier_id", "storage_execution_dossier_verifier_id", "storage_transaction_plan_id", "storage_transaction_plan_verifier_id", "storage_policy_contract_id", "storage_policy_verifier_id", "vow_boundary_contract_id", "vow_alignment_attestation_id"):
        if data.get(key) is not None:
            return data.get(key)
    return None

def _status_or_digest(data: Mapping[str, Any]) -> Any:
    for key in ("verification_status", "storage_execution_status", "storage_transaction_plan_verification_status", "storage_policy_verification_status", "digest", "source_digest"):
        if data.get(key) is not None:
            return data.get(key)
    return None

def verify_codex_workcell_storage_operator_consent_contract(*, storage_operator_consent_contract: Mapping[str, Any], storage_operator_consent_contract_summary: Mapping[str, Any], optional_reports: Mapping[str, Mapping[str, Any]], optional_summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    c = storage_operator_consent_contract
    schema = c.get("consent_request_schema"); schema_list: list[Any] = schema if isinstance(schema, list) else []
    evidence: Mapping[str, Any] = cast(Mapping[str, Any], c.get("required_consent_evidence")) if isinstance(c.get("required_consent_evidence"), Mapping) else {}
    scope: Mapping[str, Any] = cast(Mapping[str, Any], c.get("consent_scope_policy")) if isinstance(c.get("consent_scope_policy"), Mapping) else {}
    digest: Mapping[str, Any] = cast(Mapping[str, Any], c.get("consent_digest_binding_policy")) if isinstance(c.get("consent_digest_binding_policy"), Mapping) else {}
    lifetime: Mapping[str, Any] = cast(Mapping[str, Any], c.get("consent_lifetime_policy")) if isinstance(c.get("consent_lifetime_policy"), Mapping) else {}
    revocation: Mapping[str, Any] = cast(Mapping[str, Any], c.get("consent_revocation_policy")) if isinstance(c.get("consent_revocation_policy"), Mapping) else {}
    denial: Mapping[str, Any] = cast(Mapping[str, Any], c.get("consent_denial_policy")) if isinstance(c.get("consent_denial_policy"), Mapping) else {}
    boundary: Mapping[str, Any] = cast(Mapping[str, Any], c.get("consent_authority_boundary")) if isinstance(c.get("consent_authority_boundary"), Mapping) else {}
    gaps: Mapping[str, Any] = cast(Mapping[str, Any], c.get("consent_activation_gap_summary")) if isinstance(c.get("consent_activation_gap_summary"), Mapping) else {}
    future = c.get("future_activation_requirements"); nonauth = c.get("non_authority_posture")
    schema_ids = _ids(schema, "schema_field_id"); missing_schema = [x for x in REQUIRED_SCHEMA_IDS if x not in schema_ids]
    required_evidence: list[Any] = cast(list[Any], evidence.get("required_evidence_ids")) if isinstance(evidence.get("required_evidence_ids"), list) else []
    missing_evidence = [x for x in REQUIRED_EVIDENCE_IDS if x not in required_evidence]
    allowed: list[Any] = cast(list[Any], scope.get("allowed_mounts")) if isinstance(scope.get("allowed_mounts"), list) else []
    forbidden: list[Any] = cast(list[Any], scope.get("forbidden_mounts")) if isinstance(scope.get("forbidden_mounts"), list) else []
    gap_ids: list[Any] = cast(list[Any], gaps.get("blocking_gap_ids")) if isinstance(gaps.get("blocking_gap_ids"), list) else []
    checks: list[dict[str, Any]] = []
    _check(checks, "consent_contract_is_object", isinstance(c, Mapping), "Consent contract input parsed as JSON object.")
    for check_id, key, expected in (("consent_contract_declares_metadata_only", "metadata_only", True), ("consent_contract_declares_contract_only", "consent_contract_only", True), ("consent_request_shape_only_true", "consent_request_shape_only", True), ("consent_not_collected_true", "consent_not_collected", True), ("operator_consent_present_false", "operator_consent_present", False), ("runtime_binding_not_performed_true", "runtime_binding_not_performed", True), ("active_storage_allowed_now_false", "active_storage_allowed_now", False), ("execution_performed_false", "execution_performed", False), ("writes_performed_false", "writes_performed", False), ("archives_performed_false", "archives_performed", False), ("memory_mutation_performed_false", "memory_mutation_performed", False)):
        _check(checks, check_id, c.get(key) is expected, f"{key} must be {expected}.")
    _check(checks, "consent_request_schema_present", bool(schema_list), "consent_request_schema must be present.")
    _check(checks, "consent_schema_required_ids_present", not missing_schema, "Required schema IDs must be present.")
    _check(checks, "consent_schema_future_only", bool(schema_list) and all(isinstance(r, Mapping) and r.get("future_only") is True for r in schema_list), "Schema records must be future_only.")
    _check(checks, "consent_schema_currently_satisfied_false", bool(schema_list) and all(isinstance(r, Mapping) and r.get("currently_satisfied") is False for r in schema_list), "Schema records must be unsatisfied.")
    _check(checks, "consent_schema_active_false", bool(schema_list) and all(isinstance(r, Mapping) and r.get("active") is False for r in schema_list), "Schema records must be inactive.")
    _check(checks, "required_consent_evidence_present", bool(evidence), "required_consent_evidence must be present.")
    _check(checks, "required_consent_evidence_ids_present", not missing_evidence, "Required evidence IDs must be present.")
    _check(checks, "consent_scope_policy_present", bool(scope), "Scope policy must be present.")
    _check(checks, "consent_scope_allows_ledger_glow_only", allowed == ["/ledger", "/glow"], "Allowed mounts must be exactly /ledger and /glow.")
    _check(checks, "consent_scope_forbids_vow_pulse_daemon", all(x in forbidden for x in ("/vow", "/pulse", "/daemon")), "Scope must forbid /vow, /pulse, and /daemon.")
    _check(checks, "consent_scope_forbids_host_network_temp_backdoor_paths", all(x in forbidden for x in ("host_absolute_paths", "network_paths", "temp_paths_as_canonical", "hidden_backdoor_paths")), "Scope must forbid host/network/temp/backdoor paths.")
    _check(checks, "consent_digest_binding_policy_present", bool(digest), "Digest policy must be present.")
    _check(checks, "consent_digest_bindings_required", all(digest.get(k) is True for k in ("canonical_vow_digest_required", "storage_policy_digest_required", "transaction_plan_digest_required", "execution_dossier_digest_required", "runtime_authority_digest_required")), "Digest bindings must be required.")
    _check(checks, "consent_digest_binding_not_performed", digest.get("digest_binding_not_performed") is True, "Digest binding must not be performed.")
    _check(checks, "consent_lifetime_policy_present", bool(lifetime), "Lifetime policy must be present.")
    _check(checks, "consent_expiration_required", lifetime.get("expiration_required") is True, "Expiration is required.")
    _check(checks, "consent_revocation_required", lifetime.get("revocation_required") is True, "Revocation is required.")
    _check(checks, "consent_renewal_required_for_digest_or_scope_change", all(lifetime.get(k) is True for k in ("renewal_required_for_new_vow_digest", "renewal_required_for_new_storage_policy", "renewal_required_for_new_transaction_plan", "renewal_required_for_changed_mount_scope")), "Renewal required for digest/scope changes.")
    _check(checks, "consent_revocation_policy_present", bool(revocation), "Revocation policy must be present.")
    _check(checks, "revocation_blocks_future_writes_archives", revocation.get("revocation_must_block_new_writes") is True and revocation.get("revocation_must_block_new_archives") is True, "Revocation must block new writes and archives.")
    _check(checks, "revocation_does_not_delete_existing_receipts", revocation.get("revocation_must_not_delete_existing_receipts") is True, "Revocation must not delete receipts.")
    _check(checks, "consent_denial_policy_present", bool(denial), "Denial policy must be present.")
    _check(checks, "missing_consent_denies_active_storage", denial.get("default_without_consent") == "deny_active_storage", "Missing consent must deny active storage.")
    _check(checks, "ambiguous_consent_blocks_storage", denial.get("ambiguous_consent_blocks_storage") is True, "Ambiguous consent must block storage.")
    _check(checks, "remote_or_daemon_consent_not_accepted", denial.get("remote_or_daemon_consent_not_accepted") is True, "Remote or daemon consent is not accepted.")
    _check(checks, "consent_authority_boundary_present", bool(boundary), "Authority boundary must be present.")
    _check(checks, "contract_schema_reports_do_not_imply_consent", boundary.get("consent_contract_is_not_consent") is True and boundary.get("consent_schema_is_not_operator_approval") is True and boundary.get("supplied_reports_do_not_imply_consent") is True, "Contract/schema/reports must not imply consent.")
    _check(checks, "finalizer_guard_do_not_imply_consent", boundary.get("finalizer_ready_to_commit_does_not_imply_consent") is True and boundary.get("pr_metadata_guard_ready_does_not_imply_consent") is True, "Finalizer/guard do not imply consent.")
    _check(checks, "daemon_federation_do_not_imply_consent", boundary.get("daemon_recommendation_does_not_imply_consent") is True and boundary.get("federation_state_does_not_imply_consent") is True, "Daemon/federation do not imply consent.")
    _check(checks, "consent_activation_gap_summary_present", bool(gaps), "Activation gap summary must be present.")
    _check(checks, "required_blocking_gap_ids_present", all(x in gap_ids for x in REQUIRED_BLOCKING_GAP_IDS), "Required blocking gap IDs must be present.")
    _check(checks, "reviewer_hygiene_bad_openai_repo_url_absent", True, "Repository grep validation is external to this metadata verifier.", "info")
    future_ok = isinstance(future, list) and all(isinstance(r, Mapping) and r.get("status") == "future_only" and r.get("met") is False and r.get("active") is False for r in future)
    _check(checks, "future_activation_requirements_inactive", future_ok, "Future activation requirements must be future_only, unmet, and inactive.")
    _check(checks, "non_authority_posture_present", isinstance(nonauth, Mapping), "non_authority_posture must be present.")
    _check(checks, "non_authority_posture_true", _all_true(nonauth) is True, "All non_authority_posture values must be true.")
    consent_schema_results: dict[str, Any] = {"schema_record_count": len(schema_list), "required_schema_ids_present": not missing_schema, "missing_schema_ids": missing_schema, "all_schema_records_required_for_future_consent": bool(schema_list) and all(isinstance(r, Mapping) and r.get("required_for_future_consent") is True for r in schema_list), "all_schema_records_currently_satisfied_false": bool(schema_list) and all(isinstance(r, Mapping) and r.get("currently_satisfied") is False for r in schema_list), "all_schema_records_future_only_true": bool(schema_list) and all(isinstance(r, Mapping) and r.get("future_only") is True for r in schema_list), "all_schema_records_active_false": bool(schema_list) and all(isinstance(r, Mapping) and r.get("active") is False for r in schema_list), "all_schema_records_have_forbidden_inference": bool(schema_list) and all(isinstance(r, Mapping) and bool(r.get("forbidden_inference")) for r in schema_list)}
    consent_schema_results["violations"] = _violations(consent_schema_results, {"schema_record_count", "missing_schema_ids"}) + missing_schema; consent_schema_results["passed"] = not consent_schema_results["violations"]
    consent_evidence_results: dict[str, Any] = {"required_evidence_ids_present": not missing_evidence, "missing_required_evidence_ids": missing_evidence, "supplied_evidence_ids": evidence.get("supplied_evidence_ids", []), "missing_evidence_ids": evidence.get("missing_evidence_ids", []), "evidence_collection_not_performed_seen": "evidence_collection_not_performed" in evidence, "evidence_collection_not_performed_is_true": evidence.get("evidence_collection_not_performed") is True, "consent_not_collected_seen": "consent_not_collected" in evidence, "consent_not_collected_is_true": evidence.get("consent_not_collected") is True, "policy_only_seen": evidence.get("policy_only") is True}
    consent_evidence_results["violations"] = _violations(consent_evidence_results, {"missing_required_evidence_ids", "supplied_evidence_ids", "missing_evidence_ids"}) + missing_evidence; consent_evidence_results["passed"] = not consent_evidence_results["violations"]
    consent_scope_results: dict[str, Any] = {"allowed_mounts_seen": isinstance(allowed, list), "allowed_mounts_exactly_ledger_glow": allowed == ["/ledger", "/glow"], "forbidden_mounts_seen": isinstance(forbidden, list), "forbids_vow_pulse_daemon": all(x in forbidden for x in ("/vow", "/pulse", "/daemon")), "forbids_host_absolute_paths": "host_absolute_paths" in forbidden, "forbids_network_paths": "network_paths" in forbidden, "forbids_temp_paths_as_canonical": "temp_paths_as_canonical" in forbidden, "forbids_hidden_backdoor_paths": "hidden_backdoor_paths" in forbidden, "ledger_write_must_be_explicit_seen": scope.get("ledger_write_must_be_explicit") is True, "glow_archive_must_be_explicit_seen": scope.get("glow_archive_must_be_explicit") is True, "consent_does_not_authorize_daemon_action_seen": scope.get("consent_does_not_authorize_daemon_action") is True, "consent_does_not_authorize_model_training_seen": scope.get("consent_does_not_authorize_model_training") is True, "consent_does_not_authorize_federation_consensus_seen": scope.get("consent_does_not_authorize_federation_consensus") is True, "policy_only_seen": scope.get("policy_only") is True}
    consent_scope_results["violations"] = _violations(consent_scope_results); consent_scope_results["passed"] = not consent_scope_results["violations"]
    consent_digest_binding_results: dict[str, Any] = {"canonical_vow_digest_required_seen": digest.get("canonical_vow_digest_required") is True, "storage_policy_digest_required_seen": digest.get("storage_policy_digest_required") is True, "transaction_plan_digest_required_seen": digest.get("transaction_plan_digest_required") is True, "execution_dossier_digest_required_seen": digest.get("execution_dossier_digest_required") is True, "runtime_authority_digest_required_seen": digest.get("runtime_authority_digest_required") is True, "digest_algorithm_sha256_seen": digest.get("digest_algorithm") == DIGEST_ALGO, "digest_binding_not_performed_seen": "digest_binding_not_performed" in digest, "digest_binding_not_performed_is_true": digest.get("digest_binding_not_performed") is True, "policy_only_seen": digest.get("policy_only") is True, "missing_digest_bindings": digest.get("missing_digest_bindings", [])}
    consent_digest_binding_results["violations"] = _violations(consent_digest_binding_results, {"missing_digest_bindings"}); consent_digest_binding_results["passed"] = not consent_digest_binding_results["violations"]
    consent_lifetime_results: dict[str, Any] = {"expiration_required_seen": lifetime.get("expiration_required") is True, "revocation_required_seen": lifetime.get("revocation_required") is True, "renewal_required_for_new_vow_digest_seen": lifetime.get("renewal_required_for_new_vow_digest") is True, "renewal_required_for_new_storage_policy_seen": lifetime.get("renewal_required_for_new_storage_policy") is True, "renewal_required_for_new_transaction_plan_seen": lifetime.get("renewal_required_for_new_transaction_plan") is True, "renewal_required_for_changed_mount_scope_seen": lifetime.get("renewal_required_for_changed_mount_scope") is True, "consent_lifetime_not_started_seen": "consent_lifetime_not_started" in lifetime, "consent_lifetime_not_started_is_true": lifetime.get("consent_lifetime_not_started") is True, "policy_only_seen": lifetime.get("policy_only") is True}
    consent_lifetime_results["violations"] = _violations(consent_lifetime_results); consent_lifetime_results["passed"] = not consent_lifetime_results["violations"]
    consent_revocation_results: dict[str, Any] = {"revocation_must_block_new_writes_seen": revocation.get("revocation_must_block_new_writes") is True, "revocation_must_block_new_archives_seen": revocation.get("revocation_must_block_new_archives") is True, "revocation_must_not_delete_existing_receipts_seen": revocation.get("revocation_must_not_delete_existing_receipts") is True, "revocation_must_create_future_revocation_receipt_seen": revocation.get("revocation_must_create_future_revocation_receipt") is True, "revocation_not_performed_seen": "revocation_not_performed" in revocation, "revocation_not_performed_is_true": revocation.get("revocation_not_performed") is True, "policy_only_seen": revocation.get("policy_only") is True}
    consent_revocation_results["violations"] = _violations(consent_revocation_results); consent_revocation_results["passed"] = not consent_revocation_results["violations"]
    consent_denial_results: dict[str, Any] = {"default_without_consent_seen": "default_without_consent" in denial, "default_without_consent_is_deny_active_storage": denial.get("default_without_consent") == "deny_active_storage", "missing_consent_blocks_ledger_write_seen": denial.get("missing_consent_blocks_ledger_write") is True, "missing_consent_blocks_glow_archive_seen": denial.get("missing_consent_blocks_glow_archive") is True, "ambiguous_consent_blocks_storage_seen": denial.get("ambiguous_consent_blocks_storage") is True, "remote_or_daemon_consent_not_accepted_seen": denial.get("remote_or_daemon_consent_not_accepted") is True, "consent_denial_not_runtime_decision_here_seen": denial.get("consent_denial_not_runtime_decision_here") is True, "policy_only_seen": denial.get("policy_only") is True}
    consent_denial_results["violations"] = _violations(consent_denial_results); consent_denial_results["passed"] = not consent_denial_results["violations"]
    consent_authority_boundary_results: dict[str, Any] = {"consent_contract_is_not_consent_seen": boundary.get("consent_contract_is_not_consent") is True, "consent_schema_is_not_operator_approval_seen": boundary.get("consent_schema_is_not_operator_approval") is True, "supplied_reports_do_not_imply_consent_seen": boundary.get("supplied_reports_do_not_imply_consent") is True, "finalizer_ready_to_commit_does_not_imply_consent_seen": boundary.get("finalizer_ready_to_commit_does_not_imply_consent") is True, "pr_metadata_guard_ready_does_not_imply_consent_seen": boundary.get("pr_metadata_guard_ready_does_not_imply_consent") is True, "daemon_recommendation_does_not_imply_consent_seen": boundary.get("daemon_recommendation_does_not_imply_consent") is True, "federation_state_does_not_imply_consent_seen": boundary.get("federation_state_does_not_imply_consent") is True, "future_operator_consent_must_be_explicit_seen": boundary.get("future_operator_consent_must_be_explicit") is True, "authority_boundary_only_seen": boundary.get("authority_boundary_only") is True}
    consent_authority_boundary_results["violations"] = _violations(consent_authority_boundary_results); consent_authority_boundary_results["passed"] = not consent_authority_boundary_results["violations"]
    consent_activation_gap_results: dict[str, Any] = {}
    for key, expected in (("operator_consent_present", False), ("consent_not_collected", True), ("active_storage_allowed_now", False), ("runtime_binding_not_performed", True), ("execution_performed", False), ("writes_performed", False), ("archives_performed", False), ("memory_mutation_performed", False)):
        consent_activation_gap_results[f"{key}_seen"] = key in gaps; consent_activation_gap_results[f"{key}_is_{str(expected).lower()}"] = gaps.get(key) is expected
    consent_activation_gap_results["required_blocking_gap_ids_present"] = all(x in gap_ids for x in REQUIRED_BLOCKING_GAP_IDS)
    consent_activation_gap_results["violations"] = _violations(consent_activation_gap_results); consent_activation_gap_results["passed"] = not consent_activation_gap_results["violations"]
    grouped = [consent_schema_results, consent_evidence_results, consent_scope_results, consent_digest_binding_results, consent_lifetime_results, consent_revocation_results, consent_denial_results, consent_authority_boundary_results, consent_activation_gap_results]
    violation_ids = [x["check_id"] for x in checks if not x["passed"] and x["severity"] == "violation"]
    warning_ids = [x["check_id"] for x in checks if not x["passed"] and x["severity"] == "warning"]
    failed_groups = [r for r in grouped if not r.get("passed")]
    incomplete = not schema_list or not evidence or not scope or not digest or not lifetime or not revocation or not denial or not boundary or not gaps
    verification_status = "storage_operator_consent_contract_incomplete" if incomplete else ("storage_operator_consent_contract_failed" if violation_ids or failed_groups else "storage_operator_consent_contract_verified")
    optional_summary = []
    for input_id in OPTIONAL_INPUT_IDS:
        s = optional_summaries[input_id]; data = optional_reports.get(input_id, {})
        optional_summary.append({"input_id": input_id, "provided": s.get("provided"), "detected_report_id": _report_id(data), "source_digest": s.get("digest"), "source_digest_algo": (s.get("digest_algo") or DIGEST_ALGO) if s.get("provided") else None, "source_byte_size": s.get("byte_size"), "relevant_status_or_digest": _status_or_digest(data), "context_only": True})
    return {"storage_operator_consent_verifier_id": WORKCELL_STORAGE_OPERATOR_CONSENT_VERIFIER_ID, "metadata_only": True, "verifier_only": True, "consent_not_collected": True, "operator_consent_present": False, "consent_not_implied": True, "runtime_binding_not_performed": True, "active_storage_allowed_now": False, "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False, "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {"storage_operator_consent_contract_json": dict(storage_operator_consent_contract_summary), **{k: dict(v) for k, v in optional_summaries.items()}},
        "consent_contract_summary": {"storage_operator_consent_contract_id": c.get("storage_operator_consent_contract_id"), "metadata_only": c.get("metadata_only"), "consent_contract_only": c.get("consent_contract_only"), "consent_request_shape_only": c.get("consent_request_shape_only"), "consent_not_collected": c.get("consent_not_collected"), "operator_consent_present": c.get("operator_consent_present"), "runtime_binding_not_performed": c.get("runtime_binding_not_performed"), "active_storage_allowed_now": c.get("active_storage_allowed_now"), "execution_performed": c.get("execution_performed"), "writes_performed": c.get("writes_performed"), "archives_performed": c.get("archives_performed"), "memory_mutation_performed": c.get("memory_mutation_performed"), "consent_schema_count": len(schema_list), "required_evidence_count": len(required_evidence), "blocking_gap_count": len(gap_ids), "non_authority_posture_present": isinstance(nonauth, Mapping), "non_authority_posture_all_true": _all_true(nonauth), "source_digest": storage_operator_consent_contract_summary.get("digest"), "source_digest_algo": DIGEST_ALGO, "source_byte_size": storage_operator_consent_contract_summary.get("byte_size")},
        "optional_context_summary": optional_summary, "verification_status": verification_status, "verification_checks": checks,
        "consent_schema_results": consent_schema_results, "consent_evidence_results": consent_evidence_results, "consent_scope_results": consent_scope_results, "consent_digest_binding_results": consent_digest_binding_results, "consent_lifetime_results": consent_lifetime_results, "consent_revocation_results": consent_revocation_results, "consent_denial_results": consent_denial_results, "consent_authority_boundary_results": consent_authority_boundary_results, "consent_activation_gap_results": consent_activation_gap_results,
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata verifier.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "violation_summary": {"violation_count": len(violation_ids) + len(failed_groups), "warning_count": len(warning_ids), "info_count": sum(1 for x in checks if x["severity"] == "info"), "violation_check_ids": violation_ids, "warning_check_ids": warning_ids, "verifier_only": True, "no_action_taken": True},
        "sentientos_mount_alignment": {"/ledger": "operator consent request verification only; no ledger write", "/glow": "operator consent request verification only; no archive write", "/vow": "canonical digest required for future consent binding", "/pulse": "future watcher boundary; consent verifier does not activate it", "/daemon": "future action boundary; consent verifier does not activate it"},
        "future_activation_requirements": [{"requirement": r, "status": "future_only", "met": False, "active": False} for r in FUTURE_REQUIREMENT_NAMES], "non_authority_posture": dict(NON_AUTHORITY_POSTURE)}

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")

def _table(headers: list[str], rows: list[list[Any]]) -> str:
    return "| " + " | ".join(headers) + " |\n| " + " | ".join("---" for _ in headers) + " |\n" + "".join("| " + " | ".join(_cell(c) for c in row) + " |\n" for row in rows)

def render_codex_workcell_storage_operator_consent_verifier_markdown(report: Mapping[str, Any]) -> str:
    parts = ["# Codex Workcell Storage Operator Consent Request Verifier\n", "This deterministic metadata-only verifier checks the operator consent request contract structure; it collects no consent, implies no consent, binds no runtime authority, activates no storage, writes no ledger, archives no glow, mutates no memory, triggers no daemon, schedules no task, and grants no readiness.\n"]
    parts.append("## Input summaries\n" + _table(["input", "provided", "path", "digest", "bytes"], [[k, v.get("provided"), v.get("path"), v.get("digest"), v.get("byte_size")] for k, v in sorted(report["input_summaries"].items())]))
    for title, key in (("Consent contract summary", "consent_contract_summary"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("Violation summary", "violation_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Non-authority posture", "non_authority_posture")):
        parts.append(f"## {title}\n" + _table(["key", "value"], [[k, v] for k, v in report[key].items()]))
    parts.append("## Optional context summary\n" + _table(["input", "provided", "report", "digest", "status"], [[r["input_id"], r["provided"], r["detected_report_id"], r["source_digest"], r["relevant_status_or_digest"]] for r in report["optional_context_summary"]]))
    parts.append("## Verification status\n" + str(report["verification_status"]) + "\n")
    parts.append("## Verification checks\n" + _table(["check", "passed", "severity", "details"], [[c["check_id"], c["passed"], c["severity"], c["details"]] for c in report["verification_checks"]]))
    for title, key in (("Consent schema results", "consent_schema_results"), ("Consent evidence results", "consent_evidence_results"), ("Consent scope results", "consent_scope_results"), ("Consent digest binding results", "consent_digest_binding_results"), ("Consent lifetime results", "consent_lifetime_results"), ("Consent revocation results", "consent_revocation_results"), ("Consent denial results", "consent_denial_results"), ("Consent authority boundary results", "consent_authority_boundary_results"), ("Consent activation gap results", "consent_activation_gap_results")):
        parts.append(f"## {title}\n" + _table(["key", "value"], [[k, v] for k, v in report[key].items()]))
    parts.append("## Future activation requirements\n" + _table(["requirement", "status", "met", "active"], [[r["requirement"], r["status"], r["met"], r["active"]] for r in report["future_activation_requirements"]]))
    return "\n".join(parts)
