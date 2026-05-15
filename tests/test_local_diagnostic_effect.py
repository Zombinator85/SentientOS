from __future__ import annotations

from pathlib import Path

import pytest

from sentientos.local_diagnostic_effect import (
    build_local_diagnostic_effect_receipt,
    build_local_diagnostic_effect_request,
    build_local_diagnostic_rollback_plan,
    build_local_diagnostic_rollback_receipt,
    build_local_diagnostic_production_audit_receipt,
    local_diagnostic_effect_request_digest,
    perform_local_diagnostic_effect,
    perform_local_diagnostic_postcondition_check,
    run_local_diagnostic_effect_wing,
    summarize_local_diagnostic_effect_receipt,
    summarize_local_diagnostic_effect_result,
    summarize_local_diagnostic_rollback_plan,
    validate_local_diagnostic_effect_receipt,
    validate_local_diagnostic_effect_request,
)

pytestmark = pytest.mark.no_legacy_skip


def test_request_validation_rejects_unsafe_output_and_names(tmp_path: Path) -> None:
    cases = [
        {"output_dir": "", "artifact_name": "ok.json", "finding": "empty_output_dir"},
        {"output_dir": "/", "artifact_name": "ok.json", "finding": "output_dir_is_filesystem_root"},
        {"output_dir": tmp_path, "artifact_name": "nested/name.json", "finding": "artifact_name_contains_path_separator"},
        {"output_dir": tmp_path, "artifact_name": "/tmp/name.json", "finding": "absolute_artifact_name"},
        {"output_dir": tmp_path, "artifact_name": "..", "finding": "artifact_name_path_traversal"},
    ]
    for case in cases:
        req = build_local_diagnostic_effect_request(output_dir=case["output_dir"], artifact_name=case["artifact_name"])
        validation = validate_local_diagnostic_effect_request(req)
        assert not validation.ok
        assert case["finding"] in validation.findings


def test_dry_run_does_not_write_artifact(tmp_path: Path) -> None:
    records = run_local_diagnostic_effect_wing(output_dir=tmp_path, dry_run=True)
    assert records.result.effect_status == "local_diagnostic_effect_requested"
    assert records.result.real_effect_performed is False
    assert not (tmp_path / "sentientos_local_diagnostic_effect.json").exists()


def test_real_mode_writes_one_artifact_and_receipts_are_narrow(tmp_path: Path) -> None:
    out = tmp_path / "effect-out"
    records = run_local_diagnostic_effect_wing(output_dir=out)
    target = out / "sentientos_local_diagnostic_effect.json"
    assert target.exists()
    assert [p.name for p in out.iterdir()] == ["sentientos_local_diagnostic_effect.json"]
    result_summary = summarize_local_diagnostic_effect_result(records.result)
    assert result_summary["real_effect_performed"] is True
    assert result_summary["local_file_write_performed"] is True
    assert result_summary["host_mutation_performed"] is True
    receipt_summary = summarize_local_diagnostic_effect_receipt(records.receipt)
    assert receipt_summary["real_effect_receipt_created"] is True
    for flag in [
        "fan_pwm_write_performed",
        "thermal_actuation_performed",
        "power_profile_mutation_performed",
        "service_restart_performed",
        "file_cleanup_performed",
        "network_performed",
        "provider_invocation_performed",
        "prompt_assembly_performed",
    ]:
        assert receipt_summary[flag] is False
    assert records.postcondition_check.postcondition_status == "local_diagnostic_postcondition_passed"
    assert records.postcondition_check.output_path == str(target)
    assert records.rollback_plan.rollback_plan_only is True
    assert records.rollback_receipt.real_rollback_performed is False
    assert records.rollback_receipt.file_delete_performed is False
    assert target.exists()
    assert records.production_audit_receipt.production_audit_receipt_created is True
    assert records.production_audit_receipt.audit_for_local_diagnostic_effect_only is True


def test_overwrite_requires_force_and_force_only_targets_artifact(tmp_path: Path) -> None:
    first = run_local_diagnostic_effect_wing(output_dir=tmp_path)
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("keep", encoding="utf-8")
    second = run_local_diagnostic_effect_wing(output_dir=tmp_path)
    assert second.result.effect_status == "local_diagnostic_effect_blocked"
    assert second.result.real_effect_performed is False
    forced = run_local_diagnostic_effect_wing(output_dir=tmp_path, force_overwrite=True)
    assert forced.result.effect_status == "local_diagnostic_effect_performed"
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert first.result.output_path == forced.result.output_path


def test_source_admission_blocks_bad_status_and_non_low_risk(tmp_path: Path) -> None:
    blocked = {"bundle_id": "b", "digest": "sha256:x", "bundle_status": "real_effect_admission_blocked", "admission_domain": "diagnostics_real_effect_candidate"}
    req = build_local_diagnostic_effect_request(output_dir=tmp_path, source_real_effect_admission_bundle=blocked)
    assert req.request_status == "local_diagnostic_effect_blocked"
    assert "source_real_effect_admission_not_eligible" in req.warning_codes
    non_low = {"bundle_id": "b", "digest": "sha256:x", "bundle_status": "real_effect_admission_eligible_for_planning", "admission_domain": "future_cooling_real_effect_candidate"}
    req2 = build_local_diagnostic_effect_request(output_dir=tmp_path, source_real_effect_admission_bundle=non_low)
    assert req2.request_status == "local_diagnostic_effect_blocked"
    assert "source_real_effect_admission_domain_not_low_risk" in req2.warning_codes


def test_digests_are_deterministic_and_change_on_metadata(tmp_path: Path) -> None:
    a = build_local_diagnostic_effect_request(output_dir=tmp_path, artifact_payload_summary="a")
    b = build_local_diagnostic_effect_request(output_dir=tmp_path, artifact_payload_summary="a")
    c = build_local_diagnostic_effect_request(output_dir=tmp_path, artifact_payload_summary="c")
    assert a.digest == b.digest
    assert local_diagnostic_effect_request_digest(a) == a.digest
    assert a.digest != c.digest


def test_validators_accept_success_records_and_reject_forbidden_claims(tmp_path: Path) -> None:
    request = build_local_diagnostic_effect_request(output_dir=tmp_path)
    result = perform_local_diagnostic_effect(request)
    receipt = build_local_diagnostic_effect_receipt(request, result)
    check = perform_local_diagnostic_postcondition_check(receipt)
    plan = build_local_diagnostic_rollback_plan(receipt)
    rollback = build_local_diagnostic_rollback_receipt(plan)
    audit = build_local_diagnostic_production_audit_receipt(receipt, check, plan, rollback)
    assert validate_local_diagnostic_effect_request(request).ok
    assert validate_local_diagnostic_effect_receipt(receipt).ok
    assert summarize_local_diagnostic_rollback_plan(plan)["rollback_plan_only"] is True
    bad = receipt.to_dict() | {"network_performed": True}
    assert not validate_local_diagnostic_effect_receipt(bad).ok
    assert audit.host_mutation_performed is False
