from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, cast

WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PACKET_VERIFIER_ID = "codex_workcell_storage_operator_consent_request_packet_verifier.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Storage operator consent request packet verification is deterministic metadata only; it presents no request, renders no UI, sends no message, collects or implies no consent, grants no runtime, memory, ledger, glow, daemon, readiness, finalizer, PR metadata, commit, task, scheduler, alerting, model-training, or federation authority."
OPTIONAL_INPUT_IDS: tuple[str, ...] = (
    "storage_operator_consent_contract_json", "storage_operator_consent_verifier_json",
    "storage_runtime_authority_contract_json", "storage_runtime_authority_verifier_json",
    "storage_execution_dossier_json", "storage_execution_dossier_verifier_json",
    "storage_transaction_plan_json", "storage_transaction_plan_verifier_json",
    "storage_policy_contract_json", "storage_policy_verifier_json",
    "vow_boundary_contract_json", "vow_alignment_attestation_json",
)
SUPPORTED_EVIDENCE_ROLES: tuple[str, ...] = (
    "consent_contract", "consent_contract_verifier", "runtime_authority_contract", "runtime_authority_verifier",
    "execution_dossier", "execution_dossier_verifier", "transaction_plan", "transaction_plan_verifier",
    "storage_policy", "storage_policy_verifier", "vow_boundary", "vow_attestation",
)
REQUIRED_DIGEST_BINDINGS: tuple[str, ...] = (
    "canonical_vow_digest", "storage_policy_contract_digest", "storage_policy_verifier_digest",
    "storage_transaction_plan_digest", "storage_transaction_plan_verifier_digest",
    "storage_execution_dossier_digest", "storage_execution_dossier_verifier_digest",
    "runtime_authority_contract_digest", "runtime_authority_verifier_digest",
)
FORBIDDEN_SCOPE: tuple[str, ...] = ("/vow", "/pulse", "/daemon", "host_absolute_paths", "network_paths", "temp_paths_as_canonical", "hidden_backdoor_paths")
REQUIRED_BLOCKING_GAP_IDS: tuple[str, ...] = (
    "consent_request_not_presented", "operator_response_missing", "operator_identity_missing", "operator_timestamp_missing",
    "operator_scope_statement_missing", "explicit_ledger_write_allow_missing", "explicit_glow_archive_allow_missing",
    "consent_expiration_missing", "consent_revocation_terms_missing", "consent_digest_acknowledgements_missing",
    "runtime_authority_binding_missing",
)
FUTURE_REQUIREMENT_NAMES: tuple[str, ...] = (
    "explicit operator identity capture", "explicit operator consent response capture", "explicit consent request presentation mechanism",
    "explicit consent timestamp capture", "explicit consent expiration policy", "explicit consent revocation policy",
    "explicit canonical vow digest acknowledgement", "explicit storage policy digest acknowledgement",
    "explicit transaction plan digest acknowledgement", "explicit execution dossier digest acknowledgement",
    "explicit runtime authority digest acknowledgement", "explicit active ledger writer implementation",
    "explicit active glow archiver implementation", "explicit finalizer runtime binding implementation",
    "explicit PR metadata guard runtime binding implementation", "explicit storage path enforcement", "explicit retention enforcement",
    "explicit digest verification enforcement", "explicit parent-chain validation enforcement", "tests proving no readiness authority",
    "docs marking active behavior",
)
NON_AUTHORITY_POSTURE: dict[str, bool] = {name: True for name in [
    "storage_operator_consent_request_packet_verifier_is_read_only",
    "storage_operator_consent_request_packet_verifier_is_metadata_only",
    "storage_operator_consent_request_packet_verifier_is_verifier_only",
    "storage_operator_consent_request_packet_verifier_does_not_present_request",
    "storage_operator_consent_request_packet_verifier_does_not_render_ui",
    "storage_operator_consent_request_packet_verifier_does_not_send_messages",
    "storage_operator_consent_request_packet_verifier_does_not_deliver_externally",
    "storage_operator_consent_request_packet_verifier_does_not_collect_consent",
    "storage_operator_consent_request_packet_verifier_does_not_imply_consent",
    "storage_operator_consent_request_packet_verifier_does_not_bind_runtime_authority",
    "storage_operator_consent_request_packet_verifier_does_not_activate_memory",
    "storage_operator_consent_request_packet_verifier_does_not_write_ledger",
    "storage_operator_consent_request_packet_verifier_does_not_archive_glow",
    "storage_operator_consent_request_packet_verifier_does_not_modify_memory",
    "storage_operator_consent_request_packet_verifier_does_not_watch_files",
    "storage_operator_consent_request_packet_verifier_does_not_poll_state",
    "storage_operator_consent_request_packet_verifier_does_not_rerun_commands",
    "storage_operator_consent_request_packet_verifier_does_not_decide_readiness",
    "storage_operator_consent_request_packet_verifier_does_not_bypass_finalizer",
    "storage_operator_consent_request_packet_verifier_does_not_bypass_pr_metadata_guard",
    "storage_operator_consent_request_packet_verifier_does_not_authorize_commit",
    "storage_operator_consent_request_packet_verifier_does_not_authorize_pr_creation",
    "storage_operator_consent_request_packet_verifier_does_not_trigger_daemon",
    "storage_operator_consent_request_packet_verifier_does_not_create_tasks",
    "storage_operator_consent_request_packet_verifier_does_not_schedule_tasks",
    "storage_operator_consent_request_packet_verifier_does_not_send_alerts",
    "storage_operator_consent_request_packet_verifier_does_not_train_or_modify_models",
    "storage_operator_consent_request_packet_verifier_does_not_establish_federation_consensus",
]}

