from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from sentientos.workspace_file_effect import (
    BLOCKED_ACTION_LABELS,
    build_workspace_file_effect_receipt,
    build_workspace_file_effect_request,
    build_workspace_file_production_audit_receipt,
    build_workspace_file_rollback_plan,
    bytes_digest,
    perform_workspace_file_effect,
    perform_workspace_file_postcondition_check,
    perform_workspace_file_rollback,
    perform_workspace_file_rollback_postcondition_check,
    summarize_workspace_file_effect_receipt,
    summarize_workspace_file_rollback_result,
    validate_workspace_file_effect_receipt,
    validate_workspace_file_effect_request,
    validate_workspace_file_effect_result,
    validate_workspace_file_production_audit_receipt,
    validate_workspace_file_rollback_receipt,
    build_workspace_file_rollback_receipt,
)

pytestmark = pytest.mark.no_legacy_skip


def _request(root: Path, target: str = "demo.txt", payload: str = "hello", **kwargs):
    return build_workspace_file_effect_request(
        request_id=kwargs.pop("request_id", "r1"),
        workspace_root=root,
        relative_target_path=target,
        payload_text=payload,
        **kwargs,
    )


def _run(root: Path, target: str = "demo.txt", payload: str = "hello", **kwargs):
    request = _request(root, target, payload, **kwargs)
    preimage, result = perform_workspace_file_effect(request)
    receipt = build_workspace_file_effect_receipt(request, preimage, result)
    postcondition = perform_workspace_file_postcondition_check(receipt)
    plan = build_workspace_file_rollback_plan(receipt, preimage)
    audit = build_workspace_file_production_audit_receipt(receipt, postcondition, plan)
    return request, preimage, result, receipt, postcondition, plan, audit


def test_request_rejects_root_absolute_path_traversal_and_outside(tmp_path: Path) -> None:
    root_req = _request(Path("/"), "demo.txt")
    assert not validate_workspace_file_effect_request(root_req).ok
    assert "root_workspace_rejected" in validate_workspace_file_effect_request(root_req).findings
    absolute = _request(tmp_path, "/tmp/outside.txt")
    assert "absolute_target_path" in validate_workspace_file_effect_request(absolute).findings
    traversal = _request(tmp_path, "../outside.txt")
    assert "path_traversal" in validate_workspace_file_effect_request(traversal).findings
    outside = build_workspace_file_effect_request(request_id="r", workspace_root=tmp_path, relative_target_path="link/out.txt", payload_text="x")
    (tmp_path / "link").symlink_to(tmp_path.parent, target_is_directory=True)
    assert "target_outside_workspace" in validate_workspace_file_effect_request(outside).findings


