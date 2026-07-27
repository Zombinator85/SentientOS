from __future__ import annotations

import inspect
import json
import shutil
import threading
from pathlib import Path
from typing import Any, Callable

import pytest

import sentientos.host_local_diagnostic_execution_runtime as runtime
from sentientos.builtin_runner_transaction_orchestrator import run_builtin_runner_transaction_wing
from sentientos.host_local_diagnostic_execution_source_runtime import load_persisted_execution_source_bundle
from sentientos.host_local_diagnostic_execution_source_runtime import _canon, _raw_sha, _sha, digest_record
from tests.host_local_diagnostic_execution_fixture import NOW, DiagnosticExecutionFixture, build_diagnostic_execution_fixture

pytestmark = pytest.mark.no_legacy_skip


def _confirmed_execute(fixture: DiagnosticExecutionFixture, output: Path, *, coordinator: runtime.HostLocalDiagnosticExecutionRuntimeCoordinator | None = None, correlation_id: str = "runtime-proof") -> runtime.ExecutionOutcome:
    coordinator = coordinator or runtime.HostLocalDiagnosticExecutionRuntimeCoordinator()
    preflight = coordinator.preflight(execution_source_bundle_root=fixture.source_bundle, expected_source_bundle_digest=fixture.source_digest, current_snapshot=fixture.snapshot, current_verification=fixture.verification, execution_time=NOW)
    assert preflight.status == "host_local_diagnostic_execution_preflight_ready"
    challenge = preflight.records["confirmation_challenge"]
    return coordinator.execute(
        execution_source_bundle_root=fixture.source_bundle, expected_source_bundle_digest=fixture.source_digest, current_snapshot=fixture.snapshot, current_verification=fixture.verification, execution_time=NOW,
        output_root=output, confirm_local_diagnostic_write=True,
        confirm_source_bundle_digest=fixture.source_digest, confirm_effect_output_dir=str(fixture.target),
        confirmation_challenge_digest=challenge["confirmation_challenge_digest"], correlation_id=correlation_id,
    )


def test_repository_native_fixture_builds_valid_v2_execution_source(tmp_path: Path) -> None:
    fixture = build_diagnostic_execution_fixture(tmp_path)
    validation = load_persisted_execution_source_bundle(fixture.source_bundle, expected_bundle_digest=fixture.source_digest)
    assert validation.ok and validation.evaluation is not None
    assert validation.evaluation.records["runtime_request"]["schema_version"].endswith(".v2")


