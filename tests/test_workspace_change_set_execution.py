from __future__ import annotations

from dataclasses import replace

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.workspace_change_set_execution import (
    build_workspace_change_set_execution_closure_report,
    build_workspace_change_set_execution_ledger,
    build_workspace_change_set_execution_receipt,
    build_workspace_change_set_execution_request,
    execute_workspace_change_set,
    run_workspace_change_set_execution_wing,
    summarize_workspace_change_set_execution_result,
    validate_workspace_change_set_execution_result,
    validate_workspace_change_target_execution_result,
)
from sentientos.workspace_change_set_preflight import (
    build_workspace_change_set_manifest,
    build_workspace_change_set_preflight_report,
    build_workspace_change_set_rollback_plan,
    build_workspace_change_set_transaction_plan,
    build_workspace_change_target_declaration,
    preflight_workspace_change_target,
)


def _plans(root, specs=(('a.txt', 'alpha'), ('b.txt', 'beta'))):
    targets = tuple(
        build_workspace_change_target_declaration(relative_target_path=path, payload_text=payload)
        for path, payload in specs
    )
    manifest = build_workspace_change_set_manifest(workspace_root=root, targets=targets)
    preflights = tuple(preflight_workspace_change_target(workspace_root=root, target=t) for t in targets)
    report = build_workspace_change_set_preflight_report(manifest=manifest, target_preflights=preflights)
    rollback_plan = build_workspace_change_set_rollback_plan(manifest=manifest, preflight_report=report, target_preflights=preflights)
    transaction_plan = build_workspace_change_set_transaction_plan(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan)
    return targets, manifest, report, rollback_plan, transaction_plan


def test_execution_refuses_failed_preflight(tmp_path):
    targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path / 'missing')
    request = build_workspace_change_set_execution_request(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan)
    result, effects = execute_workspace_change_set(request=request, manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan)
    assert effects == ()
    assert result.execution_status == 'workspace_change_set_execution_blocked'
    assert 'preflight_not_passed' in result.risk_codes


def test_execution_refuses_non_ready_transaction_plan(tmp_path):
    targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    bad_plan = replace(transaction_plan, transaction_plan_status='workspace_change_set_transaction_plan_blocked')
    request = build_workspace_change_set_execution_request(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=bad_plan)
    result, _effects = execute_workspace_change_set(request=request, manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=bad_plan)
    assert result.execution_status == 'workspace_change_set_execution_blocked'
    assert 'transaction_plan_not_ready' in result.risk_codes


def test_executes_two_explicit_targets_and_captures_receipts(tmp_path):
    targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    assert (tmp_path / 'a.txt').read_text() == 'alpha'
    assert (tmp_path / 'b.txt').read_text() == 'beta'
    assert wing.execution_result.execution_status == 'workspace_change_set_execution_performed'
    assert wing.execution_result.applied_target_ids == tuple(t.target_id for t in targets)
    assert all(r.workspace_effect_receipt_id for r in wing.execution_result.target_results)
    assert all(r.workspace_postcondition_check_id for r in wing.execution_result.target_results)
    assert all(r.workspace_rollback_plan_id for r in wing.execution_result.target_results)
    assert all(r.workspace_production_audit_id for r in wing.execution_result.target_results)
    assert wing.ledger is not None
    assert wing.ledger.metadata_only and wing.ledger.performs_no_new_effect
    assert summarize_workspace_change_set_execution_result(wing.execution_result)['bounded_change_set_execution_only'] is True


def test_rollback_after_execute_is_reverse_exact_target_and_preserves_sibling(tmp_path):
    (tmp_path / 'sibling.txt').write_text('keep')
    targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, rollback_after_execute=True, write_ledger=True)
    assert wing.rollback_result.rollback_performed is True
    assert wing.rollback_result.rollback_target_order == tuple(reversed([t.target_id for t in targets]))
    assert not (tmp_path / 'a.txt').exists()
    assert not (tmp_path / 'b.txt').exists()
    assert (tmp_path / 'sibling.txt').read_text() == 'keep'
    assert wing.closure_report.closure_status == 'workspace_change_set_execution_closed_after_rollback'
    assert wing.rollback_result.recursive_delete_performed is False
    assert wing.rollback_result.wildcard_delete_performed is False
    assert wing.rollback_result.unrelated_file_delete_performed is False


def test_digest_drift_since_preflight_blocks_execution(tmp_path):
    targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    (tmp_path / 'a.txt').write_text('drift')
    request = build_workspace_change_set_execution_request(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan)
    result, _effects = execute_workspace_change_set(request=request, manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan)
    assert result.execution_status == 'workspace_change_set_execution_blocked'
    assert any(code.startswith('preflight_absent_target_now_exists') for code in result.risk_codes)


def test_rollback_on_failure_rolls_back_applied_targets_and_records_skipped(tmp_path):
    targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path, (('a.txt', 'alpha'), ('b.txt', 'beta'), ('c.txt', 'gamma')))
    calls = {'count': 0}
    from sentientos.workspace_file_effect import run_workspace_file_effect_wing

    def failing_runner(**kwargs):
        calls['count'] += 1
        if calls['count'] == 2:
            raise RuntimeError('boom')
        return run_workspace_file_effect_wing(**kwargs)

    request = build_workspace_change_set_execution_request(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, rollback_on_failure=True)
    result, effects = execute_workspace_change_set(request=request, manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, effect_runner=failing_runner)
    receipt = build_workspace_change_set_execution_receipt(request, result)
    assert result.execution_status == 'workspace_change_set_execution_partially_performed'
    assert result.partial_state_visible is True
    assert result.applied_target_ids == (targets[0].target_id,)
    assert result.failed_target_ids == (targets[1].target_id,)
    assert result.skipped_target_ids == (targets[2].target_id,)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, rollback_on_failure=True)
    # Standalone partial result validates forbidden flags remain false.
    assert validate_workspace_change_set_execution_result(result).ok
    assert validate_workspace_change_target_execution_result(result.target_results[0]).ok
    assert receipt.general_filesystem_access_performed is False


def test_validation_rejects_forbidden_flags(tmp_path):
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan)
    bad = replace(wing.execution_result, subprocess_used=True)
    validation = validate_workspace_change_set_execution_result(bad)
    assert not validation.ok
    assert 'contradiction:subprocess_used_true' in validation.findings


def test_closure_report_classifications(tmp_path):
    targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    report1 = wing.closure_report
    assert report1.closure_status == 'workspace_change_set_execution_closed_after_execute'
    ledger2 = build_workspace_change_set_execution_ledger(request=wing.request, execution_receipt=wing.execution_receipt, execution_result=replace(wing.execution_result, all_targets_applied=False, failed_target_ids=('x',), partial_state_visible=True))
    report2 = build_workspace_change_set_execution_closure_report(execution_receipt=wing.execution_receipt, execution_result=replace(wing.execution_result, all_targets_applied=False, failed_target_ids=('x',), partial_state_visible=True), ledger=ledger2)
    assert report2.closure_status in {'workspace_change_set_execution_partially_open', 'workspace_change_set_execution_rollback_pending'}


def test_digests_deterministic_and_change_on_metadata(tmp_path):
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    req1 = build_workspace_change_set_execution_request(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, execution_mode='change_set_execute_only')
    req2 = build_workspace_change_set_execution_request(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, execution_mode='change_set_execute_only')
    req3 = build_workspace_change_set_execution_request(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, execution_mode='change_set_execute_with_ledger')
    assert req1.digest == req2.digest
    assert req1.digest != req3.digest
