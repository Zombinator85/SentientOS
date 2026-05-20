from __future__ import annotations

from dataclasses import replace
import json

import pytest

from sentientos.reviewer_proof_bundle import (
    DEFERRED_ACTION_LABELS,
    ReviewerProofBundleArtifact,
    build_default_reviewer_proof_commands,
    build_reviewer_proof_bundle_payload,
    reviewer_proof_artifact_digest,
    reviewer_proof_bundle_manifest_digest,
    summarize_reviewer_proof_bundle_manifest,
    validate_reviewer_proof_bundle_manifest,
)

pytestmark = pytest.mark.no_legacy_skip

FIXED_CREATED_AT = "2025-07-30T00:00:00+00:00"


def test_default_bundle_payload_is_deterministic_with_fixed_created_at() -> None:
    first = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    second = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    assert first["manifest"].to_dict() == second["manifest"].to_dict()
    assert first["artifacts"] == second["artifacts"]
    assert first["manifest"].created_at == FIXED_CREATED_AT
    assert first["manifest"].bundle_status == "reviewer_proof_bundle_ready"


def test_manifest_validates_and_digests_are_deterministic() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    manifest = payload["manifest"]
    validation = validate_reviewer_proof_bundle_manifest(manifest)
    assert validation.ok, validation.findings
    assert reviewer_proof_bundle_manifest_digest(manifest) == manifest.digest
    assert reviewer_proof_artifact_digest(payload["artifacts"]["trace_json"]) == next(
        artifact.digest for artifact in manifest.artifact_records if artifact.artifact_kind == "trace_json"
    )


def test_manifest_summary_is_metadata_only_and_reviewer_proof_only() -> None:
    manifest = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)["manifest"]
    summary = summarize_reviewer_proof_bundle_manifest(manifest)
    assert summary["metadata_only"] is True
    assert summary["reviewer_proof_only"] is True
    assert summary["live_host_collection_performed"] is False
    assert summary["live_authorization_granted"] is False
    assert summary["effect_performed"] is False
    assert summary["host_mutation_performed"] is False
    assert summary["network_performed"] is False
    assert summary["provider_invocation_performed"] is False
    assert summary["prompt_assembly_performed"] is False


def test_default_proof_commands_are_listed_and_not_run() -> None:
    commands = build_default_reviewer_proof_commands()
    assert commands
    assert all(command.status == "proof_command_not_run" for command in commands)
    assert all(command.executed is False for command in commands)
    rendered = [" ".join(command.command) for command in commands]
    assert "python scripts/build_host_embodiment_trace.py --validate-only" in rendered
    assert "python scripts/verify_context_hygiene_prompt_boundaries.py" in rendered
    assert "python scripts/build_local_effect_transaction_ledger.py --effect-receipt <effect_receipt.json> --postcondition-check <postcondition.json> --production-audit <audit.json> --rollback-plan <rollback_plan.json> --summary" in rendered


def test_bundle_includes_expected_artifacts_and_content() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    artifacts = payload["artifacts"]
    for key in [
        "trace_json",
        "trace_markdown",
        "trace_summary",
        "capability_registry_summary",
        "deferred_action_inventory",
        "proof_command_manifest",
        "reviewer_readme",
        "bundle_manifest",
        "local_effect_transaction_ledger_capability",
    ]:
        assert key in artifacts
    assert "fake/sample" in artifacts["trace_summary"]
    assert "PWM presence is not control authority" in artifacts["trace_markdown"]
    assert "reviewer_proof_bundle" in artifacts["capability_registry_summary"]
    assert "real_fan_pwm_control" in artifacts["deferred_action_inventory"]
    assert "proof_command_not_run" in artifacts["proof_command_manifest"]
    assert "performs_no_new_host_effect_by_default" in artifacts["local_effect_transaction_ledger_capability"]
    assert "proof_bundle_ledger_built_by_default" in artifacts["local_effect_transaction_ledger_capability"]


def test_deferred_actions_cover_non_mutating_boundary() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    manifest = payload["manifest"]
    for label in [
        "real_fan_pwm_control",
        "real_thermal_actuation",
        "real_power_profile_mutation",
        "real_service_restart",
        "real_file_cleanup",
        "provider_invocation",
        "network_egress",
        "prompt_assembly_export",
        "federation_transport_sync_adoption",
        "remote_execution",
    ]:
        assert label in manifest.deferred_capability_labels
        assert label in DEFERRED_ACTION_LABELS


