import pytest

pytestmark = pytest.mark.no_legacy_skip

from dataclasses import replace
from pathlib import Path

from sentientos.builtin_runner_transaction_orchestrator import (
    TRANSACTION_MODES,
    build_builtin_runner_transaction_closure_report,
    build_builtin_runner_transaction_execution_request,
    build_builtin_runner_transaction_plan,
    build_builtin_runner_transaction_receipt,
    builtin_runner_transaction_digest,
    run_builtin_runner_transaction,
    run_builtin_runner_transaction_wing,
    summarize_builtin_runner_transaction_result,
    validate_builtin_runner_transaction_closure_report,
    validate_builtin_runner_transaction_result,
)


def test_dry_run_transaction_writes_nothing(tmp_path: Path) -> None:
    records = run_builtin_runner_transaction_wing(output_dir=tmp_path / "out", dry_run=True)
    assert records.result is not None
    assert records.result.runner_invoked is False
    assert records.result.host_mutation_performed is False
    assert not (tmp_path / "out").exists()


def test_diagnostic_write_only_writes_exactly_one_artifact_and_no_rollback(tmp_path: Path) -> None:
    records = run_builtin_runner_transaction_wing(output_dir=tmp_path / "out")
    assert records.result is not None
    assert records.result.local_diagnostic_write_performed is True
    assert records.result.exact_artifact_rollback_performed is False
    assert (tmp_path / "out" / "sentientos_local_diagnostic_effect.json").exists()
    assert not (tmp_path / "out" / "rollback_receipt.json").exists()


def test_diagnostic_write_with_rollback_deletes_exact_artifact_and_preserves_sibling(tmp_path: Path) -> None:
    outdir = tmp_path / "out"
    outdir.mkdir()
    sibling = outdir / "sibling.txt"
    sibling.write_text("keep", encoding="utf-8")
    records = run_builtin_runner_transaction_wing(output_dir=tmp_path / "out", transaction_mode="diagnostic_write_with_rollback", force=True)
    assert records.result is not None
    assert records.result.local_diagnostic_write_performed is True
    assert records.result.exact_artifact_rollback_performed is True
    assert not (tmp_path / "out" / "sentientos_local_diagnostic_effect.json").exists()
    assert sibling.read_text(encoding="utf-8") == "keep"


def test_write_with_ledger_builds_rollback_pending_ledger_without_artifact_by_default(tmp_path: Path) -> None:
    records = run_builtin_runner_transaction_wing(output_dir=tmp_path / "out", transaction_mode="diagnostic_write_with_ledger")
    assert records.result is not None
    assert records.result.transaction_ledger_built is True
    assert records.result.ledger_artifact_written is False
    assert records.closure_report is not None
    assert records.closure_report.closure_status == "builtin_runner_transaction_closed_after_write"
    assert not (tmp_path / "out" / "transaction_ledger.json").exists()


def test_write_rollback_with_ledger_writes_explicit_ledger_artifact(tmp_path: Path) -> None:
    out = tmp_path / "out" / "transaction_ledger.json"
    records = run_builtin_runner_transaction_wing(output_dir=tmp_path / "out", transaction_mode="diagnostic_write_rollback_with_ledger", ledger_output_path=out, force=True)
    assert records.result is not None
    assert records.result.transaction_ledger_built is True
    assert records.result.ledger_artifact_written is True
    assert out.exists()
    assert records.closure_report is not None
    assert records.closure_report.closure_status == "builtin_runner_transaction_closed_after_rollback"


def test_unsupported_mode_blocks(tmp_path: Path) -> None:
    records = run_builtin_runner_transaction_wing(output_dir=tmp_path / "out", transaction_mode="not_allowed")
    assert records.plan.plan_status == "builtin_runner_transaction_plan_blocked"
    assert records.result is not None
    assert records.result.transaction_status == "builtin_runner_transaction_blocked"


