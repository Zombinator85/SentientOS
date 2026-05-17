from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from sentientos.builtin_local_effect_runner import (
    BLOCKED_ACTIONS,
    REQUIRED_RUNNER_LABELS,
    RUNNER_ACTION_KINDS,
    build_builtin_local_effect_runner_declaration,
    build_builtin_runner_invocation_request,
    build_builtin_runner_execution_receipt,
    build_builtin_runner_block_receipt,
    run_builtin_local_effect_runner,
    run_builtin_local_effect_runner_wing,
    summarize_builtin_local_effect_runner_wing,
    validate_builtin_local_effect_runner_declaration,
    validate_builtin_runner_invocation_request,
    validate_builtin_runner_invocation_result,
    validate_builtin_runner_execution_receipt,
    validate_builtin_runner_block_receipt,
)

pytestmark = pytest.mark.no_legacy_skip


def test_runner_declaration_supports_exact_bounded_action_kinds() -> None:
    declaration = build_builtin_local_effect_runner_declaration()
    assert declaration.runner_trust_class == "bounded_builtin_runner"
    assert declaration.supported_action_kinds == RUNNER_ACTION_KINDS
    assert declaration.in_process_only is True
    assert validate_builtin_local_effect_runner_declaration(declaration).ok


def test_unsupported_action_kind_blocks(tmp_path: Path) -> None:
    declaration = build_builtin_local_effect_runner_declaration()
    request = build_builtin_runner_invocation_request(declaration, action_kind="shell_execution", output_dir=tmp_path)
    assert request.request_status != "builtin_runner_invocation_requested"
    records = run_builtin_local_effect_runner_wing(action_kind="shell_execution", output_dir=tmp_path)
    assert records.block_receipt is not None
    assert records.block_receipt.delegated_runner_invoked is False


def test_write_action_dry_run_writes_nothing(tmp_path: Path) -> None:
    records = run_builtin_local_effect_runner_wing(action_kind="local_diagnostic_artifact_write", output_dir=tmp_path, dry_run=True)
    assert records.result is not None
    assert records.result.result_status == "builtin_runner_invocation_blocked"
    assert records.result.host_mutation_performed is False
    assert not (tmp_path / "sentientos_local_diagnostic_effect.json").exists()
    assert not (tmp_path / "effect_receipt.json").exists()


def test_write_action_real_run_writes_artifact_and_receipt(tmp_path: Path) -> None:
    records = run_builtin_local_effect_runner_wing(action_kind="local_diagnostic_artifact_write", output_dir=tmp_path)
    assert records.execution_receipt is not None
    assert records.result is not None
    assert records.result.result_status == "builtin_runner_invocation_performed"
    assert records.result.local_diagnostic_effect_performed is True
    assert records.execution_receipt.host_mutation_performed is True
    assert (tmp_path / "sentientos_local_diagnostic_effect.json").exists()
    assert (tmp_path / "effect_receipt.json").exists()
    assert (tmp_path / "postcondition_check.json").exists()
    assert (tmp_path / "production_audit.json").exists()
    assert (tmp_path / "rollback_plan.json").exists()
    assert validate_builtin_runner_invocation_result(records.result).ok
    assert validate_builtin_runner_execution_receipt(records.execution_receipt).ok


def _write_effect(tmp_path: Path):
    records = run_builtin_local_effect_runner_wing(action_kind="local_diagnostic_artifact_write", output_dir=tmp_path)
    assert records.result and records.result.result_status == "builtin_runner_invocation_performed"
    return tmp_path / "effect_receipt.json", tmp_path / "rollback_plan.json"


