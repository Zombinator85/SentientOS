from __future__ import annotations

from queue import Queue

import pytest

from daemon import codex_daemon


class _DummyProcess:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


def _configure_common_paths(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(codex_daemon, "CODEX_SUGGEST_DIR", tmp_path / "suggest")
    monkeypatch.setattr(codex_daemon, "CODEX_PATCH_DIR", tmp_path / "suggest")
    monkeypatch.setattr(codex_daemon, "CODEX_REASONING_DIR", tmp_path / "reason")
    monkeypatch.setattr(codex_daemon, "CODEX_LOG", tmp_path / "codex.log")


def test_run_once_retries_until_max(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(codex_daemon, "CODEX_MODE", "repair")
    monkeypatch.setattr(codex_daemon, "CODEX_MAX_ITERATIONS", 3)
    monkeypatch.setattr(codex_daemon, "CODEX_NOTIFY", [])
    _configure_common_paths(monkeypatch, tmp_path)

    ledger_queue: Queue = Queue()
    captured_logs: list[dict] = []
    monkeypatch.setattr(codex_daemon, "log_activity", lambda entry: captured_logs.append(entry))
    monkeypatch.setattr(codex_daemon, "send_notifications", lambda entry: None)

    apply_calls: list[str] = []
    monkeypatch.setattr(
        codex_daemon,
        "apply_patch",
        lambda diff: apply_calls.append(diff) or True,
    )

    diff_outputs = [
        "--- a/module_one.py\n+++ b/module_one.py\n@@\n-1\n+1\n",
        "--- a/module_two.py\n+++ b/module_two.py\n@@\n-1\n+1\n",
        "--- a/module_three.py\n+++ b/module_three.py\n@@\n-1\n+1\n",
    ]
    codex_calls: list[list[str]] = []

    def fake_subprocess_run(cmd, *args, **kwargs):  # type: ignore[override]
        if cmd[:2] == ["codex", "exec"]:
            index = len(codex_calls)
            codex_calls.append(cmd)
            return _DummyProcess(stdout=diff_outputs[index])
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(codex_daemon.subprocess, "run", fake_subprocess_run)

    diagnostic_calls: list[int] = []
    diagnostic_outputs = [
        (False, "FAILED tests/test_example.py::test_case [0]\n", 1),
        (False, "FAILED tests/test_example.py::test_case [1]\n", 1),
        (False, "FAILED tests/test_example.py::test_case [2]\n", 1),
        (False, "FAILED tests/test_example.py::test_case [3]\n", 1),
    ]

    def fake_run_diagnostics():
        call_index = len(diagnostic_calls)
        diagnostic_calls.append(call_index)
        return diagnostic_outputs[call_index]

    monkeypatch.setattr(codex_daemon, "run_diagnostics", fake_run_diagnostics)

    result = codex_daemon.run_once(ledger_queue)

    assert result is not None
    assert result["outcome"] == "fail"
    assert result["iterations"] == 3
    assert result["final_iteration"] is True
    assert result["max_iterations_reached"] is True
    assert result["files_changed"] == sorted(
        ["module_one.py", "module_two.py", "module_three.py"]
    )

    assert len(codex_calls) == 3
    assert len(apply_calls) == 3
    assert len(diagnostic_calls) == 4
    assert ledger_queue.qsize() == 6
    assert len(captured_logs) == 6

    queue_entries = list(ledger_queue.queue)
    assert [entry["iteration"] for entry in queue_entries] == [1, 1, 2, 2, 3, 3]
    assert queue_entries[-1]["final_iteration"] is True


def test_run_once_succeeds_before_limit(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(codex_daemon, "CODEX_MODE", "repair")
    monkeypatch.setattr(codex_daemon, "CODEX_MAX_ITERATIONS", 3)
    monkeypatch.setattr(codex_daemon, "CODEX_NOTIFY", [])
    _configure_common_paths(monkeypatch, tmp_path)

    ledger_queue: Queue = Queue()
    captured_logs: list[dict] = []
    monkeypatch.setattr(codex_daemon, "log_activity", lambda entry: captured_logs.append(entry))
    notifications: list[dict] = []
    monkeypatch.setattr(codex_daemon, "send_notifications", lambda entry: notifications.append(entry))

    applied_diffs: list[str] = []

    def fake_apply_patch(diff: str) -> bool:
        applied_diffs.append(diff)
        return True

    monkeypatch.setattr(codex_daemon, "apply_patch", fake_apply_patch)

    diff_outputs = [
        "--- a/module_one.py\n+++ b/module_one.py\n@@\n-1\n+1\n",
        "--- a/module_two.py\n+++ b/module_two.py\n@@\n-1\n+1\n",
    ]
    codex_calls: list[list[str]] = []
    git_commands: list[list[str]] = []

    def fake_subprocess_run(cmd, *args, **kwargs):  # type: ignore[override]
        if cmd[:2] == ["codex", "exec"]:
            index = len(codex_calls)
            codex_calls.append(cmd)
            return _DummyProcess(stdout=diff_outputs[index])
        if cmd[0] == "git":
            git_commands.append(cmd)
            return _DummyProcess()
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(codex_daemon.subprocess, "run", fake_subprocess_run)

    diagnostic_calls: list[int] = []
    diagnostic_outputs = [
        (False, "FAILED tests/test_example.py::test_case [0]\n", 1),
        (False, "FAILED tests/test_example.py::test_case [1]\n", 1),
        (True, "2 passed\n", 0),
    ]

    def fake_run_diagnostics():
        call_index = len(diagnostic_calls)
        diagnostic_calls.append(call_index)
        return diagnostic_outputs[call_index]

    monkeypatch.setattr(codex_daemon, "run_diagnostics", fake_run_diagnostics)

    result = codex_daemon.run_once(ledger_queue)

    assert result is not None
    assert result["outcome"] == "success"
    assert result["iterations"] == 2
    assert result["final_iteration"] is True
    assert result["files_changed"] == sorted(["module_one.py", "module_two.py"])
    assert result.get("ci_passed") is True

    assert len(codex_calls) == 2
    assert len(applied_diffs) == 2
    assert len(diagnostic_calls) == 3
    assert len(git_commands) == 2
    assert len(notifications) == 1
    assert ledger_queue.qsize() == 4
    assert len(captured_logs) == 4

    queue_entries = list(ledger_queue.queue)
    assert [entry["iteration"] for entry in queue_entries] == [1, 1, 2, 2]
    assert queue_entries[-1]["event"] == "self_repair"
