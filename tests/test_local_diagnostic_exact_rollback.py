from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from sentientos.local_diagnostic_effect import (
    build_local_diagnostic_exact_rollback_request,
    local_diagnostic_exact_rollback_request_digest,
    perform_local_diagnostic_exact_rollback,
    run_local_diagnostic_effect_wing,
    run_local_diagnostic_exact_rollback_wing,
    summarize_local_diagnostic_exact_rollback_result,
    summarize_local_diagnostic_exact_rollback_receipt,
    validate_local_diagnostic_exact_rollback_receipt,
    validate_local_diagnostic_exact_rollback_request,
    validate_local_diagnostic_exact_rollback_result,
    validate_local_diagnostic_rollback_audit_receipt,
    validate_local_diagnostic_rollback_postcondition_check,
)

pytestmark = pytest.mark.no_legacy_skip


def _effect(tmp_path: Path):
    return run_local_diagnostic_effect_wing(output_dir=tmp_path / "effect")


def test_request_validation_rejects_root_and_outside_scope(tmp_path: Path) -> None:
    records = _effect(tmp_path)
    root = build_local_diagnostic_exact_rollback_request(records.receipt, records.rollback_plan, output_dir_scope="/")
    assert not validate_local_diagnostic_exact_rollback_request(root).ok
    assert "output_dir_scope_is_filesystem_root" in root.warning_codes
    outside = build_local_diagnostic_exact_rollback_request(records.receipt, records.rollback_plan, output_dir_scope=tmp_path / "other")
    assert not validate_local_diagnostic_exact_rollback_request(outside).ok
    assert "output_path_outside_scope" in outside.warning_codes


def test_rejects_directory_target_symlink_digest_mismatch_and_bad_plan(tmp_path: Path) -> None:
    records = _effect(tmp_path)
    artifact = Path(records.receipt.output_path)
    artifact.unlink()
    artifact.mkdir()
    request = build_local_diagnostic_exact_rollback_request(records.receipt, records.rollback_plan, output_dir_scope=artifact.parent)
    result = perform_local_diagnostic_exact_rollback(request)
    assert result.rollback_status == "local_diagnostic_exact_rollback_blocked"
    assert "output_path_is_directory" in result.warning_codes
    artifact.rmdir()
    sibling = artifact.parent / "sibling.txt"
    sibling.write_text("keep", encoding="utf-8")
    artifact.symlink_to(sibling)
    result = perform_local_diagnostic_exact_rollback(request)
    assert result.rollback_status == "local_diagnostic_exact_rollback_blocked"
    assert "output_path_is_symlink" in result.warning_codes
    artifact.unlink()
    artifact.write_text("changed", encoding="utf-8")
    result = perform_local_diagnostic_exact_rollback(request)
    assert result.rollback_status == "local_diagnostic_exact_rollback_digest_mismatch"
    bad_plan = records.rollback_plan.to_dict() | {"receipt_id": "other", "output_path": str(artifact.parent / "other.json")}
    bad_request = build_local_diagnostic_exact_rollback_request(records.receipt, bad_plan, output_dir_scope=artifact.parent)
    assert not validate_local_diagnostic_exact_rollback_request(bad_request).ok
    assert "rollback_plan_receipt_mismatch" in bad_request.warning_codes
    assert "rollback_plan_output_path_mismatch" in bad_request.warning_codes


def test_dry_run_deletes_nothing_but_real_rollback_deletes_only_artifact(tmp_path: Path) -> None:
    records = _effect(tmp_path)
    artifact = Path(records.receipt.output_path)
    sibling = artifact.parent / "sibling.txt"
    child_dir = artifact.parent / "kept-dir"
    sibling.write_text("keep", encoding="utf-8")
    child_dir.mkdir()
    dry = run_local_diagnostic_exact_rollback_wing(records.receipt, records.rollback_plan, output_dir_scope=artifact.parent, dry_run=True)
    assert dry.result.real_rollback_performed is False
    assert artifact.exists()
    real = run_local_diagnostic_exact_rollback_wing(records.receipt, records.rollback_plan, output_dir_scope=artifact.parent)
    assert not artifact.exists()
    assert sibling.read_text(encoding="utf-8") == "keep"
    assert child_dir.is_dir()
    result_summary = summarize_local_diagnostic_exact_rollback_result(real.result)
    assert result_summary["real_rollback_performed"] is True
    assert result_summary["file_delete_performed"] is True
    assert result_summary["host_mutation_performed"] is True
    for flag in ["directory_cleanup_performed", "recursive_delete_performed", "wildcard_delete_performed", "unrelated_file_delete_performed"]:
        assert result_summary[flag] is False
    receipt_summary = summarize_local_diagnostic_exact_rollback_receipt(real.receipt)
    assert receipt_summary["exact_artifact_only"] is True
    assert real.postcondition_check.postcondition_status == "local_diagnostic_rollback_postcondition_passed"
    assert real.postcondition_check.observed_exists is False
    assert real.audit_receipt.audit_for_exact_local_diagnostic_artifact_only is True


def test_allow_missing_records_no_deletion(tmp_path: Path) -> None:
    records = _effect(tmp_path)
    artifact = Path(records.receipt.output_path)
    artifact.unlink()
    rollback = run_local_diagnostic_exact_rollback_wing(records.receipt, records.rollback_plan, output_dir_scope=artifact.parent, allow_missing_artifact=True)
    assert rollback.result.rollback_status == "local_diagnostic_exact_rollback_missing_artifact"
    assert rollback.result.real_rollback_performed is False
    assert rollback.result.file_delete_performed is False
    assert rollback.postcondition_check.postcondition_status == "local_diagnostic_rollback_postcondition_passed"


def test_validation_rejects_forbidden_claims_and_digest_changes(tmp_path: Path) -> None:
    records = _effect(tmp_path)
    request = build_local_diagnostic_exact_rollback_request(records.receipt, records.rollback_plan, output_dir_scope=Path(records.receipt.output_path).parent)
    same = build_local_diagnostic_exact_rollback_request(records.receipt, records.rollback_plan, output_dir_scope=Path(records.receipt.output_path).parent)
    changed = replace(request, allow_missing_artifact=True, digest="")
    assert request.digest == same.digest
    assert request.digest == local_diagnostic_exact_rollback_request_digest(request)
    assert request.digest != local_diagnostic_exact_rollback_request_digest(changed)
    result = perform_local_diagnostic_exact_rollback(request, dry_run=True)
    assert validate_local_diagnostic_exact_rollback_result(result).ok
    for flag in [
        "directory_cleanup_performed",
        "recursive_delete_performed",
        "wildcard_delete_performed",
        "unrelated_file_delete_performed",
        "fan_pwm_write_performed",
        "thermal_actuation_performed",
        "power_profile_mutation_performed",
        "service_restart_performed",
        "package_install_performed",
        "driver_install_performed",
        "network_performed",
        "provider_invocation_performed",
        "prompt_assembly_performed",
    ]:
        bad = result.to_dict() | {flag: True}
        assert not validate_local_diagnostic_exact_rollback_result(bad).ok
    real = run_local_diagnostic_exact_rollback_wing(records.receipt, records.rollback_plan, output_dir_scope=Path(records.receipt.output_path).parent)
    assert validate_local_diagnostic_exact_rollback_receipt(real.receipt).ok
    assert validate_local_diagnostic_rollback_postcondition_check(real.postcondition_check).ok
    assert validate_local_diagnostic_rollback_audit_receipt(real.audit_receipt).ok
    assert not validate_local_diagnostic_exact_rollback_receipt(real.receipt.to_dict() | {"recursive_delete_performed": True}).ok
