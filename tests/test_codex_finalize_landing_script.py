from __future__ import annotations

import pytest
import hashlib
import json
import subprocess
import os
import stat
import threading
from pathlib import Path

from scripts.codex_finalize_landing import (
    _classify,
    _cleanup_generated,
    _collect_dirty_diagnostics,
    _infer_task_slugs,
    _is_safe_untracked_task_file,
    build_parser,
    main,
)


def test_parser_has_phase_and_changed_file() -> None:
    p = build_parser()
    args = p.parse_args([
        "finalize",
        "--title",
        "t",
        "--intended-commit-title",
        "t",
        "--phase",
        "pre-commit",
        "--changed-file",
        "sentientos/codex_finalize_landing.py",
    ])
    assert args.cmd == "finalize"
    assert args.phase == "pre-commit"
    assert args.changed_file == ["sentientos/codex_finalize_landing.py"]


def test_parser_has_allow_current_tracked_changes() -> None:
    p = build_parser()
    args = p.parse_args(
        [
            "finalize",
            "--title",
            "t",
            "--intended-commit-title",
            "t",
            "--phase",
            "pre-commit",
            "--allow-current-tracked-changes",
        ]
    )
    assert args.allow_current_tracked_changes is True


def test_parser_has_allow_current_task_files() -> None:
    p = build_parser()
    args = p.parse_args(["finalize", "--phase", "pre-commit", "--allow-current-task-files"])
    assert args.allow_current_task_files is True


def test_parser_has_stale_evidence_refresh_flags() -> None:
    p = build_parser()
    args = p.parse_args(["finalize", "--allow-stale-evidence-refresh", "--max-stale-evidence-refreshes", "1"])
    assert args.allow_stale_evidence_refresh is True
    assert args.max_stale_evidence_refreshes == 1


def test_classify_untracked_task_file_inferred() -> None:
    findings = _classify(["?? tests/test_new_case.py"], (), ("tests/test_new_case.py",))
    assert findings[0].classification == "intended_task_change"


def test_classify_untracked_unknown_root_and_media_blocked() -> None:
    findings = _classify(["?? random.bin", "?? docs/image.png"], (), ())
    assert findings[0].classification == "unknown_dirty_file"
    assert findings[1].classification == "unknown_dirty_file"


def test_dirty_diagnostics_include_exact_path_and_recommended_action() -> None:
    status = ["?? glow/test_runs/run.json", "?? random.tmp"]
    findings = _classify(status, (), ())
    diagnostics = _collect_dirty_diagnostics(status, findings, "declared", {"glow/test_runs/run.json": (True, "removed", "generated_artifact_cleanup")})
    assert diagnostics[0].path == "glow/test_runs/run.json"
    assert diagnostics[0].git_status == "??"
    assert diagnostics[0].recommended_action == "remove_generated_artifact"
    assert diagnostics[1].path == "random.tmp"
    assert diagnostics[1].recommended_action == "manual_review_required"


def test_cleanup_restores_tracked_generated_file(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> object:
        calls.append(cmd)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr("scripts.codex_finalize_landing.subprocess.run", fake_run)
    result = _cleanup_generated([" M glow/test_runs/archive_index.jsonl"])
    assert calls == [["git", "restore", "--", "glow/test_runs/archive_index.jsonl"]]
    assert result["glow/test_runs/archive_index.jsonl"] == (True, "restored", "generated_artifact_restore")


def test_cleanup_removes_untracked_generated_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> object:
        calls.append(cmd)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr("scripts.codex_finalize_landing.subprocess.run", fake_run)
    result = _cleanup_generated(["?? glow/test runs/weird;name/"])
    assert calls == [["git", "clean", "-fd", "--", "glow/test runs/weird;name/"]]
    assert result["glow/test runs/weird;name/"] == (True, "removed", "generated_artifact_cleanup")


def test_cleanup_restores_runtime_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> object:
        calls.append(cmd)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr("scripts.codex_finalize_landing.subprocess.run", fake_run)
    result = _cleanup_generated([" M pulse/audit/privileged_audit.runtime.jsonl"])
    assert calls == [["git", "restore", "--", "pulse/audit/privileged_audit.runtime.jsonl"]]
    assert result["pulse/audit/privileged_audit.runtime.jsonl"] == (True, "restored", "runtime_audit_restore")


def test_cleanup_leaves_source_paths_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("scripts.codex_finalize_landing.subprocess.run", lambda cmd: calls.append(cmd))
    assert _cleanup_generated([" M scripts/codex_finalize_landing.py", " M sentientos/codex_finalize_landing.py"]) == {}
    assert calls == []


def test_cleanup_failed_restore_remains_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str]) -> object:
        return type("Result", (), {"returncode": 1})()

    monkeypatch.setattr("scripts.codex_finalize_landing.subprocess.run", fake_run)
    result = _cleanup_generated([" M glow/test_runs/archive_index.jsonl"])
    assert result["glow/test_runs/archive_index.jsonl"] == (True, "failed", "generated_artifact_restore")


