from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.workspace_change_set_preflight import (
    WorkspaceChangeSetPolicy,
    build_default_workspace_change_set_policy,
    build_workspace_change_set_manifest,
    build_workspace_change_target_declaration,
    payload_digest,
    run_workspace_change_set_preflight_wing,
    validate_workspace_change_set_manifest,
    validate_workspace_change_set_preflight_report,
    validate_workspace_change_set_rollback_plan,
    validate_workspace_change_set_transaction_plan,
)

pytestmark = pytest.mark.no_legacy_skip


def _decl(path: str, payload: str = "hello", *, operation: str = "create_file", allow_replace: bool = True):
    return build_workspace_change_target_declaration(
        relative_target_path=path,
        payload_text=payload,
        operation=operation,
        allow_replace=allow_replace,
    )


def _run(tmp_path, targets, policy=None):
    return run_workspace_change_set_preflight_wing(workspace_root=tmp_path, targets=targets, policy=policy)


def test_one_safe_create_target_passes_without_writing(tmp_path):
    wing = _run(tmp_path, [_decl("demo.txt", "hello")])
    assert wing["preflight_report"]["report_status"] == "workspace_change_set_preflight_passed"
    assert wing["rollback_plan"]["rollback_plan_status"] == "workspace_change_set_rollback_plan_ready"
    assert wing["transaction_plan"]["transaction_plan_status"] == "workspace_change_set_transaction_plan_ready"
    assert wing["target_write_performed"] is False
    assert wing["target_rollback_performed"] is False
    assert wing["runner_orchestrator_invoked"] is False
    assert not (tmp_path / "demo.txt").exists()


def test_multiple_explicit_safe_targets_pass(tmp_path):
    wing = _run(tmp_path, [_decl("a.txt", "a"), _decl("b.txt", "b")])
    assert wing["manifest"]["target_count"] == 2
    assert wing["summary"]["prepares_multi_target_changes"] is True
    assert wing["summary"]["executes_multi_target_changes"] is False
    assert wing["preflight_report"]["report_status"] == "workspace_change_set_preflight_passed"


@pytest.mark.parametrize(
    "target_path,risk",
    [
        ("/abs.txt", "absolute_target_path"),
        ("../escape.txt", "path_traversal"),
        ("wild*.txt", "wildcard_target_path"),
    ],
)
def test_unsafe_target_paths_block(tmp_path, target_path, risk):
    wing = _run(tmp_path, [_decl(target_path)])
    assert wing["preflight_report"]["report_status"] == "workspace_change_set_preflight_blocked"
    assert risk in wing["manifest"]["risk_codes"] or risk in wing["target_preflights"][0]["risk_codes"]


def test_duplicate_normalized_targets_block(tmp_path):
    wing = _run(tmp_path, [_decl("demo.txt"), _decl("./demo.txt")])
    assert wing["manifest"]["manifest_status"] == "workspace_change_set_manifest_blocked"
    assert wing["preflight_report"]["duplicate_target_ids"]
    assert "duplicate_target_path" in wing["preflight_report"]["risk_codes"]


def test_target_count_and_payload_limits_block(tmp_path):
    policy = WorkspaceChangeSetPolicy(max_targets=1, max_payload_bytes_per_target=4, max_total_payload_bytes=6)
    wing = _run(tmp_path, [_decl("a.txt", "12345"), _decl("b.txt", "12345")], policy)
    risks = set(wing["manifest"]["risk_codes"])
    assert {"target_count_over_limit", "payload_bytes_over_per_target_limit", "total_payload_bytes_over_limit"}.issubset(risks)
    assert wing["preflight_report"]["report_status"] == "workspace_change_set_preflight_blocked"


def test_root_workspace_blocks():
    wing = run_workspace_change_set_preflight_wing(workspace_root="/", targets=[_decl("demo.txt")])
    assert "root_workspace_refused" in wing["manifest"]["risk_codes"]
    assert wing["preflight_report"]["report_status"] == "workspace_change_set_preflight_blocked"