@pytest.mark.parametrize(
    "flag",
    [
        "live_host_collection_performed",
        "live_authorization_granted",
        "effect_performed",
        "host_mutation_performed",
        "network_performed",
        "provider_invocation_performed",
        "prompt_assembly_performed",
    ],
)
def test_validation_rejects_forbidden_manifest_flags(flag: str) -> None:
    manifest = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)["manifest"]
    bad = replace(manifest, **{flag: True})
    result = validate_reviewer_proof_bundle_manifest(bad)
    assert not result.ok
    assert f"manifest_forbidden_flag:{flag}" in result.findings


@pytest.mark.parametrize(
    "flag",
    ["contains_live_host_data", "contains_prompt_text", "contains_secret_material", "contains_provider_material"],
)
def test_artifact_validation_rejects_forbidden_material_flags(flag: str) -> None:
    manifest = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)["manifest"]
    artifacts = list(manifest.artifact_records)
    artifacts[0] = replace(artifacts[0], **{flag: True})
    bad = replace(manifest, artifact_records=tuple(artifacts))
    result = validate_reviewer_proof_bundle_manifest(bad)
    assert not result.ok
    assert any(f"artifact_forbidden_flag:{artifacts[0].artifact_kind}:{flag}" == finding for finding in result.findings)


def test_validation_rejects_unknown_artifact_kind() -> None:
    manifest = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)["manifest"]
    artifacts = list(manifest.artifact_records)
    artifacts.append(
        ReviewerProofBundleArtifact(
            artifact_id="bad",
            artifact_kind="unknown",
            relative_path="bad.txt",
            media_type="text/plain",
            digest="sha256:bad",
            byte_count=3,
        )
    )
    result = validate_reviewer_proof_bundle_manifest(replace(manifest, artifact_records=tuple(artifacts)))
    assert not result.ok
    assert "unknown_artifact_kind:unknown" in result.findings



def test_reviewer_bundle_includes_work_item_promotion_gate_capability_artifact() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    artifacts = payload["artifacts"]
    assert "work_item_promotion_gate_capability" in artifacts
    assert "work_item_promotion_gate_capability.json" in artifacts["bundle_manifest"]
    text = artifacts["work_item_promotion_gate_capability"]
    assert '"capability_id": "work_item_promotion_gate"' in text
    assert '"authority_level": "packet_only"' in text
    assert "proof_command_not_run" in text
    assert "evaluate_work_item_promotion.py" in text
    assert "task_work_item_promotion_gate_wing.md" in text


def test_bundle_includes_host_actuation_safety_gate_posture() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    assert "safety_gate_posture" in payload["artifacts"]
    assert "safety_gates.json" in payload["artifacts"]["bundle_manifest"]
    assert "Safety gates declare prerequisites only" in payload["artifacts"]["safety_gate_posture"]
    assert "safety_gates" in payload
    validation = validate_reviewer_proof_bundle_manifest(payload["manifest"])
    assert validation.ok, validation.findings


def test_reviewer_bundle_includes_live_grant_readiness_posture() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    assert "live_grant_readiness_posture" in payload["artifacts"]
    assert "live_grant_readiness.json" in payload["artifacts"]["bundle_manifest"]
    text = payload["artifacts"]["live_grant_readiness_posture"]
    assert "Live-grant readiness is not a live grant" in text
    assert "grant_not_issued" in text
    assert payload["live_grant_readiness"].preflight_receipt.live_authorization_granted is False


def test_reviewer_bundle_includes_local_authorization_posture_without_fulfillment() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    assert "local_authorization_posture" in payload["artifacts"]
    assert "local_authorization.json" in payload["artifacts"]["bundle_manifest"]
    text = payload["artifacts"]["local_authorization_posture"]
    assert "authority metadata, not fulfillment" in text
    assert "authorizes_fulfillment" in text
    grant = payload["local_authorization"].grant
    assert grant.live_authorization_granted is True
    assert grant.fulfillment_granted is False
    assert grant.effect_performed is False
    assert grant.host_mutation_performed is False
    assert payload["local_authorization"].verification.authorizes_fulfillment is False


