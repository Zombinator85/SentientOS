from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


def _write(path: Path, payload: dict[str, object]) -> str:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return str(path)


def test_cli_writes_deterministic_json_and_prints_summary(tmp_path: Path) -> None:
    pre = _write(tmp_path / "pre.json", {"decision": {"status": "ready_to_commit"}, "evidence_freshness": {"rerun_required": False, "stale_evidence_refresh_result": "not_required"}})
    pr = _write(tmp_path / "pr.json", {"decision": {"status": "ready_for_pr_metadata"}, "evidence_freshness": {"rerun_required": False, "terminal_refresh_status": "succeeded"}})
    guard = _write(tmp_path / "guard.json", {"status": "pr_metadata_guard_ready"})
    out = tmp_path / "codex_task_lifecycle_summary.json"
    cmd = [
        sys.executable,
        "scripts/build_codex_task_lifecycle_summary.py",
        "--title",
        "[codex:landing] add Codex task lifecycle summary artifact",
        "--intended-commit-title",
        "[codex:landing] add Codex task lifecycle summary artifact",
        "--pre-commit-finalizer-json",
        pre,
        "--pr-metadata-finalizer-json",
        pr,
        "--matrix-json-path",
        "/tmp/work_item_review_packet_matrix.json",
        "--pr-metadata-guard-json",
        guard,
        "--output",
        str(out),
        "--summary",
    ]
    first = subprocess.run(cmd, check=True, text=True, capture_output=True)
    first_payload = out.read_text(encoding="utf-8")
    second = subprocess.run(cmd, check=True, text=True, capture_output=True)
    assert out.read_text(encoding="utf-8") == first_payload
    summary = json.loads(first_payload)
    assert summary["overall_lifecycle_status"] == "ready_for_pr_publication_handoff"
    assert summary["hosted_publication_custody_status"] == "hosted_publication_not_observed"
    assert summary["exact_hosted_publication_custody"] is False
    assert "ready_for_pr_publication_handoff" in first.stdout
    assert second.returncode == 0


def test_cli_invalid_json_returns_clean_error(tmp_path: Path) -> None:
    pre = tmp_path / "pre.json"
    pre.write_text("not-json", encoding="utf-8")
    pr = _write(tmp_path / "pr.json", {"decision": {"status": "ready_for_pr_metadata"}})
    out = tmp_path / "summary.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_codex_task_lifecycle_summary.py",
            "--title",
            "title",
            "--intended-commit-title",
            "title",
            "--pre-commit-finalizer-json",
            str(pre),
            "--pr-metadata-finalizer-json",
            pr,
            "--matrix-json-path",
            "/tmp/matrix.json",
            "--output",
            str(out),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "codex_task_lifecycle_summary_error" in result.stderr
    assert not out.exists()


def test_lifecycle_requires_exact_hosted_custody_for_terminal_closure(tmp_path: Path) -> None:
    pre = _write(tmp_path / "pre.json", {"decision": {"status": "ready_to_commit"}})
    post = _write(tmp_path / "post.json", {"decision": {"status": "ready_for_pr_metadata"}})
    guard = _write(tmp_path / "guard.json", {"status": "pr_metadata_guard_ready"})
    handoff = _write(tmp_path / "handoff.json", {"status": "pr_publication_handoff_ready"})
    out = tmp_path / "summary.json"
    base = [sys.executable, "scripts/build_codex_task_lifecycle_summary.py", "--title", "title", "--intended-commit-title", "title", "--pre-commit-finalizer-json", pre, "--pr-metadata-finalizer-json", post, "--matrix-json-path", "/tmp/matrix.json", "--pr-metadata-guard-json", guard, "--publication-handoff-json", handoff, "--output", str(out)]

    subprocess.run(base, check=True)
    summary = json.loads(out.read_text())
    assert summary["overall_lifecycle_status"] == "ready_for_external_pr_publication"
    assert summary["exact_hosted_publication_custody"] is False

    custody = _write(tmp_path / "custody.json", {"status": "hosted_publication_custody_verified_exact", "exact_publication_custody": True})
    subprocess.run([*base, "--hosted-publication-custody-json", custody], check=True)
    summary = json.loads(out.read_text())
    assert summary["overall_lifecycle_status"] == "exact_hosted_publication_closed"
    assert summary["exact_hosted_publication_custody"] is True
