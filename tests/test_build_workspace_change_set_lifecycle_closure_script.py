from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from scripts import build_workspace_change_set_lifecycle_closure as cli
from sentientos.workspace_change_set_execution import run_workspace_change_set_execution_wing
from sentientos.workspace_change_set_execution_verification import verify_workspace_change_set_execution
from sentientos.workspace_change_set_preflight import (
    build_workspace_change_set_manifest,
    build_workspace_change_set_preflight_report,
    build_workspace_change_set_rollback_plan,
    build_workspace_change_set_transaction_plan,
    build_workspace_change_target_declaration,
    preflight_workspace_change_target,
)


def _evidence(path: Path) -> Path:
    targets = (build_workspace_change_target_declaration(relative_target_path="a.txt", payload_text="alpha"),)
    manifest = build_workspace_change_set_manifest(workspace_root=path, targets=targets)
    preflights = tuple(preflight_workspace_change_target(workspace_root=path, target=target) for target in targets)
    report = build_workspace_change_set_preflight_report(manifest=manifest, target_preflights=preflights)
    rollback_plan = build_workspace_change_set_rollback_plan(manifest=manifest, preflight_report=report, target_preflights=preflights)
    transaction_plan = build_workspace_change_set_transaction_plan(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    verified = verify_workspace_change_set_execution(
        manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan,
        execution_request=wing.request, execution_result=wing.execution_result, execution_receipt=wing.execution_receipt,
        rollback_result=wing.rollback_result, rollback_receipt=wing.rollback_receipt, ledger=wing.ledger, closure_report=wing.closure_report,
    )
    payload = {
        "manifest": manifest.to_dict(),
        "preflight_report": report.to_dict(),
        "rollback_plan": rollback_plan.to_dict(),
        "transaction_plan": transaction_plan.to_dict(),
        "execution_request": wing.request.to_dict(),
        "execution_result": wing.execution_result.to_dict(),
        "execution_receipt": wing.execution_receipt.to_dict(),
        "rollback_result": wing.rollback_result.to_dict(),
        "rollback_receipt": None,
        "ledger": wing.ledger.to_dict(),
        "closure_report": wing.closure_report.to_dict(),
        "verification_request": verified.request.to_dict(),
        "verification_result": verified.verification_result.to_dict(),
    }
    evidence = path / "closure-evidence.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    return evidence


def test_cli_builds_closure_from_supplied_evidence_json_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    evidence = _evidence(tmp_path)
    assert cli.main(["--evidence", str(evidence), "--summary"]) == 0
    out = capsys.readouterr().out
    assert "lifecycle_closure_status: lifecycle_closed_clean" in out
    assert "verification_replay_invoked: false" in out


def test_cli_optional_output_writes_closure_artifact(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    output = tmp_path / "closure.json"
    assert cli.main(["--evidence", str(evidence), "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["lifecycle_closure_status"] == "lifecycle_closed_clean"
    assert payload["metadata_only"] is True