def test_reviewer_bundle_includes_fulfillment_authorization_consumption_posture_without_execution() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    assert "fulfillment_authorization_posture" in payload["artifacts"]
    assert "fulfillment_authorization.json" in payload["artifacts"]["bundle_manifest"]
    text = payload["artifacts"]["fulfillment_authorization_posture"]
    assert "consuming authorization is not fulfillment" in text
    assert "scope match is not execution" in text
    wing = payload["fulfillment_authorization"]
    assert wing.consumption_receipt is not None
    assert wing.consumption_receipt.authorization_consumed_for_future_fulfillment is True
    assert wing.consumption_receipt.fulfillment_granted is False
    assert wing.consumption_receipt.effect_performed is False
    assert wing.consumption_receipt.host_mutation_performed is False
    validation = validate_reviewer_proof_bundle_manifest(payload["manifest"])
    assert validation.ok, validation.findings


def test_bundle_includes_executor_contract_posture_without_execution() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    artifacts = payload["artifacts"]
    manifest = payload["manifest"]
    assert "executor_contract_posture" in artifacts
    assert any(record.artifact_kind == "executor_contract_posture" and record.relative_path == "executor_contract.json" for record in manifest.artifact_records)
    assert "Executor contract records define prerequisites" in artifacts["executor_contract_posture"]
    wing = payload["executor_contract"]
    assert wing.contract.executor_implemented is False
    assert wing.backend_declaration.backend_loaded is False
    assert wing.backend_declaration.backend_invoked is False
    assert wing.dry_run_plan.dry_run_executed is False
    assert wing.admission_packet.control_plane_admission_granted is False
    assert wing.readiness_receipt.fulfillment_granted is False
    assert wing.readiness_receipt.effect_performed is False
    assert wing.readiness_receipt.host_mutation_performed is False
    validation = validate_reviewer_proof_bundle_manifest(manifest)
    assert validation.ok, validation.findings


def test_deferred_actions_include_executor_contract_non_execution_ladder() -> None:
    manifest = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)["manifest"]
    for label in ["executor_implementation", "backend_invocation", "control_plane_admission_for_fulfillment", "fulfillment_execution"]:
        assert label in manifest.deferred_capability_labels
        assert label in DEFERRED_ACTION_LABELS


def test_default_reviewer_proof_bundle_includes_dry_run_execution_artifact() -> None:
    payload = build_reviewer_proof_bundle_payload()
    assert "dry_run_execution_posture" in payload["artifacts"]
    dry_run = json.loads(payload["artifacts"]["dry_run_execution_posture"])
    assert dry_run["dry_run_execution_harness_only"] is True
    assert dry_run["simulation_only"] is True
    assert dry_run["dry_run_executed"] is True
    assert dry_run["real_backend_invoked"] is False
    assert dry_run["real_fulfillment_performed"] is False
    assert dry_run["real_effect_performed"] is False
    assert dry_run["host_mutation_performed"] is False
    assert "dry_run_execution_posture" in {artifact.artifact_kind for artifact in payload["manifest"].artifact_records}


def test_default_reviewer_proof_bundle_includes_dry_run_audit_closure_artifact() -> None:
    payload = build_reviewer_proof_bundle_payload()
    assert "dry_run_audit_closure_posture" in payload["artifacts"]
    closure = json.loads(payload["artifacts"]["dry_run_audit_closure_posture"])
    assert closure["dry_run_audit_closure_only"] is True
    assert closure["effect_verification_summary"]["real_effect_receipt_created"] is False
    assert closure["postcondition_verification_summary"]["real_postcondition_check_performed"] is False
    assert closure["rollback_rehearsal_summary"]["real_rollback_performed"] is False
    assert closure["audit_closure_receipt_summary"]["production_audit_receipt_created"] is False
    assert closure["real_fulfillment_performed"] is False
    assert closure["host_mutation_performed"] is False
    assert "dry_run_audit_closure_posture" in {artifact.artifact_kind for artifact in payload["manifest"].artifact_records}
    validation = validate_reviewer_proof_bundle_manifest(payload["manifest"])
    assert validation.ok, validation.findings