def test_rollback_action_dry_run_deletes_nothing(tmp_path: Path) -> None:
    effect_receipt, rollback_plan = _write_effect(tmp_path)
    artifact = tmp_path / "sentientos_local_diagnostic_effect.json"
    records = run_builtin_local_effect_runner_wing(
        action_kind="local_diagnostic_exact_rollback",
        effect_receipt_path=effect_receipt,
        rollback_plan_path=rollback_plan,
        output_dir_scope=tmp_path,
        dry_run=True,
    )
    assert records.result is not None
    assert records.result.host_mutation_performed is False
    assert artifact.exists()


def test_rollback_action_real_run_deletes_exact_artifact_and_preserves_sibling(tmp_path: Path) -> None:
    effect_receipt, rollback_plan = _write_effect(tmp_path)
    artifact = tmp_path / "sentientos_local_diagnostic_effect.json"
    sibling = tmp_path / "sibling.txt"
    sibling.write_text("keep", encoding="utf-8")
    records = run_builtin_local_effect_runner_wing(
        action_kind="local_diagnostic_exact_rollback",
        effect_receipt_path=effect_receipt,
        rollback_plan_path=rollback_plan,
        output_dir_scope=tmp_path,
    )
    assert records.execution_receipt is not None
    assert records.result is not None
    assert records.result.exact_artifact_rollback_performed is True
    assert records.execution_receipt.host_mutation_performed is True
    assert not artifact.exists()
    assert sibling.exists()
    assert (tmp_path / "rollback_receipt.json").exists()
    assert validate_builtin_runner_execution_receipt(records.execution_receipt).ok


@pytest.mark.parametrize("trust_class", ["generated_code_runner", "plugin_runner", "federation_import_runner", "external_tool_runner"])
def test_untrusted_runner_trust_classes_block(trust_class: str) -> None:
    declaration = build_builtin_local_effect_runner_declaration(runner_trust_class=trust_class)
    assert declaration.declaration_status == "builtin_local_runner_blocked"
    assert not validate_builtin_local_effect_runner_declaration(declaration).ok


def test_missing_required_labels_and_boundary_contradictions_block(tmp_path: Path) -> None:
    declaration = build_builtin_local_effect_runner_declaration()
    req = build_builtin_runner_invocation_request(declaration, action_kind="local_diagnostic_artifact_write", output_dir=tmp_path, required_runner_labels=REQUIRED_RUNNER_LABELS[:-1])
    assert not validate_builtin_runner_invocation_request(req).ok
    for kwargs, code in [
        ({"boundary_profile_id": "contradicted"}, "boundary_contradiction"),
        ({"containment_profile_id": "contradicted"}, "containment_contradiction"),
        ({"grant_scaffold_id": "contradicted"}, "grant_scaffold_contradiction"),
    ]:
        bad = build_builtin_runner_invocation_request(declaration, action_kind="local_diagnostic_artifact_write", output_dir=tmp_path, **kwargs)
        assert code in bad.warning_codes
        assert bad.request_status == "builtin_runner_invocation_contradicted"


@pytest.mark.parametrize(
    "field",
    [
        "subprocess_used",
        "shell_used",
        "network_used",
        "provider_invocation_performed",
        "prompt_assembly_performed",
        "fan_pwm_write_performed",
        "thermal_actuation_performed",
        "power_profile_mutation_performed",
        "service_restart_performed",
        "general_cleanup_performed",
        "recursive_delete_performed",
        "unrelated_file_delete_performed",
    ],
)
def test_validation_rejects_forbidden_claims(tmp_path: Path, field: str) -> None:
    records = run_builtin_local_effect_runner_wing(action_kind="local_diagnostic_artifact_write", output_dir=tmp_path)
    assert records.result is not None
    bad = replace(records.result, **{field: True})
    assert not validate_builtin_runner_invocation_result(bad).ok


