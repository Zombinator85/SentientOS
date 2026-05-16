from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from sentientos.local_diagnostic_effect import run_local_diagnostic_effect_wing, run_local_diagnostic_exact_rollback_wing
from sentientos.local_effect_transaction_ledger import (
    build_local_effect_transaction_lifecycle_report,
    build_local_effect_transaction_ledger,
    build_transaction_ledger_from_local_diagnostic_records,
    local_effect_transaction_ledger_digest,
    validate_local_effect_transaction_ledger,
    validate_local_effect_transaction_lifecycle_report,
    write_local_effect_transaction_ledger_artifact,
)

pytestmark = pytest.mark.no_legacy_skip


def _effect_records(tmp_path: Path):
    return run_local_diagnostic_effect_wing(output_dir=tmp_path / "effect")


def test_ledger_builds_from_effect_records_and_marks_rollback_pending(tmp_path: Path) -> None:
    records = _effect_records(tmp_path)
    bundle = build_transaction_ledger_from_local_diagnostic_records(
        effect_receipt=records.receipt,
        postcondition_check=records.postcondition_check,
        production_audit=records.production_audit_receipt,
        rollback_plan=records.rollback_plan,
    )
    assert bundle.ledger.ledger_status == "local_effect_transaction_ledger_incomplete"
    assert bundle.ledger.current_transaction_status == "local_effect_transaction_incomplete"
    assert "rollback_pending" in bundle.ledger.open_issue_codes
    assert bundle.lifecycle_report.lifecycle_status == "local_effect_lifecycle_rollback_pending"
    assert bundle.ledger.host_mutation_performed is False
    assert bundle.lifecycle_report.host_mutation_performed is False
    assert validate_local_effect_transaction_ledger(bundle.ledger).ok
    assert validate_local_effect_transaction_lifecycle_report(bundle.lifecycle_report).ok


def test_full_effect_and_rollback_records_close_transaction(tmp_path: Path) -> None:
    records = _effect_records(tmp_path)
    rollback = run_local_diagnostic_exact_rollback_wing(records.receipt, records.rollback_plan, output_dir_scope=tmp_path / "effect")
    bundle = build_transaction_ledger_from_local_diagnostic_records(
        effect_receipt=records.receipt,
        postcondition_check=records.postcondition_check,
        production_audit=records.production_audit_receipt,
        rollback_plan=records.rollback_plan,
        exact_rollback_receipt=rollback.receipt,
        rollback_postcondition_check=rollback.postcondition_check,
        rollback_audit=rollback.audit_receipt,
    )
    assert bundle.ledger.ledger_status == "local_effect_transaction_ledger_current"
    assert bundle.ledger.current_transaction_status == "local_effect_transaction_closed"
    assert bundle.lifecycle_report.lifecycle_status == "local_effect_lifecycle_complete_with_rollback"
    assert bundle.lifecycle_report.closure_codes


def test_missing_postcondition_and_audit_are_classified(tmp_path: Path) -> None:
    records = _effect_records(tmp_path)
    missing_post = build_transaction_ledger_from_local_diagnostic_records(
        effect_receipt=records.receipt,
        production_audit=records.production_audit_receipt,
        rollback_plan=records.rollback_plan,
    )
    assert missing_post.lifecycle_report.lifecycle_status == "local_effect_lifecycle_missing_postcondition"
    missing_audit = build_transaction_ledger_from_local_diagnostic_records(
        effect_receipt=records.receipt,
        postcondition_check=records.postcondition_check,
        rollback_plan=records.rollback_plan,
    )
    assert missing_audit.lifecycle_report.lifecycle_status == "local_effect_lifecycle_missing_audit"


def test_missing_rollback_postcondition_and_audit_are_classified(tmp_path: Path) -> None:
    records = _effect_records(tmp_path)
    rollback = run_local_diagnostic_exact_rollback_wing(records.receipt, records.rollback_plan, output_dir_scope=tmp_path / "effect")
    missing_post = build_transaction_ledger_from_local_diagnostic_records(
        effect_receipt=records.receipt,
        postcondition_check=records.postcondition_check,
        production_audit=records.production_audit_receipt,
        rollback_plan=records.rollback_plan,
        exact_rollback_receipt=rollback.receipt,
        rollback_audit=rollback.audit_receipt,
    )
    assert missing_post.lifecycle_report.lifecycle_status == "local_effect_lifecycle_rollback_incomplete"
    assert "diagnostic_rollback_postcondition_passed" in missing_post.lifecycle_report.missing_event_kinds
    missing_audit = build_transaction_ledger_from_local_diagnostic_records(
        effect_receipt=records.receipt,
        postcondition_check=records.postcondition_check,
        production_audit=records.production_audit_receipt,
        rollback_plan=records.rollback_plan,
        exact_rollback_receipt=rollback.receipt,
        rollback_postcondition_check=rollback.postcondition_check,
    )
    assert missing_audit.lifecycle_report.lifecycle_status == "local_effect_lifecycle_rollback_incomplete"
    assert "diagnostic_rollback_audit_recorded" in missing_audit.lifecycle_report.missing_event_kinds


