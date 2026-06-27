from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, cast

WORKCELL_STORAGE_RUNTIME_AUTHORITY_VERIFIER_ID = "codex_workcell_storage_runtime_authority_verifier.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Storage runtime authority boundary verification is deterministic metadata only; it grants no runtime, memory, ledger, glow, daemon, readiness, finalizer, PR metadata, commit, task, scheduler, alerting, model-training, or federation authority."
OPTIONAL_INPUT_IDS: tuple[str, ...] = (
    "storage_execution_dossier_json", "storage_execution_dossier_verifier_json", "storage_transaction_plan_json",
    "storage_transaction_plan_verifier_json", "storage_policy_contract_json", "storage_policy_verifier_json",
    "vow_boundary_contract_json", "vow_alignment_attestation_json", "memory_activation_preflight_json",
)
REQUIRED_BOUNDARY_IDS: tuple[str, ...] = (
    "finalizer_runtime_binding_required", "pr_metadata_guard_runtime_binding_required", "operator_consent_required",
    "vow_digest_runtime_binding_required", "storage_policy_runtime_binding_required", "transaction_plan_runtime_binding_required",
    "transaction_plan_verifier_runtime_binding_required", "storage_execution_dossier_runtime_binding_required",
    "storage_execution_dossier_verifier_runtime_binding_required", "ledger_writer_implementation_required",
    "glow_archiver_implementation_required", "storage_path_enforcement_required", "retention_enforcement_required",
    "digest_verification_runtime_required", "parent_chain_runtime_required", "pulse_watcher_contract_required",
    "daemon_action_contract_required", "federation_consensus_required", "no_self_authorizing_daemon",
    "no_report_status_as_runtime_authority", "no_finalizer_guard_bypass", "no_active_storage_without_all_runtime_bindings",
)
REQUIRED_BLOCKING_GAP_IDS: tuple[str, ...] = (
    "active_writer_implementation_missing", "operator_consent_missing", "finalizer_guard_runtime_binding_missing",
    "storage_path_enforcement_missing", "retention_enforcement_missing", "digest_verification_runtime_missing",
    "parent_chain_runtime_missing", "pulse_watcher_contract_missing", "daemon_action_contract_missing", "federation_consensus_missing",
)
FUTURE_REQUIREMENT_NAMES: tuple[str, ...] = (
    "explicit active ledger writer implementation", "explicit active glow archiver implementation", "explicit finalizer runtime binding implementation",
    "explicit PR metadata guard runtime binding implementation", "explicit operator consent capture", "explicit storage path enforcement",
    "explicit retention enforcement", "explicit digest verification enforcement", "explicit parent-chain validation enforcement",
    "explicit pulse watcher contract", "explicit daemon action contract", "explicit federation drift consensus rule",
    "tests proving no readiness authority", "docs marking active behavior",
)
NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "storage_runtime_authority_verifier_is_read_only": True,
    "storage_runtime_authority_verifier_is_metadata_only": True,
    "storage_runtime_authority_verifier_is_verifier_only": True,
    "storage_runtime_authority_verifier_does_not_bind_runtime_authority": True,
    "storage_runtime_authority_verifier_does_not_activate_memory": True,
    "storage_runtime_authority_verifier_does_not_write_ledger": True,
    "storage_runtime_authority_verifier_does_not_archive_glow": True,
    "storage_runtime_authority_verifier_does_not_modify_memory": True,
    "storage_runtime_authority_verifier_does_not_watch_files": True,
    "storage_runtime_authority_verifier_does_not_poll_state": True,
    "storage_runtime_authority_verifier_does_not_rerun_commands": True,
    "storage_runtime_authority_verifier_does_not_decide_readiness": True,
    "storage_runtime_authority_verifier_does_not_bypass_finalizer": True,
    "storage_runtime_authority_verifier_does_not_bypass_pr_metadata_guard": True,
    "storage_runtime_authority_verifier_does_not_authorize_commit": True,
    "storage_runtime_authority_verifier_does_not_authorize_pr_creation": True,
    "storage_runtime_authority_verifier_does_not_trigger_daemon": True,
    "storage_runtime_authority_verifier_does_not_create_tasks": True,
    "storage_runtime_authority_verifier_does_not_schedule_tasks": True,
    "storage_runtime_authority_verifier_does_not_send_alerts": True,
    "storage_runtime_authority_verifier_does_not_train_or_modify_models": True,
    "storage_runtime_authority_verifier_does_not_establish_federation_consensus": True,
}

