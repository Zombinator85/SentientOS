from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from scripts import verify_workspace_change_set_execution as cli
from sentientos.workspace_change_set_execution import run_workspace_change_set_execution_wing
from sentientos.workspace_change_set_preflight import (
    build_workspace_change_set_manifest,
    build_workspace_change_set_preflight_report,
    build_workspace_change_set_rollback_plan,
    build_workspace_change_set_transaction_plan,
    build_workspace_change_target_declaration,
    preflight_workspace_change_target,
)


def _evidence(path: Path) -> Path:
    targets = (build_workspace_change_target_declaration(relative_target_path='a.txt', payload_text='alpha'),)
    manifest = build_workspace_change_set_manifest(workspace_root=path, targets=targets)
    preflights = tuple(preflight_workspace_change_target(workspace_root=path, target=target) for target in targets)
    report = build_workspace_change_set_preflight_report(manifest=manifest, target_preflights=preflights)
    rollback_plan = build_workspace_change_set_rollback_plan(manifest=manifest, preflight_report=report, target_preflights=preflights)
    transaction_plan = build_workspace_change_set_transaction_plan(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    payload = {
        'manifest': manifest.to_dict(),
        'preflight_report': report.to_dict(),
        'rollback_plan': rollback_plan.to_dict(),
        'transaction_plan': transaction_plan.to_dict(),
        'request': wing.request.to_dict(),
        'execution_result': wing.execution_result.to_dict(),
        'execution_receipt': wing.execution_receipt.to_dict(),
        'rollback_result': wing.rollback_result.to_dict(),
        'rollback_receipt': None,
        'ledger': wing.ledger.to_dict(),
        'closure_report': wing.closure_report.to_dict(),
    }
    evidence = path / 'evidence.json'
    evidence.write_text(json.dumps(payload), encoding='utf-8')
    return evidence


def test_cli_verification_summary_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    evidence = _evidence(tmp_path)
    assert cli.main(['--evidence', str(evidence), '--summary']) == 0
    out = capsys.readouterr().out
    assert 'verification_status: verified_clean' in out
    assert 'execution_invoked: false' in out
    assert 'rollback_invoked: false' in out


def test_cli_optional_audit_artifact_works(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    audit = tmp_path / 'verification.json'
    assert cli.main(['--evidence', str(evidence), '--audit-output', str(audit)]) == 0
    payload = json.loads(audit.read_text(encoding='utf-8'))
    assert payload['workspace_change_set_execution_verification_only'] is True