def test_parser_has_output_timeouts_and_progress_flags() -> None:
    p = build_parser()
    args = p.parse_args(["finalize", "--output", "/tmp/out.json", "--stage-timeout-seconds", "5", "--overall-timeout-seconds", "10", "--no-progress"])
    assert args.output == "/tmp/out.json"
    assert args.stage_timeout_seconds == 5
    assert args.overall_timeout_seconds == 10
    assert args.progress is False


def test_finalize_writes_output_and_decision_line(tmp_path: Path, capsys: object) -> None:
    out = tmp_path / "finalizer.json"
    code = main([
        "finalize",
        "--title",
        "x",
        "--intended-commit-title",
        "x",
        "--phase",
        "pr-metadata",
        "--focused-test-command",
        "python -c \"print('ok')\"",
        "--targeted-mypy-command",
        "python -c \"print('ok')\"",
        "--output",
        str(out),
        "--summary",
    ])
    assert code in {0, 1}
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "Codex Finalize Landing decision:" in captured.out
    assert "[finalizer] stage start:" in captured.out
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "runtime" in payload
    assert "stages" in payload["runtime"]


@pytest.mark.no_legacy_skip
def test_fixture_root_inferred_only_for_matching_task_slug() -> None:
    status = [
        "?? sentientos/memory_commit_execution_gate.py",
        "?? tests/test_memory_commit_execution_gate.py",
        "?? tests/fixtures/memory_commit_execution_gate/",
        "?? tests/fixtures/other_capability/",
    ]
    task_slugs = _infer_task_slugs(status, ())
    assert _is_safe_untracked_task_file("tests/fixtures/memory_commit_execution_gate/", task_slugs) is True
    assert _is_safe_untracked_task_file("tests/fixtures/memory_commit_execution_gate/nested/case.json", task_slugs) is True
    assert _is_safe_untracked_task_file("tests/fixtures/other_capability/", task_slugs) is False


@pytest.mark.no_legacy_skip
def test_classify_allows_current_capability_fixture_root_but_blocks_other_root() -> None:
    findings = _classify(
        [
            "?? tests/fixtures/memory_commit_execution_gate/",
            "?? tests/fixtures/other_capability/",
            "?? glow/test_runs/report.json",
        ],
        (),
        ("tests/fixtures/memory_commit_execution_gate/",),
    )
    by_path = {item.path: item.classification for item in findings}
    assert by_path["tests/fixtures/memory_commit_execution_gate/"] == "intended_task_change"
    assert by_path["tests/fixtures/other_capability/"] == "unknown_dirty_file"
    assert by_path["glow/test_runs/report.json"] == "generated_runtime_artifact"


def _successful_runtime(stage_id: str, command: str, required: bool):
    from scripts.codex_finalize_landing import StageRuntime

    return StageRuntime(
        stage_id=stage_id,
        command=command,
        started_at=0.0,
        completed=True,
        exit_code=0,
        duration_seconds=0.0,
        stdout_tail="",
        stderr_tail="",
        decision_impact="required" if required else "optional",
        status="passed",
        timed_out=False,
    )


ACCEPTANCE_NODE = "tests/test_codex_finalize_landing_script.py::test_generated_cleanup_can_remove_original_glow_provenance_and_still_reach_ready"


def _acceptance_fixture(tmp_path: Path, provenance: Path | None = None) -> tuple[Path, Path, bytes, bytes]:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
    provenance = provenance or tmp_path / "provenance.json"
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance_bytes = json.dumps({"git_sha": sha, "reporter_ok": True, "metrics_status": "ok", "selected_node_ids": [ACCEPTANCE_NODE], "node_outcomes": [{"node_id": ACCEPTANCE_NODE, "phase": "call", "outcome": "passed"}]}, separators=(",", ":")).encode()
    provenance.write_bytes(provenance_bytes)
    manifest = tmp_path / "manifest.json"
    manifest_bytes = json.dumps({"schema_version": "sentientos.task_acceptance:v1", "task_classification": "behavior_adding", "repository_sha": sha, "test_provenance_path": str(provenance), "required_nodes": [{"node_id": ACCEPTANCE_NODE}], "successful_path_nodes": [ACCEPTANCE_NODE]}, separators=(",", ":")).encode()
    manifest.write_bytes(manifest_bytes)
    return manifest, provenance, manifest_bytes, provenance_bytes