def test_bundle_includes_real_effect_admission_posture_and_remains_non_mutating() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    assert "real_effect_admission_posture" in payload["artifacts"]
    admission = json.loads(payload["artifacts"]["real_effect_admission_posture"])
    assert admission["real_effect_admission_only"] is True
    assert admission["authorizes_implementation"] is False
    assert admission["authorizes_execution"] is False
    assert admission["implementation_not_started"] is True
    assert admission["backend_loaded"] is False
    assert admission["backend_invoked"] is False
    assert admission["real_backend_implemented"] is False
    assert admission["real_fulfillment_performed"] is False
    assert admission["real_effect_performed"] is False
    assert admission["host_mutation_performed"] is False
    assert "fan_pwm_write" in admission["blocked_actions"]
    assert "thermal_actuation" in admission["blocked_actions"]


def test_reviewer_proof_bundle_lists_local_diagnostic_effect_but_does_not_run_it() -> None:
    payload = build_reviewer_proof_bundle_payload()
    artifacts = payload["artifacts"]
    capability = json.loads(artifacts["local_diagnostic_effect_capability"])
    assert capability["explicit_command_required"] is True
    assert capability["run_by_reviewer_proof_bundle_default"] is False
    assert capability["proof_bundle_effect_performed"] is False
    assert capability["proof_bundle_host_mutation_performed"] is False
    commands = json.loads(artifacts["proof_command_manifest"])["commands"]
    local_commands = [record for record in commands if "run_local_diagnostic_effect.py" in " ".join(record["command"])]
    assert local_commands
    assert all(record["status"] == "proof_command_not_run" and record["executed"] is False for record in local_commands)


def test_reviewer_proof_bundle_lists_exact_rollback_but_does_not_run_it() -> None:
    payload = build_reviewer_proof_bundle_payload()
    artifacts = payload["artifacts"]
    capability = json.loads(artifacts["local_diagnostic_rollback_capability"])
    assert capability["explicit_command_required"] is True
    assert capability["run_by_reviewer_proof_bundle_default"] is False
    assert capability["proof_bundle_rollback_performed"] is False
    assert capability["proof_bundle_host_mutation_performed"] is False
    assert capability["not_general_cleanup"] is True
    commands = json.loads(artifacts["proof_command_manifest"])["commands"]
    rollback_commands = [record for record in commands if "run_local_diagnostic_rollback.py" in " ".join(record["command"])]
    assert rollback_commands
    assert all(record["status"] == "proof_command_not_run" and record["executed"] is False for record in rollback_commands)


def test_bundle_includes_host_steward_boundary_posture_without_runner_execution() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    assert "host_steward_boundary_posture" in payload["artifacts"]
    assert "host_steward_boundary.json" in payload["artifacts"]["bundle_manifest"]
    posture = json.loads(payload["artifacts"]["host_steward_boundary_posture"])
    assert posture["delegated_runners_do_not_inherit_ambient_authority"] is True
    assert posture["no_runner_executes_by_default"] is True
    assert posture["containment_profiles_are_not_live_sandbox_execution"] is True
    assert posture["backend_declarations_do_not_load_or_invoke_backends"] is True
    assert posture["grant_scaffolds_do_not_issue_live_runner_grants"] is True
    assert posture["boundary_assessments_do_not_authorize_runner_execution"] is True
    assert posture["proof_bundle_effect_performed"] is False
    assert posture["proof_bundle_rollback_performed"] is False
    assert posture["proof_bundle_ledger_built_by_default"] is False
    assert posture["runner_executed"] is False
    assert posture["host_mutation_performed"] is False
    assert payload["host_steward_boundary"].runner_executed is False
    assert validate_reviewer_proof_bundle_manifest(payload["manifest"]).ok


def test_bundle_includes_builtin_local_effect_runner_capability_and_does_not_run_it() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    artifacts = payload["artifacts"]
    assert "builtin_local_effect_runner_capability" in artifacts
    artifact = json.loads(artifacts["builtin_local_effect_runner_capability"])
    assert artifact["built_in_runner_exists"] is True
    assert artifact["run_by_reviewer_proof_bundle_default"] is False
    assert artifact["proof_bundle_runner_invoked"] is False
    assert artifact["supported_action_kinds"] == ["local_diagnostic_artifact_write", "local_diagnostic_exact_rollback", "workspace_scoped_file_update", "workspace_scoped_file_exact_rollback"]
    commands = [" ".join(command.command) for command in payload["manifest"].proof_command_records]
    assert "python scripts/run_builtin_local_effect_runner.py --action local_diagnostic_artifact_write --output-dir /tmp/sentientos-local-effect-runner --summary" in commands
    assert all(command.status == "proof_command_not_run" and command.executed is False for command in payload["manifest"].proof_command_records)