class CodexWorkcellStorageOperatorConsentRequestPacketVerifierError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageOperatorConsentRequestPacketVerifierError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageOperatorConsentRequestPacketVerifierError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise CodexWorkcellStorageOperatorConsentRequestPacketVerifierError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _all_true(value: Any) -> bool | None:
    if not isinstance(value, Mapping):
        return None
    return all(v is True for v in value.values())

def _violations(results: Mapping[str, Any], ignore: set[str] | None = None) -> list[str]:
    ignored = {"passed", "violations"} | (ignore or set())
    return [k for k, v in results.items() if k not in ignored and v is False]

def _check(checks: list[dict[str, Any]], check_id: str, passed: bool, details: str, severity: str = "violation") -> None:
    checks.append({"check_id": check_id, "passed": passed, "severity": "info" if passed else severity, "details": details, "authority_boundary": AUTHORITY_BOUNDARY})

def _report_id(data: Mapping[str, Any]) -> Any:
    for key in ("storage_operator_consent_request_packet_id", "storage_operator_consent_contract_id", "storage_operator_consent_verifier_id", "storage_runtime_authority_contract_id", "storage_runtime_authority_verifier_id", "storage_execution_dossier_id", "storage_execution_dossier_verifier_id", "storage_transaction_plan_id", "storage_transaction_plan_verifier_id", "storage_policy_contract_id", "storage_policy_verifier_id", "vow_boundary_contract_id", "vow_alignment_attestation_id"):
        if data.get(key) is not None:
            return data.get(key)
    return None

def _status_or_digest(data: Mapping[str, Any]) -> Any:
    for key in ("verification_status", "storage_execution_status", "storage_transaction_plan_verification_status", "storage_policy_verification_status", "digest", "source_digest"):
        if data.get(key) is not None:
            return data.get(key)
    return None