def _run_fake_finalizer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, manifest: Path, hook=None, extra: list[str] | None = None) -> dict[str, object]:
    out = tmp_path / "out.json"
    monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: [])
    def fake(stage_id: str, command: str, required: bool, progress: bool, timeout: int, deadline: float, child_environment: dict[str, str]):
        from sentientos.codex_finalize_landing import CodexFinalizeLandingCommandResult
        if hook:
            hook(stage_id, timeout)
        runtime = _successful_runtime(stage_id, command, required)
        object.__setattr__(runtime, "configured_timeout_class", "matrix" if "matrix_summary" in stage_id else "generic")
        object.__setattr__(runtime, "configured_timeout_seconds", timeout)
        object.__setattr__(runtime, "effective_timeout_seconds", timeout)
        return CodexFinalizeLandingCommandResult(stage_id, command, 0, required=required), runtime
    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", fake)
    args = ["finalize", "--title", "x", "--intended-commit-title", "x", "--phase", "pre-commit", "--focused-test-command", "python -c 'pass'", "--task-acceptance-manifest", str(manifest), "--runtime-sandbox-root", str(tmp_path / "runtime"), "--output", str(out)]
    args.extend(extra or [])
    main(args)
    return json.loads(out.read_text())


@pytest.mark.no_legacy_skip
def test_acceptance_evidence_is_captured_before_any_child_stage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest, _, manifest_bytes, _ = _acceptance_fixture(tmp_path)
    def hook(stage: str, timeout: int) -> None:
        captured = next((tmp_path / "runtime" / "invocations").glob("*/task_acceptance/manifest.json"))
        assert captured.read_bytes() == manifest_bytes
    payload = _run_fake_finalizer(monkeypatch, tmp_path, manifest, hook)
    assert payload["task_acceptance_custody"]["initial_verification_status"] == "task_acceptance_ready"


@pytest.mark.no_legacy_skip
def test_invalid_acceptance_blocks_before_matrix_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest, _, _, _ = _acceptance_fixture(tmp_path)
    data = json.loads(manifest.read_text()); data["repository_sha"] = "0" * 40; manifest.write_text(json.dumps(data))
    seen: list[str] = []
    payload = _run_fake_finalizer(monkeypatch, tmp_path, manifest, lambda stage, timeout: seen.append(stage))
    assert seen == []
    assert payload["decision"]["status"] == "repair_required_task_caused"
    assert "repository_sha_mismatch" in payload["decision"]["reasons"]


@pytest.mark.no_legacy_skip
def test_child_stage_overwrite_of_original_provenance_does_not_change_captured_acceptance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest, provenance, _, provenance_bytes = _acceptance_fixture(tmp_path)
    changed = False
    def hook(stage: str, timeout: int) -> None:
        nonlocal changed
        if not changed:
            provenance.write_text('{"valid":"different"}'); changed = True
    payload = _run_fake_finalizer(monkeypatch, tmp_path, manifest, hook)
    custody = payload["task_acceptance_custody"]
    assert custody["terminal_verification_status"] == "task_acceptance_ready"
    assert custody["original_provenance_changed_or_disappeared"] is True
    assert custody["captured_provenance_digest"] == "sha256:" + hashlib.sha256(provenance_bytes).hexdigest()


@pytest.mark.no_legacy_skip
def test_generated_cleanup_can_remove_original_glow_provenance_and_still_reach_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provenance = Path("glow/test_runs/test_run_provenance.json")
    manifest, provenance, _, _ = _acceptance_fixture(tmp_path, provenance)
    monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: ["?? glow/test_runs/test_run_provenance.json"] if provenance.exists() else [])
    def cleanup(lines):
        provenance.unlink(missing_ok=True)
        return {str(provenance): (True, "removed", "generated_artifact_cleanup")}
    monkeypatch.setattr("scripts.codex_finalize_landing._cleanup_generated", cleanup)
    payload = _run_fake_finalizer(monkeypatch, tmp_path, manifest, extra=["--allow-generated-artifact-cleanup"])
    assert payload["decision"]["status"] == "ready_to_commit"
    assert payload["task_acceptance_custody"]["original_provenance_still_exists"] is False
    assert "glow/" in __import__("scripts.codex_finalize_landing", fromlist=["GENERATED_PREFIXES"]).GENERATED_PREFIXES