def test_bundle_includes_builtin_runner_transaction_orchestrator_capability_and_does_not_run_it() -> None:
    import json

    payload = build_reviewer_proof_bundle_payload()
    artifacts = payload["artifacts"]
    assert "builtin_runner_transaction_orchestrator_capability" in artifacts
    artifact = json.loads(artifacts["builtin_runner_transaction_orchestrator_capability"])
    assert artifact["orchestrator_exists"] is True
    assert artifact["supports_only_bounded_builtin_runner_diagnostic_write_and_exact_rollback"] is True
    assert artifact["can_build_transaction_ledger_explicitly"] is True
    assert artifact["run_by_reviewer_proof_bundle_default"] is False
    assert artifact["proof_bundle_orchestrator_invoked"] is False
    assert artifact["no_subprocess_shell_network_provider_prompt"] is True
    assert artifact["no_hardware_service_power_general_cleanup"] is True
    commands = [" ".join(command.command) for command in payload["manifest"].proof_command_records]
    assert "python scripts/run_builtin_runner_transaction.py --output-dir /tmp/sentientos-builtin-runner-transaction --mode diagnostic_write_rollback_with_ledger --ledger-output /tmp/sentientos-builtin-runner-transaction/transaction_ledger.json --summary" in commands
    assert all(command.status == "proof_command_not_run" and command.executed is False for command in payload["manifest"].proof_command_records)


def test_default_reviewer_proof_bundle_includes_workspace_file_effect_capability_without_running() -> None:
    import json
    payload = build_reviewer_proof_bundle_payload()
    artifacts = payload["artifacts"]
    assert "workspace_file_effect_capability" in artifacts
    capability = json.loads(artifacts["workspace_file_effect_capability"])
    assert capability["run_by_reviewer_proof_bundle_default"] is False
    assert capability["proof_bundle_effect_performed"] is False
    assert capability["supports_exactly_one_workspace_scoped_file_target"] is True
    assert capability["captures_preimage_before_replacement"] is True
    assert capability["supports_exact_rollback"] is True
    assert capability["no_recursive_wildcard_unrelated_delete"] is True
    commands = json.loads(artifacts["proof_command_manifest"])["commands"]
    assert any("run_workspace_file_effect.py" in " ".join(record["command"]) and record["status"] == "proof_command_not_run" for record in commands)


def test_default_reviewer_proof_bundle_includes_workspace_runner_transaction_capability_without_running() -> None:
    payload = build_reviewer_proof_bundle_payload()
    artifacts = payload["artifacts"]
    assert "workspace_file_runner_transaction_capability" in artifacts
    capability = json.loads(artifacts["workspace_file_runner_transaction_capability"])
    assert capability["built_in_runner_can_invoke_workspace_scoped_file_update"] is True
    assert capability["built_in_runner_can_invoke_workspace_scoped_file_exact_rollback"] is True
    assert capability["transaction_ledger_can_be_built_explicitly"] is True
    assert capability["run_by_reviewer_proof_bundle_default"] is False
    assert capability["proof_bundle_runner_invoked"] is False
    assert capability["proof_bundle_ledger_built_by_default"] is False
    commands = json.loads(artifacts["proof_command_manifest"])["commands"]
    workspace_runner_commands = [record for record in commands if "workspace_scoped_file_" in " ".join(record["command"])]
    assert workspace_runner_commands
    assert all(record["status"] == "proof_command_not_run" and record["executed"] is False for record in workspace_runner_commands)


def test_bundle_includes_workspace_transaction_orchestrator_capability_without_running() -> None:
    payload = build_reviewer_proof_bundle_payload()
    artifacts = payload["artifacts"]
    assert "workspace_file_transaction_orchestrator_capability" in artifacts
    capability = json.loads(artifacts["workspace_file_transaction_orchestrator_capability"])
    assert capability["workspace_transaction_orchestrator_support"] == "implemented"
    assert capability["run_by_reviewer_proof_bundle_default"] is False
    assert capability["proof_bundle_orchestrator_invoked"] is False
    assert capability["one_explicit_target_only"] is True
    assert capability["not_general_filesystem_access"] is True
    commands = json.loads(artifacts["proof_command_manifest"])["commands"]
    orch_commands = [record for record in commands if "workspace_file_update_rollback_with_ledger" in " ".join(record["command"])]
    assert orch_commands
    assert all(record["status"] == "proof_command_not_run" and record["executed"] is False for record in orch_commands)