def test_rejects_symlink_and_directory_targets(tmp_path: Path) -> None:
    (tmp_path / "real.txt").write_text("x", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(tmp_path / "real.txt")
    _, _, result, _, _, _, _ = _run(tmp_path, "link.txt")
    assert result.effect_status == "workspace_file_effect_blocked"
    assert "symlink_target_write" in result.warning_codes
    (tmp_path / "dir").mkdir()
    _, _, dir_result, _, _, _, _ = _run(tmp_path, "dir")
    assert dir_result.effect_status == "workspace_file_effect_blocked"
    assert "directory_target_write" in dir_result.warning_codes


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    request = _request(tmp_path)
    preimage, result = perform_workspace_file_effect(request, dry_run=True)
    assert not (tmp_path / "demo.txt").exists()
    assert preimage.host_mutation_performed is False
    assert result.real_effect_performed is False
    assert result.host_mutation_performed is False


def test_create_mode_writes_one_file_and_receipt_flags(tmp_path: Path) -> None:
    _, preimage, result, receipt, postcondition, plan, audit = _run(tmp_path)
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "hello"
    assert preimage.preimage_status == "workspace_file_preimage_absent"
    assert result.created_new_file is True and result.replaced_existing_file is False
    assert receipt.real_effect_receipt_created is True
    assert receipt.host_mutation_performed is True
    assert postcondition.postcondition_status == "workspace_file_postcondition_passed"
    assert plan.rollback_strategy == "remove_created_exact_target"
    assert audit.audit_for_workspace_file_effect_only is True
    assert validate_workspace_file_effect_result(result).ok
    assert validate_workspace_file_effect_receipt(receipt).ok
    assert validate_workspace_file_production_audit_receipt(audit).ok


def test_update_captures_preimage_and_allow_replace_false_blocks(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("old", encoding="utf-8")
    _, preimage, result, receipt, _, plan, _ = _run(tmp_path, payload="new")
    assert target.read_text(encoding="utf-8") == "new"
    assert preimage.preimage_status == "workspace_file_preimage_captured"
    assert preimage.preimage_digest == bytes_digest(b"old")
    assert preimage.preimage_bytes_base64 is not None
    assert result.created_new_file is False and result.replaced_existing_file is True
    assert receipt.effect_domain == "workspace_file_replace_effect"
    assert plan.rollback_strategy == "restore_exact_preimage"
    blocked_request = _request(tmp_path, payload="blocked", request_id="r2", allow_replace=False)
    _, blocked = perform_workspace_file_effect(blocked_request)
    assert blocked.effect_status == "workspace_file_effect_blocked"
    assert target.read_text(encoding="utf-8") == "new"


def test_rollback_created_file_removes_exact_target_and_preserves_sibling(tmp_path: Path) -> None:
    sibling = tmp_path / "sibling.txt"
    sibling.write_text("keep", encoding="utf-8")
    _, _, _, _, _, plan, _ = _run(tmp_path, "created.txt", "payload")
    rollback = perform_workspace_file_rollback(plan)
    receipt = build_workspace_file_rollback_receipt(plan, rollback)
    check = perform_workspace_file_rollback_postcondition_check(plan, receipt)
    assert rollback.rollback_status == "workspace_file_rollback_created_file_removed"
    assert rollback.file_delete_performed is True
    assert rollback.directory_cleanup_performed is False
    assert rollback.recursive_delete_performed is False
    assert rollback.wildcard_delete_performed is False
    assert rollback.unrelated_file_delete_performed is False
    assert not (tmp_path / "created.txt").exists()
    assert sibling.read_text(encoding="utf-8") == "keep"
    assert check.postcondition_status == "workspace_file_postcondition_passed"
    assert validate_workspace_file_rollback_receipt(receipt).ok


def test_rollback_update_restores_exact_preimage_and_preserves_sibling(tmp_path: Path) -> None:
    (tmp_path / "demo.txt").write_text("old", encoding="utf-8")
    (tmp_path / "sibling.txt").write_text("keep", encoding="utf-8")
    _, _, _, _, _, plan, _ = _run(tmp_path, "demo.txt", "new")
    rollback = perform_workspace_file_rollback(plan)
    assert rollback.rollback_status == "workspace_file_rollback_preimage_restored"
    assert rollback.local_file_write_performed is True
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "old"
    assert (tmp_path / "sibling.txt").read_text(encoding="utf-8") == "keep"


def test_rollback_refuses_digest_mismatch(tmp_path: Path) -> None:
    _, _, _, _, _, plan, _ = _run(tmp_path, "demo.txt", "new")
    (tmp_path / "demo.txt").write_text("tampered", encoding="utf-8")
    rollback = perform_workspace_file_rollback(plan)
    assert rollback.rollback_status == "workspace_file_rollback_digest_mismatch"
    assert rollback.real_rollback_performed is False
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "tampered"


def test_validation_rejects_forbidden_flags_and_cleanup_claims(tmp_path: Path) -> None:
    request = _request(tmp_path)
    bad = replace(request, network_performed=True)
    assert not validate_workspace_file_effect_request(bad).ok
    _, _, result, receipt, _, _, _ = _run(tmp_path, "demo.txt", "x")
    bad_receipt = replace(receipt, recursive_delete_performed=True)
    assert not validate_workspace_file_effect_receipt(bad_receipt).ok
    assert set(BLOCKED_ACTION_LABELS).issubset(set(receipt.blocked_actions))


def test_digests_deterministic_and_change_on_meaningful_metadata(tmp_path: Path) -> None:
    first = _request(tmp_path, payload="a")
    second = _request(tmp_path, payload="a")
    changed = _request(tmp_path, payload="b")
    assert first.digest == second.digest
    assert first.digest != changed.digest


def test_summaries_state_single_file_workspace_effect_only(tmp_path: Path) -> None:
    _, _, _, receipt, _, _, _ = _run(tmp_path, "demo.txt", "x")
    summary = summarize_workspace_file_effect_receipt(receipt)
    assert summary["workspace_scoped"] is True
    assert summary["single_target_only"] is True
    assert summary["general_filesystem_access_performed"] is False
    _, _, _, _, _, plan, _ = _run(tmp_path, "rollback.txt", "x", request_id="r2")
    rollback = perform_workspace_file_rollback(plan)
    rollback_summary = summarize_workspace_file_rollback_result(rollback)
    assert rollback_summary["directory_cleanup_performed"] is False
    assert rollback_summary["recursive_delete_performed"] is False
    assert rollback_summary["wildcard_delete_performed"] is False
    assert rollback_summary["unrelated_file_delete_performed"] is False