@pytest.mark.no_legacy_skip
def test_captured_acceptance_tampering_blocks_final_decision(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest, _, _, _ = _acceptance_fixture(tmp_path)
    changed = False
    def hook(stage: str, timeout: int) -> None:
        nonlocal changed
        if not changed:
            path = next((tmp_path / "runtime" / "invocations").glob("*/task_acceptance/provenance.json"))
            path.write_bytes(path.read_bytes() + b" "); changed = True
    payload = _run_fake_finalizer(monkeypatch, tmp_path, manifest, hook)
    assert payload["decision"]["status"] == "repair_required_task_caused"
    assert payload["task_acceptance_custody"]["captured_evidence_unchanged"] is False


@pytest.mark.no_legacy_skip
def test_primary_matrix_uses_independent_matrix_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest, _, _, _ = _acceptance_fixture(tmp_path); seen = {}
    _run_fake_finalizer(monkeypatch, tmp_path, manifest, lambda stage, timeout: seen.setdefault(stage, timeout), ["--stage-timeout-seconds", "7", "--matrix-timeout-seconds", "23"])
    assert seen["matrix_summary"] == 23 and seen["focused_tests"] == 7


@pytest.mark.no_legacy_skip
def test_stale_refresh_matrix_uses_independent_matrix_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest, _, _, _ = _acceptance_fixture(tmp_path); seen: list[tuple[str, int]] = []
    # Force the primary matrix failure while allowing the bounded refresh to pass.
    calls = 0
    def fake(stage: str, command: str, required: bool, progress: bool, timeout: int, deadline: float, child_environment: dict[str, str]):
        nonlocal calls
        from sentientos.codex_finalize_landing import CodexFinalizeLandingCommandResult
        seen.append((stage, timeout)); exit_code = 1 if stage == "matrix_summary" else 0; calls += 1
        return CodexFinalizeLandingCommandResult(stage, command, exit_code, required=required), _successful_runtime(stage, command, required)
    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", fake); monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: [])
    out = tmp_path / "out.json"
    main(["finalize", "--phase", "pre-commit", "--title", "x", "--intended-commit-title", "x", "--focused-test-command", "x", "--task-acceptance-manifest", str(manifest), "--runtime-sandbox-root", str(tmp_path / "runtime"), "--allow-stale-evidence-refresh", "--stage-timeout-seconds", "7", "--matrix-timeout-seconds", "23", "--output", str(out)])
    assert ("matrix_summary", 23) in seen and ("stale_evidence_matrix_summary", 23) in seen and ("focused_tests", 7) in seen


@pytest.mark.no_legacy_skip
def test_finalizer_artifact_records_acceptance_and_timeout_custody(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest, _, manifest_bytes, provenance_bytes = _acceptance_fixture(tmp_path)
    payload = _run_fake_finalizer(monkeypatch, tmp_path, manifest)
    custody = payload["task_acceptance_custody"]
    assert custody["original_manifest_byte_length"] == custody["captured_manifest_byte_length"] == len(manifest_bytes)
    assert custody["original_provenance_byte_length"] == custody["captured_provenance_byte_length"] == len(provenance_bytes)
    assert custody["repository_sha"] and custody["initial_verification_status"] == custody["terminal_verification_status"] == "task_acceptance_ready"
    assert payload["runtime"]["stage_timeout_seconds"] == 900 and payload["runtime"]["matrix_timeout_seconds"] == 2400 and payload["runtime"]["overall_timeout_seconds"] == 5400
    assert next(x for x in payload["runtime"]["stages"] if x["stage_id"] == "matrix_summary")["configured_timeout_class"] == "matrix"


@pytest.mark.no_legacy_skip
def test_finalizer_does_not_mutate_process_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest, _, _, _ = _acceptance_fixture(tmp_path)
    sentinel = '{"sentinel":"unchanged"}'
    monkeypatch.setenv("CODEX_FINALIZER_RUNTIME_ENV", sentinel)
    payload = _run_fake_finalizer(monkeypatch, tmp_path, manifest)
    assert os.environ["CODEX_FINALIZER_RUNTIME_ENV"] == sentinel
    assert payload["runtime_custody"]["process_environment_mutated"] is False


@pytest.mark.no_legacy_skip
def test_child_stages_receive_only_their_invocation_runtime_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest, _, _, _ = _acceptance_fixture(tmp_path)
    seen: list[dict[str, str]] = []
    monkeypatch.setenv("CODEX_FINALIZER_RUNTIME_ENV", '{"SENTIENTOS_DATA_DIR":"sentinel"}')
    monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: [])
    def fake(stage: str, command: str, required: bool, progress: bool, timeout: int, deadline: float, child_environment: dict[str, str]):
        from sentientos.codex_finalize_landing import CodexFinalizeLandingCommandResult
        seen.append(dict(child_environment))
        return CodexFinalizeLandingCommandResult(stage, command, 0, required=required), _successful_runtime(stage, command, required)
    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", fake)
    out = tmp_path / "out.json"
    main(["finalize", "--phase", "pre-commit", "--title", "x", "--intended-commit-title", "x", "--focused-test-command", "x", "--task-acceptance-manifest", str(manifest), "--runtime-sandbox-root", str(tmp_path / "runtime"), "--output", str(out)])
    assert seen and all(item["SENTIENTOS_DATA_DIR"] != "sentinel" for item in seen)
    assert len({tuple(sorted(item.items())) for item in seen}) == 1


def _concurrent_finalizers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    manifests = [_acceptance_fixture(tmp_path / f"source-{i}")[0] for i in range(2)]
    ids = iter(["invocation-a", "invocation-b"])
    monkeypatch.setattr("scripts.codex_finalize_landing._new_invocation_id", lambda: next(ids))
    monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: [])
    barrier = threading.Barrier(2)
    seen: list[dict[str, str]] = []
    seen_lock = threading.Lock()
    def fake(stage: str, command: str, required: bool, progress: bool, timeout: int, deadline: float, child_environment: dict[str, str]):
        from sentientos.codex_finalize_landing import CodexFinalizeLandingCommandResult
        if stage == "preflight_hygiene":
            barrier.wait()
        with seen_lock:
            seen.append(dict(child_environment))
        return CodexFinalizeLandingCommandResult(stage, command, 0, required=required), _successful_runtime(stage, command, required)
    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", fake)
    def run(i: int) -> None:
        main(["finalize", "--phase", "pre-commit", "--title", "x", "--intended-commit-title", "x", "--focused-test-command", "x", "--task-acceptance-manifest", str(manifests[i]), "--runtime-sandbox-root", str(tmp_path / "runtime"), "--output", str(tmp_path / f"out-{i}.json")])
    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    return [json.loads((tmp_path / f"out-{i}.json").read_text()) for i in range(2)], seen


