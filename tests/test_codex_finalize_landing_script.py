from __future__ import annotations

import pytest
import json
from pathlib import Path

from scripts.codex_finalize_landing import (
    _classify,
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