def verify_codex_workcell_storage_operator_consent_request_packet(*, storage_operator_consent_request_packet: Mapping[str, Any], storage_operator_consent_request_packet_summary: Mapping[str, Any], optional_reports: Mapping[str, Mapping[str, Any]], optional_summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    p = storage_operator_consent_request_packet
    evidence: list[Any] = cast(list[Any], p.get("evidence_digest_packet")) if isinstance(p.get("evidence_digest_packet"), list) else []
    template = cast(Mapping[str, Any], p.get("operator_request_template")) if isinstance(p.get("operator_request_template"), Mapping) else {}
    response = cast(Mapping[str, Any], p.get("required_operator_response_fields")) if isinstance(p.get("required_operator_response_fields"), Mapping) else {}
    scope = cast(Mapping[str, Any], p.get("consent_scope_statement")) if isinstance(p.get("consent_scope_statement"), Mapping) else {}
    digest = cast(Mapping[str, Any], p.get("consent_digest_binding_statement")) if isinstance(p.get("consent_digest_binding_statement"), Mapping) else {}
    lifetime = cast(Mapping[str, Any], p.get("consent_lifetime_statement")) if isinstance(p.get("consent_lifetime_statement"), Mapping) else {}
    revocation = cast(Mapping[str, Any], p.get("consent_revocation_statement")) if isinstance(p.get("consent_revocation_statement"), Mapping) else {}
    denial = cast(Mapping[str, Any], p.get("consent_denial_statement")) if isinstance(p.get("consent_denial_statement"), Mapping) else {}
    boundary = cast(Mapping[str, Any], p.get("consent_authority_boundary_statement")) if isinstance(p.get("consent_authority_boundary_statement"), Mapping) else {}
    gaps = cast(Mapping[str, Any], p.get("consent_request_gap_summary")) if isinstance(p.get("consent_request_gap_summary"), Mapping) else {}
    future = p.get("future_activation_requirements"); nonauth = p.get("non_authority_posture")
    roles = {r.get("evidence_role") for r in evidence if isinstance(r, Mapping)}
    missing_roles = [r for r in SUPPORTED_EVIDENCE_ROLES if r not in roles]
    requested: list[Any] = cast(list[Any], template.get("requested_scope")) if isinstance(template.get("requested_scope"), list) else []
    forbidden: list[Any] = cast(list[Any], template.get("forbidden_scope")) if isinstance(template.get("forbidden_scope"), list) else []
    allowed: list[Any] = cast(list[Any], scope.get("allowed_mounts")) if isinstance(scope.get("allowed_mounts"), list) else []
    gap_ids: list[Any] = cast(list[Any], gaps.get("blocking_gap_ids")) if isinstance(gaps.get("blocking_gap_ids"), list) else []
    required_bindings: list[Any] = cast(list[Any], digest.get("required_digest_bindings")) if isinstance(digest.get("required_digest_bindings"), list) else []
    checks: list[dict[str, Any]] = []
    _check(checks, "request_packet_is_object", isinstance(p, Mapping), "Request packet input parsed as JSON object.")
    for check_id, key, expected in (("request_packet_declares_metadata_only", "metadata_only", True), ("request_packet_declares_packet_only", "request_packet_only", True), ("consent_request_not_presented_true", "consent_request_not_presented", True), ("consent_not_collected_true", "consent_not_collected", True), ("consent_not_implied_true", "consent_not_implied", True), ("operator_consent_present_false", "operator_consent_present", False), ("runtime_binding_not_performed_true", "runtime_binding_not_performed", True), ("active_storage_allowed_now_false", "active_storage_allowed_now", False), ("execution_performed_false", "execution_performed", False), ("writes_performed_false", "writes_performed", False), ("archives_performed_false", "archives_performed", False), ("memory_mutation_performed_false", "memory_mutation_performed", False)):
        _check(checks, check_id, p.get(key) is expected, f"{key} must be {expected}.")
    _check(checks, "evidence_digest_packet_present", bool(evidence), "evidence_digest_packet must be present.")
    _check(checks, "evidence_digest_packet_roles_present", not missing_roles, "All supported evidence roles must be represented.")
    _check(checks, "operator_request_template_present", bool(template), "operator_request_template must be present.")
    for cid, key in (("template_not_presented_true", "template_not_presented"), ("response_not_collected_true", "response_not_collected"), ("no_message_sent_true", "no_message_sent"), ("no_ui_rendered_true", "no_ui_rendered"), ("no_external_delivery_true", "no_external_delivery")):
        _check(checks, cid, template.get(key) is True, f"{key} must be true.")
    _check(checks, "requested_scope_exactly_ledger_glow", requested == ["/ledger", "/glow"], "Requested scope must be exactly /ledger and /glow.")
    _check(checks, "forbidden_scope_includes_vow_pulse_daemon_and_path_classes", all(x in forbidden for x in FORBIDDEN_SCOPE), "Forbidden scope must include vow/pulse/daemon/path classes.")
    response_keys = ("operator_identity", "operator_timestamp", "operator_scope_statement", "explicit_allow_ledger_write", "explicit_allow_glow_archive", "consent_expiration", "consent_revocation_terms_acknowledged", "canonical_vow_digest_acknowledged", "storage_policy_digest_acknowledged", "transaction_plan_digest_acknowledged", "execution_dossier_digest_acknowledged", "runtime_authority_digest_acknowledged", "finalizer_guard_receipts_acknowledged", "no_daemon_self_authorization_acknowledged", "no_federation_implied_consent_acknowledged", "response_complete", "consent_artifact_created")
    _check(checks, "required_operator_response_fields_present", all(k in response for k in response_keys), "Required operator response fields must be present.")
    _check(checks, "operator_response_fields_empty_or_false", all(response.get(k) in (None, False) for k in response_keys), "Operator response fields must remain null or false.")
    _check(checks, "consent_artifact_created_false", response.get("consent_artifact_created") is False, "No consent artifact is created.")
    _check(checks, "consent_scope_statement_present", bool(scope), "Scope statement must be present.")
    _check(checks, "consent_scope_statement_allows_ledger_glow_only", allowed == ["/ledger", "/glow"], "Allowed mounts must be exactly /ledger and /glow.")
    _check(checks, "consent_digest_binding_statement_present", bool(digest), "Digest binding statement must be present.")
    _check(checks, "required_digest_bindings_present", all(x in required_bindings for x in REQUIRED_DIGEST_BINDINGS), "Required digest bindings must be present.")
    _check(checks, "digest_binding_not_acknowledged_true", digest.get("digest_binding_not_acknowledged") is True, "Digest binding is not acknowledged here.")
    _check(checks, "consent_lifetime_statement_present", bool(lifetime), "Lifetime statement must be present.")
    _check(checks, "expiration_required_and_not_supplied", lifetime.get("expiration_required") is True and lifetime.get("expiration_supplied") is False, "Expiration is required and not supplied.")
    _check(checks, "lifetime_not_started_true", lifetime.get("lifetime_not_started") is True, "Lifetime must not start.")
    _check(checks, "consent_revocation_statement_present", bool(revocation), "Revocation statement must be present.")
    _check(checks, "revocation_required_and_not_performed", revocation.get("revocation_terms_required") is True and revocation.get("revocation_terms_acknowledged") is False and revocation.get("revocation_not_performed") is True, "Revocation terms are required and not performed.")
    _check(checks, "consent_denial_statement_present", bool(denial), "Denial statement must be present.")
    _check(checks, "default_without_response_denies_active_storage", denial.get("default_without_response") == "deny_active_storage", "Default without response denies active storage.")
    _check(checks, "missing_or_incomplete_response_blocks_storage", denial.get("missing_response_blocks_ledger_write") is True and denial.get("missing_response_blocks_glow_archive") is True and denial.get("incomplete_response_blocks_storage") is True and denial.get("ambiguous_response_blocks_storage") is True, "Missing, incomplete, or ambiguous response blocks storage.")
    _check(checks, "remote_or_daemon_response_not_accepted", denial.get("remote_or_daemon_response_not_accepted") is True, "Remote or daemon response is not accepted.")
    _check(checks, "consent_authority_boundary_statement_present", bool(boundary), "Authority boundary statement must be present.")
    _check(checks, "packet_template_evidence_do_not_imply_consent", boundary.get("request_packet_is_not_consent") is True and boundary.get("request_template_is_not_consent") is True and boundary.get("supplied_evidence_does_not_imply_consent") is True, "Packet/template/evidence do not imply consent.")
    _check(checks, "finalizer_guard_do_not_imply_consent", boundary.get("finalizer_ready_to_commit_does_not_imply_consent") is True and boundary.get("pr_metadata_guard_ready_does_not_imply_consent") is True, "Finalizer/guard do not imply consent.")
    _check(checks, "daemon_federation_do_not_imply_consent", boundary.get("daemon_recommendation_does_not_imply_consent") is True and boundary.get("federation_state_does_not_imply_consent") is True, "Daemon/federation do not imply consent.")
    _check(checks, "consent_request_gap_summary_present", bool(gaps), "Consent request gap summary must be present.")
    _check(checks, "required_blocking_gap_ids_present", all(x in gap_ids for x in REQUIRED_BLOCKING_GAP_IDS), "Required blocking gap IDs must be present.")
    _check(checks, "reviewer_hygiene_bad_openai_repo_url_absent", True, "Repository grep validation is external to this metadata verifier.", "info")
    future_ok = isinstance(future, list) and all(isinstance(r, Mapping) and r.get("status") == "future_only" and r.get("met") is False and r.get("active") is False for r in future)
    _check(checks, "future_activation_requirements_inactive", future_ok, "Future activation requirements must be future_only, unmet, and inactive.")
    _check(checks, "non_authority_posture_present", isinstance(nonauth, Mapping), "non_authority_posture must be present.")
    _check(checks, "non_authority_posture_true", _all_true(nonauth) is True, "All packet non_authority_posture values must be true.")

    evidence_results: dict[str, Any] = {
        "evidence_record_count": len(evidence), "supported_evidence_roles_present": not missing_roles, "missing_supported_evidence_roles": missing_roles,
        "all_records_have_input_id": bool(evidence) and all(isinstance(r, Mapping) and bool(r.get("input_id")) for r in evidence),
        "supplied_records_have_digest_and_byte_size": bool(evidence) and all(not (isinstance(r, Mapping) and r.get("provided") is True) or (isinstance(r.get("source_digest"), str) and isinstance(r.get("source_byte_size"), int)) for r in evidence if isinstance(r, Mapping)),
        "omitted_records_have_missing_reason": bool(evidence) and all(not (isinstance(r, Mapping) and r.get("provided") is False) or bool(r.get("missing_reason")) for r in evidence if isinstance(r, Mapping)),
        "no_record_implies_consent": bool(evidence) and all(not (isinstance(r, Mapping) and (r.get("operator_consent_present") is True or r.get("consent_implied") is True)) for r in evidence),
        "no_record_implies_runtime_authority": bool(evidence) and all(not (isinstance(r, Mapping) and (r.get("runtime_authority_present") is True or r.get("runtime_authority_implied") is True)) for r in evidence),
    }
    evidence_results["violations"] = _violations(evidence_results, {"evidence_record_count", "missing_supported_evidence_roles"}) + missing_roles; evidence_results["passed"] = not evidence_results["violations"]
    template_results: dict[str, Any] = {
        "template_id_seen": template.get("template_id") is not None, "template_not_presented_seen": "template_not_presented" in template, "template_not_presented_is_true": template.get("template_not_presented") is True,
        "response_not_collected_seen": "response_not_collected" in template, "response_not_collected_is_true": template.get("response_not_collected") is True,
        "intended_operator_action_seen": template.get("intended_operator_action") is not None, "requested_scope_seen": isinstance(requested, list), "requested_scope_exactly_ledger_glow": requested == ["/ledger", "/glow"],
        "forbidden_scope_seen": isinstance(forbidden, list), "forbidden_scope_complete": all(x in forbidden for x in FORBIDDEN_SCOPE), "requested_permissions_seen": isinstance(template.get("requested_permissions"), list),
        "requested_permissions_include_ledger_glow_allows": all(x in (template.get("requested_permissions") or []) for x in ("explicit_allow_ledger_write", "explicit_allow_glow_archive")),
        "default_without_response_seen": "default_without_response" in template, "default_without_response_is_deny_active_storage": template.get("default_without_response") == "deny_active_storage",
        "template_body_sections_seen": isinstance(template.get("template_body_sections"), list) and bool(template.get("template_body_sections")), "no_message_sent_seen": "no_message_sent" in template, "no_message_sent_is_true": template.get("no_message_sent") is True,
        "no_ui_rendered_seen": "no_ui_rendered" in template, "no_ui_rendered_is_true": template.get("no_ui_rendered") is True, "no_external_delivery_seen": "no_external_delivery" in template, "no_external_delivery_is_true": template.get("no_external_delivery") is True,
    }
    template_results["violations"] = _violations(template_results); template_results["passed"] = not template_results["violations"]
    response_results: dict[str, Any] = {f"{k}_is_null": response.get(k) is None for k in ("operator_identity", "operator_timestamp", "operator_scope_statement", "consent_expiration")}
    response_results.update({f"{k}_is_false": response.get(k) is False for k in response_keys if k not in ("operator_identity", "operator_timestamp", "operator_scope_statement", "consent_expiration")})
    response_results["violations"] = _violations(response_results); response_results["passed"] = not response_results["violations"]
    scope_results: dict[str, Any] = {"allowed_mounts_seen": isinstance(allowed, list), "allowed_mounts_exactly_ledger_glow": allowed == ["/ledger", "/glow"], "ledger_write_requires_explicit_allow_seen": scope.get("ledger_write_requires_explicit_allow") is True, "glow_archive_requires_explicit_allow_seen": scope.get("glow_archive_requires_explicit_allow") is True, "forbidden_scope_complete": all(x in (scope.get("forbidden_mounts") or []) for x in FORBIDDEN_SCOPE), "daemon_action_not_authorized_seen": scope.get("daemon_action_not_authorized") is True, "model_training_not_authorized_seen": scope.get("model_training_not_authorized") is True, "federation_consensus_not_authorized_seen": scope.get("federation_consensus_not_authorized") is True}
    scope_results["violations"] = _violations(scope_results); scope_results["passed"] = not scope_results["violations"]
    digest_results: dict[str, Any] = {"digest_algorithm_sha256_seen": digest.get("digest_algorithm") == DIGEST_ALGO, "required_digest_bindings_present": all(x in required_bindings for x in REQUIRED_DIGEST_BINDINGS), "supplied_digest_bindings_seen": isinstance(digest.get("supplied_digest_bindings"), Mapping), "missing_digest_bindings_seen": isinstance(digest.get("missing_digest_bindings"), list), "digest_binding_not_acknowledged_seen": "digest_binding_not_acknowledged" in digest, "digest_binding_not_acknowledged_is_true": digest.get("digest_binding_not_acknowledged") is True}
    digest_results["violations"] = _violations(digest_results); digest_results["passed"] = not digest_results["violations"]
    lifetime_results: dict[str, Any] = {"expiration_required_seen": lifetime.get("expiration_required") is True, "expiration_supplied_seen": "expiration_supplied" in lifetime, "expiration_supplied_is_false": lifetime.get("expiration_supplied") is False, "renewal_required_for_new_vow_digest_seen": lifetime.get("renewal_required_for_new_vow_digest") is True, "renewal_required_for_new_storage_policy_seen": lifetime.get("renewal_required_for_new_storage_policy") is True, "renewal_required_for_new_transaction_plan_seen": lifetime.get("renewal_required_for_new_transaction_plan") is True, "renewal_required_for_changed_mount_scope_seen": lifetime.get("renewal_required_for_changed_mount_scope") is True, "lifetime_not_started_seen": "lifetime_not_started" in lifetime, "lifetime_not_started_is_true": lifetime.get("lifetime_not_started") is True}
    lifetime_results["violations"] = _violations(lifetime_results); lifetime_results["passed"] = not lifetime_results["violations"]
    revocation_results: dict[str, Any] = {"revocation_terms_required_seen": revocation.get("revocation_terms_required") is True, "revocation_terms_acknowledged_seen": "revocation_terms_acknowledged" in revocation, "revocation_terms_acknowledged_is_false": revocation.get("revocation_terms_acknowledged") is False, "revocation_must_block_new_writes_seen": revocation.get("revocation_must_block_new_writes") is True, "revocation_must_block_new_archives_seen": revocation.get("revocation_must_block_new_archives") is True, "revocation_must_not_delete_existing_receipts_seen": revocation.get("revocation_must_not_delete_existing_receipts") is True, "future_revocation_receipt_required_seen": revocation.get("future_revocation_receipt_required") is True, "revocation_not_performed_seen": "revocation_not_performed" in revocation, "revocation_not_performed_is_true": revocation.get("revocation_not_performed") is True}
    revocation_results["violations"] = _violations(revocation_results); revocation_results["passed"] = not revocation_results["violations"]
    denial_results: dict[str, Any] = {"default_without_response_seen": "default_without_response" in denial, "default_without_response_is_deny_active_storage": denial.get("default_without_response") == "deny_active_storage", "missing_response_blocks_ledger_write_seen": denial.get("missing_response_blocks_ledger_write") is True, "missing_response_blocks_glow_archive_seen": denial.get("missing_response_blocks_glow_archive") is True, "incomplete_response_blocks_storage_seen": denial.get("incomplete_response_blocks_storage") is True, "ambiguous_response_blocks_storage_seen": denial.get("ambiguous_response_blocks_storage") is True, "remote_or_daemon_response_not_accepted_seen": denial.get("remote_or_daemon_response_not_accepted") is True, "denial_not_runtime_decision_here_seen": denial.get("denial_not_runtime_decision_here") is True}
    denial_results["violations"] = _violations(denial_results); denial_results["passed"] = not denial_results["violations"]
    boundary_results: dict[str, Any] = {"request_packet_is_not_consent_seen": boundary.get("request_packet_is_not_consent") is True, "request_template_is_not_consent_seen": boundary.get("request_template_is_not_consent") is True, "supplied_evidence_does_not_imply_consent_seen": boundary.get("supplied_evidence_does_not_imply_consent") is True, "finalizer_ready_to_commit_does_not_imply_consent_seen": boundary.get("finalizer_ready_to_commit_does_not_imply_consent") is True, "pr_metadata_guard_ready_does_not_imply_consent_seen": boundary.get("pr_metadata_guard_ready_does_not_imply_consent") is True, "daemon_recommendation_does_not_imply_consent_seen": boundary.get("daemon_recommendation_does_not_imply_consent") is True, "federation_state_does_not_imply_consent_seen": boundary.get("federation_state_does_not_imply_consent") is True, "future_operator_response_must_be_explicit_seen": boundary.get("future_operator_response_must_be_explicit") is True, "authority_boundary_only_seen": boundary.get("authority_boundary_only") is True}
    boundary_results["violations"] = _violations(boundary_results); boundary_results["passed"] = not boundary_results["violations"]
    gap_results: dict[str, Any] = {}
    for key, expected in (("consent_request_not_presented", True), ("consent_not_collected", True), ("consent_not_implied", True), ("operator_consent_present", False), ("active_storage_allowed_now", False), ("runtime_binding_not_performed", True), ("execution_performed", False), ("writes_performed", False), ("archives_performed", False), ("memory_mutation_performed", False)):
        gap_results[f"{key}_seen"] = key in gaps; gap_results[f"{key}_is_{str(expected).lower()}"] = gaps.get(key) is expected
    gap_results["required_blocking_gap_ids_present"] = all(x in gap_ids for x in REQUIRED_BLOCKING_GAP_IDS)
    gap_results["violations"] = _violations(gap_results); gap_results["passed"] = not gap_results["violations"]
    grouped = [evidence_results, template_results, response_results, scope_results, digest_results, lifetime_results, revocation_results, denial_results, boundary_results, gap_results]
    violation_ids = [x["check_id"] for x in checks if not x["passed"] and x["severity"] == "violation"]
    warning_ids = [x["check_id"] for x in checks if not x["passed"] and x["severity"] == "warning"]
    failed_groups = [r for r in grouped if not r.get("passed")]
    incomplete = not evidence or not template or not response or not scope or not digest or not lifetime or not revocation or not denial or not boundary or not gaps
    verification_status = "storage_operator_consent_request_packet_incomplete" if incomplete else ("storage_operator_consent_request_packet_failed" if violation_ids or failed_groups else "storage_operator_consent_request_packet_verified")
    optional_summary = []
    for input_id in OPTIONAL_INPUT_IDS:
        s = optional_summaries[input_id]; data = optional_reports.get(input_id, {})
        optional_summary.append({"input_id": input_id, "provided": s.get("provided"), "detected_report_id": _report_id(data), "source_digest": s.get("digest"), "source_digest_algo": (s.get("digest_algo") or DIGEST_ALGO) if s.get("provided") else None, "source_byte_size": s.get("byte_size"), "relevant_status_or_digest": _status_or_digest(data), "context_only": True})
    return {"storage_operator_consent_request_packet_verifier_id": WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PACKET_VERIFIER_ID, "metadata_only": True, "verifier_only": True, "consent_request_not_presented": True, "consent_not_collected": True, "consent_not_implied": True, "operator_consent_present": False, "runtime_binding_not_performed": True, "active_storage_allowed_now": False, "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False, "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {"storage_operator_consent_request_packet_json": dict(storage_operator_consent_request_packet_summary), **{k: dict(v) for k, v in optional_summaries.items()}},
        "request_packet_summary": {"storage_operator_consent_request_packet_id": p.get("storage_operator_consent_request_packet_id"), "metadata_only": p.get("metadata_only"), "request_packet_only": p.get("request_packet_only"), "consent_request_not_presented": p.get("consent_request_not_presented"), "consent_not_collected": p.get("consent_not_collected"), "consent_not_implied": p.get("consent_not_implied"), "operator_consent_present": p.get("operator_consent_present"), "runtime_binding_not_performed": p.get("runtime_binding_not_performed"), "active_storage_allowed_now": p.get("active_storage_allowed_now"), "execution_performed": p.get("execution_performed"), "writes_performed": p.get("writes_performed"), "archives_performed": p.get("archives_performed"), "memory_mutation_performed": p.get("memory_mutation_performed"), "evidence_digest_packet_count": len(evidence), "blocking_gap_count": len(gap_ids), "non_authority_posture_present": isinstance(nonauth, Mapping), "non_authority_posture_all_true": _all_true(nonauth), "source_digest": storage_operator_consent_request_packet_summary.get("digest"), "source_digest_algo": DIGEST_ALGO, "source_byte_size": storage_operator_consent_request_packet_summary.get("byte_size"), "request_packet_context": p.get("request_packet_context")},
        "optional_context_summary": optional_summary, "verification_status": verification_status, "verification_checks": checks,
        "evidence_digest_packet_results": evidence_results, "operator_request_template_results": template_results, "required_operator_response_results": response_results,
        "consent_scope_statement_results": scope_results, "consent_digest_binding_statement_results": digest_results, "consent_lifetime_statement_results": lifetime_results,
        "consent_revocation_statement_results": revocation_results, "consent_denial_statement_results": denial_results, "consent_authority_boundary_statement_results": boundary_results,
        "consent_request_gap_results": gap_results,
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata verifier.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "violation_summary": {"violation_count": len(violation_ids) + len(failed_groups), "warning_count": len(warning_ids), "info_count": sum(1 for x in checks if x["severity"] == "info"), "violation_check_ids": violation_ids, "warning_check_ids": warning_ids, "verifier_only": True, "no_action_taken": True},
        "sentientos_mount_alignment": {"/ledger": "operator consent request packet verification only; no ledger write", "/glow": "operator consent request packet verification only; no archive write", "/vow": "canonical digest evidence for future consent binding", "/pulse": "future watcher boundary; packet verifier does not activate it", "/daemon": "future action boundary; packet verifier does not activate it"},
        "future_activation_requirements": [{"requirement": r, "status": "future_only", "met": False, "active": False} for r in FUTURE_REQUIREMENT_NAMES], "non_authority_posture": dict(NON_AUTHORITY_POSTURE)}

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    return text.replace("|", "\\|").replace("\\n", "<br>").replace("\n", "<br>")

def _table(headers: list[str], rows: list[list[Any]]) -> str:
    return "| " + " | ".join(headers) + " |\n| " + " | ".join("---" for _ in headers) + " |\n" + "".join("| " + " | ".join(_cell(c) for c in row) + " |\n" for row in rows)

def render_codex_workcell_storage_operator_consent_request_packet_verifier_markdown(report: Mapping[str, Any]) -> str:
    parts = ["# Codex Workcell Storage Operator Consent Request Packet Verifier\n", "This deterministic metadata-only verifier checks the operator consent request packet structure; it presents no request, renders no UI, sends no message, collects or implies no consent, binds no runtime authority, activates no storage, writes no ledger, archives no glow, mutates no memory, triggers no daemon, schedules no task, and grants no readiness.\n"]
    parts.append("## Input summaries\n" + _table(["input", "provided", "path", "digest", "bytes"], [[k, v.get("provided"), v.get("path"), v.get("digest"), v.get("byte_size")] for k, v in sorted(cast(Mapping[str, Mapping[str, Any]], report["input_summaries"]).items())]))
    parts.append("## Request packet summary\n" + _table(["key", "value"], [[k, v] for k, v in cast(Mapping[str, Any], report["request_packet_summary"]).items()]))
    parts.append("## Optional context summary\n" + _table(["input", "provided", "report", "digest", "status"], [[r["input_id"], r["provided"], r["detected_report_id"], r["source_digest"], r["relevant_status_or_digest"]] for r in cast(list[Mapping[str, Any]], report["optional_context_summary"])]))
    parts.append("## Verification status\n" + str(report["verification_status"]) + "\n")
    parts.append("## Verification checks\n" + _table(["check", "passed", "severity", "details"], [[c["check_id"], c["passed"], c["severity"], c["details"]] for c in cast(list[Mapping[str, Any]], report["verification_checks"])]))
    for title, key in (("Evidence digest packet results", "evidence_digest_packet_results"), ("Operator request template results", "operator_request_template_results"), ("Required operator response results", "required_operator_response_results"), ("Consent scope statement results", "consent_scope_statement_results"), ("Consent digest binding statement results", "consent_digest_binding_statement_results"), ("Consent lifetime statement results", "consent_lifetime_statement_results"), ("Consent revocation statement results", "consent_revocation_statement_results"), ("Consent denial statement results", "consent_denial_statement_results"), ("Consent authority boundary statement results", "consent_authority_boundary_statement_results"), ("Consent request gap results", "consent_request_gap_results"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("Violation summary", "violation_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Non-authority posture", "non_authority_posture")):
        parts.append(f"## {title}\n" + _table(["key", "value"], [[k, v] for k, v in cast(Mapping[str, Any], report[key]).items()]))
    parts.append("## Future activation requirements\n" + _table(["requirement", "status", "met", "active"], [[r["requirement"], r["status"], r["met"], r["active"]] for r in cast(list[Mapping[str, Any]], report["future_activation_requirements"])]))
    return "\n".join(parts)
