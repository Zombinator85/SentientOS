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
    execute_workspace_change_set,
    run_workspace_change_set_execution_wing,
)
from sentientos.workspace_change_set_execution_verification import verify_workspace_change_set_execution
from sentientos.workspace_change_set_lifecycle_closure import (
    LIFECYCLE_CLOSURE_STATUSES,
    build_workspace_change_set_lifecycle_closure_manifest,
    summarize_workspace_change_set_lifecycle_closure_manifest,
)
from sentientos.workspace_change_set_preflight import (
    build_workspace_change_set_manifest,
    build_workspace_change_set_preflight_report,
    build_workspace_change_set_rollback_plan,
    build_workspace_change_set_transaction_plan,
    build_workspace_change_target_declaration,
    preflight_workspace_change_target,
)


def _plans(root: Path, specs=(("a.txt", "alpha"), ("b.txt", "beta"))):
    targets = tuple(build_workspace_change_target_declaration(relative_target_path=path, payload_text=payload) for path, payload in specs)
    manifest = build_workspace_change_set_manifest(workspace_root=root, targets=targets)
    preflights = tuple(preflight_workspace_change_target(workspace_root=root, target=target) for target in targets)
    report = build_workspace_change_set_preflight_report(manifest=manifest, target_preflights=preflights)
    rollback_plan = build_workspace_change_set_rollback_plan(manifest=manifest, preflight_report=report, target_preflights=preflights)
    transaction_plan = build_workspace_change_set_transaction_plan(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan)
    return targets, manifest, report, rollback_plan, transaction_plan


def _verified(manifest, report, rollback_plan, transaction_plan, wing):
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
    )


def _closure(manifest, report, rollback_plan, transaction_plan, wing, verified, **kwargs):
    return build_workspace_change_set_lifecycle_closure_manifest(
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
        verification_request=verified.request,
        verification_result=verified.verification_result,
        **kwargs,
    )


def test_clean_verified_execution_closes_clean(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    verified = _verified(manifest, report, rollback_plan, transaction_plan, wing)
    closure = _closure(manifest, report, rollback_plan, transaction_plan, wing, verified)
    assert closure.closure_manifest.lifecycle_closure_status == "lifecycle_closed_clean"
    assert closure.closure_manifest.evidence_summary.declared_target_count == 2
    assert closure.closure_manifest.evidence_summary.applied_target_count == 2
    assert closure.closure_manifest.execution_invoked is False
    assert closure.closure_manifest.verification_replay_invoked is False


def test_verified_rollback_closes_after_rollback(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, rollback_after_execute=True, write_ledger=True)
    verified = _verified(manifest, report, rollback_plan, transaction_plan, wing)
    closure = _closure(manifest, report, rollback_plan, transaction_plan, wing, verified)
    assert closure.closure_manifest.lifecycle_closure_status == "lifecycle_closed_after_rollback"
    assert closure.closure_manifest.evidence_summary.rolled_back_target_count == 2


def test_verified_partial_state_closes_with_partial_state(tmp_path: Path) -> None:
    targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path, (("a.txt", "alpha"), ("b.txt", "beta"), ("c.txt", "gamma")))
    calls = {"count": 0}

    def failing_runner(**kwargs):
        from sentientos.workspace_file_effect import run_workspace_file_effect_wing
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("boom")
        return run_workspace_file_effect_wing(**kwargs)

    request = build_workspace_change_set_execution_request(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, rollback_on_failure=False)
    execution_result, _effects = execute_workspace_change_set(request=request, manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, effect_runner=failing_runner)
    receipt = build_workspace_change_set_execution_receipt(request, execution_result)
    ledger = build_workspace_change_set_execution_ledger(request=request, execution_receipt=receipt, execution_result=execution_result)
    closure_report = build_workspace_change_set_execution_closure_report(execution_receipt=receipt, execution_result=execution_result, ledger=ledger)
    wing = type("Wing", (), {"request": request, "execution_result": execution_result, "execution_receipt": receipt, "rollback_result": None, "rollback_receipt": None, "ledger": ledger, "closure_report": closure_report})()
    verified = _verified(manifest, report, rollback_plan, transaction_plan, wing)
    closure = _closure(manifest, report, rollback_plan, transaction_plan, wing, verified)
    assert closure.closure_manifest.lifecycle_closure_status == "lifecycle_closed_with_partial_state"
    assert closure.closure_manifest.evidence_summary.failed_target_ids == (targets[1].target_id,)