def test_bundle_includes_workspace_change_set_preflight_artifact_and_not_run_command() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    artifacts = payload["artifacts"]
    assert "workspace_change_set_preflight_capability" in artifacts
    capability = json.loads(artifacts["workspace_change_set_preflight_capability"])
    assert capability["change_set_preflight_exists"] is True
    assert capability["reads_only_explicitly_declared_targets"] is True
    assert capability["target_writes_occur"] is False
    assert capability["rollback_occurs"] is False
    assert capability["runner_orchestrator_invocation_occurs"] is False
    assert capability["run_by_reviewer_proof_bundle_default"] is False
    assert capability["proof_command_status"] == "proof_command_not_run"
    commands = json.loads(artifacts["proof_command_manifest"])["commands"]
    rendered = [" ".join(command["command"]) for command in commands]
    assert "python scripts/preflight_workspace_change_set.py --workspace-root /tmp/sentientos-workspace-change-set --target demo.txt=hello --summary" in rendered
    assert all(command.status == "proof_command_not_run" for command in payload["manifest"].proof_command_records)


def test_bundle_includes_workspace_change_set_execution_artifact_and_not_run_command() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    artifacts = payload["artifacts"]
    assert "workspace_change_set_execution_capability" in artifacts
    capability = json.loads(artifacts["workspace_change_set_execution_capability"])
    assert capability["bounded_change_set_execution_exists"] is True
    assert capability["consumes_passed_preflight_and_transaction_plans"] is True
    assert capability["executes_explicit_targets_only"] is True
    assert capability["uses_single_target_workspace_file_effect_helpers"] is True
    assert capability["rollback_is_reverse_order_exact_target_only"] is True
    assert capability["partial_state_is_visible"] is True
    assert capability["run_by_reviewer_proof_bundle_default"] is False
    assert capability["proof_bundle_execution_performed"] is False
    assert capability["general_filesystem_access_remains_blocked"] is True
    assert capability["cleanup_remains_blocked"] is True
    assert capability["proof_command_status"] == "proof_command_not_run"
    commands = json.loads(artifacts["proof_command_manifest"])["commands"]
    rendered = [" ".join(command["command"]) for command in commands]
    assert "python scripts/run_workspace_change_set_transaction.py --workspace-root /tmp/sentientos-workspace-change-set --target demo.txt=hello --target docs-demo.txt=docs --summary" in rendered
    assert all(command.status == "proof_command_not_run" for command in payload["manifest"].proof_command_records)


def test_bundle_includes_workspace_change_set_execution_verification_artifact_and_not_run_command() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    artifacts = payload["artifacts"]
    assert "workspace_change_set_execution_verification_capability" in artifacts
    capability = json.loads(artifacts["workspace_change_set_execution_verification_capability"])
    assert capability["read_only_verification_exists"] is True
    assert capability["verifies_completed_change_set_execution_evidence"] is True
    assert capability["reads_only_explicitly_declared_targets"] is True
    assert capability["checks_receipt_ledger_closure_consistency"] is True
    assert capability["optional_audit_artifact_only_when_caller_supplies_path"] is True
    assert capability["run_by_reviewer_proof_bundle_default"] is False
    assert capability["proof_bundle_verification_run"] is False
    assert capability["proof_bundle_execution_performed"] is False
    assert capability["proof_bundle_rollback_performed"] is False
    assert capability["proof_bundle_cleanup_performed"] is False
    assert capability["proof_command_status"] == "proof_command_not_run"
    commands = json.loads(artifacts["proof_command_manifest"])["commands"]
    rendered = [" ".join(command["command"]) for command in commands]
    assert "python scripts/verify_workspace_change_set_execution.py --evidence <workspace_change_set_execution_evidence.json> --summary" in rendered
    assert all(command.status == "proof_command_not_run" for command in payload["manifest"].proof_command_records)