@pytest.mark.no_legacy_skip
def test_concurrent_same_sandbox_finalizers_use_distinct_runtime_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payloads, seen = _concurrent_finalizers(monkeypatch, tmp_path)
    roots = {p["runtime_custody"]["invocation_context"]["resolved_invocation_root"] for p in payloads}
    assert len(roots) == 2
    assert {Path(item["SENTIENTOS_DATA_DIR"]).parent for item in seen} == {Path(root) for root in roots}


@pytest.mark.no_legacy_skip
def test_concurrent_same_sandbox_finalizers_preserve_distinct_acceptance_custody(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payloads, _ = _concurrent_finalizers(monkeypatch, tmp_path)
    paths = {(p["task_acceptance_custody"]["captured_manifest_path"], p["task_acceptance_custody"]["captured_provenance_path"]) for p in payloads}
    assert len(paths) == 2
    for payload in payloads:
        custody = payload["task_acceptance_custody"]
        assert custody["initial_verification_status"] == custody["terminal_verification_status"] == "task_acceptance_ready"
        assert _sha(Path(custody["captured_manifest_path"]).read_bytes()) == custody["captured_manifest_digest"]
        assert _sha(Path(custody["captured_provenance_path"]).read_bytes()) == custody["captured_provenance_digest"]


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@pytest.mark.no_legacy_skip
def test_symlinked_runtime_custody_ancestor_is_rejected_before_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest, _, _, _ = _acceptance_fixture(tmp_path / "source")
    runtime = tmp_path / "runtime"; runtime.mkdir()
    target = Path.cwd() / "symlink-custody-test-target"
    (runtime / "invocations").symlink_to(target)
    seen: list[str] = []
    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", lambda *args, **kwargs: seen.append("stage"))
    out = tmp_path / "out.json"
    main(["finalize", "--phase", "pre-commit", "--title", "x", "--intended-commit-title", "x", "--task-acceptance-manifest", str(manifest), "--runtime-sandbox-root", str(runtime), "--output", str(out)])
    payload = json.loads(out.read_text())
    assert seen == [] and not target.exists()
    assert "symlinked_runtime_custody_component" in payload["runtime_custody"]["runtime_error"]
    assert payload["decision"]["status"] == "repair_required_task_caused"


@pytest.mark.no_legacy_skip
def test_existing_invocation_directory_is_never_reused_or_overwritten(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"; stale = runtime / "invocations" / "stale"
    stale.mkdir(parents=True); sentinel = stale / "sentinel"; sentinel.write_bytes(b"preserve")
    ids = iter(["stale", "fresh"]); monkeypatch.setattr("scripts.codex_finalize_landing._new_invocation_id", lambda: next(ids))
    context = __import__("scripts.codex_finalize_landing", fromlist=["_create_invocation_context"])._create_invocation_context(str(Path.cwd()), str(runtime), "x")
    assert context.invocation_id == "fresh" and context.collision_attempt_count == 1
    assert sentinel.read_bytes() == b"preserve"


@pytest.mark.no_legacy_skip
def test_acceptance_custody_uses_private_exclusive_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest, _, _, _ = _acceptance_fixture(tmp_path)
    payload = _run_fake_finalizer(monkeypatch, tmp_path, manifest)
    custody = payload["task_acceptance_custody"]
    for key in ("captured_manifest_path", "captured_provenance_path"):
        assert stat.S_IMODE(Path(custody[key]).stat().st_mode) == (0o600 if os.name == "posix" else stat.S_IMODE(Path(custody[key]).stat().st_mode))
    context = payload["runtime_custody"]["invocation_context"]
    for key in ("resolved_invocation_root", "child_data_root", "child_state_root", "acceptance_custody_root"):
        assert os.name != "posix" or stat.S_IMODE(Path(context[key]).stat().st_mode) == 0o700


@pytest.mark.no_legacy_skip
def test_finalizer_artifact_binds_invocation_runtime_and_acceptance_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest, _, _, _ = _acceptance_fixture(tmp_path)
    payload = _run_fake_finalizer(monkeypatch, tmp_path, manifest)
    runtime = payload["runtime_custody"]; custody = payload["task_acceptance_custody"]
    assert runtime["invocation_context"]["schema_version"] == "sentientos.finalizer_invocation_context:v1"
    assert runtime["child_environment_digest"].startswith("sha256:")
    assert custody["source_manifest"]["stable_read"] and custody["source_provenance"]["stable_read"]
    assert custody["terminal_file_identity_status"] == "unchanged"


@pytest.mark.no_legacy_skip
def test_generated_cleanup_allowed_refresh_terminal_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = tmp_path / "finalizer.json"
    statuses = iter([["?? glow/test_runs/run.json"], [], []])
    monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: next(statuses, []))
    monkeypatch.setattr(
        "scripts.codex_finalize_landing._cleanup_generated",
        lambda status_lines: {"glow/test_runs/run.json": (True, "removed", "generated_artifact_cleanup")},
    )

    def fake_run_stage(stage_id: str, command: str, required: bool, progress: bool, stage_timeout_seconds: int, overall_deadline: float, child_environment: dict[str, str]):
        from sentientos.codex_finalize_landing import CodexFinalizeLandingCommandResult

        return CodexFinalizeLandingCommandResult(stage_id, command, 0, required=required), _successful_runtime(stage_id, command, required)

    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", fake_run_stage)
    code = main([
        "finalize",
        "--title",
        "x",
        "--intended-commit-title",
        "x",
        "--phase",
        "pre-commit",
        "--focused-test-command",
        "python -c 'pass'",
        "--allow-generated-artifact-cleanup",
        "--allow-stale-evidence-refresh",
        "--max-stale-evidence-refreshes",
        "1",
        "--allow-current-tracked-changes",
        "--output",
        str(out),
        "--summary",
    ])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["decision"]["status"] == "ready_to_commit"
    freshness = payload["evidence_freshness"]
    assert freshness["cleanup_occurred"] is True
    assert freshness["cleaned_paths"] == ["glow/test_runs/run.json"]
    assert freshness["stale_evidence_refresh_attempted"] is False
    assert freshness["stale_evidence_refresh_result"] == "not_required"
    assert freshness["refresh_stage_runs"] == 0
    assert freshness["rerun_required"] is False


@pytest.mark.no_legacy_skip
def test_stale_refresh_required_only_when_not_allowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = tmp_path / "finalizer.json"
    statuses = iter([["?? glow/test_runs/run.json"], [], []])
    monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: next(statuses, []))
    monkeypatch.setattr(
        "scripts.codex_finalize_landing._cleanup_generated",
        lambda status_lines: {"glow/test_runs/run.json": (True, "removed", "generated_artifact_cleanup")},
    )

    def fake_run_stage(stage_id: str, command: str, required: bool, progress: bool, stage_timeout_seconds: int, overall_deadline: float, child_environment: dict[str, str]):
        from sentientos.codex_finalize_landing import CodexFinalizeLandingCommandResult

        exit_code = 1 if stage_id == "matrix_summary" else 0
        return CodexFinalizeLandingCommandResult(stage_id, command, exit_code, required=required), _successful_runtime(stage_id, command, required)

    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", fake_run_stage)
    code = main([
        "finalize",
        "--title",
        "x",
        "--intended-commit-title",
        "x",
        "--phase",
        "pre-commit",
        "--focused-test-command",
        "python -c 'pass'",
        "--allow-generated-artifact-cleanup",
        "--output",
        str(out),
    ])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 1
    assert payload["decision"]["status"] == "stale_evidence_refresh_required"
    assert payload["evidence_freshness"]["stale_evidence_refresh_result"] == "required_not_allowed"
    assert payload["evidence_freshness"]["rerun_required"] is True