def test_real_execution_performs_one_bounded_transaction_and_validates_bundle(tmp_path: Path) -> None:
    fixture = build_diagnostic_execution_fixture(tmp_path)
    fixture.target.mkdir()
    sibling = fixture.target / "operator-owned.txt"
    sibling.write_text("unchanged\n")
    calls: list[dict[str, Any]] = []
    def runner(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return run_builtin_runner_transaction_wing(**kwargs)
    outcome = _confirmed_execute(fixture, tmp_path / "executions", coordinator=runtime.HostLocalDiagnosticExecutionRuntimeCoordinator(runner))
    assert outcome.status == "host_local_diagnostic_execution_completed"
    assert outcome.runner_call_count == len(calls) == 1
    assert {path.name for path in fixture.target.iterdir()} == set(runtime.TARGET_FILES) | {sibling.name}
    assert sibling.read_text() == "unchanged\n"
    assert runtime.validate_persisted_execution_bundle(outcome.bundle_root).status == "host_local_diagnostic_execution_completed"
    assert runtime.validate_live_target(outcome.bundle_root).status == "host_local_diagnostic_execution_live_target_valid"
    records = outcome.records
    assert set(records["target_snapshots"]) == set(runtime.TARGET_FILES)
    assert records["runtime_result"]["runner_invoked"] is True
    assert all(records["runtime_result"][name] is False for name in runtime.FORBIDDEN_FLAGS)


def test_completed_replay_is_read_only_after_source_and_target_deletion(tmp_path: Path) -> None:
    fixture = build_diagnostic_execution_fixture(tmp_path)
    output = tmp_path / "executions"
    calls = 0
    def runner(**kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return run_builtin_runner_transaction_wing(**kwargs)
    coordinator = runtime.HostLocalDiagnosticExecutionRuntimeCoordinator(runner)
    first = _confirmed_execute(fixture, output, coordinator=coordinator, correlation_id="durable-replay")
    shutil.rmtree(fixture.source_bundle)
    shutil.rmtree(fixture.target)
    before = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    replay = coordinator.execute(execution_source_bundle_root=fixture.source_bundle, expected_source_bundle_digest=fixture.source_digest, current_snapshot={}, current_verification={}, execution_time=NOW, output_root=output, confirm_local_diagnostic_write=True, confirm_source_bundle_digest=fixture.source_digest, confirm_effect_output_dir=str(fixture.target), confirmation_challenge_digest="unneeded-for-historical-replay", correlation_id="durable-replay")
    after = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    assert first.status == replay.status == "host_local_diagnostic_execution_completed"
    assert replay.replayed is True and replay.runner_call_count == 0 and calls == 1 and after == before
    assert runtime.validate_persisted_execution_bundle(replay.bundle_root).status == "host_local_diagnostic_execution_completed"
    assert runtime.validate_live_target(replay.bundle_root).status == "host_local_diagnostic_execution_live_target_invalid"


def test_runner_returned_crash_reconciles_without_second_runner_call(tmp_path: Path) -> None:
    fixture = build_diagnostic_execution_fixture(tmp_path)
    calls = 0
    def runner(**kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return run_builtin_runner_transaction_wing(**kwargs)
    def crash(state: str) -> None:
        if state == "runner_returned":
            raise RuntimeError("deterministic runner-returned crash")
    output = tmp_path / "executions"
    with pytest.raises(RuntimeError, match="runner-returned"):
        _confirmed_execute(fixture, output, coordinator=runtime.HostLocalDiagnosticExecutionRuntimeCoordinator(runner, crash), correlation_id="reconcile")
    reconciled = _confirmed_execute(fixture, output, coordinator=runtime.HostLocalDiagnosticExecutionRuntimeCoordinator(runner), correlation_id="reconcile")
    assert reconciled.status == "host_local_diagnostic_execution_completed"
    assert reconciled.runner_call_count == 0 and calls == 1
    assert reconciled.records["runtime_result"]["reconciled_effect_observed"] is True
    assert runtime.validate_persisted_execution_bundle(reconciled.bundle_root).status == "host_local_diagnostic_execution_completed"


def test_invocation_committed_crash_never_retries_and_reports_ambiguous(tmp_path: Path) -> None:
    fixture = build_diagnostic_execution_fixture(tmp_path)
    calls = 0
    def runner(**kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return run_builtin_runner_transaction_wing(**kwargs)
    def crash(state: str) -> None:
        if state == "invocation_committed":
            raise RuntimeError("deterministic invocation-committed crash")
    output = tmp_path / "executions"
    with pytest.raises(RuntimeError, match="invocation-committed"):
        _confirmed_execute(fixture, output, coordinator=runtime.HostLocalDiagnosticExecutionRuntimeCoordinator(runner, crash), correlation_id="ambiguous")
    outcome = _confirmed_execute(fixture, output, coordinator=runtime.HostLocalDiagnosticExecutionRuntimeCoordinator(runner), correlation_id="ambiguous")
    assert outcome.status == "host_local_diagnostic_execution_ambiguous_invocation"
    assert outcome.findings == ("runner_retry_forbidden",) and outcome.runner_call_count == 0 and calls == 0


def test_concurrent_identical_execution_invokes_runner_once(tmp_path: Path) -> None:
    fixture = build_diagnostic_execution_fixture(tmp_path)
    output = tmp_path / "executions"
    entered = threading.Event()
    release = threading.Event()
    calls = 0
    def runner(**kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(10)
        return run_builtin_runner_transaction_wing(**kwargs)
    coordinator = runtime.HostLocalDiagnosticExecutionRuntimeCoordinator(runner)
    results: list[runtime.ExecutionOutcome] = []
    threads = [threading.Thread(target=lambda: results.append(_confirmed_execute(fixture, output, coordinator=coordinator, correlation_id="concurrent"))) for _ in range(2)]
    threads[0].start(); assert entered.wait(10); threads[1].start(); release.set()
    for thread in threads: thread.join(10)
    assert not any(thread.is_alive() for thread in threads)
    assert calls == 1 and len(results) == 2
    assert {result.status for result in results} == {"host_local_diagnostic_execution_completed"}
    assert sum(result.runner_call_count for result in results) == 1
    assert len({result.bundle_root for result in results}) == 1


def _rewrite_manifests(bundle: Path) -> None:
    content = json.loads((bundle / "content_manifest.json").read_text())
    for entry in content["files"]:
        raw = (bundle / entry["relative_filename"]).read_bytes()
        entry.update(size_bytes=len(raw), sha256=_raw_sha(raw))
    content["content_manifest_digest"] = _sha({key: value for key, value in content.items() if key != "content_manifest_digest"})
    (bundle / "content_manifest.json").write_text(_canon(content) + "\n")
    receipt = json.loads((bundle / "runtime_receipt.json").read_text())
    receipt["content_manifest_digest"] = content["content_manifest_digest"]
    receipt["digest"] = digest_record(receipt)
    (bundle / "runtime_receipt.json").write_text(_canon(receipt) + "\n")
    manifest = json.loads((bundle / "bundle_manifest.json").read_text())
    for entry in manifest["files"]:
        raw = (bundle / entry["relative_filename"]).read_bytes()
        entry.update(size_bytes=len(raw), sha256=_raw_sha(raw))
    manifest["bundle_digest"] = _sha({key: value for key, value in manifest.items() if key != "bundle_digest"})
    (bundle / "bundle_manifest.json").write_text(_canon(manifest) + "\n")


def _mutate_snapshot_record(snapshots: dict[str, Any], name: str, mutate: Callable[[dict[str, Any]], None]) -> None:
    snapshot = snapshots[name]
    decoded = json.loads(bytes.fromhex(snapshot["bytes_hex"]))
    mutate(decoded)
    raw = (_canon(decoded) + "\n").encode()
    snapshot.update(bytes_hex=raw.hex(), size_bytes=len(raw), sha256=_raw_sha(raw))


def _mutate_final_intent(value: Any) -> None:
    history = value.get("history", value) if isinstance(value, dict) else value
    assert isinstance(history, list)
    history[-1]["state"] = "invocation_committed"


def test_recomputed_tampering_of_effect_ledger_intent_and_manifests_is_rejected(tmp_path: Path) -> None:
    fixture = build_diagnostic_execution_fixture(tmp_path)
    original = Path(_confirmed_execute(fixture, tmp_path / "executions").bundle_root)
    mutations: tuple[tuple[str, Callable[[dict[str, Any]], None]], ...] = (
        ("runtime_result.json", lambda value: value.update(real_effect_performed=False)),
        ("transaction_records.json", lambda value: value["result"].update(transaction_status="builtin_runner_transaction_blocked")),
        ("execution_intent_history.json", _mutate_final_intent),
        ("source_records.json", lambda value: value["target_specification"].update(transaction_mode="contradictory")),
        ("target_snapshots.json", lambda value: _mutate_snapshot_record(value, runtime.ARTIFACT_NAME, lambda artifact: artifact.update(effect_domain="contradictory_effect"))),
        ("target_snapshots.json", lambda value: _mutate_snapshot_record(value, runtime.LEDGER_NAME, lambda ledger: ledger["ledger"].update(current_transaction_status="local_effect_transaction_complete"))),
    )
    for index, (filename, mutate) in enumerate(mutations):
        bundle = tmp_path / f"tampered-{index}"
        shutil.copytree(original, bundle)
        value = json.loads((bundle / filename).read_text()); mutate(value)
        (bundle / filename).write_text(_canon(value) + "\n")
        _rewrite_manifests(bundle)
        assert runtime.validate_persisted_execution_bundle(bundle).status == "host_local_diagnostic_execution_bundle_invalid", filename


def test_execution_boundary_is_exact() -> None:
    assert runtime.TARGET_FILES == ("sentientos_local_diagnostic_effect.json", "effect_receipt.json", "postcondition_check.json", "production_audit.json", "rollback_plan.json", "sentientos_local_diagnostic_transaction_ledger.json")
    assert all(value is False for value in runtime.NO_BROAD_AUTHORITY.values())


def test_only_orchestrator_effect_dependency() -> None:
    source = inspect.getsource(runtime)
    assert "run_builtin_runner_transaction_wing" in source
    for forbidden in ("perform_local_diagnostic_effect", "run_local_diagnostic_effect_wing", "run_builtin_local_effect_runner", "write_local_effect_transaction_ledger_artifact", "import subprocess", "import requests"):
        assert forbidden not in source


def test_preflight_path_does_not_call_runner_or_write(tmp_path: Path) -> None:
    calls: list[object] = []
    coordinator = runtime.HostLocalDiagnosticExecutionRuntimeCoordinator(lambda **kwargs: calls.append(kwargs))
    before = set(tmp_path.iterdir())
    result = coordinator.preflight(execution_source_bundle_root=tmp_path / "missing", expected_source_bundle_digest="sha256:missing", current_snapshot={}, current_verification={}, execution_time="2026-01-01T00:00:00Z")
    assert result.status.startswith("blocked_") and calls == [] and set(tmp_path.iterdir()) == before


def test_runtime_discovers_intent_and_merges_replay_index() -> None:
    source = inspect.getsource(runtime.HostLocalDiagnosticExecutionRuntimeCoordinator)
    assert 'intent_dir.exists()' in source and 'mapping[pointer["correlation_id"]]=pointer' in source
    assert source.index('self._state(intent_dir,history,"finalized"') < source.index('bundle=self._persist')


def test_challenge_and_authority_records_are_digest_bound() -> None:
    assert "confirmation_challenge_id" in inspect.getsource(runtime._challenge)
    authority_source = inspect.getsource(runtime.validate_fresh_execution_authority)
    assert "execution_time" in authority_source and "authority_validation_id" in authority_source