def test_missing_parent_update_missing_target_existing_create_blocks(tmp_path):
    (tmp_path / "existing.txt").write_text("old", encoding="utf-8")
    cases = [
        (_decl("missing/child.txt"), "workspace_change_target_preflight_missing_parent"),
        (_decl("missing.txt", operation="update_file"), "workspace_change_target_preflight_missing_target"),
        (_decl("existing.txt", allow_replace=False), "workspace_change_target_preflight_blocked"),
    ]
    for target, status in cases:
        wing = _run(tmp_path, [target])
        assert wing["target_preflights"][0]["preflight_status"] == status
        assert wing["preflight_report"]["report_status"] == "workspace_change_set_preflight_blocked"


def test_symlink_and_directory_targets_block(tmp_path):
    (tmp_path / "dir").mkdir()
    symlink = tmp_path / "link.txt"
    try:
        symlink.symlink_to(tmp_path / "real.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    dir_wing = _run(tmp_path, [_decl("dir", operation="replace_file")])
    link_wing = _run(tmp_path, [_decl("link.txt", operation="replace_file")])
    assert dir_wing["target_preflights"][0]["preflight_status"] == "workspace_change_target_preflight_directory"
    assert link_wing["target_preflights"][0]["preflight_status"] == "workspace_change_target_preflight_symlink"


def test_existing_digest_captured_read_only_and_only_declared_target(tmp_path):
    existing = tmp_path / "existing.txt"
    other = tmp_path / "other.txt"
    existing.write_text("existing\n", encoding="utf-8")
    other.write_text("other\n", encoding="utf-8")
    before_other = other.read_text(encoding="utf-8")
    wing = _run(tmp_path, [_decl("existing.txt", "updated", operation="update_file")])
    preflight = wing["target_preflights"][0]
    assert preflight["existing_digest"] == payload_digest("existing\n")
    assert preflight["existing_byte_count"] == len("existing\n".encode())
    assert other.read_text(encoding="utf-8") == before_other
    assert existing.read_text(encoding="utf-8") == "existing\n"


def test_plans_are_metadata_only_and_summaries_identify_boundaries(tmp_path):
    wing = _run(tmp_path, [_decl("demo.txt")])
    rollback = wing["rollback_plan"]
    transaction = wing["transaction_plan"]
    summary = wing["summary"]
    assert rollback["metadata_only"] is True
    assert rollback["rollback_not_performed"] is True
    assert transaction["metadata_only"] is True
    assert transaction["execution_not_started"] is True
    assert summary["reads_only_declared_targets"] is True
    assert summary["target_writes"] is False
    assert summary["rollback_performed"] is False


def test_validation_rejects_forbidden_effect_claims(tmp_path):
    wing = _run(tmp_path, [_decl("demo.txt")])
    mod = __import__("sentientos.workspace_change_set_preflight", fromlist=["WorkspaceChangeSetPreflightReport"])
    report = replace(mod.WorkspaceChangeSetPreflightReport(**wing["preflight_report"]), target_write_performed=True)
    rollback = replace(mod.WorkspaceChangeSetRollbackPlan(**wing["rollback_plan"]), target_rollback_performed=True)
    transaction = replace(mod.WorkspaceChangeSetTransactionPlan(**wing["transaction_plan"]), host_mutation_performed=True)
    original_manifest = build_workspace_change_set_manifest(workspace_root=tmp_path, targets=[_decl("demo.txt")])
    manifest = replace(original_manifest, subprocess_used=True)
    assert not validate_workspace_change_set_preflight_report(report).ok
    assert not validate_workspace_change_set_rollback_plan(rollback).ok
    assert not validate_workspace_change_set_transaction_plan(transaction).ok
    assert not validate_workspace_change_set_manifest(manifest).ok


def test_digests_are_deterministic_and_change_on_metadata(tmp_path):
    first = build_workspace_change_set_manifest(workspace_root=tmp_path, targets=[_decl("a.txt", "a")])
    second = build_workspace_change_set_manifest(workspace_root=tmp_path, targets=[_decl("a.txt", "a")])
    changed = build_workspace_change_set_manifest(workspace_root=tmp_path, targets=[_decl("a.txt", "b")])
    assert first.digest == second.digest
    assert first.digest != changed.digest