@pytest.mark.no_legacy_skip
def test_refresh_failure_is_terminal_without_rerun_suggestion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = tmp_path / "finalizer.json"
    statuses = iter([["?? glow/test_runs/run.json"], [], []])
    monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: next(statuses, []))
    monkeypatch.setattr(
        "scripts.codex_finalize_landing._cleanup_generated",
        lambda status_lines: {"glow/test_runs/run.json": (True, "removed", "generated_artifact_cleanup")},
    )

    def fake_run_stage(stage_id: str, command: str, required: bool, progress: bool, stage_timeout_seconds: int, overall_deadline: float, child_environment: dict[str, str]):
        from sentientos.codex_finalize_landing import CodexFinalizeLandingCommandResult

        exit_code = 1 if stage_id in {"matrix_summary", "stale_evidence_pr_landing_gate"} else 0
        return CodexFinalizeLandingCommandResult(stage_id, command, exit_code, required=required), _successful_runtime(stage_id, command, required)

    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", fake_run_stage)
    code = main([
        "finalize",
        "--title",
        "x",
        "--intended-commit-title",
        "x",
        "--phase",
        "pre-commit",
        "--focused-test-command",
        "python -c 'pass'",
        "--allow-generated-artifact-cleanup",
        "--allow-stale-evidence-refresh",
        "--max-stale-evidence-refreshes",
        "1",
        "--allow-current-tracked-changes",
        "--output",
        str(out),
    ])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 1
    assert payload["decision"]["status"] == "stale_evidence_refresh_failed"
    assert payload["evidence_freshness"]["stale_evidence_refresh_result"] == "failed"
    assert payload["evidence_freshness"]["refresh_stage_runs"] == 2
    assert payload["evidence_freshness"]["rerun_required"] is False


