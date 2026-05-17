from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from sentientos.workspace_file_effect import run_workspace_file_effect_wing, run_workspace_file_rollback_wing
from sentientos.workspace_file_transaction_ledger import (
    build_transaction_ledger_from_workspace_file_records,
    build_workspace_file_transaction_entry,
    build_workspace_file_transaction_ledger,
    validate_workspace_file_transaction_ledger,
    write_workspace_file_transaction_ledger_artifact,
)

pytestmark = pytest.mark.no_legacy_skip


def _effect(tmp_path: Path, payload: str = "hello"):
    return run_workspace_file_effect_wing(workspace_root=tmp_path, relative_target_path="demo.txt", payload_text=payload)


def test_workspace_ledger_builds_create_records_and_reports_rollback_pending(tmp_path: Path) -> None:
    records = _effect(tmp_path)
    bundle = build_transaction_ledger_from_workspace_file_records(
        effect_request=records.request,
        preimage=records.preimage,
        effect_result=records.result,
        effect_receipt=records.receipt,
        postcondition_check=records.postcondition,
        production_audit=records.production_audit,
        rollback_plan=records.rollback_plan,
    )
    assert bundle.ledger.metadata_only is True
    assert bundle.ledger.performs_no_new_effect is True
    assert "workspace_file_created" in bundle.lifecycle_report.present_event_kinds
    assert bundle.lifecycle_report.lifecycle_status == "workspace_file_lifecycle_rollback_pending"
    assert validate_workspace_file_transaction_ledger(bundle.ledger).ok


def test_workspace_ledger_builds_update_records(tmp_path: Path) -> None:
    (tmp_path / "demo.txt").write_text("old", encoding="utf-8")
    records = _effect(tmp_path, "new")
    bundle = build_transaction_ledger_from_workspace_file_records(
        preimage=records.preimage,
        effect_result=records.result,
        effect_receipt=records.receipt,
        postcondition_check=records.postcondition,
        production_audit=records.production_audit,
        rollback_plan=records.rollback_plan,
    )
    assert "workspace_file_updated" in bundle.lifecycle_report.present_event_kinds
    assert bundle.lifecycle_report.lifecycle_status == "workspace_file_lifecycle_rollback_pending"


def test_workspace_ledger_complete_with_rollback(tmp_path: Path) -> None:
    records = _effect(tmp_path)
    rollback = run_workspace_file_rollback_wing(effect_receipt=records.receipt, rollback_plan=records.rollback_plan)
    bundle = build_transaction_ledger_from_workspace_file_records(
        preimage=records.preimage,
        effect_receipt=records.receipt,
        postcondition_check=records.postcondition,
        production_audit=records.production_audit,
        rollback_plan=records.rollback_plan,
        rollback_result=rollback.rollback_result,
        rollback_receipt=rollback.rollback_receipt,
        rollback_postcondition_check=rollback.rollback_postcondition,
        rollback_audit=rollback.production_audit,
    )
    assert bundle.lifecycle_report.lifecycle_status == "workspace_file_lifecycle_complete_with_rollback"


def test_workspace_ledger_detects_missing_inputs_and_digest_mismatch(tmp_path: Path) -> None:
    records = _effect(tmp_path)
    missing_preimage = build_transaction_ledger_from_workspace_file_records(
        effect_receipt=records.receipt,
        postcondition_check=records.postcondition,
        production_audit=records.production_audit,
        rollback_plan=records.rollback_plan,
    )
    assert missing_preimage.lifecycle_report.lifecycle_status == "workspace_file_lifecycle_missing_preimage"
    missing_post = build_transaction_ledger_from_workspace_file_records(
        preimage=records.preimage,
        effect_receipt=records.receipt,
        production_audit=records.production_audit,
        rollback_plan=records.rollback_plan,
    )
    assert missing_post.lifecycle_report.lifecycle_status == "workspace_file_lifecycle_missing_postcondition"
    bad = replace(records.receipt, digest="sha256:" + "0" * 64)
    contradicted = build_transaction_ledger_from_workspace_file_records(
        preimage=records.preimage,
        effect_receipt=bad,
        postcondition_check=records.postcondition,
        production_audit=records.production_audit,
        rollback_plan=records.rollback_plan,
    )
    assert contradicted.lifecycle_report.lifecycle_status == "workspace_file_lifecycle_contradicted"


def test_workspace_ledger_detects_duplicate_event_kind(tmp_path: Path) -> None:
    records = _effect(tmp_path)
    entry = build_workspace_file_transaction_entry(
        transaction_id="tx",
        event_kind="workspace_file_effect_receipt_recorded",
        source_record=records.receipt,
        transaction_status="workspace_file_transaction_effect_recorded",
    )
    ledger = build_workspace_file_transaction_ledger([entry, replace(entry, previous_entry_digest=entry.digest)], transaction_id="tx")
    assert ledger.ledger_status == "workspace_file_transaction_ledger_contradicted"
    assert any("duplicate_event_kind" in code for code in ledger.open_issue_codes)


def test_workspace_ledger_artifact_writes_one_explicit_file_only(tmp_path: Path) -> None:
    records = _effect(tmp_path)
    out = tmp_path / "ledger.json"
    bundle = build_transaction_ledger_from_workspace_file_records(
        preimage=records.preimage,
        effect_receipt=records.receipt,
        postcondition_check=records.postcondition,
        production_audit=records.production_audit,
        rollback_plan=records.rollback_plan,
    )
    receipt = write_workspace_file_transaction_ledger_artifact(bundle.ledger, out, lifecycle_report=bundle.lifecycle_report)
    assert receipt.host_mutation_performed is True
    assert out.exists()
    assert (tmp_path / "demo.txt").exists()
