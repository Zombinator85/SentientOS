from __future__ import annotations

from pathlib import Path

import subprocess

from scripts.compare_validation_runs import _run_one, main, workspace_identity
from sentientos.validation_causality import (
    STATUS_INCOMPLETE,
    compare_runs,
)


def test_timeout_is_recorded_as_incomplete_with_raw_output(monkeypatch, tmp_path: Path) -> None:
    killed: list[tuple[int, int]] = []

    class TimedOutProcess:
        pid = 12345
        returncode = -15

        def __init__(self):
            self.calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(
                    ["pytest"], timeout=5,
                    output=b"collected 2 items", stderr=b"portal stalled",
                )
            return "collected 2 items", "portal stalled"

    def spawn(*args, **kwargs):
        assert kwargs["start_new_session"] is True
        return TimedOutProcess()

    monkeypatch.setattr("scripts.compare_validation_runs.subprocess.Popen", spawn)
    monkeypatch.setattr("scripts.compare_validation_runs.os.killpg", lambda pid, sig: killed.append((pid, sig)))
    run = _run_one(
        root=tmp_path,
        repository_sha="a" * 40,
        source_identity="sha256:" + "1" * 64,
        nodes=["tests/test_x.py"],
        contract=[],
        env_identity={"python": "3.11"},
        label="candidate",
        output_root=tmp_path,
        timeout_seconds=5,
    )

    assert run["complete"] is False
    assert run["exit_code"] == 124
    assert run["raw_stdout_tail"] == "collected 2 items"
    assert run["raw_stderr_tail"] == "portal stalled"
    assert killed == [(12345, 15)]


def test_incomplete_timeout_cannot_be_attributed_as_no_regression() -> None:
    base = {
        "repository_sha": "a" * 40,
        "workspace_identity": "sha256:" + "1" * 64,
        "complete": False,
        "exit_code": 124,
        "tests_collected": 0,
        "tests_executed": 0,
        "normalized_failure_multiset": [],
    }
    candidate = dict(base)
    candidate.update(
        repository_sha="b" * 40,
        workspace_identity="sha256:" + "2" * 64,
        complete=True,
        exit_code=0,
        tests_collected=1,
        tests_executed=1,
    )

    result = compare_runs(
        immutable_base_sha="a" * 40,
        candidate_sha="b" * 40,
        candidate_workspace_identity="sha256:" + "2" * 64,
        base_run=base,
        candidate_run=candidate,
    )

    assert result["status"] == STATUS_INCOMPLETE


def test_workspace_identity_binds_untracked_symlink_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    (repo / "tracked.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    before = workspace_identity(repo, head_sha=head)
    (repo / "candidate-link.py").symlink_to("tracked.py")

    after = workspace_identity(repo, head_sha=head)

    assert before != after


def test_full_suite_comparison_defaults_to_runner_default_selection(monkeypatch, tmp_path: Path) -> None:
    seen = {}

    def compare(**kwargs):
        seen.update(kwargs)
        result = {
            "status": "comparison_incomplete", "comparison_digest": "sha256:" + "1" * 64,
            "matched_preexisting_failures": [], "new_candidate_failures": [],
            "retired_or_improved_failures": [],
        }
        kwargs["output_path"].write_text("{}", encoding="utf-8")
        return result

    monkeypatch.setattr("scripts.compare_validation_runs.compare_repository_runs", compare)
    output = tmp_path / "comparison.json"
    code = main([
        "--repository-root", str(tmp_path), "--candidate-root", str(tmp_path),
        "--base-sha", "a" * 40, "--candidate-sha", "b" * 40,
        "--timeout-seconds", "45", "--output", str(output),
    ])
    assert code == 1
    assert seen["nodes"] == []
    assert output.read_text(encoding="utf-8")
