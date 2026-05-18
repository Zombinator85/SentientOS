from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.workspace_change_set_execution import (
    build_workspace_change_set_execution_closure_report,
    build_workspace_change_set_execution_ledger,
    build_workspace_change_set_execution_receipt,
    build_workspace_change_set_execution_request,
    deterministic_digest,
    execute_workspace_change_set,
    run_workspace_change_set_execution_wing,
)
from sentientos.workspace_change_set_execution_verification import (
    VERIFICATION_STATUSES,
    summarize_workspace_change_set_execution_verification_result,
    verify_workspace_change_set_execution,
)
from sentientos.workspace_change_set_preflight import (
    build_workspace_change_set_manifest,
    build_workspace_change_set_preflight_report,
    build_workspace_change_set_rollback_plan,
    build_workspace_change_set_transaction_plan,
    build_workspace_change_target_declaration,
    preflight_workspace_change_target,
)


def _plans(root: Path, specs=(('a.txt', 'alpha'), ('b.txt', 'beta'))):
    targets = tuple(build_workspace_change_target_declaration(relative_target_path=path, payload_text=payload) for path, payload in specs)
    manifest = build_workspace_change_set_manifest(workspace_root=root, targets=targets)
    preflights = tuple(preflight_workspace_change_target(workspace_root=root, target=target) for target in targets)
    report = build_workspace_change_set_preflight_report(manifest=manifest, target_preflights=preflights)
    rollback_plan = build_workspace_change_set_rollback_plan(manifest=manifest, preflight_report=report, target_preflights=preflights)
    transaction_plan = build_workspace_change_set_transaction_plan(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan)
    return targets, manifest, report, rollback_plan, transaction_plan


def _verify(manifest, report, rollback_plan, transaction_plan, wing, **kwargs):
    return verify_workspace_change_set_execution(
        manifest=manifest,
        preflight_report=report,
        rollback_plan=rollback_plan,
        transaction_plan=transaction_plan,
        execution_request=wing.request,
        execution_result=wing.execution_result,
        execution_receipt=wing.execution_receipt,
        rollback_result=wing.rollback_result,
        rollback_receipt=wing.rollback_receipt,
        ledger=wing.ledger,
        closure_report=wing.closure_report,
        **kwargs,
    )


def test_clean_execution_verifies(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    verified = _verify(manifest, report, rollback_plan, transaction_plan, wing)
    result = verified.verification_result
    assert result.verification_status == 'verified_clean'
    assert result.postcondition_digest_agreement is True
    assert result.unknown_target_ids == ()
    assert all(record.target_verification_status == 'target_verified_postcondition' for record in result.target_records)
    assert summarize_workspace_change_set_execution_verification_result(result)['execution_invoked'] is False


def test_rollback_after_execute_verifies_against_preimages_or_absence(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, rollback_after_execute=True, write_ledger=True)
    verified = _verify(manifest, report, rollback_plan, transaction_plan, wing)
    assert verified.verification_result.verification_status == 'verified_rolled_back'
    assert verified.verification_result.rollback_digest_agreement is True
    assert {record.target_verification_status for record in verified.verification_result.target_records} == {'target_verified_rollback_absence'}


def test_partial_failure_remains_visible_and_verifies_as_partial_state(tmp_path: Path) -> None:
    targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path, (('a.txt', 'alpha'), ('b.txt', 'beta'), ('c.txt', 'gamma')))
    calls = {'count': 0}

    def failing_runner(**kwargs):
        from sentientos.workspace_file_effect import run_workspace_file_effect_wing
        calls['count'] += 1
        if calls['count'] == 2:
            raise RuntimeError('boom')
        return run_workspace_file_effect_wing(**kwargs)

    request = build_workspace_change_set_execution_request(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, rollback_on_failure=False)
    execution_result, _effects = execute_workspace_change_set(request=request, manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, effect_runner=failing_runner)
    receipt = build_workspace_change_set_execution_receipt(request, execution_result)
    ledger = build_workspace_change_set_execution_ledger(request=request, execution_receipt=receipt, execution_result=execution_result)
    closure = build_workspace_change_set_execution_closure_report(execution_receipt=receipt, execution_result=execution_result, ledger=ledger)
    wing = type('Wing', (), {'request': request, 'execution_result': execution_result, 'execution_receipt': receipt, 'rollback_result': None, 'rollback_receipt': None, 'ledger': ledger, 'closure_report': closure})()
    verified = _verify(manifest, report, rollback_plan, transaction_plan, wing)
    assert verified.verification_result.verification_status == 'verified_with_partial_state'
    assert verified.verification_result.partial_state_visible is True
    statuses = {record.target_id: record.target_verification_status for record in verified.verification_result.target_records}
    assert statuses[targets[0].target_id] == 'target_verified_postcondition'
    assert statuses[targets[1].target_id] == 'target_verified_failed_visible'
    assert statuses[targets[2].target_id] == 'target_verified_skipped_visible'


