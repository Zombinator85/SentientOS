from __future__ import annotations

import json
from pathlib import Path

from scripts.codex_finalize_landing import _classify, build_parser, main


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


def test_classify_untracked_task_file_inferred() -> None:
    findings = _classify(["?? tests/test_new_case.py"], (), ("tests/test_new_case.py",))
    assert findings[0].classification == "intended_task_change"


def test_classify_untracked_unknown_root_and_media_blocked() -> None:
    findings = _classify(["?? random.bin", "?? docs/image.png"], (), ())
    assert findings[0].classification == "unknown_dirty_file"
    assert findings[1].classification == "unknown_dirty_file"


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