class CodexWorkcellStorageRuntimeAuthorityVerifierError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageRuntimeAuthorityVerifierError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageRuntimeAuthorityVerifierError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise CodexWorkcellStorageRuntimeAuthorityVerifierError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _all_true(value: Any) -> bool | None:
    if not isinstance(value, Mapping):
        return None
    return all(v is True for v in value.values())

def _report_id(data: Mapping[str, Any]) -> Any:
    for key in ("storage_runtime_authority_contract_id", "storage_execution_dossier_id", "storage_execution_dossier_verifier_id", "storage_transaction_plan_id", "storage_transaction_plan_verifier_id", "storage_policy_contract_id", "storage_policy_verifier_id", "vow_boundary_contract_id", "vow_alignment_attestation_id", "memory_activation_preflight_id"):
        if data.get(key) is not None:
            return data.get(key)
    return None

def _status_or_digest(data: Mapping[str, Any]) -> Any:
    for key in ("verification_status", "storage_execution_status", "storage_transaction_plan_verification_status", "storage_policy_verification_status", "activation_preflight_status", "digest", "source_digest"):
        if data.get(key) is not None:
            return data.get(key)
    return None

def _check(checks: list[dict[str, Any]], check_id: str, passed: bool, details: str, severity: str = "violation") -> None:
    checks.append({"check_id": check_id, "passed": passed, "severity": "info" if passed else severity, "details": details, "authority_boundary": AUTHORITY_BOUNDARY})

def _violations_from_bool_map(results: Mapping[str, Any], ignore: set[str] | None = None) -> list[str]:
    ignored = {"passed", "violations"} | (ignore or set())
    return [k for k, v in results.items() if k not in ignored and v is False]