def test_partial_state_visible_if_rollback_fails(tmp_path: Path, monkeypatch) -> None:
    import sentientos.builtin_runner_transaction_orchestrator as orch

    original = orch.run_builtin_local_effect_runner_wing

    def fake_runner(*, action_kind: str, **kwargs):
        if action_kind == "local_diagnostic_exact_rollback":
            raise FileNotFoundError("simulated missing rollback inputs")
        return original(action_kind=action_kind, **kwargs)

    monkeypatch.setattr(orch, "run_builtin_local_effect_runner_wing", fake_runner)
    plan = build_builtin_runner_transaction_plan(output_dir=tmp_path / "out", transaction_mode="diagnostic_write_with_rollback")
    request = build_builtin_runner_transaction_execution_request(plan)
    try:
        result = run_builtin_runner_transaction(request)
    except FileNotFoundError:
        # The artifact proves partial state remained visible to the caller.
        assert (tmp_path / "out" / "sentientos_local_diagnostic_effect.json").exists()
    else:
        assert result.transaction_status in {"builtin_runner_transaction_incomplete", "builtin_runner_transaction_failed"}


def test_partial_state_visible_if_ledger_build_fails(tmp_path: Path, monkeypatch) -> None:
    import sentientos.builtin_runner_transaction_orchestrator as orch

    def fail_ledger(**kwargs):
        raise ValueError("simulated ledger failure")

    monkeypatch.setattr(orch, "build_transaction_ledger_from_local_diagnostic_records", fail_ledger)
    records = run_builtin_runner_transaction_wing(output_dir=tmp_path / "out", transaction_mode="diagnostic_write_with_ledger")
    assert records.result is not None
    assert records.result.local_diagnostic_write_performed is True
    assert records.result.transaction_status == "builtin_runner_transaction_incomplete"
    assert "ledger_pending" in records.result.warning_codes


def test_result_and_receipt_include_ids_digests_paths(tmp_path: Path) -> None:
    records = run_builtin_runner_transaction_wing(output_dir=tmp_path / "out", transaction_mode="diagnostic_write_rollback_with_ledger", force=True)
    assert records.result is not None and records.receipt is not None
    assert records.result.produced_record_ids
    assert records.result.produced_record_digests
    assert records.result.produced_paths
    assert records.receipt.produced_record_ids == records.result.produced_record_ids


def test_no_forbidden_flags_and_validation_rejects_claims(tmp_path: Path) -> None:
    records = run_builtin_runner_transaction_wing(output_dir=tmp_path / "out")
    assert records.result is not None
    summary = summarize_builtin_runner_transaction_result(records.result)
    for flag in ("subprocess_used", "shell_used", "network_used", "provider_invocation_performed", "prompt_assembly_performed", "general_cleanup_performed", "recursive_delete_performed", "unrelated_file_delete_performed"):
        assert summary[flag] is False
    for flag in ("subprocess_used", "shell_used", "network_used", "provider_invocation_performed", "prompt_assembly_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "general_cleanup_performed", "recursive_delete_performed", "unrelated_file_delete_performed"):
        bad = replace(records.result, **{flag: True})
        assert not validate_builtin_runner_transaction_result(bad).ok


def test_digests_are_deterministic_and_change_on_metadata(tmp_path: Path) -> None:
    plan1 = build_builtin_runner_transaction_plan(output_dir=tmp_path / "out", transaction_mode="diagnostic_write_only")
    plan2 = build_builtin_runner_transaction_plan(output_dir=tmp_path / "out", transaction_mode="diagnostic_write_only")
    plan3 = build_builtin_runner_transaction_plan(output_dir=tmp_path / "out", transaction_mode="diagnostic_write_with_rollback")
    assert plan1.digest == plan2.digest
    assert plan1.digest != plan3.digest
    assert plan1.digest == builtin_runner_transaction_digest(plan1.to_dict())


def test_all_modes_are_declared() -> None:
    assert set(TRANSACTION_MODES) == {"diagnostic_write_only", "diagnostic_write_with_rollback", "diagnostic_write_with_ledger", "diagnostic_write_rollback_with_ledger"}