def test_digests_deterministic_and_summary_identifies_boundaries(tmp_path: Path) -> None:
    a = build_builtin_local_effect_runner_declaration(runner_label="a")
    b = build_builtin_local_effect_runner_declaration(runner_label="a")
    c = build_builtin_local_effect_runner_declaration(runner_label="c")
    assert a.digest == b.digest
    assert a.digest != c.digest
    records = run_builtin_local_effect_runner_wing(action_kind="local_diagnostic_artifact_write", output_dir=tmp_path, dry_run=True)
    summary = summarize_builtin_local_effect_runner_wing(records)
    assert summary["bounded_builtin_runner_only"] is True
    assert summary["not_general_runner_framework"] is True
    assert summary["supported_action_kinds"] == RUNNER_ACTION_KINDS


def test_block_receipt_validates_without_invocation() -> None:
    receipt = build_builtin_runner_block_receipt(block_reason_codes=("unsupported_action_kind",), missing_labels=("runner_must_have_transaction_ledger",))
    assert receipt.delegated_runner_invoked is False
    assert validate_builtin_runner_block_receipt(receipt).ok


def test_workspace_update_action_real_run_writes_one_target_and_records(tmp_path: Path) -> None:
    sibling = tmp_path / "sibling.txt"
    sibling.write_text("keep", encoding="utf-8")
    records = run_builtin_local_effect_runner_wing(
        action_kind="workspace_scoped_file_update",
        workspace_root=tmp_path,
        relative_target_path="demo.txt",
        payload_text="hello",
    )
    assert records.execution_receipt is not None
    assert records.result is not None
    assert records.result.workspace_scoped_file_effect_performed is True
    assert records.result.host_mutation_performed is True
    assert records.result.general_filesystem_access_performed is False
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "hello"
    assert sibling.read_text(encoding="utf-8") == "keep"
    assert (tmp_path / "workspace_effect_receipt.json").exists()
    assert (tmp_path / "workspace_rollback_plan.json").exists()


def test_workspace_update_dry_run_writes_nothing(tmp_path: Path) -> None:
    records = run_builtin_local_effect_runner_wing(
        action_kind="workspace_scoped_file_update",
        workspace_root=tmp_path,
        relative_target_path="demo.txt",
        payload_text="hello",
        dry_run=True,
    )
    assert records.result is not None
    assert records.result.host_mutation_performed is False
    assert not (tmp_path / "demo.txt").exists()
    assert not (tmp_path / "workspace_effect_receipt.json").exists()


def test_workspace_rollback_action_restores_exact_target_and_preserves_sibling(tmp_path: Path) -> None:
    update = run_builtin_local_effect_runner_wing(
        action_kind="workspace_scoped_file_update",
        workspace_root=tmp_path,
        relative_target_path="demo.txt",
        payload_text="hello",
    )
    assert update.result and update.result.host_mutation_performed
    sibling = tmp_path / "sibling.txt"
    sibling.write_text("keep", encoding="utf-8")
    records = run_builtin_local_effect_runner_wing(
        action_kind="workspace_scoped_file_exact_rollback",
        workspace_effect_receipt_path=tmp_path / "workspace_effect_receipt.json",
        workspace_rollback_plan_path=tmp_path / "workspace_rollback_plan.json",
        workspace_root_scope=tmp_path,
    )
    assert records.execution_receipt is not None
    assert records.result is not None
    assert records.result.workspace_scoped_file_exact_rollback_performed is True
    assert records.result.host_mutation_performed is True
    assert not (tmp_path / "demo.txt").exists()
    assert sibling.read_text(encoding="utf-8") == "keep"
    assert (tmp_path / "workspace_rollback_receipt.json").exists()


def test_workspace_update_rejects_path_traversal_via_underlying_checks(tmp_path: Path) -> None:
    records = run_builtin_local_effect_runner_wing(
        action_kind="workspace_scoped_file_update",
        workspace_root=tmp_path,
        relative_target_path="../outside.txt",
        payload_text="no",
    )
    assert records.result is not None
    assert records.result.result_status == "builtin_runner_invocation_failed"
    assert records.result.host_mutation_performed is False
    assert not (tmp_path.parent / "outside.txt").exists()