def test_digest_mismatch_fails_verification(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    (tmp_path / 'a.txt').write_text('tampered')
    verified = _verify(manifest, report, rollback_plan, transaction_plan, wing)
    assert verified.verification_result.verification_status == 'verification_failed'
    assert any('postcondition_digest_mismatch' in code for code in verified.verification_result.finding_codes)


def test_missing_applied_declared_target_fails_verification(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    (tmp_path / 'a.txt').unlink()
    verified = _verify(manifest, report, rollback_plan, transaction_plan, wing)
    assert verified.verification_result.verification_status == 'verification_failed'
    assert any('applied_target_missing' in code for code in verified.verification_result.finding_codes)


def test_unknown_target_evidence_fails_verification(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    unknown = replace(wing.execution_result.target_results[0], target_id='unknown-target', digest='')
    unknown = replace(unknown, digest=deterministic_digest('workspace-change-target-execution-result-', unknown.to_dict()))
    execution_result = replace(wing.execution_result, target_results=wing.execution_result.target_results + (unknown,), digest='')
    execution_result = replace(execution_result, digest=deterministic_digest('workspace-change-set-execution-result-', execution_result.to_dict()))
    verified = verify_workspace_change_set_execution(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, execution_request=wing.request, execution_result=execution_result, execution_receipt=wing.execution_receipt, rollback_result=wing.rollback_result, rollback_receipt=wing.rollback_receipt, ledger=wing.ledger, closure_report=wing.closure_report)
    assert verified.verification_result.verification_status == 'verification_failed'
    assert verified.verification_result.unknown_target_ids == ('unknown-target',)


def test_stale_or_contradictory_ledger_receipt_closure_fails(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    bad_ledger = replace(wing.ledger, execution_status='workspace_change_set_execution_failed')
    bad_receipt = replace(wing.execution_receipt, applied_target_ids=())
    bad_closure = replace(wing.closure_report, open_target_ids=('ghost',))
    verified = verify_workspace_change_set_execution(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, execution_request=wing.request, execution_result=wing.execution_result, execution_receipt=bad_receipt, rollback_result=wing.rollback_result, rollback_receipt=wing.rollback_receipt, ledger=bad_ledger, closure_report=bad_closure)
    assert verified.verification_result.verification_status == 'verification_failed'
    assert {'ledger_execution_status_stale', 'execution_receipt_lists_mismatch', 'closure_open_targets_contradict_evidence'} <= set(verified.verification_result.finding_codes)


def test_verifier_reads_only_declared_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / 'unrelated.txt').write_text('do not read')
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    reads: list[Path] = []
    original = Path.read_bytes

    def recording_read_bytes(self: Path) -> bytes:
        reads.append(self.resolve())
        return original(self)

    monkeypatch.setattr(Path, 'read_bytes', recording_read_bytes)
    _verify(manifest, report, rollback_plan, transaction_plan, wing)
    assert set(reads) == {(tmp_path / 'a.txt').resolve(), (tmp_path / 'b.txt').resolve()}


def test_verifier_performs_no_writes_except_optional_audit_artifact(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    mtimes = {path: path.stat().st_mtime_ns for path in (tmp_path / 'a.txt', tmp_path / 'b.txt')}
    audit_path = tmp_path / 'verification_audit.json'
    verified = _verify(manifest, report, rollback_plan, transaction_plan, wing, audit_output_path=str(audit_path))
    assert audit_path.exists()
    assert verified.verification_result.audit_artifact_path == str(audit_path)
    assert {path: path.stat().st_mtime_ns for path in mtimes} == mtimes


def test_verifier_does_not_import_execution_or_rollback_helpers() -> None:
    import sentientos.workspace_change_set_execution_verification as verifier
    assert not hasattr(verifier, 'run_workspace_file_effect_wing')
    assert not hasattr(verifier, 'run_workspace_file_rollback_wing')
    assert VERIFICATION_STATUSES == {'verified_clean', 'verified_with_partial_state', 'verified_rolled_back', 'verification_failed', 'verification_blocked', 'insufficient_evidence'}