@pytest.mark.no_legacy_skip
def test_dirty_source_blocks_after_cleanup_and_refresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = tmp_path / "finalizer.json"
    statuses = iter([["?? glow/test_runs/run.json", " M sentientos/codex_finalize_landing.py"], [" M sentientos/codex_finalize_landing.py"], [" M sentientos/codex_finalize_landing.py"]])
    monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: next(statuses, [" M sentientos/codex_finalize_landing.py"]))
    monkeypatch.setattr(
        "scripts.codex_finalize_landing._cleanup_generated",
        lambda status_lines: {"glow/test_runs/run.json": (True, "removed", "generated_artifact_cleanup")},
    )

    def fake_run_stage(stage_id: str, command: str, required: bool, progress: bool, stage_timeout_seconds: int, overall_deadline: float, child_environment: dict[str, str]):
        from sentientos.codex_finalize_landing import CodexFinalizeLandingCommandResult

        exit_code = 1 if stage_id == "matrix_summary" else 0
        return CodexFinalizeLandingCommandResult(stage_id, command, exit_code, required=required), _successful_runtime(stage_id, command, required)

    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", fake_run_stage)
    code = main([
        "finalize",
        "--title",
        "x",
        "--intended-commit-title",
        "x",
        "--phase",
        "pre-commit",
        "--focused-test-command",
        "python -c 'pass'",
        "--allow-generated-artifact-cleanup",
        "--allow-stale-evidence-refresh",
        "--output",
        str(out),
    ])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 1
    assert payload["decision"]["status"] == "repair_required_task_caused"
    assert "source_change_not_declared" in payload["decision"]["reasons"]
    assert payload["evidence_freshness"]["refresh_stage_runs"] == 3


