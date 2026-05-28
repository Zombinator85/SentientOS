from __future__ import annotations

import json
from pathlib import Path

from scripts.codex_pr_metadata_guard import main

TITLE = "[codex:developer] harden blocked bootstrap and PR metadata gates"


def _write_ready(tmp_path: Path) -> tuple[Path, Path, Path]:
    pre = tmp_path / "pre.json"
    pr = tmp_path / "pr.json"
    matrix = tmp_path / "matrix.json"
    base = {
        "request": {"title": TITLE, "intended_commit_title": TITLE},
        "report": {"commands": [{"stage": "pr_landing_gate", "exit_code": 0}, {"stage": "landing_supervisor", "exit_code": 0}], "artifacts": [{"classification": "clean", "path": "", "action": "none"}]},
        "evidence_freshness": {"stale_evidence_refresh_result": "not_required"},
    }
    pre.write_text(json.dumps(base | {"decision": {"status": "ready_to_commit", "reasons": []}}, sort_keys=True), encoding="utf-8")
    pr.write_text(json.dumps(base | {"decision": {"status": "ready_for_pr_metadata", "reasons": []}}, sort_keys=True), encoding="utf-8")
    matrix.write_text(json.dumps({"status": "passed", "required_failure_count": 0}, sort_keys=True), encoding="utf-8")
    return pre, pr, matrix


def test_script_ready_outputs_json_and_summary(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    pre, pr, matrix = _write_ready(tmp_path)
    code = main([
        "verify",
        "--title", TITLE,
        "--intended-commit-title", TITLE,
        "--pre-commit-finalizer-json", str(pre),
        "--pr-metadata-finalizer-json", str(pr),
        "--matrix-json-path", str(matrix),
        "--summary",
    ])
    out = capsys.readouterr().out
    assert code == 0
    assert '"status": "pr_metadata_guard_ready"' in out
    assert "Codex PR metadata guard decision: pr_metadata_guard_ready" in out


def test_script_missing_pre_commit_exits_nonzero_and_names_proof(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    _, pr, matrix = _write_ready(tmp_path)
    code = main([
        "verify",
        "--title", TITLE,
        "--intended-commit-title", TITLE,
        "--pre-commit-finalizer-json", str(tmp_path / "missing.json"),
        "--pr-metadata-finalizer-json", str(pr),
        "--matrix-json-path", str(matrix),
        "--summary",
    ])
    out = capsys.readouterr().out
    assert code == 1
    assert "pr_metadata_guard_blocked_missing_pre_commit_finalizer" in out
    assert "missing_pre_commit_finalizer" in out