def test_unverified_execution_is_insufficient_evidence(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan)
    closure = build_workspace_change_set_lifecycle_closure_manifest(
        manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan,
        execution_request=wing.request, execution_result=wing.execution_result, execution_receipt=wing.execution_receipt,
        rollback_result=wing.rollback_result, rollback_receipt=wing.rollback_receipt, ledger=wing.ledger, closure_report=wing.closure_report,
    )
    assert closure.closure_manifest.lifecycle_closure_status == "lifecycle_insufficient_evidence"
    assert "missing_evidence:verification_result" in closure.closure_manifest.blocker_codes


def test_contradictory_evidence_yields_contradicted(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    verified = _verified(manifest, report, rollback_plan, transaction_plan, wing)
    bad_request = replace(wing.request, source_manifest_id="other")
    closure = build_workspace_change_set_lifecycle_closure_manifest(
        manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan,
        execution_request=bad_request, execution_result=wing.execution_result, execution_receipt=wing.execution_receipt,
        rollback_result=wing.rollback_result, rollback_receipt=wing.rollback_receipt, ledger=wing.ledger, closure_report=wing.closure_report,
        verification_request=verified.request, verification_result=verified.verification_result,
    )
    assert closure.closure_manifest.lifecycle_closure_status == "lifecycle_contradicted"
    assert "execution_request_manifest_id_mismatch" in closure.closure_manifest.contradiction_codes


def test_blocked_verification_yields_blocked(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, write_ledger=True)
    verified = _verified(manifest, report, rollback_plan, transaction_plan, wing)
    blocked = replace(verified.verification_result, verification_status="verification_blocked")
    closure = build_workspace_change_set_lifecycle_closure_manifest(
        manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan,
        execution_request=wing.request, execution_result=wing.execution_result, execution_receipt=wing.execution_receipt,
        rollback_result=wing.rollback_result, rollback_receipt=wing.rollback_receipt, ledger=wing.ledger, closure_report=wing.closure_report,
        verification_request=verified.request, verification_result=blocked,
    )
    assert closure.closure_manifest.lifecycle_closure_status == "lifecycle_blocked"


def test_missing_evidence_yields_insufficient_evidence(tmp_path: Path) -> None:
    closure = build_workspace_change_set_lifecycle_closure_manifest(created_at="2026-01-01T00:00:00+00:00")
    assert closure.closure_manifest.lifecycle_closure_status == "lifecycle_insufficient_evidence"
    assert closure.closure_manifest.evidence_summary.declared_target_count == 0


def test_closure_manifest_is_metadata_only_and_omits_payloads(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path, (("a.txt", "secret-payload"),))
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan)
    verified = _verified(manifest, report, rollback_plan, transaction_plan, wing)
    closure = _closure(manifest, report, rollback_plan, transaction_plan, wing, verified)
    payload = json.dumps(closure.closure_manifest.to_dict(), sort_keys=True)
    assert "secret-payload" not in payload
    assert "relative_target_path" not in payload
    assert closure.closure_manifest.metadata_only is True
    assert closure.closure_manifest.target_file_read_performed is False
    assert summarize_workspace_change_set_lifecycle_closure_manifest(closure.closure_manifest)["target_file_read_performed"] is False


def test_closure_artifact_write_is_only_optional_write(tmp_path: Path) -> None:
    _targets, manifest, report, rollback_plan, transaction_plan = _plans(tmp_path)
    wing = run_workspace_change_set_execution_wing(manifest=manifest, preflight_report=report, rollback_plan=rollback_plan, transaction_plan=transaction_plan)
    verified = _verified(manifest, report, rollback_plan, transaction_plan, wing)
    artifact = tmp_path / "closure.json"
    closure = _closure(manifest, report, rollback_plan, transaction_plan, wing, verified, artifact_output_path=str(artifact))
    assert artifact.exists()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["closure_manifest_only"] is True
    assert payload["execution_invoked"] is False
    assert closure.closure_result.artifact_path == str(artifact)


def test_all_lifecycle_statuses_are_compact() -> None:
    assert LIFECYCLE_CLOSURE_STATUSES == {
        "lifecycle_closed_clean",
        "lifecycle_closed_with_partial_state",
        "lifecycle_closed_after_rollback",
        "lifecycle_open",
        "lifecycle_blocked",
        "lifecycle_contradicted",
        "lifecycle_insufficient_evidence",
    }


def test_closure_builder_source_does_not_import_or_call_effect_execution_rollback_or_verification_replay_helpers() -> None:
    source = Path("sentientos/workspace_change_set_lifecycle_closure.py").read_text(encoding="utf-8")
    forbidden = (
        "execute_workspace_change_set",
        "run_workspace_change_set_execution_wing",
        "rollback_workspace_change_set",
        "verify_workspace_change_set_execution(",
        "run_workspace_file_effect_wing",
        "run_workspace_file_rollback_wing",
        "subprocess.",
    )
    for token in forbidden:
        assert token not in source