def test_duplicate_event_kinds_and_digest_mismatch_are_contradictions(tmp_path: Path) -> None:
    records = _effect_records(tmp_path)
    bundle = build_transaction_ledger_from_local_diagnostic_records(effect_receipt=records.receipt, postcondition_check=records.postcondition_check, production_audit=records.production_audit_receipt, rollback_plan=records.rollback_plan)
    duplicate = build_local_effect_transaction_ledger((bundle.ledger.entries[0], bundle.ledger.entries[0]), transaction_id=bundle.ledger.transaction_id)
    assert duplicate.ledger_status == "local_effect_transaction_ledger_contradicted"
    bad_receipt = {**records.receipt.to_dict(), "digest": "bad"}
    mismatched = build_transaction_ledger_from_local_diagnostic_records(effect_receipt=bad_receipt, postcondition_check=records.postcondition_check, production_audit=records.production_audit_receipt, rollback_plan=records.rollback_plan)
    assert mismatched.ledger.ledger_status == "local_effect_transaction_ledger_contradicted"
    assert any("digest_mismatch" in code for code in mismatched.lifecycle_report.contradiction_codes)


def test_forbidden_flags_are_contradictions(tmp_path: Path) -> None:
    records = _effect_records(tmp_path)
    bad_receipt = {**records.receipt.to_dict(), "network_performed": True, "provider_invocation_performed": True, "prompt_assembly_performed": True, "subprocess_performed": True, "shell_performed": True, "fan_pwm_write_performed": True}
    bundle = build_transaction_ledger_from_local_diagnostic_records(effect_receipt=bad_receipt, postcondition_check=records.postcondition_check, production_audit=records.production_audit_receipt, rollback_plan=records.rollback_plan)
    assert bundle.ledger.ledger_status == "local_effect_transaction_ledger_contradicted"
    assert bundle.lifecycle_report.lifecycle_status == "local_effect_lifecycle_contradicted"
    assert any("forbidden_claim" in code for code in bundle.lifecycle_report.contradiction_codes)


def test_digest_chain_and_record_digests_are_deterministic(tmp_path: Path) -> None:
    records = _effect_records(tmp_path)
    first = build_transaction_ledger_from_local_diagnostic_records(effect_receipt=records.receipt, postcondition_check=records.postcondition_check, production_audit=records.production_audit_receipt, rollback_plan=records.rollback_plan)
    second = build_transaction_ledger_from_local_diagnostic_records(effect_receipt=records.receipt, postcondition_check=records.postcondition_check, production_audit=records.production_audit_receipt, rollback_plan=records.rollback_plan)
    assert [entry.digest for entry in first.ledger.entries] == [entry.digest for entry in second.ledger.entries]
    assert first.ledger.entries[1].previous_entry_digest == first.ledger.entries[0].digest
    assert first.ledger.digest == second.ledger.digest
    assert first.lifecycle_report.digest == second.lifecycle_report.digest
    changed = replace(first.ledger, warning_codes=first.ledger.warning_codes + ("changed",), digest="")
    changed = replace(changed, digest=local_effect_transaction_ledger_digest(changed.to_dict()))
    assert changed.digest != first.ledger.digest


def test_optional_artifact_write_is_explicit_and_refuses_unsafe_paths(tmp_path: Path) -> None:
    records = _effect_records(tmp_path)
    bundle = build_transaction_ledger_from_local_diagnostic_records(effect_receipt=records.receipt, postcondition_check=records.postcondition_check, production_audit=records.production_audit_receipt, rollback_plan=records.rollback_plan)
    before = set(tmp_path.rglob("*"))
    output = tmp_path / "ledger.json"
    receipt = write_local_effect_transaction_ledger_artifact(bundle.ledger, output, lifecycle_report=bundle.lifecycle_report)
    after = set(tmp_path.rglob("*"))
    assert output.exists()
    assert after - before == {output}
    assert receipt.local_file_write_performed is True
    assert receipt.host_mutation_performed is True
    with pytest.raises(ValueError):
        write_local_effect_transaction_ledger_artifact(bundle.ledger, tmp_path)
    with pytest.raises(ValueError):
        write_local_effect_transaction_ledger_artifact(bundle.ledger, Path("/"))