@pytest.mark.no_legacy_skip
def test_pre_commit_uses_single_matrix_stage_with_summary_and_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = tmp_path / "finalizer.json"
    monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: [])
    seen: list[tuple[str, str]] = []

    def fake_run_stage(stage_id: str, command: str, required: bool, progress: bool, stage_timeout_seconds: int, overall_deadline: float, child_environment: dict[str, str]):
        from sentientos.codex_finalize_landing import CodexFinalizeLandingCommandResult

        seen.append((stage_id, command))
        return CodexFinalizeLandingCommandResult(stage_id, command, 0, required=required), _successful_runtime(stage_id, command, required)

    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", fake_run_stage)
    code = main([
        "finalize",
        "--title",
        "x",
        "--intended-commit-title",
        "x",
        "--phase",
        "pre-commit",
        "--focused-test-command",
        "python -c 'pass'",
        "--matrix-json-path",
        str(tmp_path / "matrix path;safe.json"),
        "--output",
        str(out),
    ])
    payload = json.loads(out.read_text(encoding="utf-8"))
    matrix_stages = [item for item in seen if item[0].startswith("matrix")]
    assert code == 0
    assert [item[0] for item in matrix_stages] == ["matrix_summary"]
    assert "--summary" in matrix_stages[0][1]
    assert "--output" in matrix_stages[0][1]
    assert "matrix_output" not in [stage["stage_id"] for stage in payload["runtime"]["stages"]]


@pytest.mark.no_legacy_skip
def test_post_commit_exact_reuse_performs_zero_matrix_stages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pre = tmp_path / "pre.json"
    pre.write_text(json.dumps({"workspace_binding": {}}), encoding="utf-8")
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"status": "passed", "required_failure_count": 0}), encoding="utf-8")
    out = tmp_path / "finalizer.json"
    monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: [])
    seen: list[str] = []

    def fake_run_stage(stage_id: str, command: str, required: bool, progress: bool, stage_timeout_seconds: int, overall_deadline: float, child_environment: dict[str, str]):
        from sentientos.codex_finalize_landing import CodexFinalizeLandingCommandResult

        seen.append(stage_id)
        return CodexFinalizeLandingCommandResult(stage_id, command, 0, required=required), _successful_runtime(stage_id, command, required)

    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", fake_run_stage)
    code = main([
        "finalize",
        "--title",
        "x",
        "--intended-commit-title",
        "x",
        "--phase",
        "pr-metadata",
        "--focused-test-command",
        "python -c 'pass'",
        "--pre-commit-finalizer-json",
        str(pre),
        "--matrix-json-path",
        str(matrix),
        "--output",
        str(out),
    ])
    assert not any("matrix" in stage for stage in seen)

@pytest.mark.no_legacy_skip
def test_finalizer_blocks_unsatisfied_task_acceptance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = tmp_path / "finalizer.json"
    provenance = tmp_path / "provenance.json"
    provenance.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"test_provenance_path": str(provenance)}), encoding="utf-8")
    monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: [])
    monkeypatch.setattr("scripts.codex_finalize_landing.verify_task_acceptance", lambda *args, **kwargs: {"status": "task_acceptance_blocked", "reasons": ["required_node_not_passed:x"]})

    def fake_run_stage(stage_id: str, command: str, required: bool, progress: bool, stage_timeout_seconds: int, overall_deadline: float, child_environment: dict[str, str]):
        from sentientos.codex_finalize_landing import CodexFinalizeLandingCommandResult
        return CodexFinalizeLandingCommandResult(stage_id, command, 0, required=required), _successful_runtime(stage_id, command, required)

    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", fake_run_stage)
    code = main(["finalize", "--title", "x", "--intended-commit-title", "x", "--phase", "pre-commit", "--focused-test-command", "python -c 'pass'", "--task-acceptance-manifest", str(manifest), "--output", str(out)])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 1
    assert payload["decision"]["status"] == "repair_required_task_caused"
    assert payload["task_acceptance"]["status"] == "task_acceptance_blocked"