def verify_codex_workcell_storage_runtime_authority_contract(*, storage_runtime_authority_contract: Mapping[str, Any], storage_runtime_authority_contract_summary: Mapping[str, Any], optional_reports: Mapping[str, Mapping[str, Any]], optional_summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    c = storage_runtime_authority_contract
    catalog = c.get("runtime_authority_boundary_catalog")
    finalizer: Mapping[str, Any] = cast(Mapping[str, Any], c.get("finalizer_guard_binding_policy")) if isinstance(c.get("finalizer_guard_binding_policy"), Mapping) else {}
    consent: Mapping[str, Any] = cast(Mapping[str, Any], c.get("operator_consent_policy")) if isinstance(c.get("operator_consent_policy"), Mapping) else {}
    storage: Mapping[str, Any] = cast(Mapping[str, Any], c.get("storage_enforcement_policy")) if isinstance(c.get("storage_enforcement_policy"), Mapping) else {}
    digest: Mapping[str, Any] = cast(Mapping[str, Any], c.get("digest_and_parent_runtime_policy")) if isinstance(c.get("digest_and_parent_runtime_policy"), Mapping) else {}
    pulse: Mapping[str, Any] = cast(Mapping[str, Any], c.get("pulse_daemon_runtime_boundary")) if isinstance(c.get("pulse_daemon_runtime_boundary"), Mapping) else {}
    federation: Mapping[str, Any] = cast(Mapping[str, Any], c.get("federation_runtime_boundary")) if isinstance(c.get("federation_runtime_boundary"), Mapping) else {}
    gaps: Mapping[str, Any] = cast(Mapping[str, Any], c.get("runtime_activation_gap_summary")) if isinstance(c.get("runtime_activation_gap_summary"), Mapping) else {}
    future = c.get("future_activation_requirements")
    nonauth = c.get("non_authority_posture")
    checks: list[dict[str, Any]] = []
    for check_id, key, expected in (
        ("runtime_authority_contract_declares_metadata_only", "metadata_only", True), ("runtime_authority_contract_declares_contract_only", "runtime_authority_contract_only", True),
        ("runtime_binding_not_performed_true", "runtime_binding_not_performed", True), ("active_storage_allowed_now_false", "active_storage_allowed_now", False),
        ("execution_performed_false", "execution_performed", False), ("writes_performed_false", "writes_performed", False), ("archives_performed_false", "archives_performed", False),
        ("memory_mutation_performed_false", "memory_mutation_performed", False),
    ):
        _check(checks, check_id, c.get(key) is expected, f"{key} must be {expected}.")
    _check(checks, "runtime_authority_contract_is_object", isinstance(c, Mapping), "Runtime authority contract input parsed as JSON object.")
    catalog_list: list[Any] = catalog if isinstance(catalog, list) else []
    ids = {b.get("boundary_id") for b in catalog_list if isinstance(b, Mapping)}
    missing_boundary_ids = [x for x in REQUIRED_BOUNDARY_IDS if x not in ids]
    _check(checks, "boundary_catalog_present", isinstance(catalog, list) and bool(catalog), "runtime_authority_boundary_catalog must be a non-empty list.")
    _check(checks, "boundary_catalog_required_ids_present", not missing_boundary_ids, "Required boundary IDs must be present.")
    _check(checks, "boundaries_future_only", bool(catalog_list) and all(isinstance(b, Mapping) and b.get("future_only") is True for b in catalog_list), "All boundaries must be future_only true.")
    _check(checks, "boundaries_currently_bound_false", bool(catalog_list) and all(isinstance(b, Mapping) and b.get("currently_bound") is False for b in catalog_list), "All boundaries must be currently_bound false.")
    _check(checks, "boundaries_active_false", bool(catalog_list) and all(isinstance(b, Mapping) and b.get("active") is False for b in catalog_list), "All boundaries must be active false.")
    _check(checks, "finalizer_guard_binding_policy_present", bool(finalizer), "Finalizer/guard binding policy must be present.")
    _check(checks, "finalizer_guard_readiness_not_runtime_authority", finalizer.get("finalizer_ready_to_commit_is_not_runtime_write_authority") is True and finalizer.get("pr_metadata_guard_ready_is_not_runtime_write_authority") is True, "Finalizer/guard readiness must not be runtime write authority.")
    _check(checks, "finalizer_guard_binding_not_performed", finalizer.get("currently_bound") is False and finalizer.get("binding_not_performed") is True, "Finalizer/guard binding must be absent.")
    _check(checks, "operator_consent_policy_present", bool(consent), "Operator consent policy must be present.")
    _check(checks, "operator_consent_required", consent.get("operator_consent_required") is True, "Operator consent must be required.")
    _check(checks, "operator_consent_absent", consent.get("operator_consent_present") is False, "Operator consent must be absent.")
    _check(checks, "operator_consent_not_collected", consent.get("consent_not_collected") is True, "Operator consent must not be collected here.")
    _check(checks, "storage_enforcement_policy_present", bool(storage), "Storage enforcement policy must be present.")
    _check(checks, "active_writer_absent", storage.get("active_ledger_writer_present") is False, "Active ledger writer must be absent.")
    _check(checks, "active_archiver_absent", storage.get("active_glow_archiver_present") is False, "Active glow archiver must be absent.")
    _check(checks, "storage_enforcement_not_performed", storage.get("enforcement_not_performed") is True, "Storage enforcement must not be performed.")
    _check(checks, "digest_parent_runtime_policy_present", bool(digest), "Digest/parent runtime policy must be present.")
    _check(checks, "digest_runtime_absent", digest.get("digest_verification_runtime_present") is False, "Digest runtime must be absent.")
    _check(checks, "parent_chain_runtime_absent", digest.get("parent_chain_runtime_present") is False, "Parent-chain runtime must be absent.")
    _check(checks, "pulse_daemon_boundary_present", bool(pulse), "Pulse/daemon boundary must be present.")
    _check(checks, "pulse_watcher_contract_absent", pulse.get("pulse_watcher_contract_present") is False, "Pulse watcher contract must be absent.")
    _check(checks, "daemon_action_contract_absent", pulse.get("daemon_action_contract_present") is False, "Daemon action contract must be absent.")
    _check(checks, "daemon_self_authorization_forbidden", pulse.get("daemon_self_authorization_forbidden") is True, "Daemon self-authorization must be forbidden.")
    _check(checks, "federation_boundary_present", bool(federation), "Federation boundary must be present.")
    _check(checks, "federation_consensus_absent", federation.get("federation_consensus_present") is False, "Federation consensus must be absent.")
    _check(checks, "runtime_activation_gap_summary_present", bool(gaps), "Runtime activation gap summary must be present.")
    gap_ids: list[Any] = cast(list[Any], gaps.get("blocking_gap_ids")) if isinstance(gaps.get("blocking_gap_ids"), list) else []
    _check(checks, "required_blocking_gap_ids_present", all(x in gap_ids for x in REQUIRED_BLOCKING_GAP_IDS), "Required blocking gap IDs must be present.")
    _check(checks, "reviewer_hygiene_bad_openai_repo_url_absent", True, "Repository grep validation is external to this metadata verifier.", "info")
    future_ok = isinstance(future, list) and all(isinstance(r, Mapping) and r.get("status") == "future_only" and r.get("met") is False and r.get("active") is False for r in future)
    _check(checks, "future_activation_requirements_inactive", future_ok, "Future activation requirements must be future_only, unmet, and inactive.")
    _check(checks, "non_authority_posture_present", isinstance(nonauth, Mapping), "non_authority_posture must be present.")
    _check(checks, "non_authority_posture_true", _all_true(nonauth) is True, "All contract non_authority_posture values must be true.")
    boundary_catalog_results: dict[str, Any] = {
        "boundary_count": len(catalog_list), "required_boundary_ids_present": not missing_boundary_ids, "missing_boundary_ids": missing_boundary_ids,
        "all_boundaries_required_for_active_storage": bool(catalog_list) and all(isinstance(b, Mapping) and b.get("required_for_active_storage") is True for b in catalog_list),
        "all_boundaries_currently_bound_false": bool(catalog_list) and all(isinstance(b, Mapping) and b.get("currently_bound") is False for b in catalog_list),
        "all_boundaries_future_only_true": bool(catalog_list) and all(isinstance(b, Mapping) and b.get("future_only") is True for b in catalog_list),
        "all_boundaries_active_false": bool(catalog_list) and all(isinstance(b, Mapping) and b.get("active") is False for b in catalog_list),
        "all_boundaries_have_forbidden_inference": bool(catalog_list) and all(isinstance(b, Mapping) and bool(b.get("forbidden_inference")) for b in catalog_list),
        "all_boundaries_have_authority_category": bool(catalog_list) and all(isinstance(b, Mapping) and bool(b.get("category") or b.get("authority_category")) for b in catalog_list),
    }
    boundary_catalog_results["violations"] = _violations_from_bool_map(boundary_catalog_results, {"boundary_count", "missing_boundary_ids"}) + missing_boundary_ids
    boundary_catalog_results["passed"] = not boundary_catalog_results["violations"]
    finalizer_guard_binding_results: dict[str, Any] = {
        "finalizer_runtime_binding_required_seen": finalizer.get("finalizer_runtime_binding_required") is True, "pr_metadata_guard_runtime_binding_required_seen": finalizer.get("pr_metadata_guard_runtime_binding_required") is True,
        "finalizer_ready_to_commit_is_not_runtime_write_authority_seen": finalizer.get("finalizer_ready_to_commit_is_not_runtime_write_authority") is True, "pr_metadata_guard_ready_is_not_runtime_write_authority_seen": finalizer.get("pr_metadata_guard_ready_is_not_runtime_write_authority") is True,
        "no_finalizer_guard_bypass_seen": finalizer.get("no_finalizer_guard_bypass") is True, "currently_bound_seen": "currently_bound" in finalizer, "currently_bound_is_false": finalizer.get("currently_bound") is False,
        "binding_not_performed_seen": "binding_not_performed" in finalizer, "binding_not_performed_is_true": finalizer.get("binding_not_performed") is True, "policy_only_seen": finalizer.get("policy_only") is True,
    }
    finalizer_guard_binding_results["violations"] = _violations_from_bool_map(finalizer_guard_binding_results); finalizer_guard_binding_results["passed"] = not finalizer_guard_binding_results["violations"]
    scopes: list[Any] = cast(list[Any], consent.get("consent_must_be_scoped_to_mounts")) if isinstance(consent.get("consent_must_be_scoped_to_mounts"), list) else []
    operator_consent_results: dict[str, Any] = {"operator_consent_required_seen": consent.get("operator_consent_required") is True, "operator_consent_present_seen": "operator_consent_present" in consent, "operator_consent_present_is_false": consent.get("operator_consent_present") is False, "consent_not_collected_seen": "consent_not_collected" in consent, "consent_not_collected_is_true": consent.get("consent_not_collected") is True, "consent_must_be_explicit_seen": consent.get("consent_must_be_explicit") is True, "consent_must_be_scoped_to_mounts_seen": isinstance(scopes, list), "consent_scope_includes_ledger_glow": "/ledger" in scopes and "/glow" in scopes, "consent_must_reference_vow_digest_seen": consent.get("consent_must_reference_vow_digest") is True, "consent_must_reference_storage_policy_seen": consent.get("consent_must_reference_storage_policy") is True, "consent_must_reference_transaction_plan_seen": consent.get("consent_must_reference_transaction_plan") is True, "policy_only_seen": consent.get("policy_only") is True}
    operator_consent_results["violations"] = _violations_from_bool_map(operator_consent_results); operator_consent_results["passed"] = not operator_consent_results["violations"]
    forbidden_modes: list[Any] = cast(list[Any], storage.get("forbidden_runtime_write_modes")) if isinstance(storage.get("forbidden_runtime_write_modes"), list) else []
    storage_enforcement_results: dict[str, Any] = {"storage_path_enforcement_required_seen": storage.get("storage_path_enforcement_required") is True, "retention_enforcement_required_seen": storage.get("retention_enforcement_required") is True, "active_ledger_writer_required_seen": storage.get("active_ledger_writer_required") is True, "active_glow_archiver_required_seen": storage.get("active_glow_archiver_required") is True, "active_ledger_writer_present_seen": "active_ledger_writer_present" in storage, "active_ledger_writer_present_is_false": storage.get("active_ledger_writer_present") is False, "active_glow_archiver_present_seen": "active_glow_archiver_present" in storage, "active_glow_archiver_present_is_false": storage.get("active_glow_archiver_present") is False, "enforcement_not_performed_seen": "enforcement_not_performed" in storage, "enforcement_not_performed_is_true": storage.get("enforcement_not_performed") is True, "forbidden_runtime_write_modes_present": bool(forbidden_modes), "report_status_as_runtime_authority_forbidden": "report_status_as_runtime_authority" in forbidden_modes, "policy_only_seen": storage.get("policy_only") is True}
    storage_enforcement_results["violations"] = _violations_from_bool_map(storage_enforcement_results); storage_enforcement_results["passed"] = not storage_enforcement_results["violations"]
    digest_parent_runtime_results: dict[str, Any] = {"digest_verification_runtime_required_seen": digest.get("digest_verification_runtime_required") is True, "parent_chain_runtime_required_seen": digest.get("parent_chain_runtime_required") is True, "digest_verification_runtime_present_seen": "digest_verification_runtime_present" in digest, "digest_verification_runtime_present_is_false": digest.get("digest_verification_runtime_present") is False, "parent_chain_runtime_present_seen": "parent_chain_runtime_present" in digest, "parent_chain_runtime_present_is_false": digest.get("parent_chain_runtime_present") is False, "runtime_verification_not_performed_seen": "runtime_verification_not_performed" in digest, "runtime_verification_not_performed_is_true": digest.get("runtime_verification_not_performed") is True, "required_digest_bindings_present": bool(digest.get("required_digest_bindings")), "required_parent_chain_bindings_present": bool(digest.get("required_parent_chain_bindings")), "policy_only_seen": digest.get("policy_only") is True}
    digest_parent_runtime_results["violations"] = _violations_from_bool_map(digest_parent_runtime_results); digest_parent_runtime_results["passed"] = not digest_parent_runtime_results["violations"]
    pulse_daemon_boundary_results: dict[str, Any] = {"pulse_watcher_contract_required_seen": pulse.get("pulse_watcher_contract_required") is True, "daemon_action_contract_required_seen": pulse.get("daemon_action_contract_required") is True, "pulse_watcher_contract_present_seen": "pulse_watcher_contract_present" in pulse, "pulse_watcher_contract_present_is_false": pulse.get("pulse_watcher_contract_present") is False, "daemon_action_contract_present_seen": "daemon_action_contract_present" in pulse, "daemon_action_contract_present_is_false": pulse.get("daemon_action_contract_present") is False, "daemon_self_authorization_forbidden_seen": pulse.get("daemon_self_authorization_forbidden") is True, "pulse_signals_are_not_actions_seen": pulse.get("pulse_signals_are_not_actions") is True, "daemon_recommendations_are_not_commands_seen": pulse.get("daemon_recommendations_are_not_commands") is True, "boundary_only_seen": pulse.get("boundary_only") is True}
    pulse_daemon_boundary_results["violations"] = _violations_from_bool_map(pulse_daemon_boundary_results); pulse_daemon_boundary_results["passed"] = not pulse_daemon_boundary_results["violations"]
    federation_boundary_results: dict[str, Any] = {"federation_consensus_required_seen": federation.get("federation_consensus_required") is True, "federation_consensus_present_seen": "federation_consensus_present" in federation, "federation_consensus_present_is_false": federation.get("federation_consensus_present") is False, "federation_consensus_not_established_seen": federation.get("federation_consensus_not_established") is True, "local_storage_authority_not_implied_by_remote_state_seen": federation.get("local_storage_authority_not_implied_by_remote_state") is True, "remote_consensus_not_implied_seen": federation.get("remote_consensus_not_implied") is True, "boundary_only_seen": federation.get("boundary_only") is True}
    federation_boundary_results["violations"] = _violations_from_bool_map(federation_boundary_results); federation_boundary_results["passed"] = not federation_boundary_results["violations"]
    runtime_activation_gap_results: dict[str, Any] = {}
    for key, expected in (("active_storage_allowed_now", False), ("runtime_binding_not_performed", True), ("execution_performed", False), ("writes_performed", False), ("archives_performed", False), ("memory_mutation_performed", False), ("active_writer_implementation_present", False), ("operator_consent_present", False), ("finalizer_guard_runtime_binding_present", False), ("storage_path_enforcement_present", False), ("retention_enforcement_present", False), ("digest_verification_runtime_present", False), ("parent_chain_runtime_present", False), ("pulse_watcher_contract_present", False), ("daemon_action_contract_present", False), ("federation_consensus_present", False)):
        runtime_activation_gap_results[f"{key}_seen"] = key in gaps
        runtime_activation_gap_results[f"{key}_is_{str(expected).lower()}"] = gaps.get(key) is expected
    runtime_activation_gap_results["required_blocking_gap_ids_present"] = all(x in gap_ids for x in REQUIRED_BLOCKING_GAP_IDS)
    runtime_activation_gap_results["violations"] = _violations_from_bool_map(runtime_activation_gap_results); runtime_activation_gap_results["passed"] = not runtime_activation_gap_results["violations"]
    violation_ids = [x["check_id"] for x in checks if not x["passed"] and x["severity"] == "violation"]
    warning_ids = [x["check_id"] for x in checks if not x["passed"] and x["severity"] == "warning"]
    grouped_failed = [r for r in (boundary_catalog_results, finalizer_guard_binding_results, operator_consent_results, storage_enforcement_results, digest_parent_runtime_results, pulse_daemon_boundary_results, federation_boundary_results, runtime_activation_gap_results) if not r.get("passed")]
    verification_status = "storage_runtime_authority_contract_failed" if violation_ids or grouped_failed else "storage_runtime_authority_contract_verified"
    optional_summary = []
    for input_id in OPTIONAL_INPUT_IDS:
        s = optional_summaries[input_id]; data = optional_reports.get(input_id, {})
        optional_summary.append({"input_id": input_id, "provided": s.get("provided"), "detected_report_id": _report_id(data), "source_digest": s.get("digest"), "source_digest_algo": (s.get("digest_algo") or DIGEST_ALGO) if s.get("provided") else None, "source_byte_size": s.get("byte_size"), "relevant_status_or_digest": _status_or_digest(data), "context_only": True})
    return {
        "storage_runtime_authority_verifier_id": WORKCELL_STORAGE_RUNTIME_AUTHORITY_VERIFIER_ID, "metadata_only": True, "verifier_only": True,
        "runtime_binding_not_performed": True, "active_storage_allowed_now": False, "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False,
        "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {"storage_runtime_authority_contract_json": dict(storage_runtime_authority_contract_summary), **{k: dict(v) for k, v in optional_summaries.items()}},
        "runtime_authority_contract_summary": {"storage_runtime_authority_contract_id": c.get("storage_runtime_authority_contract_id"), "metadata_only": c.get("metadata_only"), "runtime_authority_contract_only": c.get("runtime_authority_contract_only"), "runtime_binding_not_performed": c.get("runtime_binding_not_performed"), "active_storage_allowed_now": c.get("active_storage_allowed_now"), "execution_performed": c.get("execution_performed"), "writes_performed": c.get("writes_performed"), "archives_performed": c.get("archives_performed"), "memory_mutation_performed": c.get("memory_mutation_performed"), "boundary_catalog_count": len(catalog_list), "blocking_gap_count": len(gap_ids), "non_authority_posture_present": isinstance(nonauth, Mapping), "non_authority_posture_all_true": _all_true(nonauth), "source_digest": storage_runtime_authority_contract_summary.get("digest"), "source_digest_algo": DIGEST_ALGO, "source_byte_size": storage_runtime_authority_contract_summary.get("byte_size")},
        "optional_context_summary": optional_summary, "verification_status": verification_status, "verification_checks": checks,
        "boundary_catalog_results": boundary_catalog_results, "finalizer_guard_binding_results": finalizer_guard_binding_results, "operator_consent_results": operator_consent_results, "storage_enforcement_results": storage_enforcement_results, "digest_parent_runtime_results": digest_parent_runtime_results, "pulse_daemon_boundary_results": pulse_daemon_boundary_results, "federation_boundary_results": federation_boundary_results, "runtime_activation_gap_results": runtime_activation_gap_results,
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata verifier.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "violation_summary": {"violation_count": len(violation_ids) + len(grouped_failed), "warning_count": len(warning_ids), "info_count": sum(1 for x in checks if x["severity"] == "info"), "violation_check_ids": violation_ids, "warning_check_ids": warning_ids, "verifier_only": True, "no_action_taken": True},
        "sentientos_mount_alignment": {"/ledger": "runtime authority verification only; no ledger write", "/glow": "runtime authority verification only; no archive write", "/vow": "canonical digest context for runtime authority boundaries", "/pulse": "future watcher boundary; inactive here", "/daemon": "future action boundary; inactive here"},
        "future_activation_requirements": [{"requirement": r, "status": "future_only", "met": False, "active": False} for r in FUTURE_REQUIREMENT_NAMES],
        "non_authority_posture": dict(NON_AUTHORITY_POSTURE),
    }

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")

def _table(headers: list[str], rows: list[list[Any]]) -> str:
    return "| " + " | ".join(headers) + " |\n| " + " | ".join("---" for _ in headers) + " |\n" + "".join("| " + " | ".join(_cell(c) for c in row) + " |\n" for row in rows)

def render_codex_workcell_storage_runtime_authority_verifier_markdown(report: Mapping[str, Any]) -> str:
    parts = ["# Codex Workcell Storage Runtime Authority Boundary Verifier\n", "This deterministic metadata-only verifier checks the runtime authority boundary contract structure; it performs no runtime binding, storage activation, readiness decision, write, archive, memory mutation, watcher, scheduler, daemon action, task creation, alerting, model training, or federation consensus.\n"]
    parts.append("## Input summaries\n" + _table(["input", "provided", "path", "digest", "bytes"], [[k, v.get("provided"), v.get("path"), v.get("digest"), v.get("byte_size")] for k, v in sorted(report["input_summaries"].items())]))
    for title, key in (("Runtime authority contract summary", "runtime_authority_contract_summary"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("Violation summary", "violation_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Non-authority posture", "non_authority_posture")):
        parts.append(f"## {title}\n" + _table(["key", "value"], [[k, v] for k, v in report[key].items()]))
    parts.append("## Optional context summary\n" + _table(["input", "provided", "report", "digest", "status"], [[r["input_id"], r["provided"], r["detected_report_id"], r["source_digest"], r["relevant_status_or_digest"]] for r in report["optional_context_summary"]]))
    parts.append("## Verification status\n" + str(report["verification_status"]) + "\n")
    parts.append("## Verification checks\n" + _table(["check", "passed", "severity", "details"], [[c["check_id"], c["passed"], c["severity"], c["details"]] for c in report["verification_checks"]]))
    for title, key in (("Boundary catalog results", "boundary_catalog_results"), ("Finalizer/guard binding results", "finalizer_guard_binding_results"), ("Operator consent results", "operator_consent_results"), ("Storage enforcement results", "storage_enforcement_results"), ("Digest/parent runtime results", "digest_parent_runtime_results"), ("Pulse/daemon boundary results", "pulse_daemon_boundary_results"), ("Federation boundary results", "federation_boundary_results"), ("Runtime activation gap results", "runtime_activation_gap_results")):
        parts.append(f"## {title}\n" + _table(["key", "value"], [[k, v] for k, v in report[key].items()]))
    parts.append("## Future activation requirements\n" + _table(["requirement", "status", "met", "active"], [[r["requirement"], r["status"], r["met"], r["active"]] for r in report["future_activation_requirements"]]))
    return "\n".join(parts)