def test_bundle_includes_workspace_change_set_lifecycle_closure_artifact_and_not_run_command() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    artifacts = payload["artifacts"]
    assert "workspace_change_set_lifecycle_closure_capability" in artifacts
    capability = json.loads(artifacts["workspace_change_set_lifecycle_closure_capability"])
    assert capability["lifecycle_closure_manifest_exists"] is True
    assert capability["consumes_supplied_evidence_json_only"] is True
    assert capability["does_not_verify_replay"] is True
    assert capability["does_not_read_target_files"] is True
    assert capability["optional_closure_artifact_only_when_caller_supplies_path"] is True
    assert capability["run_by_reviewer_proof_bundle_default"] is False
    assert capability["proof_bundle_closure_run"] is False
    assert capability["proof_bundle_execution_performed"] is False
    assert capability["proof_bundle_rollback_performed"] is False
    assert capability["proof_bundle_cleanup_performed"] is False
    assert capability["proof_command_status"] == "proof_command_not_run"
    commands = json.loads(artifacts["proof_command_manifest"])["commands"]
    rendered = [" ".join(command["command"]) for command in commands]
    assert "python scripts/build_workspace_change_set_lifecycle_closure.py --evidence <workspace_change_set_lifecycle_evidence.json> --summary" in rendered
    assert all(command.status == "proof_command_not_run" for command in payload["manifest"].proof_command_records)


def test_bundle_includes_workspace_change_set_admission_artifact_and_not_run_command() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    artifacts = payload["artifacts"]
    assert "workspace_change_set_admission_capability" in artifacts
    capability = json.loads(artifacts["workspace_change_set_admission_capability"])
    assert capability["change_set_admission_exists"] is True
    assert capability["admission_review_only"] is True
    assert capability["inspects_supplied_proposal_metadata_only"] is True
    assert capability["target_payload_bodies_included"] is False
    assert capability["workspace_target_files_read"] is False
    assert capability["preflight_performed"] is False
    assert capability["execution_performed"] is False
    assert capability["run_by_reviewer_proof_bundle_default"] is False
    assert capability["proof_command_status"] == "proof_command_not_run"
    commands = json.loads(artifacts["proof_command_manifest"])["commands"]
    rendered = [" ".join(command["command"]) for command in commands]
    assert "python scripts/admit_workspace_change_set.py --proposal <workspace_change_set_proposal_metadata.json> --summary" in rendered
    assert all(command.status == "proof_command_not_run" for command in payload["manifest"].proof_command_records)


def test_bundle_includes_workspace_change_set_lifecycle_orchestration_artifact_and_not_run_command() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    artifacts = payload["artifacts"]
    assert "workspace_change_set_lifecycle_orchestration_capability" in artifacts
    capability = json.loads(artifacts["workspace_change_set_lifecycle_orchestration_capability"])
    assert capability["lifecycle_orchestration_exists"] is True
    assert capability["coordinates_existing_workspace_change_set_wings_only"] is True
    assert capability["dry_run_does_not_execute_or_verify"] is True
    assert capability["does_not_read_target_files_directly"] is True
    assert capability["run_by_reviewer_proof_bundle_default"] is False
    assert capability["proof_bundle_lifecycle_orchestration_run"] is False
    assert capability["proof_command_status"] == "proof_command_not_run"


def test_reviewer_bundle_includes_work_item_operator_admission_review_capability_artifact() -> None:
    payload = build_reviewer_proof_bundle_payload(created_at=FIXED_CREATED_AT)
    artifacts = payload["artifacts"]
    assert "work_item_operator_admission_review_capability" in artifacts
    text = artifacts["work_item_operator_admission_review_capability"]
    assert "work_item_operator_admission_review" in text
    assert "proof_command_not_run" in text

def test_reviewer_bundle_includes_work_item_operator_confirmed_admission_run_capability_artifact() -> None:
    from sentientos.reviewer_proof_bundle import build_reviewer_proof_bundle_payload
    artifacts = build_reviewer_proof_bundle_payload()["artifacts"]
    assert "work_item_operator_confirmed_admission_run_capability" in artifacts
    assert "work_item_operator_confirmed_admission_run" in artifacts["work_item_operator_confirmed_admission_run_capability"]


def test_reviewer_bundle_includes_work_item_operator_confirmed_preflight_run_capability_artifact() -> None:
    from sentientos.reviewer_proof_bundle import build_reviewer_proof_bundle_payload
    artifacts = build_reviewer_proof_bundle_payload()["artifacts"]
    assert "work_item_operator_confirmed_preflight_run_capability" in artifacts
    assert "work_item_operator_confirmed_preflight_run" in artifacts["work_item_operator_confirmed_preflight_run_capability"]
